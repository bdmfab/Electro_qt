"""Rich text markup (Qt-free). A text object with rich=True keeps its source as plain text
with a few inline tags:

    <b>..</b> bold   <i>..</i> italic   <u>..</u> underline
    <size=1.5>..</size>   size as a multiple of the text height
    <color=1>..</color>   colour as an index of the colour palette (1 red ... 11 orange)

A literal < > & is written &lt; &gt; &amp;. Field codes such as {page} work inside the markup
(they are replaced before the markup is read)."""
from __future__ import annotations
import re
from dataclasses import dataclass

_TAG = re.compile(r"<(/?)(b|i|u|size|color)(?:=([^>]*))?>")


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    size: float = 1.0
    color: int = None


def escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def unescape(s: str) -> str:
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def parse(markup: str):
    """-> [[Run, ...], ...] one list of runs per line."""
    lines = [[]]
    b = i = u = 0
    sizes, colors = [], []
    pos = 0

    def add(text):
        for k, part in enumerate(text.split("\n")):
            if k:
                lines.append([])
            if part:
                lines[-1].append(Run(unescape(part), b > 0, i > 0, u > 0, sizes[-1] if sizes else 1.0,
                                     colors[-1] if colors else None))

    for mt in _TAG.finditer(markup):
        add(markup[pos:mt.start()])
        pos = mt.end()
        closing, name, arg = mt.group(1) == "/", mt.group(2), mt.group(3)
        if name == "b":
            b = max(0, b + (-1 if closing else 1))
        elif name == "i":
            i = max(0, i + (-1 if closing else 1))
        elif name == "u":
            u = max(0, u + (-1 if closing else 1))
        elif name == "size":
            if closing:
                if sizes:
                    sizes.pop()
            else:
                try:
                    sizes.append(min(max(float(arg), 0.1), 20.0))
                except (TypeError, ValueError):
                    sizes.append(1.0)
        else:
            if closing:
                if colors:
                    colors.pop()
            else:
                try:
                    colors.append(int(arg))
                except (TypeError, ValueError):
                    colors.append(None)
    add(markup[pos:])
    return lines


def plain(markup: str) -> str:
    """The text without formatting."""
    return "\n".join("".join(r.text for r in line) for line in parse(markup))


def dumps(lines) -> str:
    """[[Run, ...], ...] -> markup (inverse of parse)."""
    out = []
    for line in lines:
        s = ""
        for r in line:
            t = escape(r.text)
            if r.underline:
                t = f"<u>{t}</u>"
            if r.italic:
                t = f"<i>{t}</i>"
            if r.bold:
                t = f"<b>{t}</b>"
            if abs(r.size - 1.0) > 1e-6:
                t = f"<size={r.size:g}>{t}</size>"
            if r.color is not None:
                t = f"<color={r.color}>{t}</color>"
            s += t
        out.append(s)
    return "\n".join(out)
