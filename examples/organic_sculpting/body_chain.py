"""Curved body: a chain of short round segments on hinges, each bent a few degrees,
so the angles add up to an even arc (the Charmander tail method), instead of one straight
tube tilted on a pivot.

Segment (built upright in its own model, body axis on the grid line x=C, z=C):
  y0-1  hinge top 6134, inside the ring of the segment below (pivot 2 studs toward the bend)
  y2    full disc plate: two 22888 half-round plates
  y3..  solid disc: four 2577 quarter-round bricks per brick layer
  top   ring: four quarter rings (5651 curved-top on the inside of the bend, so the next
        segment can tip into it; 48092 on the outside) with the next hinge base 3937 inside
The last segment ends in the smooth dome (four 49612).

Run: python body_chain.py <out.png> [angle] [segments] [layers]
"""
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from modules import mount, Model, BuildError, BB  # noqa: E402
from brickbuilder import render  # noqa: E402

R, A = 4, 321
C = 12
QUAD = ((C, C - 4, 0), (C, C, 90), (C - 4, C, 180), (C - 4, C - 4, 270))   # FR, BR, BL, FL
RING = "48092"


def free(model, part, col, x, y, z, rot=0, plate_top=False):
    """Add at a grid position but as a free part (real-shape collisions). plate_top: put the
    part's own top (local y=0) at the top of plate level y, for parts whose bounds reach
    above it (a ball plate's ball)."""
    from brickbuilder.model import Placement, compute_geometry
    g = compute_geometry(Placement(0, part, 0, x, y, z, rot))
    pos = [float(v) for v in g.pos]
    if plate_top:
        pos[1] = -8.0 * (y + 1)
    return model.add(part, col, 0, 0, 0, rot, "up", pos)


PIVOT_X = (C + 1.5) * 20            # hinge pivot: 1.5 studs from the axis, toward the bend (+x)


def _hinge(model, part, y, grid=True, col=R):
    """Hinge part turned so its pivot runs front-to-back (z) at x = PIVOT_X, filling
    cells x C..C+1 (6134) or C+1 (3937), z C-1..C."""
    for rot in (90, 270):
        for x in ((C, C + 1) if part == "6134" else (C + 1,)):
            try:
                q = (model.add(part, col, x, y, C - 1, rot) if grid else free(model, part, col, x, y, C - 1, rot))
            except BuildError:
                continue
            k, c, f = model.geometry(q.id).joints()[0]
            lo, hi = model.geometry(q.id).aabb()
            if abs(c[0] - PIVOT_X) < 1 and abs(c[2] - C * 20) < 1 and lo[0] >= C * 20 - 1:
                return q
            model.remove([q.id])
    raise BuildError(f"no placement for {part}")


def _ball_out(model, sign, y, col):
    """1x2 ball plate at the body's edge (cells x C+3 or C-4, z C-1..C), ball pointing out (+-x)."""
    x = C + 3 if sign > 0 else C - 5                  # box includes the ball
    for rot in (0, 90, 180, 270):
        try:
            q = free(model, "14417", col, x, y, C - 1, rot, plate_top=True)
        except BuildError:
            continue
        k, c, f = model.geometry(q.id).joints()[0]
        # joint axis points from the ball back into the plate
        if np.dot(f[:, 2], [-sign, 0, 0]) > 0.9 and abs(c[2] - C * 20) < 1 and sign * (c[0] - C * 20) > 70:
            return q
        model.remove([q.id])
    raise BuildError("no shoulder ball placement")


def _face_band(s, y, face, col):
    """A band carrying single printed face tiles on side-stud bricks (not drawn in bricks).
    The back half is the usual round quarters / half-round plates; the front half is packed
    around the side-stud bricks.
      mouth: 3 plates, a 1x2 brick with two side studs at the front, one 1x2 smile tile.
      eyes:  7 plates (plate, 5-plate brick band, plate), two 2x2 eye tiles (body-coloured
             lid over a white sleepy eye) on 1x2x1 2/3 bricks with four side studs, set one
             row in; the front row is left open so the eyes sit in a shallow recess.
    Returns (tiles, band height in plates)."""
    from brickbuilder import packing, geometry as G
    from brickbuilder.model import direction_name
    eyes = face == "eyes"
    if eyes:
        specs, tile, n_front, height, by = [("22885", C - 3, C - 3), ("22885", C + 1, C - 3)], "14769p0d", 4, 7, y + 1
        opened = {(x, C - 4) for x in range(C - 2, C + 2)}
    else:
        specs, tile, n_front, height, by = [("11211", C - 1, C - 4)], "3069bp69", 2, 3, y
        opened = set()
    tiles, taken = [], set(opened)
    for part, x, z in specs:
        for rot in (0, 90, 180, 270):
            try:
                b = s.add(part, col, x, by, z, rot)
            except BuildError:
                continue
            front = [i for i, (p, d) in enumerate(s.geometry(b.id).studs()) if direction_name(d) == "front"]
            if len(front) != n_front:
                s.remove([b.id])
                continue
            taken |= {(c[0], c[2]) for c in s.geometry(b.id).cells}
            best = None
            for si in front:
                for rec in range(len(G.receivers(tile))):
                    for trot in (0, 90, 180, 270):
                        try:
                            t = s.attach(tile, col, b.id, si, rec, trot)
                        except BuildError:
                            continue
                        used = sum(1 for u in s.stud_usage(b.id) if u == t.id)
                        s.remove([t.id])
                        if best is None or used > best[0]:
                            best = (used, si, rec, trot)
            if best is None or best[0] < n_front:
                raise BuildError(f"{tile} does not seat on all of {part}'s side studs ({best})")
            tiles.append(s.attach(tile, col, b.id, best[1], best[2], best[3]))
            break
        else:
            raise BuildError(f"no front-facing {part} at x {x}")
    front_half = lambda x, z, skip: z < C and math.hypot(x + .5 - C, z + .5 - C) <= 3.9 and (x, z) not in skip
    rows = lambda skip: ["".join("R" if front_half(x, z, skip) else "." for x in range(24)) for z in range(23, -1, -1)]
    back_plate = lambda yy: s.add("22888", col, C - 4, yy, C, 180)
    if eyes:
        for yy in (y, y + 6):                               # plates above and below, front row open
            back_plate(yy)
            packing.fill_layers(s, [rows(opened)], {"R": col}, 0, yy, 0, "plate")
    for qx, qz, rot in QUAD:
        if rot in (90, 180):                                # back half stays round
            free(s, "2577", col, qx, by, qz, rot)
    packing.fill_layers(s, [rows(taken)], {"R": col}, 0, by, 0, "brick")
    if eyes:                                                # two more plates up to the bricks' height
        for dy in (3, 4):
            back_plate(by + dy)
            packing.fill_layers(s, [rows(taken)], {"R": col}, 0, by + dy, 0, "plate")
    return tiles, height


def segment(layers, last=False, shoulder=False, col=R, face=None):
    """shoulder: an extra plate layer with a ball joint sticking out at each side; face:
    "eyes" or "mouth", an extra brick band carrying printed face tiles at the front; returns
    (model, hinge top, next hinge base, {+1: right ball, -1: left ball})."""
    s = Model("seg")
    top = _hinge(s, "6134", 0)
    # plate 1: half-round plate on the outside of the bend, narrow 2x6 on the inside
    s.add("22888", R, C - 4, 2, C - 4, 270)
    s.add("3795", R, C, 2, C - 3, 90)
    # plate 2: full disc tying both halves; on the inside it sits a plate above the seam
    s.add("22888", R, C - 4, 3, C - 4, 0)
    s.add("22888", R, C - 4, 3, C, 180)
    y = 4
    balls = {}
    if shoulder:
        for sign in (1, -1):
            balls[sign] = _ball_out(s, sign, y, col)
        taken = {(c[0], c[2]) for b in balls.values() for c in s.geometry(b.id).cells if c[1] == y}
        from brickbuilder import packing
        rows = ["".join("R" if math.hypot(x + .5 - C, z + .5 - C) <= 4.0 and (x, z) not in taken else "."
                        for x in range(24)) for z in range(23, -1, -1)]
        packing.fill_layers(s, [rows], {"R": col}, 0, y, 0, "plate")
        # a plate layer above (leaving the ball plates' cells open, under the puff sleeves):
        # the ring's rim would otherwise graze the tops of the balls
        packing.fill_layers(s, [rows], {"R": col}, 0, y + 1, 0, "plate")
        y += 2
    if face:
        _, h = _face_band(s, y, face, col)
        y += h
    for _ in range(layers):
        for qx, qz, rot in QUAD:
            free(s, "2577", R, qx, y, qz, rot)
        y += 3
    base = None
    if last:
        for qx, qz, rot in QUAD:
            free(s, "49612", R, qx, y, qz, rot)
    else:
        for qx, qz, rot in QUAD:
            # hollow ring only where the hinge is (inside of the bend); solid elsewhere
            free(s, RING if rot in (0, 90) else "2577", R, qx, y, qz, rot)
        base = _hinge(s, "3937", y, grid=False)          # next hinge, inside the ring
    return s, top, base, balls


def build(angle, n, layers, name="body_chain"):
    m = Model(name)
    m.add("22888", A, C - 4, 0, C - 4, 0)
    m.add("22888", A, C - 4, 0, C, 180)
    base = _hinge(m, "3937", 1)
    sign = None
    for i in range(n):
        seg, top, nxt, _ = segment(layers, last=i == n - 1)
        ids, err = None, None
        for sg in ((sign,) if sign else (1, -1)):
            try:
                ids = mount(m, seg, top.id, 0, base.id, 0, bend=sg * angle)
            except BuildError as e:
                err = e
                continue
            if sign is None and angle:
                # the bend must carry the next hinge toward +x (the side the hinge is on)
                lo, hi = m.geometry(ids[nxt.id]).aabb()
                blo, bhi = m.geometry(base.id).aabb()
                if (lo[0] + hi[0]) < (blo[0] + bhi[0]):
                    m.remove(list(ids.values()))
                    ids = None
                    continue
            sign = sign or sg
            break
        if ids is None:
            raise BuildError(f"segment {i}: {err}")
        if nxt is not None:
            base = m.parts[ids[nxt.id]]
    return m


if __name__ == "__main__":
    out = sys.argv[1]
    angle = float(sys.argv[2]) if len(sys.argv) > 2 else 3
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    layers = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    m = build(angle, n, layers)
    ov = m.overlaps()
    chk = m.check()
    print(f"angle {angle} x {n} segments: parts {chk['parts']} groups {chk['group_sizes'][:4]} "
          f"overlaps {[(m.parts[i].part, m.parts[j].part, k) for i, j, k in ov]}")
    Path(out).write_bytes(render.render(m, ["front", "right", "iso_front_left", "iso_back_right"], 420))
