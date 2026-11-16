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

# Joint primitives: (kind) by file name. The primitive's origin is the joint centre and its
# frame is the joint frame: a joint-8 ball sits at the origin with its stem along +Z; a
# joint-8 socket cup is centred on the origin, opening toward -Z (its part is on +Z).
_JOINT_PRIMS = {"joint8ball.dat": "ball", "joint8socket1.dat": "socket",
                "joint8socket2.dat": "socket", "joint8socket3.dat": "socket"}
# Joints LDraw has no primitive for: part -> [(kind, origin, frame columns X, Y, Z)].
# Hinge 3937 + 6134: both pivot about the line along local X through (0, 10, 0).
_JOINT_OVERRIDES = {
    "3937": [("hinge_base", (0, 10, 0), np.eye(3))],
    "6134": [("hinge_top", (0, 10, 0), np.eye(3))],
}
JOINT_PAIRS = {("ball", "socket"), ("socket", "ball"), ("hinge_base", "hinge_top"), ("hinge_top", "hinge_base")}

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
    """Joint primitives inside one LDraw file: ((kind, origin (3,), frame (3,3)), ...)."""
    name = name.strip().lower().replace("\\", "/")
    base = name.rsplit("/", 1)[-1]
    if base in _JOINT_PRIMS:
        return ((_JOINT_PRIMS[base], np.zeros(3), np.eye(3)),)
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


@functools.lru_cache(maxsize=4096)
def joints(part: str) -> tuple:
    """Joints of a part in its local frame: ((kind, origin (3,), frame (3,3)), ...).
    Kinds: ball, socket (joint-8 system), hinge_base, hinge_top (3937 / 6134)."""
    pid = ldraw.normalize_part_id(part)
    if pid in _JOINT_OVERRIDES:
        return tuple((k, np.array(o, float), np.array(f, float)) for k, o, f in _JOINT_OVERRIDES[pid])
    return _joint_refs(pid + ".dat")


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
    x0 = b.x0 - VOXEL * math.ceil((b.x0 - lo[0] - 1e-6) / VOXEL)
    z0 = b.z0 - VOXEL * math.ceil((b.z0 - lo[2] - 1e-6) / VOXEL)
    nx = int(math.floor((hi[0] - 1e-6 - x0) / VOXEL)) + 1
    nz = int(math.floor((hi[2] - 1e-6 - z0) / VOXEL)) + 1
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


def contains(part: str, pts: np.ndarray, margin: float = 1.0) -> np.ndarray:
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
    return inside & (pts[:, 1] > lo_y + margin) & (pts[:, 1] < hi_y - margin)


@functools.lru_cache(maxsize=4096)
def samples(part: str) -> np.ndarray:
    """Points filling the solid every 2 LDU (each 4 LDU voxel split in eight)."""
    v = voxels(part)
    if not len(v):
        return v
    offs = np.array([[dx, dy, dz] for dx in (-1, 1) for dy in (-1, 1) for dz in (-1, 1)], float)
    return (v[:, None, :] + offs[None, :, :]).reshape(-1, 3)


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
