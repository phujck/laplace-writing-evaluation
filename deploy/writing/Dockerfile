# syntax=docker/dockerfile:1.7
# STAGE ORDER (M5 S3, release cache boundary). Everything heavy and pinned comes first and depends only on its
# declarations: the OS packages, the Python dependency closure (resolved from the two pyproject files), Node and
# the pinned provider CLIs. The application source and its --no-deps install come LAST, in the same APP block at
# the end of each named target (runtime, provider-codex, provider-claude, provider-both). A source-only change
# therefore rebuilds only those light layers; it never invalidates the dependency or provider npm layers.
# tests/test_writing_recipe_order.py checks the order and that the four APP blocks are byte-identical. Each APP install
# retires its generated build output (the two setuptools build trees and the two source egg-info directories) after a
# successful install; the installed site .dist-info stays the canonical metadata.
FROM python:3.12-slim-bookworm AS deps

ARG LAPLACE_UID=1000
ARG LAPLACE_GID=1000
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LAPLACE_SESSION_WORKSPACES=/var/lib/laplace/session-workspaces

# texlive-publishers carries REVTeX (revtex4-2.cls, apsrev4-2.bst: the QDE original source) and lmodern carries
# lmodern.sty (the DD briefing); the 45-request installed-dependency audit found only these three missing. cm-super
# carries the scalable Type 1 EC fonts a T1-encoded document (the VWO source) needs, without which pdfTeX falls back to
# bitmap fonts. The build refuses unless kpsewhich finds each input, the recorded installed input (the pdfTeX glyph
# map), the T1 map cm-super-minimal ships (cm-super-minimal-t1.map;
# cm-super depends on cm-super-minimal) and one cm-super EC outline font.
RUN apt-get update && apt-get install -y --no-install-recommends \
      biber bibtex2html ca-certificates cm-super ghostscript git graphviz latexmk lmodern \
      librsvg2-bin poppler-utils qpdf ripgrep tini \
      tex-gyre texlive-fonts-extra texlive-fonts-recommended texlive-latex-base \
      texlive-latex-extra texlive-latex-recommended texlive-pictures texlive-plain-generic texlive-publishers \
      texlive-science \
    && rm -rf /var/lib/apt/lists/* \
    && for input in revtex4-2.cls apsrev4-2.bst lmodern.sty glyphtounicode.tex cm-super-minimal-t1.map sfrm1000.pfb; do \
         kpsewhich "$input" >/dev/null || { echo "missing TeX distribution input: $input" >&2; exit 1; }; \
       done \
    && groupadd --gid "${LAPLACE_GID}" laplace \
    && useradd --uid "${LAPLACE_UID}" --gid "${LAPLACE_GID}" --create-home laplace

WORKDIR /opt/laplace
# Resolve the declared CPU runtime once per dependency change. Source edits must
# rebuild the real packages, but need not download their dependencies again.
COPY atlas/pyproject.toml ./atlas/
COPY pyproject.toml ./
RUN python - <<'PY'
import re
import subprocess
import sys
import tomllib
from pathlib import Path

requirements = []
for filename, extras in [("atlas/pyproject.toml", ()), ("pyproject.toml", ("research", "review"))]:
    data = tomllib.loads(Path(filename).read_text(encoding="utf-8"))
    project = data["project"]
    if {"dependencies", "optional-dependencies"} & set(project.get("dynamic", [])):
        raise SystemExit(f"{filename}: dynamic dependencies require a reviewed container recipe")
    groups = [data["build-system"]["requires"], project.get("dependencies", [])]
    groups.extend(project["optional-dependencies"][extra] for extra in extras)
    own_name = re.sub(r"[-_.]+", "-", project["name"]).lower()
    for group in groups:
        for requirement in group:
            match = re.match(r"[A-Za-z0-9_.-]+", requirement)
            if not match or re.sub(r"[-_.]+", "-", match[0]).lower() == own_name:
                raise SystemExit(f"{filename}: local/self dependency requires a reviewed recipe")
            requirements.append(requirement)
subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir",
                *dict.fromkeys(requirements)], check=True)
PY
EXPOSE 8771
ENTRYPOINT ["/usr/bin/tini","--","/usr/local/bin/laplace-writing-entrypoint"]
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD ["python","-c","import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8771/authoring/health',timeout=2)); assert d['runtime']=='writing'"]

FROM node:22-bookworm-slim AS node22

FROM deps AS provider-deps
COPY --from=node22 /usr/local/bin/node /usr/local/bin/node
COPY --from=node22 /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && node --version | grep '^v22\.'

FROM provider-deps AS provider-codex-deps
ARG CODEX_NPM_SPEC=@openai/codex@0.160.1
RUN test -n "${CODEX_NPM_SPEC}" \
    && npm install --global --omit=dev "${CODEX_NPM_SPEC}" \
    && npm cache clean --force

FROM provider-deps AS provider-claude-deps
ARG CLAUDE_NPM_SPEC=@anthropic-ai/claude-code@2.1.304
RUN test -n "${CLAUDE_NPM_SPEC}" \
    && npm install --global --omit=dev "${CLAUDE_NPM_SPEC}" \
    && npm cache clean --force

FROM provider-deps AS provider-both-deps
ARG CODEX_NPM_SPEC=@openai/codex@0.160.1
ARG CLAUDE_NPM_SPEC=@anthropic-ai/claude-code@2.1.304
RUN test -n "${CODEX_NPM_SPEC}" && test -n "${CLAUDE_NPM_SPEC}" \
    && npm install --global --omit=dev "${CODEX_NPM_SPEC}" "${CLAUDE_NPM_SPEC}" \
    && npm cache clean --force

FROM deps AS runtime
# APP: the application source and its install, identical in every named target
COPY setup.py ./
COPY MANIFEST.in ./
COPY atlas/README.md ./atlas/
COPY README.md ./
COPY src ./src
COPY profiles ./profiles
COPY docs ./docs
COPY tests ./tests
COPY scripts ./scripts
# OPERATIONAL-TOOLS: generated from OPERATIONAL_INPUTS
COPY ["tools/writing_verbs/gen_routes.py", "/opt/laplace/tools/writing_verbs/gen_routes.py"]
COPY ["tools/writing_verbs/reanchor_http_routes.py", "/opt/laplace/tools/writing_verbs/reanchor_http_routes.py"]
COPY ["tools/writing_verbs/http_routes.csv", "/opt/laplace/tools/writing_verbs/http_routes.csv"]
# END OPERATIONAL-TOOLS
COPY deploy/writing ./deploy/writing
COPY docs/writing-reviewer-guide.md ./REVIEWER_GUIDE.md
COPY docs/writing-pytest.ini ./pytest.ini
RUN python -m pip install --no-cache-dir --no-deps --no-build-isolation ./atlas ".[research]" \
    && rm -rf /opt/laplace/build /opt/laplace/atlas/build /opt/laplace/src/laplace_engine.egg-info /opt/laplace/src/atlas.egg-info \
    && python -m pip check
COPY deploy/writing/writing-entrypoint.sh /usr/local/bin/laplace-writing-entrypoint
COPY deploy/writing/smoke.py /opt/laplace/container-smoke.py
RUN chmod 0755 /usr/local/bin/laplace-writing-entrypoint \
    && mkdir -p /var/lib/laplace/session-workspaces \
    && chown laplace:laplace /var/lib/laplace/session-workspaces

USER laplace
WORKDIR /workspace

FROM provider-codex-deps AS provider-codex
# APP: the application source and its install, identical in every named target
COPY setup.py ./
COPY MANIFEST.in ./
COPY atlas/README.md ./atlas/
COPY README.md ./
COPY src ./src
COPY profiles ./profiles
COPY docs ./docs
COPY tests ./tests
COPY scripts ./scripts
# OPERATIONAL-TOOLS: generated from OPERATIONAL_INPUTS
COPY ["tools/writing_verbs/gen_routes.py", "/opt/laplace/tools/writing_verbs/gen_routes.py"]
COPY ["tools/writing_verbs/reanchor_http_routes.py", "/opt/laplace/tools/writing_verbs/reanchor_http_routes.py"]
COPY ["tools/writing_verbs/http_routes.csv", "/opt/laplace/tools/writing_verbs/http_routes.csv"]
# END OPERATIONAL-TOOLS
COPY deploy/writing ./deploy/writing
COPY docs/writing-reviewer-guide.md ./REVIEWER_GUIDE.md
COPY docs/writing-pytest.ini ./pytest.ini
RUN python -m pip install --no-cache-dir --no-deps --no-build-isolation ./atlas ".[research]" \
    && rm -rf /opt/laplace/build /opt/laplace/atlas/build /opt/laplace/src/laplace_engine.egg-info /opt/laplace/src/atlas.egg-info \
    && python -m pip check
COPY deploy/writing/writing-entrypoint.sh /usr/local/bin/laplace-writing-entrypoint
COPY deploy/writing/smoke.py /opt/laplace/container-smoke.py
RUN chmod 0755 /usr/local/bin/laplace-writing-entrypoint \
    && mkdir -p /var/lib/laplace/session-workspaces \
    && chown laplace:laplace /var/lib/laplace/session-workspaces

USER laplace
WORKDIR /workspace
LABEL org.laplace.capability.provider="codex-explicit-login-required"

FROM provider-claude-deps AS provider-claude
# APP: the application source and its install, identical in every named target
COPY setup.py ./
COPY MANIFEST.in ./
COPY atlas/README.md ./atlas/
COPY README.md ./
COPY src ./src
COPY profiles ./profiles
COPY docs ./docs
COPY tests ./tests
COPY scripts ./scripts
# OPERATIONAL-TOOLS: generated from OPERATIONAL_INPUTS
COPY ["tools/writing_verbs/gen_routes.py", "/opt/laplace/tools/writing_verbs/gen_routes.py"]
COPY ["tools/writing_verbs/reanchor_http_routes.py", "/opt/laplace/tools/writing_verbs/reanchor_http_routes.py"]
COPY ["tools/writing_verbs/http_routes.csv", "/opt/laplace/tools/writing_verbs/http_routes.csv"]
# END OPERATIONAL-TOOLS
COPY deploy/writing ./deploy/writing
COPY docs/writing-reviewer-guide.md ./REVIEWER_GUIDE.md
COPY docs/writing-pytest.ini ./pytest.ini
RUN python -m pip install --no-cache-dir --no-deps --no-build-isolation ./atlas ".[research]" \
    && rm -rf /opt/laplace/build /opt/laplace/atlas/build /opt/laplace/src/laplace_engine.egg-info /opt/laplace/src/atlas.egg-info \
    && python -m pip check
COPY deploy/writing/writing-entrypoint.sh /usr/local/bin/laplace-writing-entrypoint
COPY deploy/writing/smoke.py /opt/laplace/container-smoke.py
RUN chmod 0755 /usr/local/bin/laplace-writing-entrypoint \
    && mkdir -p /var/lib/laplace/session-workspaces \
    && chown laplace:laplace /var/lib/laplace/session-workspaces

USER laplace
WORKDIR /workspace
LABEL org.laplace.capability.provider="claude-explicit-login-required"

FROM provider-both-deps AS provider-both
# APP: the application source and its install, identical in every named target
COPY setup.py ./
COPY MANIFEST.in ./
COPY atlas/README.md ./atlas/
COPY README.md ./
COPY src ./src
COPY profiles ./profiles
COPY docs ./docs
COPY tests ./tests
COPY scripts ./scripts
# OPERATIONAL-TOOLS: generated from OPERATIONAL_INPUTS
COPY ["tools/writing_verbs/gen_routes.py", "/opt/laplace/tools/writing_verbs/gen_routes.py"]
COPY ["tools/writing_verbs/reanchor_http_routes.py", "/opt/laplace/tools/writing_verbs/reanchor_http_routes.py"]
COPY ["tools/writing_verbs/http_routes.csv", "/opt/laplace/tools/writing_verbs/http_routes.csv"]
# END OPERATIONAL-TOOLS
COPY deploy/writing ./deploy/writing
COPY docs/writing-reviewer-guide.md ./REVIEWER_GUIDE.md
COPY docs/writing-pytest.ini ./pytest.ini
RUN python -m pip install --no-cache-dir --no-deps --no-build-isolation ./atlas ".[research]" \
    && rm -rf /opt/laplace/build /opt/laplace/atlas/build /opt/laplace/src/laplace_engine.egg-info /opt/laplace/src/atlas.egg-info \
    && python -m pip check
COPY deploy/writing/writing-entrypoint.sh /usr/local/bin/laplace-writing-entrypoint
COPY deploy/writing/smoke.py /opt/laplace/container-smoke.py
RUN chmod 0755 /usr/local/bin/laplace-writing-entrypoint \
    && mkdir -p /var/lib/laplace/session-workspaces \
    && chown laplace:laplace /var/lib/laplace/session-workspaces

USER laplace
WORKDIR /workspace
LABEL org.laplace.capability.provider="codex-and-claude-explicit-logins-required"
