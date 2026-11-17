"""Joint families: clip / bar, large balls (towball and 2x2 brick balls), hinge plates and
turntables, plus the original joint-8 balls and 3937 / 6134 hinges.

Run with `python -m pytest tests` or, without pytest, `python tests/test_joints.py`.
Needs the LDraw library in data/ldraw (scripts/fetch_ldraw.sh).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brickbuilder import geometry  # noqa: E402
from brickbuilder.model import BuildError, Model  # noqa: E402

Y = 12  # build in the air so tilted parts never reach the ground


def _attach(base: str, base_joint: int, new: str, new_joint: int, **kw) -> tuple[Model, int, int]:
    m = Model("t")
    b = m.add(base, "red", 4, Y, 4)
    p = m.attach_joint(new, "blue", b.id, base_joint, new_joint, **kw)
    return m, b.id, p.id


def _assert_joined(m: Model, a: int, b: int) -> None:
    r = m.check()
    assert r["connected_groups"] == 1, r
    assert m.overlaps() == [], m.overlaps()
    assert m.joint_usage(a).count(b) == 1 and b in m.joint_usage(a)


def _kinds(part: str) -> list[str]:
    return [k for k, *_ in geometry.joints(part)]


# ------------------------------------------------------------------ detection


def test_every_family_is_detected():
    expected = {
        "clip": ["61252", "63868", "60470", "15712", "11090", "11476"],
        "bar": ["60478", "48336", "2540", "26047", "87994"],
        "towball": ["3731", "15456", "3614a", "3184"],
        "towball_socket": ["3730"],
        "large_ball": ["17114"],
        "large_socket": ["92013", "62712", "57910", "67696"],
        "swivel_base": ["2429"], "swivel_top": ["2430"],
        "click_hinge_1": ["44301a"], "click_hinge_2": ["44302a"],
        "turntable_base": ["3403"], "turntable_top": ["3404"],
        "flat_turntable": ["61485"], "snapstud": ["60474"],
    }
    for kind, parts in expected.items():
        for p in parts:
            pid = "60470a" if p == "60470" else p
            assert kind in _kinds(pid), (p, _kinds(pid))
    # Technic holes from the LDCad snap data come on top of these
    snap_only = {"pin", "pin_hole", "axle", "axle_hole", "finger_m", "finger_f"}
    assert [k for k in _kinds("60470a") if k not in snap_only] == ["clip", "clip"]
    assert [k for k in _kinds("17114") if k not in snap_only] == ["large_ball", "large_ball"]


def test_bar_slide_ranges():
    slide = {p: geometry.joints_full(p)[0][3] for p in ("60478", "48336", "2540", "26047", "87994")}
    assert slide["87994"] == 26          # 60 LDU bar, 8 LDU clip
    assert slide["48336"] == 10          # 34 LDU between handle attachments
    assert slide["2540"] == 2
    assert slide["60478"] == 0 and slide["26047"] == 0


def test_click_hinge_halves_share_a_pivot():
    (_, a, fa, _), = geometry.joints_full("44301a")
    (_, b, fb, _), = geometry.joints_full("44302a")
    assert np.allclose(a, b) and np.allclose(fa[:, 0], fb[:, 0])


# ------------------------------------------------------------------ clip / bar


def test_clip_on_handle_any_angle():
    for bend in (0, 45, 90, -90, 180, 137.5):
        m, a, b = _attach("60478", 0, "61252", 0, bend=bend)
        _assert_joined(m, a, b)


def test_clip_at_angle_zero_continues_the_handle_plate():
    m, a, b = _attach("60478", 0, "63868", 0)
    ga, gb = m.geometry(a), m.geometry(b)
    assert np.allclose(gb.matrix @ [0, 1, 0], [0, 1, 0])          # same way up
    assert abs(ga.pos[1] - gb.pos[1]) < 1e-6                         # plates level
    axis_x = ga.pos[0] + 30                                          # handle bar at local x=30
    assert gb.pos[0] > axis_x and ga.pos[0] < axis_x                 # opposite sides of it


def test_clip_slides_along_a_bar():
    for slide in (-10, 0, 10):
        m, a, b = _attach("48336", 0, "63868", 0, bend=30, slide=slide)
        _assert_joined(m, a, b)
    xs = [_attach("48336", 0, "63868", 0, slide=s)[0].geometry(2).pos[0] for s in (-10, 10)]
    assert abs(abs(xs[1] - xs[0]) - 20) < 1e-6


def test_bar_through_a_clip_with_slide_and_flip():
    for bend, slide, flip in ((0, 0, False), (90, -20, False), (45, 26, True)):
        m, a, b = _attach("61252", 0, "87994", 0, bend=bend, slide=slide, flip=flip)
        _assert_joined(m, a, b)


def test_clip_slide_is_limited_to_the_bar():
    m = Model("t")
    h = m.add("48336", "red", 4, Y, 4)
    try:
        m.attach_joint("63868", "blue", h.id, 0, 0, slide=11)
    except BuildError:
        pass
    else:
        raise AssertionError("slide past the end of the bar was accepted")


def test_two_clip_plate_and_tile_clip_on_bars():
    m, a, b = _attach("2540", 0, "60470", 1, bend=-60)
    _assert_joined(m, a, b)
    m, a, b = _attach("87994", 0, "15712", 0, bend=90, slide=-15)
    _assert_joined(m, a, b)


# ------------------------------------------------------------------ large balls


def test_towballs_into_the_towball_socket():
    for ball in ("3731", "15456", "3614a", "3184"):
        for bend, swing, twist in ((0, 0, 0), (30, 0, 0), (0, -40, 90), (40, 30, 0)):
            m, a, b = _attach(ball, 0, "3730", 0, bend=bend, swing=swing, twist=twist)
            _assert_joined(m, a, b)


def test_large_ball_into_2x2_sockets_both_ways():
    for sock in ("62712", "92013", "57910", "67696"):
        for bend, swing in ((0, 0), (25, 0), (-30, 20)):
            m, a, b = _attach("17114", 0, sock, 0, bend=bend, swing=swing)
            _assert_joined(m, a, b)
    m, a, b = _attach("62712", 0, "17114", 1, bend=20)  # ball brick onto a socket brick
    _assert_joined(m, a, b)


def test_ball_systems_only_mate_with_their_own_kind():
    for base, bj, new, nj in (("3731", 0, "62712", 0), ("17114", 0, "3730", 0),
                              ("14417", 0, "3730", 0), ("3731", 0, "14704", 0)):
        m = Model("t")
        b = m.add(base, "red", 4, Y, 4)
        try:
            m.attach_joint(new, "blue", b.id, bj, nj)
        except BuildError:
            continue
        raise AssertionError(f"{new} connected to {base}")


def test_large_ball_tilt_limit():
    m = Model("t")
    b = m.add("17114", "red", 4, Y, 4)
    try:
        m.attach_joint("62712", "blue", b.id, 0, 0, bend=60)
    except BuildError:
        return
    raise AssertionError("60 degrees accepted on a 45 degree joint")


# ------------------------------------------------------------------ hinge plates


def test_swivel_hinge_plates_any_angle():
    for bend in (0, 30, 90, -90, -135):
        m, a, b = _attach("2429", 0, "2430", 0, bend=bend)
        _assert_joined(m, a, b)
        assert np.allclose(m.geometry(b).matrix @ [0, 1, 0], [0, 1, 0])  # turns flat


def test_locking_hinge_plates_any_angle():
    for bend in (0, 45, -45, 90, -90):
        m, a, b = _attach("44301a", 0, "44302a", 0, bend=bend)
        _assert_joined(m, a, b)
    m, a, b = _attach("44302a", 0, "44301a", 0, bend=-30)
    _assert_joined(m, a, b)


def test_hinge_plate_rejects_swing():
    m = Model("t")
    b = m.add("2429", "red", 4, Y, 4)
    try:
        m.attach_joint("2430", "blue", b.id, 0, 0, swing=10)
    except BuildError:
        return
    raise AssertionError("swing accepted on a hinge")


# ------------------------------------------------------------------ turntables


def test_turntables_any_angle():
    for base, top in (("3403", "3404"), ("3680", "3679"), ("61485", "60474"), ("61485", "11213")):
        for bend in (0, 30, 45, 90, 200):
            m, a, b = _attach(base, 0, top, 0, bend=bend)
            _assert_joined(m, a, b)


def test_flat_turntable_top_sits_on_the_base():
    # as in 61485c01: the plate's underside on the base's top face (the base's centre ring
    # rises into the plate's hole)
    m, a, b = _attach("61485", 0, "60474", 0, bend=30)
    assert abs(m.geometry(a).pos[1] - m.geometry(b).aabb()[1][1]) < 1.0


# ------------------------------------------------------------------ old families still work


def test_joint8_and_classic_hinge_unchanged():
    m, a, b = _attach("14417", 0, "14704", 0, bend=30, twist=45)
    _assert_joined(m, a, b)
    m, a, b = _attach("3937", 0, "6134", 0, bend=-60)
    _assert_joined(m, a, b)


def test_module_on_a_clip_follows_it():
    """A plate pressed onto a tilted clip plate stays connected to the whole chain."""
    m, a, b = _attach("60478", 0, "63868", 0, bend=-30)
    m.attach("3024", "white", b, 0)
    m.attach("3024", "white", b, 1)
    assert m.check()["connected_groups"] == 1
    assert m.overlaps() == []


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok    {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
