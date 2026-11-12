"""Receipt-only serving contract for Atlas mathematical instruments.

An instrument is a declared-dial projection over a banked computation.  This reader verifies
the detached receipt custody and the receipt's named input digests, then returns a bounded
projection for the interface.  It never imports or invokes the producer: a GET may hash the
banked inputs when the board cache rebuilds, but it can never eigensolve, embed, or repour.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REGISTRY: dict[str, dict[str, Any]] = {
    "diffusion-scissors/1": {
        "receipt": "evidence/DIFFUSION_SCISSORS_2026-08-25/RECEIPT.json",
        "custody_sidecar": "evidence/DIFFUSION_SCISSORS_2026-08-25/RECEIPT.sha256",
        "producer": "evidence/DIFFUSION_SCISSORS_2026-08-25/scissors.py",
        "preimage": [
            "VERDICT-20260824-card2-honest-geometry-walked",
            "RUL-20260825-metric-is-a-diffusion-filter",
        ],
        "reader": "Gerard exploring a banked geometry through declared dials",
        "retirement": (
            "superseded per instrument when this view graduates into a receipt-gated face tier"
        ),
        "derived_channels": [
            "legacy_sha_slices_g1",
            "codex_spectral_preview_k114",
            "intrinsic_kmeans_k114",
            "intrinsic_kmeans_k12",
        ],
        "non_claim": (
            "an instrument view over one banked generation; it does not promote a partition, "
            "prove the Atlas face, or discharge T2/T3"
        ),
    },
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _load_json(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, f"{path}: {type(exc).__name__}: {exc}"
    if not isinstance(value, dict):
        return {}, f"{path}: receipt root is {type(value).__name__}, expected object"
    return value, None


def _expected_sidecar(path: Path) -> tuple[str | None, str | None]:
    try:
        token = path.read_text(encoding="utf-8").split()[0]
    except (OSError, IndexError) as exc:
        return None, f"{path}: {type(exc).__name__}: {exc}"
    token = token.removeprefix("sha256:")
    if len(token) != 64 or any(c not in "0123456789abcdef" for c in token.lower()):
        return None, f"{path}: malformed sha256 token"
    return token.lower(), None


def source_paths(repo_root: Path | str, instrument_id: str | None = None) -> tuple[str, ...]:
    """Every file whose movement invalidates an instrument serve, without running a producer."""
    root = Path(repo_root)
    ids = [instrument_id] if instrument_id else sorted(REGISTRY)
    paths: set[str] = set()
    for iid in ids:
        spec = REGISTRY.get(iid)
        if not spec:
            continue
        receipt_rel = str(spec["receipt"])
        paths.update((receipt_rel, str(spec["custody_sidecar"])))
        receipt, error = _load_json(root / receipt_rel)
        if error:
            continue
        store = str((receipt.get("dials") or {}).get("corpus_store") or "").strip("/")
        for name in (receipt.get("input_sha256") or {}):
            if store and isinstance(name, str) and name and "/" not in name:
                paths.add(f"{store}/{name}")
    return tuple(sorted(paths))


def project(repo_root: Path | str, instrument_id: str) -> dict[str, Any]:
    """Verify and project one registered receipt.  All failures are named data, never raises."""
    root = Path(repo_root)
    spec = REGISTRY.get(instrument_id)
    if spec is None:
        return {"instrument": instrument_id, "status": "RED",
                "errors": [f"instrument {instrument_id!r} is not registered"]}

    receipt_rel = str(spec["receipt"])
    sidecar_rel = str(spec["custody_sidecar"])
    receipt_path = root / receipt_rel
    receipt, receipt_error = _load_json(receipt_path)
    errors = [receipt_error] if receipt_error else []

    observed_receipt = None
    custody_status = "RED"
    expected_receipt, sidecar_error = _expected_sidecar(root / sidecar_rel)
    if sidecar_error:
        errors.append(sidecar_error)
    if not receipt_error:
        try:
            observed_receipt = _sha256(receipt_path)
        except OSError as exc:
            errors.append(f"{receipt_path}: {type(exc).__name__}: {exc}")
    if expected_receipt and observed_receipt:
        custody_status = "PASS" if expected_receipt == observed_receipt else "FAIL"
        if custody_status == "FAIL":
            errors.append("receipt bytes disagree with the detached custody sha256")

    input_rows: list[dict[str, Any]] = []
    dials = receipt.get("dials") or {}
    store = str(dials.get("corpus_store") or "").strip("/")
    raw_inputs = receipt.get("input_sha256") or {}
    if not isinstance(raw_inputs, dict) or not raw_inputs:
        errors.append("receipt has no input_sha256 map")
    else:
        for name, expected in sorted(raw_inputs.items()):
            rel = f"{store}/{name}" if store else str(name)
            path = root / rel
            observed = None
            try:
                observed = _sha256(path)
            except OSError as exc:
                errors.append(f"{path}: {type(exc).__name__}: {exc}")
            state = "PASS" if observed and observed == expected else "FAIL"
            if state == "FAIL" and observed:
                errors.append(f"{rel}: input digest moved since the instrument was minted")
            input_rows.append({
                "path": rel,
                "expected": f"sha256:{expected}",
                "observed": f"sha256:{observed}" if observed else None,
                "status": state,
            })

    if custody_status != "PASS":
        status = "CUSTODY-RED"
    elif not input_rows or any(row["status"] != "PASS" for row in input_rows):
        status = "STALE-RED"
    elif receipt.get("instrument") != instrument_id:
        status = "RED"
        errors.append("receipt instrument id disagrees with the registry key")
    else:
        status = "CURRENT"

    series = []
    for raw_t, values in (receipt.get("results", {}).get("per_t", {}) or {}).items():
        try:
            t = float(raw_t)
        except (TypeError, ValueError):
            errors.append(f"non-numeric diffusion dial {raw_t!r}")
            continue
        if not isinstance(values, dict):
            errors.append(f"dial {raw_t!r} has no channel object")
            continue
        series.append({"t": int(t) if t.is_integer() else t, **values})
    series.sort(key=lambda row: row["t"])

    return {
        "class": "INSTRUMENT",
        "instrument": instrument_id,
        "status": status,
        "registry": {
            "preimage": list(spec["preimage"]),
            "reader": spec["reader"],
            "retirement": spec["retirement"],
        },
        "receipt": receipt_rel,
        "receipt_content_handle": f"sha256:{observed_receipt}" if observed_receipt else None,
        "custody": {"status": custody_status, "sidecar": sidecar_rel},
        "inputs": input_rows,
        "producer": spec["producer"],
        "preimage": list(spec["preimage"]),
        "reader": spec["reader"],
        "retirement": spec["retirement"],
        "generation": dials.get("generation"),
        "graph": dials.get("graph", {}),
        "operator": dials.get("operator", {}),
        "solver": dials.get("solver", {}),
        "dial": "diffusion t",
        "dial_values": dials.get("t_sweep", []),
        "channel_class": "DERIVED",
        "derived_channels": list(spec["derived_channels"]),
        "series": series,
        "fidelity_preview_vs_real_ari": receipt.get("fidelity_preview_vs_real_ari"),
        "fidelity_k_sub": receipt.get("fidelity_k_sub"),
        "eigenvalues_head": receipt.get("eigenvalues_head", []),
        "non_claim": spec["non_claim"],
        "renew": f"/usr/bin/python3 {spec['producer']}",
        "census": {
            "organ": f"instrument:{instrument_id}",
            "status": status,
            "receipt": receipt_rel,
        },
        "errors": [error for error in errors if error],
    }
