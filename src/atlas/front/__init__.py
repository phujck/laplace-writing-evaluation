"""Supported optional research front door; importing this namespace is inert.

``python -m atlas.front --help`` describes the existing command without loading
numeric dependencies. Public exports stay lazy and retain their original owners.
The whole FrontDoor composes stored records, graded trees and range readers;
the narrow typed projection is not proof of whole-front or scientific acceptance.
See README.md beside this module for input/state/currentness and cost boundaries.
"""
from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "FrontDoor": "door", "run_dataset": "door", "run_front_door": "door",
    "DECLARED_DRAW": "draw", "runs_of_the_draw": "draw",
    "LoadedLens": "faces", "load_persisted_lens": "faces",
    "CompiledQuestion": "question", "QuestionSpec": "question", "compile_question": "question",
    "ReadResult": "read", "resolve_handles": "read",
    "FrontDoorReceipt": "receipts", "StageReceipt": "receipts",
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module("." + _EXPORTS[name], __name__), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))


# The read FUNCTION is not exported: atlas.front.read remains the submodule.
