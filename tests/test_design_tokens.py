"""THE DESIGN TOKENS LINT (M5 C11, 2026-10-14): colour literals live in tokens.css only.

The app stylesheets, the shell modules and the walk page were migrated to tokens (plan §2: 303 + 221
+ 95 literals in the three largest sheets, 1,101 uses over 19 files in all). This test keeps them out:
the allowed homes are tokens.css (the semantic set and the derived extended palette), hymn.css (the
other applets' palette, outside M5) and the walk page's own `:root` alias block (its walk-only marks).
It also checks that every token the migrated files reference is defined, so a renamed token cannot
silently fall back to the browser default.
"""
import re
from pathlib import Path

STATIC = Path('src/laplace/web/static_shared')
WALK = Path('src/laplace/web/walk.html')
LITERAL = re.compile(r'(?<![\w&-])#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![\w-])|rgba?\(\s*[\d.]+\s*[, ]')
TOKEN_USE = re.compile(r'var\((--[\w-]+)')
TOKEN_DEF = re.compile(r'(--[\w-]+)\s*:')
ALLOWED = {'tokens.css', 'hymn.css'}


def _walk_outside_aliases():
    text = WALK.read_text()
    block = re.search(r':root\s*\{[^}]*\}', text)
    return text[:block.start()] + text[block.end():]


def test_no_colour_literal_outside_the_token_sheet():
    offenders = {}
    for path in sorted(STATIC.glob('*.css')) + sorted(STATIC.glob('*.mjs')):
        if path.name in ALLOWED:
            continue
        hits = [m.group(0) for m in LITERAL.finditer(path.read_text())]
        if hits:
            offenders[path.name] = hits[:8]
    walk_hits = [m.group(0) for m in LITERAL.finditer(_walk_outside_aliases())]
    if walk_hits:
        offenders[WALK.name] = walk_hits[:8]
    assert not offenders, offenders


def test_every_referenced_token_is_defined_and_every_extended_token_is_used():
    tokens = (STATIC / 'tokens.css').read_text()
    defined = set(TOKEN_DEF.findall(tokens))
    assert {'--ink', '--ink2', '--bg', '--panel', '--panel2', '--edge', '--edge2', '--accent', '--ok', '--warn', '--bad', '--dim', '--focus-ring'} <= defined
    used = set()
    local = set()
    for path in sorted(STATIC.glob('*.css')) + sorted(STATIC.glob('*.mjs')) + [WALK]:
        if path.name in ALLOWED:
            continue
        text = path.read_text()
        used.update(TOKEN_USE.findall(text))
        local.update(TOKEN_DEF.findall(text))   # component-local custom properties (--nav-width, --rc-*, the walk aliases ...)
    family = r'--(?:(?:grey|red|orange|gold|lime|green|mint|teal|cyan|sky|blue|indigo|violet|magenta|rose|shade|tint)-\d[\w-]*|paper|black)'
    palette = {name for name in defined if re.fullmatch(family, name)}
    # the colour tokens (semantic and palette) a file references must be defined in tokens.css; other
    # custom properties (--nav-width, --rc-*, the walk's own names, JS-set --fill ...) are the modules' own
    colour = {name for name in used if name in {'--ink', '--ink2', '--bg', '--panel', '--panel2', '--edge', '--edge2', '--accent', '--ok', '--warn', '--bad', '--dim', '--held'}
              or re.fullmatch(family, name)}
    undefined = colour - defined
    assert not undefined, sorted(undefined)
    unused = palette - used
    assert not unused, sorted(unused)


def test_the_extended_palette_is_bounded_and_derived():
    tokens = (STATIC / 'tokens.css').read_text()
    assert 'THE EXTENDED PALETTE (M5 C11' in tokens, 'the derived palette carries its own account'
    extended = tokens[tokens.index('THE EXTENDED PALETTE (M5 C11'):]
    names = TOKEN_DEF.findall(extended)
    assert len(names) == len(set(names)) and len(names) <= 220, len(names)


def test_custom_properties_resolve_without_cycles_in_every_reached_scope():
    """Repair H2 (W3C css-variables-1 §2.3): a custom property whose value refers to itself, directly or through
    other custom properties, is invalid at computed-value time and takes the guaranteed-invalid value instead of
    inheriting. The migration must never alias a name to itself (`--accent: var(--accent)`) in any scope. This
    walks every custom-property declaration of the app stylesheets, the walk page and the shell modules' inline
    style text, builds the reference graph (scope-insensitive, so a cycle through any scope is caught) and
    refuses self and indirect cycles; it also checks that every colour token a declaration refers to is defined."""
    decl = re.compile(r'(--[\w-]+)\s*:\s*([^;}]+)')
    refs = {}
    for path in sorted(STATIC.glob('*.css')) + sorted(STATIC.glob('*.mjs')) + [WALK]:
        if path.name in ALLOWED - {'tokens.css'}:
            continue
        for name, value in decl.findall(path.read_text()):
            uses = set(TOKEN_USE.findall(value))
            if uses:
                refs.setdefault(name, set()).update(uses)
            assert name not in uses, '%s: %s aliases itself (%s)' % (path.name, name, value.strip())
    # indirect cycles
    def walk(start, node, seen):
        for nxt in refs.get(node, ()):
            assert nxt != start, 'custom property cycle through %s -> %s' % (start, ' -> '.join(seen + [nxt]))
            if nxt not in seen:
                walk(start, nxt, seen + [nxt])
    for name in refs:
        walk(name, name, [name])
    # the scoped workspace aliases resolve to root tokens, never to themselves
    workspace = (STATIC / 'workspace.css').read_text()
    assert '--accent:var(--accent)' not in workspace and workspace.count('--surface:var(--panel)') >= 1
    defined = set(TOKEN_DEF.findall((STATIC / 'tokens.css').read_text()))
    assert '--accent' in defined and '--held' in defined


def _css_rules(text):
    """A bounded CSS block walker (comments and strings stripped): returns (prelude, body, nested) for every
    top-level rule. Enough to prove the grammar shape this test needs; not a browser."""
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    text = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '""', text)
    rules, i, start, depth, open_at = [], 0, 0, 0, None
    while i < len(text):
        c = text[i]
        if c == '{':
            if depth == 0:
                open_at = i
            depth += 1
        elif c == '}':
            depth -= 1
            assert depth >= 0, 'unbalanced closing brace at offset %d' % i
            if depth == 0:
                rules.append((text[start:open_at].strip(), text[open_at + 1:i]))
                start = i + 1
        elif c == ';' and depth == 0:
            start = i + 1   # a top-level statement such as @import
        i += 1
    assert depth == 0, 'unclosed block'
    assert not text[start:].strip(), 'dangling text after the last rule: %r' % text[start:].strip()[:80]
    return rules


def test_app_stylesheets_have_well_formed_top_level_rules_and_the_narrow_help_rules_are_a_real_media_block():
    """Repair2 R1: a dangling selector before `@media(max-width:1000px)` made the browser read the media query
    as part of an invalid selector and drop the three narrow help rules. Every top-level prelude must be an
    at-rule or a selector that contains no at-keyword, braces must balance, and the dock rules must sit
    inside a top-level @media(max-width:1000px) block."""
    for path in sorted(STATIC.glob('*.css')):
        for prelude, body in _css_rules(path.read_text()):
            assert prelude, '%s: a block without a prelude' % path.name
            if not prelude.startswith('@'):
                assert '@' not in prelude, '%s: selector swallows an at-rule: %r' % (path.name, prelude[:120])
    rules = _css_rules((STATIC / 'workspace.css').read_text())
    narrow = [body for prelude, body in rules if prelude.replace(' ', '') == '@media(max-width:1000px)' and '.workspace-help.is-dock' in body]
    assert len(narrow) == 1, 'the narrow help dock rules are in one top-level media block'
    for selector in ('.workspace-help.is-dock{', '.workspace-help.is-dock.is-expanded{', '.workspace-help.is-dock:not(.is-expanded) .workspace-help-body{'):
        assert selector in narrow[0], selector
    # the topology viewport keeps one style owner
    assert '.topology-viewport' not in (STATIC / 'workspace.css').read_text()
    assert '.workspace-help-diagram .topology-viewport{height:260px}' in (STATIC / 'workspace-presentation.css').read_text()
