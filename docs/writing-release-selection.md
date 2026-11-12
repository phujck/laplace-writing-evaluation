# Release export: owners, selection and refusals

How `scripts/writing_eval_manifest.py`, `scripts/export_writing_evaluation.py` and
`scripts/verify_writing_evaluation.py` decide what a Writing evaluation export contains. Written 2026-10-16 for the
research-collection release (`WORK-editor-campaign-release-portability-20261016`). It describes the tooling, not any
particular release.

## Metadata at its owner

Each authored metadata file is read where its owner keeps it (`writing_eval_manifest.metadata_paths`):

| File | Owner coordinate |
|---|---|
| `references.json` | `references_surface._manuscript`: the project state home (`manuscript_source.project_state_dir`) |
| `research_records.json` | `research_surface._project`: the same state home |
| `projection_plan.json` | the registry's declared `plan_path` |
| `figure_manifest.json` | `visuals_surface._m`: the registry manuscript home |
| built PDF | beside the selected TeX root |

An editable source-optional project keeps its references and research records in its state home whichever nested
draft is selected; the selected TeX directory is only the edit, compile and bibliography root.

## Intent

`--project-intent PROJECT=completed-manuscript` (default) requires all of the above.
`PROJECT=current-project-snapshot` may lack the figure manifest and built PDF, and may lack authored plan, reference
and research metadata: the manifest records each as `UNAUTHORED` (`project_closure.authored_metadata`) and nothing is
created. A present record that requires a missing current file (a placed figure, an artifact reference) still refuses.

## The selected source closure

The selected TeX root and its complete declared local inputs travel even when they lie outside the project
directory, together with every other required input (owner metadata, the built PDF, current record inputs). The
closure is the canonical declaration contract, `tex_dependencies.prepare_closure`: braced and unbraced `\input`,
includes resolved as TeX does (against the compilation directory), bibliography databases, local styles and classes,
graphics and graphic paths. Only those exact files travel; no ancestor tree is walked. Each is bound to every
selected project whose home (`project_dir` or registered `tex_root`) holds it (`source_bindings`) and copied once. A
file in the home of a registered project that is not selected refuses and names that project.

Every unresolved declaration refuses before anything is copied, naming its code and argument: a missing, ambiguous,
escaping or dynamic declaration, a missing graphic, a cyclic include, a private or fenced path and a symlinked path.
Two cases are qualified rather than refused, and both are recorded in `selected_source_closure`:

- `installed_inputs`: an `\input` of a bare name that `kpsewhich` finds inside the TeX distribution tree
  (`TEXMFDIST`/`TEXMFMAIN`), looked up with author and session search overrides (`TEXINPUTS`, `TEXMF*`, `KPATHSEA*`)
  removed. Example: `glyphtounicode`. The record names the distribution root, the distribution-relative path and
  the pin. Nothing is copied from the system, and verification re-observes the same file. An input found only
  through `TEXINPUTS`, `TEXMFHOME` or another checkout is not installed: it refuses like any missing input.
- `frozen_bibliography`: for a `current-project-snapshot` whose bibliography database is absent, the original
  `<root>.bbl` beside the selected root travels with its exact pin, and the missing databases are named. Editable
  bibliography regeneration is unavailable for that snapshot. No bibliography is invented. Without such a `.bbl`,
  or under `completed-manuscript`, a missing bibliography database refuses.

Installed package, class and bibliography-style requests (`installed_requests`) are never required as checkout files.

## Re-export and recorded history

Some history rows record an absolute store address of the checkout they were written in. One example is a Work bank
receipt naming `<checkout>/corpus_friction/work_orders.jsonl`. Selection relates such a row to an exact selected
ledger file and row id. An ordinary source checkout supplies only its own root for that match.

A published export supplies the original roots it records, so its re-export keeps those rows. These are the
absolute identity entries of `directory_aliases`. They count only after the export's portability index, export
manifest and source manifest agree by pin (`writing_eval_manifest.published_lineage`). The match is exact by root:
there is no suffix matching, and the original host is never read.

Each hop carries those roots forward. A re-export refuses before copying if it would drop any history row that its
published export selected for the same project (compared by ledger file and exact row bytes). New import-boundary
rows may be added.

## Empty project homes

An export carries files, and Git and ZIP keep no empty directory. A selected project's registered home that holds no
exportable authored file would vanish, for example an imported project whose selected TeX lives elsewhere, and a
re-export would then refuse ("registered project directory is missing"). Such a home receives the generated
marker `.writing-project-home.json`. It names the project and directory, is declared in `derived_files` and is
size-gated like every output. It is not a plan, reference, research record or source, and the authored metadata
status stays as recorded (for example `UNAUTHORED`). A home holding any exported file gets no marker.

On re-export the walk never counts the marker as an authored file; the marker is generated again. A different file
at that reserved path refuses. The verifier requires every selected home and checks that a marker present is the
exact declared generated marker.

## The reviewed selection

Without a policy a selected project's directory is exported whole (private, cache and secret fences apply).
`--selection-policy FILE` names a reviewed per-file selection:

```json
{"schema": "laplace.writing-export-selection/1",
 "projects": {"corpus-as-a-state": {"files": [
   {"path": "synthetics papers/corpus-as-a-state/README.md", "sha256": "sha256:...", "bytes": 8066,
    "decision": "include", "reason": "Authored campaign source"}]}}}
```

A project with an entry exports exactly its included files. Before anything is copied the export refuses when a walked
file is not reviewed, an included file is absent or its bytes differ, an excluded file's bytes changed since review, a
path lies outside the project, or an excluded file is a required input of ANY selected project. The policy's exact
bytes travel as `release/selection-policy.json`; the verifier checks that the export holds exactly the included files
with their pins, and a re-export may pass that same file (excluded entries may then be absent).

## Size

Every file the export would write is planned in memory before the destination directory exists: copied inputs,
supplementary companions, selected history, the travelled selection policy and every generated manifest. Any planned
file over 100 MiB (`LARGE_FILE_BYTES`) refuses, naming each path; there is no external-asset policy.
`--max-total-bytes N` bounds the complete written output, `release/export-manifest.json` included. The manifest
reports `output_size` (the written total) separately from `selected_size` (source-input bytes only). An omitted
required file is never treated as available.

## The portable index

`writing-portability.json` is the resolver's index: `writing_portability.source_path` parses it once per file
identity (inode, size, mtime, ctime) for every recorded-path lookup, under an unchanged 4 MiB guard. It therefore
lists only what resolution needs:

- `directory_aliases` maps the source checkout root to `.`. A copied file's own current-root spelling resolves
  through it to exactly its exported path, and that file's pin is `copied_files[path].sha256` in the export
  manifest. Such per-file primaries are not repeated; `directory_covered` records their count.
- `source_aliases` keeps every alias that says more: another target, pinned `versions`, a supplementary `reason`, or
  a historical or published `proof`.
- `alias_proofs` names `release/alias-proofs.json` with its pin and count. The proofs are evidence, not resolution
  input, and travel exactly beside the index.

For the 21-project collection this is 1,067 aliases in a 442 KB index (previously 20,252 aliases in 8.6 MB), with
identical resolution of every recorded spelling. An export written before this change keeps its old index and is
refused by the guard if it is larger than 4 MiB. Export again from the source checkout and verify; the project
files, history and pins are unchanged.

## Verification

Besides exact bytes, history and sources, the verifier reports authored-metadata status per project and checks:

- **The portable index.** Every pinned alias target is a declared file with its exact bytes. The alias proofs are
  the declared file the index names, with its pin and count.

- **The actual selection.** Under each policy project's home it inventories the files actually present, not the
  declared copy list. Anything other than the included files and declared derived outputs fails with its exact
  path: a reintroduced excluded file, an unreviewed addition, a private, runtime or secret name, a symlink or an
  oversized file. The private, runtime and secret check comes first and applies to every actual file. No copied
  or derived label exempts one.
- **Sizes.** Sizes are the actual file sizes. A declared byte count must agree with the actual size.
- **The source closure.** It is re-established in the export with the same owner: the same files, the same pins and
  the same frozen bibliography pin.
- **Links.** Every relative link of an exported Markdown entry document (inline, angle-bracket, titled or reference
  form) is classified by its owner:
  - `resolved`;
  - `missing-selected`: a selected project's directory, TeX root or manuscript directory, or a source binding (a
    failure);
  - `unselected-project`: the home of a registered project this export did not select (reported with that project,
    never copied);
  - `missing-common`: any other missing engine, script or document file (a failure).

  A `docs/` source whose exact bytes are the generated `README.md` or `AGENTS.md` is checked once, at that root
  location.

## Manuscript links and current Work inputs

One qualified relationship, read where its owner keeps it (`scripts/writing_portable_links.py`, which travels with
the export tooling), consumed by the manifest, the exporter and the verifier; no second link store and no second
acceptance policy.

- **Links.** Every `\href` in the selected TeX closure is classified finitely: an owner route relative to the app
  (`/research/artifact`, `/research/result`), the same route spelled absolutely on a host this machine answers for
  (loopback, private or link-local: the same relationship, recorded as host-bound, never an external success),
  another app route (`app-only`), another path on such a host (`unavailable`: it answers nowhere else), a URL on a
  public host (`external`, kept as written), or nothing (a provider working directory, a bare path, an ART id, an
  unresolved macro). An artifact link is admitted by the CANONICAL human owner
  (`research_artifact_read.resolve_read`): owner, receipt, scope, path and pin are judged together, exactly as the
  live link is, with the coordinates decoded once as the route decodes them (a literal `%2F` in a file name stays
  a file name). A result is identified by the Research catalogue (`research_catalogue.state_read`). One entry holds
  one admitted meaning: repeated references share it and list every place they occur (file, line, nearest heading,
  figure or table, spelling); a refused owner or receipt at the same path is another entry. Statuses: `packaged`
  (the admitted pin's bytes travel), `not-selected`, `changed` (the recorded revision is named, never substituted),
  `missing`, `unselected-project` (never copied), `refused` (the owner's own reason), `app-only`, `unavailable`,
  `external`. The source manifest records this under `manuscript_links`; the export manifest records it against
  what the export actually holds.
- **Work inputs.** The exact review each obligation resolves to in the canonical facet
  (`project_work_review.facet`): that review's own pins (which may cover inputs the obligation left undeclared),
  its verdict, currentness and independence; an obligation without a review lists its declared inputs unreviewed,
  with no pin claimed. Dispositions for this selection: `selected`, `supplementary`, `outside-closure`, `changed`,
  `missing`, `private`. Eligibility for the current-input selection is the facet's own satisfaction (accepted,
  current, independent where required), never equal bytes or ledger chronology. Recorded under `work_inputs` in
  both manifests; nothing is copied by following a Work row.
- **`--work-inputs current`.** Selects every eligible `outside-closure` input through the existing pinned
  supplementary route (`repository_path` = its exact path, `sha256` = its review pin, a reason naming the Work,
  obligation and review). An outside-closure input the facet does not call current, accepted and independent, or
  an unreviewed one, is an explicit omission with the facet's reason (`work_input_omissions`, also printed in the
  appendix and the HTML list); a reviewed input that is changed, missing or private refuses before the destination
  exists. Without the flag every input is stated, not copied.
- **`--portable-document`.** Stages a derived copy of each selected source closure under
  `portable/<project>/<original relative layout>`: each owner link becomes `\protect\hyperlink` to an entry of
  the generated appendix (`portable-links.tex`, input before `\end{document}`) that names the target, its status
  and where the text uses it, with `\href` relative to the delivered document for packaged targets; each packaged
  result gets an exact record page (`portable/<project>/records/<id>.html`, the owner's record with an element to
  land on) that is its destination; `links.html` beside them lists the same entries with relative links; the PDF is
  compiled from the derived copy by the declared build chain (`projection_viewer`: latexmk, else the pdflatex
  sequence) in a scratch directory and declared only when it is fresh and TeX reported no error
  (`portable_documents[project].pdf`, `compiler`), otherwise the exact reason is recorded and the TeX and HTML still
  travel. Every derived file is mapped to its exported source and pin. The author's manuscript, built PDF and
  history are unchanged and keep their live app links. A destination is written in three distinct steps: the
  filesystem path relative to the document, the relative URL (each segment percent-encoded exactly once, so a
  literal `%`, `#`, `?`, space or non-ASCII character in an owner-admitted file name is reached by decoding once;
  separators and `..` kept), and the HTML or TeX carrier escaping of that URL. Record pages are named by a digest
  of the qualified identity (project and the owner's exact result id), so distinct ids never share a page and a
  collision refuses. An omission states the live review observation and the omitted pin and says that the omission
  can make the imported review STALE; the imported canonical facet alone decides the resulting state.
- **Verification.** The optional portable metadata (`portable_documents`, `manuscript_links`, `work_inputs`) is
  admitted as a shape once before any of it is consumed; a malformed container or field is a named finite failure
  (`portable metadata shape: …`) and nothing of that section is read. Every candidate-controlled coordinate the new metadata names (a link target, a Work input
  path, a derived, appendix, HTML or PDF file) must first be a declared copied or derived entry of the export
  manifest, is then admitted through the verifier's shared read fence (`writing_export_bytes.Fence`: a regular
  file inside the root, no symbolic-link component, no climb) and only then hashed through the same streamed read;
  an undeclared, refused or unreadable coordinate is a finite failure, never an open outside the candidate. The
  verifier checks derived-to-source mapping, packaged link pins, travelling reviewed-input pins and stated reasons,
  and reports `manuscript_links`, `work_inputs` and `portable_documents` counts. The exported tooling runs from the
  export itself (`scripts/verify_writing_evaluation.py`, `scripts/export_writing_evaluation.py`) with no original
  checkout on the path.

## Tests

`tests/test_writing_release_portability.py`, with `tests/test_writing_eval_manifest.py`,
`tests/test_writing_evaluation_export.py` and `tests/test_writing_portable_links.py` (owner admission of links, the
facet-selected Work inputs and omissions, the portable copy with its record pages, the fenced verifier reads and the
isolated exported tooling, on one synthetic checkout).
