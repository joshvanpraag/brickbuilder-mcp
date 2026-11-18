"""Software preview renderer: simplified brick shapes, z-buffered, outlined.

Render space is LDraw with Y flipped so +Y is up: (X, Y, Z) = (x_ldu, -y_ldu, z_ldu).
The front of the model faces -Z.
"""

from __future__ import annotations

import io
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import ldraw
from .model import Model

VIEWS = {
    "front": (0, 0), "back": (180, 0), "left": (-90, 0), "right": (90, 0), "top": (0, 90),
    "iso_front_left": (-45, 30), "iso_front_right": (45, 30),
    "iso_back_left": (-135, 30), "iso_back_right": (135, 30),
}
DEFAULT_VIEWS = ["iso_front_left", "iso_back_right", "front", "top"]
BACKGROUND = np.array([226, 229, 233], dtype=float)
LIGHT = np.array([-0.45, 1.0, -0.65]) / np.linalg.norm([-0.45, 1.0, -0.65])


def _profile(shape, b) -> list[tuple[float, float]]:
    """Convex cross-section in the local (z, y) plane, y down."""
    z0, z1, yt, yb = b.z0, b.z1, b.y_top, b.y_bottom
    zf = z1 - 20 * shape.flat_rows
    lip = min(4, (yb - yt) / 4)
    if shape.kind == "slope":
        if shape.flat_rows == 0:
            return [(z1, yt), (z1, yb), (z0, yb)]
        return [(zf, yt), (z1, yt), (z1, yb), (z0, yb), (z0, yb - lip)]
    if shape.kind == "slope_inv":
        return [(z0, yt), (z1, yt), (z1, yb), (zf, yb), (z0, yt + lip)]
    if shape.kind == "ridge":
        zm = (z0 + z1) / 2
        return [(zm, yt), (z1, yb - lip), (z1, yb), (z0, yb), (z0, yb - lip)]
    return [(z0, yt), (z1, yt), (z1, yb), (z0, yb)]


class Mesh:
    def __init__(self):
        self.tris: list[np.ndarray] = []
        self.colors: list[np.ndarray] = []
        self.fids: list[int] = []
        self._next_fid = 1

    def polygon(self, pts: np.ndarray, color: np.ndarray, inside: np.ndarray, fid: int | None = None) -> None:
        """Add a convex planar polygon, oriented so its normal points away from `inside`."""
        if fid is None:
            fid = self.new_fid()
        n = np.cross(pts[1] - pts[0], pts[2] - pts[0])
        if np.dot(n, pts.mean(0) - inside) < 0:
            pts = pts[::-1]
        for i in range(1, len(pts) - 1):
            self.tris.append(np.array([pts[0], pts[i], pts[i + 1]]))
            self.colors.append(color)
            self.fids.append(fid)

    def new_fid(self) -> int:
        self._next_fid += 1
        return self._next_fid


def build_mesh(model: Model) -> Mesh:
    mesh = Mesh()
    flip = np.array([1.0, -1.0, 1.0])
    table = ldraw.colours()
    for pid, p in model.parts.items():
        g = model.geometry(pid)
        b = ldraw.part_bounds(p.part)
        col = table[p.color]
        rgb = np.array(col.rgb, dtype=float)
        if col.alpha < 255:
            rgb = rgb * 0.6 + 255 * 0.4

        def world(local: np.ndarray) -> np.ndarray:
            return (local @ g.matrix.T + g.pos) * flip

        prof = _profile(g.shape, b)
        left = np.array([[b.x0, y, z] for z, y in prof], dtype=float)
        right = np.array([[b.x1, y, z] for z, y in prof], dtype=float)
        wl, wr = world(left), world(right)
        centre = np.vstack([wl, wr]).mean(0)
        mesh.polygon(wl, rgb, centre)
        mesh.polygon(wr, rgb, centre)
        n = len(prof)
        for i in range(n):
            j = (i + 1) % n
            mesh.polygon(np.array([wl[i], wl[j], wr[j], wr[i]]), rgb, centre)

        top_y = 8 * (g.y_top + 1)
        for (x, z) in g.top_studs:
            if (x, g.y_top + 1, z) in model.occ:
                continue
            cx, cz = 20 * x + 10, 20 * z + 10
            ang = np.linspace(0, 2 * math.pi, 9)[:-1]
            ring = np.stack([cx + 6 * np.cos(ang), np.zeros(8), cz + 6 * np.sin(ang)], 1)
            lo, hi = ring + [0, top_y, 0], ring + [0, top_y + 4, 0]
            inside = np.array([cx, top_y + 2, cz])
            mesh.polygon(hi, rgb * 1.04, inside)
            side = mesh.new_fid()
            for i in range(8):
                j = (i + 1) % 8
                mesh.polygon(np.array([lo[i], lo[j], hi[j], hi[i]]), rgb, inside, fid=side)
    return mesh


def _camera(az: float, el: float):
    a, e = math.radians(az), math.radians(el)
    v = np.array([math.sin(a) * math.cos(e), math.sin(e), -math.cos(a) * math.cos(e)])
    r = np.array([math.cos(a), 0.0, math.sin(a)])
    u = np.array([-math.sin(e) * math.sin(a), math.cos(e), math.sin(e) * math.cos(a)])
    return r, u, v


def render_view(mesh: Mesh, az: float, el: float, width: int, height: int, ss: int = 2) -> Image.Image:
    W, H = width * ss, height * ss
    img = np.tile(BACKGROUND, (H, W, 1))
    if not mesh.tris:
        return Image.fromarray(img.astype(np.uint8)).resize((width, height))
    tris = np.array(mesh.tris)
    colors = np.array(mesh.colors)
    fids = np.array(mesh.fids)
    r, u, v = _camera(az, el)

    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    ok = lengths > 1e-9
    tris, colors, fids, normals = tris[ok], colors[ok], fids[ok], normals[ok] / lengths[ok, None]
    visible = normals @ v > 1e-6
    tris, colors, fids, normals = tris[visible], colors[visible], fids[visible], normals[visible]

    shade = 0.42 + 0.48 * np.clip(normals @ LIGHT, 0, 1) + 0.18 * np.clip(normals @ v, 0, 1)
    shaded = np.clip(colors * shade[:, None], 0, 255)

    sx, sy, depth = tris @ r, tris @ u, tris @ v
    allx, ally = np.array(mesh.tris) @ r, np.array(mesh.tris) @ u
    margin = 0.06
    span_x = max(allx.max() - allx.min(), 1e-6)
    span_y = max(ally.max() - ally.min(), 1e-6)
    scale = min(W * (1 - 2 * margin) / span_x, H * (1 - 2 * margin) / span_y)
    cx, cy = (allx.max() + allx.min()) / 2, (ally.max() + ally.min()) / 2
    px = (sx - cx) * scale + W / 2
    py = H / 2 - (sy - cy) * scale

    zbuf = np.full((H, W), -np.inf)
    fbuf = np.zeros((H, W), dtype=np.int64)
    for i in range(len(px)):
        x0, x1, x2 = px[i]
        y0, y1, y2 = py[i]
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-9:
            continue
        minx, maxx = max(int(math.floor(min(x0, x1, x2))), 0), min(int(math.ceil(max(x0, x1, x2))), W - 1)
        miny, maxy = max(int(math.floor(min(y0, y1, y2))), 0), min(int(math.ceil(max(y0, y1, y2))), H - 1)
        if minx > maxx or miny > maxy:
            continue
        xs = np.arange(minx, maxx + 1) + 0.5
        ys = np.arange(miny, maxy + 1)[:, None] + 0.5
        w0 = ((x1 - xs) * (y2 - ys) - (x2 - xs) * (y1 - ys)) / area
        w1 = ((x2 - xs) * (y0 - ys) - (x0 - xs) * (y2 - ys)) / area
        w2 = 1 - w0 - w1
        eps = -1e-4
        inside = (w0 >= eps) & (w1 >= eps) & (w2 >= eps)
        if not inside.any():
            continue
        d0, d1, d2 = depth[i]
        z = w0 * d0 + w1 * d1 + w2 * d2
        region = zbuf[miny:maxy + 1, minx:maxx + 1]
        m = inside & (z > region + 1e-3)
        region[m] = z[m]
        fbuf[miny:maxy + 1, minx:maxx + 1][m] = fids[i]
        img[miny:maxy + 1, minx:maxx + 1][m] = shaded[i]

    edge = np.zeros((H, W), dtype=bool)
    edge[:, :-1] |= fbuf[:, :-1] != fbuf[:, 1:]
    edge[:-1, :] |= fbuf[:-1, :] != fbuf[1:, :]
    edge[:, 1:] |= edge[:, :-1] & (fbuf[:, 1:] == 0)  # thicken silhouette onto background side
    img[edge] = img[edge] * 0.35 + np.array([20, 20, 25]) * 0.65
    out = Image.fromarray(img.astype(np.uint8))
    return out.resize((width, height), Image.Resampling.LANCZOS) if ss > 1 else out


def parse_view(name: str) -> tuple[str, float, float]:
    key = name.strip().lower()
    if key in VIEWS:
        return key, *VIEWS[key]
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", key)
    if m:
        return key, float(m.group(1)), float(m.group(2))
    raise ValueError(f"Unknown view '{name}'. Use {', '.join(VIEWS)} or 'azimuth,elevation' in degrees")


# ---------------------------------------------------------------- real geometry


def real_scene(model: Model):
    """Every part's actual LDraw polygons and edge lines in render space (+Y up)."""
    from . import geometry
    flip = np.array([1.0, -1.0, 1.0])
    P, PC, L, LC, PI = [], [], [], [], []
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
    cat = lambda xs, shape: np.concatenate(xs) if xs else np.zeros(shape)
    return (cat(P, (0, 4, 3)), cat(PC, (0,)).astype(int), cat(L, (0, 2, 3)), cat(LC, (0,)).astype(int),
            cat(PI, (0,)).astype(int))


def _raster(px: np.ndarray, py: np.ndarray, pz: np.ndarray, W: int, H: int, zbuf: np.ndarray,
            write=None) -> None:
    """Rasterise triangles (N, 3) of pixel coords / depths into zbuf (flattened, larger depth =
    nearer). Vectorised scanline: for every triangle and pixel row, the covered x-span is
    computed from its edges, and only those pixels are generated (no wasted bounding-box
    samples on long thin triangles). Without `write`, keeps the nearest depth per pixel; with
    `write(pix, tri)`, calls it for the samples that are the nearest surface (second pass)."""
    area = (px[:, 1] - px[:, 0]) * (py[:, 2] - py[:, 0]) - (px[:, 2] - px[:, 0]) * (py[:, 1] - py[:, 0])
    ok = (np.abs(area) > 1e-9) & (px.max(1) >= 0) & (px.min(1) < W) & (py.max(1) >= 0) & (py.min(1) < H)
    idx_all = np.nonzero(ok)[0]
    # depth as a plane over the screen: z = za * x + zb * y + zc
    ax, ay, az_ = px[:, 0], py[:, 0], pz[:, 0]
    bx, by, bz = px[:, 1] - ax, py[:, 1] - ay, pz[:, 1] - az_
    cx_, cy_, cz = px[:, 2] - ax, py[:, 2] - ay, pz[:, 2] - az_
    with np.errstate(divide="ignore", invalid="ignore"):
        za = (bz * cy_ - cz * by) / area
        zb = (cz * bx - bz * cx_) / area
        zc = az_ - za * ax - zb * ay
    r0 = np.clip(np.ceil(py.min(1) - 0.5), 0, H - 1).astype(int)
    r1 = np.clip(np.floor(py.max(1) - 0.5), 0, H - 1).astype(int)
    rows_per = np.maximum(r1 - r0 + 1, 0)
    # process in chunks of triangles so the expanded arrays stay a manageable size
    order = idx_all
    cum = np.cumsum(rows_per[order])
    start = 0
    while start < len(order):
        stop = int(np.searchsorted(cum, (cum[start - 1] if start else 0) + 2_000_000, side="right"))
        stop = max(stop, start + 1)
        idx = order[start:stop]
        start = stop
        n = rows_per[idx]
        if not n.sum():
            continue
        tri = np.repeat(idx, n)
        yrow = np.repeat(r0[idx], n) + (np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n))
        yc = yrow + 0.5
        lo = np.full(len(tri), np.inf)
        hi = np.full(len(tri), -np.inf)
        for e0, e1 in ((0, 1), (1, 2), (2, 0)):
            x0, y0 = px[tri, e0], py[tri, e0]
            x1, y1 = px[tri, e1], py[tri, e1]
            crosses = (np.minimum(y0, y1) <= yc) & (np.maximum(y0, y1) >= yc) & (y0 != y1)
            with np.errstate(divide="ignore", invalid="ignore"):
                xe = x0 + (yc - y0) * (x1 - x0) / (y1 - y0)
            lo = np.where(crosses, np.minimum(lo, xe), lo)
            hi = np.where(crosses, np.maximum(hi, xe), hi)
        c0 = np.clip(np.ceil(lo - 0.5), 0, W).astype(np.int64, copy=False)
        c1 = np.clip(np.floor(hi - 0.5), -1, W - 1).astype(np.int64, copy=False)
        cnt = np.where(np.isfinite(lo) & np.isfinite(hi), np.maximum(c1 - c0 + 1, 0), 0)
        if not cnt.sum():
            continue
        t2 = np.repeat(tri, cnt)
        y2 = np.repeat(yrow, cnt)
        x2 = np.repeat(c0, cnt) + (np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt))
        zz = za[t2] * (x2 + 0.5) + zb[t2] * (y2 + 0.5) + zc[t2]
        pix = y2 * W + x2
        if write is None:
            np.maximum.at(zbuf, pix, zz)
        else:
            front = zz >= zbuf[pix] - 1e-6
            write(pix[front], t2[front])


def render_real_view(scene, az: float, el: float, width: int, height: int, ss: int = 2,
                     ghost=None, frame=None) -> Image.Image:
    """Depth-buffered render of real part shapes: every pixel shows the nearest surface, so
    parts never appear to pass through each other. Part outlines where parts meet, plus the
    parts' own LDraw edge lines where they are visible.

    ghost: part ids drawn faded (building instructions: what was built in earlier steps).
    frame: 3D points (render space) to fit the picture to instead of the scene itself, so a
    series of pictures keeps the same scale and position."""
    from . import geometry
    P, PC, L, LC, PI = scene
    W, H = width * ss, height * ss
    if not len(P):
        return Image.new("RGB", (width, height), tuple(int(c) for c in BACKGROUND))
    r, u, v = _camera(az, el)
    tris = np.concatenate([P[:, [0, 1, 2]], P[:, [0, 2, 3]]])
    cols = np.concatenate([PC, PC])
    pids = np.concatenate([PI, PI])
    sx, sy, sd = tris @ r, tris @ u, tris @ v
    if frame is not None:
        allx, ally = np.asarray(frame) @ r, np.asarray(frame) @ u
    else:
        allx, ally = np.concatenate([sx.ravel(), (L @ r).ravel()]), np.concatenate([sy.ravel(), (L @ u).ravel()])
    margin = 0.06
    span = max(allx.max() - allx.min(), 1e-6), max(ally.max() - ally.min(), 1e-6)
    scale = min(W * (1 - 2 * margin) / span[0], H * (1 - 2 * margin) / span[1])
    cx, cy = (allx.max() + allx.min()) / 2, (ally.max() + ally.min()) / 2
    px, py = (sx - cx) * scale + W / 2, H / 2 - (sy - cy) * scale

    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n = np.linalg.norm(normals, axis=1)
    n[n == 0] = 1
    normals = normals / n[:, None]
    facing = np.where((normals @ v)[:, None] < 0, -normals, normals)  # two-sided
    shade = 0.42 + 0.48 * np.clip(facing @ LIGHT, 0, 1) + 0.18 * np.clip(facing @ v, 0, 1)
    table = ldraw.colours()
    codes, inverse = np.unique(cols, return_inverse=True)
    pal = np.array([table[int(c)].rgb if int(c) in table else (200, 200, 200) for c in codes], float)
    tri_rgb = np.clip(pal[inverse] * shade[:, None], 0, 255)
    if ghost:
        faded = np.isin(pids, np.fromiter(ghost, dtype=np.int64))
        tri_rgb[faded] = tri_rgb[faded] * 0.35 + np.array([238, 240, 243]) * 0.65

    zbuf = np.full(W * H, -np.inf)
    _raster(px, py, sd, W, H, zbuf)
    img = np.tile(BACKGROUND, (W * H, 1))
    idbuf = np.full(W * H, -1, dtype=np.int64)

    def write(pix, tri):
        img[pix] = tri_rgb[tri]
        idbuf[pix] = pids[tri]
    _raster(px, py, sd, W, H, zbuf, write)

    # outlines where one part meets another (or the background)
    ids = idbuf.reshape(H, W)
    edge = np.zeros((H, W), bool)
    edge[:, :-1] |= ids[:, :-1] != ids[:, 1:]
    edge[:-1, :] |= ids[:-1, :] != ids[1:, :]
    img = img.reshape(H, W, 3)
    img[edge] = img[edge] * 0.35 + np.array([20, 20, 25]) * 0.65
    # the parts' own edge lines, only where nothing is in front of them
    if len(L):
        lx, ly, ld = (L @ r - cx) * scale + W / 2, H / 2 - (L @ u - cy) * scale, L @ v
        length = np.hypot(lx[:, 1] - lx[:, 0], ly[:, 1] - ly[:, 0])
        keep = length >= 1.5
        lx, ly, ld, length = lx[keep], ly[keep], ld[keep], length[keep]
        steps = np.ceil(length).astype(int) + 1
        seg = np.repeat(np.arange(len(steps)), steps)
        k = np.arange(steps.sum()) - np.repeat(np.cumsum(steps) - steps, steps)
        t = k / np.maximum(np.repeat(steps, steps) - 1, 1)
        qx = lx[seg, 0] + t * (lx[seg, 1] - lx[seg, 0])
        qy = ly[seg, 0] + t * (ly[seg, 1] - ly[seg, 0])
        qz = ld[seg, 0] + t * (ld[seg, 1] - ld[seg, 0])
        ix, iy = np.floor(qx).astype(int), np.floor(qy).astype(int)
        inb = (ix >= 0) & (ix < W) & (iy >= 0) & (iy < H)
        pix = iy[inb] * W + ix[inb]
        vis = qz[inb] >= zbuf[pix] - 1.5
        flat = img.reshape(-1, 3)
        flat[pix[vis]] = flat[pix[vis]] * 0.45 + np.array([25, 25, 30]) * 0.55
    out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    return out.resize((width, height), Image.Resampling.LANCZOS) if ss > 1 else out


def render_real_view_painter(scene, az: float, el: float, width: int, height: int, ss: int = 2) -> Image.Image:
    """Painter's-algorithm render of real part shapes with LDraw edge lines (kept for
    comparison; large faces can be drawn over nearer ones)."""
    from . import geometry
    P, PC, L, LC, _ = scene
    W, H = width * ss, height * ss
    img = Image.new("RGB", (W, H), tuple(int(c) for c in BACKGROUND))
    if not len(P):
        return img.resize((width, height))
    r, u, v = _camera(az, el)
    sx, sy, sd = P @ r, P @ u, P @ v
    lx, ly, ld = L @ r, L @ u, L @ v
    allx = np.concatenate([sx.ravel(), lx.ravel()])
    ally = np.concatenate([sy.ravel(), ly.ravel()])
    margin = 0.06
    span = max(allx.max() - allx.min(), 1e-6), max(ally.max() - ally.min(), 1e-6)
    scale = min(W * (1 - 2 * margin) / span[0], H * (1 - 2 * margin) / span[1])
    cx, cy = (allx.max() + allx.min()) / 2, (ally.max() + ally.min()) / 2
    to_px = lambda x, y: np.stack([(x - cx) * scale + W / 2, H / 2 - (y - cy) * scale], -1)

    normals = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    n = np.linalg.norm(normals, axis=1)
    n[n == 0] = 1
    normals = normals / n[:, None]
    facing = np.where((normals @ v)[:, None] < 0, -normals, normals)  # two-sided
    shade = 0.42 + 0.48 * np.clip(facing @ LIGHT, 0, 1) + 0.18 * np.clip(facing @ v, 0, 1)
    table = ldraw.colours()
    rgb_cache: dict[int, np.ndarray] = {}

    def rgb(code: int) -> np.ndarray:
        if code not in rgb_cache:
            c = table.get(code)
            rgb_cache[code] = np.array(c.rgb if c else (200, 200, 200), float)
        return rgb_cache[code]

    poly_px = to_px(sx, sy)
    line_px = to_px(lx, ly)
    # Skip what is too small to see at this size (stud and tube detail on big models).
    x, y = poly_px[..., 0], poly_px[..., 1]
    area = 0.5 * np.abs((x * np.roll(y, -1, 1) - np.roll(x, -1, 1) * y).sum(1))
    keep_p = np.nonzero(area >= 0.6)[0]
    seg = np.linalg.norm(line_px[:, 1] - line_px[:, 0], axis=1) if len(L) else np.zeros(0)
    keep_l = np.nonzero(seg >= 1.5)[0]
    depth_p, depth_l = sd.mean(1), (ld.mean(1) if len(L) else np.zeros(0))
    items = [(float(depth_p[i]), 0, int(i)) for i in keep_p]
    items += [(float(depth_l[i]) + 0.6, 1, int(i)) for i in keep_l]  # lines win ties
    items.sort(key=lambda it: it[0])  # far (small depth) first
    draw = ImageDraw.Draw(img)
    lw = max(1, ss // 2)
    for _, kind, i in items:
        if kind == 0:
            col = tuple(int(c) for c in np.clip(rgb(PC[i]) * shade[i], 0, 255))
            draw.polygon([tuple(p) for p in poly_px[i]], fill=col)
        else:
            code = LC[i]
            col = (35, 35, 42) if code == geometry.EDGE else tuple(int(c * 0.6) for c in rgb(code))
            draw.line([tuple(p) for p in line_px[i]], fill=col, width=lw)
    return img.resize((width, height), Image.Resampling.LANCZOS) if ss > 1 else img


def render(model: Model, views: list[str] | None = None, size: int = 520,
           reference: str | None = None, detail: str = "real") -> bytes:
    """detail='real' draws every part's true shape (slower, exact); 'simple' draws boxes and
    slope prisms (fast)."""
    views = views or DEFAULT_VIEWS
    parsed = [parse_view(v) for v in views]
    real = detail == "real"
    mesh = real_scene(model) if real else build_mesh(model)
    panels = []
    if reference:
        ref = Image.open(Path(reference).expanduser()).convert("RGB")
        ref.thumbnail((size, size))
        canvas = Image.new("RGB", (size, size), tuple(int(c) for c in BACKGROUND))
        canvas.paste(ref, ((size - ref.width) // 2, (size - ref.height) // 2))
        panels.append(("reference", canvas))
    for name, az, el in parsed:
        panels.append((name, render_real_view(mesh, az, el, size, size) if real
                       else render_view(mesh, az, el, size, size)))

    cols = 1 if len(panels) == 1 else 2 if len(panels) <= 4 else 3
    rows = math.ceil(len(panels) / cols)
    sheet = Image.new("RGB", (cols * size, rows * size), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    for i, (name, panel) in enumerate(panels):
        ox, oy = (i % cols) * size, (i // cols) * size
        sheet.paste(panel, (ox, oy))
        draw.rectangle([ox, oy, ox + size - 1, oy + size - 1], outline=(255, 255, 255), width=2)
        draw.text((ox + 8, oy + 6), name, fill=(40, 40, 50))
    buf = io.BytesIO()
    sheet.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
