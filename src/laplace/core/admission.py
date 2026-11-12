"""Payload admission: the refusal and the shape rules every owner call shares, with no operation table.

  AdmissionRefused       a pure shape refusal (operation, said, requested_by); its cure never observes source or
                         currentness, and a diagnostic over 4,000 characters is truncated with a marker
  request_value          the request facts: attribution is UTF-8 text, the payload is an object, the payload names
                         no other project; returns the payload without ``project``
  admit_attribution      the outer requested attribution may not contradict a literal owner ``by``
  admit_literal_by       a literal owner ``by`` is UTF-8 text and is declared by the schema
  admit_shape            JSON Schema 2020-12 validation, refused with the nearest concrete branch error
  admit_owner_payload    the whole admission of an owner that declares its own contract and accepts no canonical
                         expected tokens (Work review, development source, Work delivery)
  selector_scope         the unique supported selector axis of a ``oneOf`` schema, or None (never an admission)

Every function takes the refusal class from its caller (``refusal=``). The native door passes its own subclass
(writing_declarations.PayloadAdmissionError), whose response names help from the door's declaration table; an owner
keeps the plain refusal, which its HTTP door reports by message. Standard library and jsonschema only; no
import-time effects.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class AdmissionRefused(ValueError):
    """Pure shape refusal; its cure must not observe source/currentness."""
    def __init__(self, operation: str, said: str, *, requested_by: str = ""):
        self.operation, self.requested_by = operation, requested_by
        super().__init__(said if len(said)<=4000 else said[:3930]+" [diagnostic truncated; exact attempt retained when receipt is available]")


def request_value(operation: str, payload: Any, *, project: str, requested_by: Any = "",
                  refusal: type[AdmissionRefused] = AdmissionRefused) -> dict:
    """The request facts every owner call shares; the payload without its bound ``project``."""
    if not isinstance(requested_by,str):
        raise refusal(operation,"Requested attribution must be text")
    try: requested_by.encode("utf-8")
    except UnicodeError as exc: raise refusal(operation,"Requested attribution must be UTF-8 text") from exc
    if not isinstance(payload, Mapping):
        raise refusal(operation, "Operation payload must be an object")
    if "project" in payload and payload["project"] != project:
        raise refusal(operation, "Payload project conflicts with the bound project")
    return {key:item for key,item in payload.items() if key != "project"}


def admit_attribution(operation: str, value: Mapping[str, Any], *, requested_by: str = "",
                      refusal: type[AdmissionRefused] = AdmissionRefused) -> None:
    if requested_by and value.get("by") and requested_by != value["by"]:
        raise refusal(operation,"Outer requested attribution conflicts with literal owner by",requested_by=requested_by)


def owns_by(schema: Mapping[str, Any]) -> bool:
    """Whether the schema (or any of its alternatives) declares a literal owner ``by``."""
    return "by" in schema.get("properties", {}) or any(owns_by(item) for axis in ("anyOf","oneOf","allOf") for item in schema.get(axis,()))


def admit_literal_by(operation: str, payload: Mapping[str, Any], schema: Mapping[str, Any], *,
                     refusal: type[AdmissionRefused] = AdmissionRefused) -> None:
    if "by" in payload and isinstance(payload["by"],str):
        try: payload["by"].encode("utf-8")
        except UnicodeError as exc: raise refusal(operation,"Literal owner attribution must be UTF-8 text") from exc
    if "by" in payload and not owns_by(schema):
        raise refusal(operation,"Literal owner by is not declared for this operation; outer requested attribution belongs in Request.by")


def admit_shape(operation: str, payload: Mapping[str, Any], schema: Mapping[str, Any], *,
                refusal: type[AdmissionRefused] = AdmissionRefused) -> None:
    from jsonschema import Draft202012Validator
    error = next(Draft202012Validator(schema).iter_errors(payload), None)
    if error is not None:
        # A union's concrete branch errors retain useful field/type information.
        while error.context:
            error = min(error.context, key=lambda item:(item.validator in {"const","enum"},
                        -len(item.absolute_path)))
        path = ".".join(map(str,error.absolute_path)) or "payload"
        raise refusal(operation, "Payload rejected at %s: %s; inspect current help for this operation." % (path,error.message))


def admit_owner_payload(operation: str, payload: Any, schema: Mapping[str, Any], *, project: str, requested_by: Any = "",
                        refusal: type[AdmissionRefused] = AdmissionRefused) -> None:
    """Complete owner-call admission for an owner whose contract is ``schema`` and which accepts no canonical
    expected tokens: the same checks, order and words as the native door's admission of that operation."""
    value = request_value(operation, payload, project=project, requested_by=requested_by, refusal=refusal)
    admit_attribution(operation, value, requested_by=requested_by, refusal=refusal)
    admit_literal_by(operation, value, schema, refusal=refusal)
    admit_shape(operation, value, schema, refusal=refusal)
    if value.get("expected"):
        raise refusal(operation, "This owner does not accept canonical expected tokens")


def selector_scope(payload: Mapping[str, Any], schema: Mapping[str, Any]) -> dict | None:
    """A unique supported selector axis of a ``oneOf`` schema, observed through that retained schema (the help
    selector of a recorded refusal's contract). Unsupported extra keys do not become selector authority; multiple
    supported axes or invalid selector values remain unproved. This grants no admission."""
    from jsonschema import Draft202012Validator
    if not isinstance(payload,Mapping) or not isinstance(schema,Mapping):return None
    properties=schema.get('properties')
    if not isinstance(properties,Mapping) or not schema.get('oneOf'):return None
    value={key:item for key,item in payload.items() if key!='project' and key in properties}
    if not value and any(key!='project' for key in payload):return None
    from jsonschema.exceptions import SchemaError
    try:
        Draft202012Validator.check_schema(schema)
        if list(Draft202012Validator(schema).iter_errors(value)):return None
    except (SchemaError,TypeError,ValueError):return None
    return value
