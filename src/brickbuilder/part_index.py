"""A searchable index of every part in the LDraw library.

Title search alone only finds a part if you already know its name. This index stores, for
every part, what a builder searches by:
  - size: footprint in studs and height in plates
  - connectors: studs up / sideways / down, receivers, joints
  - shape: width at four heights (bottom to top), and tags such as round, narrows_upward,
    widens_upward, curved, inverted, dome, cone, wedge, arch, smooth_top, side_studs
  - kind: normal part, printed/stickered variant (with its base part), or obsolete alias

It is built once (a few minutes: every part's geometry is analysed, using all CPU cores)
and saved next to the LDraw library as part_index.json. Rebuild it after updating the
library or the connector detection: `uv run python scripts/build_part_index.py`.
"""
from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from . import ldraw

INDEX_VERSION = 1


def index_path() -> Path:
    return ldraw.LDRAW_DIR.parent / "part_index.json"


# ---------------------------------------------------------------- analysis

_TITLE_TAGS = {
    "curved": "curved", "slope": "slope", "inverted": "inverted", "round": "round",
    "dome": "dome", "cone": "cone", "wedge": "wedge", "arch": "arch", "tile": "tile",
    "bracket": "bracket", "hinge": "hinge", "clip": "clip", "handle": "bar", "bar": "bar",
    "ball": "ball", "socket": "socket", "towball": "ball", "technic": "technic",
    "cylinder": "round", "dish": "dish", "hemisphere": "dome", "turntable": "turntable",
    "jumper": "offset", "rail": "offset", "macaroni": "round", "quarter": "quarter",
    "half": "half", "corner": "corner", "facet": "facet", "panel": "panel",
}
_PRINT = re.compile(r"\b(pattern|sticker)\b", re.I)
_PRINT_ID = re.compile(r"^(.+?)(p[0-9a-z]{2,}|d[0-9]{2,})$")


def _category(title: str, meta_cat: str | None) -> str:
    if meta_cat:
        return meta_cat
    word = title.lstrip("~=_|").split(" ")[0] if title else ""
    return word.capitalize()


def _meta(pid: str) -> tuple[str, str | None, list[str]]:
    """Title, !CATEGORY and !KEYWORDS from the part file header."""
    path = ldraw._find(pid + ".dat")
    title, cat, keys = "", None, []
    if path is None:
        return title, cat, keys
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if i == 0:
                title = line[2:].strip() if line.startswith("0 ") else line
            elif line.startswith("0 !CATEGORY"):
                cat = line[len("0 !CATEGORY"):].strip()
            elif line.startswith("0 !KEYWORDS"):
                keys += [k.strip().lower() for k in line[len("0 !KEYWORDS"):].split(",") if k.strip()]
            elif line.startswith("1 ") or line.startswith("3 ") or line.startswith("4 "):
                break                                    # header is over
    return title, cat, keys


def _shape(pid: str) -> dict:
    """Size, connectors and shape of one part (local frame, LDU, -Y up)."""
    from . import catalog, geometry
    from .model import direction_name
    out: dict = {}
    sx, sz, h = catalog.footprint(pid)
    out["size"] = [sx, sz, h]
    st = geometry.studs(pid)
    dirs = [direction_name(d) for _, d in st]
    out["studs"] = {"up": dirs.count("up"), "side": sum(d not in ("up", "down") for d in dirs),
                    "down": dirs.count("down")}
    out["receivers"] = len(geometry.receivers(pid))
    out["joints"] = sorted({j[0] for j in geometry.joints(pid)})
    pts = np.asarray(geometry.samples(pid), float)
    tags = set()
    if len(pts) >= 8:
        lo, hi = pts.min(0), pts.max(0)
        cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
        top, bottom = lo[1], hi[1]                       # -Y is up: top has the smaller y
        span = max(bottom - top, 1e-6)
        widths = []
        for k in range(4):                               # bands from the bottom up
            b0 = bottom - span * (k + 1) / 4
            b1 = bottom - span * k / 4
            band = pts[(pts[:, 1] >= b0 - 0.5) & (pts[:, 1] <= b1 + 0.5)]
            if len(band) == 0:
                widths.append(0.0)
                continue
            w = 2 * max(np.abs(band[:, 0] - cx).max(), np.abs(band[:, 2] - cz).max()) / 20
            widths.append(round(float(w), 2))
        out["widths"] = widths
        # roundness: a round cross-section leaves the bounding square's corners empty
        mid = pts[(pts[:, 1] >= top + span * 0.25) & (pts[:, 1] <= top + span * 0.75)]
        if len(mid) >= 8:
            rx = max(np.abs(mid[:, 0] - cx).max(), 1e-6)
            rz = max(np.abs(mid[:, 2] - cz).max(), 1e-6)
            corner = (np.abs(mid[:, 0] - cx) > 0.8 * rx) & (np.abs(mid[:, 2] - cz) > 0.8 * rz)
            if corner.mean() < 0.005 and abs(rx - rz) < 2.5:
                tags.add("round")
        nonzero = [w for w in widths if w > 0]
        if len(nonzero) >= 2 and nonzero[0] > 0:
            lo_w, hi_w = nonzero[0], nonzero[-1]
            if hi_w < 0.9 * lo_w and lo_w - hi_w >= 0.3:
                tags.add("narrows_upward")
            elif hi_w > 1.1 * lo_w and hi_w - lo_w >= 0.3:
                tags.add("widens_upward")
    if out["studs"]["side"]:
        tags.add("side_studs")
    if out["studs"]["down"]:
        tags.add("down_studs")
    if not out["studs"]["up"]:
        tags.add("smooth_top")
    if not out["receivers"]:
        tags.add("no_underside")
    out["tags"] = sorted(tags)
    return out


def _analyse(pid: str) -> dict | None:
    try:
        title, cat, keys = _meta(pid)
        if not title:
            return None
        rec = {"id": pid, "title": title, "category": _category(title, cat), "keywords": keys}
        if title.startswith("~Moved to") or title.startswith("="):
            rec["kind"] = "alias"
            return rec
        if title.startswith("~") or title.startswith("_"):
            rec["kind"] = "obsolete"
        elif _PRINT.search(title):
            rec["kind"] = "print"
            m = _PRINT_ID.match(pid)
            if m:
                rec["base"] = m.group(1)
            return rec                                   # shape is filled in from the base part
        else:
            rec["kind"] = "part"
        rec.update(_shape(pid))
        words = set(re.findall(r"[a-z]+", title.lower()))
        rec["tags"] = sorted(set(rec.get("tags", [])) | {t for w, t in _TITLE_TAGS.items() if w in words})
        return rec
    except Exception as e:                               # a broken part file must not stop the build
        return {"id": pid, "title": "", "kind": "error", "error": str(e)[:200]}


def build(workers: int | None = None, progress=print) -> Path:
    """Analyse every part in the library and write the index. Returns its path."""
    parts = sorted(f[:-4].lower() for f in os.listdir(ldraw.LDRAW_DIR / "parts") if f.lower().endswith(".dat"))
    t0 = time.time()
    records: dict[str, dict] = {}
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i, rec in enumerate(pool.map(_analyse, parts, chunksize=64)):
            if rec:
                records[rec["id"]] = rec
            if progress and (i + 1) % 2500 == 0:
                progress(f"  {i + 1}/{len(parts)} parts ({time.time() - t0:.0f}s)")
    # printed variants share their base part's shape
    for rec in records.values():
        if rec.get("kind") == "print":
            base = records.get(rec.get("base", ""))
            if base and "size" in base:
                for k in ("size", "studs", "receivers", "joints", "widths"):
                    if k in base:
                        rec[k] = base[k]
                rec["tags"] = sorted(set(base.get("tags", [])) | {"printed"})
            else:
                try:
                    rec.update(_shape(rec["id"]))
                    rec["tags"] = sorted(set(rec.get("tags", [])) | {"printed"})
                except Exception:
                    pass
    data = {"version": INDEX_VERSION, "built": time.strftime("%Y-%m-%d %H:%M"), "parts": records}
    path = index_path()
    path.write_text(json.dumps(data, separators=(",", ":")))
    if progress:
        progress(f"Indexed {len(records)} parts in {time.time() - t0:.0f}s -> {path}")
    _load.cache_clear()
    return path


# ---------------------------------------------------------------- search

import functools  # noqa: E402


@functools.lru_cache(maxsize=1)
def _load() -> dict:
    path = index_path()
    if not path.exists():
        raise FileNotFoundError(str(path))
    data = json.loads(path.read_text())
    if data.get("version") != INDEX_VERSION:
        raise FileNotFoundError(f"{path} is from an older version; rebuild it")
    return data["parts"]


def available() -> bool:
    try:
        _load()
        return True
    except FileNotFoundError:
        return False


def record(pid: str) -> dict | None:
    try:
        return _load().get(ldraw.normalize_part_id(pid))
    except FileNotFoundError:
        return None


# categories that are not general building elements: ranked after them
_DEMOTE = ("minifig", "animal", "figure", "duplo", "fabuland", "znap", "belville", "scala",
           "bionicle", "constraction", "electric", "train", "sticker", "string", "hose",
           "baseplate", "car", "boat", "aircraft", "jack", "homemaker", "magnet", "tyre",
           "wheel", "flag", "plant", "rock", "food", "container", "tool")


# words a builder uses -> index tags
_SYNONYMS = {
    "snot": "side_studs", "sideways": "side_studs", "smooth": "smooth_top", "flat": "smooth_top",
    "circular": "round", "cylinder": "round", "cylindrical": "round", "tapered": "narrows_upward",
    "taper": "narrows_upward", "flare": "widens_upward", "flared": "widens_upward",
    "upside": "inverted", "joint": "ball", "printed": "printed", "print": "printed",
}


def _range(spec, name: str) -> tuple[float, float] | None:
    if spec is None or spec == "":
        return None
    if isinstance(spec, (int, float)):
        return float(spec), float(spec)
    m = re.fullmatch(r"\s*([\d.]+)\s*(?:-\s*([\d.]+))?\s*", str(spec))
    if not m:
        raise ValueError(f"{name} must be a number or a range like 2-4, not '{spec}'")
    a = float(m.group(1))
    return a, float(m.group(2)) if m.group(2) else a


def search(query: str = "", footprint: str | None = None, height=None, tags: list[str] | None = None,
           joints: list[str] | None = None, bottom_width=None, top_width=None,
           include_prints: bool = False, limit: int = 25) -> list[dict]:
    """Find parts by words and by shape. footprint 'AxB' matches either orientation;
    height (plates), bottom_width / top_width (studs) take a number or a range '2-4'."""
    parts = _load()
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower())]
    want_tags = set(tags or [])
    words_left = []
    for w in words:
        if w in _SYNONYMS:
            want_tags.add(_SYNONYMS[w])
        else:
            words_left.append(w)
    if "printed" in want_tags:
        include_prints = True
    fp = None
    if footprint:
        m = re.fullmatch(r"\s*(\d+)\s*[xX*]\s*(\d+)\s*", footprint)
        if not m:
            raise ValueError("footprint must look like '2x4'")
        fp = sorted((int(m.group(1)), int(m.group(2))))
    hr, bw, tw = _range(height, "height"), _range(bottom_width, "bottom_width"), _range(top_width, "top_width")
    hits = []
    for rec in parts.values():
        kind = rec.get("kind")
        if kind in ("alias", "error") or (kind == "obsolete" and "obsolete" not in words_left):
            continue
        if kind == "print" and not include_prints:
            continue
        if "size" not in rec:
            continue
        if fp and sorted(rec["size"][:2]) != fp:
            continue
        if hr and not hr[0] <= rec["size"][2] <= hr[1]:
            continue
        rtags = set(rec.get("tags", []))
        if want_tags - rtags:
            continue
        if joints and not set(joints) & set(rec.get("joints", [])):
            continue
        w = rec.get("widths") or []
        if bw and (not w or not bw[0] - 0.25 <= w[0] <= bw[1] + 0.25):
            continue
        if tw and (not w or not tw[0] - 0.25 <= w[-1] <= tw[1] + 0.25):
            continue
        title = rec["title"].lower()
        title_words = set(re.findall(r"[a-z0-9]+", title))
        score = 0.0
        ok = True
        for word in words_left:
            if word in title_words or word == rec["id"]:
                score += 3
            elif word in rec.get("keywords", []) or word == rec.get("category", "").lower():
                score += 2
            elif word in rtags or any(word in t for t in title_words):
                score += 1
            else:
                ok = False
                break
        if not ok:
            continue
        score -= len(title) / 200                        # prefer plain, short titles
        if kind == "print":
            score -= 1
        # building elements first: figures, animals, accessories and other systems last
        cat = rec.get("category", "").lower()
        if any(cat.startswith(c) for c in _DEMOTE) and not any(w in cat for w in words_left):
            score -= 5
        if rec.get("receivers") and (rec.get("studs", {}).get("up") or rec.get("studs", {}).get("side")):
            score += 0.5
        hits.append((score, rec))
    hits.sort(key=lambda sr: -sr[0])
    return [r for _, r in hits[:max(1, min(int(limit), 200))]]


def describe(rec: dict) -> str:
    """One line: id, size, profile, tags, title."""
    sx, sz, h = rec.get("size", ["?", "?", "?"])
    w = rec.get("widths")
    prof = f" w {w[0]:g}->{w[-1]:g}" if w else ""
    st = rec.get("studs", {})
    conn = []
    if st.get("side"):
        conn.append(f"{st['side']} side studs")
    if rec.get("joints"):
        conn.append("joints " + "/".join(rec["joints"]))
    tags = [t for t in rec.get("tags", []) if t not in ("side_studs",)]
    return (f"{rec['id']:12} {sx}x{sz} h{h}{prof}  [{', '.join(tags)}]"
            f"{'  ' + '; '.join(conn) if conn else ''}  {rec['title']}")
