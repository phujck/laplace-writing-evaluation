// A small markup-parsing DOM double for source render coverage (repair2 R4, 2026-10-14). It parses the
// well-formed markup templates the shell and the conversation pane assign through innerHTML, keeps
// attributes, dataset, classList, hidden and the parent chain coherent, and answers the selector forms
// those modules use (tag, #id, .class, [attr], [attr=value], compounds, descendant and child combinators,
// comma lists, :not(), :scope). It is a test double, not a browser: no layout, no CSS cascade, no events
// beyond direct dispatch to registered listeners.
const VOID = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr']);
const ENTITIES = {amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', times: '×', middot: '·', hellip: '…', rarr: '→', larr: '←'};
const decode = text => text.replace(/&(#x[0-9a-f]+|#\d+|\w+);/gi, (m, e) => e[0] === '#' ? String.fromCodePoint(e[1].toLowerCase() === 'x' ? parseInt(e.slice(2), 16) : +e.slice(1)) : ENTITIES[e] ?? m);
const camel = name => name.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
const kebab = name => name.replace(/[A-Z]/g, c => '-' + c.toLowerCase());

export class Text {
  constructor(text = '') {this.nodeType = 3; this.data = String(text); this.parentNode = null;}
  get textContent() {return this.data;} set textContent(v) {this.data = String(v ?? '');}
  get parentElement() {return this.parentNode;}
  get isConnected() {return !!this.parentNode?.isConnected;}
  remove() {this.parentNode?.removeChild(this);}
  all() {return [];}
}

export class Element {
  constructor(tag, doc) {
    this.nodeType = 1; this.tagName = String(tag).toUpperCase(); this.localName = String(tag).toLowerCase(); this.ownerDocument = doc;
    this.childNodes = []; this.parentNode = null; this._attrs = new Map(); this.style = {setProperty(k, v) {this[k] = v;}, removeProperty(k) {delete this[k];}};
    this._listeners = new Map(); this.value = ''; this.checked = false; this.scrollTop = 0; this.scrollLeft = 0;
    const self = this;
    this.dataset = new Proxy({}, {
      get: (_, key) => typeof key === 'string' ? self.getAttribute('data-' + kebab(key)) ?? undefined : undefined,
      set: (_, key, value) => {self.setAttribute('data-' + kebab(key), String(value)); return true;},
      deleteProperty: (_, key) => {self.removeAttribute('data-' + kebab(key)); return true;},
      has: (_, key) => self.hasAttribute('data-' + kebab(key)),
      ownKeys: () => [...self._attrs.keys()].filter(k => k.startsWith('data-')).map(k => camel(k.slice(5))),
      getOwnPropertyDescriptor: (_, key) => self.hasAttribute('data-' + kebab(key)) ? {enumerable: true, configurable: true, value: self.getAttribute('data-' + kebab(key))} : undefined});
    this.classList = {
      contains: c => self.className.split(/\s+/).includes(c),
      add: (...cs) => {const set = new Set(self.className.split(/\s+/).filter(Boolean)); cs.forEach(c => set.add(c)); self.className = [...set].join(' ');},
      remove: (...cs) => {self.className = self.className.split(/\s+/).filter(c => c && !cs.includes(c)).join(' ');},
      toggle: (c, force) => {const on = force === undefined ? !self.classList.contains(c) : !!force; on ? self.classList.add(c) : self.classList.remove(c); return on;},
      replace: (a, b) => {if (self.classList.contains(a)) {self.classList.remove(a); self.classList.add(b);}}};
  }
  // attributes
  getAttribute(k) {return this._attrs.has(k) ? this._attrs.get(k) : null;}
  setAttribute(k, v) {this._attrs.set(k, String(v)); if (k === 'value') this.value = String(v);}
  removeAttribute(k) {this._attrs.delete(k);}
  hasAttribute(k) {return this._attrs.has(k);}
  toggleAttribute(k, force) {const on = force === undefined ? !this.hasAttribute(k) : !!force; on ? this.setAttribute(k, '') : this.removeAttribute(k); return on;}
  get attributes() {return [...this._attrs].map(([name, value]) => ({name, value}));}
  get attrs() {return Object.fromEntries(this._attrs);}
  get className() {return this.getAttribute('class') || '';} set className(v) {this.setAttribute('class', String(v ?? ''));}
  get id() {return this.getAttribute('id') || '';} set id(v) {this.setAttribute('id', v);}
  for(name) {return this;}
  // reflected boolean/string properties
  get hidden() {return this.hasAttribute('hidden');} set hidden(v) {this.toggleAttribute('hidden', !!v);}
  get disabled() {return this.hasAttribute('disabled');} set disabled(v) {this.toggleAttribute('disabled', !!v);}
  get open() {return this.hasAttribute('open');} set open(v) {this.toggleAttribute('open', !!v);}
  get required() {return this.hasAttribute('required');} set required(v) {this.toggleAttribute('required', !!v);}
  get multiple() {return this.hasAttribute('multiple');} set multiple(v) {this.toggleAttribute('multiple', !!v);}
  get readOnly() {return this.hasAttribute('readonly');} set readOnly(v) {this.toggleAttribute('readonly', !!v);}
  get inert() {return this.hasAttribute('inert');} set inert(v) {this.toggleAttribute('inert', !!v);}
  get type() {return this.getAttribute('type') || (this.localName === 'button' ? 'submit' : this.localName === 'input' ? 'text' : '');} set type(v) {this.setAttribute('type', v);}
  get name() {return this.getAttribute('name') || '';} set name(v) {this.setAttribute('name', v);}
  get title() {return this.getAttribute('title') || '';} set title(v) {this.setAttribute('title', v);}
  get href() {return this.getAttribute('href') || '';} set href(v) {this.setAttribute('href', v);}
  get src() {return this.getAttribute('src') || '';} set src(v) {this.setAttribute('src', v);}
  get placeholder() {return this.getAttribute('placeholder') || '';} set placeholder(v) {this.setAttribute('placeholder', v);}
  get tabIndex() {return Number(this.getAttribute('tabindex') ?? -1);} set tabIndex(v) {this.setAttribute('tabindex', v);}
  get htmlFor() {return this.getAttribute('for') || '';} set htmlFor(v) {this.setAttribute('for', v);}
  get rel() {return this.getAttribute('rel') || '';} set rel(v) {this.setAttribute('rel', v);}
  get target() {return this.getAttribute('target') || '';} set target(v) {this.setAttribute('target', v);}
  get rows() {return Number(this.getAttribute('rows') || 0);} set rows(v) {this.setAttribute('rows', v);}
  get size() {return Number(this.getAttribute('size') || 0);} set size(v) {this.setAttribute('size', v);}
  get selected() {return this.hasAttribute('selected');} set selected(v) {this.toggleAttribute('selected', !!v);}
  // tree
  get children() {return this.childNodes.filter(n => n.nodeType === 1);}
  get parentElement() {return this.parentNode && this.parentNode.nodeType === 1 ? this.parentNode : null;}
  get firstChild() {return this.childNodes[0] || null;} get lastChild() {return this.childNodes.at(-1) || null;}
  get firstElementChild() {return this.children[0] || null;} get lastElementChild() {return this.children.at(-1) || null;}
  get nextElementSibling() {const s = this.parentNode?.children || []; return s[s.indexOf(this) + 1] || null;}
  get previousElementSibling() {const s = this.parentNode?.children || []; return s[s.indexOf(this) - 1] || null;}
  get nextSibling() {const s = this.parentNode?.childNodes || []; return s[s.indexOf(this) + 1] || null;}
  get isConnected() {let n = this; while (n.parentNode) n = n.parentNode; return n === this.ownerDocument?.documentElement || n === this.ownerDocument;}
  _adopt(node) {if (typeof node === 'string' || typeof node === 'number') node = new Text(node); if (node?.nodeType === 11) return node.childNodes.splice(0).map(n => this._adopt(n)); node.parentNode?.removeChild(node); node.parentNode = this; return node;}
  append(...nodes) {for (const n of nodes) {const adopted = this._adopt(n); this.childNodes.push(...[adopted].flat());}}
  appendChild(n) {this.append(n); return n;}
  prepend(...nodes) {const adopted = nodes.flatMap(n => [this._adopt(n)].flat()); this.childNodes.unshift(...adopted);}
  insertBefore(node, ref) {const adopted = [this._adopt(node)].flat(); const at = ref ? this.childNodes.indexOf(ref) : -1; if (at < 0) this.childNodes.push(...adopted); else this.childNodes.splice(at, 0, ...adopted); return node;}
  removeChild(node) {const at = this.childNodes.indexOf(node); if (at >= 0) this.childNodes.splice(at, 1); node.parentNode = null; return node;}
  remove() {this.parentNode?.removeChild(this);}
  replaceChildren(...nodes) {for (const n of this.childNodes) n.parentNode = null; this.childNodes = []; this.append(...nodes);}
  replaceWith(...nodes) {const p = this.parentNode; if (!p) return; const at = p.childNodes.indexOf(this); const adopted = nodes.flatMap(n => [p._adopt(n)].flat()); p.childNodes.splice(at, 1, ...adopted); this.parentNode = null;}
  before(...nodes) {const p = this.parentNode; if (!p) return; const adopted = nodes.flatMap(n => [p._adopt(n)].flat()); p.childNodes.splice(p.childNodes.indexOf(this), 0, ...adopted);}
  after(...nodes) {const p = this.parentNode; if (!p) return; const adopted = nodes.flatMap(n => [p._adopt(n)].flat()); p.childNodes.splice(p.childNodes.indexOf(this) + 1, 0, ...adopted);}
  contains(node) {for (let n = node; n; n = n.parentNode) if (n === this) return true; return false;}
  get textContent() {return this.childNodes.map(n => n.textContent).join('');}
  set textContent(v) {this.replaceChildren(); if (v !== '' && v != null) this.append(new Text(v));}
  get innerText() {return this.textContent;} set innerText(v) {this.textContent = v;}
  set innerHTML(html) {this.replaceChildren(...parseHTML(String(html), this.ownerDocument));}
  get innerHTML() {return '';}
  all() {return [this, ...this.children.flatMap(n => n.all())];}
  querySelectorAll(selector) {const list = parseSelector(selector); return this.all().slice(1).filter(n => list.some(s => matchComplex(n, s, this)));}
  querySelector(selector) {return this.querySelectorAll(selector)[0] || null;}
  matches(selector) {return parseSelector(selector).some(s => matchComplex(this, s, null));}
  closest(selector) {for (let n = this; n && n.nodeType === 1; n = n.parentNode) if (n.matches(selector)) return n; return null;}
  // events and behaviour
  addEventListener(type, fn) {if (!this._listeners.has(type)) this._listeners.set(type, []); this._listeners.get(type).push(fn);}
  removeEventListener(type, fn) {this._listeners.set(type, (this._listeners.get(type) || []).filter(f => f !== fn));}
  dispatchEvent(event) {event.target ??= this; for (const fn of this._listeners.get(event.type) || []) fn(event); this['on' + event.type]?.(event); return true;}
  focus() {if (this.ownerDocument) this.ownerDocument.activeElement = this;}
  blur() {} select() {} setSelectionRange() {} scrollIntoView() {} scrollTo() {} setPointerCapture() {} releasePointerCapture() {}
  async click() {return this.onclick?.({preventDefault() {}, stopPropagation() {}, target: this, currentTarget: this});}
  showModal() {this.open = true;} show() {this.open = true;} close() {this.open = false; this.dispatchEvent({type: 'close'});}
  getBoundingClientRect() {return {top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0};}
  get clientWidth() {return 0;} get clientHeight() {return 0;} get offsetWidth() {return 0;} get offsetHeight() {return 0;}
  get scrollHeight() {return 0;} get scrollWidth() {return 0;}
  get options() {return this.children.filter(n => n.localName === 'option');}
  get selectedOptions() {return this.options.filter(o => o.selected);}
  get form() {return this.closest('form');}
  get elements() {return this.all().filter(n => ['input', 'select', 'textarea', 'button'].includes(n.localName));}
  checkValidity() {return true;} reportValidity() {return true;} reset() {} requestSubmit() {this.onsubmit?.({preventDefault() {}});}
  get content() {return this;}
  cloneNode(deep) {const c = new Element(this.localName, this.ownerDocument); c._attrs = new Map(this._attrs); if (deep) c.append(...this.childNodes.map(n => n.nodeType === 3 ? new Text(n.data) : n.cloneNode(true))); return c;}
  get contentWindow() {return this._contentWindow ?? null;} set contentWindow(v) {this._contentWindow = v;}
}

export function parseHTML(html, doc) {
  const root = new Element('#fragment', doc), stack = [root];
  const re = /<!--[\s\S]*?-->|<\/([a-zA-Z][\w-]*)\s*>|<([a-zA-Z][\w-]*)((?:\s+[^\s=>\/]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+))?)*)\s*(\/?)>|([^<]+)/g;
  let m;
  while ((m = re.exec(html))) {
    const top = stack.at(-1);
    if (m[1]) {const tag = m[1].toLowerCase(); for (let i = stack.length - 1; i > 0; i--) if (stack[i].localName === tag) {stack.length = i; break;} continue;}
    if (m[2]) {
      const el = new Element(m[2], doc);
      const attrRe = /([^\s=>\/]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g; let a;
      while ((a = attrRe.exec(m[3] || ''))) el.setAttribute(a[1].toLowerCase(), decode(a[2] ?? a[3] ?? a[4] ?? ''));
      if (el.hasAttribute('value')) el.value = el.getAttribute('value');
      top.append(el);
      if (!VOID.has(el.localName) && !m[4]) stack.push(el);
      continue;
    }
    if (m[5] != null && m[5] !== '') {if (top.localName === 'textarea') top.value += decode(m[5]); top.append(new Text(decode(m[5])));}
  }
  return root.childNodes.splice(0).map(n => {n.parentNode = null; return n;});
}

// --- selectors ---
function parseSelector(selector) {
  return splitTop(selector, ',').map(part => {
    const steps = [], tokens = part.trim().match(/(?:\[[^\]]*\]|\([^)]*\)|[^\s>])+|>/g) || [];
    let combinator = ' ';
    for (const t of tokens) {if (t === '>') {combinator = '>'; continue;} steps.push({combinator, compound: parseCompound(t)}); combinator = ' ';}
    return steps;
  });
}
function splitTop(text, sep) {const out = []; let depth = 0, cur = ''; for (const c of text) {if (c === '(' || c === '[') depth++; if (c === ')' || c === ']') depth--; if (c === sep && !depth) {out.push(cur); cur = '';} else cur += c;} out.push(cur); return out;}
function parseCompound(text) {
  const parts = [], re = /(\*)|([a-zA-Z][\w-]*)|#([\w-]+)|\.([\w-]+)|\[\s*([^\]=~^$*|\s]+)\s*(?:([~^$*|]?=)\s*(?:"([^"]*)"|'([^']*)'|([^\]\s]+)))?\s*\]|:not\(([^)]*)\)|:scope|:([\w-]+)(?:\([^)]*\))?/g;
  for (const m of text.matchAll(re)) {   // one const binding per match: closures keep their own match
    if (m[1]) continue;
    if (m[2]) parts.push(n => n.localName === m[2].toLowerCase());
    else if (m[3]) parts.push(n => n.id === m[3]);
    else if (m[4]) parts.push(n => n.classList.contains(m[4]));
    else if (m[5]) {const name = m[5], op = m[6], value = m[7] ?? m[8] ?? m[9];
      parts.push(n => {if (!n.hasAttribute(name)) return false; if (!op) return true; const v = n.getAttribute(name);
        return op === '=' ? v === value : op === '^=' ? v.startsWith(value) : op === '$=' ? v.endsWith(value) : op === '*=' ? v.includes(value) : op === '~=' ? v.split(/\s+/).includes(value) : v === value || v.startsWith(value + '-');});}
    else if (m[10] != null) {const inner = parseSelector(m[10]); parts.push(n => !inner.some(s => matchComplex(n, s, null)));}
    else if (m[0] === ':scope') parts.push((n, scope) => n === scope);
    else if (m[11]) {const p = m[11]; parts.push(n => p === 'checked' ? n.checked : p === 'disabled' ? n.disabled : p === 'focus' || p === 'focus-visible' || p === 'focus-within' ? n.ownerDocument?.activeElement === n : p === 'first-child' ? n.parentNode?.children[0] === n : true);}
  }
  return parts;
}
function matchCompound(n, parts, scope) {return n?.nodeType === 1 && parts.every(p => p(n, scope));}
function matchComplex(node, steps, scope) {
  const walk = (n, i) => {
    if (!matchCompound(n, steps[i].compound, scope)) return false;
    if (i === 0) return true;
    if (steps[i].combinator === '>') return walk(n.parentElement, i - 1);
    for (let p = n.parentElement; p; p = p.parentElement) if (walk(p, i - 1)) return true;
    return false;
  };
  return walk(node, steps.length - 1);
}

export function installHTMLDocument({width = 1280} = {}) {
  const saved = {};
  for (const key of ['document', 'window', 'location', 'history', 'localStorage', 'sessionStorage', 'innerWidth', 'innerHeight', 'matchMedia', 'requestAnimationFrame', 'cancelAnimationFrame', 'MutationObserver', 'ResizeObserver', 'CustomEvent', 'fetch', 'HTMLElement', 'Node', 'getComputedStyle', 'IntersectionObserver']) saved[key] = Object.getOwnPropertyDescriptor(globalThis, key);
  const doc = {nodeType: 9, activeElement: null, _listeners: new Map()};
  doc.createElement = tag => new Element(tag, doc);
  doc.createElementNS = (_ns, tag) => new Element(tag, doc);
  doc.createTextNode = text => new Text(text);
  doc.createDocumentFragment = () => {const f = new Element('#fragment', doc); f.nodeType = 11; return f;};
  doc.documentElement = new Element('html', doc); doc.documentElement.parentNode = doc;
  doc.head = new Element('head', doc); doc.body = new Element('body', doc); doc.documentElement.append(doc.head, doc.body);
  doc.activeElement = doc.body;
  doc.querySelector = s => doc.documentElement.matches(s) ? doc.documentElement : doc.documentElement.querySelector(s);
  doc.querySelectorAll = s => doc.documentElement.querySelectorAll(s);
  doc.getElementById = id => doc.documentElement.querySelector('#' + id);
  doc.addEventListener = (t, fn) => {if (!doc._listeners.has(t)) doc._listeners.set(t, []); doc._listeners.get(t).push(fn);};
  doc.removeEventListener = (t, fn) => doc._listeners.set(t, (doc._listeners.get(t) || []).filter(f => f !== fn));
  doc.dispatchEvent = e => {for (const fn of doc._listeners.get(e.type) || []) fn(e); return true;};
  const store = () => {const m = new Map(); return {getItem: k => m.has(k) ? m.get(k) : null, setItem: (k, v) => m.set(k, String(v)), removeItem: k => m.delete(k), clear: () => m.clear(), key: i => [...m.keys()][i] ?? null, get length() {return m.size;}};};
  const winListeners = new Map();
  const win = {document: doc, addEventListener: (t, fn) => {if (!winListeners.has(t)) winListeners.set(t, []); winListeners.get(t).push(fn);}, removeEventListener: (t, fn) => winListeners.set(t, (winListeners.get(t) || []).filter(f => f !== fn)),
    dispatchEvent: e => {for (const fn of winListeners.get(e.type) || []) fn(e); return true;}, scrollTo() {}, open() {}, getSelection: () => null};
  const url = new URL('http://local/project?workspace=writing&corpus=book');
  const location = {get href() {return url.href;}, set href(v) {const n = new URL(v, url); url.href = n.href;}, get search() {return url.search;}, get pathname() {return url.pathname;}, get origin() {return url.origin;}, get hash() {return url.hash;}, assign() {}, replace() {}, reload() {}};
  const history = {state: null, replaceState(_s, _t, u) {if (u) location.href = String(u);}, pushState(_s, _t, u) {if (u) location.href = String(u);}, back() {}};
  class CustomEvent {constructor(type, init = {}) {this.type = type; this.detail = init.detail;}}
  const set = (k, v) => Object.defineProperty(globalThis, k, {configurable: true, writable: true, value: v});
  set('document', doc); set('window', Object.assign(win, {location, history, innerWidth: width, innerHeight: 900}));
  set('location', location); set('history', history); set('localStorage', store()); set('sessionStorage', store());
  set('innerWidth', width); set('innerHeight', 900);
  set('matchMedia', q => ({matches: /max-width:\s*(\d+)/.test(q) ? width <= Number(/max-width:\s*(\d+)/.exec(q)[1]) : false, addEventListener() {}, removeEventListener() {}}));
  set('requestAnimationFrame', fn => setTimeout(fn, 0)); set('cancelAnimationFrame', id => clearTimeout(id));
  set('MutationObserver', class {observe() {} disconnect() {} takeRecords() {return [];}});
  set('ResizeObserver', class {observe() {} unobserve() {} disconnect() {}});
  set('IntersectionObserver', class {observe() {} unobserve() {} disconnect() {}});
  set('CustomEvent', CustomEvent); set('HTMLElement', Element); set('getComputedStyle', () => ({getPropertyValue: () => ''}));
  win.CustomEvent = CustomEvent; win.localStorage = globalThis.localStorage; win.sessionStorage = globalThis.sessionStorage; win.matchMedia = globalThis.matchMedia;
  return {document: doc, window: win, location, restore() {for (const [k, d] of Object.entries(saved)) {if (d) Object.defineProperty(globalThis, k, d); else delete globalThis[k];}}};
}
