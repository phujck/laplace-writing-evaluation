"""Bounded renderer for authored TikZ conceptual diagrams."""
from __future__ import annotations
import shutil,subprocess,tempfile,re
from pathlib import Path
from typing import Any

def render(snippet:str, *, style:dict[str,Any]|None=None, out_dir:Path|str, timeout:int=45)->dict:
    if not isinstance(snippet,str) or not snippet.strip(): raise ValueError('TikZ snippet is required')
    latex=shutil.which('pdflatex') or shutil.which('lualatex')
    if not latex:return {'status':'UNAVAILABLE','reason':'no local TeX compiler'}
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    values=style or {}; preamble='\\documentclass[tikz,border=2pt]{standalone}\n\\usepackage{amsmath,amssymb,pgfplots}\n\\pgfplotsset{compat=1.18}\n\\usetikzlibrary{positioning,arrows.meta,calc,fit,matrix,backgrounds,decorations.pathreplacing,patterns,shapes.geometric}\n'
    font_size=float(values.get('font_size',9)); line_width=float(values.get('line_width',1.2))
    if not 6<=font_size<=24 or not 0<line_width<10: raise ValueError('Invalid TikZ house-style dimensions')
    for name,key,default in [('eigenInk','ink','#20252a'),('eigenFill','diagram_fill','#f5f7fa'),('eigenBorder','diagram_border','#7b8794')]:
        colour=str(values.get(key,default))
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',colour): raise ValueError('Invalid TikZ house colour')
        preamble+='\\definecolor{'+name+'}{HTML}{'+colour[1:]+'}\n'
    for index,colour in enumerate(values.get('palette',[])):
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',str(colour)):raise ValueError('Invalid TikZ palette')
        preamble+='\\definecolor{eigenAccent'+str(index)+'}{HTML}{'+colour[1:]+'}\n'
    preamble+='\\tikzset{every picture/.style={draw=eigenInk,line width='+str(line_width)+'pt},every node/.style={text=eigenInk,font=\\rmfamily\\fontsize{'+str(font_size)+'}{'+str(font_size*1.2)+'}\\selectfont},eigen box/.style={draw=eigenBorder,fill=eigenFill,rounded corners=2pt,inner sep=5pt},eigen arrow/.style={-{Stealth},draw=eigenInk}}\n'
    source=preamble+'\\begin{document}\n'+snippet+'\n\\end{document}\n'
    with tempfile.TemporaryDirectory(prefix='laplace-tikz-') as tmp:
        work=Path(tmp); tex=work/'diagram.tex';tex.write_text(source,encoding='utf8')
        run=subprocess.run([latex,'-no-shell-escape','-interaction=nonstopmode','-halt-on-error',tex.name],cwd=work,capture_output=True,text=True,timeout=timeout)
        pdf=work/'diagram.pdf'
        if run.returncode or not pdf.is_file(): return {'status':'FAILED','reason':(run.stderr or run.stdout)[-2000:],'source':snippet}
        target=out/'diagram.pdf';shutil.copy2(pdf,target)
        png=out/'diagram.png';cairo=shutil.which('pdftocairo')
        if cairo: subprocess.run([cairo,'-png','-singlefile','-r','180',str(target),str(png.with_suffix(''))],capture_output=True,timeout=timeout)
        svg=out/'diagram.svg';conv=shutil.which('pdf2svg')
        if conv: subprocess.run([conv,str(target),str(svg)],capture_output=True,timeout=timeout)
        elif shutil.which('dvisvgm'):
            subprocess.run([shutil.which('dvisvgm'),'--pdf','--no-fonts','--page=1',
                            '--output='+str(svg),str(target)],capture_output=True,timeout=timeout)
        (out/'diagram.tikz').write_text(snippet,encoding='utf8')
    return {'status':'READY','pdf_path':str(target),'png_path':str(png) if png.is_file() else None,'svg_path':str(svg) if svg.is_file() else None,'source_path':str(out/'diagram.tikz'),'style':values}
