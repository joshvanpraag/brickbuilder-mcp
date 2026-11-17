"""The Lowell sphere: a round ball from plain plates (a technique by Bruce Lowell).

How it's built:
- Six identical caps. Each cap is three layers of plates that step in like a low dome:
  1. a 4 x 4 ring of four corner plates (2420), with a 2 x 2 hole in the middle;
  2. two 1 x 4 plates (3710) and two 1 x 2 plates (3023): 4 x 4 with the corners left off;
  3. one 2 x 2 plate (3022) on top.
- The core is eight bricks 1 x 1 with studs on four sides (4733). Four hang under the corners
  of the top cap and four under the bottom cap (that half is built the same way and turned
  upside down). Their side studs line up exactly 3 studs apart, which is where the corner
  plates of a cap sit, so the four side caps press onto them. The side caps are what hold
  the top and bottom halves together.
The ball is about 6.5 studs across. See docs/round_shapes_techniques.md.

Use it from your own build:
    from lowell_sphere import lowell_sphere
    ids = lowell_sphere(m, centre=[0, -100, 0], color="red", core_color="black")

Run the demo from the brickbuilder-mcp folder:
    uv run python examples/organic_sculpting/lowell_sphere.py sphere.png
"""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "src"))

from brickbuilder import geometry, render  # noqa: E402
from brickbuilder.model import BuildError, Model  # noqa: E402
from modules import mount_on_stud  # noqa: E402

CORE_GAP = 4          # plates between the top and bottom halves of the core
HALF_HEIGHT = 40.0    # LDU from the centre to the underside of the top cap


def cap(color) -> tuple[Model, int]:
    """One cap, built upright: three layers of plates stepping in. Returns the model and
    the id of the corner plate at its (0, 0) corner."""
    m = Model("lowell cap")
    # layer 1: a 4 x 4 ring of corner plates, one per corner, arms pointing along the edges
    corner = None
    for x, z, rot in ((0, 0, 0), (2, 0, 90), (2, 2, 180), (0, 2, 270)):
        p = _ring_plate(m, color, x, z, rot)
        if (x, z) == (0, 0):
            corner = p.id
    # layer 2: 4 x 4 with the corners left off
    m.add("3710", color, 0, 1, 1)
    m.add("3710", color, 0, 1, 2)
    m.add("3023", color, 1, 1, 0)
    m.add("3023", color, 1, 1, 3)
    # layer 3: 2 x 2 on top
    m.add("3022", color, 1, 2, 1)
    return m, corner


def _ring_plate(m: Model, color, x: int, z: int, rot: int):
    """A corner plate (2420, 2 x 2 with one stud missing) whose corner is at the outside
    corner of the 4 x 4 ring. Tries the four turns and keeps the one that leaves the
    middle 2 x 2 open."""
    for r in (0, 90, 180, 270):
        try:
            p = m.add("2420", color, x, 0, z, r)
        except BuildError:
            continue
        studs = {(round(s[0] / 20 - 0.5), round(s[2] / 20 - 0.5)) for s, _ in m.geometry(p.id).studs()}
        if not studs & {(1, 1), (1, 2), (2, 1), (2, 2)}:
            return p
        m.remove([p.id])
    raise BuildError(f"no turn of the corner plate fits at {x}, {z}")


def half(color, core_color) -> tuple[Model, list[int]]:
    """A cap with four core bricks hanging under its corners. Returns the model and the ids
    of the four bricks."""
    m = Model("lowell half")
    bricks = [m.add("4733", core_color, x, 0, z).id for x in (0, 3) for z in (0, 3)]
    c, _ = cap(color)
    for pid, p in c.parts.items():
        g = c.geometry(pid)
        m.add(p.part, p.color, 0, 0, 0, 0, "up", [float(v) for v in g.pos + np.array([0, -24.0, 0])],
              matrix=g.matrix)
    return m, bricks


def _place(main: Model, module: Model, R: np.ndarray, t: np.ndarray) -> dict[int, int]:
    """Put every part of `module` into `main`, turned by R and moved by t."""
    placed = {}
    try:
        for pid, p in module.parts.items():
            g = module.geometry(pid)
            q = main.add(p.part, p.color, 0, 0, 0, 0, "up", [float(v) for v in R @ g.pos + t],
                         matrix=R @ g.matrix)
            placed[pid] = q.id
    except BuildError as e:
        main.remove(list(placed.values()))
        raise BuildError(f"lowell sphere: {e}") from None
    return placed


def lowell_sphere(main: Model, centre, color, core_color=None) -> list[int]:
    """Build a Lowell sphere in `main` centred on `centre` (LDraw coordinates, LDU; y points
    down, so a ball resting on the ground has centre y about -66). Returns the new part ids."""
    core_color = color if core_color is None else core_color
    centre = np.asarray(centre, float)
    mod, bricks = half(color, core_color)
    # the half's frame: bricks' bottoms at y = 0, centred on x = z = 40 (the 4 x 4 middle)
    mid = np.array([40.0, 0.0, 40.0])
    up = _place(main, mod, np.eye(3), centre - mid + np.array([0, -(HALF_HEIGHT - 24), 0]))
    flip = np.diag([1.0, -1.0, -1.0])                     # upside down (turned about x)
    down = _place(main, mod, flip, centre - flip @ mid + np.array([0, HALF_HEIGHT - 24, 0]))
    ids = list(up.values()) + list(down.values())
    core = [up[b] for b in bricks] + [down[b] for b in bricks]
    # side caps: press a cap's corner plate onto a core brick's outward side stud
    side_cap, corner = cap(color)
    recv = _corner_receiver(side_cap, corner)
    for direction in ([1, 0, 0], [-1, 0, 0], [0, 0, 1], [0, 0, -1]):
        d = np.array(direction, float)
        ids += _side_cap(main, side_cap, corner, recv, core, centre, d)
    return ids


def _corner_receiver(m: Model, corner: int) -> int:
    """The receiver of the corner plate that sits at the ring's outside corner."""
    g = m.geometry(corner)
    best, far = 0, -1.0
    for i, (p, _) in enumerate(g.receivers()):
        dist = float(np.hypot(p[0] - 40, p[2] - 40))     # farthest from the cap's middle
        if dist > far:
            best, far = i, dist
    return best


def _side_cap(main, cap_model, corner, recv, core, centre, d) -> list[int]:
    """Mount one side cap facing direction d, on the core brick stud that matches its corner."""
    for b in core:
        studs = main.geometry(b).studs()
        for si, (pos, sdir) in enumerate(studs):
            if np.dot(sdir, d) < 0.99 or np.dot(pos - centre, d) < 30:
                continue                     # wrong way, or facing into the hollow core
            for spin in (0, 90, 180, 270):
                try:
                    placed = mount_on_stud(main, cap_model, corner, recv, b, si, spin)
                except BuildError:
                    continue
                # keep it only if the cap sits centred on this face
                pts = np.array([main.geometry(q).pos for q in placed.values()])
                off = pts.mean(0) - centre
                if np.linalg.norm(off - np.dot(off, d) * d) < 12:
                    return list(placed.values())
                main.remove(list(placed.values()))
    raise BuildError(f"no side cap fits facing {d.tolist()}")


if __name__ == "__main__":
    m = Model("lowell sphere")
    ids = lowell_sphere(m, [0, -100, 0], "red", "black")
    chk = m.check()
    print("parts", chk["parts"], "groups", chk["group_sizes"], "overlaps", m.overlaps())
    out = sys.argv[1] if len(sys.argv) > 1 else HERE / "renders" / "lowell_sphere.png"
    Path(out).write_bytes(render.render(m, ["front", "top", "iso_front_left"], 420))
