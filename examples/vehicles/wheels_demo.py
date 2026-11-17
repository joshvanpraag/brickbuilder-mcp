"""Two ways to put wheels on a small car chassis, as most minifig-scale car MOCs do.

Front: Technic bricks 1 x 2 with a hole (3700) in the chassis, an axle pin (3749) pushed
into each hole, and a rim-with-tyre (18976c01, the Speed Champions wheel) on the axle end.
Back: a wheel holder plate (4600) with a wheel and tyre (6014ac01) on each of its pins.

Run from the brickbuilder-mcp folder:
    uv run python examples/vehicles/wheels_demo.py wheels.png
"""
import sys
from pathlib import Path

from brickbuilder import geometry, render
from brickbuilder.model import BuildError, Model

HERE = Path(__file__).parent
BLACK, WHITE, TAN, GREY = 0, 15, 19, 71
FLIP_LEFT = True


def joints(part):
    return [k for k, *_ in geometry.joints_full(part)]


def attach(m, part, color, target, kind, own_kind, nth=0, flips=(False, True)):
    """Join `part` to the nth `kind` joint of `target`, trying each way round in `flips`."""
    which = [i for i, k in enumerate(joints(target.part)) if k == kind][nth]
    for flip in flips:
        try:
            return m.attach_joint(part, color, target.id, which, joints(part).index(own_kind), 0, flip=flip)
        except BuildError as e:
            err = e
    raise err


m = Model("wheels demo")
# chassis: two Technic bricks turned so their holes run left-right, under a 4 x 8 plate.
# The chassis is narrower than the wheel track, so the wheel hubs clear it.
left = m.add("3700", BLACK, 1, 6, 0, 90)
right = m.add("3700", BLACK, 4, 6, 0, 90)
m.add("3035", WHITE, 1, 9, 0, 90)
# front wheels: axle pin into the hole, wheel onto the axle end
# (flip turns the axle pin end for end, so its axle end points out of the car)
for brick, flip in ((left, FLIP_LEFT), (right, not FLIP_LEFT)):
    pin = attach(m, "3749", TAN, brick, "pin_hole", "pin", flips=(flip,))
    attach(m, "18976c01", GREY, pin, "axle", "axle_hole")
# back wheels: a wheel holder hung under a 2 x 2 brick, a wheel on each pin
m.add("3003", BLACK, 2, 6, 5)
# The holder's pins stick out past its body, so a grid corner would put it half a stud off.
# Give its exact LDraw position instead: centred under the brick (x 60, z 120 LDU, its top at the brick's underside).
holder = m.add("4600", BLACK, 0, 0, 0, ldu=[60, -48, 120])
for nth, flip in ((0, True), (1, False)):     # flip so each tyre faces outward
    attach(m, "6014ac01", GREY, holder, "bar", "bar_hole", nth, flips=(flip,))

chk = m.check()
print("parts", chk["parts"], "groups", chk["group_sizes"], "overlaps", m.overlaps())
Path(sys.argv[1] if len(sys.argv) > 1 else HERE / "renders" / "wheels_demo.png").write_bytes(
    render.render(m, ["front", "right", "iso_front_left"], 420))
