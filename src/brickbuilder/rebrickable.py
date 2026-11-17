"""Real-world LEGO catalogue facts from Rebrickable's free downloads.

scripts/fetch_rebrickable.sh downloads the CSV files into data/rebrickable and calls build(),
which writes data/rebrickable_index.json:
  - for each part: its name, and every colour it was really produced in, with how many
    sets it appeared in and the years (from set inventories, plus LEGO element ids)
  - related parts: printed versions, mould variants and alternates
  - colours: name and RGB
Rebrickable colour ids match LDraw colour codes for the usual colours, and its part numbers
mostly match LDraw part numbers; lookup() bridges the common differences (suffix letters,
printed LDraw ids). Data from rebrickable.com.
"""
from __future__ import annotations

import csv
import functools
import gzip
import io
import json
import re
import time
from collections import defaultdict
from pathlib import Path

from . import ldraw

DATA = ldraw.LDRAW_DIR.parent / "rebrickable"
INDEX = ldraw.LDRAW_DIR.parent / "rebrickable_index.json"


def _rows(name: str):
    with gzip.open(DATA / f"{name}.csv.gz", "rt", encoding="utf-8", newline="") as fh:
        yield from csv.DictReader(fh)


def build() -> str:
    """Read the downloaded CSVs and write the compact index. Returns a summary line."""
    t0 = time.time()
    colours = {int(r["id"]): {"name": r["name"], "rgb": r["rgb"], "trans": r["is_trans"] == "True"}
               for r in _rows("colors")}
    names = {r["part_num"]: r["name"] for r in _rows("parts")}
    year = {r["set_num"]: int(r["year"]) for r in _rows("sets") if r["year"].isdigit()}
    inv_set = {r["id"]: r["set_num"] for r in _rows("inventories")}
    seen: dict[str, dict[int, list]] = defaultdict(dict)        # part -> colour -> [sets, y1, y2]
    sets_seen: dict[tuple, set] = defaultdict(set)
    for r in _rows("inventory_parts"):
        if r["is_spare"] == "True":
            continue
        s = inv_set.get(r["inventory_id"])
        if s is None:
            continue
        key = (r["part_num"], int(r["color_id"]))
        if s in sets_seen[key]:
            continue
        sets_seen[key].add(s)
        y = year.get(s)
        rec = seen[r["part_num"]].setdefault(key[1], [0, y, y])
        rec[0] += 1
        if y is not None:
            rec[1] = y if rec[1] is None else min(rec[1], y)
            rec[2] = y if rec[2] is None else max(rec[2], y)
    for r in _rows("elements"):                                 # produced, maybe not yet in a set
        seen[r["part_num"]].setdefault(int(r["color_id"]), [0, None, None])
    related: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    kinds = {"P": "prints", "M": "moulds", "A": "alternates", "T": "patterns"}
    for r in _rows("part_relationships"):
        k = kinds.get(r["rel_type"])
        if not k:
            continue
        child, parent = r["child_part_num"], r["parent_part_num"]
        if k in ("prints", "patterns"):
            related[parent][k].append(child)
            related[child]["print_of"].append(parent)
        else:
            related[parent][k].append(child)
            related[child][k].append(parent)
    parts = {}
    for p in set(names) | set(seen):
        rec = {"name": names.get(p, ""), "colors": {str(c): v for c, v in seen.get(p, {}).items()}}
        rel = related.get(p)
        if rel:
            rec.update({k: sorted(set(v))[:30] for k, v in rel.items()})
        parts[p] = rec
    INDEX.write_text(json.dumps({"colours": colours, "parts": parts}, separators=(",", ":")))
    _load.cache_clear()
    return (f"Rebrickable index: {len(parts)} parts, {len(colours)} colours, "
            f"{sum(len(v) for v in seen.values())} part/colour combinations ({time.time() - t0:.0f}s)")


@functools.lru_cache(maxsize=1)
def _load() -> dict:
    if not INDEX.exists():
        raise FileNotFoundError(str(INDEX))
    return json.loads(INDEX.read_text())


def available() -> bool:
    try:
        _load()
        return True
    except FileNotFoundError:
        return False


_LDRAW_PRINT = re.compile(r"^(.+?)(p[0-9a-z]{2,}|d[0-9]{2,})$")


def lookup(part: str) -> tuple[str | None, dict | None, str]:
    """(rebrickable part number, record, note) for an LDraw part id."""
    parts = _load()["parts"]
    pid = ldraw.normalize_part_id(part)
    if pid in parts:
        return pid, parts[pid], ""
    m = _LDRAW_PRINT.match(pid)
    candidates = []
    if m:
        candidates.append((m.group(1), "printed part: colours are for the plain base part"))
    stripped = re.sub(r"[a-d]$", "", pid)
    if stripped != pid:
        candidates.append((stripped, ""))
    for c in (pid + "a", pid + "b"):
        candidates.append((c, ""))
    for c, note in candidates:
        if c in parts:
            return c, parts[c], note
        s2 = re.sub(r"[a-d]$", "", c)
        if s2 in parts:
            return s2, parts[s2], note
    return None, None, "not in the Rebrickable catalogue"


def colour_name(cid: int | str) -> str:
    c = _load()["colours"].get(str(cid))
    return c["name"] if c else f"colour {cid}"


def colours_of(part: str) -> dict[int, list]:
    """{colour id: [sets, first year, last year]} the part was really produced in."""
    _, rec, _ = lookup(part)
    return {int(c): v for c, v in (rec or {}).get("colors", {}).items()}


def _rgb(cid: int) -> tuple[int, int, int] | None:
    c = _load()["colours"].get(str(cid))
    if not c:
        return None
    h = c["rgb"]
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def nearest_real_colours(part: str, cid: int, n: int = 3) -> list[int]:
    """The colours this part really came in that look closest to colour cid."""
    want = _rgb(cid)
    have = colours_of(part)
    if not want or not have:
        return []
    def dist(c):
        rgb = _rgb(c)
        return sum((a - b) ** 2 for a, b in zip(rgb, want)) if rgb else 1e9
    return sorted(have, key=dist)[:n]


def summary(part: str) -> str:
    """One paragraph of real-world facts about a part, for part_info."""
    rb, rec, note = lookup(part)
    if rec is None:
        return f"Real world: {note}."
    cols = rec.get("colors", {})
    if cols:
        top = sorted(cols.items(), key=lambda kv: -kv[1][0])
        years = [v[1] for v in cols.values() if v[1]] + [v[2] for v in cols.values() if v[2]]
        span = f", {min(years)}-{max(years)}" if years else ""
        names = ", ".join(f"{colour_name(c)} ({v[0]} sets)" for c, v in top[:8])
        more = f" and {len(top) - 8} more" if len(top) > 8 else ""
        line = (f"Real world (Rebrickable {rb}): made in {len(cols)} colour{'s' if len(cols) != 1 else ''}"
                f"{span}: {names}{more}.")
    else:
        line = f"Real world (Rebrickable {rb}): no colour records (rare, promotional or not released)."
    rel = []
    for k, label in (("moulds", "mould variants"), ("alternates", "alternates"), ("print_of", "printed version of")):
        if rec.get(k):
            rel.append(f"{label}: {', '.join(rec[k][:6])}")
    if rel:
        line += " " + "; ".join(rel) + "."
    if note:
        line += f" ({note})"
    return line


def colour_problems(model) -> list[str]:
    """Parts in the model whose colour was never produced for that part."""
    out, done = [], set()
    for p in model.parts.values():
        key = (p.part, p.color)
        if key in done:
            continue
        done.add(key)
        rb, rec, _ = lookup(p.part)
        if rec is None or not rec.get("colors"):
            continue
        if str(p.color) in rec["colors"]:
            continue
        ids = [q.id for q in model.parts.values() if (q.part, q.color) == key]
        near = ", ".join(colour_name(c) for c in nearest_real_colours(p.part, p.color))
        out.append(f"{p.part} ({rec.get('name', '')[:40]}) in {colour_name(p.color)} was never made "
                   f"({len(ids)} in the model, e.g. #{ids[0]}); closest real colours: {near or 'none'}")
    return out


def parts_list(model) -> tuple[str, str]:
    """(Rebrickable import CSV, readable list) for the model's parts."""
    count: dict[tuple[str, int], int] = defaultdict(int)
    for p in model.parts.values():
        count[(p.part, p.color)] += 1
    csv_buf = io.StringIO()
    w = csv.writer(csv_buf, lineterminator="\n")
    w.writerow(["Part", "Color", "Quantity"])
    lines = []
    for (part, col), n in sorted(count.items(), key=lambda kv: (-kv[1], kv[0])):
        rb, rec, _ = lookup(part) if available() else (None, None, "")
        w.writerow([rb or part, col, n])
        name = (rec or {}).get("name") or ldraw.part_title(part) or ""
        lines.append(f"{n:4} x {rb or part:12} {colour_name(col) if available() else col:22} {name}")
    return csv_buf.getvalue(), "\n".join(lines)
