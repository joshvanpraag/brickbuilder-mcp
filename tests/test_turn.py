"""A part held by a single stud can be turned to any angle (attach ... turn=45).
From the brickbuilder-mcp folder:
    uv run python tests/test_turn.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from brickbuilder.model import BuildError, Model  # noqa: E402


def test_turn_90_matches_rot_90():
    a, b = Model("a"), Model("b")
    for m in (a, b):
        m.add("3036", "tan", 0, 0, 0, 0)
    pa = a.attach("3004", "red", 1, 10, 0, rot=90)
    pb = b.attach("3004", "red", 1, 10, 0, turn=90)
    assert np.allclose(a.geometry(pa.id).pos, b.geometry(pb.id).pos)
    assert np.allclose(a.geometry(pa.id).matrix, b.geometry(pb.id).matrix)


def test_window_turned_45_on_one_stud():
    m = Model("t")
    base = m.add("3024", "tan", 4, 0, 4, 0)                # 1x1 plate: one stud to turn on
    w = m.attach("60592", "tan", base.id, 0, 0, turn=45)    # window 1 x 2 x 2, turned 45 degrees
    g = m.geometry(w.id)
    assert g.free and not g.axis_aligned
    # the long side of the window now runs at 45 degrees in plan
    long_side = g.matrix @ np.array([1.0, 0, 0])
    assert abs(abs(long_side[0]) - abs(long_side[2])) < 1e-6
    assert base.id in m.connections()[w.id]               # held by its one stud
    glass = m.add_insert("60601", "trans_clear", w.id)     # the glass still seats in it
    assert w.id in m.connections()[glass.id]
    assert m.check()["group_sizes"] == [3]
    assert m.overlaps() == []


def test_turned_part_still_collides():
    m = Model("t")
    base = m.add("3024", "tan", 4, 0, 4, 0)
    m.add("3005", "red", 5, 1, 4, 0)                       # a brick right beside the stud
    try:
        m.attach("3004", "red", base.id, 0, 0, turn=30)     # a turned 1x2 would pass into it
    except BuildError:
        return
    raise AssertionError("a turned part passing into a brick was allowed")


if __name__ == "__main__":
    for t in (test_turn_90_matches_rot_90, test_window_turned_45_on_one_stud, test_turned_part_still_collides):
        t()
        print("ok", t.__name__)
