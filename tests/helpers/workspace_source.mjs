// The workspace shell's source as one text, for tests that read or slice it (M5 S2 F1/F2): workspace.mjs is
// the mount and export facade, and its domain controllers are the modules named here (created in S2). Order:
// the facade, then the controllers by file name. Slices are each module's own verbatim text.
import {readFileSync} from 'node:fs';
const dir = new URL('../../src/laplace/web/static_shared/', import.meta.url);
export const SHELL_MODULES = Object.freeze(['workspace-activity.mjs','workspace-argument.mjs','workspace-chrome.mjs','workspace-context.mjs','workspace-conversation.mjs','workspace-dom.mjs','workspace-figures.mjs','workspace-help-door.mjs','workspace-home.mjs','workspace-inspection.mjs','workspace-manuscript-outline.mjs','workspace-manuscript.mjs','workspace-notices.mjs','workspace-proposals.mjs','workspace-reader-plan-view.mjs','workspace-research.mjs','workspace-returns.mjs','workspace-walk-handlers.mjs','workspace-work-view.mjs']);
export const WORKSPACE_FILES = Object.freeze(['workspace.mjs', ...SHELL_MODULES]);
export const workspaceSource = () => WORKSPACE_FILES.map(name => readFileSync(new URL(name, dir), 'utf8')).join('\n');
export const shellModuleSource = name => readFileSync(new URL(name, dir), 'utf8');
