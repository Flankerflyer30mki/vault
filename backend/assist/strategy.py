"""Description → validated spec, with repair (D-080). No Django models here: the worker and the evaluation both call
generate() with a provider.

The model's answer is untrusted data. It must be one JSON object; an "ok" answer's spec goes through spec.validate, the
same allowlist that checks hand-built strategies. Validation errors (keyed by path) go back to the model, at most
`max_repairs` times. Nothing the model writes is ever executed.
"""
import json
from dataclasses import dataclass, field

from assist import prompts
from backtester import spec

MAX_NAME = 60
MAX_NOTES, MAX_NOTE_CHARS, MAX_REASON_CHARS = 5, 300, 500


class Stopped(Exception):
    """The worker is shutting down; checked before each model call."""


@dataclass
class Outcome:
    kind: str  # "spec" | "unsupported" | "invalid"
    spec: dict | None = None
    name: str = ""
    notes: list = field(default_factory=list)
    reason: str = ""
    errors: dict = field(default_factory=dict)
    calls: int = 0
    repair_rounds: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    first_try_valid: bool = False
    answers: list = field(default_factory=list)  # raw model texts, for evaluation and debugging

    def result(self):
        if self.kind == "spec":
            return {"spec": self.spec, "name": self.name, "notes": self.notes}
        if self.kind == "unsupported":
            return {"reason": self.reason}
        return {"errors": self.errors}


def parse_answer(text):
    """The first JSON object in the text. Tolerates code fences and stray prose around it; anything else is an error."""
    text = (text or "").strip()
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(obj, dict):
        raise ValueError("not a JSON object")
    return obj


def _clean_text(v, limit):
    return " ".join(v.split())[:limit] if isinstance(v, str) else ""


def check_answer(obj):
    """Returns ("spec", normalised spec, name, notes) / ("unsupported", reason) or raises spec.SpecError."""
    status = obj.get("status")
    if status == "unsupported":
        reason = _clean_text(obj.get("reason"), MAX_REASON_CHARS)
        if not reason:
            raise spec.SpecError({"reason": "must say what isn't supported"})
        return ("unsupported", reason)
    if status != "ok":
        raise spec.SpecError({"status": 'must be "ok" or "unsupported"'})
    if "spec" not in obj:
        raise spec.SpecError({"spec": "is missing"})
    try:
        normalised = spec.validate(obj["spec"])
    except spec.SpecError as e:  # paths relative to the whole answer, so the model sees where to fix
        raise spec.SpecError({k if k == "spec" else f"spec.{k}": v for k, v in e.errors.items()}) from None
    notes = obj.get("notes") if isinstance(obj.get("notes"), list) else []
    notes = [n for n in (_clean_text(x, MAX_NOTE_CHARS) for x in notes) if n][:MAX_NOTES]
    name = _clean_text(obj.get("name"), MAX_NAME) or "AI strategy"
    return ("spec", normalised, name, notes)


def generate(provider, description, variant="full", max_repairs=2, should_stop=lambda: False):
    msgs = prompts.messages(description, variant)
    out = Outcome(kind="invalid")
    for attempt in range(max_repairs + 1):
        if should_stop():
            raise Stopped()
        c = provider.complete(msgs)
        out.calls += 1
        out.tokens_in += c.tokens_in
        out.tokens_out += c.tokens_out
        out.answers.append(c.text)
        try:
            checked = check_answer(parse_answer(c.text))
        except ValueError:
            errors = {"answer": "must be a single JSON object"}
        except spec.SpecError as e:
            errors = e.errors
        else:
            out.first_try_valid = attempt == 0
            if checked[0] == "unsupported":
                out.kind, out.reason = "unsupported", checked[1]
            else:
                out.kind, out.spec, out.name, out.notes = "spec", checked[1], checked[2], checked[3]
            return out
        out.errors = errors
        if attempt == max_repairs:
            break
        msgs = msgs + [{"role": "assistant", "content": c.text},
                       {"role": "user", "content": prompts.repair_message(errors)}]
        out.repair_rounds += 1
    return out
