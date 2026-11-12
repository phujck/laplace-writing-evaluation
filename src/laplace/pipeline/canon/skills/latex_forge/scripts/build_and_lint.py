import sys
import re
import os

def read_safe(filepath):
    """Gracefully handle UTF-16 artifacts from PowerShell and standard UTF-8."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.readlines()
    except UnicodeDecodeError:
        with open(filepath, 'r', encoding='utf-16') as f:
            return f.readlines()

def lint_file(filepath, auto_fix=False):
    # Honest exit contract: an unreadable target is an operational failure
    # (exit 2), never a silent pass. A report with flags is still a successful
    # run (exit 0) - flagging slop is the skill working, not failing.
    if not os.path.isfile(filepath):
        print(f"Error: {filepath} is not a readable file.", file=sys.stderr)
        sys.exit(2)

    try:
        lines = read_safe(filepath)
    except (OSError, UnicodeError) as e:
        print(f"Error: cannot read {filepath}: {e}", file=sys.stderr)
        sys.exit(2)
    flags = []           # structural violations (layout / variable / TikZ) - real faults
    advisories = []      # recorded forks (F33 orthography, F34 punctuation) + slop review

    # Dictionaries of banned syntax
    americanisms = {
        r'\banalyze\b': 'analyse',
        r'\bbehavior\b': 'behaviour',
        r'\bparameterize\b': 'parametrise',
        r'\bparameterized\b': 'parametrised',
        r'\bcolor\b': 'colour',
        r'\bmodeling\b': 'modelling'
    }

    ai_slop = [
        r'\bdelve\b',
        r'\btapestry\b',
        r'\btestament\b',
        r'\bcrucial\b',
        r'\bnot merely\b',
        r'\bbut rather\b',
        r'\bin summary\b',
        r'\bin conclusion\b'
    ]

    tikz_bans = {
        r'\[red\]': '[red!80!black]',
        r'\[blue\]': '[blue!80!black]',
        r'\[green\]': '[green!80!black]',
        r'\[yellow\]': '[yellow!80!black]',
        r'\boutput/.style\b': 'finalnode/.style (output is a reserved TikZ keyword that breaks positioning)',
        r'\bstyle\s*=\s*output\b': 'style=finalnode (output is a reserved TikZ keyword)',
        r'\[output\]': '[finalnode] (output is a reserved TikZ keyword)'
    }

    # F34 punctuation surface - his STATED going-forward preference (spaced hyphen;
    # no semicolons / em- / en-dashes). RECALIBRATED 2026-07-09 (Phase I1): the
    # corpus USES semicolons (69) and spaced en-dashes (27), so this is a stated
    # editorial override, NOT a corpus derivation - demoted from hard flag to
    # advisory. (The weld voice floor, schema.VOICE_FAILURE_PATTERNS['surface-
    # invariant'], keeps it enforced on freshly generated prose; this general
    # linter no longer hard-flags his own historical practice.)
    punctuation_pref = [
        (r';', "Semicolon - his stated preference is a spaced hyphen ( - ) (corpus uses semicolons; advisory only)."),
        (r'---', "Em-dash (---) - his stated preference is a spaced hyphen ( - ) (advisory only)."),
        (r'(?<!\-)--(?!\-)', "En-dash (--) - his stated preference is a spaced hyphen ( - ) (advisory only).")
    ]

    modified_lines = []
    changed = False

    in_figure_star = False
    in_tikz = False

    for i, line in enumerate(lines):
        orig_line = line
        
        # Track environments for layout and variable consistency checks
        if r'\begin{figure*}' in line:
            in_figure_star = True
        elif r'\end{figure*}' in line:
            in_figure_star = False
            
        if r'\begin{tikzpicture}' in line or r'\begin{axis}' in line:
            in_tikz = True
        elif r'\end{tikzpicture}' in line or r'\end{axis}' in line:
            in_tikz = False

        # Check Layout Distortion
        if in_figure_star and r'\linewidth' in line and r'\includegraphics' in line:
            flags.append(f"- **Line {i+1}** [Layout Distortion]: `\\linewidth` used for graphic inside `figure*`. This stretches single-column Python figures across the full page. Consider using `\\columnwidth` or a specific scaled width.")

        # Check Variable Inconsistency in TikZ/Axis
        if in_tikz:
            if re.search(r'[xy]label\s*=\s*\{?\s*\$?[xyz]\$?\s*\}?(?=[,\]\s]|$)', line, re.IGNORECASE):
                flags.append(f"- **Line {i+1}** [Variable Inconsistency]: Generic TikZ axis label (x/y/z) detected. Ensure this matches manuscript text (e.g., \\mathcal{{M}} vs x, \\theta vs z).")
            if re.search(r'\\node[^;]*\{\s*\$?[xyz]\$?\s*\}\s*;', line, re.IGNORECASE):
                flags.append(f"- **Line {i+1}** [Variable Inconsistency]: Generic TikZ node variable (x/y/z) detected. Ensure this matches manuscript text (e.g., \\mathcal{{M}} vs x, \\theta vs z).")

        # Orthography is a RECORDED FORK (F33), not a hard rule. The corpus is
        # MIXED - British AND American, even within a single file (polaron uses
        # both "behaviour" and "behavior") - so British-only is NOT corpus-derived;
        # his own papers fail it. RECALIBRATED 2026-07-09 (Phase I1): report as
        # advisory, NEVER auto-correct spelling.
        for pattern, replacement in americanisms.items():
            if re.search(pattern, line, re.IGNORECASE):
                name = pattern.replace(r'\b', '')
                advisories.append(f"- **Line {i+1}** [Orthography Fork F33 (advisory)]: Found `{name}`. British/American is a recorded fork; the corpus is mixed - reported, not corrected.")

        # AI slop stays advisory (flag-for-review, never auto-strip): a blacklist
        # breeds synonyms, and "crucial"/"showcase" appear in his genuine prose.
        for pattern in ai_slop:
            if re.search(pattern, line, re.IGNORECASE):
                name = pattern.replace(r'\b', '')
                advisories.append(f"- **Line {i+1}** [AI Slop (advisory)]: Found `{name}`. Review for sycophantic or narrative bloat.")

        # Check and Fix TikZ Colors
        for pattern, replacement in tikz_bans.items():
            if re.search(pattern, line, re.IGNORECASE):
                flags.append(f"- **Line {i+1}** [Aesthetics]: Found raw `{pattern}` in TikZ. The 'Child Made It' rule mandates Nature-style premium colors (e.g., `{replacement}`).")
                if auto_fix:
                    line = re.sub(pattern, replacement, line, flags=re.IGNORECASE)
                    
        # F34 punctuation preference - advisory (see punctuation_pref note above).
        for pattern, message in punctuation_pref:
            if re.search(pattern, line):
                # Simple heuristic to avoid flagging TikZ semicolons: if line ends with ';' and contains '\' or '(', ignore.
                if pattern == r';' and line.strip().endswith(';') and ('\\' in line or '(' in line or 'tikz' in line.lower()):
                    continue
                # Ignore en-dashes used for page ranges or equations or TikZ paths
                if pattern == r'(?<!\-)--(?!\-)' and (re.search(r'\d--\d', line) or '\\draw' in line or '\\path' in line or '\\node' in line or '\\fill' in line):
                    continue
                advisories.append(f"- **Line {i+1}** [Punctuation F34 (advisory, stated-preference)]: {message}")

        modified_lines.append(line)
        if line != orig_line:
            changed = True

    if auto_fix and changed:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(modified_lines)
        # Only Nature-style TikZ colours are auto-fixed. Spelling (F33) and
        # punctuation (F34) are recorded FORKS and are NEVER auto-corrected.
        print(f"AUTO-FIX APPLIED: Re-wrote {filepath} with Nature-style TikZ colours (spelling/punctuation forks untouched).")

    print(f"# LaTeX Forge Lint Report: {os.path.basename(filepath)}")
    print("*" * 50)
    if not flags and not advisories:
        print("PASS: No violations detected.")
    else:
        if flags:
            print("STRUCTURAL FLAGS (address before presenting):\n")
            for flag in flags:
                print(flag)
        else:
            print("PASS (structural): no structural violations detected.")
        if advisories:
            print("\nADVISORY - recorded forks (F33 spelling / F34 punctuation) + slop review.")
            print("These NEVER block and are NEVER auto-corrected (the corpus is mixed / stated-preference):\n")
            for a in advisories:
                print(a)
        print("\n*Protocol:* structural flags are faults; advisories are recorded forks/review only. "
              "`--auto-fix` resolves TikZ colours only - spelling and punctuation are never auto-edited.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python build_and_lint.py <path_to_tex_file> [--auto-fix]", file=sys.stderr)
        sys.exit(2)
    else:
        filepath = sys.argv[1]
        auto_fix = '--auto-fix' in sys.argv
        lint_file(filepath, auto_fix)
