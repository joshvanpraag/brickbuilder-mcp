"""Building instructions (steps, phone PDF, fold-in-half booklet PDF) and the BrickLink
wanted list. From the brickbuilder-mcp folder:
    uv run python tests/test_instructions.py
"""
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from brickbuilder import bricklink, instructions  # noqa: E402
from brickbuilder.model import Model  # noqa: E402


def small_model():
    m = Model("t")
    m.add("3036", "tan", 0, 0, 0, 0)                       # plate 6x8
    for x in range(0, 6, 2):                               # three courses of 2x2 bricks
        for y in (1, 4, 7):
            m.add("3003", "reddish_brown", x, y, 0, 0)
    m.add("3039", "black", 0, 10, 0, 0)                     # a slope on top
    return m


def test_steps_cover_every_part_once_bottom_to_top():
    m = small_model()
    steps = instructions.plan_steps(m, max_parts=4, min_parts=1)
    flat = [i for s in steps for i in s]
    assert sorted(flat) == sorted(m.parts)
    assert all(len(s) <= 4 for s in steps)
    lows = [min(m.parts[i].y for i in s) for s in steps]
    assert lows == sorted(lows)


def test_booklet_places_every_page_once():
    for n in (5, 8, 13, 44):
        sheets, order = instructions.booklet_order(n)
        P = 4 * sheets
        assert P >= n and P - n < 4
        seen = [c for (ft, fb), (bt, bb) in order for c in (ft, fb, bt, bb)]
        assert sorted(seen) == list(range(P))
        (ft, fb), (bt, bb) = order[0]
        assert ft == 0 and fb == P - 1                # cover on top, back cover below it
        assert bb == 2                                # behind the cover: the second page read
        assert order[1][0][0] == 1                    # the first page read: next sheet's top


def test_bricklink_wanted_list():
    m = small_model()
    xml, problems = bricklink.wanted_list(m)
    assert problems == []
    root = ET.fromstring(xml)
    items = root.findall("ITEM")
    assert sum(int(i.find("MINQTY").text) for i in items) == len(m.parts)
    colours = {i.find("COLOR").text for i in items}
    assert colours == {"2", "88", "11"}                 # tan, reddish brown, black on BrickLink
    assert {i.find("ITEMID").text for i in items} == {"3036", "3003", "3039"}


def test_bricklink_part_numbers():
    # checked on bricklink.com: these are filed under the plain number there
    for ours, theirs in (("3040b", "3040"), ("3069b", "3069"), ("3062b", "3062"), ("3070b", "3070"),
                         ("3068b", "3068"), ("4032a", "4032"), ("3001", "3001")):
        assert bricklink.bricklink_part(ours) == theirs, ours


def test_pdfs_are_written():
    m = small_model()
    with tempfile.TemporaryDirectory() as d:
        info = instructions.export(m, Path(d), "Test Model", "a test", max_parts=4)
        assert Path(info["phone"]).stat().st_size > 1000
        assert Path(info["booklet"]).stat().st_size > 1000
        assert info["sheets"] == -(-info["pages"] // 4)


def test_build_pack():
    from brickbuilder import buildpack
    m = small_model()
    with tempfile.TemporaryDirectory() as d:
        info = buildpack.export(m, Path(d), "Test Model", max_parts=4)
        names = sorted(Path(f).name for f in info["files"].values())
        assert names == sorted(["t.ldr", "t.io", "t_bricklink_wanted_list.xml", "t_rebrickable_parts.csv",
                                "t_instructions_phone.pdf", "t_instructions_booklet.pdf", "HOW_TO_BUY.md",
                                "REBRICKABLE_MOC.md", "STUDIO_GALLERY.md"])
        assert len(list(Path(d, "showcase_pictures").glob("*.png"))) == len(buildpack.MOC_VIEWS)
        from PIL import Image
        with Image.open(Path(d, "showcase_pictures", "1_main.png")) as main:
            assert main.width * 4 == main.height * 5             # Rebrickable's 5:4 thumbnail
        assert all(Path(f).stat().st_size > 20 for f in info["files"].values())
        assert "Upload BrickLink XML format" in Path(d, "HOW_TO_BUY.md").read_text(encoding="utf-8")
        # the model file carries the same steps as the PDFs (Studio shows them in the Gallery)
        ldr = Path(d, "t.ldr").read_text()
        assert ldr.count("0 STEP") == info["steps"]
        assert ldr.count("\n1 ") == len(m.parts)
        assert f"same {info['steps']} steps" in Path(d, "STUDIO_GALLERY.md").read_text(encoding="utf-8")


def test_studio_io():
    import json
    import zipfile
    from brickbuilder import studio
    m = small_model()
    steps = instructions.plan_steps(m, max_parts=4, min_parts=1)
    with tempfile.TemporaryDirectory() as d:
        p = studio.write_io(m, Path(d, "t.io"), steps=steps)
        with zipfile.ZipFile(p) as z:
            assert sorted(z.namelist()) == sorted(["model.ldr", "thumbnail.png", "errorPartList.err", ".info"])
            info = json.loads(z.read(".info"))
            assert info["total_parts"] == len(m.parts)
            text = z.read("model.ldr").decode("utf-8-sig")
        assert text.startswith("0 FILE t.io") and text.rstrip().endswith("0 NOFILE")
        assert text.count("\n1 ") == len(m.parts) and text.count("0 STEP") == len(steps)


if __name__ == "__main__":
    for t in (test_steps_cover_every_part_once_bottom_to_top, test_booklet_places_every_page_once,
              test_bricklink_wanted_list, test_bricklink_part_numbers, test_pdfs_are_written,
              test_build_pack, test_studio_io):
        t()
        print("ok", t.__name__)
