"""The identity gate — the challenge half of the identity defence (soul/0012).

His rulings (2026-08-03b, in-session): friction is the enemy; a hard stop is
weighted by certainty x potential damage; lockout must be impossible; the
refusal is SILENT about what was expected. The challenge is the standing
greeting returned as a question — deniable as house idiom. Only the author
knows it is a challenge. A refusal names the refusal, never the gate.

The organ is the instrument, not the enforcer: it stores the seeded digests,
verifies candidate answers, and banks every firing to the ledger so the
thresholds tune from data (there is no science for the weighting yet — so
instrument it). The operator wields it at the tiers named in soul/0012; the
tier list is deliberately not enumerated here.

Storage: ``soul/identity_seed.json`` — salt + digests only, no plaintext,
sealed with the rest of soul/ at every boundary that travels. Firings append
to ``contract/identity_firings.jsonl``.

Matching is over the NORMALIZED KERNEL, never bytes: lowercase, strip
punctuation and filler, light stemming, sorted unique content words. A reply
CONTAINING the kernel clears (subset search over the reply's words), so no
formulation needs remembering precisely. Lockout is impossible by
construction: a failed challenge refuses the protected classes only, the
session continues, and the author can always delete and re-seed the file.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

SEED_REL = "soul/identity_seed.json"
FIRINGS_REL = "contract/identity_firings.jsonl"

#: filler dropped before hashing — small and fixed; changing it invalidates seeds.
_STOPWORDS = frozenset(
    "a an and are as at be but by for from has have i if in is it its me my of on or "
    "our so that the their there this to was we will with you your".split()
)

#: max content words considered from a reply, and max kernel size searched.
#: Bounds the subset search (C(12, <=6) is small) and forces challenge answers
#: to be answers, not essays.
_MAX_REPLY_WORDS = 12
_MAX_KERNEL = 6


def _stem(word: str) -> str:
    """Light, deterministic stemming — plural/verbal suffixes only."""
    if word.endswith("ies") and len(word) >= 6:
        return word[:-3] + "y"
    if word.endswith("es") and len(word) >= 5 and (
            word[:-2].endswith(("s", "x", "z", "ch", "sh"))):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) >= 4:
        return word[:-1]
    for suf in ("ing", "ed"):
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            return word[: -len(suf)]
    return word


def kernel(text: str) -> tuple[str, ...]:
    """The normalized content-word kernel: what the hash is computed over."""
    words = re.findall(r"[a-z]+", text.lower())
    content = [_stem(w) for w in words if w not in _STOPWORDS]
    return tuple(sorted(set(content)))


def _digest(salt: str, words: tuple[str, ...]) -> str:
    return hashlib.sha256((salt + "\x1f" + "\x1f".join(words)).encode()).hexdigest()


def _seed_path(repo_root: Path | str = ".") -> Path:
    return Path(repo_root) / SEED_REL


def load_seed(repo_root: Path | str = ".") -> dict[str, Any] | None:
    p = _seed_path(repo_root)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - an unreadable seed is a disarmed gate, never a crash
        return None


def armed(repo_root: Path | str = ".") -> bool:
    seed = load_seed(repo_root)
    return bool(seed and seed.get("digests"))


def seed(phrases: list[str], repo_root: Path | str = ".") -> dict[str, Any]:
    """Seed the gate: hash each phrase's kernel under a fresh salt. Plaintext
    is consumed here and never stored; the caller is responsible for how the
    plaintext reached this call (stdin, never a repo file)."""
    salt = secrets.token_hex(16)
    kernels = [kernel(p) for p in phrases if kernel(p)]
    if not kernels:
        raise ValueError("no seedable content in the given phrases")
    over = [k for k in kernels if len(k) > _MAX_KERNEL]
    if over:
        raise ValueError(
            f"kernel too long to ever verify (> {_MAX_KERNEL} content words): "
            f"{len(over)} phrase(s) — a shorter phrase, or nothing, seeds")
    digests = sorted({_digest(salt, k) for k in kernels})
    obj = {
        "salt": salt,
        "digests": digests,
        "seeded": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": "salted kernel digests only - no plaintext, by design (soul/0012)",
    }
    p = _seed_path(repo_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1) + "\n", encoding="utf-8")
    return {"digests": len(digests), "path": str(p)}


def verify(reply: str, repo_root: Path | str = ".") -> bool:
    """True iff the reply CONTAINS a seeded kernel. Subset search over the
    reply's content words gives formulation tolerance with hashes only.
    A disarmed gate verifies nothing (returns False) — the operator treats
    disarmed as log-only, never as a pass."""
    s = load_seed(repo_root)
    if not s or not s.get("digests"):
        return False
    salt, digests = s["salt"], set(s["digests"])
    words = kernel(reply)[:_MAX_REPLY_WORDS]
    for k in range(1, min(len(words), _MAX_KERNEL) + 1):
        for combo in combinations(words, k):
            if _digest(salt, tuple(sorted(combo))) in digests:
                return True
    return False


def log_firing(trigger_class: str, certainty: float, damage: float, outcome: str,
               note: str = "", repo_root: Path | str = ".") -> dict[str, Any]:
    """Bank a firing: the instrumentation his ruling asked for. outcome is one
    of cleared / refused / log-only. The ledger is how thresholds get tuned."""
    rec = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kind": "identity-firing",
        "trigger_class": trigger_class,
        "certainty": round(float(certainty), 2),
        "damage": round(float(damage), 2),
        "outcome": outcome,
        "armed": armed(repo_root),
        "note": note,
    }
    p = Path(repo_root) / FIRINGS_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def main(argv: list[str] | None = None) -> int:
    """CLI. ``seed`` reads phrases from stdin (one per line — plaintext never
    appears in argv or a file); ``verify`` reads one candidate line from stdin
    and exits 0/1 silently (the silence ruling holds even here); ``status``
    prints armed/disarmed only."""
    args = list(sys.argv[1:] if argv is None else argv)
    root = os.environ.get("LAPLACE_REPO_ROOT", ".")
    if not args or args[0] not in ("seed", "verify", "status"):
        print("usage: identity_gate seed|verify|status  (input via stdin)")
        return 2
    if args[0] == "seed":
        phrases = [ln.strip() for ln in sys.stdin.read().splitlines() if ln.strip()]
        out = seed(phrases, root)
        print(f"seeded {out['digests']} digest(s) -> {out['path']}")
        return 0
    if args[0] == "verify":
        return 0 if verify(sys.stdin.read(), root) else 1
    print("armed" if armed(root) else "disarmed (log-only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
