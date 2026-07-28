import sys
import json
import ast

ALLOWED_IMPORTS = {'math'}

def is_code_safe(code_str):
    """Parse the code and reject it if it imports anything not whitelisted."""
    tree = ast.parse(code_str)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in ALLOWED_IMPORTS:
                    return False, f"Import not allowed: {alias.name}"
        if isinstance(node, ast.ImportFrom):
            if node.module not in ALLOWED_IMPORTS:
                return False, f"Import not allowed: {node.module}"
    return True, None


def main():
    # Read the user's code from the first argument (a file path)
    code_path = sys.argv[1]
    with open(code_path, 'r') as f:
        user_code = f.read()

    safe, error = is_code_safe(user_code)
    if not safe:
        print(json.dumps({"error": error}))
        sys.stdout.flush()
        return

    # Execute the user's code in a restricted namespace to define on_bar
    restricted_globals = {"__builtins__": {
        "len": len, "range": range, "abs": abs, "min": min, "max": max,
        "sum": sum, "float": float, "int": int, "str": str, "bool": bool,
        "True": True, "False": False, "None": None,
    }}
    local_namespace = {}

    try:
        exec(user_code, restricted_globals, local_namespace)
    except Exception as e:
        print(json.dumps({"error": f"Failed to load strategy: {str(e)}"}))
        sys.stdout.flush()
        return

    on_bar = local_namespace.get('on_bar')
    if on_bar is None:
        print(json.dumps({"error": "No on_bar function defined"}))
        sys.stdout.flush()
        return

    state = {}

    # Main loop: read one bar per line from stdin, call on_bar, print decision
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        bar = json.loads(line)
        try:
            decision = on_bar(bar, state)
        except Exception as e:
            decision = "HOLD"  # fail safe: if user code errors on one bar, don't crash the whole run

        print(json.dumps({"decision": decision}))
        sys.stdout.flush()  # critical: without this, the engine won't see the output right away


if __name__ == "__main__":
    main()