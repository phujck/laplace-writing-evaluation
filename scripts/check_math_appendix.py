import re
from collections import Counter

SUPMAP = str.maketrans('\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079'
                       '\u2080\u2081\u2082\u2083\u2084\u2085\u2086\u2087\u2088\u2089',
                       '01234567890123456789')
SUPCHARS = '\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079' \
           '\u2080\u2081\u2082\u2083\u2084\u2085\u2086\u2087\u2088\u2089'

def common(t):
    # unicode super/subscript RUNS -> a separated decimal number (kw_16 stays 16, x^2 -> 2)
    t = re.sub('[' + SUPCHARS + ']+', lambda m: ' ' + m.group(0).translate(SUPMAP) + ' ', t)
    t = t.replace('−','-').replace('–','-').replace('—','-')
    t = t.replace('½',' 1 2 ')   # vulgar one-half == \tfrac{1}{2}
    # thousands separators -> nothing (formatting only)
    t = re.sub(r'(?<=\d),(?=\d\d\d(?!\d))', '', t)
    return t

def md_tokens(path):
    lines = open(path, encoding='utf-8').read().split('\n')
    out=[]
    for L in lines:
        # markdown heading numbering (## 1. / ### 1.1) -> LaTeX auto-numbering, dropped
        L = re.sub(r'^(#{1,6}\s+)[0-9]+(\.[0-9]+)?\.?\s', r'\1', L)
        out.append(L)
    t = common('\n'.join(out))
    return Counter(re.findall(r'\d+(?:\.\d+)?', t))

def tex_tokens(path):
    t = open(path, encoding='utf-8').read()
    t = re.sub(r'(?m)(?<!\\)%.*$', '', t)          # comments
    t = t.replace('{,}', ',')                       # math thousands separator
    t = re.sub(r'\\\\allowbreak\\s*', '', t)               # invisible break hints
    t = re.sub(r'\\[A-Za-z]+', ' ', t)              # control sequences (\S, \texttt, \mathrm...)
    t = t.replace('{',' ').replace('}',' ')
    t = common(t)
    return Counter(re.findall(r'\d+(?:\.\d+)?', t))


# Baselined structural residue (the 2026-08-16 conversion report): tex-side macro
# tokens and the md's five ordered-list markers absorbed by enumerate.
TEX_STRUCTURAL = Counter({"1": 4, "3": 2, "0": 1})
MD_STRUCTURAL = Counter({"1": 1, "2": 1, "3": 1, "4": 1, "5": 1})

def main(md_path="ATLAS_MATHEMATICS.md", tex_path="walkthrough/appendix-mathematics.tex"):
    md = md_tokens(md_path)
    tx = tex_tokens(tex_path)
    only_md = md - tx - MD_STRUCTURAL
    only_tx = tx - md - TEX_STRUCTURAL
    if not only_md and not only_tx:
        print(f"math appendix: OK - numeric multisets match ({sum(md.values())} tokens) "
              "modulo the baselined conversion residue")
        return 0
    if only_md:
        print("DRIFT md-only:", dict(only_md))
    if only_tx:
        print("DRIFT tex-only:", dict(only_tx))
    print("the source or the copy moved since the 2026-08-16 baseline - re-convert or "
          "re-baseline through a reviewed commit, never ignore")
    return 1

if __name__ == "__main__":
    import sys
    args = sys.argv[1:3]
    raise SystemExit(main(*args))
