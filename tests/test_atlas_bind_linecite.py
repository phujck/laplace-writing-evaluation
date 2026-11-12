"""test_atlas_bind_linecite.py - the comma multi-cite is a citation, not prose.

WO-20260817-comma-multicite-parser: a citation of the form ``path:12-13,20-25``
(several spans into one file behind a single backtick pair) failed
``LINECITE_RE``, fell through ``classify_token`` as a non-candidate, and was
dropped in silence - it read to a human as a citation and was never
fingerprinted, so the drawing standing on it could never go stale.

The parser now expands the comma form into one citation per span. These cases
pin that behaviour at three levels:

  token      ``classify_token`` returns ("line", (path, [spans...])) for the
             six forms the 2026-08-17 re-bind packet actually found, and still
             refuses the prose that must stay prose.
  bullet     ``scan_citations`` emits one row per span, deduped, from both the
             backticked and the bare (un-backticked) form - the bare pattern
             used to match only the FIRST span and hand the classifier a
             truncated token, dropping the rest just as silently.
  end-to-end ``bind`` writes a fingerprint row per span and ``check`` reports
             FRESH; editing inside the SECOND span alone is caught, which is
             the whole point: before the fix that span was invisible.
"""

import importlib.util
import json
import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO_ROOT, "scripts", "atlas_bind.py")


def _load():
    spec = importlib.util.spec_from_file_location("atlas_bind_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ab = _load()


# The six that the re-bind packet found dropped, verbatim from the work order.
DROPPED = [
    ("meaning_upfold.py:453-465,500-519", "meaning_upfold.py", [(453, 465), (500, 519)]),
    ("meaning_upfold.py:400-419,422-441", "meaning_upfold.py", [(400, 419), (422, 441)]),
    ("meaning_upfold.py:143,153,400-419", "meaning_upfold.py", [(143, 143), (153, 153), (400, 419)]),
    ("keeper.py:104-111,166", "keeper.py", [(104, 111), (166, 166)]),
    ("embed_router.py:679-680,794-805", "embed_router.py", [(679, 680), (794, 805)]),
    ("DESIGN_2026-08-11_the-atlas-gauntlet.md:392-395,404-407",
     "DESIGN_2026-08-11_the-atlas-gauntlet.md", [(392, 395), (404, 407)]),
]


@pytest.mark.parametrize("tok,path,spans", DROPPED, ids=[d[0] for d in DROPPED])
def test_dropped_multicites_classify_as_line_citations(tok, path, spans):
    kind, parsed = ab.classify_token(tok)
    assert kind == "line", "%s must read as a citation, not fall through as prose" % tok
    assert parsed == (path, spans)


def test_single_span_forms_unchanged():
    assert ab.classify_token("keeper.py:104") == ("line", ("keeper.py", [(104, 104)]))
    assert ab.classify_token("keeper.py:104-111") == ("line", ("keeper.py", [(104, 111)]))


def test_reversed_span_is_normalised():
    assert ab.classify_token("keeper.py:20-10,5") == ("line", ("keeper.py", [(10, 20), (5, 5)]))


def test_prose_still_reads_as_prose():
    # backticked prose that looks pathlike, and malformed span lists: none of
    # these may become citations just because the comma form is now legal.
    # (a TRAILING comma is not listed: strip_edges deliberately eats trailing
    # punctuation before classification, so `keeper.py:12,` is the prose-comma
    # case the parser is meant to tolerate, not a malformed span list.)
    for tok in ("node_forms", "promises.jsonl:", "keeper.py:12,x", "keeper.py:,12",
                "keeper.py:12-", "src/"):
        kind, _ = ab.classify_token(tok)
        assert kind != "line", "%r must not classify as a line citation" % tok
    assert ab.classify_token("promises.jsonl")[0] == "bare"


def test_scan_citations_expands_and_dedupes():
    bullet = "the fold organ `meaning_upfold.py:453-465,500-519` and again `meaning_upfold.py:500-519`"
    rows = ab.scan_citations(bullet)
    assert [(r["path"], r["line_start"], r["line_end"]) for r in rows] == [
        ("meaning_upfold.py", 453, 465),
        ("meaning_upfold.py", 500, 519),
    ]


def test_bare_unbackticked_multicite_is_not_truncated():
    # LOOSE_RE used to stop at the first span and hand over a truncated token.
    rows = ab.scan_citations("see keeper.py:104-111,166 for the seam")
    assert [(r["line_start"], r["line_end"]) for r in rows] == [(104, 111), (166, 166)]


# ------------------------------------------------------------- end to end ----

def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _run(args):
    return subprocess.run([sys.executable, SCRIPT] + args,
                          capture_output=True, text=True, cwd=REPO_ROOT)


@pytest.fixture()
def atlas(tmp_path):
    src = tmp_path / "src"
    body = "\n".join("line %03d" % i for i in range(1, 61)) + "\n"
    _write(str(src / "keeper.py"), body)
    diagrams = tmp_path / "diagrams"
    _write(str(diagrams / "room" / "d1.md"),
           "# The keeper seam\n\n"
           "Audience: ROOM-SAFE\n\n"
           "Sources:\n"
           "- the two halves of the seam `keeper.py:10-12,40-42`\n")
    return src, diagrams


def test_bind_fingerprints_every_span_and_check_sees_the_second(atlas):
    src, diagrams = atlas
    r = _run(["bind", str(diagrams), "--stamp", "2026-08-21T00:00:00Z",
              "--source-root", str(src)])
    assert r.returncode == 0, r.stderr
    index = json.loads((diagrams / "atlas_index.json").read_text())
    cits = index["diagrams"]["room/d1.md"]["citations"]
    assert [(c["line_start"], c["line_end"]) for c in cits] == [(10, 12), (40, 42)]
    assert cits[0]["window_sha256"] != cits[1]["window_sha256"]

    r = _run(["check", str(diagrams), "--source-root", str(src), "--json"])
    assert r.returncode == 0, r.stderr + r.stdout
    assert '"STALE"' not in r.stdout and '"MOVED"' not in r.stdout

    # edit inside the SECOND span only - invisible before the fix
    lines = (src / "keeper.py").read_text().split("\n")
    lines[40] = "line 041 EDITED"
    (src / "keeper.py").write_text("\n".join(lines))
    r = _run(["check", str(diagrams), "--source-root", str(src), "--json"])
    payload = json.loads(r.stdout)
    row = payload["rows"][0]
    assert row["citations_total"] == 2
    assert row["state"] == "STALE", row
    # the edited span goes STALE; the other reports MOVED (content intact, the
    # file changed elsewhere) - either way BOTH spans are now under watch.
    stale = [(d["line_start"], d["line_end"]) for d in row["detail"] if d["state"] == "STALE"]
    moved = [(d["line_start"], d["line_end"]) for d in row["detail"] if d["state"] == "MOVED"]
    assert stale == [(40, 42)], row
    assert moved == [(10, 12)], row
