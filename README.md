# brickbuilder-mcp

**Show Claude a photo, get a buildable LEGO model back.**

An MCP server that lets Claude design LEGO models brick by brick, usually from a
reference picture, check that they actually hold together, and export them as LDraw
`.ldr` files that [Mecabricks](https://www.mecabricks.com) and
[BrickLink Studio](https://www.bricklink.com/v3/studio/download.page) open directly.

![Reference still of Helm's Deep next to the 41,864-part LEGO build](docs/compare_helms_deep.jpg)

## What it looks like

Every build below was made by Claude through this server from the photo on the left.
Nothing was placed by hand.

![Airliner cabin: reference photo and LEGO build](docs/compare_airliner_cabin.jpg)

![Bowling alley: reference photo and LEGO build](docs/compare_bowling_alley.jpg)

<p align="center"><img src="docs/build_airliner.gif" width="300" alt="The airliner cabin building itself course by course"></p>

The models are real, buildable LEGO: standard parts in real colours, bricks laid in
staggered courses, and a connectivity check that flags anything floating before export.

## Setup

> **New computer, or don't code?** Follow [RESTORE.md](RESTORE.md): a step-by-step guide
> to getting this tool and everything built with it back from GitHub.
> For curvy, character-style builds, see [docs/organic_sculpting.md](docs/organic_sculpting.md)
> and the worked example in [examples/organic_sculpting](examples/organic_sculpting/).

Needs Python 3.11+, [uv](https://docs.astral.sh/uv/), `curl` and `unzip`.

```bash
git clone https://github.com/ElRashoMacuin24/brickbuilder-mcp.git
cd brickbuilder-mcp
scripts/fetch_ldraw.sh   # downloads the LDraw parts library (~145 MB zip) into data/ldraw
scripts/fetch_ldcad_snaps.sh   # connection data for pins, axles, clips, hinges (~2 MB)
uv sync
uv run python scripts/build_part_index.py   # part search index (a few minutes, once)
scripts/fetch_rebrickable.sh   # real-world catalogue: colours each part was made in (~17 MB)
claude mcp add brickbuilder -s user -- uv --directory "$PWD" run brickbuilder-mcp
```

Restart Claude Code, then run `/mcp` and check that `brickbuilder` is listed.
Other MCP clients work too: run `uv --directory /path/to/brickbuilder-mcp run brickbuilder-mcp` over stdio.

## How to use it

### 1. Give Claude a picture and a goal

Paste or drag an image into Claude Code (or give a path) and say what you want.
The more you say about scale, the better:

> Build this scene in LEGO without the people. Make it minifig scale, so the chairs
> are just big enough for a minifig to sit in.

> Build this house in LEGO, about 16 studs wide: ~/Pictures/house.jpg

> Make a 48×48 flat mosaic of this logo: ~/Pictures/logo.png

Useful things to specify:

- **Scale**: "minifig scale" (doors, seats and stairs sized for minifigures),
  "microscale", or a size in studs ("about 32 studs wide").
- **What to leave out**: people, background, text.
- **Colours**: "use only common colours" keeps it cheap to build for real.

### 2. Let it work, then steer

Claude plans the scale, builds bottom-up, renders previews next to your photo and
fixes what doesn't match. Ask for changes in plain language:

> The orange is too brown, use a redder shade.
> Make the tower taller and add windows.
> The left rack is hidden behind the bench, move it.

### 3. Export and open it

When you're happy, ask Claude to export. The file lands in `exports/<name>.ldr`.

- **Mecabricks**: Workshop → File → Import → LDraw, then pick the file. You can publish it to the
  Mecabricks gallery from there.
- **BrickLink Studio**: File → Import → Import LDraw. Studio also gives you a parts list and
  prices to buy the bricks. It handles very large models better than a browser tab.

If Mecabricks shows missing parts, ask Claude to re-export with `legacy_ids` (older part
numbers such as `3023` instead of `3023b`).

### 4. Pick it up later, on any computer

Models autosave to `models/<name>.json`. Say "open the bowling alley model" in a later
session to keep editing. Copy `models/` and `exports/` to another machine to take your
builds with you.

## Tools

| Tool | Purpose |
|---|---|
| `new_model` / `open_model` / `list_models` | Models autosave to `models/*.json` |
| `list_parts`, `list_colors` | Curated catalog, full LDraw library search, colour codes |
| `add_parts`, `remove_parts`, `undo` | Place parts on the stud grid, with collision checks; `up`/`ldu` for turned parts |
| `attach_parts` | Press a part onto any stud, in any direction (sideways building / SNOT) |
| `insert_parts` | Seat window glass in a placed window frame (it clips in rather than using studs) |
| `attach_joint` | Connect parts by ball joint, hinge, clip on bar or turntable at any angle (posed modules) |
| `part_info`, `list_studs`, `list_joints` | A part's studs, receivers, joints and shape (width at four heights); a placed part's studs/joints and what is on them |
| `find_parts` | Search all ~25,000 LDraw parts by words and by shape: footprint, height, taper (width at bottom and top), tags like round / widens_upward / curved / side_studs |
| `preview_part` | Render one part from several angles, to see its real shape before building with it |
| `build_part_index` | Build the search index `find_parts` uses (once, a few minutes) |
| `fill_layers` | Colour layer maps packed automatically into bricks/plates/tiles in running bond |
| `image_to_grid`, `build_mosaic` | Quantize pictures to LEGO colours; build mosaics |
| `describe_model`, `check_model` | Per-level maps, part counts, floating/loose-part detection from real stud contact |
| `check_strength` | Where the model would break: sections hanging on one weak link, ranked by weight, leverage and link strength |
| `check_colors` | Parts used in a colour LEGO never made for them, with the closest real colours |
| `export_parts_list` | Parts list as a Rebrickable import CSV plus a readable list, to buy the bricks |
| `export_bricklink` | BrickLink wanted list (XML) to upload and buy the whole model |
| `export_instructions` | Building instructions: a phone PDF and a print-and-fold booklet PDF |
| `render_model` | Preview sheet with real part shapes (or `detail="simple"`), optionally beside the reference picture |
| `export_ldr` | LDraw file, one build step per level; `legacy_ids` for older part numbers |

### Grid

- `x`: studs to the right; `z`: studs toward the back (z=0 is the front); `y`: plates up (brick = 3).
- A part's position is the min corner of its body after rotation.
- `rot` 0/90/180/270 (or front/right/back/left). A slope's sloped face points
  that way. At rot 0 a 2x4 brick is 4 studs long in x.

### Sideways building (SNOT)

Sculpted models cover a core of side-stud bricks (87087, 4733, 32952, 67329, 11211)
and brackets (99780, 99207, 99781, 44728, ...) with outward-facing curved slopes,
tiles and wedges. To build that way:

- `list_studs(id)` shows a placed part's studs, which way each points and whether
  it is free.
- `attach_parts` presses a new part's receiver (an underside stud hole, see
  `part_info`) onto one of those studs. The new part's top then faces the stud's
  direction, and `rot` spins it about that direction.
- Overlap checks follow each part's real outline to 1 LDU, so a part that only touches a
  round column or a rounded end at an angle is not counted as an overlap.
- `turn` (on `attach_parts`) turns a part held by one stud to any angle, e.g. 45
  degrees: a flat window on the angled face of a bay, or a panel turned a few
  degrees. It still counts as connected through that one stud.
- `add_parts` also accepts `up` (up/down/front/back/right/left) to place a turned
  part by its grid corner, or `ldu=[x, y, z]` for an exact LDraw position.

Studs come from the stud primitives in each part's LDraw file. Receivers are
derived from the underside shape: one per stud cell whose walls reach a common
plane with room for a stud. Collisions for turned parts use each part's real
shape, voxelized at 4 LDU. `check_model` counts a connection wherever a stud sits
in a receiver facing the opposite way, in any direction.
A few parts are drawn with an underside the detection can't read (a cone's round hollow,
a curved inverted slope); their stud holes are listed by hand in `geometry.py`, so 2x2
cones (3942) sit on a 2x2 of studs like a round brick does. Round parts are also measured
with a small tolerance, so a round 2x2 plate fits flush between tiles without a false overlap.

### Joints (posed models)

Organic models are built as modules (arm, tail segment, shell panel) joined at angles
that are not 90 degree steps:

- **Ball joints (joint-8):** balls 14417, 22890, 3170 and 22484; sockets 14704,
  14418, 63082 and 98263. The joints are read from the joint primitives in each
  part's LDraw file. `attach_joint` puts the new part's ball in the socket (or the
  socket on the ball): `bend` and `swing` tilt it up to 45 degrees combined, and
  `twist` turns it about the joint's axis.
- **Large balls** (each system only mates with itself): towballs 3731, 15456, 3614a
  and 3184 into the towball socket 3730 (up to 60 degrees of tilt); the brick 2x2 with
  two balls 17114 into the 2x2 socket bricks 62712, 92013, 57910 and 67696 (45 degrees).
  Same `bend` / `swing` / `twist` as joint-8.
- **Hinges:** 3937 (hinge base) with 6134 (hinge top); hinge plates 2429 + 2430 (1x4
  swivel, turns in its own plane); locking hinge plates 44301a + 44302a (any part drawn
  with the `clh4` / `clh6` click-hinge primitives). `bend` is the hinge angle, any value.
- **Clips on bars:** clips are read from the `clip*.dat` primitives (61252, 63868,
  60470, 11090, 11476, ...; 15712 by override). Bars are handles (pairs of `phandle*.dat`,
  e.g. 60478, 48336, 2540, 26047) and plain bars (4 LDU cylinders in parts titled
  "Bar ...", e.g. 87994 Bar 3L). `bend` turns the clip round the bar, `slide` moves it
  along the bar in LDU (`list_joints` shows each bar's range) and `flip` turns the new
  part end for end. At `bend` 0 the clip's part stands on the far side of the bar from
  the bar's part, the same way up, so 63868 on 60478 continues the plate flat.
- **Turntables:** 3403 + 3404, 3680 + 3679, and the flat base 61485 under a round plate
  with snapstud (60474, 11213, 74611, 89523, 87081). `bend` turns the top about the
  vertical axis.
- **Building out from a joint:** `attach_parts` onto a tilted part follows its tilt,
  so a whole module builds outward from its joint at that angle.
- **Checks:** `check_model` counts joints as connections. It also reports any parts
  whose real shapes pass into each other: points every 2 LDU inside each part are
  tested against the other part's solid, in that part's own frame, with a 1.5 LDU
  margin. So touching is fine, and tilted parts can't hide an overlap.

### Joint guide in plain words

Every joint works the same way: place the first part, ask `list_joints` for its joint
numbers, then call `attach_joint` with the second part. `bend` is the angle in degrees.
Each kind of joint only connects to its own partner; the tool says so if you mix them.

| Joint | Part A (place first) | Part B (attach) | What you can set |
|---|---|---|---|
| Small ball (joint-8) | 14417, 22890, 3170, 22484 | sockets 14704, 14418, 63082, 98263 | `bend`, `swing` (tilt, 45 degrees max together), `twist` |
| Towball | 3731, 15456, 3614a, 3184 | socket 3730 | `bend`, `swing` (60 degrees max), `twist` |
| Big ball | 17114 (brick 2x2 with a ball at each end) | socket bricks 62712, 92013, 57910, 67696 | `bend`, `swing` (45 degrees max), `twist` |
| Hinge | 3937 hinge base | 6134 hinge top | `bend` = hinge angle |
| Swivel hinge plate (turns flat) | 2429 | 2430 | `bend` = angle in the plate's own plane |
| Locking hinge plate | 44301a | 44302a | `bend` = fold angle (negative folds up) |
| Clip on a bar | a bar: handles 60478, 48336, 2540, 26047 or plain bars like 87994 | a clip: 61252, 63868, 60470, 15712, 11090, 11476 | `bend` = angle round the bar, `slide` = move along the bar (LDU, 20 = one stud), `flip` = turn end for end |
| Turntable | 3403 (4x4), 3680 (2x2), 61485 (flat 4x4) | 3404, 3679, or a round plate with snapstud (60474, 11213, 74611, 89523, 87081) on 61485 | `bend` = turn about the vertical axis |
| Technic pin | a part with a pin hole (beams, bricks with holes such as 3700, liftarms) | a pin: 2780, 6558, or any part with a pin (32054 ...) | `bend` = turn the pin in the hole, `flip` = turn end for end |
| Technic axle | a part with an axle hole (cross hole) or a round pin hole | an axle: 3705 and other axles, or parts with an axle | `bend` = turn (90 degree steps in a cross hole, any angle in a round hole), `slide` = move along the hole |
| Hinge fingers | a part with hinge fingers (finger_m) | the matching part (finger_f) | `bend` = hinge angle |

Either part can be placed first: a clip can go onto a placed bar, or a bar through a
placed clip.

Example: a hand-hold plate (60478, part #1) with a clip plate swung down 45 degrees:

```json
attach_joint(parts=[{"part": "61252", "color": "blue", "to_id": 1, "to_joint": 0,
                     "joint": 0, "bend": 45}])
```

A clip plate (63868) slid 10 LDU (half a stud) along the long handle of 48336 (#1):

```json
attach_joint(parts=[{"part": "63868", "color": "yellow", "to_id": 1, "bend": -30, "slide": 10}])
```

A big ball socket brick on the ball of 17114 (#1), tilted 20 degrees:

```json
attach_joint(parts=[{"part": "62712", "color": "blue", "to_id": 1, "to_joint": 0, "bend": 20}])
```

A turntable top turned 30 degrees on its base 3403 (#1):

```json
attach_joint(parts=[{"part": "3404", "color": "red", "to_id": 1, "bend": 30}])
```

A Technic pin (2780) pushed into a brick with a hole (3700, #1):

```json
attach_joint(parts=[{"part": "2780", "color": "black", "to_id": 1, "to_joint": 0, "joint": 0}])
```

Wheels, as most minifig-scale cars mount them
([demo](examples/vehicles/wheels_demo.py), [render](examples/vehicles/renders/wheels_demo.png)):
- **On an axle pin:** an axle pin (3749) goes into a brick with a hole (3700) by its `pin`
  joint, and a rim goes on its `axle` joint. A rim grips the axle with a thin ring, so it
  can `slide` along the axle end.
- **On a wheel holder:** a rim's `bar_hole` goes onto a wheel holder's pin (`bar`), e.g.
  6014b on 4600. Use `flip` so each rim faces out. Grid placement lines a wheel holder up by
  its plate, not its pins.
- **Tyres:** a tyre's `tyre` joint goes onto a rim's `tyre_seat`. It sits where LDraw's
  ready-made rim + tyre parts put it, and a tyre that doesn't fit the rim is refused. Wheels
  missing from the LDCad data (such as 6014b) get their hub hole from the drawn shape.

**Where the Technic, finger and extra clip/bar joints come from:** the
[LDCad shadow library](https://github.com/RolandMelkert/LDCadShadowLibrary) lists every
connection point (stud, hole, bar, clip, pin, axle, ball, hinge finger) of about 3,400 parts
and primitives. `scripts/fetch_ldcad_snaps.sh` downloads it into `data/ldcad_shadow`, and the
server adds those connections to any part where its own detection found none. It adds bars
to about 1,700 parts, clips to about 150, and pins, pin holes, axles, axle holes and hinge
fingers to about 2,500. `part_info` lists every connector a part has, and `find_parts`
can search by them (tags `pin`, `pin_hole`, `axle`, `axle_hole`, `hinge_fingers`; joint
`bar_hole`). Without
the download, everything else still works; those joints just aren't there.

Each of these joints is checked against the part's drawn shape before it is used (the
surface must sit about one connector radius from the joint, and a hole must be open), so
data that doesn't fit the LDraw model is ignored. `uv run python scripts/audit_snap_joints.py`
reports how many of each kind are kept and dropped, and on which parts. Every bar, pin,
axle and ball passes. About 98% of pin holes and 94% of axle holes pass, and the ones
dropped are mostly on Duplo, electric, train and minifig parts.

### Real parts in real colours

The LDraw library says what a part looks like, not whether LEGO ever made it in tan.
`scripts/fetch_rebrickable.sh` downloads Rebrickable's free catalogue (about 17 MB) and
indexes which colours each part really came in, in how many sets, and in which years.

- **`part_info`:** adds a "Real world" line, for example *made in 1 colour, 2014-2026:
  Dark Bluish Gray (694 sets)* for the small ball plate 14417.
- **`find_parts(color=...)`:** only lists parts that were made in that colour.
- **`check_colors`:** flags every part in the model whose colour never existed for it,
  and suggests the closest real colours. For example, the small ball-joint plates
  14417 / 14704 were only ever made in dark bluish gray.
- **`export_parts_list`:** writes the model's parts as a CSV that rebrickable.com can
  import as a part list. From there you can export a BrickLink wanted list to buy the
  bricks, or see which of your own sets already contain them.

Printed LDraw parts are looked up as their plain base part.

### Buying the parts and building instructions

- **`export_bricklink`:** writes a BrickLink wanted list. On bricklink.com go to
  **Want > Upload**, upload the file into a new wanted list, then **Buy All** to find
  sellers that cover the whole list. Part numbers that BrickLink writes differently from
  Rebrickable (for example 3040b is 3040 on BrickLink) are translated, and colours are
  mapped to BrickLink's colour numbers.
- **`export_instructions`:** writes two PDFs of building instructions, one step per page,
  bottom to top. Each step shows the model so far with the step's new parts in full colour
  (earlier work faded) and a box of the parts for that step. A level with many parts is
  split round the building into stretches (at most `max_parts` new parts, 40 by default).
  The parts list shows BrickLink's part numbers, so it matches the wanted list.
  - **Phone PDF:** the pages in order: cover, parts list, steps, back cover.
  - **Booklet PDF:** to print and fold. Print it on US letter paper, both sides, with the
    printer's normal "flip on long edge" setting. Keep the sheets in order, staple across
    the middle and fold in half. Each half sheet is one page and the top half of the
    outside sheet is the cover. Open it like a calendar: read the top page, then the bottom
    page, then flip on. The PDF looks scrambled on screen; that is how the pages land in the
    right order once folded.

### Strength check

`check_model` says whether everything is connected. `check_strength` says where it would
break. A model is a network of parts joined by studs and joints, and a weak link is a
single connection that a whole section hangs on. Each weak link gets a risk score:

- **Weight:** the volume of the section that would fall, in 1x1 bricks.
- **Leverage:** how far out that weight sits, in studs.
- **Strength:** 1 per stud, and joints by type (a large ball 3, a hinge 2, a clip 1).

The score is weight x leverage / strength. Weight resting straight on top of studs only
counts its leverage, because it presses the bricks together. Hinges, balls, clips and
turntables are held by friction, so they always count fully.

The scores are rough. They rank weak spots rather than predict exactly when something
snaps. Anything over 20, or a single stud holding more than two bricks, is listed with
how to fix it.

### Finding parts

The LDraw library has about 25,000 part files (including printed variants), but a part
is only useful if you can find it. `find_parts` searches an index of every part's
size, connectors and shape, so you can ask for what you need rather than its name:

- `find_parts(query="curved slope", footprint="2x2")`: words plus a footprint (either way round).
- `find_parts(tags=["widens_upward"], bottom_width="1-2", top_width="2-4")`: parts
  that flare out going up, from about 2 studs wide at the bottom to 2-4 at the top.
- `find_parts(query="snot", height="3")`: bricks with studs on their sides, one brick tall.
- `find_parts(query="eye closed", include_prints=True)`: printed parts (hidden unless asked).
- `find_parts(tags=["half_round"], footprint="1x4", color="tan")`: a 1-stud-wide half-round
  for a column face, in a colour it was really made in.

Shape tags come from each part's real geometry: `round` (round cross-section),
`narrows_upward` / `widens_upward` (width at the top vs the bottom), `smooth_top` (no
top studs), `side_studs`, `down_studs`, `no_underside`, and the shape of the top across
the part's short side: `half_round` (a half cylinder, e.g. 79756, 3563), `quarter_round`
(curved down one edge only, e.g. 37352, which looks like a half-round in a parts list but
isn't) and `ridge` (two straight slopes meeting, e.g. 3043, 3044c). Further tags come from words in
the name: `curved`, `slope`, `inverted`, `dome`, `cone`, `wedge`, `arch`, `tile`,
`quarter`, `corner`, `bracket`, `hinge`, `clip`, `bar`, `ball`, `socket`.

The index is built once, after setup: run `uv run python scripts/build_part_index.py`
(a few minutes, using all CPU cores), or ask Claude to call `build_part_index`. It is
saved as `data/part_index.json`; rebuild it after updating the LDraw library.
`preview_part` then shows any result from four angles.

### Notes

- Any LDraw part can be placed. Upright parts on the grid collide by grid cell
  (bounding box); turned and attached parts collide by real shape. The exported
  file always uses the real part.
- `render_model` draws real part shapes by default; `detail="simple"` is faster
  and shows round parts and arches as boxes.
- Connections modelled: studs in any direction and the joints above (balls, hinges,
  clips on bars, turntables). Technic pins/axles are exported correctly but do not count
  as connections in `check_model` yet.
- Tests: `python tests/test_joints.py` (or `pytest tests`) attaches every joint family
  at several angles and checks there is one connected group and no overlaps.

## Very large builds

![The Hornburg up close](docs/hornburg_closeup.png)

Placing tens of thousands of parts one tool call at a time doesn't scale, so for
Helm's Deep (192 × 160 studs, 41,864 parts) Claude wrote a generator instead.
`scripts/helms_deep/` contains it:

- `gen.py` designs the scene as a colour voxel grid (terrain, walls, stairs, towers) and
  hollows it into a supported shell.
- `slopes.py` adds 45° slopes along the rock ledges.
- `pack.py` packs everything into staggered bricks and plates, then repairs any floating groups.

```bash
uv run python scripts/helms_deep/gen.py
uv run python scripts/helms_deep/slopes.py
uv run python scripts/helms_deep/pack.py
```

Then ask Claude to `open_model helms_deep` and export it.

### Building from a 3D model (STL)

A finished 3D model of a building can drive a generator the same way:

- **Massing:** look down on the model and record the highest point over each stud. That
  height map gives the footprint, wings, bays and roof shape.
- **Facade details:** look at each side straight on and record how deep the surface is.
  Compared with the wall around it, a recessed patch two studs wide is a window and a
  raised horizontal run is a trim band or sill. Rows that are trim along most of the
  front are carried round every wall.
- **Gables:** a wall face that carries on above the eave at the same depth is a gable,
  one stud thick, with the top cell of every step in the trim colour.
- **Roof:** build it as rings of 45 degree slopes, one ring per brick course, each one
  stud in from the last, with 3045 / 3046 corner slopes at the hips and valleys, a hidden
  brick core and a tiled top. Copying the model's roof height column by column gives ugly
  terraces instead. See [docs/roof_techniques.md](docs/roof_techniques.md).
- **Hollow but solid:** keep one-stud walls, a solid roof core and a solid plate layer at
  the eave. Then pack, and wherever a part is loose or `strength.report` finds
  a section hanging on one weak link, fill the solid design back in underneath and
  pack again.
- **Real colours:** run `check_colors` and keep a list of part/colour pairs to skip
  in the packer (for example a 1x3 plate in trans-dark blue was never made).
- **Facade kit:** after packing shape, swap coloured window and trim cells for real parts:
  framed windows with glass, masonry bricks on the stone base, tiled ledges, pilasters
  built sideways, round bays and a porch. See [docs/facade_techniques.md](docs/facade_techniques.md).

## Showcase renders and video

`scripts/showcase/` has a GPU renderer (OpenGL via moderngl) for nicer images than the
built-in previews, plus the scripts that made the pictures on this page:

```bash
uv run --with moderngl python scripts/showcase/glrender.py helms_deep out.png   # one image
uv run --with moderngl python scripts/showcase/compare.py                       # photo vs build
uv run --with moderngl python scripts/showcase/video.py                         # 9:16 build video
```

`compare.py` and `video.py` read reference photos from `scripts/showcase/refs/`. That
folder isn't in the repo, so put your own photos there. `video.py` needs `ffmpeg`.

## Safety

The server runs locally over stdio and makes no network requests (only
`scripts/fetch_ldraw.sh` downloads, from library.ldraw.org). Tool inputs are
treated as untrusted:

- Part ids must be plain LDraw names; library lookups can't leave `data/ldraw`.
- Image tools only open picture files (`.png`, `.jpg`, …) and refuse decompression bombs.
- `export_ldr` only writes `.ldr` / `.mpd` files; models are saved under `models/`
  with sanitised names.
- Render size, grid size and parts per call are capped so one call can't exhaust memory.

It does read picture paths and write `.ldr` files wherever the MCP client asks, with
your user's permissions, so review tool calls as you would any other file access.

## Credits and licence

Code: MIT (see `LICENSE`). Parts geometry comes from the
[LDraw parts library](https://www.ldraw.org), which is downloaded separately and is
licensed CC BY 2.0 by its authors; it is not included in this repository.
Connection (snap) data comes from the
[LDCad shadow library](https://github.com/RolandMelkert/LDCadShadowLibrary) by Roland
Melkert, licensed CC BY-SA 4.0; it is also downloaded separately, not included here.
The real-world catalogue (colours, sets, years) comes from [Rebrickable](https://rebrickable.com)'s
free downloads, fetched at setup and not included here.

The reference stills shown next to the builds are from *The Phoenician Scheme* (2025),
*The Big Lebowski* (1998) and *The Lord of the Rings: The Two Towers* (2002). They are
shown small, for comparison only, and remain the property of their owners.

LEGO® is a trademark of the LEGO Group, which does not sponsor or endorse this project.
