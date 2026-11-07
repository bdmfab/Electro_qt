"""Field codes in text ({job}, {page}, ...). Qt-free."""
from __future__ import annotations
import datetime
import re
from . import model as m
from .geometry import walk

_CODE = re.compile(r"\{(\w+)\}")


def today() -> str:
    return datetime.date.today().strftime("%m/%d/%y")


def context(project: m.Project, sheet: m.Sheet) -> dict:
    ctx = {k: str(v) for k, v in project.info.items()}
    ctx.update(page=f"{sheet.page:02d}", pages=f"{len(project.sheets):02d}",
               sheet_name=sheet.title, job=ctx.get("job", ""))
    for i, t in enumerate(sheet.title_lines, 1):
        ctx[f"title{i}"] = t
    return ctx


def resolve(source: str, ctx: dict) -> str:
    """Replace {name} with its value; unknown names are left as written."""
    return _CODE.sub(lambda mt: ctx.get(mt.group(1), mt.group(0)), source)


def refresh_sheet(project: m.Project, sheet: m.Sheet) -> None:
    ctx = context(project, sheet)
    for e in walk(list(sheet.frame) + list(sheet.entities)):
        if isinstance(e, m.Text):
            e.resolved = resolve(e.source, ctx)


def refresh_project(project: m.Project) -> None:
    for s in project.sheets.values():
        refresh_sheet(project, s)
