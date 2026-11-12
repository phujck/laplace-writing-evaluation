"""The three properties wave J3 turns on, each observed in a SECOND PROCESS.

THE AUTHOR, 2026-09-22: "Why would it need to be mounting handles on every fucking descent.
Does reconstruct need an upfold before every execution?"

1. ORDINALS ARE REPRODUCED. ``open_record`` installs every row at the ordinal the ingestion
   that built the record assigned and persisted in its manifest row, so a second process holds
   the same layout - and the persisted tree names its rows by B.2 IDENTITY anyway, so it would
   still name the same rows if the layout moved.
2. THE WARM DOOR ADMITS THE SAME ROWS AS THE COLD DOOR, on every dataset of the declared draw.
   This is J2's escalated defect measured the other way round: there, qasper's answer came from
   966 rows cold and 953 warm with only 224 of 966 ordinals shared.
3. A READ MINTS NOTHING. The identity is minted once at ingestion, so a read that runs with the
   minting entry point POISONED must still return every handle. This is the property the
   author's question asks for, asserted rather than argued.

Run with ``--basetemp=/tmp/pytest-<something unique>``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"


def _run(code: str, *, cwd: Path) -> dict:
    """Run a snippet in a FRESH interpreter and return the JSON it printed on its last line."""
    done = subprocess.run([sys.executable, "-c", code], cwd=str(cwd), text=True,  # pool-once: one child per property under test, spawned by the test that owns it
                          capture_output=True, env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin",
                                                    "HOME": str(cwd)})
    assert done.returncode == 0, done.stderr[-4000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


_BUILD_TOY = """
import json, sys
from pathlib import Path
from atlas.record.ingest import toy
from atlas.record import segments as S
from atlas.record.extract import extractor_roster_hash
from atlas.record.identity import ids_of_words

root = Path(sys.argv[0]).parent if False else Path("store")
store = S.SegmentStore(root)
built = toy.ingest()
S.store_ingestion(store, built.ingestion, extractor_roster_hash=extractor_roster_hash())
table = built.ingestion.store.table("toy_row")
print(json.dumps({"ordinals": table.global_ordinals.tolist(),
                  "identities": ids_of_words(table.identity)}))
"""

_OPEN_TOY = """
import json
from pathlib import Path
from atlas.record.ingest import toy
from atlas.record import segments as S
from atlas.record.identity import ids_of_words

opened = S.open_record(S.SegmentStore(Path("store")), toy.declaration(), digests=False)
table = opened.ingestion.store.table("toy_row")
print(json.dumps({"ordinals": table.global_ordinals.tolist(),
                  "identities": ids_of_words(table.identity)}))
"""


def test_a_second_process_reproduces_the_ordinals_and_the_identities(tmp_path):
    built = _run(_BUILD_TOY, cwd=tmp_path)
    opened = _run(_OPEN_TOY, cwd=tmp_path)
    assert opened["ordinals"] == built["ordinals"], (
        "open_record must install every row at the ordinal the ingestion assigned")
    assert opened["identities"] == built["identities"], (
        "B.2 identity is minted once at ingestion and travels in the segment")
    assert len(set(built["identities"])) == len(built["identities"])


_READ_WITH_THE_MINT_POISONED = """
import json
from pathlib import Path
from atlas.record.ingest import toy
from atlas.record import segments as S
from atlas.record.typed_row_store import TypedRowStore
from atlas.grading import tree as T
from atlas.grading.lenses import toy_lens
from atlas.front import faces as FA, question as Q, read as RD
from atlas.store import CompressedHive

opened = S.open_record(S.SegmentStore(Path("store")), toy.declaration(), digests=False)
lens = toy_lens(opened.ingestion)
identities = opened.ingestion.store.identity_by_global()
hive = CompressedHive(Path("hive"))
built = T.build_graded_tree(opened.ingestion, lens)
manifest = T.persist_tree(built, hive, identities)
loaded = FA.load_persisted_lens(manifest, hive, opened.ingestion.device, identities)

# THE POISON: after this line nothing may hash a row. If the read still answers with handles,
# the identity it returns was minted at ingestion and gathered, exactly as the ruling says.
def _refuse(*a, **k):
    raise AssertionError("the read minted a B.2 identity")
TypedRowStore.row_ids = _refuse

out = []
for spec in Q.toy_questions(opened):
    compiled = Q.compile_question(spec, opened, lens, loaded.rows)
    result = RD.read(opened, loaded, compiled, tolerance=compiled.tolerances[0], supply="whole")
    out.append({"qid": spec.qid, "answer": result.answer,
                "handles": len(result.row_handles),
                "row_ids": [h["row_id"] for h in result.row_handles.as_dicts()],
                "ranges": len(result.range_handles),
                "ordinals_reproduced": loaded.executed["ordinals_reproduced"]})
print(json.dumps(out))
"""


def test_a_read_returns_its_handles_with_the_identity_mint_poisoned(tmp_path):
    _run(_BUILD_TOY, cwd=tmp_path)
    results = _run(_READ_WITH_THE_MINT_POISONED, cwd=tmp_path)
    assert results, "the toy declares five questions"
    assert all(r["ordinals_reproduced"] for r in results)
    assert any(r["handles"] for r in results), (
        "an answer must return the handles of the content it was drawn from")
    for row in results:
        for row_id in row["row_ids"]:
            assert row_id.startswith("sha256:") and len(row_id) == 71


@pytest.mark.slow
def test_the_warm_door_admits_the_same_rows_as_the_cold_door_on_all_four_datasets(tmp_path):
    """THE RULING'S OWN TEST: run the declared entry twice, in two processes, and compare.

    Each pass is its own interpreter, so the second one opens the persisted record with no
    memory of the first. What is compared is what the defect moved: the number of rows each
    answer was admitted from, and the SET of B.2 identities its handles name.
    """
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "record": "atlas.front-door-manifest/1", "root": str(tmp_path / "store"),
        "datasets": ["toy", "engine", "longmem", "qasper"], "declared_draw": "J2-smoke"}))
    receipts = []
    for pass_name in ("cold", "warm"):  # loop-ok: the two passes the ruling names
        out = tmp_path / f"{pass_name}.json"
        done = subprocess.run(  # pool-once: exactly two children, one per pass, which IS the property under test
            [sys.executable, "-m", "atlas.front", str(manifest), "--out", str(out)],
            cwd=str(ROOT), text=True, capture_output=True,
            env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
        assert done.returncode == 0, done.stderr[-4000:]
        receipts.append(json.loads(out.read_text()))
    cold, warm = receipts
    from atlas.front.comparison import compare_observations
    comparison = compare_observations(cold, warm)
    assert comparison['status'] == 'EQUIVALENT', comparison
    assert set(comparison['coverage']) == {'toy', 'engine', 'longmem', 'qasper'}

    assert set(cold["datasets"]) == {"toy", "engine", "longmem", "qasper"}
    for name in cold["datasets"]:  # loop-ok: the four datasets of the declared draw
        warm_ingest = [s for s in warm["datasets"][name]["receipt"]["stages"]
                       if s["stage"] == "ingest"][0]
        assert warm_ingest["executed"]["path"] == "open_record", name
        assert warm_ingest["executed"]["extractions"] == 0, name
        assert warm_ingest["payload"]["persisted_bytes_per_source_byte"]["source_bytes"] > 0, (
            f"{name}: the compactness receipt must exist on the path a judge runs")
        warm_faces = [s for s in warm["datasets"][name]["receipt"]["stages"]
                      if s["stage"] == "faces"][0]
        assert warm_faces["executed"]["ordinals_reproduced"] is True, name
        # The shared owner verifies all versions/hashes and complete nonempty
        # dataset/qid coverage. Represented identity is required to be complete;
        # a saved first-40 sample is UNPROVED, never a same-rows success.
        assert comparison['coverage'][name], name
        for claim in ('answers_and_controls', 'admitted_counts', 'represented_identity'):
            assert comparison['clauses'][claim]['status'] == 'EQUIVALENT', comparison
