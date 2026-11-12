CodeMirror 6 — a single offline ESM bundle (MIT), no CDN.

Built with esbuild 0.28.1 (`--bundle --format=esm --minify`) from a curated
entry module. The offline law: NOTHING in the viewer surface may fetch a CDN;
this file is served from `/shared/vendor/codemirror/codemirror.bundle.mjs` via
shared_ui.py (the KaTeX/pdf.js precedent). W4.1 vendors it; W4.2 consumes it.

Bundled packages (all MIT, Marijn Haverbeke and others):
  codemirror@6.0.2
  @codemirror/state@6.7.1
  @codemirror/view@6.43.6
  @codemirror/language@6.12.4
  @codemirror/commands@6.10.4
  @codemirror/legacy-modes@6.5.3   (mode/stex — the TeX stream mode)
  @codemirror/theme-one-dark@6.1.3
  @lezer/highlight, @lezer/common  (transitive)

Exports (the stable viewer API — 4.2 imports only these):
  EditorState, EditorView, Compartment, keymap, lineNumbers
  StreamLanguage, stex, stexLanguage   (TeX language)
  baseSetup                            (batteries-included extension list)
  shellDark, shellDarkTheme, shellDarkHighlight  (dark theme keyed to hymn.css)
  oneDark                              (upstream dark theme, fallback)

Rebuild: see the entry module + build recipe recorded alongside this stage's
work. `node_modules` is NEVER committed — only this prebuilt bundle + LICENSE.
