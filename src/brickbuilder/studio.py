"""BrickLink Studio .io files, written directly (no Studio needed).

A .io file is a zip. Studio's own sample files show the layout:
    model.ldr          the model as LDraw (one "0 FILE <name>.io" section; LDraw colours;
                       "0 STEP" lines are Studio's build steps)
    thumbnail.png      a picture of the model
    errorPartList.err  "[]" (no part errors)
    .info              {"version": ..., "total_parts": N, "parts_db_version": ...}
    model2.ldr         the same model with BrickLink colour ids and part numbers. The
                       BrickLink website reads this copy for a Gallery design's parts list:
                       without it, LDraw codes were read as BrickLink ids (Tan 19 became
                       Trans-Yellow), and LDraw names with a letter (3069b) were dropped.
                       After the model it packs in every part's shape (each part, subpart and
                       primitive as its own "0 FILE" section), as Studio's own files do: the
                       Gallery's "View Instructions" viewer draws from these, and showed an
                       empty window without them. Saving in Studio does not add them.
Newer files also carry instruction layouts (model.ins), which Studio writes itself. Its
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


def model_ldr(model, steps: list[list[int]] | None = None, title: str | None = None,
              bricklink_colours: bool = False) -> str:
    """model.ldr inside the .io: the model's part lines and steps in Studio's wrapper.
    bricklink_colours: write BrickLink colour ids instead of LDraw codes, as in model2.ldr -
    the copy the BrickLink website reads for a Gallery design's parts list (with LDraw codes
    there, Tan 19 reads as BrickLink's Trans-Yellow 19)."""
    body = [ln for ln in model.to_ldr(steps=steps).splitlines() if ln.startswith(("1 ", "0 STEP"))]
    if bricklink_colours:
        # BrickLink's colour ids, and BrickLink's part numbers too: the website matches part
        # names in this copy to its catalogue directly, and dropped the parts whose LDraw
        # names carry a letter (3069b, 3070b, 3062b...) that BrickLink files without it.
        from .bricklink import COLOURS, bricklink_part
        out, refs = [], {}
        for ln in body:
            if ln.startswith("1 "):
                bits = ln.split(" ")
                code = int(bits[1])
                if code not in COLOURS:
                    raise ValueError(f"no BrickLink colour id known for LDraw colour {code}")
                bits[1] = str(COLOURS[code])
                ours = bits[-1][:-4]
                bits[-1] = bricklink_part(ours) + ".dat"
                refs.setdefault(bits[-1], ours)
                ln = " ".join(bits)
            out.append(ln)
        body = out
    lines = [f"0 FILE {model.name}.io", f"0 {title or model.name}", f"0 Name:  {model.name}",
             "0 Author:  ", *body, "0 NOFILE"]
    if bricklink_colours:
        lines += part_sections(refs)
    return "﻿" + "\r\n".join(lines) + "\r\n"


def part_sections(refs: dict[str, str]) -> list[str]:
    """Every part's shape, as Studio packs them into model2.ldr: one "0 FILE <name>" section per
    part, subpart and primitive it uses, named by the bare file name (s\\ and 48\\ dropped, as
    Studio does), with colour 16 written -1 and 24 written -2, comments and BFC lines left out.
    The Gallery's 3D step viewer draws from these; without them it shows an empty window.
    refs: the name each part goes by in the model -> its LDraw file (3069.dat -> 3069b)."""
    from . import ldraw
    out, done = [], set()
    todo = [(name, src) for name, src in refs.items()]
    while todo:
        name, src = todo.pop(0)
        if name.lower() in done:
            continue
        done.add(name.lower())
        path = ldraw._find(src if src.lower().endswith(".dat") else src + ".dat")
        if path is None:
            raise ValueError(f"no LDraw file for {src}")
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        title = lines[0][2:].strip() if lines and lines[0].startswith("0 ") else name
        body = [f"0 FILE {name}", f"0 {title}", f"0 Name:  {name[:-4]}", "0 Author:  "]
        for ln in lines:
            bits = ln.split()
            if not bits or bits[0] not in ("1", "2", "3", "4", "5"):
                continue
            bits[1] = {"16": "-1", "24": "-2"}.get(bits[1], bits[1])
            if bits[0] == "1":
                sub = " ".join(bits[14:]).replace("\\", "/")
                base = sub.rsplit("/", 1)[-1].lower()
                bits = bits[:14] + [base]
                if base not in done:
                    todo.append((base, sub))
            body.append(" ".join(bits))
        out += body + ["0 NOFILE"]
    return out


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
        z.writestr("model2.ldr", model_ldr(model, steps, title, bricklink_colours=True))
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
