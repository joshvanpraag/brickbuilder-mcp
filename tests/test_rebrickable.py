"""Checks for the Rebrickable catalogue (rebrickable.py) and its tools.

Needs scripts/fetch_rebrickable.sh. From the brickbuilder-mcp folder:
    uv run python tests/test_rebrickable.py
"""
from brickbuilder import rebrickable as R
from brickbuilder.model import Model


def test_catalogue_installed():
    assert R.available(), "run scripts/fetch_rebrickable.sh first"


def test_lookup_bridges_ldraw_numbers():
    assert R.lookup("3001")[0] == "3001"
    assert R.lookup("14769p0d")[0] == "14769"             # LDraw print -> plain base part
    assert R.lookup("41769a")[0] in ("41769", "41769a")    # LDraw variant letter


def test_real_colours():
    assert 4 in R.colours_of("3001")                        # brick 2 x 4 in red: obviously made
    assert set(R.colours_of("14417")) == {72}               # the small ball plate: dark bluish gray only


def test_colour_problems_and_parts_list():
    m = Model("colours")
    m.add("3001", 4, 0, 0, 0)                               # red 2x4: fine
    m.add("14417", 4, 0, 3, 0)                              # red ball plate: never made
    probs = R.colour_problems(m)
    assert len(probs) == 1 and "14417" in probs[0] and "Dark Bluish Gray" in probs[0]
    csv_text, readable = R.parts_list(m)
    assert csv_text.splitlines()[0] == "Part,Color,Quantity" and len(csv_text.splitlines()) == 3


if __name__ == "__main__":
    for t in (test_catalogue_installed, test_lookup_bridges_ldraw_numbers, test_real_colours,
              test_colour_problems_and_parts_list):
        t()
        print("ok", t.__name__)
