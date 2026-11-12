# Run and inspect the research campaigns

The Writing App includes the code behind the SuperARC campaign and the two linked
memory studies, **Corpus as a State** and **Memory in Pieces**. The papers explain
the arguments; the folders below contain their implementations, protocols,
recorded results and figure producers. Historical results keep their original
identities. Running a command creates a new observation rather than renewing an
old benchmark claim.

Run the commands below from the repository root. The supplied container already
provides the Writing App and its CPU research dependencies. For a local checkout,
use the Python environment installed by the entry README. In the examples,
`python` means that environment's interpreter.

## Find the code

| Question | Start here |
|---|---|
| How did the SuperARC score work? | [`src/laplace/research/superarc/phi.py`](../src/laplace/research/superarc/phi.py), [`bdm.py`](../src/laplace/research/superarc/bdm.py), and [`bin_classifier.py`](../src/laplace/research/superarc/bin_classifier.py) |
| How were candidates executed and development items made? | [`sequence_exec.py`](../src/laplace/research/superarc/sequence_exec.py), [`genesis_loop.py`](../src/laplace/research/superarc/genesis_loop.py), and [`dev_suite.py`](../src/laplace/research/superarc/dev_suite.py) |
| What did the SuperARC campaign actually produce? | [`synthetics papers/superarc/frozen_run`](../synthetics%20papers/superarc/frozen_run/), its report, preregistration and retained answer/program records |
| Which exact SuperARC code was frozen for that run? | [`historical-source/frozen-run-20260804/recovery-manifest.json`](../synthetics%20papers/superarc/historical-source/frozen-run-20260804/recovery-manifest.json) pins all eleven original harness files; their exact bytes are stored alongside it. Current development code is separate. |
| Where is the first memory construction? | [`synthetics papers/corpus-as-a-state/numerics`](../synthetics%20papers/corpus-as-a-state/numerics/) and the adjacent original manuscript |
| Where are ingestion, query semantics and the independent reference answers? | [`reconstruction`](../synthetics%20papers/corpus-as-a-state/reconstruction/): `oracle.py`, `semantic.py`, `section_ingest.py`, `section_news_ingest.py`, `section_native_query.py`, and their tests |
| Where are the later Skein/Parallax experiments? | [`reconstruction/extension`](../synthetics%20papers/corpus-as-a-state/reconstruction/extension/): protocols, source-view extraction, witness/readout and packing methods, benchmark drivers and retained results |
| Where are the reusable algorithms and GPU kernels now? | [`src/atlas/reconstruction`](../src/atlas/reconstruction/). Some historical campaign entry files are explicit adapters to these included modules. |
| Which code and inputs produced a historical result? | The campaign's release manifests, `results/code_snapshots`, and [`reconstruction/evidence`](../synthetics%20papers/corpus-as-a-state/reconstruction/evidence/). Read the manifest before extracting a frozen bundle. |
| How were the DD figures made? | [`writing_projects/eigen-technical-due-diligence-briefing/calculations`](../writing_projects/eigen-technical-due-diligence-briefing/calculations/) and its adjacent evidence snapshots and research records |

The campaign READMEs describe their original working environment. Absolute paths
there are historical coordinates. The portable commands on this page are the
entry points for this release. The release inventory distinguishes retained
evidence bundles from regenerable embedding caches and downloaded model weights.

## Quick CPU checks

These checks need no model account, model inference, GPU or benchmark download.

### SuperARC arithmetic and complexity measure

The small MIT-licensed BDM implementation and binary reference table are included
under `models/ctm`, with their licence and checksummed source manifest. Set the
path explicitly so the same command works with an installed package:

```sh
export LAPLACE_CTM_DIR="$PWD/models/ctm"
python - <<'PY'
from laplace.research.superarc.bdm import nbdm
expected = 0.39709716116701
observed = nbdm("1,1,0,0,0,1,0,0,0,0,1,0")
assert abs(observed - expected) < 1e-12
print("BDM reference check passed")
PY
```

For the fuller arithmetic checks, install `pytest` in the local environment if it
is not present, then run:

```sh
python -m pytest -q tests/test_superarc_bdm.py tests/test_superarc_phi.py
```

Tests requiring the original authors' external answer table report a skip when
that input is absent. The independent arithmetic fixtures still run.

### Memory reference semantics

The reference evaluator uses exact sets, integers and rational probabilities:

```sh
python "synthetics papers/corpus-as-a-state/reconstruction/oracle.py" --self-test
```

To produce a small development example, keeping method input separate from the
reference answers:

```sh
python "synthetics papers/corpus-as-a-state/reconstruction/oracle.py" \
  --family distributed --seed 1702 --split development --n 32 \
  --output runs/memory-example/method-input.json \
  --evaluator-output runs/memory-example/reference-answers.json
```

The evaluator is a correctness reference, not the fast reconstruction method.
Do not feed `reference-answers.json` to the method being evaluated.

### Original eight-point counterexample and its figure

This example exhaustively checks 127 partitions and generates the original
counterexample figure using NumPy and Matplotlib. Output is directed to a new
folder so the historical result and figure remain intact:

```sh
python - <<'PY'
from pathlib import Path
import os, sys
out = Path("runs/corpus-counterexample").resolve()
out.mkdir(parents=True, exist_ok=False)
for key, folder in [("CACHE", "cache"), ("RESULTS", "results"),
                    ("FIGURES", "figures"), ("MODELS", "models")]:
    os.environ["CORPUS_STATE_" + key] = str(out / folder)
numerics = Path("synthetics papers/corpus-as-a-state/numerics").resolve()
sys.path.insert(0, str(numerics))
from c13_counterexample import main
main()
PY
```

This is the eight-point `c13_counterexample` calculation, not the separate
16-point experiment recorded as `C13`.

## Reproduce the DD SuperARC figure from retained results

This redraws the campaign's recorded score and format controls. It makes no new
model calls or benchmark measurements:

```sh
cd writing_projects/eigen-technical-due-diligence-briefing
mkdir -p runs/reproduce-superarc
python calculations/superarc_figure.py --mode smoke --args-json '{}' \
  --result runs/reproduce-superarc/result.json
```

The result names the input digest and the generated PDF, SVG and PNG. Choose a
new output folder for a subsequent run; the producer refuses to overwrite its
figure directory.

## Full development and benchmark runs

**SuperARC.** The original benchmark is a separate upstream dependency, pinned in
`synthetics papers/superarc/dev_suite/manifest.json` to commit
`0e6cb65a6575ba4d543fcf2c05d76f20180065ab` of
[AlgoDynLab/SuperintelligenceTest](https://github.com/AlgoDynLab/SuperintelligenceTest).
Use its own distribution terms. The acquisition folder needs a `repo/` checkout
and a `manifest.json` identifying the source and CSV. The following creates a new
acquisition; it does not pretend to recover the original temporary acquisition
manifest:

```sh
export LAPLACE_SUPERARC_BENCH="$PWD/runs/superarc-upstream"
mkdir -p "$LAPLACE_SUPERARC_BENCH"
git init "$LAPLACE_SUPERARC_BENCH/repo"
git -C "$LAPLACE_SUPERARC_BENCH/repo" remote add origin \
  https://github.com/AlgoDynLab/SuperintelligenceTest
git -C "$LAPLACE_SUPERARC_BENCH/repo" fetch --depth 1 origin \
  0e6cb65a6575ba4d543fcf2c05d76f20180065ab
git -C "$LAPLACE_SUPERARC_BENCH/repo" checkout --detach FETCH_HEAD
python - <<'PY'
import hashlib, json, os, subprocess
from pathlib import Path
base = Path(os.environ["LAPLACE_SUPERARC_BENCH"])
commit = subprocess.check_output(
    ["git", "-C", str(base / "repo"), "rev-parse", "HEAD"], text=True).strip()
assert commit == "0e6cb65a6575ba4d543fcf2c05d76f20180065ab"
relative = "data/RandomBinarySeriesWithLLMs.csv"
digest = hashlib.sha256((base / "repo" / relative).read_bytes()).hexdigest()
assert digest == "fcc08553c1b4d6c104a3d1ca7e72c2b885be6168ee64c95f99adf5f7dea86ccb"
manifest = {
    "source": {"commit_sha": commit,
               "clone_url": "https://github.com/AlgoDynLab/SuperintelligenceTest"},
    "key_files": {"binary_suite_csv": {"path": relative,
                 "sha256": digest, "sequence_column": "sequence"}},
    "purpose": "New pinned acquisition for development-suite verification"
}
with (base / "manifest.json").open("x") as f:
    json.dump(manifest, f, indent=2)
PY
```

The development-suite verifier then checks the exclusion and generated-item
digests against the retained suite:

```sh
python -m laplace.research.superarc.dev_suite --verify \
  --out "synthetics papers/superarc/dev_suite" \
  --bench "$LAPLACE_SUPERARC_BENCH"
```

The original published-score comparison additionally uses
`LAPLACE_SUPERARC_CSV` for the supplied answer table. Generating new model answers
is a separate, potentially costly run; it needs an explicitly configured provider
and a declared evaluation protocol. Reading or replotting the frozen campaign
does not trigger it.

The frozen campaign recorded eleven harness-file hashes. The included
historical-source snapshot recovers all eleven original files exactly; its
manifest records where each was recovered. Current development includes later
repairs, including portable development-suite arithmetic, and keeps its own
source identity. Use a separate
working copy when reconstructing that harness, leaving the current application
and the original run records unchanged.

**Memory in Pieces.** Read the exact evaluation protocol and split manifest for
the chosen driver before running it. The CUDA reconstruction and Triton
contraction benchmarks require an NVIDIA GPU, a compatible driver and the
optional dependencies declared by `atlas/pyproject.toml`:

```sh
python -m pip install './atlas[reconstruction-kernels]'
```

The CPU application image does not pretend to provide a GPU. Use the appropriate
GPU-enabled environment for these runs. The original campaign also includes
embedding and language-reader experiments: their corpus downloads, encoder
weights and model endpoint must be supplied as specified in the corresponding
protocol. Data manifests, code snapshots and frozen results remain available for
inspection without those services.

Keep development and held-out inputs separate. Preserve the original protocols
and outputs, run into a separate working copy or output directory, and report
ingestion/build time, memory, cold and warm query costs, correctness and reader
quality separately. A successful CPU packaging check is not a fresh GPU timing
or a new held-out result.
