"""Connection points of LDraw parts from the LDCad shadow library.

LDCad (an LDraw editor by Roland Melkert) keeps a "shadow library": for each part or
primitive, a list of its connection points ("snaps") as LDraw meta lines. They're licensed
CC BY-SA 4.0 and downloaded by scripts/fetch_ldcad_snaps.sh into data/ldcad_shadow.

Snap kinds used here:
  SNAP_CYL   a cylinder: studs, anti-studs, bars, pins, pin holes, axles, axle holes.
             gender M (sticks out) or F (hole); secs = sections "shape radius length",
             shape R round, S stud-ish round, A axle (cross), L/_L other; the cylinder
             starts at pos and runs along the snap's -Y (or is centred on pos).
  SNAP_CLP   a clip gripping a bar of `radius`, `length` long, axis along Y.
  SNAP_FGR   hinge fingers along Y: `seq` finger lengths, alternating with gaps.
  SNAP_GEN   a generic connector, usually a sphere (ball joints): `bounding=sph r`.
  SNAP_INCL  include another file's snaps at pos/ori (optionally on a grid).
  SNAP_CLEAR forget the snaps inherited from sub-files (all, or one ID).
A part inherits the snaps of every sub-file it uses (so stud.dat gives every stud),
transformed by that sub-file's placement, before its own shadow lines apply.

Positions are LDU in the part's local frame (-Y up), like everything in LDraw.
"""
from __future__ import annotations

import functools
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import ldraw

SHADOW_DIR = Path(os.environ.get("LDCAD_SHADOW_DIR", ldraw.LDRAW_DIR.parent / "ldcad_shadow"))
_MAX_DEPTH = 12


def available() -> bool:
    return (SHADOW_DIR / "p").is_dir() and (SHADOW_DIR / "parts").is_dir()


@dataclass
class Snap:
    """One connection point. `frame` columns are the snap's local X, Y, Z axes; its
    axis (cylinder, clip, finger) is frame[:, 1] (Y)."""
    type: str                      # cyl | clp | fgr | gen
    gender: str                    # M | F ('' for clips)
    pos: np.ndarray
    frame: np.ndarray
    params: dict = field(default_factory=dict)
    id: str = ""
    group: str = ""

    def moved(self, rot: np.ndarray, off: np.ndarray) -> "Snap":
        return Snap(self.type, self.gender, rot @ self.pos + off, rot @ self.frame, self.params, self.id, self.group)

    @property
    def axis(self) -> np.ndarray:
        return self.frame[:, 1]


_META = re.compile(r"0\s+!LDCAD\s+(SNAP_\w+)\s*(.*)", re.I)
_ARG = re.compile(r"\[(\w+)=([^\]]*)\]")


def _shadow_lines(name: str) -> list[tuple[str, dict]]:
    """The snap meta lines of one file's shadow (empty if it has none)."""
    name = name.strip().lower().replace("\\", "/")
    for sub in ("parts", "p"):
        path = (SHADOW_DIR / sub / name).resolve()
        if not path.is_relative_to(SHADOW_DIR.resolve()):
            return []
        if path.exists():
            out = []
            with open(path, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    m = _META.match(line.strip())
                    if m:
                        args = {k.lower(): v.strip() for k, v in _ARG.findall(m.group(2))}
                        out.append((m.group(1).upper(), args))
            return out
    return []


def _subfiles(name: str) -> list[tuple[str, np.ndarray, np.ndarray]]:
    """The type-1 (sub-file) lines of an LDraw file: (name, rotation, offset)."""
    path = ldraw._find(name)
    if path is None:
        return []
    out = []
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            tok = line.split()
            if len(tok) >= 15 and tok[0] == "1":
                vals = list(map(float, tok[2:14]))
                out.append((" ".join(tok[14:]), np.array(vals[3:]).reshape(3, 3), np.array(vals[:3])))
    return out


def _vec(s: str | None, n: int, default) -> np.ndarray:
    if not s:
        return np.array(default, float)
    vals = [float(v) for v in s.split()]
    return np.array(vals[:n], float) if len(vals) >= n else np.array(default, float)


def _grid(spec: str | None) -> list[np.ndarray]:
    """Offsets in the snap's own frame for a grid: 2D [grid=[C] nx [C] nz sx sz] (X/Z
    plane) or 3D [grid=[C] nx [C] ny [C] nz sx sy sz]. C centres that axis's copies."""
    if not spec:
        return [np.zeros(3)]
    tok = spec.split()
    numbers = [t for t in tok if t.upper() != "C"]
    dims = len(numbers) // 2                          # 4 numbers: X/Z grid, 6: X/Y/Z grid
    if dims not in (2, 3) or len(numbers) != 2 * dims:
        return [np.zeros(3)]
    counts, centred, steps = [], [], []
    pending_c = False
    try:
        for t in tok:
            if t.upper() == "C":
                pending_c = True
            elif len(counts) < dims:
                counts.append(int(float(t)))
                centred.append(pending_c)
                pending_c = False
            else:
                steps.append(float(t))
    except ValueError:
        return [np.zeros(3)]
    if dims == 2:                                     # 2D: X and Z
        counts.insert(1, 1)
        centred.insert(1, False)
        steps.insert(1, 0.0)
    if len(counts) != 3 or len(steps) != 3:
        return [np.zeros(3)]
    axes = []
    for n, c, s in zip(counts, centred, steps):
        n = max(n, 1)
        axes.append([(k - (n - 1) / 2) * s if c else k * s for k in range(n)])
    return [np.array([x, y, z]) for z in axes[2] for y in axes[1] for x in axes[0]]


def _secs(spec: str) -> list[tuple[str, float, float]]:
    tok = spec.split()
    out = []
    for k in range(0, len(tok) - 2, 3):
        try:
            out.append((tok[k].upper(), float(tok[k + 1]), float(tok[k + 2])))
        except ValueError:
            break
    return out


def _own(meta: str, a: dict, depth: int) -> list[Snap]:
    """Snaps defined by one shadow meta line (an INCL resolves its target)."""
    pos = _vec(a.get("pos"), 3, [0, 0, 0])
    ori = _vec(a.get("ori"), 9, np.eye(3).ravel()).reshape(3, 3)
    offsets = _grid(a.get("grid"))
    out: list[Snap] = []
    if meta == "SNAP_INCL":
        ref = a.get("ref", "")
        if not ref:
            return []
        inner = resolve_file(ref, depth + 1)
        for off in offsets:
            o = pos + ori @ off
            out += [s.moved(ori, o) for s in inner]
        return out
    kind = {"SNAP_CYL": "cyl", "SNAP_CLP": "clp", "SNAP_FGR": "fgr", "SNAP_GEN": "gen"}.get(meta)
    if not kind:
        return []
    params = dict(a)
    if kind == "cyl":
        params["secs"] = _secs(a.get("secs", ""))
    gender = a.get("gender", a.get("genderofs", "")).upper()[:1]
    for off in offsets:
        out.append(Snap(kind, gender, pos + ori @ off, ori.copy(), params, a.get("id", ""), a.get("group", "")))
    return out


@functools.lru_cache(maxsize=16384)
def _resolve_cached(name: str, depth: int) -> tuple:
    inherited: list[Snap] = []
    if depth < _MAX_DEPTH:
        for sub, rot, off in _subfiles(name):
            inherited += [s.moved(rot, off) for s in resolve_file(sub, depth + 1)]
    own: list[Snap] = []
    for meta, a in _shadow_lines(name):
        if meta == "SNAP_CLEAR":
            cid = a.get("id", "")
            inherited = [s for s in inherited if cid and s.id != cid]
        else:
            own += _own(meta, a, depth)
    return tuple(inherited + own)


def resolve_file(name: str, depth: int = 0) -> list[Snap]:
    name = name.strip().lower().replace("\\", "/")
    if not name.endswith(".dat"):
        name += ".dat"
    return list(_resolve_cached(name, depth))


def part_snaps(part: str) -> list[Snap]:
    """Every connection point of a part, in its local frame."""
    if not available():
        return []
    out, seen = [], set()
    for s in resolve_file(ldraw.normalize_part_id(part) + ".dat"):
        key = (s.type, s.gender, *np.round(s.pos, 1), *np.round(s.axis, 2),   # direction matters: a pin has two halves
               str(s.params.get("secs") or s.params.get("bounding") or s.params.get("radius")))
        if key not in seen:                       # the same connector included twice
            seen.add(key)
            out.append(s)
    return out


# ---------------------------------------------------------------- classification

def classify(s: Snap) -> str:
    """A plain name for a snap: stud, antistud, bar, clip, pin, pin_hole, axle, axle_hole,
    finger, ball, ball_socket, or other."""
    if s.type == "clp":
        return "clip"
    if s.type == "fgr":
        return "finger"
    if s.type == "gen":
        if "sph" in s.params.get("bounding", ""):
            return "ball" if s.gender == "M" else "ball_socket"
        return "other"
    secs = s.params.get("secs") or []
    if not secs:
        return "other"
    shapes = {sh for sh, _, _ in secs}
    radius = max(secs, key=lambda sec: sec[2])[1]          # radius of the longest section
    total = sum(length for _, _, length in secs)
    male = s.gender == "M"
    if "A" in shapes:
        return "axle" if male else "axle_hole"
    if male:
        if max(r for _, r, _ in secs) <= 4.5:
            return "bar"
        if total <= 4.5 and 5.5 <= radius <= 6.5:
            return "stud"
        return "pin" if 5.5 <= radius <= 6.6 and total >= 8 else "other"
    if radius <= 4.5:
        return "bar_hole"
    if secs[0][0] == "S" or (len(secs) == 1 and secs[0][2] <= 4.5):
        return "antistud"
    # a brick's underside: one plain round section, closed at one end, where studs go in.
    # Technic pin holes go right through (centred) or have a collar recess (more sections).
    centred = str(s.params.get("center", "")).lower() == "true"
    if len(secs) == 1 and not centred and s.params.get("caps", "one") == "one":
        return "antistud"
    return "pin_hole"


def summary(part: str) -> dict[str, int]:
    """How many of each connector a part has, e.g. {'stud': 4, 'antistud': 2}."""
    out: dict[str, int] = {}
    for s in part_snaps(part):
        k = classify(s)
        out[k] = out.get(k, 0) + 1
    return out


# ---------------------------------------------------------------- shape check

# largest allowed distance from the joint centre to the part's surface (LDU)
NEAR = {"bar": 6.5, "pin": 9, "axle": 9, "clip": 8, "ball": 11, "socket": 12, "large_ball": 16,
        "large_socket": 16, "finger_m": 12, "finger_f": 12, "pin_hole": 9.5, "axle_hole": 9.5,
        "bar_hole": 6.5}


@functools.lru_cache(maxsize=512)
def _tris(pid):
    from . import geometry
    polys = geometry.load(pid).polys
    if not len(polys):
        return np.zeros((0, 3, 3))
    return np.concatenate([polys[:, [0, 1, 2]], polys[:, [0, 2, 3]]])


def surface_distance(p, tris):
    """Distance from point p to the nearest triangle (vectorised, exact)."""
    if not len(tris):
        return 1e9
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = p - b
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = p - c
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2
    denom = va + vb + vc
    denom = np.where(np.abs(denom) < 1e-12, 1e-12, denom)
    v, w = vb / denom, vc / denom
    closest = a + ab * v[:, None] + ac * w[:, None]
    # fall back to the nearest vertex where the projection leaves the triangle
    outside = (v < 0) | (w < 0) | (v + w > 1)
    dist = np.linalg.norm(closest - p, axis=1)
    vert = np.min(np.stack([np.linalg.norm(a - p, axis=1), np.linalg.norm(b - p, axis=1),
                            np.linalg.norm(c - p, axis=1)]), 0)
    # and the nearest point on each edge
    def seg(u, v_):
        t = np.clip(((p - u) * (v_ - u)).sum(1) / np.maximum(((v_ - u) ** 2).sum(1), 1e-12), 0, 1)
        return np.linalg.norm(u + (v_ - u) * t[:, None] - p, axis=1)
    edge = np.min(np.stack([seg(a, b), seg(b, c), seg(c, a)]), 0)
    return float(np.where(outside, np.minimum(vert, edge), dist).min())



def plausible(pid: str, kind: str, origin) -> tuple[bool, float]:
    """Does a snap-derived joint match the part's drawn shape? The surface must be about
    one connector radius from its centre, and a hole's centre must be open."""
    d = surface_distance(np.asarray(origin, float), _tris(pid))
    ok = d <= NEAR.get(kind, 10)
    if kind in ("pin_hole", "axle_hole", "bar_hole"):
        ok = ok and d >= 2.0
    return ok, d
