#!/usr/bin/env python3
"""Package or load the Writing image from repository Release assets (stdlib only)."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

SCHEMA = "laplace.writing-container-package/1"
MANIFEST = "container-package.json"
CHUNK = 4 * 1024 * 1024
PART_BYTES = 1_000_000_000  # Below GitHub's 2 GiB per-asset limit.


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


class Parts:
    """Write a compressed stream without retaining a second full archive."""
    def __init__(self, directory, limit=PART_BYTES):
        if limit < 1:
            raise ValueError("part size must be positive")
        self.directory, self.limit = directory, limit
        self.rows, self.stream, self.size = [], None, 0

    def write(self, data):
        total = len(data)
        while data:
            if self.stream is None:
                self.name = f"container-image.tar.gz.part{len(self.rows) + 1:03d}"
                self.stream = (self.directory / self.name).open("xb")
                self.hasher, self.size = hashlib.sha256(), 0
            n = min(len(data), self.limit - self.size)
            block, data = data[:n], data[n:]
            self.stream.write(block)
            self.hasher.update(block)
            self.size += n
            if self.size == self.limit:
                self.close()
        return total

    def flush(self):
        if self.stream:
            self.stream.flush()

    def close(self):
        if self.stream:
            self.stream.close()
            self.rows.append({"name": self.name, "bytes": self.size,
                              "sha256": self.hasher.hexdigest()})
            self.stream = None


def inspect_image(image):
    return json.loads(subprocess.check_output(["docker", "image", "inspect", image], text=True))[0]


def pack(root, output, image, tag):
    output.mkdir(parents=True, exist_ok=False)
    source = inspect_image(image)
    if source["Os"] != "linux" or source["Architecture"] != "amd64":
        raise ValueError("this release must contain the verified Linux/amd64 image")
    subprocess.run(["docker", "tag", image, tag], check=True)
    parts = Parts(output)
    with subprocess.Popen(["docker", "image", "save", tag], stdout=subprocess.PIPE) as process:
        try:
            with gzip.GzipFile(fileobj=parts, mode="wb", compresslevel=1, mtime=0) as compressed:
                shutil.copyfileobj(process.stdout, compressed, CHUNK)
            if process.wait():
                raise RuntimeError("docker image save failed; package is incomplete")
        finally:
            parts.close()
    workspace = output / "laplace-writing-workspace.zip"
    subprocess.run(["git", "archive", "--format=zip", "--output=" + str(workspace), "HEAD"],
                   cwd=root, check=True)
    manifest = {"schema": SCHEMA, "image": image, "local_tag": tag,
                "image_id": source["Id"], "platform": "linux/amd64",
                "workspace_commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
                "parts": parts.rows,
                "workspace": {"name": workspace.name, "bytes": workspace.stat().st_size,
                              "sha256": digest(workspace)}}
    (output / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def verified_package(directory):
    directory = directory.resolve()
    manifest = json.loads((directory / MANIFEST).read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA or manifest.get("platform") != "linux/amd64":
        raise ValueError("unsupported container package")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", manifest.get("image_id", "")):
        raise ValueError("invalid recorded image identity")
    if not re.fullmatch(r"laplace-writing:[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}",
                        manifest.get("local_tag", "")):
        raise ValueError("invalid package image tag")
    rows = manifest.get("parts")
    if not isinstance(rows, list) or not rows:
        raise ValueError("package has no image parts")
    for index, row in enumerate(rows, 1):
        if row.get("name") != f"container-image.tar.gz.part{index:03d}":
            raise ValueError("image parts must be consecutive and in recorded order")
        path = directory / row["name"]
        if path.is_symlink() or not path.is_file() or path.stat().st_size != row.get("bytes"):
            raise ValueError("missing or wrong-sized image part: " + row["name"])
        if digest(path) != row.get("sha256"):
            raise ValueError("image part checksum mismatch: " + row["name"])
    return manifest


def load(directory, force=False):
    manifest = verified_package(directory)
    try:
        current = inspect_image(manifest["local_tag"])
    except subprocess.CalledProcessError:
        current = None
    if force or not current or current["Id"] != manifest["image_id"]:
        # Docker accepts the gzip stream directly. No multi-GB reassembly copy.
        with subprocess.Popen(["docker", "image", "load"], stdin=subprocess.PIPE) as process:
            try:
                for row in manifest["parts"]:
                    with (directory / row["name"]).open("rb") as stream:
                        shutil.copyfileobj(stream, process.stdin, CHUNK)
            finally:
                process.stdin.close()
            if process.wait():
                raise RuntimeError("Docker refused the image archive")
    actual = inspect_image(manifest["local_tag"])
    if actual["Id"] != manifest["image_id"] or actual["Os"] != "linux" or actual["Architecture"] != "amd64":
        raise ValueError("loaded image does not match the package's recorded identity")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    builder = sub.add_parser("pack")
    builder.add_argument("--output", type=Path, required=True)
    builder.add_argument("--image", required=True)
    builder.add_argument("--tag", required=True)
    for name in ("load", "start"):
        action = sub.add_parser(name)
        action.add_argument("--package", type=Path, default=Path(".container-package"))
        action.add_argument("--force", action="store_true", help="reload even if exact image is already installed")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.command == "pack":
        print(json.dumps(pack(root, args.output.resolve(), args.image, args.tag), indent=2))
        return
    manifest = load(args.package.resolve(), args.force)
    print("Verified image: " + manifest["image_id"], flush=True)
    if args.command == "start":
        if not (root / "registry_projects.json").is_file():
            raise ValueError("run this script from the complete Writing repository or workspace ZIP")
        env = dict(os.environ, LAPLACE_WORKSPACE=str(root), LAPLACE_IMAGE=manifest["local_tag"])
        print("Open http://127.0.0.1:" + env.get("LAPLACE_PORT", "8771") +
              "/project?workspace=writing ; Ctrl+C stops the server.", flush=True)
        subprocess.run(["docker", "compose", "-f", str(root / "deploy/writing/compose.registry.yaml"),
                        "up", "--pull", "never"], cwd=root, env=env, check=True)


if __name__ == "__main__":
    main()
