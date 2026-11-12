"""The spec business model's arithmetic — one source, everything recomputes.

Reads ``site_exports/registers/deck/model.json`` (the SPEC dials, each with
its derivation and bracket) and derives every projected figure the deck and
the analysis document serve. No projected number is typed anywhere else: the
documents interpolate from here, so the model file and the served pages can
never drift.

The chain, per scenario (bear/base/bull):
  monthly saving   = spend × overhead_share × overhead_reduction
  gainshare rev/yr = monthly saving × 12 × gainshare
  unit ARR         = gainshare rev/yr + platform fee
  year-N revenue   = unit ARR × deployments_yN

``python3 scripts/spec_model.py`` prints the derived table.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODEL = REPO / "site_exports" / "registers" / "deck" / "model.json"

SCEN = ("bear", "base", "bull")


def dials() -> dict:
    return json.loads(MODEL.read_text(encoding="utf-8"))["dials"]


def derive() -> dict:
    d = dials()
    out: dict = {s: {} for s in SCEN}
    for i, s in enumerate(SCEN):
        spend = d["client_monthly_model_spend_gbp"]["value"][i]
        share = d["context_overhead_share"]["value"][i]
        red = d["overhead_reduction"]["value"][i]
        gs = d["gainshare"]["value"][i]
        fee = d["platform_fee_annual_gbp"]["value"][i]
        saving_mo = spend * share * red
        gs_yr = saving_mo * 12 * gs
        unit_arr = gs_yr + fee
        o = out[s]
        o["spend_mo"] = spend
        o["saving_mo"] = saving_mo
        o["gainshare_yr"] = gs_yr
        o["unit_arr"] = unit_arr
        for yk, dk in (("y1", "deployments_y1"), ("y2", "deployments_y2"),
                       ("y3", "deployments_y3")):
            n = d[dk]["value"][i]
            o[f"n_{yk}"] = n
            o[f"rev_{yk}"] = unit_arr * n
    return out


def _gbp(n: float) -> str:
    if n >= 950_000:
        return f"£{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"£{round(n / 1000)}k"
    return f"£{round(n)}"


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def values() -> dict[str, str]:
    """Formatted strings for <mv key=.../> interpolation — deck + documents."""
    d = dials()
    m = derive()
    v: dict[str, str] = {}
    for s in SCEN:
        o = m[s]
        v[f"{s}_spend_mo"] = _gbp(o["spend_mo"])
        v[f"{s}_saving_mo"] = _gbp(o["saving_mo"])
        v[f"{s}_unit_arr"] = _gbp(o["unit_arr"])
        for yk in ("y1", "y2", "y3"):
            v[f"{s}_n_{yk}"] = str(o[f"n_{yk}"])
            v[f"{s}_rev_{yk}"] = _gbp(o[f"rev_{yk}"])
    v["base_overhead_share"] = _pct(d["context_overhead_share"]["value"][1])
    v["base_overhead_reduction"] = _pct(d["overhead_reduction"]["value"][1])
    v["base_gainshare"] = _pct(d["gainshare"]["value"][1])
    v["base_fee"] = _gbp(d["platform_fee_annual_gbp"]["value"][1])
    return v


if __name__ == "__main__":
    for s, o in derive().items():
        print(s, {k: (round(x) if isinstance(x, float) else x) for k, x in o.items()})
    print()
    print(json.dumps(values(), indent=1))
