"""A checked public copy of the shared battery instrument's ONE tier guard.

The instrument (evidence/WRITING_CONSOLIDATION_2026-10-03/resume-codex-20261003/provider_contact.py,
Git blob a98ac7813ca561b377136fb8f8b764ab41c0eae2) contacts providers and lives in private evidence that a
sparse or exported tree does not carry. Its tier_guard makes no contact: it only resolves a tier through
laplace.pipeline.schema and admits it. This file holds that function verbatim, so the local tier rules are
tested without provider contact or evidence imports. TIER_GUARD_SHA256 is the sha256 of the function's
exact source text; tests/test_writing_provider_tiers.py compares it with the instrument whenever the
instrument is present.
"""
from pathlib import Path

TIER_GUARD_SHA256 = "f9669f6a0e2cdcc9e2b49aa56ac65084987be3d861b36a0232b8ee4899d3017b"


def tier_guard(args):
 """The instrument's economy guard, stated as a TIER instead of two model literals.

 S1 finding F1 and residual R2: the literal here ('This smoke permits only Codex
 gpt-5.6-luna low or Claude haiku low; no fallback.') meant the campaign's own acceptance
 battery could not measure ANY tier above light, so the orchestrator's Sonnet re-run of the
 refused structural case was refused by the instrument itself - a tier table with no
 instrument that can compare tiers is a render without rows.  The economy is kept, and kept
 in ONE place: the floor tier is the 'test' role's own tier (schema.ROLE_TIER), a tier above
 it needs an authorisation FILE that exists, and the file's path is banked on every call row
 this run makes, so a per-plan ceiling can count unauthorised rows only."""
 from laplace.pipeline import schema
 if args.provider not in ('codex','claude'):raise ValueError(f'Unknown provider {args.provider!r}.')
 expected=schema.tier_model(args.tier,args.provider)
 if args.model!=expected:raise ValueError(f'The {args.tier} tier resolves to {expected!r} for {args.provider}, not {args.model!r}; name a tier, not a model.')
 floor=schema.role_tier('test')
 if args.tier!=floor and not (args.authorised_by and Path(args.authorised_by).is_file()):
  raise ValueError(f'The {args.tier} tier is above the economy floor ({floor}); pass --authorised-by <an existing authorisation file>.')
 if args.tier==floor and args.effort!=schema.tier_effort(floor):
  raise ValueError(f'The {floor} tier runs at effort {schema.tier_effort(floor)!r}, not {args.effort!r}.')
 return {'tier':args.tier,'model':expected,'effort':args.effort,
         'authorised_by':str(Path(args.authorised_by).resolve()) if args.authorised_by else None}
