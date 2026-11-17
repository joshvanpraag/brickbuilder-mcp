"""Wheels: tyres on rims, and the hub hole of wheels the LDCad data doesn't cover.

LDraw draws wheel rims and tyres round the part's Z axis, centred on it. This module adds:
- a `tyre_seat` joint on every rim and a `tyre` joint on every tyre, so a tyre can be
  fitted onto a rim with attach_joint (bend turns it round the axle);
- a hub joint (`axle_hole`, `pin_hole` or `bar_hole`) on wheels that have no connection
  data, found from the size of the hole drawn through the hub.

Where the tyre sits along the rim: LDraw ships about a hundred ready-made rim + tyre parts
(named like the rim plus c01, c02, ...). Each records exactly where a real tyre sits on that
rim, so a rim that appears in one takes its seat from there. Other rims use the middle of
their outer barrel, which matches the ready-made parts about 9 times in 10.
"""
from __future__ import annotations

import functools
import re

import numpy as np

from . import ldraw

_NOT_WHEELS = ("cover", "caterpillar", "track", "belt", "train", "gear")
# how much smaller a tyre's hole may be than the rim it goes on (LDU); real pairs are 0-13
MAX_STRETCH = 14.0
SEAT_SLIDE = 8.0


@functools.lru_cache(maxsize=4096)
def _title(pid: str) -> str:
    path = ldraw._find(pid + ".dat")
    if path is None:
        return ""
    with open(path, encoding="utf-8", errors="ignore") as fh:
        line = fh.readline()
    return line[1:].strip() if line.startswith("0") else ""


@functools.lru_cache(maxsize=4096)
def _points(pid: str) -> np.ndarray:
    from . import geometry
    g = geometry._load_file(pid + ".dat")
    return np.array(g[0], float).reshape(-1, 3)


def _round_about_z(pid: str) -> bool:
    p = _points(pid)
    if len(p) < 8:
        return False
    span = p.max(0) - p.min(0)
    r = np.hypot(p[:, 0], p[:, 1]).max()
    return abs(span[0] - span[1]) < 1.0 and abs(span[0] / 2 - r) < 1.5 and abs(p[:, 0].mean()) < 2


def is_tyre(pid: str) -> bool:
    t = _title(pid).lower()
    return t.startswith("tyre") and _round_about_z(pid)


def is_wheel(pid: str) -> bool:
    """A rim or wheel, with or without a tyre already on it."""
    t = _title(pid).lower()
    return (t.startswith("wheel") and not any(w in t for w in _NOT_WHEELS)
            and _round_about_z(pid))


def is_rim(pid: str) -> bool:
    """A wheel without a tyre: something a tyre can go on."""
    return is_wheel(pid) and "tyre" not in _title(pid).lower() and "tire" not in _title(pid).lower()


def rim_radius(pid: str) -> float:
    p = _points(pid)
    return float(np.hypot(p[:, 0], p[:, 1]).max())


def tyre_bore(pid: str) -> float:
    p = _points(pid)
    return float(np.hypot(p[:, 0], p[:, 1]).min())


def _tyre_centre(pid: str) -> float:
    z = _points(pid)[:, 2]
    return float((z.min() + z.max()) / 2)


def _barrel_centre(pid: str) -> float:
    p = _points(pid)
    r = np.hypot(p[:, 0], p[:, 1])
    z = p[r >= r.max() - 0.5, 2]
    return float((z.min() + z.max()) / 2)


@functools.lru_cache(maxsize=1)
def _recorded_fits() -> dict[tuple[str, str], tuple[np.ndarray, np.ndarray]]:
    """(rim, tyre) -> (tyre centre in the rim's frame, tyre axis in the rim's frame), read
    from LDraw's ready-made rim + tyre parts."""
    out: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
    parts = ldraw.LDRAW_DIR / "parts"
    if not parts.exists():
        return out
    for path in sorted(parts.glob("*c0[0-9].dat")):
        with open(path, encoding="utf-8", errors="ignore") as fh:
            lines = fh.read().splitlines()
        if not lines or "tyre" not in lines[0].lower():
            continue
        subs = []
        for line in lines:
            t = line.split()
            if len(t) >= 15 and t[0] == "1":
                v = list(map(float, t[2:14]))
                subs.append((re.sub(r"\.dat$", "", t[14].lower()), np.array(v[3:]).reshape(3, 3), np.array(v[:3])))
        if len(subs) != 2:
            continue
        (a, ra, pa), (b, rb, pb) = subs
        if is_tyre(a) and not is_tyre(b):
            (a, ra, pa), (b, rb, pb) = (b, rb, pb), (a, ra, pa)
        if not (is_tyre(b) and is_rim(a)) or (a, b) in out:
            continue
        centre = ra.T @ (rb @ np.array([0.0, 0.0, _tyre_centre(b)]) + pb - pa)
        axis = ra.T @ rb @ np.array([0.0, 0.0, 1.0])
        out[(a, b)] = (centre, axis)
    return out


def seat(pid: str) -> tuple[np.ndarray, np.ndarray]:
    """Where a tyre's centre goes on this rim, and the rim's axis (both in its own frame)."""
    fits = sorted((t, v) for (r, t), v in _recorded_fits().items() if r == pid)
    if fits:
        return fits[0][1]
    return np.array([0.0, 0.0, _barrel_centre(pid)]), np.array([0.0, 0.0, 1.0])


def pair_shift(rim: str, tyre: str) -> np.ndarray:
    """For a rim that takes several tyres at different places: how far (in the rim's frame)
    this tyre's recorded place is from the rim's tyre_seat. Zero when nothing is recorded."""
    fit = _recorded_fits().get((rim, tyre))
    return fit[0] - seat(rim)[0] if fit else np.zeros(3)


def fit_problem(rim: str, tyre: str) -> str | None:
    """Why this tyre doesn't fit this rim, or None if it does."""
    if (rim, tyre) in _recorded_fits():
        return None
    r, b = rim_radius(rim), tyre_bore(tyre)
    if b > r + 0.5:
        return f"tyre {tyre} is too big for rim {rim} (its hole is {b:.0f} LDU across the radius, the rim {r:.0f})"
    if r - b > MAX_STRETCH:
        return f"tyre {tyre} is too small for rim {rim} (its hole is {b:.0f} LDU across the radius, the rim {r:.0f})"
    return None


def _hub(pid: str) -> tuple[str, np.ndarray, float] | None:
    """The hole through a wheel's hub: (kind, centre, length), from the drawn shape."""
    p = _points(pid)
    r = np.hypot(p[:, 0], p[:, 1])
    inner = r[r > 1.0]
    if not len(inner):
        return None
    bore = float(inner.min())
    band = p[np.abs(r - bore) < 0.6, 2]
    if band.max() - band.min() < 2:
        return None                               # a decorative ring, not a hole
    if 3.3 <= bore <= 3.8:
        kind = "axle_hole"                        # the inner corners of a cross-shaped hole
    elif 3.8 < bore <= 4.6:
        kind = "bar_hole"
    elif 5.6 <= bore <= 6.4:
        kind = "pin_hole"
    else:
        return None
    return kind, np.array([0.0, 0.0, float(band.min() + band.max()) / 2]), float(band.max() - band.min())


def joints(pid: str, have: list) -> list:
    """Extra joints for wheels and tyres (see the module docstring)."""
    from . import geometry
    out = []
    z = np.array([0.0, 0.0, 1.0])
    if is_tyre(pid):
        o = np.array([0.0, 0.0, _tyre_centre(pid)])
        out.append(("tyre", o, geometry._fit_frame(pid, o, z), 0.0))
    elif is_wheel(pid):
        if is_rim(pid):
            o, axis = seat(pid)
            # slide: other tyres recorded for this rim sit a few LDU along from the seat
            out.append(("tyre_seat", o, geometry._fit_frame(pid, o, axis), SEAT_SLIDE))
        on_axis = [k for k, o, f, _ in have if k in ("axle_hole", "pin_hole", "bar_hole")
                   and np.hypot(o[0], o[1]) < 2]
        if not on_axis:
            hub = _hub(pid)
            if hub:
                kind, o, length = hub
                slide = (20.0 - length) / 2 if kind == "axle_hole" and length < 20 else 0.0
                out.append((kind, o, geometry._fit_frame(pid, o, z), slide))
    return out
