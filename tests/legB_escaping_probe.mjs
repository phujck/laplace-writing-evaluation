// legB F1/F2 headless probe — drives the REAL shipped review-surface JS.
//
// Not a reimplementation: it extracts `esc` and `wireOverrule` verbatim from the
// served review_surface.html and exercises them, so the assertions bind to the
// exact bytes the server hands the browser. Node-only (no DOM, no browser): the
// two helpers are pure over their inputs by construction.
//
//   node legB_escaping_probe.mjs <path-to-served-review_surface.html>
//
// Prints "LEGB-PROBE OK" and exits 0 when every assertion holds; throws (nonzero
// exit) on the first failure.
import { readFileSync } from "node:fs";

const path = process.argv[2];
if (!path) { throw new Error("usage: node legB_escaping_probe.mjs <html>"); }
const html = readFileSync(path, "utf8");

function assert(cond, msg) { if (!cond) throw new Error("ASSERT FAILED: " + msg); }

// ── extract `const esc = <arrow>;` — anchor on the )) ; terminator so the match
// does not stop at a ; inside a string literal like "&amp;" ────────────────────
const escMatch = html.match(/const esc = ([\s\S]*?\));/);
assert(escMatch, "could not locate the esc helper in the served HTML");
const esc = eval("(" + escMatch[1] + ")");

// ── extract `function wireOverrule(...) { ... }` by string-aware brace matching ──
function extractFunction(src, name) {
  const start = src.indexOf("function " + name);
  assert(start >= 0, "could not locate function " + name);
  let i = src.indexOf("{", start);
  assert(i >= 0, "no body for function " + name);
  let depth = 0, q = null;
  for (; i < src.length; i++) {
    const c = src[i], p = src[i - 1];
    if (q) { if (c === q && p !== "\\") q = null; continue; }
    if (c === '"' || c === "'" || c === "`") { q = c; continue; }
    if (c === "{") depth++;
    else if (c === "}") { depth--; if (depth === 0) { i++; break; } }
  }
  return src.slice(start, i);
}
const wireOverrule = eval("(" + extractFunction(html, "wireOverrule") + ")");

// ── F1: the judge's exact vector renders INERT ──────────────────────────────
// a crafted node id that closes the (double-quoted-in-source, single-quoted-in-DOM)
// attribute and appends a hover handler.
const payload = "def:x' onmouseover='alert(document.domain)";
const out = esc(payload);
assert(out.includes("&#39;"), "esc did not escape the single quote to &#39;");
assert(!/'/.test(out), "a raw single quote survived esc(): " + out);
assert(!/onmouseover\s*=/.test(out) || out.indexOf("onmouseover") > out.indexOf("&#39;"),
  "the handler is not neutralised behind the escape");
// build the ACTUAL rendered chip the way dismissalAudit() does and confirm the
// span carries exactly one attribute value and no injected handler attribute.
const chip = "<span class='danode' data-node='" + out + "'>" + esc(payload) + "</span>";
assert(!/data-node='[^']*'\s+onmouseover/.test(chip),
  "the crafted node id broke out into a live onmouseover attribute: " + chip);
// the '<' and '>' of nothing here, but the ' must be gone entirely from the value
assert((chip.match(/'/g) || []).length === 4,
  "the rendered chip has stray single quotes (attribute breakout): " + chip);

// a benign node id round-trips unharmed (no over-escaping of normal ids)
assert(esc("def:hamiltonian") === "def:hamiltonian", "esc mangled a benign node id");

// ── F2: the overrule guard — singleton one-click, multi two-step arm→confirm ──
function fakeBtn() {
  const s = new Set();
  return {
    classList: { add: c => s.add(c), remove: c => s.delete(c), contains: c => s.has(c) },
    textContent: "overrule", onclick: null,
  };
}
// a controllable timer: never auto-fires unless we call it, so arming is deterministic
let pending = null;
const fakeSetTimeout = (fn) => { pending = fn; return 1; };
const fakeClearTimeout = () => { pending = null; };
const opts = { setTimeout: fakeSetTimeout, clearTimeout: fakeClearTimeout };

// singleton class (nSupp = 1): revokes on the FIRST click, no arming
let confirmed = 0;
const b1 = fakeBtn();
wireOverrule(b1, 1, () => confirmed++, opts);
b1.onclick();
assert(confirmed === 1, "singleton class did not revoke on the first click");
assert(!b1.classList.contains("armed"), "singleton class should never arm");

// multi class (nSupp = 3): first click ARMS (no revoke), second click CONFIRMS
confirmed = 0;
const b3 = fakeBtn();
wireOverrule(b3, 3, () => confirmed++, opts);
b3.onclick();                                   // arm
assert(confirmed === 0, "multi class revoked on the FIRST click — the guard is absent");
assert(b3.classList.contains("armed"), "multi class did not arm on the first click");
assert(b3.textContent.includes("3"), "the armed label does not show the class size: " + b3.textContent);
b3.onclick();                                   // confirm
assert(confirmed === 1, "the confirming second click did not revoke");
assert(!b3.classList.contains("armed"), "the button stayed armed after confirming");

// multi class auto-disarm: arm, fire the timer → disarmed, a later click re-arms (not confirm)
confirmed = 0;
const b3b = fakeBtn();
wireOverrule(b3b, 3, () => confirmed++, opts);
b3b.onclick();                                  // arm
assert(pending, "no auto-disarm timer was scheduled");
pending();                                      // the timeout fires
assert(!b3b.classList.contains("armed"), "auto-disarm did not clear the armed state");
b3b.onclick();                                  // must ARM again, not confirm
assert(confirmed === 0, "a click after auto-disarm confirmed instead of re-arming");
assert(b3b.classList.contains("armed"), "the click after auto-disarm did not re-arm");

console.log("LEGB-PROBE OK");
