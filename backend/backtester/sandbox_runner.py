"""Strategy process: parent side (StrategyProcess) and child side (__main__).

THIS IS NOT A SECURITY BOUNDARY. The child is an OS subprocess with an AST filter,
reduced builtins, an empty environment, rlimits (CPU, memory, no forking, no file
writes) and a hard wall-clock deadline. That contains accidents (infinite loops,
memory blow-ups, crashes, garbage output). It does NOT contain hostile code: there is
no network or filesystem namespace. Untrusted public code needs a real isolated runner
(container/VM: no network, read-only FS, non-root, no secrets) -- until then the API
keeps ALLOW_CUSTOM_CODE off and only built-in strategies run. See README "Security".

Protocol (newline-delimited JSON on stdin/stdout):
  parent -> {"code": "..."}             child -> {"ok": true} | {"error": "..."}
  parent -> {"bar": {...}, "indicators": {...}}   child -> {"decision": "..."} | {"error": "..."}
"""
import ast
import json
import os
import select
import signal
import subprocess
import sys
import time

DECISIONS = {"BUY", "SELL", "HOLD"}
ALLOWED_IMPORTS = {"math"}
MAX_LINE_BYTES = 4096


# ---------------------------------------------------------------- child side

def check_code(code):
    """Defence in depth only. Returns an error string or None."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"Syntax error on line {e.lineno}: {e.msg}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(a.name not in ALLOWED_IMPORTS for a in node.names):
            return "Only 'import math' is allowed"
        if isinstance(node, ast.ImportFrom) and node.module not in ALLOWED_IMPORTS:
            return "Only 'import math' is allowed"
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            return f"Access to private attribute '{node.attr}' is not allowed"
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            return f"Use of '{node.id}' is not allowed"
    if not any(isinstance(n, ast.FunctionDef) and n.name == "on_bar" for n in tree.body):
        return "Strategy must define on_bar(bar, indicators, state)"
    return None


def _child_main():
    import builtins
    import math

    def send(obj):
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()

    code = json.loads(sys.stdin.readline())["code"]
    err = check_code(code)
    if err:
        return send({"error": err})
    safe_builtins = {n: getattr(builtins, n) for n in (
        "abs", "all", "any", "bool", "dict", "enumerate", "float", "int", "len", "list", "max",
        "min", "range", "round", "sorted", "str", "sum", "tuple", "zip", "isinstance")}
    safe_builtins["__import__"] = lambda name, *a, **k: math if name == "math" else None
    ns = {"__builtins__": safe_builtins}
    try:
        exec(code, ns)
    except Exception as e:
        return send({"error": f"Failed to load strategy: {type(e).__name__}: {e}"})
    on_bar, state = ns["on_bar"], {}
    send({"ok": True})
    for line in sys.stdin:
        msg = json.loads(line)
        try:
            decision = on_bar(msg["bar"], msg["indicators"], state)
        except Exception as e:
            return send({"error": f"on_bar raised {type(e).__name__}: {e}"})
        send({"decision": decision if isinstance(decision, str) else repr(decision)[:50]})


# ---------------------------------------------------------------- parent side

def _limit_child(cpu_seconds, memory_bytes):
    def apply():
        import resource
        limits = [
            (resource.RLIMIT_CPU, cpu_seconds),
            (resource.RLIMIT_AS, memory_bytes),
            (resource.RLIMIT_FSIZE, 0),
            (resource.RLIMIT_NPROC, 0),
            (resource.RLIMIT_CORE, 0),
        ]
        for res, value in limits:
            try:
                resource.setrlimit(res, (value, value))
            except (ValueError, OSError):
                pass  # ponytail: some limits (RLIMIT_AS on macOS) are unsupported; Linux enforces them
    return apply


class StrategyProcess:
    """One child per backtest. The whole run shares one wall-clock deadline."""

    def __init__(self, code, timeout_s=60, cpu_s=30, memory_mb=256):
        from backtester.engine import StrategyError
        self.StrategyError = StrategyError
        self.deadline = time.monotonic() + timeout_s
        self.proc = subprocess.Popen(
            [sys.executable, "-I", "-S", os.path.abspath(__file__)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env={}, cwd="/", start_new_session=True,
            preexec_fn=_limit_child(cpu_s, memory_mb * 1024 * 1024),
        )
        self._buf = b""
        self._send({"code": code})
        reply = self._recv()
        if "error" in reply:
            self.close()
            raise StrategyError(reply["error"])

    def decide(self, bar, indicators):
        self._send({"bar": bar, "indicators": indicators})
        reply = self._recv()
        if "error" in reply:
            raise self.StrategyError(reply["error"])
        decision = reply.get("decision")
        if decision not in DECISIONS:
            raise self.StrategyError(f"on_bar must return BUY, SELL or HOLD, got {str(decision)[:50]!r}")
        return decision

    def _send(self, obj):
        try:
            self.proc.stdin.write((json.dumps(obj) + "\n").encode())
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            raise self.StrategyError("Strategy process exited unexpectedly") from None

    def _recv(self):
        fd = self.proc.stdout.fileno()
        while b"\n" not in self._buf:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise self.StrategyError("Strategy exceeded its time limit")
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                continue
            chunk = os.read(fd, MAX_LINE_BYTES)
            if not chunk:
                raise self.StrategyError("Strategy process exited unexpectedly (crash or resource limit)")
            self._buf += chunk
            if len(self._buf) > MAX_LINE_BYTES:
                raise self.StrategyError("Strategy produced too much output")
        line, self._buf = self._buf.split(b"\n", 1)
        try:
            reply = json.loads(line)
        except ValueError:
            raise self.StrategyError("Strategy produced malformed output") from None
        if not isinstance(reply, dict):
            raise self.StrategyError("Strategy produced malformed output")
        return reply

    def close(self):
        try:
            os.killpg(self.proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        self.proc.wait()
        for f in (self.proc.stdin, self.proc.stdout):
            try:
                f.close()
            except OSError:
                pass


if __name__ == "__main__":
    _child_main()
