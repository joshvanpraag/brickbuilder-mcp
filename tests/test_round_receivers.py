"""2x2 cones sit on studs like any other part, and round parts fit flush between neighbours.
From the brickbuilder-mcp folder:
    uv run python tests/test_round_receivers.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from brickbuilder.model import Model  # noqa: E402


def test_cones_and_domes_connect():
    for part in ("3942a", "3942b", "3942c"):
        m = Model("t")
        base = m.add("3003", "red", 0, 0, 0, 0)          # brick 2x2
        top = m.add(part, "orange", 0, 3, 0, 0)
        assert base.id in m.connections()[top.id], part
        assert m.check()["group_sizes"] == [2], part


def test_round_parts_fit_flush():
    # a round 2x2 plate / brick boxed in by 2x2 tiles on all eight sides: no clash
    for part in ("4032a", "3941"):
        m = Model("t")
        m.add("3036", "blue", 0, 0, 0, 0)               # plate 6x8 underneath
        m.add(part, "blue", 2, 1, 2, 0)
        for x, z in [(0, 2), (4, 2), (2, 0), (2, 4), (0, 0), (4, 4), (0, 4), (4, 0)]:
            m.add("3068b", "blue", x, 1, z, 0)
        assert m.overlaps() == [], part


if __name__ == "__main__":
    test_cones_and_domes_connect()
    test_round_parts_fit_flush()
    print("ok")
