"""The workspace shell's source as one text for tests that read it (M5 S2 F1/F2): workspace.mjs is the mount
facade and its domain controllers are the modules named here (same list as tests/helpers/workspace_source.mjs)."""
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / 'src' / 'laplace' / 'web' / 'static_shared'
SHELL_MODULES = ['workspace-activity.mjs','workspace-argument.mjs','workspace-chrome.mjs','workspace-context.mjs','workspace-conversation.mjs','workspace-dom.mjs','workspace-figures.mjs','workspace-help-door.mjs','workspace-home.mjs','workspace-inspection.mjs','workspace-manuscript-outline.mjs','workspace-manuscript.mjs','workspace-notices.mjs','workspace-proposals.mjs','workspace-reader-plan-view.mjs','workspace-research.mjs','workspace-returns.mjs','workspace-walk-handlers.mjs','workspace-work-view.mjs']
WORKSPACE_FILES = ['workspace.mjs', *SHELL_MODULES]


def workspace_source() -> str:
    return '\n'.join((STATIC / name).read_text(encoding='utf-8') for name in WORKSPACE_FILES)
