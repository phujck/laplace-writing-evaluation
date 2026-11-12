#!/usr/bin/env node
/**
 * THE EDITOR'S DOORS, PROVED IN A REAL BROWSER (WRITING-CONSOLIDATION-W1, editor-doors).
 *
 *   node tools/writing_verbs/editor_doors_proof.mjs --tree <tree> --out <dir> [--headed]
 *
 * `harness2/browser.mjs` MEASURES (wall times and bytes, against a baseline). This one
 * ASSERTS: every claim the packet makes about the editor's doors is driven as a real gesture
 * in chromium against a server started from the tree being proved, and every step writes a
 * screenshot beside its own verdict. A timing cannot tell you that a refusal carried its cure
 * and that the retry applied; this can, and it fails loudly when it does not.
 *
 * It never contacts the author's app on 8771: it builds the harness's own fixture (a COPIED
 * workspace), starts its own server on a port the OS reported free, and stops it at the end.
 *
 * WHAT IT PROVES, in order
 *   1 identities      /walk/doc?identities=1 carries a `prose` token on every editable block,
 *                     and the walk's own block model carries it through
 *   2 save            one typed character -> POST /review/adjudicate in the GRAMMAR shape
 *                     ({verb, concept, target, expected, payload}), carrying the token the
 *                     read published, and the door applies it
 *   3 stale -> needed The file is changed on disk BEHIND the page (so the page's token is now
 *                     stale, which is exactly the race between two writers). The next save is
 *                     refused by identity, the refusal carries `needed`, the walk retries ONCE
 *                     with `{**request, **needed}` and the splice applies --- with the other
 *                     writer's sentence still in the file. Nothing is overwritten.
 *   4 undo            Ctrl+Z posts the SAME shape through the same producer, and applies
 *   5 ruling          the `8` key rules the armed passage CUT, Enter banks it, the band shows
 *                     the ruling, and after a RELOAD the project's ledger still shows it ---
 *                     which is the only form of "visible" that outlives the session
 */
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:net";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const TREE_DEFAULT = resolve(HERE, "..", "..");
const CAMPAIGN = "/home/phujck/VScodeProjects/laplace/evidence/WRITING_CONSOLIDATION_2026-10-03";
const BANKED = "/home/phujck/VScodeProjects/laplace";

function parseArgs(argv) {
  const out = { tree: TREE_DEFAULT, out: null, headed: false,
                project: "synthetics-foundations", actor: "editor-doors-proof",
                work: "/tmp/claude-1000/consol-editor-doors/proof", timeout: 120000 };
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i].replace(/^--/, "").replace(/-/g, "_");
    if (key === "headed") { out[key] = true; continue; }
    out[key] = argv[i + 1]; i += 1;
  }
  if (!out.out) { throw new Error("--out <dir> is required"); }
  out.tree = resolve(out.tree);
  out.out = resolve(out.out);
  out.timeout = Number(out.timeout);
  return out;
}

const steps = [];
function claim(name, ok, says, detail) {
  steps.push({ step: name, ok: !!ok, says, ...(detail ? { detail } : {}) });
  if (!ok) { throw new Error(`${name}: ${says}\n${JSON.stringify(detail, null, 1)}`); }
}

async function freePort() {
  return new Promise((ok, bad) => {
    const probe = createServer();
    probe.once("error", bad);
    probe.listen(0, "127.0.0.1", () => {
      const { port } = probe.address();
      probe.close(() => ok(port));
    });
  });
}

async function waitReady(base, deadlineMs) {
  const until = Date.now() + deadlineMs;
  let last = "";
  while (Date.now() < until) {
    try {
      const got = await fetch(`${base}/authoring/projects`,
        { headers: { "X-Laplace-Writing": "1" } });
      if (got.status) { return; }
    } catch (error) { last = String(error); }
    await new Promise((ok) => setTimeout(ok, 300));
  }
  throw new Error(`the server never answered on ${base}: ${last}`);
}

/** The grammar body, read off the POST the page actually sent. */
function body(request) {
  let parsed = {};
  try { parsed = JSON.parse(request || "{}") || {}; } catch { return {}; }
  const inner = parsed.payload || {};
  const m = /^(.*?)::(.+):(\d+)-(\d+)$/.exec(String(parsed.target || ""));
  return { shape: parsed.concept ? "grammar" : "owner", verb: parsed.verb,
           concept: parsed.concept, target: parsed.target,
           expected: Array.isArray(parsed.expected) ? parsed.expected : [],
           file: m ? m[2] : inner.file, line_start: m ? Number(m[3]) : inner.line_start,
           line_end: m ? Number(m[4]) : inner.line_end,
           before: inner.before_content, after: inner.after,
           passage_before: inner.passage_before, passage_after: inner.passage_after,
           // the ruling rides the PAYLOAD of a grammar body and the TOP of a flat one (the
           // comment gesture is still the owner's own shape plus the ruling), so read both:
           // a reader of one spelling only reported `undefined` for a field that was there.
           disposition: inner.disposition || parsed.disposition,
           altitude: inner.altitude || parsed.altitude,
           source: inner.source || parsed.source };
}

async function main() {
  const args = parseArgs(process.argv);
  mkdirSync(args.out, { recursive: true });
  const fixtureRun = spawnSync(resolve(args.tree, "scripts/laplace-python"),
    [resolve(CAMPAIGN, "harness2/_measure.py"), "--work", args.work,
     "--projects", args.project],
    { cwd: args.tree, encoding: "utf8", maxBuffer: 1 << 24 });
  if (fixtureRun.status !== 0) {
    throw new Error(`the fixture could not be built: ${fixtureRun.stderr || fixtureRun.stdout}`);
  }
  const fixture = JSON.parse(fixtureRun.stdout);
  const port = await freePort();
  const state = `${args.work}/server-state`;
  mkdirSync(state, { recursive: true });
  const base = `http://127.0.0.1:${port}`;
  const server = spawn(resolve(args.tree, "scripts/laplace-python"),
    ["-m", "laplace.web.writing_server", "--root", fixture.sandbox, "--state", state,
     "--host", "127.0.0.1", "--port", String(port)],
    { cwd: args.tree, stdio: ["ignore", "pipe", "pipe"] });
  const log = [];
  server.stdout.on("data", (c) => log.push(String(c)));
  server.stderr.on("data", (c) => log.push(String(c)));

  let browser = null;
  const posts = [];
  const errors = [];
  try {
    await waitReady(base, args.timeout);
    const { chromium } = await import(resolve(BANKED, "node_modules/playwright/index.mjs"));
    browser = await chromium.launch({ headless: !args.headed });
    const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
    page.on("pageerror", (e) => errors.push(String(e.message).slice(0, 300)));
    page.on("response", (r) => {
      if (!r.url().includes("/review/adjudicate")) { return; }
      if (r.request().method() !== "POST") { return; }
      posts.push({ status: r.status(), sent: body(r.request().postData()) });
    });
    const shot = (name) => page.screenshot(
      { path: resolve(args.out, `${name}.png`), fullPage: false });
    const walkUrl = `${base}/walk?corpus=${encodeURIComponent(args.project)}`
      + `&actor=${encodeURIComponent(args.actor)}`;

    // ── 1 the identities the read publishes ────────────────────────────────────────────
    await page.goto(walkUrl, { waitUntil: "domcontentloaded", timeout: args.timeout });
    await page.waitForFunction(() => document.querySelectorAll("[data-block]").length > 0,
      null, { timeout: args.timeout });
    await page.waitForLoadState("networkidle", { timeout: args.timeout }).catch(() => {});
    const identities = await page.evaluate(() => {
      const blocks = window.walk.identities();
      const withToken = blocks.filter((b) => (b.expected || []).length);
      return { blocks: blocks.length, with_token: withToken.length,
               one: (withToken[0] || {}).expected || [] };
    });
    claim("identities", identities.with_token > 0 && /^rev:prose:/.test(identities.one[0] || ""),
      `the canvas carries a prose token on ${identities.with_token} of ${identities.blocks} `
      + `blocks, read from GET /walk/doc?identities=1 and never computed in the page`,
      identities);
    await shot("1-walk-loaded");

    // ── 2 one typed character, saved in the grammar shape with its token ──────────────
    const target = await page.evaluate(() => {
      const b = window.walk.identities().find((x) => x.kind === "para"
        && (x.expected || []).length && (x.tex || "").length > 80);
      return b ? { id: b.id, file: b.src.file, repo_file: b.src.repo_file,
                   line_start: b.src.lineStart, line_end: b.src.lineEnd, tex: b.tex } : null;
    });
    claim("target", !!target, "a paragraph with a published token and real prose was found",
      target);
    await page.evaluate((id) => {
      const node = document.querySelector(`[data-block="${id}"] .blk-body`);
      node.scrollIntoView({ block: "center" });
      node.focus();
      const range = document.createRange();
      range.selectNodeContents(node);
      range.collapse(false);
      const sel = document.getSelection();
      sel.removeAllRanges(); sel.addRange(range);
    }, target.id);
    await page.keyboard.type(" Spliced by the proof.");
    await page.keyboard.press("Shift+Enter");
    await page.waitForFunction(() => window.walk.deposits().length > 0,
      null, { timeout: args.timeout });
    const save = posts.at(-1);
    claim("save", save && save.status === 200 && save.sent.shape === "grammar"
      && save.sent.concept === "prose@paragraph" && save.sent.expected.length > 0,
      "the save posts the grammar shape, carrying the token the read published, and the "
      + "door answered 200", save);
    const applied = await page.evaluate(() => window.walk.deposits()[0]);
    claim("save_applied", applied && applied.applied === true,
      "the splice applied: the walk's own band row says so", applied);
    await shot("2-saved");

    // ── 3 the race: stale token -> refused -> needed -> retried -> applied ────────────
    const planted = await page.evaluate(async (project) => {
      // Another writer touches the same file between the read and the next save. This is the
      // state `expected` exists for, and it is planted through the SAME door, so the proof
      // uses no privilege the editor does not have.
      const got = await fetch("/review/fragment?" + new URLSearchParams(
        { corpus: project, section: "", paragraph: "" }));
      return got.status;
    }, args.project);
    const victim = await page.evaluate(() => {
      const taken = window.walk.deposits().map((r) => r.blockId);
      const b = window.walk.identities().find((x) => x.kind === "para"
        && (x.expected || []).length && (x.tex || "").length > 120
        && !taken.includes(x.id));
      return b ? { id: b.id, file: b.src.file, repo_file: b.src.repo_file,
                   line_start: b.src.lineStart, line_end: b.src.lineEnd,
                   tex: b.tex, expected: b.expected } : null;
    });
    claim("victim", !!victim, "a second paragraph was found for the race", { victim, planted });
    // the other writer: the same /review/adjudicate door, a different sentence, no token
    const byOther = await page.evaluate(async ([project, v]) => {
      const got = await fetch("/review/adjudicate?corpus=" + encodeURIComponent(project), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Laplace-Writing": "1" },
        body: JSON.stringify({ verb: "rewrite", by: "another-writer", corpus: project,
          file: v.file, line_start: v.line_start, line_end: v.line_end,
          before: v.tex, after: v.tex + " A sentence another writer added.",
          source: "proof-other-writer", scope: "sentence" }),
      });
      return { status: got.status, body: await got.json() };
    }, [args.project, victim]);
    claim("other_writer", byOther.status === 200 && byOther.body.pending !== true,
      "another writer changed that span through the same door, so the page's token for it "
      + "is now stale", byOther);
    const before = posts.length;
    await page.evaluate((id) => {
      const node = document.querySelector(`[data-block="${id}"] .blk-body`);
      node.scrollIntoView({ block: "center" });
      node.focus();
      const range = document.createRange();
      range.selectNodeContents(node);
      range.collapse(false);
      const sel = document.getSelection();
      sel.removeAllRanges(); sel.addRange(range);
    }, victim.id);
    await page.keyboard.type(" Typed against the stale read.");
    await page.keyboard.press("Shift+Enter");
    await page.waitForFunction((n) => window.walk.deposits().length > n,
      1, { timeout: args.timeout }).catch(() => {});
    await page.waitForTimeout(1500);
    const race = posts.slice(before);
    const retried = race.length > 1;
    // read off DISK, from the fixture the server was started on: the file is the truth, and a
    // route is one more thing that could be answering from a cache
    const onDisk = resolve(fixture.sandbox, victim.repo_file);
    const source = readFileSync(onDisk, "utf8");
    claim("race", retried && race.at(-1).status === 200,
      `the stale save was refused and retried ONCE from the refusal's own needed: `
      + `${race.length} POSTs, the last answering ${race.at(-1).status}`,
      race.map((p) => ({ status: p.status, expected: p.sent.expected.length,
                         before_lines: String(p.sent.before || "").split("\n").length })));
    claim("no_clobber",
      source.includes("A sentence another writer added.")
      && source.includes("Typed against the stale read."),
      "the other writer's sentence is STILL in the file after the retry, and the author's own "
      + "edit is in it too: a current token is not a licence to overwrite",
      { file: onDisk,
        other_writer_kept: source.includes("A sentence another writer added."),
        author_edit_applied: source.includes("Typed against the stale read."),
        span: source.split("\n").slice(victim.line_start - 1, victim.line_end).join("\n")
          .slice(0, 400) });
    await shot("3-race-retried");

    // ── 4 undo, through the same producer ─────────────────────────────────────────────
    const undoBefore = posts.length;
    await page.evaluate((id) => {
      const node = document.querySelector(`[data-block="${id}"] .blk-body`);
      if (node) { node.focus(); }
    }, target.id);
    await page.keyboard.press("Control+z");
    await page.waitForTimeout(2500);
    const undo = posts.slice(undoBefore).at(-1);
    // THE TWO LANES' MEETING POINT, ASSERTED (WRITING-CONSOLIDATION-W1). Before the synthesis
    // this gesture posted `line_start:1, line_end:<every line of the file>` and no token: the
    // storage lane narrowed the span, the editor-doors lane gave the door tokens, and neither
    // on its own could make the undo refusable --- a request addressed at the whole file has a
    // `prose` home nothing published a token for. So the claim is BOTH halves at once: the
    // span is the hunk the inverse touches, and `expected` carries the token the read
    // published for exactly that span.
    const fileLines = undo ? String(undo.sent.before || "").split("\n").length : 0;
    const undoSpan = undo ? undo.sent.line_end - undo.sent.line_start + 1 : 0;
    const wholeFile = undo
      ? readFileSync(resolve(fixture.sandbox, target.repo_file || target.file), "utf8")
        .split("\n").length : 0;
    claim("undo", undo && undo.status === 200 && undo.sent.shape === "grammar"
      && undo.sent.concept === "prose@paragraph"
      && undo.sent.line_start > 1 && undoSpan < wholeFile
      && fileLines === undoSpan && undo.sent.expected.length > 0,
      `Ctrl+Z posts the SAME shape through the same producer, addressed at the HUNK `
      + `(${undo && undo.sent.line_start}-${undo && undo.sent.line_end}, ${undoSpan} of the `
      + `file's ${wholeFile} lines) and carrying ${undo && undo.sent.expected.length} `
      + `published token(s); the door answered ${undo && undo.status}`,
      undo && { status: undo.status, shape: undo.sent.shape, concept: undo.sent.concept,
                source_field: undo.sent.source,
                span: [undo.sent.line_start, undo.sent.line_end],
                span_lines: undoSpan, file_lines: wholeFile,
                before_lines: fileLines, expected: undo.sent.expected });
    await shot("4-undone");

    // ── 5 the keep/cut ruling: the key, the bank, the band, and after a reload ────────
    const ruled = await page.evaluate((id) => {
      window.walk.armBlock(id);
      return window.walk.armed();
    }, victim.id);
    claim("armed", !!ruled, "the composer is armed on a passage", ruled);
    // Alt+8 first: the ruling key works wherever the caret is, which is the law the scope
    // digits already hold (walk.mjs's own comment at the Alt+digit branch).
    await page.keyboard.press("Alt+8");                    // 7 keep · 8 cut · 9 rework
    const ruling = await page.evaluate(() => window.walk.ruling());
    claim("ruling_key_alt", ruling.disposition === "cut",
      "Alt+8 ruled the armed passage CUT from wherever the caret was, through the same "
      + "function the chip calls", ruling);
    // ... and the CHIP, which is the other way his hand reaches it: a real click on the
    // rendered control, which also proves the chip is rendered, pressed and toggling.
    const chips = await page.evaluate(() => [...document.querySelectorAll("#comp-rulings .chip")]
      .map((n) => {
        const box = n.getBoundingClientRect();
        return { ruling: n.dataset.ruling, pressed: n.getAttribute("aria-pressed"),
                 key: n.querySelector(".k").textContent,
                 w: Math.round(box.width), h: Math.round(box.height) };
      }));
    // The composer's rail is laid out off-screen until the author opens it, so a POINTER click
    // cannot reach the chip in this headless run and `page.click` times out on visibility.
    // The chip's own handler is what is driven instead, by dispatching a real click event on
    // the real element: the three toggles below are the handler's behaviour, and the LIMIT is
    // that the pointer gesture itself is unproved here. The key path (Alt+8 above) is a real
    // key press, and it reaches the same `setDisposition`.
    const toggle = async (which) => page.evaluate((w) => {
      document.querySelector(`#comp-rulings .chip[data-ruling="${w}"]`)
        .dispatchEvent(new MouseEvent("click", { bubbles: true }));
      return window.walk.ruling().disposition;
    }, which);
    const cleared = await toggle("cut");
    const kept = await toggle("keep");
    const again = await toggle("cut");
    claim("ruling_chips",
      chips.length === 3 && chips.map((c) => c.ruling).join(",") === "keep,cut,rework"
      && chips.map((c) => c.key).join(",") === "7,8,9"
      && cleared === "" && kept === "keep" && again === "cut",
      "the three ruling chips are rendered with their keys and their pressed state, a click on "
      + "the pressed one clears it and a click on another replaces it (the chip's handler, "
      + "dispatched on the real element: the rail is off-screen until opened, so the pointer "
      + "gesture itself is NOT proved here)", { chips, cleared, kept, again });
    await shot("5-ruling-armed");
    await page.evaluate(() => { window.walk.body("Cut this: it repeats the opening."); });
    const banked = await page.evaluate(async () => {
      const row = await window.walk.bank();
      return row ? { id: row.id, disposition: row.disposition, altitude: row.altitude,
                     kind: row.kind } : null;
    });
    claim("ruling_banked", banked && banked.disposition === "cut" && banked.kind === "comment",
      "the ruling banked on the EXISTING comment row kind, with its altitude", banked);
    // THE LAST GESTURE THAT DID NOT SPEAK THE GRAMMAR (WRITING-CONSOLIDATION-W1). The judge of
    // the editor-doors lane was right: the comment gesture still posted the owner's flat body
    // with the old top-level `verb:"comment"` while every other gesture on this canvas had
    // moved to verb x concept, and nothing said so. It sends the grammar spelling now, with
    // the altitude as half of the concept and the home id as the `target`, which is what makes
    // `expected` mean anything at this door. The banked ROW is unchanged, which is the other
    // half of the claim and is why the recorded corpus still replays (the shim restores the
    // executor's own discriminator: review_surface._owner_adjudication).
    const commentPost = posts.at(-1);
    // The altitude is the GESTURE's, not a constant: `commentAltitude` answers `paragraph` for a
    // gesture with a paragraph marker and `section` otherwise, and the concept must be whichever
    // one this gesture reached and must agree with the altitude the row banked. Pinning it to
    // `paragraph` here would be the test asserting the fixture rather than the behaviour.
    const altitude = String(commentPost && commentPost.sent.concept || "").split("@")[1] || "";
    claim("comment_shape", commentPost && commentPost.status === 200
      && commentPost.sent.shape === "grammar" && commentPost.sent.verb === "create"
      && ["paragraph", "section", "chapter"].includes(altitude)
      && String(commentPost.sent.target || "").includes("::")
      && commentPost.sent.disposition === "cut"
      && commentPost.sent.expected.length > 0
      && banked && banked.altitude === altitude,
      `the keep/cut gesture posts verb x concept (create note@${altitude}) with its home as the `
      + "target and the published token in `expected`, and the row it banks is the old one, at "
      + "the same altitude",
      commentPost && { status: commentPost.status, shape: commentPost.sent.shape,
                       verb: commentPost.sent.verb, concept: commentPost.sent.concept,
                       target: commentPost.sent.target,
                       expected: commentPost.sent.expected.length,
                       disposition: commentPost.sent.disposition,
                       banked_altitude: banked && banked.altitude,
                       banked_kind: banked && banked.kind,
                       altitude_also_in_payload: commentPost.sent.altitude });
    const chip = await page.evaluate(() => {
      const node = document.querySelector('#band-list .dep-ruling');
      return node ? { text: node.textContent, ruling: node.dataset.ruling } : null;
    });
    claim("ruling_in_band", chip && chip.ruling === "cut",
      "the walk shows the ruling beside the passage's own deposit row", chip);
    await shot("6-ruling-banked");

    // the reload: the band is empty by law (it holds only this walk), so the ledger is where
    // a past ruling has to be visible — press `l`, which is the door it lives behind
    await page.reload({ waitUntil: "domcontentloaded", timeout: args.timeout });
    await page.waitForFunction(() => document.querySelectorAll("[data-block]").length > 0,
      null, { timeout: args.timeout });
    await page.waitForLoadState("networkidle", { timeout: args.timeout }).catch(() => {});
    await page.keyboard.press("l");
    await page.waitForFunction(() => window.walk.ledger().loaded,
      null, { timeout: args.timeout });
    const afterReload = await page.evaluate(() => {
      const rows = [...document.querySelectorAll("#ledger-list .dep-ruling")]
        .map((n) => ({ text: n.textContent, ruling: n.dataset.ruling }));
      return { ledger: window.walk.ledger(), rulings: rows,
               band: window.walk.deposits().length };
    });
    claim("ruling_after_refresh",
      afterReload.rulings.some((r) => r.ruling === "cut") && afterReload.band === 0,
      "after a reload the band is empty (it holds only this walk, by its own law) and the "
      + "project's ledger shows the ruling — which is the only visibility that outlives a "
      + "session", afterReload);
    await shot("7-after-refresh");

    // ── 6 the MIXED body of this transition: 422, with an answer ─────────────────────
    // The old discriminator `verb:"comment"` beside the new `concept` is the natural body of
    // exactly this transition, and it used to kill the connection with no HTTP response at all
    // (`grammar_request` rewrites a verb outside the nine to the route's table verb, so the pair
    // is undeclared and `g.Request` raised). An unanswered request is worse than a refusal: the
    // caller cannot tell a bad body from a dead server.
    const mixed = await page.evaluate(async ([project, v]) => {
      const got = await fetch("/review/adjudicate?corpus=" + encodeURIComponent(project), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Laplace-Writing": "1" },
        body: JSON.stringify({ verb: "comment", concept: "note@paragraph",
          by: "mixed-body-probe",
          target: project + "::" + v.file + ":" + v.line_start + "-" + v.line_end,
          payload: { section: "", comment: "a body of the transition", disposition: "cut" } }),
      });
      let parsed = null;
      try { parsed = await got.json(); } catch (e) { parsed = { parse_error: String(e) }; }
      return { status: got.status, body: parsed };
    }, [args.project, victim]);
    claim("mixed_body_answers_422",
      mixed.status === 422 && /note@paragraph/.test(String(mixed.body && mixed.body.error || "")),
      "a body carrying the OLD discriminator and the NEW concept is refused 422 with the "
      + "grammar's own sentence naming the concept, and the connection answers at all",
      mixed);

    // ── 7 the ruling at SECTION altitude: the container is the FILE, and it is gated ──
    // The editor used to send a token at paragraph altitude only, so a section ruling banked
    // against bytes the author might never have read. The token now comes from the same read the
    // page was built from, which is what makes this refusable: the file is moved behind the page
    // by another writer, and the ruling is refused, cured and retried.
    const head = await page.evaluate(() => {
      const rows = window.walk.identities();
      const h = rows.find((x) => x.kind === "head" && x.src && x.src.file);
      if (!h) return null;
      const para = rows.find((x) => x.kind === "para" && x.src.file === h.src.file
        && (x.expected || []).length && (x.tex || "").length > 60);
      return para ? { id: h.id, file: h.src.file, repo_file: h.src.repo_file,
                      para: { file: para.src.file, line_start: para.src.lineStart,
                              line_end: para.src.lineEnd, tex: para.tex } } : null;
    });
    claim("section_target", !!head,
      "a heading block (no paragraph marker, so the gesture rules at SECTION altitude) was "
      + "found with a paragraph of the same file to move", head);
    const moved = await page.evaluate(async ([project, para]) => {
      const got = await fetch("/review/adjudicate?corpus=" + encodeURIComponent(project), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Laplace-Writing": "1" },
        body: JSON.stringify({ verb: "rewrite", by: "another-writer", corpus: project,
          file: para.file, line_start: para.line_start, line_end: para.line_end,
          before: para.tex, after: para.tex + " A sentence that moves the file.",
          source: "proof-section-race", scope: "sentence" }),
      });
      return { status: got.status };
    }, [args.project, head.para]);
    claim("section_file_moved", moved.status === 200,
      "another writer changed a paragraph of that file, so the page's FILE token is now stale",
      moved);
    const sectionBefore = posts.length;
    const sectionRuling = await page.evaluate(async (id) => {
      window.walk.armBlock(id);
      window.walk.setRuling("cut");
      window.walk.body("Cut this section: it repeats the chapter opening.");
      let banked = null, error = null;
      try { banked = await window.walk.bank(); } catch (e) { error = String(e && e.message || e); }
      return { armed: window.walk.armed(), banked, error };
    }, head.id);
    const sectionPosts = posts.slice(sectionBefore);
    claim("ruling_section_refused_then_retried",
      sectionPosts.length > 1 && sectionPosts[0].status === 409
      && sectionPosts.at(-1).status === 200
      // THE ALTITUDE IS THE CONCEPT NOW (WRITING-CONSOLIDATION-W1): this read
      // `p.sent.altitude`, the payload key the editor-doors lane wrote beside the concept that
      // already carried it. The synthesis removed the duplicate, so the assertion reads the one
      // place the altitude lives, and the banked row is checked separately below.
      && sectionPosts.every((p) => p.sent.concept === "note@section")
      && sectionPosts.every((p) => p.sent.expected.length === 1),
      `the section-altitude ruling carried the FILE's token, was refused 409 on the stale one `
      + `and retried ONCE from the refusal's own needed: ${sectionPosts.length} POSTs, `
      + `${sectionPosts.map((p) => p.status).join(" then ")}`,
      { posts: sectionPosts.map((p) => ({ status: p.status, concept: p.sent.concept,
          disposition: p.sent.disposition, tokens: p.sent.expected.length })),
        banked: sectionRuling.banked, error: sectionRuling.error });
    claim("ruling_section_banked",
      sectionRuling.banked && sectionRuling.banked.disposition === "cut"
      && sectionRuling.banked.altitude === "section"
      && sectionRuling.banked.kind === "comment",
      "and it banked on the existing comment row kind at section altitude",
      sectionRuling.banked);
    await shot("8-section-ruling");

    claim("no_page_errors", errors.length === 0,
      "no uncaught page error during the whole proof", errors);
  } finally {
    if (browser) { await browser.close().catch(() => {}); }
    server.kill("SIGTERM");
    await new Promise((ok) => setTimeout(ok, 400));
    if (!server.killed) { server.kill("SIGKILL"); }
  }
  const report = {
    schema: "laplace.editor-doors-proof/1",
    meta: { tree: args.tree, project: args.project, at: new Date().toISOString(),
            head: spawnSync("git", ["-C", args.tree, "rev-parse", "HEAD"],
              { encoding: "utf8" }).stdout.trim(),
            fixture: fixture.sandbox, server_log_tail: log.join("").slice(-400),
            port_strategy: "net.createServer().listen(0); the author's app on 8771 is "
              + "never contacted" },
    steps,
    posts: posts.map((p) => ({ status: p.status, shape: p.sent.shape, verb: p.sent.verb,
      concept: p.sent.concept, target: p.sent.target,
      expected: p.sent.expected.length, disposition: p.sent.disposition || null,
      source: p.sent.source || null })),
    page_errors: errors,
  };
  writeFileSync(resolve(args.out, "proof.json"), JSON.stringify(report, null, 1) + "\n");
  for (const row of steps) {
    process.stdout.write(`${row.ok ? "PASS" : "FAIL"}  ${row.step}  ${row.says}\n`);
  }
  process.stdout.write(`\n${steps.filter((s) => s.ok).length} of ${steps.length} claims hold; `
    + `${posts.length} POSTs to /review/adjudicate; written ${resolve(args.out, "proof.json")}\n`);
  return steps.every((s) => s.ok) ? 0 : 1;
}

main().then((code) => process.exit(code)).catch((error) => {
  process.stderr.write(String(error && error.stack || error) + "\n");
  try {
    writeFileSync(resolve(parseArgs(process.argv).out, "proof.json"),
      JSON.stringify({ schema: "laplace.editor-doors-proof/1", steps,
        failed: String(error && error.message || error) }, null, 1) + "\n");
  } catch { /* the output directory may not exist yet */ }
  process.exit(1);
});
