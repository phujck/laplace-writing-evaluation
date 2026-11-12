"""B6 — the reader-verdict TRANSPORT shim: CLEAN/LABEL by FILE + EXIT CODE.

builder ≠ judge: these exercise the PLUMBING (the verdict file schema, the exit
code, the disk-backed sidecar rebuild, silence => failed), never the read QUALITY.
The banked seam this closes: the CLEAN/LABEL bit must not ride a model — it is a
file plus an exit code, and the per-round sidecar is assembled from those files, one
source of truth.
"""
import json
import subprocess
import sys
from pathlib import Path

from laplace.pipeline.readers import verdict_io as V

REPO = Path(__file__).resolve().parents[1]


def _run_write(organ, rid, label, out_dir, reply):
    """Invoke the verdict_io `write` CLI exactly as the reader's verbatim tail does
    (the `-c ... main([...])` form the loop emits), piping the raw reply on stdin."""
    code = ("import sys; from laplace.pipeline.readers.verdict_io import main; "
            f"sys.exit(main(['write', {organ!r}, {rid!r}, {label!r}, {str(out_dir)!r}]))")
    return subprocess.run([sys.executable, "-c", code], input=reply,
                          capture_output=True, text=True, cwd=str(REPO))


# --- (a) write_verdict: exact schema, exit 0 on clean / nonzero on unclean -----

def test_write_verdict_library_exact_schema(tmp_path):
    d = tmp_path / "rounds" / "lock_r2"
    rec = V.write_verdict("R1", "cold_reader", [], d)
    assert set(rec) == {"label", "reader", "clean", "findings_n", "finding_ids"}
    assert rec == {"label": "cold_reader", "reader": "R1", "clean": True,
                   "findings_n": 0, "finding_ids": []}
    on_disk = json.loads((d / "R1_verdict.json").read_text())
    assert on_disk == rec


def test_write_verdict_label_single_sourced_from_roster(tmp_path):
    # even a wrong label passed by an agent is overridden by the roster panel_label
    rec = V.write_verdict("R2", "WRONG_LABEL", [], tmp_path)
    assert rec["label"] == "referee"


def test_cli_write_exit_zero_on_clean(tmp_path):
    res = _run_write("sealed", "R1", "cold_reader", tmp_path, "[]")
    assert res.returncode == 0, res.stderr
    rec = json.loads((tmp_path / "R1_verdict.json").read_text())
    assert rec["clean"] is True and rec["findings_n"] == 0


def test_cli_write_exit_nonzero_on_unclean(tmp_path):
    reply = json.dumps([{"where": "§2", "issue": "Z used before definition",
                         "fix": "define Z", "kind": "cold-undefined-term"}])
    res = _run_write("sealed", "R1", "cold_reader", tmp_path, reply)
    assert res.returncode != 0, "unclean verdict must exit nonzero"
    rec = json.loads((tmp_path / "R1_verdict.json").read_text())
    assert rec["clean"] is False and rec["findings_n"] == 1
    assert rec["finding_ids"] and isinstance(rec["finding_ids"][0], str)


def test_cli_write_referee_organ(tmp_path):
    reply = json.dumps([{"where": "claim 1", "issue": "evidence too thin",
                         "fix": "add data", "kind": "referee-insufficient"}])
    res = _run_write("referee", "R2", "referee", tmp_path, reply)
    assert res.returncode != 0
    rec = json.loads((tmp_path / "R2_verdict.json").read_text())
    assert rec == {"label": "referee", "reader": "R2", "clean": False,
                   "findings_n": 1, "finding_ids": rec["finding_ids"]}


def test_cli_write_garbage_reply_is_failed_not_clean(tmp_path):
    """The judge's refutation, banked: a present-but-garbage reply must bank a
    FAILED verdict and exit nonzero — corruption is loud, like absence. A
    genuinely clean reply ([]) still passes."""
    import subprocess, sys as _sys
    cases = [
        "not json at all",                                            # prose
        "",                                                           # empty
        '[{"where":"s2","issue":"Z undefined","fix":"define Z",',    # truncated UNCLEAN
    ]
    for raw in cases:
        r = subprocess.run(
            [_sys.executable, "-c",
             "import sys; from laplace.pipeline.readers.verdict_io import main;"
             " sys.exit(main(['write','sealed','R1','x',sys.argv[1]]))",
             str(tmp_path)],
            input=raw, capture_output=True, text=True)
        assert r.returncode != 0, f"garbage reply exited 0: {raw!r}"
        rec = json.loads((tmp_path / "R1_verdict.json").read_text(encoding="utf-8"))
        assert rec["failed"] is True and rec["clean"] is False
    # the genuine-clean path is unharmed
    r = subprocess.run(
        [_sys.executable, "-c",
         "import sys; from laplace.pipeline.readers.verdict_io import main;"
         " sys.exit(main(['write','sealed','R1','x',sys.argv[1]]))",
         str(tmp_path)],
        input="[]", capture_output=True, text=True)
    assert r.returncode == 0
    rec = json.loads((tmp_path / "R1_verdict.json").read_text(encoding="utf-8"))
    assert rec["clean"] is True and not rec.get("failed")


def test_assemble_carries_planted_unclean_from_disk(tmp_path):
    d = tmp_path / "rounds" / "lock_r5"
    d.mkdir(parents=True)
    # a hand-planted UNCLEAN R1 verdict, as if a sealed reader had written it
    (d / "R1_verdict.json").write_text(json.dumps(
        {"label": "cold_reader", "reader": "R1", "clean": False,
         "findings_n": 3, "finding_ids": ["a", "b", "c"]}))
    entries = V.assemble_sidecar(d, ["R1"])
    cold = next(e for e in entries if e["label"] == "cold_reader")
    assert cold["clean"] is False
    assert cold["flags"] == [{"n": 3}]           # non-clean flags mirror findings_n
    assert not cold.get("failed")


def test_assemble_clean_file_reads_clean(tmp_path):
    d = tmp_path / "rounds" / "lock_r5"
    V.write_verdict("R6", "visual", [], d)
    entries = V.assemble_sidecar(d, ["R6"])
    vis = next(e for e in entries if e["label"] == "visual")
    assert vis["clean"] is True and vis["flags"] == []


# --- (c) a rostered reader with NO verdict file => failed:true -----------------

def test_assemble_absent_file_is_failed_never_pass(tmp_path):
    d = tmp_path / "rounds" / "lock_r7"
    d.mkdir(parents=True)
    V.write_verdict("R1", "cold_reader", [], d)          # only R1 present
    entries = V.assemble_sidecar(d, ["R1", "R6"])        # R6 rostered but absent
    vis = next(e for e in entries if e["label"] == "visual")
    assert vis.get("failed") is True and vis["clean"] is False
    # silence never reads as pass: reader_verdict_score treats it as neutral 0.5
    from laplace.pipeline.readers import reader_verdict_score
    assert reader_verdict_score(vis) == 0.5


# --- calc mirror + voice extra: derived from the file-backed entries -----------

def test_assemble_calc_mirrors_file_backed_referee(tmp_path):
    d = tmp_path / "rounds" / "lock_r3"
    V.write_verdict("R2", "referee",
                    [{"where": "c", "issue": "i", "fix": None,
                      "kind": "referee-insufficient", "reader": "R2"}], d)
    entries = V.assemble_sidecar(d, ["R2"])
    ref = next(e for e in entries if e["label"] == "referee")
    calc = next(e for e in entries if e["label"] == "calc")
    assert calc["clean"] == ref["clean"] == False
    assert calc["flags"] == ref["flags"]


def test_assemble_no_calc_when_referee_absent(tmp_path):
    d = tmp_path / "rounds" / "lock_r3"
    V.write_verdict("R1", "cold_reader", [], d)
    entries = V.assemble_sidecar(d, ["R1"])
    assert not any(e["label"] == "calc" for e in entries)


def test_assemble_appends_voice_extra_entry(tmp_path):
    d = tmp_path / "rounds" / "lock_r3"
    V.write_verdict("R1", "cold_reader", [], d)
    voice = {"label": "voice", "clean": True, "flags": []}
    entries = V.assemble_sidecar(d, ["R1"], extra_entries=[voice])
    assert any(e["label"] == "voice" and e["clean"] is True for e in entries)


# --- the assemble CLI writes the sidecar from disk, extra entries on stdin -----

# --- R10 (the restart organ): the two-phase read over the single-reply transport --
#
# C5.1: verdict_io gains the R10 organ. The load-bearing mapping — the organ parses
# ONLY the COMPARE-phase reply (clean = no mismatches); the blind packet is banked
# separately via restart_reader.bank and never rides parse_reply. These exercise the
# TRANSPORT (dispatch, exit code, silence => failed for the rostered tier), not the
# read quality.

def test_parse_reply_restart_maps_compare_mismatches_to_findings():
    """The compare reply (a list of typed mismatches) parses to R10 findings via the
    reader's own verb law; an empty compare list is clean (no findings)."""
    reply = json.dumps([{"type": "contribution",
                         "object_key": "meta.contribution_rank",
                         "note": "recovered contribution is not the intended one"}])
    findings = V.parse_reply("restart", "R10", reply)
    assert len(findings) == 1
    assert findings[0]["kind"] == "identity-mismatch"        # contribution → RESPINE kind
    assert findings[0]["reader"] == "R10"
    # empty compare reply → no mismatches → clean (no findings)
    assert V.parse_reply("restart", "R10", "[]") == []
    # the "r10" alias resolves to the same organ
    assert V.parse_reply("r10", "R10", "[]") == []


def test_cli_write_restart_unclean_verdict(tmp_path):
    """A compare reply naming a mismatch → nonzero exit + a file-backed verdict whose
    label is single-sourced from the roster (restart_reader), clean False."""
    reply = json.dumps([{"type": "identity", "object_key": "meta",
                         "note": "the recovered paper is a different object"}])
    res = _run_write("restart", "R10", "WRONG_LABEL", tmp_path, reply)
    assert res.returncode != 0, "an R10 mismatch verdict must exit nonzero"
    rec = json.loads((tmp_path / "R10_verdict.json").read_text(encoding="utf-8"))
    assert rec["label"] == "restart_reader"                  # roster, not the passed label
    assert rec["clean"] is False and rec["findings_n"] == 1
    assert rec["finding_ids"] and isinstance(rec["finding_ids"][0], str)


def test_cli_write_restart_clean_on_empty_compare(tmp_path):
    """An empty compare reply (the recovered paper IS the intended paper) → exit 0,
    clean True — the genuine-clean path is not swallowed by the fail-closed gate."""
    res = _run_write("restart", "R10", "restart_reader", tmp_path, "[]")
    assert res.returncode == 0, res.stderr
    rec = json.loads((tmp_path / "R10_verdict.json").read_text(encoding="utf-8"))
    assert rec["clean"] is True and rec["findings_n"] == 0 and not rec.get("failed")


def test_cli_write_restart_garbage_compare_is_failed_not_clean(tmp_path):
    """FAIL-CLOSED (a): a truncated/garbage COMPARE reply carries no JSON list →
    the transport gate banks a FAILED verdict and exits nonzero — never clean. A
    whole-artefact judge whose reply is corrupt must not quietly certify."""
    cases = [
        "no mismatches here, all good",                              # prose, no JSON
        "",                                                          # empty
        '[{"type":"identity","object_key":"meta","note":"different',  # truncated
    ]
    for raw in cases:
        res = _run_write("restart", "R10", "restart_reader", tmp_path, raw)
        assert res.returncode != 0, f"garbage compare reply exited 0: {raw!r}"
        rec = json.loads((tmp_path / "R10_verdict.json").read_text(encoding="utf-8"))
        assert rec["failed"] is True and rec["clean"] is False


def test_assemble_absent_r10_is_failed_when_rostered(tmp_path):
    """FAIL-CLOSED (b): when R10 is in the ACTIVE roster but its verdict file is
    absent, assemble marks it failed:true / clean:false — silence never passes for
    the rostered tier (the load-bearing precondition C5.3's AND-in relies on)."""
    d = tmp_path / "rounds" / "lock_r6"
    d.mkdir(parents=True)
    V.write_verdict("R1", "cold_reader", [], d)              # only R1 present
    entries = V.assemble_sidecar(d, ["R1", "R10"])           # R10 rostered but absent
    r10 = next(e for e in entries if e["label"] == "restart_reader")
    assert r10.get("failed") is True and r10["clean"] is False
    from laplace.pipeline.readers import reader_verdict_score
    assert reader_verdict_score(r10) == 0.5                  # neutral, never a pass


def test_cli_write_restart_wrong_shape_dict_banks_failed_verdict(tmp_path):
    """FAIL-CLOSED (c) — the judge's counterexample: a WELL-FORMED JSON dict that is
    not a recognised compare shape passes the transport gate (it admits dicts) and
    reaches the fail-loud organ. The raise must become a first-class FAILED verdict
    FILE + nonzero exit — never a clean, and never a traceback with no file (which
    would be fail-closed only through assemble's absent-file rule)."""
    cases = [
        json.dumps({"type": "identity", "object_key": "meta",
                    "note": "a genuine mismatch delivered as a bare dict"}),
        json.dumps({"mismatches": "yes"}),
        json.dumps({"foo": 1}),
    ]
    for raw in cases:
        res = _run_write("restart", "R10", "restart_reader", tmp_path, raw)
        assert res.returncode != 0, f"wrong-shape dict exited 0: {raw!r}"
        assert "Traceback" not in res.stderr, "the raise must be caught, not crash"
        rec = json.loads((tmp_path / "R10_verdict.json").read_text(encoding="utf-8"))
        assert rec["failed"] is True and rec["clean"] is False
        assert "rejected" in rec["note"]


def test_cli_assemble_writes_sidecar_from_disk(tmp_path):
    d = tmp_path / "rounds" / "lock_r4"
    V.write_verdict("R1", "cold_reader", [], d)          # clean
    V.write_verdict("R2", "referee",
                    [{"where": "c", "issue": "i", "fix": None,
                      "kind": "referee-insufficient", "reader": "R2"}], d)   # unclean
    sidecar = tmp_path / "rounds" / "lock_r4.json"
    code = ("import sys; from laplace.pipeline.readers.verdict_io import main; "
            f"sys.exit(main(['assemble', {str(d)!r}, {str(sidecar)!r}, 'R1,R2,R6']))")
    voice = json.dumps([{"label": "voice", "clean": True, "flags": []}])
    res = subprocess.run([sys.executable, "-c", code], input=voice,
                         capture_output=True, text=True, cwd=str(REPO))
    assert res.returncode == 0, res.stderr
    panel = json.loads(sidecar.read_text())
    by = {e["label"]: e for e in panel}
    assert by["cold_reader"]["clean"] is True
    assert by["referee"]["clean"] is False
    assert by["visual"].get("failed") is True            # R6 rostered, absent
    assert by["calc"]["clean"] is False                  # mirrors referee
    assert by["voice"]["clean"] is True                  # extra entry from stdin
