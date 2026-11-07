"""Where exports go and what they are called (Qt-free). Files sit in a folder next to the project
file: pdf/ and dxf/. One file per sheet named after its tab ("01 Title"), and a merged PDF named
after the job."""
from __future__ import annotations
import os
import re
from . import model as m

_BAD = re.compile(r'[\\/:*?"<>|\n\r\t]')


def clean(name: str) -> str:
    s = re.sub(r"\s+", " ", _BAD.sub("_", name)).strip().rstrip(".")
    return s or "untitled"


def tab_label(sheet: m.Sheet) -> str:
    return f"{sheet.page:02d}  {sheet.title}".rstrip()


def sheet_stem(sheet: m.Sheet) -> str:
    """File name (no extension) of a sheet: its tab name."""
    return clean(tab_label(sheet))


def job_stem(project: m.Project, project_path: str = "") -> str:
    """Name of the merged file: the Job field, else the project file's name."""
    job = str(project.info.get("job", "")).strip()
    if job:
        return clean(job)
    return clean(os.path.splitext(os.path.basename(project_path))[0]) if project_path else "job"


def export_folder(project_path: str, kind: str) -> str:
    """<folder of the project file>/<kind> (pdf or dxf)."""
    return os.path.join(os.path.dirname(os.path.abspath(project_path)), kind)
