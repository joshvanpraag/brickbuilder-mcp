"""BrickLink Studio .io files, written directly (no Studio needed).

A .io file is a zip. Studio's own sample files show the layout:
    model.ldr          the model as LDraw (one "0 FILE <name>.io" section; LDraw colours;
                       "0 STEP" lines are Studio's build steps)
    thumbnail.png      a picture of the model
    errorPartList.err  "[]" (no part errors)
    .info              {"version": ..., "total_parts": N, "parts_db_version": ...}
Studio also keeps model2.ldr (every part's shape packed in, BrickLink colours), and newer
files carry instruction layouts (model.ins); Studio writes those itself when it saves. Its
samples include both password-locked and plain zips; this writes a plain one, which Studio
opens (checked by opening a 1,048-part model with 37 steps in Studio, November 2026).
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

INFO_VERSION = "2.25.11_3"      # as written by Studio 2.25 (its Banana sample)
PARTS_DB_VERSION = 200


def model_ldr(model, steps: list[list[int]] | None = None, title: str | None = None) -> str:
    """model.ldr inside the .io: the model's part lines and steps in Studio's wrapper."""
    body = [ln for ln in model.to_ldr(steps=steps).splitlines() if ln.startswith(("1 ", "0 STEP"))]
    lines = [f"0 FILE {model.name}.io", f"0 {title or model.name}", f"0 Name:  {model.name}",
             "0 Author:  ", *body, "0 NOFILE"]
    return "﻿" + "\r\n".join(lines) + "\r\n"


def io_bytes(model, steps: list[list[int]] | None = None, title: str | None = None,
             thumbnail=None) -> bytes:
    """The .io file's bytes. thumbnail: a PIL image (rendered here if not given)."""
    if thumbnail is None:
        from . import instructions, render
        sub = instructions._subset(instructions._scene(model), list(model.parts))
        thumbnail = render.render_real_view(sub, -35, 25, 800, 600)
    png = io.BytesIO()
    thumbnail.save(png, format="PNG")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("model.ldr", model_ldr(model, steps, title))
        z.writestr("thumbnail.png", png.getvalue())
        z.writestr("errorPartList.err", "[]")
        z.writestr(".info", json.dumps({"version": INFO_VERSION, "total_parts": len(model.parts),
                                        "parts_db_version": PARTS_DB_VERSION}, separators=(",", ":")))
    return buf.getvalue()


def write_io(model, path: Path, steps: list[list[int]] | None = None, title: str | None = None,
             thumbnail=None) -> Path:
    path = Path(path)
    path.write_bytes(io_bytes(model, steps, title, thumbnail))
    return path
