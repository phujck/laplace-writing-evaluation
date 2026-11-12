# Current evaluation registry image

The current image repository is `ghcr.io/phujck/laplace-writing-evaluation`. Use the actual published tag/digest and run command in [README](../README.md). The image carries the complete selected workspace as well as application code/runtime; it does not require a separately mounted clone or the author’s private workspace.

A public package should pull anonymously. Registry authentication is not an AI-provider login. If a pull is denied, confirm the exact published reference and package visibility; do not substitute an older private `laplace-writing` image or copy the publisher’s credentials.

## Image identity and updates

A tag can identify the release for people; an immutable digest identifies the downloaded image bytes. The publication record linked from README records both the observed registry identity and the qualified source/data selection. Local image IDs and registry manifest digests are different identities.

Use a fresh named volume for a new source revision. Existing volumes carry your saved work and an image/source marker; a mismatch is held for explicit migration rather than overwritten. See [container storage](writing-container.md#what-persists).

The default image is CPU-oriented. GPU examples require their declared compatible hardware/runtime and explicit device access. The publication record states the actual tested platform; other host/architecture combinations require their own checks.
