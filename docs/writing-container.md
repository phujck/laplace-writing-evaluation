# Run the evaluation image

The current evaluation image contains the Writing application, full source and tests, four canonical papers with their figure/method/result inputs, and the genuine **Behaviour example** project with its saved author, review and synthesis records. It starts with this selected public workspace already present; no host checkout, Python environment or private author workspace is required.

Use the published command in [README](../README.md). The runtime listens on container port 8771; the documented loopback mapping opens the application at <http://127.0.0.1:8772/project?workspace=writing&app=projects>.

## What persists

One named Docker volume is mounted at `/data`:

| Location | Purpose |
| --- | --- |
| `/data/workspace` | Writable complete workspace: papers, source, project records and saved changes |
| `/data/session-workspaces` | Provider working directories, outside the workspace’s repository instructions |
| `/data/accounts` | Runtime HOME and account configuration, initially unauthenticated |

The immutable distribution seed is `/opt/evaluation/seed`. First launch verifies all manifest-declared files, copies them into an empty data volume, and derives the local image-Python runtime configuration. The runtime configuration is recorded as an explicit derivation from the verified seed. Initialization also creates a new local Git snapshot for the distributed workspace, with the upstream image/source revision recorded separately. Scientific inputs and retained run records keep their original bytes. Later starts preserve the marked workspace and saved work.

The entrypoint refuses an unmarked nonempty data directory or an incompatible source-revision marker. It does not replace an existing volume with a different image’s seed. To inspect a newer distribution, use a different named volume; move selected work deliberately with the [project handover owner](project-data-handover.md).

Stopping or removing the container leaves the named volume intact. Saved manuscript edits and records live there. Browser drafts remain browser state until saved. Keep or back up your data volume when retaining work; removing the volume removes its saved workspace and account configuration.

## Read, edit and reproduce

Start in **Projects**. Read a paper through **Writing → PDF**, inspect **TeX**, and follow **Research → Open the evidence** to actual inputs/results. Open **Behaviour example** for its saved conversation, proposal, independent review and synthesis. The [behaviour tour](writing-behaviour-tour.md) maps the implemented groups to real records and reproduction recipes.

The image supplies CPU PyTorch, the declared application/analysis/media/literature dependencies, TeX/rendering tools, Node and Chromium, plus the pinned provider CLIs. The default runtime is CPU-based. Reading retained GPU/model results does not execute them. GPU-tagged recipes need a compatible NVIDIA device/driver, explicit Docker GPU access and the declared CUDA/PyTorch/CuPy/Triton runtime for that recipe. A CPU image does not become a qualified GPU runtime merely by receiving a device. Provider work separately needs the user’s own authenticated CLI account; see [account setup](writing-account-setup.md).

Source execution checks require working Linux namespace isolation as well as Bubblewrap. The tested image includes the binary, but the observed default Docker policy refused the user-namespace operation; a separate seccomp-unconfined diagnostic still refused mounting. Source-check execution is therefore not qualified inside the plain-container run. The guarded refusal remains in place; the default launch does not request privileged mode or waive isolation. Use an explicitly supported host/runtime policy for that capability. Formal Lean recipes separately require the declared Lean/lake toolchain. Consult the image verification record for the capabilities actually exercised.

The publication record identifies the tested image platform. Docker Desktop can run Linux containers on other hosts, but the observed Linux container checks are not native Windows/macOS or ARM performance qualification.

## Build and verify a matching image

The current self-contained recipe is [deploy/evaluation/Dockerfile](../deploy/evaluation/Dockerfile). The older `deploy/writing` recipes describe a separate runtime-plus-mounted-workspace architecture and are not the current evaluation-image entry point.

The publisher’s clean-download check must start from the registry image and a fresh volume with no host checkout/auth mounts. Its recorded checks cover seed pins, paper/PDF bytes, source/figure assets, retained body/history reads, the default example, CPU reproduction and persistence across a container restart. Read the actual publication/verification record linked from README for observed results and immutable image identity.
