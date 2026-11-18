"""BrickLink wanted list: an XML file to upload on bricklink.com (Want > Upload), which then
finds sellers for the whole order.

BrickLink numbers parts and colours its own way. Part numbers mostly match Rebrickable's;
where they don't, PART_IDS says what BrickLink calls the part (checked against BrickLink's
catalogue). Colours are mapped from LDraw codes to BrickLink colour ids in COLOURS.
"""
from __future__ import annotations

from collections import Counter
from xml.sax.saxutils import escape

# LDraw colour code -> BrickLink colour id (the common solid and transparent colours)
COLOURS = {
    0: 11,    # Black
    1: 7,     # Blue
    2: 6,     # Green
    4: 5,     # Red
    6: 8,     # Brown (old)
    7: 9,     # Light Gray (old)
    8: 10,    # Dark Gray (old)
    14: 3,    # Yellow
    15: 1,    # White
    19: 2,    # Tan
    25: 4,    # Orange
    28: 69,   # Dark Tan
    70: 88,   # Reddish Brown
    71: 86,   # Light Bluish Gray
    72: 85,   # Dark Bluish Gray
    272: 63,  # Dark Blue
    288: 80,  # Dark Green
    308: 120,  # Dark Brown
    320: 59,  # Dark Red
    378: 48,  # Sand Green
    484: 68,  # Dark Orange
    33: 14,   # Trans-Dark Blue
    34: 20,   # Trans-Green
    36: 17,   # Trans-Red
    40: 13,   # Trans-Black
    43: 15,   # Trans-Light Blue
    46: 19,   # Trans-Yellow
    47: 12,   # Trans-Clear
}

# Rebrickable / LDraw part number -> BrickLink part number, where they differ. Each was
# checked on bricklink.com: BrickLink files these under the plain number, without the letter.
PART_IDS = {
    "3040b": "3040",     # Slope 45 2 x 1
    "3046a": "3046",     # Slope 45 2 x 2 Double Concave
    "3023b": "3023",     # Plate 1 x 2
    "3062b": "3062",     # Brick, Round 1 x 1
    "3068b": "3068",     # Tile 2 x 2
    "3069b": "3069",     # Tile 1 x 2
    "3070b": "3070",     # Tile 1 x 1
    "4032a": "4032",     # Plate, Round 2 x 2 with Axle Hole
}


def bricklink_part(part: str) -> str:
    from . import rebrickable
    rb = rebrickable.lookup(part)[0] if rebrickable.available() else None
    pid = rb or part
    return PART_IDS.get(pid, PART_IDS.get(part, pid))


def wanted_list(model) -> tuple[str, list[str]]:
    """(XML text for BrickLink's wanted list upload, problems). Problems name parts whose
    colour has no BrickLink id here; they are left out of the XML."""
    count = Counter((p.part, p.color) for p in model.parts.values())
    items, problems = [], []
    for (part, colour), n in sorted(count.items(), key=lambda kv: (-kv[1], kv[0])):
        bl_colour = COLOURS.get(int(colour))
        if bl_colour is None:
            problems.append(f"{part} in LDraw colour {colour}: no BrickLink colour id known")
            continue
        items.append(
            "  <ITEM>\n"
            "    <ITEMTYPE>P</ITEMTYPE>\n"
            f"    <ITEMID>{escape(bricklink_part(part))}</ITEMID>\n"
            f"    <COLOR>{bl_colour}</COLOR>\n"
            f"    <MINQTY>{n}</MINQTY>\n"
            "  </ITEM>")
    return "<INVENTORY>\n" + "\n".join(items) + "\n</INVENTORY>\n", problems
