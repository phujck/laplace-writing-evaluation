"""The walk's source as one text for tests that read or slice its functions (M5 S2): walk.mjs is the
composition root and its owner modules are walk-*.mjs beside it (same order as tests/helpers/walk_source.mjs)."""
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / 'src' / 'laplace' / 'web' / 'static_shared'
WALK_FILES = ['walk.mjs', *sorted(p.name for p in STATIC.glob('walk-*.mjs'))]


def walk_source() -> str:
    return '\n'.join((STATIC / name).read_text(encoding='utf-8') for name in WALK_FILES)


def walk_declaration(name: str) -> str:
    """One top-level declaration by name, verbatim with its leading comment, from whichever owner module
    holds it (the same rule as walkDeclaration in tests/helpers/walk_source.mjs)."""
    import re
    pattern = re.compile(r'^(?:export )?(?:async )?(?:function\*? ' + re.escape(name) + r'\(|(?:const|let) ' + re.escape(name) + r'\b)', re.M)
    for file in WALK_FILES:
        text = (STATIC / file).read_text(encoding='utf-8')
        match = pattern.search(text)
        if not match:
            continue
        start = match.start()
        while start > 0:
            previous = text.rfind('\n', 0, start - 1) + 1
            if not re.match(r'(//|/\*\*|\s\*)', text[previous:start - 1]):
                break
            start = previous
        following = re.search(r'\n(?=[^\s}\])])', text[match.start() + 1:])
        end = match.start() + 1 + following.start() + 1 if following else len(text)
        return text[start:end]
    raise LookupError('No walk declaration named ' + name)


def walk_declarations(*names: str) -> str:
    return '\n'.join(walk_declaration(name) for name in names)
