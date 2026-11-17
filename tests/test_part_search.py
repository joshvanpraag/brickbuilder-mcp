"""Checks for the part index, find_parts and preview_part.

Run from the brickbuilder-mcp folder (after scripts/build_part_index.py):
    uv run python tests/test_part_search.py
Also works under pytest.
"""
from brickbuilder import part_index, server


def ids(hits):
    return {h["id"] for h in hits}


def test_shape_analysis():
    cone = part_index._analyse("3943b")              # 4x4 cone: narrows going up, round
    assert cone["size"] == [4, 4, 6] and {"round", "narrows_upward", "cone"} <= set(cone["tags"])
    bowl = part_index._analyse("15395")              # 2x2 inverted dome: widens going up
    assert "widens_upward" in bowl["tags"]
    snot = part_index._analyse("87087")              # 1x1 brick with a side stud
    assert snot["studs"]["side"] == 1 and "side_studs" in snot["tags"]
    assert part_index._analyse("14769p0d")["kind"] == "print"


def test_profile_tags():
    # measured from the real shape, not the name: these look alike but are not
    assert part_index._profile_tags("79756") == {"half_round"}     # 1x4 x 2/3 curved top
    assert part_index._profile_tags("3563") == {"half_round"}      # 1x2 x 2/3 curved top
    assert part_index._profile_tags("37352") == {"quarter_round"}  # 1x2 curved top: one edge only
    assert part_index._profile_tags("3044c") == {"ridge"}          # straight double slope
    assert part_index._profile_tags("3043") == {"ridge"}
    for plain in ("3040b", "3039", "3001", "3069b", "3941", "93273"):
        assert not part_index._profile_tags(plain) & {"half_round", "quarter_round"}, plain


def test_search():
    assert part_index.available(), "build the index first: scripts/build_part_index.py"
    assert "3941" in ids(part_index.search("round brick", footprint="2x2", height="3"))
    flare = ids(part_index.search(tags=["widens_upward"], bottom_width="1-1.5", top_width="1.5-2.5", limit=200))
    assert "15395" in flare
    snot = part_index.search("snot", height="3", limit=200)
    assert snot and all(h["studs"]["side"] for h in snot)
    assert "87087" in ids(snot)
    assert not any(h["kind"] == "print" for h in part_index.search("tile round", limit=200))
    assert "98138p2d" in ids(part_index.search("eye closed lashes", include_prints=True))
    assert "No matches" in server.find_parts("zzzz qqqq")


def test_preview_and_info():
    img = server.preview_part("15395")
    assert img.data[:4] == b"\x89PNG"
    info = server.part_info("6233")
    assert "shape: width" in info and "narrows_upward" in info


if __name__ == "__main__":
    for t in (test_shape_analysis, test_profile_tags, test_search, test_preview_and_info):
        t()
        print("ok", t.__name__)
