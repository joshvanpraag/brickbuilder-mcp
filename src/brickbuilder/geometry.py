"""Real part geometry: polygons, stud connectors and solid volume.

Everything here is in a part's local LDraw frame: X right, Y DOWN, Z back, origin at
the centre of the part's top surface for standard parts. Studs point along local -Y.

  load(part)          -> polygons and edge lines, with studs kept separately
  studs(part)         -> where the part's studs are and which way they point
  receivers(part)     -> where studs from another part can plug into its underside
  voxels(part)        -> centres of 4 LDU cubes filling the part's solid body (no studs)

Receivers are not marked in LDraw files, so they are derived: one per stud-grid column
of the footprint whose underside is flat (inverted slopes and other shaped undersides
get none where the underside is not flat).
"""

from __future__ import annotations

import functools
import math
import re
from dataclasses import dataclass

import numpy as np

from . import ldraw

VOXEL = 4.0  # LDU; 1 stud = 5 voxels, 1 plate = 2 voxels

# Joints. Every joint is (kind, origin, frame, slide) in the part's local frame; frame columns
# are the joint's X, Y, Z axes and slide is how far (LDU) a clip may sit off the joint centre
# along X (bars only, 0 elsewhere).
#
# Ball families (joint-8 ball / socket, towball, large 2x2 brick ball): the joint centre is
# the ball centre, Z points from the joint toward its own part (a ball's stem, the side of
# a socket cup that is closed).
#
# Rotation joints turn about frame X:
#   clip / bar and click hinges are "opposed": Z points from the axis toward the part's body
#   and Y toward the part's underside, so at angle 0 the two parts stand on opposite sides
#   of the axis, the same way up (a clip plate continuing a handle plate, a hinge lying flat).
#   hinge (3937 / 6134), swivel hinge plates and turntables are "aligned": at angle 0 the
#   two frames coincide, which is the assembled position LDraw draws them in.
BALL_KINDS = {"ball", "socket", "towball", "towball_socket", "large_ball", "large_socket"}
# pin / pin_hole / axle / axle_hole, bar_hole (a 1-stud-wide bar fits in: a wheel on a
# wheel holder's pin, a bar in a hollow stud) and finger_m / finger_f come from the LDCad snap data
# (snaps.py), as do clips and bars that LDraw draws without a recognisable primitive.
OPPOSED_KINDS = {"clip", "bar", "bar_hole", "click_hinge_1", "click_hinge_2", "pin", "pin_hole", "axle",
                 "axle_hole"}
SLIDE_KINDS = {"clip", "bar", "axle", "axle_hole", "pin_hole", "tyre", "tyre_seat"}
FLIP_KINDS = (SLIDE_KINDS - {"tyre", "tyre_seat"}) | {"pin"}
MALE_SLIDE_KINDS = {"bar", "axle"}          # slide moves the other part along these
# Largest tilt (degrees, bend and swing combined) each ball system allows.
BALL_TILT = {"ball": 45, "socket": 45, "towball": 60, "towball_socket": 60,
             "large_ball": 45, "large_socket": 45}
CLIP_WIDTH = 8.0  # LDU of bar a clip grips

_PAIRS = [("ball", "socket"), ("towball", "towball_socket"), ("large_ball", "large_socket"),
          ("hinge_base", "hinge_top"), ("clip", "bar"), ("swivel_base", "swivel_top"),
          ("click_hinge_1", "click_hinge_2"), ("turntable_base", "turntable_top"),
          ("turntable2_base", "turntable2_top"), ("flat_turntable", "snapstud"),
          ("pin", "pin_hole"), ("axle", "axle_hole"), ("axle", "pin_hole"), ("finger_m", "finger_f"),
          ("bar", "bar_hole"), ("tyre_seat", "tyre")]
JOINT_PAIRS = {p for a, b in _PAIRS for p in ((a, b), (b, a))}

# Joint primitives by file name: (kind, centre, axis) in the primitive's frame. For ball
# primitives the frame is the primitive's own; for the others only the axis is taken from
# the primitive and the rest of the frame is fitted to the part (see _fit_frame).
_JOINT_PRIMS = {"joint8ball.dat": ("ball", None, None), "joint8socket1.dat": ("socket", None, None),
                "joint8socket2.dat": ("socket", None, None), "joint8socket3.dat": ("socket", None, None)}
# Clips that grip a 4 LDU (radius) bar. Horizontal clips hold the bar along X through
# (0, 2, 0), vertical ones along Y, top clips along Z. clip4 (road signs) grips plates, not bars.
for _name, _c, _a in [("clip1", (0, 0, 0), (0, 1, 0)), ("clip2", (0, 0, -10), (0, 1, 0)),
                      ("clip3", (0, 2, 0), (1, 0, 0)), ("clip5", (0, 0, 0), (0, 1, 0)),
                      ("clip6", (0, 2, 0), (1, 0, 0)), ("clip7", (0, 0, 0), (0, 1, 0)),
                      ("clip8", (0, -6, 0), (0, 0, 1)), ("clip9", (0, 0, -10), (0, 1, 0)),
                      ("clip10", (0, 0, -10), (0, 1, 0)), ("clip11", (0, -6, 0), (0, 0, 1)),
                      ("clip12", (0, 0, 0), (0, 1, 0)), ("clip13", (0, 0, 0), (0, 1, 0)),
                      ("clip14", (0, 0, -10), (0, 1, 0)), ("clip15", (0, 0, 0), (0, 1, 0)),
                      ("clip16", (0, 0, 0), (0, 1, 0))]:
    _JOINT_PRIMS[_name + ".dat"] = ("clip", _c, _a)
# Handle attachments: one end of a handle bar. Paired into a bar by _pair_handles.
_JOINT_PRIMS["phandle1.dat"] = ("handle_end", (0, 2, 0), (1, 0, 0))
_JOINT_PRIMS["phandle2.dat"] = ("handle_end", (0, 2, 0), (1, 0, 0))
# Click (locking) hinge halves: clh6 single finger, clh4 dual finger (two mirrored halves).
_JOINT_PRIMS["clh6.dat"] = ("click_hinge_1", (0, 0, -10), (1, 0, 0))
_JOINT_PRIMS["clh4.dat"] = ("click_hinge_2", (0, 0, 4), (1, 0, 0))

_I = np.eye(3)
_VERTICAL = np.array([[0, 1, 0], [-1, 0, 0], [0, 0, 1]], float)  # X up (local -Y), Y = local +X
_STEM_LEFT = np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], float)  # Z = +X: ball on the -X end
_STEM_RIGHT = np.array([[0, 0, -1], [0, 1, 0], [1, 0, 0]], float)  # Z = -X: ball on the +X end
# Joints LDraw has no primitive for: part -> [(kind, origin, frame)]. Frames of None are
# fitted to the part from the axis given instead (see _fit_frame).
_JOINT_OVERRIDES = {
    # Hinge 3937 + 6134: both pivot about the line along local X through (0, 10, 0).
    "3937": [("hinge_base", (0, 10, 0), _I)],
    "6134": [("hinge_top", (0, 10, 0), _I)],
    # Tile 1 x 1 with Clip: clip drawn without a clip primitive, bar along Z at y=-6.
    "15712": [("clip", (0, -6, 0), (0, 0, 1))],
    # Towballs (8 LDU ball, stem toward +Z) and the towball socket (cup open toward -Z).
    "3731": [("towball", (0, 4, -40), _I)],
    "15456": [("towball", (0, 4, -40), _I)],
    "3614a": [("towball", (0, 4, -19), _I)],
    "3614": [("towball", (0, 4, -18), _I)],
    "3184": [("towball", (0, 4, -28), _I)],
    "3730": [("towball_socket", (0, 4, -30), _I)],
    # Brick 2 x 2 with two large balls (12.8 LDU) and the 2 x 2 bricks with a socket on +X.
    "17114": [("large_ball", (40, 10, 0), _STEM_RIGHT), ("large_ball", (-40, 10, 0), _STEM_LEFT)],
    **{p: [("large_socket", (40, 10, 0), _STEM_RIGHT)] for p in ("62712", "92013", "57910", "67696")},
    # Hinge plates 1 x 4 swivel: both halves turn about the vertical line through the origin.
    "2429": [("swivel_base", (0, 0, 0), _VERTICAL)],
    "2430": [("swivel_top", (0, 0, 0), _VERTICAL)],
    # Turntables: top and base share the vertical axis through the origin (3403c01, 3680c01).
    "3403": [("turntable_base", (0, 0, 0), _VERTICAL)],
    "3404": [("turntable_top", (0, 0, 0), _VERTICAL)],
    "3680": [("turntable2_base", (0, 0, 0), _VERTICAL)],
    "3679": [("turntable2_top", (0, 0, 0), _VERTICAL)],
    # Flat turntable base 4 x 4: a round plate's snapstud turns in its centre (61485c01 puts
    # the plate's underside on the base's top).
    "61485": [("flat_turntable", (0, 0, 0), _VERTICAL)],
    **{p: [("snapstud", (0, 8, 0), _VERTICAL)] for p in ("60474", "11213", "74611", "89523")},
    "87081": [("snapstud", (0, 24, 0), _VERTICAL)],
}
# Plain bars LDraw draws as one cylinder: part -> (end, other end) of the bar axis.
_BAR_OVERRIDES: dict[str, tuple] = {}

# Primitives that are a stud you can press something onto (not underside tubes).
_MALE = re.compile(r"(stud|stud-logo\d*|stud2|stud2-logo\d*|stud2a|stud6|stud6a|stud10|stud13|stud15|"
                   r"stud17|stud17a|stud26)\.dat")
EDGE = -2  # marker for LDraw edge colour 24


@dataclass(frozen=True)
class PartMesh:
    polys: np.ndarray        # (N, 4, 3) quads; triangles repeat their last vertex
    poly_colours: np.ndarray  # (N,) colour codes, 16 = the part's own colour
    lines: np.ndarray        # (M, 2, 3) edge lines
    line_colours: np.ndarray  # (M,) colour codes, EDGE = default edge colour
    body: np.ndarray         # (K,) bool: polygon belongs to the body (not a stud)
    studs: tuple             # ((pos (3,), dir (3,)), ...)


def _empty() -> tuple:
    return (np.zeros((0, 4, 3)), np.zeros(0, int), np.zeros((0, 2, 3)), np.zeros(0, int),
            np.zeros(0, bool), ())


def _orthonormal(mat: np.ndarray) -> np.ndarray:
    """Strip the scale from a primitive's matrix, keeping its axes."""
    cols = []
    for k in range(3):
        c = mat[:, k]
        n = np.linalg.norm(c)
        cols.append(c / n if n else c)
    return np.stack(cols, 1)


@functools.lru_cache(maxsize=4096)
def _joint_refs(name: str) -> tuple:
    """Joint primitives inside one LDraw file: ((kind, origin (3,), frame (3,3)), ...).
    For non-ball primitives only frame column X (the axis) is meaningful."""
    name = name.strip().lower().replace("\\", "/")
    base = name.rsplit("/", 1)[-1]
    if base in _JOINT_PRIMS:
        kind, c, a = _JOINT_PRIMS[base]
        if c is None:
            return ((kind, np.zeros(3), np.eye(3)),)
        return ((kind, np.array(c, float), _axis_frame(np.array(a, float))),)
    if _MALE.fullmatch(base) or base.startswith(("stud", "box", "rect", "edge", "4-4", "1-", "2-", "3-")):
        return ()
    path = ldraw._find(name)
    if path is None:
        return ()
    out = []
    for line in open(path, encoding="utf-8", errors="ignore"):
        t = line.split()
        if len(t) >= 15 and t[0] == "1":
            v = list(map(float, t[2:14]))
            pos, mat = np.array(v[:3]), np.array(v[3:]).reshape(3, 3)
            for kind, o, f in _joint_refs(" ".join(t[14:])):
                out.append((kind, mat @ o + pos, _orthonormal(mat) @ f))
    return tuple(out)


def _axis_frame(axis: np.ndarray) -> np.ndarray:
    """Some frame whose X column is `axis` (Y and Z are refitted per part later)."""
    x = axis / np.linalg.norm(axis)
    helper = np.array([0.0, 1.0, 0.0]) if abs(x[1]) < 0.9 else np.array([0.0, 0.0, 1.0])
    z = np.cross(x, helper)
    z /= np.linalg.norm(z)
    return np.stack([x, np.cross(z, x), z], 1)


def _fit_frame(part: str, origin: np.ndarray, axis: np.ndarray) -> np.ndarray:
    """Frame for a rotation joint of an "opposed" kind: X along `axis`, Z from the axis
    toward the part's body, Y toward the part's underside (local +Y) as far as possible.
    Signs come from the part, not from how a primitive happened to be mirrored, so two
    parts' frames line up the same way for the same physical connection."""
    x = axis / np.linalg.norm(axis)
    v = voxels(part)
    # toward the body's centre when it is clearly off the axis (1 LDU), else a fixed choice
    cands = [(v.mean(0) - origin, 1.0)] if len(v) else []
    cands += [(np.array([0.0, 0.0, 1.0]), 0.5), (np.array([1.0, 0.0, 0.0]), 0.5),
              (np.array([0.0, 1.0, 0.0]), 0.5)]
    for c, need in cands:
        c = c - np.dot(c, x) * x
        if np.linalg.norm(c) > need:
            z = c / np.linalg.norm(c)
            break
    if np.max(np.abs(x)) > 0.999:
        # axis-aligned joint: point Z straight along the nearest part axis, so angle 0 is
        # square to the part rather than aimed at its (off-centre) middle
        k = int(np.argmax(np.abs(z) * (np.abs(x) < 0.5)))
        sign = 1.0 if z[k] > 0 else -1.0
        z = np.zeros(3)
        z[k] = sign
    for c in (np.array([0.0, 1.0, 0.0]), np.array([1.0, 0.0, 0.0]), np.array([0.0, 0.0, 1.0])):
        y = c - np.dot(c, x) * x - np.dot(c, z) * z
        if np.linalg.norm(y) > 0.5:
            y /= np.linalg.norm(y)
            break
    # right-handed: re-derive X's sign from Y and Z
    return np.stack([np.cross(y, z), y, z], 1)


def _pair_handles(ends: list) -> list:
    """Pair handle attachments that face each other on one line into bars:
    [(origin, axis, slide)]. A clip grips the free bar between the two attachments."""
    bars, used = [], set()
    for i, (oi, ai) in enumerate(ends):
        if i in used:
            continue
        best = None
        for j in range(i + 1, len(ends)):
            if j in used:
                continue
            oj, aj = ends[j]
            d = oj - oi
            n = np.linalg.norm(d)
            if n < 1 or abs(np.dot(ai, aj)) < 0.99 or abs(np.dot(d / n, ai)) < 0.99:
                continue
            if best is None or n < best[1]:
                best = (j, n)
        if best is None:
            continue
        j, n = best
        used |= {i, j}
        free = n - 6.0  # each attachment covers 3 LDU of the bar
        bars.append(((oi + ends[j][0]) / 2, (ends[j][0] - oi) / n, max(0.0, (free - CLIP_WIDTH) / 2)))
    return bars


_BAR_CYLS = re.compile(r"(48/|8/)?4-4cyl[io]\.dat")


def _plain_bars(pid: str) -> list:
    """Bars drawn as 4 LDU radius cylinders in parts titled 'Bar ...':
    [(origin, axis, slide)]. Collinear cylinders that touch are merged."""
    if pid in _BAR_OVERRIDES:
        a, b = (np.array(p, float) for p in _BAR_OVERRIDES[pid])
        n = np.linalg.norm(b - a)
        return [((a + b) / 2, (b - a) / n, max(0.0, (n - CLIP_WIDTH) / 2))]
    title = ldraw.part_title(pid) or ""
    if not re.match(r"Bar\b", title) or re.search(r"Tube|Holder|Grille|Window", title):
        return []
    path = ldraw._find(pid + ".dat")
    if path is None:
        return []
    segs = []
    for line in open(path, encoding="utf-8", errors="ignore"):
        t = line.split()
        if len(t) < 15 or t[0] != "1" or not _BAR_CYLS.fullmatch(" ".join(t[14:]).lower().replace("\\", "/")):
            continue
        v = list(map(float, t[2:14]))
        pos, mat = np.array(v[:3]), np.array(v[3:]).reshape(3, 3)
        if not (abs(np.linalg.norm(mat[:, 0]) - 4) < 0.3 and abs(np.linalg.norm(mat[:, 2]) - 4) < 0.3):
            continue
        segs.append((pos, pos + mat[:, 1]))
    # merge collinear touching segments
    merged = []
    for a, b in segs:
        d = b - a
        if np.linalg.norm(d) < 1e-6:
            continue
        u = d / np.linalg.norm(d)
        for k, (ma, mb, mu) in enumerate(merged):
            off = a - ma
            if abs(abs(np.dot(u, mu)) - 1) < 1e-3 and np.linalg.norm(off - np.dot(off, mu) * mu) < 0.5:
                ts = [0.0, np.dot(mb - ma, mu), np.dot(a - ma, mu), np.dot(b - ma, mu)]
                lo, hi = min(ts), max(ts)
                if min(np.dot(a - ma, mu), np.dot(b - ma, mu)) <= np.dot(mb - ma, mu) + 0.5 and \
                        max(np.dot(a - ma, mu), np.dot(b - ma, mu)) >= -0.5:
                    merged[k] = (ma + lo * mu, ma + hi * mu, mu)
                    break
        else:
            merged.append((a, b, u))
    out = []
    for a, b, u in merged:
        n = np.linalg.norm(b - a)
        if n >= CLIP_WIDTH - 0.5:
            out.append(((a + b) / 2, u, max(0.0, (n - CLIP_WIDTH) / 2)))
    return out


@functools.lru_cache(maxsize=4096)
def joints(part: str) -> tuple:
    """Joints of a part in its local frame: ((kind, origin (3,), frame (3,3)), ...).
    See joints_full for the kinds and for how far a clip can slide on a bar."""
    return tuple((k, o, f) for k, o, f, _ in joints_full(part))


@functools.lru_cache(maxsize=4096)
def joints_full(part: str) -> tuple:
    """Joints of a part in its local frame: ((kind, origin (3,), frame (3,3), slide), ...).
    Kinds: ball / socket (joint-8), towball / towball_socket, large_ball / large_socket
    (2 x 2 brick ball system), hinge_base / hinge_top (3937 / 6134), clip / bar,
    swivel_base / swivel_top (hinge plates 2429 / 2430), click_hinge_1 / click_hinge_2
    (locking hinges), turntable_base / turntable_top (3403 / 3404), turntable2_base /
    turntable2_top (3680 / 3679) and flat_turntable / snapstud (61485 + round plates)."""
    pid = ldraw.normalize_part_id(part)
    raw, out = [], []
    if pid in _JOINT_OVERRIDES:
        for k, o, f in _JOINT_OVERRIDES[pid]:
            o, f = np.array(o, float), np.array(f, float)
            raw.append((k, o, f if f.shape == (3, 3) else _axis_frame(f)))
    else:
        raw = list(_joint_refs(pid + ".dat"))
    ends = []
    for k, o, f in raw:
        if k == "handle_end":
            ends.append((o, f[:, 0]))
            continue
        if k in OPPOSED_KINDS:
            # one joint per pivot (a dual finger hinge is drawn as two mirrored halves)
            if any(k2 == k and np.linalg.norm(o2 - o) < 0.5 for k2, o2, _, _ in out):
                continue
            f = _fit_frame(pid, o, f[:, 0])
        out.append((k, o, f, 0.0))
    for o, a, s in _pair_handles(ends) + (_plain_bars(pid) if pid not in _JOINT_OVERRIDES else []):
        out.append(("bar", o, _fit_frame(pid, o, a), s))
    out += _snap_joints(pid, out)
    from . import wheels
    out += wheels.joints(pid, out)
    return tuple(out)


_HINGE_KINDS = {"hinge_base", "hinge_top", "swivel_base", "swivel_top", "click_hinge_1", "click_hinge_2"}


def _snap_joints(pid: str, have: list, validate: bool = True) -> list:
    """Joints from the LDCad snap data that the detection above did not find: clips and
    bars it missed, Technic pins / pin holes / axles / axle holes, hinge fingers, and ball
    joints on parts that have none yet. Nothing is added when the data is not installed.
    With `validate`, a joint is kept only if it matches the part's drawn shape
    (snaps.plausible), so data that doesn't fit the LDraw model is ignored."""
    from . import snaps
    if not snaps.available():
        return []
    out = _Checked(pid, validate)       # drops joints that don't match the part's shape

    def dup(kind, o, axis):
        for k, o2, f2, _ in list(have) + list(out):
            if k == kind and np.linalg.norm(o2 - o) < 3 and (axis is None or abs(np.dot(f2[:, 0], axis)) > 0.98):
                return True
        return False

    kinds_have = {k for k, *_ in have}
    centre = None
    for s in snaps.part_snaps(pid):
        name = snaps.classify(s)
        y = s.axis / (np.linalg.norm(s.axis) or 1)
        if name in ("bar", "bar_hole", "pin", "pin_hole", "axle", "axle_hole"):
            secs = s.params.get("secs") or []
            total = sum(length for _, _, length in secs)
            start = -total / 2 if str(s.params.get("center", "")).lower() == "true" else 0.0
            # the part of the cylinder that goes into the other part (not a pin's collar).
            # An axle pin (3749, 6562) is one cylinder with a round pin half and a cross
            # axle half: it becomes two joints, a pin and an axle.
            def wanted(shape, r, kind):
                if kind == "pin":
                    return r <= 6.6 and "A" not in shape
                if kind == "axle" and s.gender == "M":
                    return "A" in shape
                return True
            groups = [name]
            if name == "axle" and s.gender == "M" and any(
                    "A" not in sh and r <= 6.6 and length >= 8 for sh, r, length in secs):
                groups = ["pin", "axle"]
            for kind in groups:
                spans, t = [], start
                for shape, r, length in secs:
                    if (kind not in ("pin", "axle") or len(groups) == 1 and kind == "axle"
                            or wanted(shape, r, kind)):
                        spans.append((t, t + length))
                    t += length
                if not spans:
                    continue
                a, b = spans[0][0], spans[-1][1]
                o = s.pos - y * (a + b) / 2              # cylinders run along the snap's -Y
                length = b - a
                if kind == "bar" and length < CLIP_WIDTH - 0.5:
                    continue                             # too short to clip (a stud's core)
                if dup(kind, o, y):
                    continue
                slide = max(0.0, (length - (CLIP_WIDTH if kind == "bar" else 20.0)) / 2) \
                    if kind in ("bar", "axle") else 0.0
                if kind == "axle_hole" and length < 20.0:
                    # a short grip ring (a wheel rim's hub): the part can sit anywhere
                    # along a one-stud axle end, not only at its middle
                    slide = (20.0 - length) / 2
                out.append((kind, o, _fit_frame(pid, o, y), slide))
        elif name == "clip":
            length = float(s.params.get("length", CLIP_WIDTH) or CLIP_WIDTH)
            centred = str(s.params.get("center", "")).lower() == "true"
            o = s.pos if centred else s.pos - y * length / 2
            if not dup("clip", o, y):
                out.append(("clip", o, _fit_frame(pid, o, y), 0.0))
        elif name == "finger" and not (kinds_have & _HINGE_KINDS):
            kind = "finger_m" if s.gender == "M" else "finger_f"
            frame = np.stack([s.frame[:, 1], s.frame[:, 2], s.frame[:, 0]], 1)   # X = finger axis
            frame = np.stack([c / (np.linalg.norm(c) or 1) for c in frame.T], 1)
            if not dup(kind, s.pos, frame[:, 0]):
                out.append((kind, s.pos.copy(), frame, 0.0))
        elif name in ("ball", "ball_socket") and not (kinds_have & BALL_KINDS):
            try:
                r = float(s.params.get("bounding", "").split()[1])
            except (IndexError, ValueError):
                continue
            if r <= 9:
                kind = "ball" if name == "ball" else "socket"
            elif 11.5 <= r <= 14:
                kind = "large_ball" if name == "ball" else "large_socket"
            else:
                continue
            if centre is None:
                v = voxels(pid)
                centre = v.mean(0) if len(v) else np.zeros(3)
            z = centre - s.pos                           # from the ball back into the part
            if np.linalg.norm(z) < 1:
                continue
            frame = _axis_frame(z / np.linalg.norm(z))
            frame = np.stack([frame[:, 1], frame[:, 2], frame[:, 0]], 1)        # Z = stem axis
            if not dup(kind, s.pos, None):
                out.append((kind, s.pos.copy(), frame, 0.0))
    return list(out)


class _Checked(list):
    """A list that only accepts joints passing the shape check."""

    def __init__(self, pid: str, validate: bool):
        super().__init__()
        self.pid, self.validate = pid, validate

    def append(self, joint) -> None:
        if self.validate:
            from . import snaps
            if not snaps.plausible(self.pid, joint[0], joint[1])[0]:
                return
        super().append(joint)


@functools.lru_cache(maxsize=4096)
def _load_file(name: str) -> tuple:
    """Recursively expanded geometry of one LDraw file, in that file's frame."""
    name = name.strip().lower().replace("\\", "/")
    path = ldraw._find(name)
    if path is None:
        return _empty()
    P, PC, L, LC, B, S = [], [], [], [], [], []
    for line in open(path, encoding="utf-8", errors="ignore"):
        t = line.split()
        if not t or t[0] == "0":
            continue
        kind = t[0]
        if kind == "1" and len(t) >= 15:
            c = int(t[1]) if t[1].isdigit() else 16
            v = list(map(float, t[2:14]))
            pos, mat = np.array(v[:3]), np.array(v[3:]).reshape(3, 3)
            sub = " ".join(t[14:]).strip().lower().replace("\\", "/")
            sp, spc, sl, slc, sb, ss = _load_file(sub)
            is_stud = bool(_MALE.fullmatch(sub.rsplit("/", 1)[-1]))
            if len(sp):
                P.append(sp @ mat.T + pos)
                PC.append(np.where(spc == 16, c, spc))
                B.append(np.zeros(len(sp), bool) if is_stud else sb)
            if len(sl):
                L.append(sl @ mat.T + pos)
                LC.append(np.where(slc == 16, c, slc))
            if is_stud:
                d = mat @ np.array([0.0, -1.0, 0.0])
                n = np.linalg.norm(d)
                S.append((pos.copy(), d / n if n else d))
            else:
                for spos, sdir in ss:
                    d = mat @ sdir
                    n = np.linalg.norm(d)
                    S.append((mat @ spos + pos, d / n if n else d))
        elif kind in ("3", "4"):
            n = int(kind)
            if len(t) < 2 + 3 * n:
                continue
            pts = np.array(list(map(float, t[2:2 + 3 * n]))).reshape(n, 3)
            if n == 3:
                pts = np.vstack([pts, pts[2:3]])
            P.append(pts[None])
            PC.append(np.array([int(t[1]) if t[1].lstrip("-").isdigit() else 16]))
            B.append(np.ones(1, bool))
        elif kind == "2" and len(t) >= 8:
            pts = np.array(list(map(float, t[2:8]))).reshape(2, 3)
            c = int(t[1]) if t[1].isdigit() else 24
            L.append(pts[None])
            LC.append(np.array([EDGE if c == 24 else c]))
    cat = lambda xs, shape, dt=float: np.concatenate(xs).astype(dt) if xs else np.zeros(shape, dt)
    return (cat(P, (0, 4, 3)), cat(PC, (0,), int), cat(L, (0, 2, 3)), cat(LC, (0,), int),
            cat(B, (0,), bool), tuple(S))


@functools.lru_cache(maxsize=4096)
def load(part: str) -> PartMesh:
    pid = ldraw.normalize_part_id(part)
    P, PC, L, LC, B, S = _load_file(pid + ".dat")
    # merge duplicate studs (some parts reference a stud twice, e.g. stud + logo)
    uniq, seen = [], set()
    for pos, d in S:
        key = tuple(np.round(pos, 1)) + tuple(np.round(d, 2))
        if key not in seen:
            seen.add(key)
            uniq.append((pos, d))
    return PartMesh(P, PC, L, LC, B, tuple(uniq))


def studs(part: str) -> list[tuple[np.ndarray, np.ndarray]]:
    """(position of the stud's base, unit direction it points) in the local frame."""
    return list(load(part).studs)


# ---------------------------------------------------------------- solid volume


@functools.lru_cache(maxsize=4096)
def _columns(part: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Column hull of the body along local Y on a 4 LDU grid.
    Returns (xs, zs, ytop, ybottom) per column that contains material."""
    mesh = load(part)
    polys = mesh.polys[mesh.body]
    if not len(polys):
        return np.zeros(0), np.zeros(0), np.zeros(0), np.zeros(0)
    tris = np.concatenate([polys[:, [0, 1, 2]], polys[:, [0, 2, 3]]])
    pts = _sample_surface(tris, 1.5)
    lo, hi = pts.min(0), pts.max(0)
    # Align the voxel grid with the part's own edges (bounds are on the 10 LDU half-stud
    # grid, not on multiples of 4), so cubes never stick out past a face: two parts that
    # merely touch then never share a voxel.
    b = ldraw.part_bounds(part)
    # Round parts are drawn from circle primitives whose points land a hair outside the
    # stud grid (20.0005 LDU for a 2x2 round plate). Without a tolerance that sliver adds a
    # whole extra column, and the part then clashes with flush neighbours.
    tol = 0.01
    x0 = b.x0 - VOXEL * math.ceil((b.x0 - lo[0] - tol) / VOXEL)
    z0 = b.z0 - VOXEL * math.ceil((b.z0 - lo[2] - tol) / VOXEL)
    nx = int(math.floor((hi[0] - tol - x0) / VOXEL)) + 1
    nz = int(math.floor((hi[2] - tol - z0) / VOXEL)) + 1
    # points exactly on a column boundary belong to the column they face into
    ix = np.clip(np.floor((pts[:, 0] - x0) / VOXEL - 1e-6).astype(int), 0, nx - 1)
    iz = np.clip(np.floor((pts[:, 2] - z0) / VOXEL - 1e-6).astype(int), 0, nz - 1)
    ymin = np.full((nx, nz), np.inf)
    ymax = np.full((nx, nz), -np.inf)
    np.minimum.at(ymin, (ix, iz), pts[:, 1])
    np.maximum.at(ymax, (ix, iz), pts[:, 1])
    ok = np.isfinite(ymin) & (ymax - ymin > 0.5)
    gx = x0 + VOXEL / 2 + VOXEL * np.arange(nx)
    gz = z0 + VOXEL / 2 + VOXEL * np.arange(nz)
    X, Z = np.meshgrid(gx, gz, indexing="ij")
    return X[ok], Z[ok], ymin[ok], ymax[ok]


def _sample_surface(tris: np.ndarray, spacing: float) -> np.ndarray:
    """Points covering every triangle (including vertical walls) at about `spacing` LDU."""
    out = [tris.reshape(-1, 3)]
    e1, e2 = tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
    longest = np.maximum(np.linalg.norm(e1, axis=1), np.linalg.norm(e2, axis=1))
    steps = np.maximum(1, np.ceil(longest / spacing).astype(int))
    for n in np.unique(steps):
        sel = steps == n
        u, v = np.meshgrid(np.arange(n + 1) / n, np.arange(n + 1) / n, indexing="ij")
        keep = (u + v) <= 1 + 1e-9
        u, v = u[keep], v[keep]
        a = tris[sel, 0][:, None, :]
        pts = a + u[None, :, None] * e1[sel][:, None, :] + v[None, :, None] * e2[sel][:, None, :]
        out.append(pts.reshape(-1, 3))
    return np.concatenate(out)


@functools.lru_cache(maxsize=4096)
def _column_grid(part: str):
    """Column hull as a lookup grid: (x0, z0, ytop[nx, nz], ybottom[nx, nz]) with NaN where
    there is no material. Column (i, k) covers x0 + 4i .. x0 + 4i + 4 (and likewise z)."""
    xs, zs, yt, yb = _columns(part)
    if not len(xs):
        return 0.0, 0.0, np.full((1, 1), np.nan), np.full((1, 1), np.nan)
    x0, z0 = xs.min() - VOXEL / 2, zs.min() - VOXEL / 2
    ix = np.round((xs - x0 - VOXEL / 2) / VOXEL).astype(int)
    iz = np.round((zs - z0 - VOXEL / 2) / VOXEL).astype(int)
    top = np.full((ix.max() + 1, iz.max() + 1), np.nan)
    bot = np.full_like(top, np.nan)
    top[ix, iz], bot[ix, iz] = yt, yb
    return x0, z0, top, bot


def contains(part: str, pts: np.ndarray, margin: float = 1.5) -> np.ndarray:
    """Which local-frame points lie inside the part's solid by more than `margin` LDU
    (points on or near a surface do not count, so parts that only touch never clash)."""
    if not len(pts):
        return np.zeros(0, bool)
    x0, z0, top, bot = _column_grid(part)
    nx, nz = top.shape
    inside = np.ones(len(pts), bool)
    lo_y = np.full(len(pts), -np.inf)
    hi_y = np.full(len(pts), np.inf)
    for dx in (-margin, margin):
        for dz in (-margin, margin):
            i = np.floor((pts[:, 0] + dx - x0) / VOXEL).astype(int)
            k = np.floor((pts[:, 2] + dz - z0) / VOXEL).astype(int)
            ok = (i >= 0) & (i < nx) & (k >= 0) & (k < nz)
            t = np.full(len(pts), np.nan)
            b = np.full(len(pts), np.nan)
            t[ok], b[ok] = top[i[ok], k[ok]], bot[i[ok], k[ok]]
            inside &= ~np.isnan(t)
            lo_y = np.fmax(lo_y, t)
            hi_y = np.fmin(hi_y, b)
    inside &= (pts[:, 1] > lo_y + margin) & (pts[:, 1] < hi_y - margin)
    bore = _bore(part)
    if bore:                                   # a tyre: its hole runs sideways, so the
        inside &= np.hypot(pts[:, 0], pts[:, 1]) > bore + margin   # columns filled it in
    return inside


def _bore(part: str) -> float:
    """The radius of a tyre's hole (0 for other parts). The solid is built from vertical
    columns, which fill in a hole running sideways; this lets the rim and axle sit inside."""
    from . import wheels
    pid = ldraw.normalize_part_id(part)
    return wheels.tyre_bore(pid) if wheels.is_tyre(pid) else 0.0


@functools.lru_cache(maxsize=4096)
def samples(part: str) -> np.ndarray:
    """Points filling the solid every 2 LDU (each 4 LDU voxel split in eight)."""
    v = voxels(part)
    if not len(v):
        return v
    offs = np.array([[dx, dy, dz] for dx in (-1, 1) for dy in (-1, 1) for dz in (-1, 1)], float)
    pts = (v[:, None, :] + offs[None, :, :]).reshape(-1, 3)
    bore = _bore(part)
    return pts[np.hypot(pts[:, 0], pts[:, 1]) > bore] if bore else pts


@functools.lru_cache(maxsize=4096)
def voxels(part: str) -> np.ndarray:
    """(K, 3) centres of 4 LDU cubes filling the body (studs excluded), local frame."""
    xs, zs, yt, yb = _columns(part)
    y0 = ldraw.part_bounds(part).y_bottom  # align vertically with the part's bottom face
    out = []
    for x, z, a, b in zip(xs, zs, yt, yb):
        ys = y0 - VOXEL / 2 - VOXEL * np.arange(0, math.ceil((y0 - a) / VOXEL) + 1)
        ys = ys[(ys > a - 1e-6) & (ys < b + 1e-6)]
        out.extend((x, y, z) for y in ys)
    return np.array(out, float) if out else np.zeros((0, 3))


# Parts whose LDraw underside is drawn as one continuous curve, leaving out the stud hole the
# real part has under its high end: (x, z) of each receiver, at the part's bottom face.
_RECEIVER_OVERRIDES = {
    "24201": [(0, 20)],             # Slope Curved 2 x 1 Inverted
    "32803": [(-10, 20), (10, 20)],  # Slope Curved 2 x 2 Inverted
    # Dome 4 x 4 Smooth: hollow, its rim fits over a 4x4 round stud pattern (no corners)
    "86500": [(x, z) for z in (-30, -10, 10, 30) for x in (-30, -10, 10, 30)
              if abs(x) + abs(z) < 60],
    # 2x2 round parts drawn with a round hollow underside and no stud cells: their rim
    # fits over a 2x2 stud pattern like a round brick's does
    **{p: [(x, z) for z in (-10, 10) for x in (-10, 10)]
       for p in ("3942a", "3942b", "3942c")},   # Cone 2 x 2 x 2
}


@functools.lru_cache(maxsize=4096)
def receivers(part: str) -> tuple:
    pid = ldraw.normalize_part_id(part)
    if pid in _RECEIVER_OVERRIDES:
        y = float(ldraw.part_bounds(pid).y_bottom)
        return tuple((np.array([float(x), y, float(z)]), np.array([0.0, 1.0, 0.0]))
                     for x, z in _RECEIVER_OVERRIDES[pid])
    return _derived_receivers(pid)


@functools.lru_cache(maxsize=4096)
def _derived_receivers(part: str) -> tuple:
    """Underside positions that accept a stud: ((pos (3,), dir (3,)), ...).
    dir is the way the opening faces (local +Y, down). One per stud-grid column of the
    footprint with a flat underside; ordered front-left first (by z, then x)."""
    b = ldraw.part_bounds(part)
    xs, zs, yt, yb = _columns(part)
    out = []
    if not len(xs):
        return ()
    # Stud cells: try the grid implied by the bounds and the grids implied by the top studs
    # (bounds can be off by a few LDU on parts with overhangs such as brackets; a jumper's
    # centre stud is deliberately off-grid) and keep the one with the most fully filled cells.
    up = [p for p, d in studs(part) if d[1] < -0.9]
    options = [((b.x0 + 10) % 20, (b.z0 + 10) % 20)] + [(p[0] % 20, p[2] % 20) for p in up]
    def centres(o, vals):
        return o + 20 * np.arange(math.floor((vals.min() - o) / 20), math.ceil((vals.max() - o) / 20) + 1)
    def full_cells(o):
        return sum(int(((np.abs(xs - cx) <= 10) & (np.abs(zs - cz) <= 10)).sum() >= 25)
                   for cx in centres(o[0], xs) for cz in centres(o[1], zs))
    ox, oz = max(dict.fromkeys(options), key=full_cells)  # ties keep the bounds grid (first)
    centres_x, centres_z = centres(ox, xs), centres(oz, zs)
    for cz in centres_z:
        for cx in centres_x:
            cell = (np.abs(xs - cx) <= 10) & (np.abs(zs - cz) <= 10)
            if cell.sum() < 16:
                continue  # less than about two thirds of the cell has material
            if not cell.any():
                continue
            # How deep the material reaches along each of the cell's four edges (walls, rims,
            # tubes). A stud cell is a receiver when at least three edges reach the same depth:
            # that is the plane a stud from below presses up into.
            edges = []
            for on_edge in ((xs - cx) <= -5.5, (xs - cx) >= 5.5, (zs - cz) <= -5.5, (zs - cz) >= 5.5):
                sel = cell & on_edge
                if sel.any():
                    edges.append(yb[sel].max())
            if len(edges) < 2:
                continue
            centre = cell & (np.abs(xs - cx) <= 3.5) & (np.abs(zs - cz) <= 3.5)
            ceiling = yb[centre].max() if centre.any() else -np.inf
            # The receiver plane is the shallowest depth every walled edge reaches. Shaped
            # undersides (inverted slopes) fail: one edge is shallow and material comes down
            # below that plane in the middle. A flat solid underside is accepted, because
            # LDraw often leaves the stud recess out of brackets and similar parts.
            plane = min(edges)
            if ceiling > plane + 0.5:
                continue
            out.append((np.array([cx, float(round(plane)), cz]), np.array([0.0, 1.0, 0.0])))
    return tuple(out)


# ---------------------------------------------------------------- grid footprint

_STICKING_OUT = {"bar", "pin", "axle", "clip"}


@functools.lru_cache(maxsize=4096)
def grid_bounds(part: str):
    """The box grid placement (x, y, z) lines up: the part's body, without pins or bars that
    stick out past it. ldraw.part_bounds measures everything drawn, so for a wheel holder
    (4600) whose pins stick out each side it is a stud wider than the plate, and grid
    placement would put the plate half a stud off. Here an overhang is left out only when
    it is even on both sides and a pin, bar, axle or clip sits in it; any other part (a
    dome whose underside covers only its middle, an inverted slope) keeps its full box."""
    pid = ldraw.normalize_part_id(part)
    b = ldraw.part_bounds(pid)
    r = receivers(pid)
    if not r:
        return b
    xs = [float(q[0][0]) for q in r]
    zs = [float(q[0][2]) for q in r]
    sticking = [o for k, o, *_ in joints_full(pid) if k in _STICKING_OUT]
    box = {"x": [b.x0, b.x1], "z": [b.z0, b.z1]}
    for axis, i, vals in (("x", 0, xs), ("z", 2, zs)):
        lo, hi = min(vals) - 10, max(vals) + 10
        full = box[axis]
        if not (lo > full[0] + 0.5 and hi < full[1] - 0.5):
            continue
        if abs((lo - full[0]) - (full[1] - hi)) > 0.5:
            continue                          # overhang on one side only: keep the full box
        if not any(o[i] < lo - 0.5 for o in sticking) or not any(o[i] > hi + 0.5 for o in sticking):
            continue                          # nothing like a pin in the overhang
        box[axis] = [lo, hi]
    if box == {"x": [b.x0, b.x1], "z": [b.z0, b.z1]}:
        return b
    y_bottom = b.y_bottom
    y = max(float(q[0][1]) for q in r)        # the body's underside
    if 0 < b.y_bottom - y < 8:
        y_bottom = y
    return ldraw.PartBounds(box["x"][0], box["x"][1], y_bottom - (b.y_bottom - b.y_top),
                            y_bottom, box["z"][0], box["z"][1])
