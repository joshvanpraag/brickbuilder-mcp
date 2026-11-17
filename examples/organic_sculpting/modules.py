"""Subassembly mounting for brickbuilder models.

Build a module (arm, bow, ...) upright in its own Model, then mount it onto a joint of the
main model at chosen angles: every part is moved rigidly so the module's joint lands on the
target joint, and is added with the main model's real-shape collision check. If any part
collides, everything mounted so far is removed again and the error is raised.
"""
import math
import sys
from pathlib import Path

import numpy as np

BB = Path(__file__).resolve().parents[2]          # the brickbuilder-mcp folder (two levels up)
sys.path.insert(0, str(BB / "src"))
from brickbuilder import geometry  # noqa: E402
from brickbuilder.model import BuildError, Model, _rot  # noqa: E402

FLIP = np.diag([-1.0, 1.0, -1.0])  # ball/socket: stems opposite, tops the same way up


def mount(main: Model, module: Model, mod_part: int, mod_joint: int, target: int, target_joint: int = 0,
          bend: float = 0, swing: float = 0, twist: float = 0) -> dict[int, int]:
    """Mount `module` so joint `mod_joint` of its part `mod_part` connects to joint
    `target_joint` of main-model part `target`. Angles as in Model.attach_joint.
    Returns {module part id: main part id}."""
    tk, tc, tf = main.geometry(target).joints()[target_joint]
    mk, mc, mf = module.geometry(mod_part).joints()[mod_joint]
    if (tk, mk) not in geometry.JOINT_PAIRS:
        raise BuildError(f"a {mk} does not connect to a {tk}")
    if tk in ("ball", "socket"):
        user = _rot("x", bend) @ _rot("y", swing) @ _rot("z", twist)
        tilt = math.degrees(math.acos(max(-1.0, min(1.0, user[2, 2]))))
        if tilt > 45.5:
            raise BuildError(f"ball joint tilt {tilt:.0f} > 45 degrees")
        new_frame = tf @ user @ FLIP
    else:
        new_frame = tf @ _rot("x", bend)
    R = new_frame @ mf.T
    t = tc - R @ mc
    placed: dict[int, int] = {}
    try:
        for pid, p in module.parts.items():
            g = module.geometry(pid)
            m_new = R @ g.matrix
            pos = R @ g.pos + t
            q = main.add(p.part, p.color, 0, 0, 0, 0, "up", [float(v) for v in pos], matrix=m_new,
                         ignore={target} if pid == mod_part else None)
            placed[pid] = q.id
    except BuildError as e:
        main.remove(list(placed.values()))
        raise BuildError(f"module part {p.part}: {e}") from None
    return placed


def _align(u: np.ndarray, d: np.ndarray) -> np.ndarray:
    """Smallest rotation taking unit vector u onto unit vector d."""
    u, d = u / np.linalg.norm(u), d / np.linalg.norm(d)
    c = float(np.dot(u, d))
    if c > 1 - 1e-9:
        return np.eye(3)
    if c < -1 + 1e-9:                                   # opposite: half turn about any perpendicular
        p = np.cross(u, [1.0, 0, 0])
        if np.linalg.norm(p) < 1e-6:
            p = np.cross(u, [0, 0, 1.0])
        p /= np.linalg.norm(p)
        return 2 * np.outer(p, p) - np.eye(3)
    v = np.cross(u, d)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1 + c)


def _spin(axis: np.ndarray, deg: float) -> np.ndarray:
    a = axis / np.linalg.norm(axis)
    k = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    r = math.radians(deg)
    return np.eye(3) + math.sin(r) * k + (1 - math.cos(r)) * k @ k


def mount_on_stud(main: Model, module: Model, mod_part: int, mod_receiver: int, target: int, target_stud: int,
                  spin: float = 0) -> dict[int, int]:
    """Mount `module` by pressing receiver `mod_receiver` of its part `mod_part` onto stud
    `target_stud` of main-model part `target`, whichever way that stud points (up, sideways,
    down, or tilted). The module is built upright in its own frame (e.g. a belly built lying
    on its back, a face panel, an ear), then turned so that part's top faces along the stud;
    `spin` turns it about the stud axis (degrees; multiples of 90 keep it on the stud grid).
    Every part is checked for collisions; on failure nothing is left placed.
    Returns {module part id: main part id}."""
    spos, sdir = main.geometry(target).studs()[target_stud]
    g = module.geometry(mod_part)
    recv = geometry.receivers(module.parts[mod_part].part)
    rpos = g.matrix @ np.asarray(recv[mod_receiver][0], float) + g.pos      # receiver, module frame
    up = g.matrix @ np.array([0.0, -1.0, 0.0])                                # that part's top
    R = _spin(np.asarray(sdir, float), spin) @ _align(up, np.asarray(sdir, float))
    t = np.asarray(spos, float) - R @ rpos
    placed: dict[int, int] = {}
    try:
        for pid, p in module.parts.items():
            pg = module.geometry(pid)
            q = main.add(p.part, p.color, 0, 0, 0, 0, "up", [float(v) for v in R @ pg.pos + t],
                         matrix=R @ pg.matrix)
            placed[pid] = q.id
    except BuildError as e:
        main.remove(list(placed.values()))
        raise BuildError(f"module part {p.part}: {e}") from None
    return placed
