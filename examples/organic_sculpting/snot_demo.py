"""Demo of modules.mount_on_stud: sub-assemblies built in their own frame and pressed onto
sideways studs, the way the 31133 Moomin-style build makes its belly (built lying on its back,
then stood up) and the MF DOOM bust clads a 1x1-studs-on-all-sides core with panels.

Run: <server>/.venv/Scripts/python.exe snot_demo.py out.png
"""
import sys

import numpy as np
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from modules import Model, BuildError, mount_on_stud  # noqa: E402
from brickbuilder import render  # noqa: E402
from brickbuilder.model import direction_name  # noqa: E402

W, R = 15, 4
m = Model("snot_demo")
# core: a 4x4 footing, then a brick with four side studs facing front (two 1x2x1 2/3 bricks)
m.add("3031", R, 0, 0, 0)
core = [m.add("22885", R, x, 1, 0, 0) for x in (0, 2)]
m.add("3031", R, 0, 6, 0)


def belly():
    """Built lying on its back: 4x4 round plate with the smooth 4x4 dome on it."""
    b = Model("belly")
    base = b.add("60474", W, 0, 0, 0)
    mid = lambda g: (g.aabb()[0] + g.aabb()[1]) / 2
    best = None
    for st in range(len(b.geometry(base.id).studs())):
        for rec in range(12):
            try:
                q = b.attach("86500", W, base.id, st, rec, 0)
            except BuildError:
                continue
            d = np.linalg.norm((mid(b.geometry(q.id)) - mid(b.geometry(base.id)))[[0, 2]])
            b.remove([q.id])
            if best is None or d < best[0]:
                best = (d, st, rec)
    b.attach("86500", W, base.id, best[1], best[2], 0)          # dome centred on the plate
    return b, base


bm, bb = belly()
front = [(c, i) for c in core for i, (p, d) in enumerate(m.geometry(c.id).studs()) if direction_name(d) == "front"]
face_mid = np.mean([m.geometry(c.id).studs()[i][0] for c, i in front], axis=0)
done = None
for c, i in front:
    for rec in range(12):
        for spin in (0, 90, 180, 270):
            try:
                ids = mount_on_stud(m, bm, bb.id, rec, c.id, i, spin)
            except BuildError:
                continue
            g = m.geometry(ids[bb.id])
            off = np.linalg.norm(((g.aabb()[0] + g.aabb()[1]) / 2 - face_mid)[[0, 1]])
            m.remove(list(ids.values()))
            if done is None or off < done[0]:
                done = (off, c, i, rec, spin)
ids = mount_on_stud(m, bm, bb.id, done[3], done[1].id, done[2], done[4])
print("belly centred on the face, off by", round(float(done[0]), 1), "LDU")
chk = m.check()
print("parts", chk["parts"], "groups", chk["group_sizes"], "overlaps", m.overlaps())
Path(sys.argv[1] if len(sys.argv) > 1 else HERE / "snot_demo.png").write_bytes(
    render.render(m, ["front", "right", "iso_front_left"], 420))
