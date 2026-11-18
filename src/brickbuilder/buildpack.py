"""A model's build pack: everything needed to buy the parts and build it, in one folder.

    <name>.ldr                          the model (opens in Studio, Mecabricks, LDraw tools)
    <name>.io                           the same model as a BrickLink Studio file
    <name>_bricklink_wanted_list.xml    upload on BrickLink to buy the parts
    <name>_rebrickable_parts.csv        import on Rebrickable (compare with your own sets,
                                        other stores); a readable .txt list next to it
    <name>_instructions_phone.pdf       building instructions, one step per page
    <name>_instructions_booklet.pdf     the same, laid out to print, staple and fold
    HOW_TO_BUY.md                       the steps for BrickLink and Rebrickable
    showcase_pictures/                  renders for sharing the model (5:4, main picture first)
    STUDIO_GALLERY.md                   how to put it in the BrickLink Studio Gallery (the
                                        .ldr carries the same steps as the PDFs)
    REBRICKABLE_MOC.md                  the fields to paste, to publish it as a MOC on Rebrickable
                                        (another option; Rebrickable reviews every MOC)
"""
from __future__ import annotations

from pathlib import Path

from . import bricklink, instructions, rebrickable

HOW_TO = """# {title}: buying the parts and building it

{parts} parts in {lines} part/colour lines. Files in this folder:

| File | What it is for |
|---|---|
| `{name}_bricklink_wanted_list.xml` | Buy the parts on BrickLink |
| `{name}_rebrickable_parts.csv` | Put the parts list on Rebrickable |
| `{name}_instructions_phone.pdf` | Instructions to read on a phone or screen |
| `{name}_instructions_booklet.pdf` | Instructions to print, staple and fold |
| `{name}.io` | The model as a BrickLink Studio file |
| `{name}.ldr` | The model as an LDraw file (Mecabricks, other tools) |

## Buy on BrickLink

1. Log in at bricklink.com and open the upload page:
   https://www.bricklink.com/v2/wanted/upload.page
2. Click the second tab, **Upload BrickLink XML format** (the first tab does not take XML).
3. Open `{name}_bricklink_wanted_list.xml` in Notepad, select all, copy, and paste it into
   the box.
4. Keep **Create New Wanted List**, name it "{title}", press **Proceed to verify items**,
   then **Add to Wanted List**.
5. Open the wanted list and press **Buy All**: BrickLink suggests a few sellers that
   between them have everything. Fewer sellers means less shipping. Used parts are
   usually cheaper; a maximum price per part keeps overpriced sellers out.

## Put it on Rebrickable

Rebrickable does not sell parts. It shows which of your own sets already have them, and
compares stores (BrickLink, Brick Owl, LEGO Pick a Brick).

1. Log in at rebrickable.com, open **My LEGO > Part Lists** and create a new list named
   "{title}".
2. On that list choose **Import Parts**, pick the **Rebrickable CSV** format and choose
   `{name}_rebrickable_parts.csv`. (Rebrickable also takes the BrickLink XML or the
   `.ldr` file, if you prefer.)
3. To see what you still need: add your sets under **My LEGO > Sets**, then use
   **Build** on the part list (or the "Can I build it?" check) against your collection.
4. To buy what is missing, export the missing parts as a BrickLink wanted list or use
   **Buy Parts** to compare stores.

## Print the booklet

Print `{name}_instructions_booklet.pdf` on US letter paper, **both sides**, with the
printer's normal "flip on long edge" setting ({sheets} sheets). Keep the sheets in order,
staple across the middle and fold in half. The top half of the outside sheet is the cover.
Open it like a calendar: read the top page, then the bottom page, then flip on. (On screen
the PDF looks scrambled; that is how the pages land in order once folded.)
"""


def export(model, out_dir: Path, title: str | None = None, max_parts: int = 40, moc: bool = True,
           story: str = "", theme: str = "Modular Buildings", tags: list[str] | None = None,
           category: str | None = None) -> dict:
    """Write the build pack for `model` into out_dir. Returns the paths and counts.
    tags/category: for the BrickLink Studio Gallery form (up to 10 tags)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = model.name
    title = title or name.replace("_", " ").title()
    files = {}
    ldr = out / f"{name}.ldr"
    # the model file carries the instruction steps, so Studio's own instructions match the PDFs
    steps = instructions.plan_steps(model, max_parts=max_parts)
    ldr.write_text(model.to_ldr(steps=steps))
    files["ldr"] = str(ldr)
    from . import studio                     # the same model as a BrickLink Studio file
    files["io"] = str(studio.write_io(model, out / f"{name}.io", steps=steps, title=title))
    xml, problems = bricklink.wanted_list(model)
    bl = out / f"{name}_bricklink_wanted_list.xml"
    bl.write_text(xml)
    files["bricklink"] = str(bl)
    csv_text, readable = rebrickable.parts_list(model)
    rb = out / f"{name}_rebrickable_parts.csv"
    rb.write_text(csv_text)
    rb.with_suffix(".txt").write_text(readable + "\n")
    files["rebrickable"] = str(rb)
    info = instructions.export(model, out, title, f"{len(model.parts)} parts", max_parts=max_parts)
    # name the PDFs after the model, not the title
    for key in ("phone", "booklet"):
        target = out / f"{name}_instructions_{key}.pdf"
        if Path(info[key]) != target:
            target.unlink(missing_ok=True)
            Path(info[key]).rename(target)
        files[key] = str(target)
    lines = xml.count("<ITEM>")
    how = out / "HOW_TO_BUY.md"
    how.write_text(HOW_TO.format(title=title, name=name, parts=len(model.parts), lines=lines,
                                 sheets=info["sheets"]), encoding="utf-8")
    files["how_to"] = str(how)
    if moc:                                  # pictures, Studio Gallery and Rebrickable guides
        kit = moc_kit(model, out, title, story, theme)
        files["moc_guide"] = kit["guide"]
        files["studio_guide"] = studio_kit(model, out, title, story, kit["names"], info["steps"],
                                           tags=tags, category=category)
    return {"files": files, "steps": info["steps"], "pages": info["pages"], "sheets": info["sheets"],
            "problems": problems}


# ------------------------------------------------------------------------------- Rebrickable MOC

MOC_VIEWS = [  # (file name, azimuth, elevation): the first is the main picture
    ("1_main", -35, 25), ("2_front", 0, 6), ("3_front_right", 35, 25),
    ("4_back", 145, 28), ("5_side", -90, 8), ("6_above", -25, 62),
]
STUD_IN, PLATE_IN = 0.315, 0.126          # one stud (8 mm) and one plate (3.2 mm) in inches

MOC_GUIDE = """# {title}: publishing it as a MOC on Rebrickable

Rebrickable's own guide: https://rebrickable.com/help/submit-moc-how-to/ and the rules:
https://rebrickable.com/help/mocs-submit/ . Start at **MOCs > Submit a MOC** (logged in).
You can save after each step and come back; an admin reviews it before it goes live.

## Step 1 - Description

- **MOC Name:** {title}
- **Theme:** {theme}
- **Description**: copy everything between the two lines below and paste it in (edit as you like).

---

{description}

---

## Step 2 - Images

Upload the pictures in `showcase_pictures/` (renders of the model, 5:4, the whole model in
view, no LEGO logo). Make `1_main.png` the primary image. Up to 12 images are allowed.

{images}

## Step 3 - Instructions

- Choose **Free Instructions** (or For Sale; premium MOCs need a PDF, no inventory errors
  and an admin's approval of quality).
- Upload `{name}_instructions_phone.pdf` (one step per page, best for reading on screen).
- Leave the "based on a Set/MOC" part empty: this is an original design.

## Step 4 - Inventory

- Click **Import/Delete Parts**, choose `{name}_rebrickable_parts.csv`, then **+ Append Parts**.
- If the inventory shows errors (usually an older or newer mould of the same part), click
  each one and pick the suggested equivalent.
- Expect {parts} parts in {lines} lines.

## Step 5 - Submit

Press **Submit MOC for Approval**. It shows as "Waiting for Approval" under Account >
Submissions; you get an email when it is approved, or a note if something needs fixing.
"""


def describe(model, title: str, story: str = "") -> tuple[str, str]:
    """(description text, size line) with the model's facts filled in."""
    from collections import Counter
    b = model.bounds()
    w, d, h = b[1] - b[0] + 1, b[5] - b[4] + 1, b[3] - b[2] + 1
    size = (f"{w} x {d} studs, {h} plates tall: about {w * STUD_IN:.1f} x {d * STUD_IN:.1f} x "
            f"{h * PLATE_IN:.1f} in")
    colours = Counter(rebrickable.colour_name(p.color) if rebrickable.available() else str(p.color)
                      for p in model.parts.values())
    palette = ", ".join(c for c, _ in colours.most_common())
    text = (f"{story.strip()}\n\n" if story else "") + (
        f"- {len(model.parts)} parts\n"
        f"- Size: {size}\n"
        f"- Colours: {palette}\n"
        f"- Step-by-step PDF instructions included\n"
        f"- Pictures are renders of the digital model; every part exists in its colour and the "
        f"model was checked to hold together.")
    return text, size


def moc_kit(model, out_dir: Path, title: str, story: str = "", theme: str = "Modular Buildings",
            size: int = 1500) -> dict:
    """Pictures and a fill-in guide for submitting the model as a MOC on Rebrickable."""
    out = Path(out_dir)
    pics = out / "showcase_pictures"
    pics.mkdir(parents=True, exist_ok=True)
    scene = instructions._scene(model)
    sub = instructions._subset(scene, list(model.parts))
    from . import render
    names = []
    for fname, az, el in MOC_VIEWS:
        img = render.render_real_view(sub, az, el, size, size * 4 // 5)       # 5:4
        p = pics / f"{fname}.png"
        img.save(p)
        names.append(p.name)
    text, _ = describe(model, title, story)
    lines = len({(p.part, p.color) for p in model.parts.values()})
    guide = out / "REBRICKABLE_MOC.md"
    guide.write_text(MOC_GUIDE.format(
        title=title, theme=theme, name=model.name, parts=len(model.parts), lines=lines,
        description=text,
        images="\n".join(f"- `showcase_pictures/{n}`" for n in names)), encoding="utf-8")
    return {"guide": str(guide), "images": [str(pics / n) for n in names], "names": names}


# ------------------------------------------------------------------------------- Studio Gallery

STUDIO_GUIDE = """# {title}: sharing it in the BrickLink Studio Gallery

`{name}.io` is the model as a Studio file. It carries the same {steps} steps as the PDF
instructions, so the Gallery's "View Instructions" matches the booklet. (It opens in Studio
as it is; if it ever won't, import `{name}.ldr` in Studio and save it as `.io`.)

Start at bricklink.com > **My Studio** > upload a design (logged in). The form has three steps.

## Step 1 of 3 - Upload Studio file

Upload `{name}.io` from this folder.

## Step 2 of 3 - Select sharing option

- **Full Access** (recommended): shown in the Gallery with the instructions and parts list;
  you choose whether people can download the file. BrickLink reviews Full Access designs by
  hand; until then it shows in Display mode (pictures only).
- **Display:** pictures only, no instructions, parts list or download.
- **Private:** only you.

## Step 3 of 3 - Enter design details

| Field | What to put |
|---|---|
| **Design name** (64 characters max) | {title} |
| **Category** | {category} |
| **Tags** (up to 10) | see **Tags** below: one at a time |
| **Featured images** (up to 10, 4:3, 2 MB max) | the pictures in `studio_pictures/`, in this order (the first is the thumbnail): {images} |
| **Artistic statement** | copy the text between the two lines below |

**Tags**: the tags box only makes a tag when you press Enter, so pasting a whole list does
not work. Copy one line, paste it into the box, press **Enter**, and repeat:

{tags}

---

{statement}

---

**Add more details (optional)**: click **Add description** and paste this:

---

{extra}

---

Then **Preview**, and **Publish** (or **Save for later**). Copy the design's Gallery link
to share. The Gallery cannot hold our PDFs, so send `{name}_instructions_phone.pdf` and
`{name}_instructions_booklet.pdf` along with the link for anyone who wants them.
"""

STUDIO_EXTRA = """Build it yourself
- Instructions: {steps} steps, the same as the printable booklet (Full Access shows them here as "View Instructions").
- Parts: {parts} parts in {lines} part/colour lines, all in common colours. Use the parts list on this page to buy them through BrickLink.
- A printable booklet (letter paper, fold in half) and a phone/tablet PDF of the instructions are available from the designer."""


def studio_kit(model, out_dir: Path, title: str, story: str, picture_names: list[str] | None, steps: int,
               tags: list[str] | None = None, category: str | None = None, size: int = 1200) -> str:
    """STUDIO_GALLERY.md, walking through BrickLink's three-step upload form field by field,
    with 4:3 pictures under 2 MB (the Gallery's shape and size limit) in studio_pictures/."""
    out = Path(out_dir)
    pics = out / "studio_pictures"
    pics.mkdir(parents=True, exist_ok=True)
    scene = instructions._scene(model)
    sub = instructions._subset(scene, list(model.parts))
    from . import render
    names = []
    for fname, az, el in MOC_VIEWS:
        img = render.render_real_view(sub, az, el, size, size * 3 // 4)        # 4:3
        p = pics / f"{fname}.png"
        img.save(p, optimize=True)
        if p.stat().st_size > 2_000_000:                                      # the Gallery's limit
            p.unlink()
            p = pics / f"{fname}.jpg"
            img.save(p, quality=90)
        names.append(p.name)
    text, _ = describe(model, title, story)
    lines = len({(p.part, p.color) for p in model.parts.values()})
    tags = (tags or [title, "building", "architecture"])[:10]
    guide = out / "STUDIO_GALLERY.md"
    guide.write_text(STUDIO_GUIDE.format(
        title=title[:64], name=model.name, steps=steps, statement=text,
        category=category or "the closest match to buildings or architecture in the list",
        tags="\n".join(f"    {t}" for t in tags),  # one per line: the box takes one tag per Enter
        images=" ".join(f"`{n}`" for n in names),
        extra=STUDIO_EXTRA.format(steps=steps, parts=len(model.parts), lines=lines)), encoding="utf-8")
    return str(guide)
