import shutil
from pathlib import Path
import pytest
from laplace.pipeline import tikz_render

@pytest.mark.skipif(not (shutil.which('pdflatex') or shutil.which('lualatex')),reason='TeX unavailable')
def test_renders_labelled_conceptual_diagram(tmp_path):
 out=tikz_render.render('\\begin{tikzpicture}\\node[draw] (a) {Evidence};\\node[draw,right=of a] (b) {Claim};\\draw[->] (a)--(b);\\end{tikzpicture}',out_dir=tmp_path)
 assert out['status']=='READY' and Path(out['pdf_path']).is_file() and 'Evidence' in Path(out['source_path']).read_text()
