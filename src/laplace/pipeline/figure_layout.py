"""figure_layout.py - the house figure standard's "reserve space for every label" made mechanical.

Every text placed through :class:`Layout` is registered with the horizontal span it is allowed and the patch it
may sit on. After drawing, :meth:`Layout.check` converts every rendered extent into data coordinates and refuses
the figure on any of: text outside its span, text outside its container box, text over another text, text over a
patch that is not its container, text clipped by the axes. A figure with a collision is never written.

    from laplace.pipeline.figure_layout import Layout, house_rc, OKABE_ITO
    house_rc()
    fig = plt.figure(figsize=(16.8 / 2.54, 6 / 2.54)); ax = fig.add_axes([0, 0, 1, 1])   # the axes ARE the figure
    L = Layout(ax)
    L.text(x, y, "label", span=(x0, x1), box=patch, ...)          # box may be (container, frame, ...)
    L.check(fig)          # raises SystemExit with every collision named
    fig.savefig(out)      # no bbox_inches="tight": the page is exactly figsize, so type is never rescaled

The two rules that make the arithmetic honest: the axes fill the figure (a point on the page is a point in the
script) and the figure is saved at its declared size (LaTeX scales nothing).
"""
from __future__ import annotations

import matplotlib
from matplotlib.patches import FancyArrowPatch

# Okabe-Ito categorical palette (figure_standards.md)
OKABE_ITO = {"orange": "#E69F00", "sky": "#56B4E9", "green": "#009E73", "yellow": "#F0E442", "blue": "#0072B2",
             "vermilion": "#D55E00", "purple": "#CC79A7", "black": "#000000"}
GREY = "#6f6f6f"


def house_rc() -> None:
    """Body serif via usetex, embedded TrueType, 9 pt base - the manuscript's own type."""
    matplotlib.rcParams.update({"text.usetex": True, "font.family": "serif", "font.size": 9, "pdf.fonttype": 42})


class Layout:
    def __init__(self, ax):
        self.ax = ax
        self.placed: list[tuple] = []   # (text, allowed span or None, container patch or None)

    def text(self, x, y, s, span=None, box=None, **k):
        k.setdefault("color", OKABE_ITO["black"])
        t = self.ax.text(x, y, s, **k)
        self.placed.append((t, span, box))
        return t

    def extent(self, artist, renderer):
        b = artist.get_window_extent(renderer)
        inv = self.ax.transData.inverted()
        (x0, y0), (x1, y1) = inv.transform([[b.x0, b.y0], [b.x1, b.y1]])
        return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)

    def check(self, fig, box_pad=(0.04, 0.02)) -> None:
        fig.canvas.draw()
        r = fig.canvas.get_renderer()
        ax = self.ax

        def hit(a, b, pad=0.0):
            return a[0] < b[2] - pad and b[0] < a[2] - pad and a[1] < b[3] - pad and b[1] < a[3] - pad

        texts = [(t, self.extent(t, r), span, box) for t, span, box in self.placed if t.axes is ax and t.get_text()]
        ax_x0, ax_x1 = sorted(ax.get_xlim()); ax_y0, ax_y1 = sorted(ax.get_ylim())
        bad: list[str] = []
        for k, (t, e, span, box) in enumerate(texts):
            s = t.get_text()
            if e[0] < ax_x0 - 1e-6 or e[2] > ax_x1 + 1e-6 or e[1] < ax_y0 - 1e-6 or e[3] > ax_y1 + 1e-6:
                bad.append(f"clipped by the axes: {s!r} x {e[0]:.2f}-{e[2]:.2f} y {e[1]:.2f}-{e[3]:.2f}")
            if span and (e[0] < span[0] - 1e-6 or e[2] > span[1] + 1e-6):
                bad.append(f"overflows its span: {s!r} x {e[0]:.2f}-{e[2]:.2f}, allowed {span[0]:.2f}-{span[1]:.2f}")
            boxes = tuple(box) if isinstance(box, (tuple, list)) else (box,)   # first = container, rest = frames it sits in
            if boxes[0] is not None:
                eb = self.extent(boxes[0], r); px, py = box_pad
                if e[0] < eb[0] + px or e[2] > eb[2] - px or e[1] < eb[1] + py or e[3] > eb[3] - py:
                    bad.append(f"not inside its box: {s!r} x {e[0]:.2f}-{e[2]:.2f} y {e[1]:.2f}-{e[3]:.2f}, "
                               f"box x {eb[0]:.2f}-{eb[2]:.2f} y {eb[1]:.2f}-{eb[3]:.2f}")
            for t2, e2, _, _ in texts[k + 1:]:
                if hit(e, e2):
                    bad.append(f"text on text: {s!r} x {t2.get_text()!r}")
            for pch in ax.patches:
                if pch in boxes or isinstance(pch, FancyArrowPatch) or not pch.get_visible():
                    continue
                if hit(e, self.extent(pch, r), pad=0.01):
                    ep = self.extent(pch, r)
                    bad.append(f"text on a patch: {s!r} over {type(pch).__name__} at x {ep[0]:.2f}-{ep[2]:.2f} y {ep[1]:.2f}-{ep[3]:.2f}")
        if bad:
            raise SystemExit("figure_layout: collisions -\n  " + "\n  ".join(bad))
