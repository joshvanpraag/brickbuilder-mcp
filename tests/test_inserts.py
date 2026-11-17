"""Window glass seated in its frame counts as connected and does not clash with the frame.
From the brickbuilder-mcp folder:
    uv run python tests/test_inserts.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from brickbuilder.model import BuildError, Model  # noqa: E402


def test_glass_in_frames():
    m = Model("t")
    m.add("3036", "tan", 0, 0, 0, 0)                     # plate 6x8 to stand on
    for rot, (x, z) in zip((0, 90), ((1, 1), (4, 1))):
        f = m.add("60592", "tan", x, 1, z, rot)           # window 1 x 2 x 2
        g = m.add_insert("60601", "trans_dark_blue", f.id)
        assert f.id in m.connections()[g.id]
    f3 = m.add("60593", "tan", 1, 1, 5, 0)                # window 1 x 2 x 3
    m.add_insert("60602", "trans_dark_blue", f3.id)
    assert m.check()["group_sizes"] == [7]          # plate + 3 frames + 3 panes
    assert m.overlaps() == []


def test_two_panes_in_round_corner_window():
    m = Model("t")
    m.add("3036", "tan", 0, 0, 0, 0)
    f = m.add("73878", "white", 1, 1, 1, 0)               # window round corner 3 x 3 x 2
    a = m.add_insert("60601", "trans_clear", f.id)
    b = m.add_insert("60601", "trans_clear", f.id)
    assert m._geom[a.id].pos.tolist() != m._geom[b.id].pos.tolist()
    adj = m.connections()
    assert f.id in adj[a.id] and f.id in adj[b.id]
    assert m.check()["group_sizes"] == [4]
    assert m.overlaps() == []
    try:
        m.add_insert("60601", "trans_clear", f.id)        # both seats taken
    except BuildError:
        return
    raise AssertionError("a third pane was accepted")


def test_wrong_frame_is_refused():
    m = Model("t")
    f = m.add("3005", "tan", 0, 0, 0, 0)
    try:
        m.add_insert("60601", "trans_clear", f.id)
    except BuildError:
        return
    raise AssertionError("glass accepted in a plain brick")


if __name__ == "__main__":
    test_glass_in_frames()
    test_two_panes_in_round_corner_window()
    test_wrong_frame_is_refused()
    print("ok")
