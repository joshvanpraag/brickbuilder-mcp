"""Checks the Lowell sphere helper (examples/organic_sculpting/lowell_sphere.py).
From the brickbuilder-mcp folder:
    uv run python tests/test_lowell_sphere.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "examples" / "organic_sculpting"))
from lowell_sphere import lowell_sphere  # noqa: E402

from brickbuilder.model import Model  # noqa: E402


def test_sphere_is_whole_round_and_connected():
    m = Model("sphere")
    centre = np.array([0.0, -100.0, 0.0])
    ids = lowell_sphere(m, centre, "red", "black")
    assert len(ids) == 62                              # 6 caps of 9 plates + 8 core bricks
    chk = m.check()
    assert chk["group_sizes"] == [62]                  # everything holds together
    assert not m.overlaps()
    lo = np.min([m.geometry(i).aabb()[0] for i in ids], 0) - centre
    hi = np.max([m.geometry(i).aabb()[1] for i in ids], 0) - centre
    assert np.allclose(lo, -hi, atol=1) and np.ptp(hi) < 2   # the same size every way


if __name__ == "__main__":
    test_sphere_is_whole_round_and_connected()
    print("ok test_sphere_is_whole_round_and_connected")
