"""Checks for wheels: tyres on rims, hub holes found from the shape, and grid placement of
wheel holders. From the brickbuilder-mcp folder:
    uv run python tests/test_wheels.py
"""
import numpy as np

from brickbuilder import geometry, wheels
from brickbuilder.model import BuildError, Model


def kinds(pid):
    return [k for k, *_ in geometry.joints_full(pid)]


def test_rims_and_tyres_have_joints():
    assert "tyre_seat" in kinds("18976") and "tyre_seat" in kinds("6014b")
    assert kinds("18977") == ["tyre"]
    assert "tyre_seat" not in kinds("18976c01")          # already has its tyre


def test_hub_found_from_the_shape():
    # 6014b has no LDCad connection data: its hole is found from the drawn hub
    assert "bar_hole" in kinds("6014b")


def test_tyre_sits_where_ldraw_puts_it():
    """18976c01 is LDraw's rim 18976 at z 6 with tyre 18977 at 0."""
    m = Model("tyre")
    rim = m.add("18976", 71, 0, 0, 0, ldu=[0, -100, 6], matrix=np.eye(3))
    tyre = m.attach_joint("18977", 0, rim.id, kinds("18976").index("tyre_seat"), 0, 0)
    assert np.allclose(m.geometry(tyre.id).pos, [0, -100, 0], atol=0.5)
    assert not m.overlaps()                               # the rim sits inside the tyre's hole


def test_a_tyre_that_does_not_fit_is_refused():
    m = Model("too small")
    rim = m.add("18976", 71, 0, 0, 0, ldu=[0, -100, 0], matrix=np.eye(3))
    assert wheels.fit_problem("18976", "3641")             # a tiny tyre on a big rim
    try:
        m.attach_joint("3641", 0, rim.id, kinds("18976").index("tyre_seat"), 0, 0)
        raise AssertionError("should refuse")
    except BuildError:
        pass


def test_wheel_holder_on_the_grid_lines_up_with_the_brick_above():
    m = Model("holder")
    m.add("3003", 0, 2, 6, 5)
    holder = m.add("4600", 0, 2, 5, 5)                      # pins stick out each side
    assert np.allclose(m.geometry(holder.id).pos, [60, -48, 120])
    assert m.check()["group_sizes"] == [2]


def test_other_parts_keep_their_full_box():
    from brickbuilder import ldraw
    for pid in ("3660", "24130", "11476", "3020"):         # inverted slope, dome, clip plate
        assert geometry.grid_bounds(pid) == ldraw.part_bounds(pid)


if __name__ == "__main__":
    for t in (test_rims_and_tyres_have_joints, test_hub_found_from_the_shape,
              test_tyre_sits_where_ldraw_puts_it, test_a_tyre_that_does_not_fit_is_refused,
              test_wheel_holder_on_the_grid_lines_up_with_the_brick_above,
              test_other_parts_keep_their_full_box):
        t()
        print("ok", t.__name__)
