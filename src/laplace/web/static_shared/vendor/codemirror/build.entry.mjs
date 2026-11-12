// The Laplace CodeMirror 6 bundle — a single offline ESM file, no CDN.
// Vendored for the integrated viewer (W4). 4.2 consumes it via a dynamic
// import from /shared/vendor/codemirror/codemirror.bundle.mjs. NOTHING else
// pulls @codemirror/* — this file IS the surface.
//
// Exports a curated, stable API so the viewer never reaches into the internal
// package graph: the editor primitives, the TeX (stex) language mode, and a
// dark theme keyed to the shell palette (hymn.css).

import { EditorState, Compartment } from "@codemirror/state";
import {
  EditorView, keymap, lineNumbers, highlightActiveLine,
  highlightActiveLineGutter, drawSelection, rectangularSelection,
  crosshairCursor, dropCursor, highlightSpecialChars,
} from "@codemirror/view";
import {
  syntaxHighlighting, defaultHighlightStyle, StreamLanguage,
  bracketMatching, foldGutter, indentOnInput, HighlightStyle,
} from "@codemirror/language";
import {
  defaultKeymap, history, historyKeymap, indentWithTab,
} from "@codemirror/commands";
import { stex } from "@codemirror/legacy-modes/mode/stex";
import { oneDark } from "@codemirror/theme-one-dark";
import { tags as t } from "@lezer/highlight";

// The TeX language, wrapped from the legacy stream mode.
const stexLanguage = StreamLanguage.define(stex);

// A dark theme keyed to the shell palette (static_shared/hymn.css :root):
//   --bg:#0e1116 --panel:#141a23 --edge:#222a36 --ink:#d7dee8 --dim:#6b7689
//   --accent:#7aa2f7 --teal:#5ee6b0 --warn:#e0af68 --bad:#f7768e --keystone:#bb9af7
const shellDarkTheme = EditorView.theme(
  {
    "&": { color: "#d7dee8", backgroundColor: "#0e1116" },
    ".cm-content": {
      caretColor: "#7aa2f7",
      fontFamily: "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace",
      fontSize: "12.5px",
    },
    ".cm-cursor, .cm-dropCursor": { borderLeftColor: "#7aa2f7" },
    "&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection":
      { backgroundColor: "#283449" },
    ".cm-panels": { backgroundColor: "#141a23", color: "#d7dee8" },
    ".cm-activeLine": { backgroundColor: "#141a2340" },
    ".cm-gutters": {
      backgroundColor: "#0e1116",
      color: "#6b7689",
      border: "none",
      borderRight: "1px solid #222a36",
    },
    ".cm-activeLineGutter": { backgroundColor: "#141a23", color: "#9aa5b4" },
    ".cm-foldPlaceholder": {
      backgroundColor: "transparent",
      border: "none",
      color: "#9aa5b4",
    },
    ".cm-matchingBracket, &.cm-focused .cm-matchingBracket": {
      backgroundColor: "#283449",
      outline: "1px solid #5ee6b0",
    },
  },
  { dark: true },
);

// Syntax colours for the stex tokens, on the shell palette.
const shellDarkHighlight = HighlightStyle.define(
  [
    { tag: t.keyword, color: "#bb9af7" }, // \commands
    { tag: [t.name, t.deleted, t.character, t.macroName], color: "#7aa2f7" },
    { tag: [t.tagName, t.labelName], color: "#7aa2f7" },
    { tag: [t.literal, t.string, t.inserted], color: "#5ee6b0" }, // math / braces content
    { tag: [t.number, t.bool, t.atom], color: "#e0af68" },
    { tag: [t.comment], color: "#6b7689", fontStyle: "italic" },
    { tag: [t.bracket, t.brace], color: "#9aa5b4" },
    { tag: [t.typeName, t.className], color: "#5ee6b0" },
    { tag: [t.operator, t.operatorKeyword], color: "#e0af68" },
    { tag: [t.invalid], color: "#f7768e" },
  ],
  { themeType: "dark" },
);

const shellDark = [shellDarkTheme, syntaxHighlighting(shellDarkHighlight)];

// A sensible batteries-included setup (the CM6 basicSetup, minus the search
// panel which the viewer supplies itself). Kept small and explicit so 4.2 can
// see exactly what the editor carries.
const baseSetup = [
  lineNumbers(),
  highlightActiveLineGutter(),
  highlightSpecialChars(),
  history(),
  foldGutter(),
  drawSelection(),
  dropCursor(),
  indentOnInput(),
  syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
  bracketMatching(),
  rectangularSelection(),
  crosshairCursor(),
  highlightActiveLine(),
  keymap.of([...defaultKeymap, ...historyKeymap, indentWithTab]),
];

export {
  EditorState, EditorView, Compartment,
  keymap, lineNumbers,
  StreamLanguage, stex, stexLanguage,
  oneDark, shellDark, shellDarkTheme, shellDarkHighlight,
  baseSetup,
};
