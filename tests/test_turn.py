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


def test_round_ends_touching_at_an_angle_do_not_clash():
    """Two plates with rounded ends (35480) whose round ends just touch, one turned 48 degrees
    to the other (the corner of an angled bay): touching, not overlapping."""
    m = Model("t")
    m.add("3036", "tan", 0, 0, 0, 0)
    turned = m.attach("35480", "tan", 1, 21, 0, turn=-48.19)   # on a plate stud, turned
    g = m.geometry(turned.id)
    end = g.matrix @ np.array([20.0, 0, 0]) + g.matrix @ np.array([-10.0, 0, 0]) + g.pos  # far stud
    # a straight piece whose round end is centred one stud (20 LDU) on from that far stud
    m.add("35480", "tan", 0, 0, 0, 0, "up", [float(end[0] + 20 + 10), float(end[1]), float(end[2])],
          matrix=np.eye(3))
    assert m.overlaps() == []
    # a real overlap is still refused: the same piece pushed 6 LDU into it
    try:
        m.add("35480", "tan", 0, 0, 0, 0, "up", [float(end[0] + 24), float(end[1]), float(end[2])],
              matrix=np.eye(3))
    except BuildError:
        return
    raise AssertionError("a real overlap of rounded ends was allowed")


def test_brick_touching_a_round_column_at_an_angle():
    """A 1x2 brick turned about 48 degrees, its end just touching a 1x1 round brick: the overlap
    test follows the column's real round outline, not a blocky one, so this is allowed."""
    import math
    m = Model("t")
    m.add("3036", "tan", 0, 0, 0, 0)
    c, s = 2 / 3, math.sqrt(5) / 3                  # direction of the angled wall
    col = m.add("3062b", "tan", 2, 1, 2, 0)          # round column, centre (2.5, 2.5) studs
    centre = np.array([2.5, 2.5])
    mat = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    for t0 in (0.5, -2.5):                           # brick on either side, its end 0.5 from the centre
        mid = centre + (t0 + 1.0) * np.array([c, -s])  # brick centre, 1 stud along from its end
        pos = [20 * mid[0], -8 - 24, 20 * mid[1]]      # origin at the top of the brick
        m.add("3004", "tan", 0, 0, 0, 0, "up", [float(v) for v in pos], matrix=mat)
    assert m.overlaps() == [], m.overlaps()


if __name__ == "__main__":
    for t in (test_turn_90_matches_rot_90, test_window_turned_45_on_one_stud, test_turned_part_still_collides,
              test_round_ends_touching_at_an_angle_do_not_clash,
              test_brick_touching_a_round_column_at_an_angle):
        t()
        print("ok", t.__name__)
