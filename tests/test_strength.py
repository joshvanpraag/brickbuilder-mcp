"""Checks for the strength check (strength.py).

From the brickbuilder-mcp folder:  uv run python tests/test_strength.py
"""
from brickbuilder import strength
from brickbuilder.model import Model


def test_running_bond_wall_is_fine():
    m = Model("wall")
    for y in range(0, 12, 3):
        off = 0 if (y // 3) % 2 == 0 else 2
        for x in range(off, off + 8, 4):
            m.add("3001", 4, x, y, 0)
    assert not strength.report(m)["flagged"]


def test_long_arm_on_one_stud_is_flagged():
    m = Model("arm")
    base = m.add("3001", 4, 0, 0, 0)
    post = m.add("3005", 4, 0, 3, 0)              # a single 1x1 brick: one stud each way
    m.add("3460", 1, 0, 6, 0)                     # 1x8 plates sticking out sideways
    m.add("3460", 1, 0, 7, 0)
    m.add("3001", 1, 6, 8, 0)                     # weight at the far end
    rep = strength.report(m)
    worst = rep["flagged"][0]
    assert worst["strength"] == 1 and worst["lever"] > 4
    assert {base.id, post.id} & set(worst["parts"])


def test_weight_resting_on_a_wide_base_is_not_flagged():
    m = Model("tower")
    m.add("3001", 4, 0, 0, 0)
    for y in (3, 6, 9, 12):
        m.add("3001", 4, 0, y, 0)                 # straight stack of 2x4 bricks, 8 studs each
    assert not strength.report(m)["flagged"]


if __name__ == "__main__":
    for t in (test_running_bond_wall_is_fine, test_long_arm_on_one_stud_is_flagged,
              test_weight_resting_on_a_wide_base_is_not_flagged):
        t()
        print("ok", t.__name__)
