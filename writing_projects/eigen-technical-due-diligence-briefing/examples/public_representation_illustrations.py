"""Public metadata derivation around one unchanged deterministic illustration run.
Not a new scientific experiment, empirical benchmark or independent verification.
Only the pinned executable, public parameter JSON and generated outputs are read.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import runpy
import sys

ORIGINAL_SHA = "6fbec2ba4f746abc5e5038455b450e0ef1ca546a64803a6827ac45b3cbcde670"
PARAMETER_SHA = "61b593fdfa0672b09859c813e28a8dcb6dea12cce56c7607b334da7e6710a713"

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["smoke"], required=True)
    parser.add_argument("--args-json", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    if json.loads(args.args_json) != {}:
        raise ValueError("No arguments are admitted")
    root = Path(__file__).resolve().parent.parent
    if Path.cwd().resolve() != root:
        raise ValueError("Expected declared projectRoot cwd")
    original = root / "calculations/representation_illustrations.py"
    parameters = root / "examples/public-illustration-inputs-v1.json"
    if sha(original) != ORIGINAL_SHA or sha(parameters) != PARAMETER_SHA:
        raise ValueError("Pinned public input changed")
    public_inputs = json.loads(parameters.read_bytes())
    if public_inputs["executable"]["sha256"] != ORIGINAL_SHA:
        raise ValueError("Parameter executable pin mismatch")
    result = Path(args.result)
    if not result.is_absolute():
        raise ValueError("Result path must be absolute")
    raw = result.with_name(result.stem + ".raw.json")
    output = raw.parent / (raw.stem + "-illustrations")
    # Claim the derived result exclusively first. Failed partials are retained.
    if any(p.exists() for p in (result, raw, output)):
        raise FileExistsError("Refusing existing result/raw/output collision")
    result.parent.mkdir(parents=True, exist_ok=True)
    with result.open("x", encoding="utf-8") as destination:
        old_argv = sys.argv
        try:
            sys.argv = [str(original), "--mode", "smoke", "--args-json", "{}", "--result", str(raw)]
            runpy.run_path(str(original), run_name="__main__")  # exactly once; no retries
        finally:
            sys.argv = old_argv
        raw_bytes = raw.read_bytes()
        original_result = json.loads(raw_bytes)
        before_hashes = {}
        for artifact in original_result["artifacts"]:
            path = Path(artifact["path"])
            if not path.is_absolute():
                path = root / path
            if path.resolve().parent != output.resolve():
                raise ValueError("Original artifact escaped expected output directory")
            digest = sha(path)
            if digest != artifact["sha256"]:
                raise ValueError("Original artifact hash mismatch")
            before_hashes[str(path)] = digest
        if sha(original) != ORIGINAL_SHA or sha(parameters) != PARAMETER_SHA:
            raise ValueError("Input changed during execution")
        derived = copy.deepcopy(original_result)
        derived["schema_version"] = "public.illustration-metadata-derivation/1"
        derived["status"] = "derived"
        derived["interpretation"] = (
            "Metadata derivation from one execution of the unchanged supplied deterministic "
            "illustrations; not a new scientific experiment, empirical benchmark, "
            "independent verification or theorem acceptance."
        )
        derived["source_basis"] = [
            {"path": "examples/public-illustration-inputs-v1.json", "scope": "project", "sha256": PARAMETER_SHA},
            {"path": "calculations/representation_illustrations.py", "scope": "project", "sha256": ORIGINAL_SHA}
        ]
        derived["raw_result"] = {
            "path": str(raw), "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "bytes": len(raw_bytes), "retained_byte_exact": True,
            "historical_source_basis": "Names emitted by original only; unavailable notes were not read."
        }
        derived["metadata_derivation"] = {
            "kind": "metadata-only", "original_executions": 1,
            "not_new_scientific_experiment": True,
            "checks_equal_raw": derived["checks"] == original_result["checks"],
            "parameters_equal_raw": derived["parameters"] == original_result["parameters"],
            "artifacts_equal_raw": derived["artifacts"] == original_result["artifacts"],
            "public_parameter_artifact_is_explanatory_not_runtime_override": True
        }
        assert all(derived["metadata_derivation"][key] for key in
                   ("checks_equal_raw", "parameters_equal_raw", "artifacts_equal_raw"))
        assert raw.read_bytes() == raw_bytes
        assert all(sha(Path(path)) == digest for path, digest in before_hashes.items())
        destination.write(json.dumps(derived, indent=2) + "\n")
    print(json.dumps({"kind": "metadata-derivation", "result": str(result),
                      "raw_result_sha256": derived["raw_result"]["sha256"],
                      "original_executions": 1, "artifacts_retained": len(before_hashes)}))

if __name__ == "__main__":
    main()
