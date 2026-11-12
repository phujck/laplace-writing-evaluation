"""The figures organ — hermetic plumbing tests.

builder != judge: these exercise the WIRING (promise enumeration off the tex,
generator discovery off a script, keyword matching, honest-absence typing,
idempotent placement + manifest), never the aesthetic quality of a rendered
figure. No live matplotlib run and no LaTeX compile is needed — the generator
script is a hand-written fixture whose docstring and ``fig_*`` defs drive
discovery, and placement is asserted against the mutated ``.tex`` text.

The one regression these lock: a generator whose docstring wraps across lines
(``... (left,\\n log scale) and the ... sweep``) must still surface its
continuation keywords, or a promise that a real generator serves (``sweep``)
gets dishonestly typed as an absent computation-class gap.
"""
import inspect
import json
from pathlib import Path

from laplace.pipeline import figure_runner as fr


# --------------------------------------------------------------------------- #
# Fixtures — a manuscript that promises two named plots (one served, one not)
# and a generator script that serves exactly one of them, with a MULTI-LINE
# docstring so the wrap-parse regression is exercised.
# --------------------------------------------------------------------------- #

_S1 = """\
% PLAN:s1
% NODES: node_a node_b
Section one develops the argument. We defer the witness-scaling plot to the
verification section, and the reader is pointed at the coupling-landscape plot
for the phase behaviour.
"""

_APPENDIX = """\
% PLAN:appendix
% NODES: node_c
The witness-scaling plot and the coupling-landscape plot are registered here.
"""

# a generator script: fig_witness serves the witness-scaling promise; its
# docstring entry WRAPS across two lines so "scaling" sits past the wrap.
_GEN_SCRIPT = '''\
"""Two data figures for the fixture manuscript.

fig_witness   - the protocol's verification: flag behaviour vs the commutator
                prediction and the quiet-branch error scaling.
"""
import matplotlib


def save(fig, name):
    pass


def fig_witness():
    fig = object()
    save(fig, "fig_witness")
'''


def _manuscript(tmp_path: Path) -> Path:
    m = tmp_path / "manuscript"
    m.mkdir()
    (m / "s1.tex").write_text(_S1, encoding="utf-8")
    (m / "appendix_a.tex").write_text(_APPENDIX, encoding="utf-8")
    return m


def _script(tmp_path: Path) -> Path:
    # sits under a sibling of a "figures" dir, mirroring the real layout
    numerics = tmp_path / "numerics"
    numerics.mkdir()
    s = numerics / "gen.py"
    s.write_text(_GEN_SCRIPT, encoding="utf-8")
    return s


# --------------------------------------------------------------------------- #
# Enumeration
# --------------------------------------------------------------------------- #


def test_enumerate_promises_finds_named_plots(tmp_path):
    m = _manuscript(tmp_path)
    promises = fr.enumerate_promises(m)
    phrases = {p.phrase for p in promises}
    assert phrases == {"witness-scaling", "coupling-landscape"}


def test_enumerate_promises_dedups_by_phrase_first_site_wins(tmp_path):
    m = _manuscript(tmp_path)
    promises = fr.enumerate_promises(m)
    by = {p.phrase: p for p in promises}
    # witness-scaling appears in s1 first (section order) then the appendix;
    # the first occurrence owns the site.
    assert by["witness-scaling"].site_file == "s1.tex"
    assert by["witness-scaling"].keywords == ("witness", "scaling")


def test_enumerate_ignores_number_word_figures(tmp_path):
    # "three figures" / "all three figures" name numerals, not graphics; the
    # named-plot regex must not fire on bare "figures".
    m = tmp_path / "man"
    m.mkdir()
    (m / "s1.tex").write_text(
        "All three figures assume convergence; see the figure below.",
        encoding="utf-8")
    assert fr.enumerate_promises(m) == []


# --------------------------------------------------------------------------- #
# Generator discovery — the multi-line docstring regression
# --------------------------------------------------------------------------- #


def test_discover_generators_reads_defs_and_output(tmp_path):
    s = _script(tmp_path)
    gens = fr.discover_generators(s)
    assert [g.name for g in gens] == ["fig_witness"]
    assert gens[0].output == "fig_witness"


def test_discover_generators_captures_wrapped_docstring_keywords(tmp_path):
    # the REGRESSION: "scaling" lives on the continuation line of the docstring
    # entry; a single-line parse drops it and the witness-scaling promise then
    # fails to match its real generator.
    s = _script(tmp_path)
    gens = fr.discover_generators(s)
    assert "scaling" in gens[0].keywords
    assert "witness" in gens[0].keywords


# --------------------------------------------------------------------------- #
# Matching + honest absence
# --------------------------------------------------------------------------- #


def test_match_served_promise_and_type_absent_one(tmp_path):
    m = _manuscript(tmp_path)
    s = _script(tmp_path)
    promises = fr.enumerate_promises(m)
    gens = fr.discover_generators(s)
    matched, unmatched = fr.match_promises(promises, gens)
    matched_phrases = {p.phrase for p, _ in matched}
    unmatched_phrases = {p.phrase for p in unmatched}
    assert matched_phrases == {"witness-scaling"}
    assert unmatched_phrases == {"coupling-landscape"}


def test_run_dry_types_absence_as_computation_intent(tmp_path):
    m = _manuscript(tmp_path)
    s = _script(tmp_path)
    manifest = fr.run(m, s, apply=False)
    assert manifest["matched_count"] == 1
    assert manifest["unmatched_count"] == 1
    intents = manifest["intents"]
    assert len(intents) == 1
    it = intents[0]
    assert it["cls"] == "computation"
    assert it["promise"] == "coupling-landscape"
    assert it["id"] == "RI-COMP-coupling-landscape"
    # a matched promise must NOT mint an intent
    assert not any(i["promise"] == "witness-scaling" for i in intents)


def test_run_dry_does_not_mutate_tree(tmp_path):
    m = _manuscript(tmp_path)
    s = _script(tmp_path)
    before = {p.name: p.read_text(encoding="utf-8") for p in m.glob("*.tex")}
    fr.run(m, s, apply=False)
    after = {p.name: p.read_text(encoding="utf-8") for p in m.glob("*.tex")}
    assert before == after
    assert not (m / "figure_manifest.json").exists()
    assert not (m / "research_intents.jsonl").exists()


# --------------------------------------------------------------------------- #
# Placement — idempotent float insertion + honest TODO env
# --------------------------------------------------------------------------- #


def test_place_figure_idempotent(tmp_path):
    m = _manuscript(tmp_path)
    spec = {"float": "figure", "label": "fig:x",
            "caption": "cap", "ref_sentence": "See Fig.~\\ref{fig:x}."}
    block = fr._float_block(spec, "figures/fig_x")
    s1 = m / "s1.tex"
    first = fr.place_figure(s1, block, "fig:x", spec["ref_sentence"])
    second = fr.place_figure(s1, block, "fig:x", spec["ref_sentence"])
    assert first is True
    assert second is False  # label already present -> no-op
    text = s1.read_text(encoding="utf-8")
    assert text.count("\\label{fig:x}") == 1
    assert text.count("\\ref{fig:x}") == 1


def test_place_inserts_after_nodes_anchor(tmp_path):
    m = _manuscript(tmp_path)
    spec = {"float": "figure", "label": "fig:y", "caption": "cap"}
    block = fr._float_block(spec, "figures/fig_y")
    s1 = m / "s1.tex"
    fr.place_figure(s1, block, "fig:y", None)
    text = s1.read_text(encoding="utf-8")
    nodes_pos = text.index("% NODES:")
    fig_pos = text.index("\\label{fig:y}")
    assert fig_pos > nodes_pos


def test_honest_absence_env_names_the_intent(tmp_path):
    block = fr._todo_block("fig:todo-x", "coupling-landscape", "RI-COMP-x")
    assert "Figure pending" in block
    assert "coupling-landscape" in block
    assert "RI-COMP-x" in block
    assert "\\label{fig:todo-x}" in block


# --------------------------------------------------------------------------- #
# Intent banking — deduped JSONL
# --------------------------------------------------------------------------- #


def test_bank_intents_dedups_by_id(tmp_path):
    m = tmp_path / "man"
    m.mkdir()
    it = fr.ResearchIntent(id="RI-COMP-z", cls="computation",
                           promise="z", site="s1.tex:1", note="n")
    fr._bank_intents(m, [it])
    fr._bank_intents(m, [it])  # second call must not duplicate
    ledger = (m / "research_intents.jsonl").read_text(encoding="utf-8")
    lines = [ln for ln in ledger.splitlines() if ln.strip()]
    assert len(lines) == 1


# --------------------------------------------------------------------------- #
# Promise-site reconciliation — the fulfilled promise CLOSED at its claim site
# (the July-17 fix-round catch: placement rendered s6/s8 but the appendix still
# called the plots "not rendered in this version", so the artefact self-
# contradicted). These lock: the stale sentence is rewritten with a \ref; a
# comment line and an adjacent paragraph are NEVER swallowed; the aggregate
# residue tally is decremented only when every promise is truly fulfilled; and a
# re-run is byte-stable.
# --------------------------------------------------------------------------- #

_PROMISE_SITE = (
    "% appendix-p15\n"
    "The sweep-tradeoff plot and the witness-scaling plot are registered TODOs, "
    "with neither rendered in this version, even though both draw from committed "
    "readings JSONs. The same data holds a fidelity that is undiscussed.\n"
    "\n"
    "% appendix-p16\n"
    "Six defects were fixed. Eight items remain open: one mismatched citation, "
    "eleven literature records, three LITERATURE-tier constants, one missing "
    "construction, one unbacked figure, one deferred comparison, one unmeasured "
    "assumption, and two unrendered figures. A reader should treat the residue "
    "as the active risk.\n"
)

_FULFILLED = {"sweep-tradeoff": "fig:resources", "witness-scaling": "fig:witness"}


def _site(tmp_path, text=_PROMISE_SITE):
    m = tmp_path / "man"
    m.mkdir()
    (m / "appendix_c.tex").write_text(text, encoding="utf-8")
    return m


def test_reconcile_rewrites_named_plot_claim_with_ref(tmp_path):
    m = _site(tmp_path)
    changed = fr.reconcile_promise_prose(m, _FULFILLED, all_fulfilled=True)
    assert changed == ["appendix_c.tex"]
    out = (m / "appendix_c.tex").read_text(encoding="utf-8")
    # the fulfilled restatement names BOTH placed floats and drops the stale tell
    # (sentence-initial subject is capitalised; the second clause stays lower)
    assert "The sweep-tradeoff plot (Figure~\\ref{fig:resources})" in out
    assert "the witness-scaling plot (Figure~\\ref{fig:witness})" in out
    assert "are rendered in this version" in out
    assert "registered TODO" not in out
    assert "neither rendered" not in out
    # the sentence that FOLLOWED the promise sentence survives verbatim
    assert "The same data holds a fidelity that is undiscussed." in out


def test_reconcile_preserves_comments_and_adjacent_paragraphs(tmp_path):
    # the regression that a whole-file sentence split would cause: a rewrite must
    # not swallow the % marker or merge the neighbouring paragraph.
    m = _site(tmp_path)
    before_lines = _PROMISE_SITE.count("\n")
    fr.reconcile_promise_prose(m, _FULFILLED, all_fulfilled=True)
    out = (m / "appendix_c.tex").read_text(encoding="utf-8")
    assert "% appendix-p15" in out
    assert "% appendix-p16" in out
    assert out.count("\n") == before_lines          # no line added or dropped
    assert "Six defects were fixed." in out          # p16 lead survives


def test_reconcile_decrements_residue_tally_when_all_fulfilled(tmp_path):
    m = _site(tmp_path)
    fr.reconcile_promise_prose(m, _FULFILLED, all_fulfilled=True)
    out = (m / "appendix_c.tex").read_text(encoding="utf-8")
    assert "Seven items remain open:" in out         # Eight -> Seven
    assert "Eight items remain open" not in out
    assert "two unrendered figures" not in out       # clause dropped
    assert "one unmeasured assumption. A reader" in out   # clean re-join + period


def test_reconcile_leaves_tally_when_a_promise_is_unfulfilled(tmp_path):
    # a surviving honest-absence TODO means the residue tally is still TRUE;
    # all_fulfilled=False must leave both the count and the clause untouched.
    m = _site(tmp_path)
    fr.reconcile_promise_prose(m, _FULFILLED, all_fulfilled=False)
    out = (m / "appendix_c.tex").read_text(encoding="utf-8")
    assert "Eight items remain open" in out
    assert "two unrendered figures" in out
    # the named-plot sentence is still fulfilled-rewritten (that promise IS kept)
    assert "are rendered in this version" in out


def test_reconcile_skips_sentence_with_an_unfulfilled_plot(tmp_path):
    # a sentence naming a fulfilled AND a not-fulfilled plot stays honest.
    m = tmp_path / "man"
    m.mkdir()
    (m / "s1.tex").write_text(
        "The sweep-tradeoff plot and the coupling-landscape plot are not yet "
        "rendered in this version.\n", encoding="utf-8")
    fr.reconcile_promise_prose(m, _FULFILLED, all_fulfilled=False)
    out = (m / "s1.tex").read_text(encoding="utf-8")
    assert out == (
        "The sweep-tradeoff plot and the coupling-landscape plot are not yet "
        "rendered in this version.\n")  # untouched — mixed state


def test_reconcile_is_idempotent(tmp_path):
    m = _site(tmp_path)
    fr.reconcile_promise_prose(m, _FULFILLED, all_fulfilled=True)
    once = (m / "appendix_c.tex").read_text(encoding="utf-8")
    changed = fr.reconcile_promise_prose(m, _FULFILLED, all_fulfilled=True)
    twice = (m / "appendix_c.tex").read_text(encoding="utf-8")
    assert changed == []          # no marker left to match
    assert once == twice          # byte-stable


def test_run_apply_reconciles_the_promise_site(tmp_path):
    # end-to-end through run(): a manuscript that PROMISES a served plot AND
    # calls it not-rendered has its promise site reconciled and the manifest
    # records the reconciled file.
    m = tmp_path / "man"
    m.mkdir()
    (m / "s8.tex").write_text("% s8\n% NODES: n1\nThe verification section.\n",
                              encoding="utf-8")
    (m / "appendix_c.tex").write_text(
        "% appendix\nThe witness-scaling plot is a registered TODO, not yet "
        "rendered in this version.\n", encoding="utf-8")
    # a generator serving the witness-scaling promise, placed into s8 by PLACEMENT
    numerics = tmp_path / "numerics"
    numerics.mkdir()
    (numerics / "gen.py").write_text(_GEN_SCRIPT, encoding="utf-8")
    # PLACEMENT keys fig_witness -> s8; run without the matplotlib subprocess but
    # pretend the artefact exists so placement fires.
    figs = m / "figures"
    figs.mkdir()
    (figs / "fig_witness.pdf").write_bytes(b"%PDF-1.5 fake")
    (numerics.parent / "figures").mkdir(exist_ok=True)
    (numerics.parent / "figures" / "fig_witness.pdf").write_bytes(b"%PDF-1.5 fake")
    manifest = fr.run(m, numerics / "gen.py", apply=True, run_gen=False)
    assert "appendix_c.tex" in manifest["reconciled_sites"]
    ap = (m / "appendix_c.tex").read_text(encoding="utf-8")
    assert "registered TODO" not in ap
    assert "Figure~\\ref{fig:witness}" in ap


# --------------------------------------------------------------------------- #
# The lawful reader — read_manifest(): the banked manifest read back as facts,
# zero re-execution. view=mechanism: the /pipeline figures sub-card reads its
# state THROUGH this function, so these lock the fact contract (figures placed,
# promises matched/absent, computation-class intents banked), honest-absence as
# a first-class return (present=False, never a raise), and read-path purity (no
# subprocess/compile/network/write).
# --------------------------------------------------------------------------- #

# a banked manifest with the full spread: one matched-and-placed figure, one
# promise typed as an absent computation-class intent, a real generator_run.
_BANKED_MANIFEST = {
    "organ": "figure_runner",
    "manuscript": "some/manuscript",
    "generator_script": "some/numerics/gen.py",
    "promises": [
        {"phrase": "sweep-tradeoff", "keywords": ["sweep", "tradeoff"],
         "site_file": "s6.tex", "site_line": 3, "quote": "the sweep-tradeoff plot"},
        {"phrase": "coupling-landscape", "keywords": ["coupling", "landscape"],
         "site_file": "appendix_a.tex", "site_line": 5,
         "quote": "the coupling-landscape plot"},
    ],
    "generators": [
        {"name": "fig_resources", "script": "some/numerics/gen.py",
         "output": "fig_resources", "keywords": ["sweep", "resources"]},
    ],
    "matched_count": 1,
    "unmatched_count": 1,
    "generator_run": {"attempted": True, "ok": True,
                      "artefacts": ["figures/fig_resources.pdf"],
                      "log_tail": "wrote 1 figure"},
    "placed": [
        {"promise": "sweep-tradeoff", "generator": "fig_resources",
         "artefact": "figures/fig_resources.pdf", "placed_at": "s6.tex",
         "label": "fig:resources", "matched": True, "intent_id": None},
        {"promise": "coupling-landscape", "generator": None, "artefact": None,
         "placed_at": "appendix_a.tex", "label": "fig:todo-coupling-landscape",
         "matched": False, "intent_id": "RI-COMP-coupling-landscape"},
    ],
    "intents": [
        {"id": "RI-COMP-coupling-landscape", "cls": "computation",
         "promise": "coupling-landscape", "site": "appendix_a.tex:5",
         "note": "n", "status": "open", "record": "research-intent"},
    ],
    "reconciled_sites": ["appendix_c.tex"],
}


def _bank(tmp_path: Path, manifest=_BANKED_MANIFEST) -> Path:
    m = tmp_path / "man"
    m.mkdir()
    (m / "figure_manifest.json").write_text(
        json.dumps(manifest, indent=1), encoding="utf-8")
    return m


def test_read_manifest_returns_honest_facts(tmp_path):
    # (a) the fact contract off a hand-built banked manifest: one matched figure
    # placed, one promise absent-and-typed, one computation-class intent banked.
    m = _bank(tmp_path)
    facts = fr.read_manifest(m)
    assert facts["present"] is True
    assert facts["manuscript"] == "some/manuscript"
    assert facts["generator_script"] == "some/numerics/gen.py"
    assert facts["figures_placed"] == 1          # only the matched+placed row
    assert facts["promises_total"] == 2
    assert facts["promises_matched"] == 1
    assert facts["promises_absent"] == 1         # the promised-but-absent branch
    assert facts["intents_banked"] == 1          # computation-class
    assert facts["generator_run"]["attempted"] is True
    assert facts["generator_run"]["ok"] is True
    assert facts["generator_run"]["artefacts"] == 1   # count, not the paths
    # the raw rows the card renders per-figure are passed through
    assert len(facts["placed"]) == 2
    assert len(facts["intents"]) == 1
    assert facts["intents"][0]["id"] == "RI-COMP-coupling-landscape"
    assert facts["reconciled_sites"] == ["appendix_c.tex"]


def test_read_manifest_round_trips_the_writer(tmp_path):
    # view=mechanism end-to-end: run(apply=True) BANKS the manifest, read_manifest
    # reads back exactly what the organ wrote — a served plot placed into its
    # owning section (s8 via PLACEMENT) and an unserved plot typed as an intent.
    m = tmp_path / "man"
    m.mkdir()
    (m / "s8.tex").write_text("% s8\n% NODES: n1\nThe verification section.\n",
                              encoding="utf-8")
    (m / "appendix_a.tex").write_text(
        "% appendix\n% NODES: nc\nWe defer the witness-scaling plot and the "
        "coupling-landscape plot to later.\n", encoding="utf-8")
    numerics = tmp_path / "numerics"
    numerics.mkdir()
    (numerics / "gen.py").write_text(_GEN_SCRIPT, encoding="utf-8")
    # fake the served artefact so placement fires without the matplotlib run
    (m / "figures").mkdir()
    (m / "figures" / "fig_witness.pdf").write_bytes(b"%PDF-1.5 fake")
    (numerics.parent / "figures").mkdir(exist_ok=True)
    (numerics.parent / "figures" / "fig_witness.pdf").write_bytes(b"%PDF-1.5 fake")
    written = fr.run(m, numerics / "gen.py", apply=True, run_gen=False)

    facts = fr.read_manifest(m)
    assert facts["present"] is True
    assert facts["figures_placed"] == 1           # witness-scaling placed into s8
    assert facts["promises_total"] == 2
    assert facts["promises_matched"] == 1
    assert facts["promises_absent"] == 1          # coupling-landscape unserved
    assert facts["intents_banked"] == 1
    # the reader's counts agree with the manifest the writer banked
    assert facts["promises_matched"] == written["matched_count"]
    assert facts["promises_absent"] == written["unmatched_count"]
    assert facts["intents_banked"] == len(written["intents"])


def test_read_manifest_honest_empty_when_absent(tmp_path):
    # (b) a NEVER_RUN project has no manifest: present=False, every count zeroed,
    # every list empty, and NO raise / NO None.
    m = tmp_path / "never-run"
    m.mkdir()
    facts = fr.read_manifest(m)
    assert facts is not None
    assert facts["present"] is False
    assert facts["figures_placed"] == 0
    assert facts["promises_total"] == 0
    assert facts["promises_matched"] == 0
    assert facts["promises_absent"] == 0
    assert facts["intents_banked"] == 0
    assert facts["placed"] == []
    assert facts["intents"] == []
    assert facts["reconciled_sites"] == []
    # the absent shape carries the SAME keys as the present shape (the card reads
    # one payload contract either way)
    present = fr.read_manifest(_bank(tmp_path))
    assert set(facts) == set(present)


def test_read_manifest_corrupt_json_is_honest_absence(tmp_path):
    # a truncated / malformed artifact must not boom a pure GET: it degrades to
    # the honest-absence shape, not a raise.
    m = tmp_path / "man"
    m.mkdir()
    (m / "figure_manifest.json").write_text("{ this is not json",
                                            encoding="utf-8")
    facts = fr.read_manifest(m)
    assert facts["present"] is False
    assert facts["figures_placed"] == 0


def test_read_manifest_read_path_is_pure(tmp_path, monkeypatch):
    # (c) the GET-path purity guard: read_manifest does ONE read + ONE json.loads
    # and NOTHING else. Bank the manifest first, then boom every subprocess /
    # compile / write entrypoint; the read still returns the facts, proving none
    # of them is on the read path.
    m = _bank(tmp_path)

    def _boom(*a, **k):  # pragma: no cover - must never be reached
        raise AssertionError("read path fired a mutating/executing call")

    monkeypatch.setattr(fr.subprocess, "run", _boom)
    monkeypatch.setattr(fr, "run_generators", _boom)
    monkeypatch.setattr(fr, "run", _boom)              # no re-execution of run()
    monkeypatch.setattr(Path, "write_text", _boom)
    monkeypatch.setattr(Path, "write_bytes", _boom)
    monkeypatch.setattr(Path, "mkdir", _boom)

    facts = fr.read_manifest(m)                         # returns, does not boom
    assert facts["present"] is True
    assert facts["figures_placed"] == 1

    # the source-level guard: no subprocess/compile/network/write CALL form
    # appears in the reader's own body.
    src = inspect.getsource(fr.read_manifest)
    for tok in ("subprocess.run(", "run_generators(", ".write_text(",
                ".write_bytes(", ".mkdir(", "urllib", "requests",
                "socket.", "compile(", "http"):
        assert tok not in src, f"read path must not carry {tok!r}"
