"""Checks for the LDCad snap data (snaps.py) and the joints it adds.

Needs scripts/fetch_ldcad_snaps.sh to have been run. From the brickbuilder-mcp folder:
    uv run python tests/test_snaps.py
"""
from brickbuilder import geometry, snaps
from brickbuilder.model import BuildError, Model


def kinds(pid):
    return [k for k, *_ in geometry.joints_full(pid)]


def test_data_installed():
    assert snaps.available(), "run scripts/fetch_ldcad_snaps.sh first"


def test_connector_summaries():
    assert snaps.summary("3001") == {"stud": 8, "antistud": 8}  # brick 2 x 4: no pin holes
    assert snaps.summary("32316")["pin_hole"] == 5            # Technic beam 5
    assert "pin_hole" not in snaps.summary("2577")            # hollow underside isn't a pin hole
    assert snaps.summary("3705")["axle"] == 1                 # Technic axle 4
    assert snaps.summary("2780")["pin"] >= 2                  # Technic pin
    assert snaps.summary("3700")["pin_hole"] == 1             # brick 1 x 2 with hole
    assert snaps.summary("61252")["clip"] >= 1


def test_new_joint_kinds():
    assert "pin_hole" in kinds("3700")
    assert "pin" in kinds("2780")
    assert "axle" in kinds("3705") and "axle_hole" in kinds("32054")
    assert set(kinds("48729b")) >= {"clip", "bar"}            # bar with clip: was unsupported


def test_pin_into_brick_with_hole():
    m = Model("pins")
    brick = m.add("3700", 4, 0, 0, 0)
    pin = m.attach_joint("2780", 0, brick.id, kinds("3700").index("pin_hole"), 0, 0)
    assert pin.id in m.parts
    # a second brick goes onto the other half of the pin (whichever end that is)
    placed = None
    for j in range(len(kinds("2780"))):
        for flip in (False, True):
            try:
                placed = m.attach_joint("3700", 4, pin.id, j, kinds("3700").index("pin_hole"), 0, flip=flip)
                break
            except BuildError:
                continue
        if placed:
            break
    assert placed and placed.id in m.parts and not m.overlaps()


def test_axle_turns_in_90_degree_steps():
    m = Model("axle")
    beam = m.add("32054", 4, 0, 1, 0)
    hole = kinds("32054").index("axle_hole")
    try:
        m.attach_joint("3705", 0, beam.id, hole, 0, 45)
        raise AssertionError("45 degrees should be refused in a cross hole")
    except BuildError:
        pass


def test_axle_pin_has_a_pin_end_and_an_axle_end():
    assert kinds("3749") == ["pin", "axle"]


def test_wheel_on_axle_pin():
    """A brick with a hole, an axle pin, and a Speed Champions wheel on the axle end."""
    m = Model("wheel")
    brick = m.add("3700", 0, 4, 6, 0, 90)
    pin = m.attach_joint("3749", 19, brick.id, kinds("3700").index("pin_hole"), kinds("3749").index("pin"), 0)
    # the rim grips the axle with a thin ring, so it may sit anywhere along the axle end
    m.attach_joint("18976c01", 71, pin.id, kinds("3749").index("axle"), 0, 0, slide=9)
    assert not m.overlaps()


def test_wheel_on_wheel_holder_pin():
    assert "bar_hole" in kinds("6014ac01")
    m = Model("holder")
    holder = m.add("4600", 0, 0, 0, 0, ldu=[60, -48, 120])
    m.attach_joint("6014ac01", 71, holder.id, 0, 0, 0, flip=True)
    m.attach_joint("6014ac01", 71, holder.id, 1, 0, 0)
    assert not m.overlaps()


if __name__ == "__main__":
    for t in (test_data_installed, test_connector_summaries, test_new_joint_kinds,
              test_pin_into_brick_with_hole, test_axle_turns_in_90_degree_steps,
              test_axle_pin_has_a_pin_end_and_an_axle_end, test_wheel_on_axle_pin,
              test_wheel_on_wheel_holder_pin):
        t()
        print("ok", t.__name__)
