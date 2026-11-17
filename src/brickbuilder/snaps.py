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
    """Offsets (in the snap's own X/Z plane) for [grid=[C] nx [C] nz sx sz]."""
    if not spec:
        return [np.zeros(3)]
    tok = spec.split()
    try:
        cx = tok[0].upper() == "C"
        i = 1 if cx else 0
        nx = int(float(tok[i]))
        i += 1
        cz = tok[i].upper() == "C"
        i += 1 if cz else 0
        nz = int(float(tok[i]))
        sx, sz = float(tok[i + 1]), float(tok[i + 2])
    except (IndexError, ValueError):
        return [np.zeros(3)]
    xs = [(k - (nx - 1) / 2) * sx if cx else k * sx for k in range(max(nx, 1))]
    zs = [(k - (nz - 1) / 2) * sz if cz else k * sz for k in range(max(nz, 1))]
    return [np.array([x, 0.0, z]) for z in zs for x in xs]


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
    return resolve_file(ldraw.normalize_part_id(part) + ".dat")


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
    return "pin_hole"


def summary(part: str) -> dict[str, int]:
    """How many of each connector a part has, e.g. {'stud': 4, 'antistud': 2}."""
    out: dict[str, int] = {}
    for s in part_snaps(part):
        k = classify(s)
        out[k] = out.get(k, 0) + 1
    return out
