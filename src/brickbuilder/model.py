"""Brick model on a stud grid.

Grid coordinates (what tools use):
  x: studs, increasing to the right (as seen from the front)
  z: studs, increasing toward the back (z=0 is the front row)
  y: plates, increasing upward (y=0 is the ground; a brick is 3 plates tall)
A part's (x, y, z) is the minimum corner of its body after rotation.

LDraw coordinates: X = 20*x, Z = 20*z, Y = -8*y (LDraw -Y is up).

Parts can also face sideways or upside down (SNOT): `up` names the world direction the
part's own top (its studs) points, and `rot` spins it about that direction. Such parts
are placed either by grid corner, by an exact LDraw position (`ldu`), or by attaching
one of their receivers onto a stud of a placed part (Model.attach). Their collisions are
checked against their real shape (4 LDU voxels) and connections come from real stud
contact (see geometry.py).
"""

from __future__ import annotations

import copy
import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from . import catalog, geometry, ldraw

FACINGS = {"front": 0, "right": 90, "back": 180, "left": 270}

# World direction (LDraw frame, -Y up, -Z front) for each `up` name, and the rotation that
# turns a part's local top (-Y) to point that way. Columns are images of local X, Y, Z.
DIRECTIONS = {"up": (0, -1, 0), "down": (0, 1, 0), "front": (0, 0, -1), "back": (0, 0, 1),
              "right": (1, 0, 0), "left": (-1, 0, 0)}
_UP_MATRIX = {
    "up": np.eye(3),
    "down": np.diag([1.0, -1.0, -1.0]),
    "front": np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], dtype=float),
    "back": np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=float),
    "right": np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]], dtype=float),
    "left": np.array([[0, 1, 0], [-1, 0, 0], [0, 0, 1]], dtype=float),
}
CLASH_VOXELS = 2  # tolerated shared 4 LDU voxels (curved surfaces that only touch)
CLASH_POINTS = 2  # 2 LDU sample points allowed inside another part (curved faces that touch)


def parse_up(up: str | None) -> str:
    key = (up or "up").strip().lower()
    if key not in _UP_MATRIX:
        raise BuildError(f"up must be one of {', '.join(_UP_MATRIX)}, got '{up}'")
    return key


def orientation(up: str, rot: int) -> np.ndarray:
    """Rotation matrix: spin by `rot` about the part's own vertical axis, then turn its top
    to face `up`."""
    return _UP_MATRIX[parse_up(up)] @ rot_matrix(rot)


def direction_name(d: np.ndarray, strict: bool = True) -> str:
    for name, v in DIRECTIONS.items():
        if np.dot(d, v) > 0.99:
            return name
    if not strict:
        best = max(DIRECTIONS, key=lambda k: float(np.dot(d, DIRECTIONS[k])))
        return f"mostly {best}"
    raise BuildError(f"stud direction {np.round(d, 3).tolist()} is not along an axis")


class BuildError(Exception):
    pass


def rot_matrix(rot: int) -> np.ndarray:
    """Rotation about the vertical axis. rot=90 turns a slope's downhill face
    (local -Z, the front) to face +X (right)."""
    t = math.radians(rot)
    c, s = round(math.cos(t)), round(math.sin(t))
    return np.array([[c, 0, -s], [0, 1, 0], [s, 0, c]], dtype=float)


def parse_rot(rot: int | str | None) -> int:
    if rot is None:
        return 0
    if isinstance(rot, str):
        key = rot.strip().lower()
        if key in FACINGS:
            return FACINGS[key]
        if not re.fullmatch(r"-?\d+", key):
            raise BuildError(f"rot must be 0/90/180/270 or front/right/back/left, got '{rot}'")
        rot = int(key)
    rot = int(rot) % 360
    if rot % 90:
        raise BuildError(f"rot must be a multiple of 90, got {rot}")
    return rot


@dataclass
class Placement:
    id: int
    part: str
    color: int
    x: int
    y: int
    z: int
    rot: int = 0
    up: str = "up"                     # world direction the part's top faces
    ldu: list[float] | None = None     # exact LDraw origin position (free placement)
    matrix: list[float] | None = None  # full rotation (row-major 3x3), for parts on joints

    @property
    def free(self) -> bool:
        return self.up != "up" or self.ldu is not None or self.matrix is not None


@dataclass
class Geometry:
    matrix: np.ndarray
    pos: np.ndarray  # LDraw position of the part origin
    cells: list[tuple[int, int, int]]  # (x, y, z) occupied
    top_studs: set[tuple[int, int]]  # (x, z) columns with a stud on the top level
    bottom_conn: set[tuple[int, int]]  # (x, z) columns that accept studs from below
    y_top: int  # highest occupied level
    shape: catalog.Shape = field(default_factory=catalog.Shape)
    free: bool = False
    part: str = ""
    _vox: set | None = None
    _aabb: tuple | None = None

    # ---- real-shape queries (world LDraw coordinates)

    def voxels(self) -> set[tuple[int, int, int]]:
        if self._vox is None:
            local = geometry.voxels(self.part)
            w = local @ self.matrix.T + self.pos if len(local) else np.zeros((0, 3))
            self._vox = set(map(tuple, np.floor(w / geometry.VOXEL).astype(int).tolist()))
        return self._vox

    def aabb(self) -> tuple[np.ndarray, np.ndarray]:
        """World box of the body in LDU (studs excluded)."""
        if self._aabb is None:
            local = geometry.voxels(self.part)
            if len(local):
                w = local @ self.matrix.T + self.pos
                self._aabb = (w.min(0) - geometry.VOXEL / 2, w.max(0) + geometry.VOXEL / 2)
            else:
                self._aabb = (self.pos.copy(), self.pos.copy())
        return self._aabb

    def studs(self) -> list[tuple[np.ndarray, np.ndarray]]:
        return [(self.matrix @ p + self.pos, self.matrix @ d) for p, d in geometry.studs(self.part)]

    def receivers(self) -> list[tuple[np.ndarray, np.ndarray]]:
        return [(self.matrix @ p + self.pos, self.matrix @ d) for p, d in geometry.receivers(self.part)]

    def joints(self) -> list[tuple[str, np.ndarray, np.ndarray]]:
        """(kind, world centre, world frame) for each ball / socket / hinge."""
        return [(k, self.matrix @ o + self.pos, self.matrix @ f) for k, o, f in geometry.joints(self.part)]

    @property
    def axis_aligned(self) -> bool:
        return bool(np.all(np.isclose(np.abs(self.matrix), np.round(np.abs(self.matrix)), atol=1e-6)))


def _rot(axis: str, deg: float) -> np.ndarray:
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def _free_geometry(p: Placement, pid: str, shape: catalog.Shape) -> Geometry:
    m = np.array(p.matrix, float).reshape(3, 3) if p.matrix is not None else orientation(p.up, p.rot)
    local = geometry.voxels(pid)
    if not len(local):
        raise BuildError(f"{pid} has no solid geometry to place")
    w = local @ m.T
    lo, hi = w.min(0) - geometry.VOXEL / 2, w.max(0) + geometry.VOXEL / 2
    if p.ldu is not None:
        pos = np.array([float(v) for v in p.ldu])
    else:
        # grid placement of a turned part: its body's min corner at (x, z), bottom at level y
        pos = np.array([20 * p.x - lo[0], -8 * p.y - hi[1], 20 * p.z - lo[2]])
    g = Geometry(m, pos, [], set(), set(), 0, shape, free=True, part=pid)
    centres = local @ m.T + pos
    cells = {(math.floor(c[0] / 20), math.floor(-c[1] / 8), math.floor(c[2] / 20)) for c in centres}
    g.cells = sorted(cells)
    g.y_top = max(c[1] for c in cells)
    # keep the placement's grid fields meaningful (sorting, listings) for free parts
    p.x, p.y, p.z = min(c[0] for c in cells), min(c[1] for c in cells), min(c[2] for c in cells)
    return g


def compute_geometry(p: Placement) -> Geometry:
    pid, shape, _ = catalog.lookup(p.part)
    if p.free:
        return _free_geometry(p, pid, shape)
    b = ldraw.part_bounds(pid)
    m = rot_matrix(p.rot)
    corners = np.array([[x, 0, z] for x in (b.x0, b.x1) for z in (b.z0, b.z1)], dtype=float) @ m.T
    mx, mz = corners[:, 0].min(), corners[:, 2].min()
    pos = np.array([20 * p.x - mx, -8 * p.y - b.y_bottom, 20 * p.z - mz])

    nx, nz = round((b.x1 - b.x0) / 20), round((b.z1 - b.z0) / 20)
    h = b.height_plates
    cells, top, bottom = [], set(), set()
    for ix in range(nx):
        for iz in range(nz):
            local = np.array([b.x0 + 20 * ix + 10, 0, b.z0 + 20 * iz + 10])
            w = m @ local + pos
            gx, gz = math.floor(w[0] / 20), math.floor(w[2] / 20)
            for gy in range(p.y, p.y + h):
                cells.append((gx, gy, gz))
            high_row = iz >= nz - shape.flat_rows
            if shape.kind == "box":
                has_stud = shape.studs
            elif shape.kind == "slope":
                has_stud = high_row
            elif shape.kind == "slope_inv":
                has_stud = True
            else:
                has_stud = False
            if has_stud:
                top.add((gx, gz))
            if shape.kind != "slope_inv" or high_row:
                bottom.add((gx, gz))
    return Geometry(m, pos, cells, top, bottom, p.y + h - 1, shape, part=pid)


class Model:
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.parts: dict[int, Placement] = {}
        self.next_id = 1
        self._geom: dict[int, Geometry] = {}
        self.occ: dict[tuple[int, int, int], int] = {}          # grid cells of upright grid parts
        self.free_cells: dict[tuple[int, int, int], set[int]] = {}  # cells touched by free parts
        self._history: list[tuple[dict[int, Placement], int]] = []

    # ------------------------------------------------------------ editing

    def checkpoint(self) -> None:
        self._history.append((copy.deepcopy(self.parts), self.next_id))
        del self._history[:-50]

    def undo(self) -> bool:
        if not self._history:
            return False
        parts, next_id = self._history.pop()
        self._rebuild(parts, next_id)
        return True

    def _rebuild(self, parts: dict[int, Placement], next_id: int) -> None:
        self.parts, self.next_id = {}, next_id
        self._geom.clear()
        self.occ.clear()
        self.free_cells.clear()
        for p in parts.values():
            self._insert(p)

    def _insert(self, p: Placement, g: Geometry | None = None) -> None:
        g = g or compute_geometry(p)
        self.parts[p.id] = p
        self._geom[p.id] = g
        if g.free:
            for c in g.cells:
                self.free_cells.setdefault(c, set()).add(p.id)
        else:
            for c in g.cells:
                self.occ[c] = p.id

    def geometry(self, pid: int) -> Geometry:
        return self._geom[pid]

    def _shape_clashes(self, g: Geometry, only_free: bool, ignore: set[int] | None = None) -> list[int]:
        """Parts whose real shape overlaps g's. Points filling each part every 2 LDU are
        tested against the other part's solid (in its own frame) with a 1 LDU margin, both
        ways round, so touching is fine and any real interpenetration is caught - also for
        tilted parts on joints."""
        lo, hi = g.aabb()
        mine = geometry.samples(g.part) @ g.matrix.T + g.pos
        hits = []
        for i, other in self._geom.items():
            if (only_free and not other.free) or (ignore and i in ignore):
                continue
            olo, ohi = other.aabb()
            if np.any(olo >= hi - 0.5) or np.any(ohi <= lo + 0.5):
                continue
            theirs = geometry.samples(other.part) @ other.matrix.T + other.pos
            if _penetration(mine, other) + _penetration(theirs, g) > CLASH_POINTS:
                hits.append(i)
        return hits

    def add(self, part: str, color: int | str, x: int, y: int, z: int, rot: int | str | None = 0,
            up: str | None = "up", ldu: list[float] | None = None, matrix=None,
            ignore: set[int] | None = None) -> Placement:
        """Place a part. Upright parts go on the grid by (x, y, z, rot); turned parts take `up`;
        `ldu` gives an exact LDraw position and `matrix` (3x3) any rotation. Parts in `ignore`
        are not checked for collision (a joint partner, whose ball sits inside the socket)."""
        pid, _, _ = catalog.lookup(part)
        colour = ldraw.resolve_colour(color)
        mat = None if matrix is None else [round(float(v), 9) for v in np.asarray(matrix, float).ravel()]
        p = Placement(self.next_id, pid, colour.code, int(x), int(y), int(z), parse_rot(rot), parse_up(up),
                      None if ldu is None else [float(v) for v in ldu], mat)
        g = compute_geometry(p)
        if p.ldu is not None:
            where = f"ldu={_fmt_vec(p.ldu)} " + ("tilted" if mat is not None else f"up={p.up} rot={p.rot}")
        else:
            where = f"x={x} y={y} z={z} rot={p.rot}" + ("" if p.up == "up" else f" up={p.up}")
        if g.free:
            clashes = self._shape_clashes(g, only_free=False, ignore=ignore)
            if g.aabb()[1][1] > 0.5:
                raise BuildError(f"{pid} at {where} would go below the ground")
        else:
            clashes = sorted({self.occ[c] for c in g.cells if c in self.occ})
            if self.free_cells and any(c in self.free_cells for c in g.cells):
                clashes += self._shape_clashes(g, only_free=True)
            if min(c[1] for c in g.cells) < 0:
                raise BuildError(f"{pid} at y={y} would go below the ground (y<0)")
        if clashes:
            others = ", ".join(f"#{i} {self.parts[i].part}" for i in sorted(set(clashes))[:5])
            raise BuildError(f"{pid} at {where} collides with {others}")
        self.next_id += 1
        self._insert(p, g)
        return p

    def attach(self, part: str, color: int | str, to_id: int, stud: int, receiver: int = 0,
               rot: int | str | None = 0) -> Placement:
        """Press one of the new part's receivers (underside stud holes) onto stud number
        `stud` of placed part `to_id`. The new part's top then faces the way that stud
        points; `rot` spins it about that direction. Works on tilted parts too (parts on
        joints): the new part then follows the target's tilt."""
        if to_id not in self.parts:
            raise BuildError(f"No part #{to_id}")
        tg = self._geom[to_id]
        target = tg.studs()
        if not 0 <= stud < len(target):
            raise BuildError(f"#{to_id} {self.parts[to_id].part} has {len(target)} studs (0..{len(target) - 1}), not {stud}")
        pid, _, _ = catalog.lookup(part)
        recv = geometry.receivers(pid)
        if not recv:
            raise BuildError(f"{pid} has no underside that can sit on a stud")
        if not 0 <= receiver < len(recv):
            raise BuildError(f"{pid} has {len(recv)} receivers (0..{len(recv) - 1}), not {receiver}")
        spos, sdir = target[stud]
        r = parse_rot(rot)
        if tg.axis_aligned:
            up = direction_name(sdir)
            pos = spos - orientation(up, r) @ recv[receiver][0]
            return self.add(pid, color, 0, 0, 0, r, up, [round(float(v), 3) for v in pos])
        # tilted target: work in its own frame, where its studs are axis-aligned
        local_dir = geometry.studs(self.parts[to_id].part)[stud][1]
        m = tg.matrix @ orientation(direction_name(local_dir), r)
        pos = spos - m @ recv[receiver][0]
        return self.add(pid, color, 0, 0, 0, r, "up", [float(v) for v in pos], matrix=m)

    def attach_joint(self, part: str, color: int | str, to_id: int, to_joint: int = 0, joint: int = 0,
                     bend: float = 0, swing: float = 0, twist: float = 0) -> Placement:
        """Connect the new part's joint `joint` to joint `to_joint` of placed part `to_id`:
        a ball into a socket (or the other way round), or a hinge top onto a hinge base.
        Angles are in degrees, in the target joint's frame. Ball joint: `bend` and `swing`
        tilt the new part away from straight (about the joint's X and Y axes, at most 45
        degrees combined) and `twist` turns it about the joint's axis. Hinge: `bend` is the
        hinge angle (any value)."""
        if to_id not in self.parts:
            raise BuildError(f"No part #{to_id}")
        tj = self._geom[to_id].joints()
        if not 0 <= to_joint < len(tj):
            raise BuildError(f"#{to_id} {self.parts[to_id].part} has {len(tj)} joints (0..{len(tj) - 1}), not {to_joint}")
        pid, _, _ = catalog.lookup(part)
        nj = geometry.joints(pid)
        if not 0 <= joint < len(nj):
            raise BuildError(f"{pid} has {len(nj)} joints (0..{len(nj) - 1}), not {joint}")
        tkind, centre, frame = tj[to_joint]
        nkind, origin, nframe = nj[joint]
        if (tkind, nkind) not in geometry.JOINT_PAIRS:
            raise BuildError(f"a {nkind} does not connect to a {tkind}")
        if tkind in ("ball", "socket"):
            user = _rot("x", bend) @ _rot("y", swing) @ _rot("z", twist)
            tilt = math.degrees(math.acos(max(-1.0, min(1.0, user[2, 2]))))
            if tilt > 45.5:
                raise BuildError(f"a joint-8 ball joint tilts about 45 degrees at most; bend/swing give {tilt:.0f}")
            m = frame @ user @ np.diag([-1.0, 1.0, -1.0]) @ nframe.T  # stems opposite, tops the same way up
        else:
            m = frame @ _rot("x", bend) @ nframe.T
        pos = centre - m @ origin
        return self.add(pid, color, 0, 0, 0, 0, "up", [float(v) for v in pos], matrix=m, ignore={to_id})

    def remove(self, ids: list[int]) -> list[int]:
        removed = []
        for i in ids:
            if i in self.parts:
                g = self._geom[i]
                for c in g.cells:
                    if g.free:
                        holders = self.free_cells.get(c)
                        if holders:
                            holders.discard(i)
                            if not holders:
                                del self.free_cells[c]
                    elif self.occ.get(c) == i:
                        del self.occ[c]
                del self.parts[i], self._geom[i]
                removed.append(i)
        return removed

    def parts_in_region(self, x0, x1, y0, y1, z0, z1) -> list[int]:
        inside = lambda c: x0 <= c[0] <= x1 and y0 <= c[1] <= y1 and z0 <= c[2] <= z1
        hits = {pid for c, pid in self.occ.items() if inside(c)}
        hits |= {pid for c, pids in self.free_cells.items() if inside(c) for pid in pids}
        return sorted(hits)

    def clear(self) -> None:
        self._rebuild({}, 1)

    # ------------------------------------------------------------ queries

    def bounds(self) -> tuple[int, int, int, int, int, int] | None:
        cells = list(self.occ.keys()) + list(self.free_cells.keys())
        if not cells:
            return None
        xs, ys, zs = zip(*cells)
        return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)

    def connections(self) -> dict[int, set[int]]:
        """Stud connections between parts (undirected adjacency), from real stud contact:
        a stud of one part sitting in a receiver of another, facing opposite ways. Works for
        studs pointing any direction (SNOT)."""
        adj: dict[int, set[int]] = {i: set() for i in self.parts}
        holes: dict[tuple[int, int, int], list[tuple[int, np.ndarray]]] = {}
        for i, g in self._geom.items():
            for pos, d in g.receivers():
                holes.setdefault(_key(pos), []).append((i, d))
        for i, g in self._geom.items():
            for pos, d in g.studs():
                for j, rd in holes.get(_key(pos), ()):
                    if j != i and float(np.dot(d, rd)) < -0.9:
                        adj[i].add(j)
                        adj[j].add(i)
        for i, j in self._joint_links():
            adj[i].add(j)
            adj[j].add(i)
        return adj

    @staticmethod
    def _joints_mate(k1, c1, f1, k2, c2, f2) -> bool:
        if (k1, k2) not in geometry.JOINT_PAIRS or np.linalg.norm(c1 - c2) > 1.0:
            return False
        return not k1.startswith("hinge") or abs(float(np.dot(f1[:, 0], f2[:, 0]))) >= 0.99

    def _joint_links(self) -> list[tuple[int, int]]:
        """Pairs of parts joined by a ball joint or a hinge (centres together; hinge axes
        parallel)."""
        js = [(i, k, c, f) for i, g in self._geom.items() for k, c, f in g.joints()]
        links = []
        for a in range(len(js)):
            i, k1, c1, f1 = js[a]
            for b in range(a + 1, len(js)):
                j, k2, c2, f2 = js[b]
                if i != j and self._joints_mate(k1, c1, f1, k2, c2, f2):
                    links.append((i, j))
        return links

    def joint_usage(self, pid: int) -> list[int | None]:
        """For each joint of part pid: the id of the part joined to it, or None."""
        out = []
        for k, c, f in self._geom[pid].joints():
            hit = None
            for j, g in self._geom.items():
                if j != pid and any(self._joints_mate(k, c, f, k2, c2, f2) for k2, c2, f2 in g.joints()):
                    hit = j
            out.append(hit)
        return out

    def stud_usage(self, pid: int) -> list[int | None]:
        """For each stud of part pid: the id of the part plugged onto it, or None."""
        holes: dict[tuple[int, int, int], list[tuple[int, np.ndarray]]] = {}
        for i, g in self._geom.items():
            if i == pid:
                continue
            for pos, d in g.receivers():
                holes.setdefault(_key(pos), []).append((i, d))
        out = []
        for pos, d in self._geom[pid].studs():
            hit = next((j for j, rd in holes.get(_key(pos), ()) if float(np.dot(d, rd)) < -0.9), None)
            out.append(hit)
        return out

    def overlaps(self, limit: int = 50) -> list[tuple[int, int, int]]:
        """Pairs of parts whose real shapes interpenetrate: (id, id, sample points inside).
        Joint partners (a ball inside its socket) are expected to overlap and are skipped."""
        joined = {tuple(sorted(p)) for p in self._joint_links()}
        buckets: dict[tuple[int, int, int], list[int]] = {}
        for i, g in self._geom.items():
            lo, hi = g.aabb()
            a, b = np.floor(lo / 80).astype(int), np.floor(hi / 80).astype(int)
            for bx in range(a[0], b[0] + 1):
                for by in range(a[1], b[1] + 1):
                    for bz in range(a[2], b[2] + 1):
                        buckets.setdefault((bx, by, bz), []).append(i)
        seen, out = set(), []
        pts = {}
        for ids in buckets.values():
            for x in range(len(ids)):
                for y in range(x + 1, len(ids)):
                    i, j = sorted((ids[x], ids[y]))
                    if (i, j) in seen or (i, j) in joined:
                        continue
                    seen.add((i, j))
                    gi, gj = self._geom[i], self._geom[j]
                    lo1, hi1 = gi.aabb()
                    lo2, hi2 = gj.aabb()
                    if np.any(lo1 >= hi2 - 0.5) or np.any(lo2 >= hi1 - 0.5):
                        continue
                    for k, g in ((i, gi), (j, gj)):
                        if k not in pts:
                            pts[k] = geometry.samples(g.part) @ g.matrix.T + g.pos
                    n = _penetration(pts[i], gj) + _penetration(pts[j], gi)
                    if n > CLASH_POINTS:
                        out.append((i, j, n))
                        if len(out) >= limit:
                            return out
        return out

    def grounded(self, pid: int) -> bool:
        g = self._geom[pid]
        return g.aabb()[1][1] >= -0.5 if g.free else self.parts[pid].y == 0

    def check(self) -> dict:
        adj = self.connections()
        seen, groups = set(), []
        for start in self.parts:
            if start in seen:
                continue
            stack, group = [start], []
            seen.add(start)
            while stack:
                n = stack.pop()
                group.append(n)
                for m in adj[n]:
                    if m not in seen:
                        seen.add(m)
                        stack.append(m)
            groups.append(sorted(group))
        groups.sort(key=len, reverse=True)
        grounded = lambda grp: any(self.grounded(i) for i in grp)
        floating = [grp for grp in groups if not grounded(grp)]
        # Parts that sit only on tiles / slopes rest without being attached.
        return {
            "parts": len(self.parts),
            "connected_groups": len(groups),
            "group_sizes": [len(g) for g in groups[:10]],
            "floating_groups": floating[:10],
            "loose_grounded_groups": [g for g in groups[1:] if grounded(g)][:10],
        }

    def layer_map(self, y: int, legend: dict[int, str]) -> list[str]:
        b = self.bounds()
        if b is None:
            return []
        x0, x1, _, _, z0, z1 = b
        rows = []
        for z in range(z1, z0 - 1, -1):  # back row first, front row last
            row = []
            for x in range(x0, x1 + 1):
                pid = self.occ.get((x, y, z))
                if pid is None and (x, y, z) in self.free_cells:
                    pid = min(self.free_cells[(x, y, z)])
                row.append("." if pid is None else legend.setdefault(self.parts[pid].color, _next_char(legend)))
            rows.append("".join(row))
        return rows

    # ------------------------------------------------------------ persistence

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "next_id": self.next_id,
            "parts": [asdict(p) for p in self.parts.values()],
        }

    @classmethod
    def from_json(cls, data: dict) -> "Model":
        m = cls(data["name"], data.get("description", ""))
        m._rebuild({p["id"]: Placement(**p) for p in data["parts"]}, data.get("next_id", 1))
        return m

    def save(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{safe_name(self.name)}.json"
        path.write_text(json.dumps(self.to_json(), indent=1))
        return path

    def to_ldr(self, legacy_ids: bool = False) -> str:
        lines = [
            f"0 {self.name}",
            f"0 Name: {safe_name(self.name)}.ldr",
            "0 Author: brickbuilder-mcp",
            f"0 // {self.description}" if self.description else None,
            f"0 // Exported {datetime.now():%Y-%m-%d %H:%M}",
        ]
        lines = [line for line in lines if line]
        # One build step per plate level, bottom to top.
        ordered = sorted(self.parts.values(), key=lambda p: (p.y, p.z, p.x))
        last_y = None
        for p in ordered:
            if last_y is not None and p.y != last_y:
                lines.append("0 STEP")
            last_y = p.y
            g = self._geom[p.id]
            m = g.matrix
            nums = [*g.pos, *m.flatten()]
            part = legacy_part_id(p.part) if legacy_ids else p.part
            lines.append(f"1 {p.color} " + " ".join(_fmt(v) for v in nums) + f" {part}.dat")
        lines.append("0 STEP")
        return "\n".join(lines) + "\n"


def legacy_part_id(pid: str) -> str:
    """Map e.g. 3023b -> 3023 when the plain number is an alias of this part."""
    m = re.fullmatch(r"(\d+)([a-z])", pid)
    if m and ldraw.resolve_moved(m.group(1)) == pid:
        return m.group(1)
    return pid


def _fmt(v: float) -> str:
    v = round(float(v), 3)
    return str(int(v)) if v == int(v) else f"{v:g}"


def _penetration(world_pts: np.ndarray, g: Geometry) -> int:
    """How many world points lie inside g's solid (more than 1 LDU in)."""
    lo, hi = g.aabb()
    sel = np.all((world_pts > lo - 1) & (world_pts < hi + 1), axis=1)
    if not sel.any():
        return 0
    local = (world_pts[sel] - g.pos) @ g.matrix   # inverse of a rotation is its transpose
    return int(geometry.contains(g.part, local).sum())


def _fmt_vec(v) -> str:
    return "[" + ", ".join(_fmt(x) for x in v) + "]"


def _key(pos: np.ndarray) -> tuple[int, int, int]:
    """Connector position rounded to whole LDU (stud and receiver must coincide)."""
    return tuple(int(round(float(c))) for c in pos)


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "model"


_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789@$%&*+=?"


def _next_char(legend: dict) -> str:
    used = set(legend.values())
    for ch in _CHARS:
        if ch not in used:
            return ch
    return "#"
