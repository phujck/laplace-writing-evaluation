from __future__ import annotations
import hashlib
import json

class Recorder:
    def __init__(self, root):
        self.root = root
        self.calls = []
    def save(self, name, value):
        path = self.root/"evidence"/(name+".json")
        path.write_text(json.dumps(value, indent=2, default=str)+"\n", encoding="utf-8")
        return str(path.relative_to(self.root))
    def call(self, name, fn, *args, **kwargs):
        try:
            value = fn(*args, **kwargs)
        except Exception as exc:
            self.save(name, {"outcome": "EXCEPTION", "type": type(exc).__name__,
                             "message": str(exc)})
            raise
        self.calls.append(name)
        self.save(name, {"outcome": "RETURNED", "value": value})
        return value
    def refuses(self, name, exception, fn, *args, **kwargs):
        try:
            fn(*args, **kwargs)
        except exception as exc:
            return self.save(name, {"outcome": "EXPECTED_REFUSAL",
                "type": type(exc).__name__, "message": str(exc),
                "reason": getattr(exc, "reason", None)})
        raise AssertionError(name + ": owner admitted forbidden input")
    @staticmethod
    def digest(path):
        return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()
