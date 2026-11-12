# syntax=docker/dockerfile:1.7
FROM node:22-bookworm-slim@sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee AS node
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS dependencies
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    biber bibtex2html ca-certificates cm-super-minimal ghostscript git graphviz \
    latexmk lmodern librsvg2-bin poppler-utils qpdf ripgrep tini \
    tex-gyre texlive-fonts-recommended texlive-latex-base texlive-latex-extra \
    texlive-latex-recommended texlive-pictures texlive-plain-generic \
    texlive-publishers texlive-science \
    && rm -rf /var/lib/apt/lists/*
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
ARG CODEX_NPM_SPEC=@openai/codex@0.160.1
ARG CLAUDE_NPM_SPEC=@anthropic-ai/claude-code@2.1.304
RUN npm install --global --omit=dev "$CODEX_NPM_SPEC" "$CLAUDE_NPM_SPEC" \
    && npm cache clean --force
WORKDIR /tmp/declarations
COPY pyproject.toml ./
COPY atlas/pyproject.toml ./atlas/
# The default image is the CPU application profile. Avoid downloading CUDA
# libraries for Torch's record/grammar operations; GPU qualification is explicit.
RUN python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu 'torch>=2.11,<3'
RUN python - <<'PY'
import subprocess, sys, tomllib
from pathlib import Path
requirements = []
for path, extras in [('pyproject.toml', ['evaluation', 'embed']), ('atlas/pyproject.toml', ['records'])]:
    data = tomllib.loads(Path(path).read_text())
    requirements.extend(data['build-system']['requires'])
    requirements.extend(data['project'].get('dependencies', []))
    for extra in extras:
        requirements.extend(data['project']['optional-dependencies'][extra])
requirements.append('playwright==1.65.0')  # same published Python/Node browser driver
subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-cache-dir', *dict.fromkeys(requirements)], check=True)
PY
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 bubblewrap \
    && rm -rf /var/lib/apt/lists/*
RUN python - <<'PY'
import importlib.metadata, subprocess
version = importlib.metadata.version('playwright')
subprocess.run(['npm', 'install', '--prefix', '/opt/evaluation/browser', '--omit=dev',
                'playwright@' + version], check=True)
PY
RUN python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /root/.cache /tmp/declarations

FROM dependencies AS evaluation
ARG SOURCE_REVISION=unknown
ARG RELEASE_VERSION=2026-11-12
LABEL org.opencontainers.image.title="Eigen writing and research evaluation" \
    org.opencontainers.image.source="https://github.com/phujck/laplace-writing-evaluation" \
    org.opencontainers.image.revision="$SOURCE_REVISION" \
    org.opencontainers.image.version="$RELEASE_VERSION" \
    org.opencontainers.image.description="Self-contained application, manuscripts, assets and genuine workflow records."
WORKDIR /opt/evaluation/seed
COPY . .
RUN python scripts/check_evaluation_selection.py \
    && python -m pip install --no-cache-dir --no-deps --no-build-isolation ./atlas '.[evaluation,embed]' \
    && python -m pip check \
    && rm -rf build atlas/build src/*.egg-info \
    && python scripts/check_evaluation_selection.py \
    && python -m pip freeze > /opt/evaluation/python-packages.txt \
    && printf '%s\n' "$SOURCE_REVISION" > /opt/evaluation/source-revision \
    && for input in revtex4-2.cls apsrev4-2.bst lmodern.sty physics.sty orcidlink.sty; do kpsewhich "$input" >/dev/null; done
RUN groupadd --gid 1000 laplace && useradd --uid 1000 --gid 1000 --create-home laplace \
    && mkdir -p /data && chown laplace:laplace /data \
    && chmod -R a+rX /opt/evaluation /opt/playwright
COPY deploy/evaluation/entrypoint.py /usr/local/bin/evaluation-entrypoint.py
ENV HOME=/data/accounts XDG_CONFIG_HOME=/data/accounts/.config \
    XDG_CACHE_HOME=/data/accounts/.cache XDG_STATE_HOME=/data/accounts/.local/state \
    LAPLACE_REPO_ROOT=/data/workspace LAPLACE_STATE=/data/workspace/.laplace-state \
    LAPLACE_SESSION_WORKSPACES=/data/session-workspaces
USER 1000:1000
WORKDIR /tmp
EXPOSE 8771
VOLUME ["/data"]
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=6 \
    CMD ["python", "-c", "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8771/authoring/health',timeout=4)); assert d['runtime']=='writing'"]
ENTRYPOINT ["/usr/bin/tini", "--", "python", "/usr/local/bin/evaluation-entrypoint.py"]
