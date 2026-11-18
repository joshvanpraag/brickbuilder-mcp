"""Building instructions for a model: steps, step pictures, and two PDFs.

- A phone PDF: one page per step, in order (cover, parts list, steps, back cover).
- A booklet PDF to print and fold: US letter sheets, printed on both sides (the printer's
  normal "flip on long edge" setting), stacked, stapled across the middle and folded in half.
  Each half sheet is one page (half a letter page, landscape). The top half of the outside
  sheet is the cover. Opened, the booklet shows two pages one above the other: read the top
  one, then the bottom one, then flip the bottom page up... the pages are placed on the sheets
  so that this all comes out in order once folded (see `booklet_order`).

Steps go bottom to top, one level of the model at a time. Levels with many parts are split
round the building (each chunk is a stretch of the walls), and levels with very few parts
are merged with the next, so every step has a sensible number of new parts.
"""
from __future__ import annotations

import math
from collections import Counter
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import bricklink, geometry, ldraw, render

DPI = 150
PAGE_W, PAGE_H = int(8.5 * DPI), int(5.5 * DPI)      # half a letter sheet, landscape
SHEET_W, SHEET_H = int(8.5 * DPI), int(11 * DPI)     # a letter sheet, portrait
INK = (35, 38, 46)
SOFT = (110, 116, 128)
PAPER = (255, 255, 255)
PANEL = (240, 242, 245)
VIEW = (-35, 28)                                       # front-left, from a little above


def _font(size: int, bold: bool = False):
    for name in (("arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else ("arial.ttf", "DejaVuSans.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


# ------------------------------------------------------------------------------- steps

def plan_steps(model, max_parts: int = 40, min_parts: int = 6) -> list[list[int]]:
    """Part ids per step, bottom to top. A level with more than max_parts is split into
    stretches round the building (by angle about its centre); levels with fewer than
    min_parts join the next level."""
    by_level: dict[int, list[int]] = {}
    for pid, p in model.parts.items():
        by_level.setdefault(p.y, []).append(pid)
    if not by_level:
        return []
    cx = np.mean([model.geometry(i).pos[0] for i in model.parts])
    cz = np.mean([model.geometry(i).pos[2] for i in model.parts])
    steps: list[list[int]] = []
    carry: list[int] = []
    for y in sorted(by_level):
        ids = carry + by_level[y]
        carry = []
        if len(ids) < min_parts and y != max(by_level):
            carry = ids
            continue
        if len(ids) <= max_parts:
            steps.append(ids)
            continue
        ang = {i: math.atan2(model.geometry(i).pos[2] - cz, model.geometry(i).pos[0] - cx) for i in ids}
        ids.sort(key=lambda i: ang[i])
        k = math.ceil(len(ids) / max_parts)
        size = math.ceil(len(ids) / k)
        steps += [ids[j:j + size] for j in range(0, len(ids), size)]
    if carry:
        steps.append(carry)
    return steps


# ------------------------------------------------------------------------------- pictures

def _scene(model):
    """Real part polygons and lines, with the part id of every polygon and line."""
    flip = np.array([1.0, -1.0, 1.0])
    P, PC, PI, L, LC, LI = [], [], [], [], [], []
    for pid, p in model.parts.items():
        g = model.geometry(pid)
        mesh = geometry.load(p.part)
        if len(mesh.polys):
            P.append((mesh.polys @ g.matrix.T + g.pos) * flip)
            PC.append(np.where(mesh.poly_colours == 16, p.color, mesh.poly_colours))
            PI.append(np.full(len(mesh.polys), pid))
        if len(mesh.lines):
            L.append((mesh.lines @ g.matrix.T + g.pos) * flip)
            LC.append(np.where(mesh.line_colours == 16, p.color, mesh.line_colours))
            LI.append(np.full(len(mesh.lines), pid))
    cat = lambda xs, shape: np.concatenate(xs) if xs else np.zeros(shape)
    return (cat(P, (0, 4, 3)), cat(PC, (0,)).astype(int), cat(PI, (0,)).astype(int),
            cat(L, (0, 2, 3)), cat(LC, (0,)).astype(int), cat(LI, (0,)).astype(int))


def _subset(scene, ids):
    P, PC, PI, L, LC, LI = scene
    keep = np.isin(PI, ids)
    keep_l = np.isin(LI, ids)
    return P[keep], PC[keep], L[keep_l], LC[keep_l], PI[keep]


def _frame(scene):
    P = scene[0]
    lo, hi = P.reshape(-1, 3).min(0), P.reshape(-1, 3).max(0)
    return np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])


def step_picture(scene, shown, new, width, height, frame=None, view=VIEW) -> Image.Image:
    """Everything built so far, the parts of this step in full colour and the rest faded."""
    sub = _subset(scene, np.fromiter(shown, dtype=np.int64))
    ghost = set(shown) - set(new)
    return render.render_real_view(sub, view[0], view[1], width, height, ghost=ghost, frame=frame)


@lru_cache(maxsize=512)
def part_picture(part: str, color: int, size: int = 110) -> Image.Image:
    """A small picture of one part, for the parts boxes."""
    from .model import Model
    m = Model("thumb")
    m.add(part, color, 0, 0, 0, 0)
    sc = _scene(m)
    img = render.render_real_view((sc[0], sc[1], sc[3], sc[4], sc[2]), -35, 30, size, size)
    # make the background white so it sits on the page
    a = np.asarray(img).astype(int)
    bg = np.all(np.abs(a - render.BACKGROUND.astype(int)) < 6, axis=2)
    a[bg] = 255
    return Image.fromarray(a.astype(np.uint8))


# ------------------------------------------------------------------------------- pages

def _parts_box(draw, page, items, box, thumb=78):
    """Draw part pictures with 'Nx' under each, packed left to right, top to bottom."""
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=14, fill=PANEL)
    f = _font(20, bold=True)
    cell_w, cell_h = thumb + 22, thumb + 30
    cols = max(1, (x1 - x0 - 16) // cell_w)
    for k, ((part, color), n) in enumerate(items):
        r, c = divmod(k, cols)
        px, py = x0 + 10 + c * cell_w, y0 + 10 + r * cell_h
        if py + cell_h > y1:
            draw.text((px, py), "...", font=f, fill=INK)
            break
        page.paste(part_picture(part, color, thumb), (px + 8, py))
        draw.text((px + 8 + thumb // 2, py + thumb + 12), f"{n}x", font=f, fill=INK, anchor="mm")


def _counts(model, ids):
    c = Counter((model.parts[i].part, model.parts[i].color) for i in ids)
    return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))


def make_pages(model, title: str, steps: list[list[int]], subtitle: str = "") -> list[Image.Image]:
    """Cover, parts list pages, one page per step, back cover."""
    scene = _scene(model)
    frame = _frame(scene)
    all_ids = list(model.parts)
    pages = []

    # cover
    page = Image.new("RGB", (PAGE_W, PAGE_H), PAPER)
    draw = ImageDraw.Draw(page)
    pic = render.render_real_view(_subset(scene, np.array(all_ids)), VIEW[0], VIEW[1], PAGE_W - 80, PAGE_H - 190)
    page.paste(pic, (40, 150))
    draw.text((PAGE_W // 2, 56), title, font=_font(52, bold=True), fill=INK, anchor="mm")
    if subtitle:
        draw.text((PAGE_W // 2, 112), subtitle, font=_font(24), fill=SOFT, anchor="mm")
    pages.append(page)

    # parts list
    items = _counts(model, all_ids)
    per_page = 6 * 3
    for start in range(0, len(items), per_page):
        page = Image.new("RGB", (PAGE_W, PAGE_H), PAPER)
        draw = ImageDraw.Draw(page)
        draw.text((40, 30), "Parts" + (" (continued)" if start else ""), font=_font(34, bold=True), fill=INK)
        chunk = items[start:start + per_page]
        cw, ch = (PAGE_W - 80) // 6, (PAGE_H - 110) // 3
        for k, ((part, color), n) in enumerate(chunk):
            r, c = divmod(k, 6)
            x, y = 40 + c * cw, 90 + r * ch
            page.paste(part_picture(part, color, 120), (x + (cw - 120) // 2, y))
            draw.text((x + cw // 2, y + 138), f"{n}x  {bricklink.bricklink_part(part)}", font=_font(20, bold=True),
                      fill=INK, anchor="mm")                  # BrickLink's number, to match the order
            draw.text((x + cw // 2, y + 164), _colour_label(color), font=_font(17), fill=SOFT, anchor="mm")
        pages.append(page)

    # steps
    total = len(steps)
    for k in range(total):
        page = Image.new("RGB", (PAGE_W, PAGE_H), PAPER)
        draw = ImageDraw.Draw(page)
        shown = [i for s in steps[:k + 1] for i in s]
        pic = step_picture(scene, shown, steps[k], PAGE_W - 330, PAGE_H - 30, frame)
        page.paste(pic, (320, 15))
        draw.text((34, 18), str(k + 1), font=_font(80, bold=True), fill=INK)
        draw.text((38, 112), f"of {total}", font=_font(20), fill=SOFT)
        _parts_box(draw, page, _counts(model, steps[k]), (24, 150, 312, PAGE_H - 20))
        pages.append(page)

    # back cover: the finished model from behind
    page = Image.new("RGB", (PAGE_W, PAGE_H), PAPER)
    draw = ImageDraw.Draw(page)
    pic = render.render_real_view(_subset(scene, np.array(all_ids)), 145, 28, PAGE_W - 80, PAGE_H - 120)
    page.paste(pic, (40, 90))
    draw.text((PAGE_W // 2, 50), f"{title}: {len(model.parts)} parts, {total} steps", font=_font(28, bold=True),
              fill=INK, anchor="mm")
    pages.append(page)
    return pages


def _colour_label(code: int) -> str:
    try:
        from . import rebrickable
        if rebrickable.available():
            return rebrickable.colour_name(code)
    except Exception:  # noqa: BLE001
        pass
    c = ldraw.colours().get(int(code))
    return c.name.replace("_", " ") if c else f"colour {code}"


# ------------------------------------------------------------------------------- PDFs

def write_phone_pdf(pages: list[Image.Image], path: Path) -> None:
    pages[0].save(path, save_all=True, append_images=pages[1:], resolution=DPI)


def booklet_order(n_content: int) -> tuple[int, list[tuple[tuple[int, int], tuple[int, int]]]]:
    """How pages go onto sheets for the fold-in-half booklet.

    Returns (number of sheets, per sheet ((front top, front bottom), (back top, back bottom)))
    as content indexes (0 = cover, last = back cover; indexes past the content are blank,
    placed just before the back cover).

    Folded, the booklet opens to two pages one above the other: the top one is read first.
    The cover is the top half of the outside sheet's front. Physical page q (1..P, P = 4 x
    sheets) shows content: q = 1 the cover, q = P the back cover, odd q the content q - 2
    (top of a spread), even q the content q (bottom of a spread). Sheet i from the outside
    carries pages 2i + 1 (front top), P - 2i (front bottom), and on the back, for printing
    with "flip on short edge", P - 2i - 1 (top) and 2i + 2 (bottom); for the usual "flip on
    long edge" the back is turned upside down, which `write_booklet_pdf` does."""
    sheets = max(1, math.ceil(n_content / 4))
    P = 4 * sheets

    def content_of(q: int) -> int:
        if q == 1:
            return 0
        if q == P:
            return P - 1
        return q - 2 if q % 2 else q

    out = []
    for i in range(sheets):
        out.append(((content_of(2 * i + 1), content_of(P - 2 * i)),
                    (content_of(P - 2 * i - 1), content_of(2 * i + 2))))
    return sheets, out


def write_booklet_pdf(pages: list[Image.Image], path: Path) -> int:
    """Lay the pages out on letter sheets for printing both sides (flip on long edge),
    stapling across the middle and folding in half. Returns the number of sheets."""
    sheets, order = booklet_order(len(pages))
    P = 4 * sheets
    blank = Image.new("RGB", (PAGE_W, PAGE_H), PAPER)
    content = pages[:-1] + [blank] * (P - len(pages)) + pages[-1:]   # blanks before the back cover
    out = []
    for (ft, fb), (bt, bb) in order:
        front = Image.new("RGB", (SHEET_W, SHEET_H), PAPER)
        front.paste(content[ft], (0, 0))
        front.paste(content[fb], (0, PAGE_H))
        back = Image.new("RGB", (SHEET_W, SHEET_H), PAPER)
        back.paste(content[bt], (0, 0))
        back.paste(content[bb], (0, PAGE_H))
        back = back.rotate(180)                     # printed with the usual "flip on long edge"
        for side in (front, back):
            d = ImageDraw.Draw(side)                # a faint fold mark in the margins
            for x0 in (0, SHEET_W - 30):
                d.line([(x0, PAGE_H), (x0 + 30, PAGE_H)], fill=(200, 200, 200), width=2)
        out += [front, back]
    out[0].save(path, save_all=True, append_images=out[1:], resolution=DPI)
    return sheets


def export(model, out_dir: Path, title: str, subtitle: str = "", max_parts: int = 40) -> dict:
    """Write <name>_instructions_phone.pdf and <name>_instructions_booklet.pdf."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    steps = plan_steps(model, max_parts=max_parts)
    pages = make_pages(model, title, steps, subtitle)
    base = title.lower().replace(" ", "_")
    phone = out_dir / f"{base}_instructions_phone.pdf"
    booklet = out_dir / f"{base}_instructions_booklet.pdf"
    write_phone_pdf(pages, phone)
    sheets = write_booklet_pdf(pages, booklet)
    return {"phone": str(phone), "booklet": str(booklet), "steps": len(steps), "pages": len(pages),
            "sheets": sheets}
