"""tools - the commands that turn a bundle into evidence.

Three, all of them read-mostly and all of them runnable as ``python -m atlas.tools.<name>``:

    build_spans     read a bundle AS DATA and write spans.jsonl + segmentation.json beside it
    export_verify   verify a bundle and print its seal report; nonzero exit on any refusal
    segment_sweep   the span-size sweep - measure, print, write nothing

``build_spans`` is where the one-way dependence lands: the laplace-side exporter writes nodes
and blobs and never imports atlas, so segmentation - which is atlas code - runs afterwards, over
the bundle, from this side. It writes ``segmentation.json`` beside the bundle and never mutates
``manifest.json``: the snapshot's identity is fixed at export and a later segmentation cannot
reach back and change it.
"""
