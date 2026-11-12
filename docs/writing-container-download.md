# Download and start the complete evaluation

Use the current public image and the single run command in [README](../README.md). Docker downloads both the application runtime and its complete selected public workspace. There is no separate workspace ZIP, private repository Release, split image archive or host source checkout to assemble.

The first start seeds an empty named volume from the image’s verified distribution. Open <http://127.0.0.1:8772/project?workspace=writing&app=projects>, choose one of the four papers, or open **Behaviour example** and follow the [tour](writing-behaviour-tour.md). Reading, manual editing and retained evidence inspection need no provider login.

The [container guide](writing-container.md) explains the persistent workspace, provider working directories and account home. Reuse the same volume to retain saved work. For a different image/source revision, start a separate volume and use an explicit handover for your work; the entrypoint does not silently overwrite a populated workspace.

## Check the download

The published tag is a convenient name. The immutable registry digest and exact source/data selection belong to the matching publication record linked from README. The publisher verifies a fresh registry download with no author checkout or credentials mounted, including actual saved-history/body reads and restart persistence.

For an existing local installation, `docker pull` downloads the named image; an already-running container keeps its current image until recreated. Preserve its volume when recreating it. Download completion is distinct from successful startup and from the actual verification results.

## Earlier Writing packages

Earlier `laplace-writing` runtime images and split private Release packages retain their own stored collections and manifests. They are historical distributions, not substitutes for this workspace-baked evaluation image. Use their own documentation only when reproducing those editions. Current canonical papers and the current image entry are in this repository’s README.
