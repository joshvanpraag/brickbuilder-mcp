"""MCP server: build LEGO models brick by brick and export LDraw for Mecabricks."""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
import warnings
from typing import Literal

from PIL import Image as PILImage

from mcp.server.mcpserver import Image, MCPServer
from pydantic import BaseModel, Field

from . import catalog, ldraw, packing, part_index, render
from .model import BuildError, Model, legacy_part_id, safe_name

HOME = Path(os.environ.get("BRICKBUILDER_HOME", ldraw.PROJECT_ROOT))
MODELS_DIR = HOME / "models"
EXPORTS_DIR = HOME / "exports"

INSTRUCTIONS = """\
Build LEGO models on a stud grid, preview them, and export LDraw (.ldr) files that
Mecabricks (mecabricks.com > Workshop > File > Import) and Studio can open.

Coordinates: x = studs to the right, z = studs toward the BACK (z=0 is the front row),
y = height in PLATES (brick = 3 plates, plate/tile = 1; y=0 is the ground).
A part's (x, y, z) is the min corner of its body after rotation. rot 0/90/180/270
(or front/right/back/left) turns parts about the vertical axis; for slopes it is the
direction the sloped face points (0 = toward the front). A 2x4 brick (3001) is 4 long
in x at rot 0 and 4 long in z at rot 90.

Workflow for building from a picture:
1. Look at the picture (Read the image file). Decide the scale (studs wide/tall/deep)
   and the main colours. image_to_grid helps: it downsamples a picture into rows of
   LEGO-colour letters.
2. new_model, then build bottom-up. fill_layers is the fastest path: give top-down
   colour maps per brick layer and it packs them into real bricks with staggered seams.
   Use add_parts for details: slopes for roofs and angled surfaces, tiles for smooth
   tops, plates for fine height steps.
3. render_model (optionally with reference_image) and compare against the picture;
   describe_model shows per-level maps. Iterate with remove_parts / add_parts / undo.
4. check_model to find floating or unconnected parts, then export_ldr.

Sideways building (SNOT - studs not on top), for smooth, rounded sculpted shapes:
- Parts with studs on their sides give studs pointing front/back/left/right, e.g. 87087
  (1x1, stud on 1 side), 4733 (studs on 4 sides), 32952 / 67329 (1.667 bricks with side
  studs), 11211 / 30414 (studs on one side), and brackets 99780 / 99207 / 36840 (up) and
  99781 / 44728 / 36841 (down).
- part_info(part) lists a part's studs and its receivers (underside stud holes, numbered).
- list_studs(id) lists a placed part's studs, which way each points and whether it is free.
- attach_parts presses a new part's receiver onto one of those studs: the new part's top
  then faces the stud's direction (a curved slope on a front-facing stud has its curve
  facing front) and rot spins it about that direction. This is how shells of curved
  slopes (15068, 11477, 93273, 50950, 93606), tiles and wedges cover a core.
- add_parts also takes up ('up','down','front','back','right','left') to place a turned
  part by its grid corner, or ldu=[x, y, z] for an exact LDraw position.
Collisions use each part's real shape and check_model counts real stud contact in every
direction. render_model draws real part shapes by default.

Joints, for posed, organic models (modules at any angle, not just 90 degree steps):
- Ball joints (joint-8): balls 14417 (on a 1x2 plate's side), 22890 (on the end), 3170
  (both ends), 22484 (bar); sockets 14704 (1x2 plate, centre), 14418 (end), 63082, 98263.
- Large balls (only with each other): towballs 3731, 15456, 3614a, 3184 into socket 3730
  (tilt up to 60 degrees); brick 2x2 with two balls 17114 into 2x2 socket bricks 62712,
  92013, 57910, 67696.
- Hinges, any angle (bend): 3937 (hinge base 1x2) + 6134 (hinge top 2x2); hinge plates
  2429 + 2430 (1x4 swivel, turns flat); locking hinges 44301a + 44302a.
- Clips on bars: clips (61252, 63868, 60470, 15712, 11090, 11476 and any part drawn with a
  clip) grip bars (handles 60478, 48336, 2540, 26047 and plain bars such as 87994 Bar 3L).
  bend turns the clip round the bar, slide (LDU) moves it along the bar, flip turns it
  end for end. At bend 0 the clip part stands opposite the bar's part, the same way up.
- Turntables, any angle (bend) about the vertical axis: 3403 + 3404, 3680 + 3679, and the
  flat base 61485 under a round plate with snapstud (60474, 11213, 74611, 89523, 87081).
- Technic and more, from the LDCad snap data (scripts/fetch_ldcad_snaps.sh): pins into pin
  holes (bend turns the pin, flip turns it end for end), axles into axle holes (90 degree
  steps) or round pin holes (any angle), axles slide through holes, bars into bar holes
  (bar_hole: a wheel on a wheel holder's pin, a bar in a hollow stud or tube), axle pins
  (3749) with a pin end and an axle end for wheels, tyres onto rims (tyre into tyre_seat;
  a tyre that doesn't fit is refused), hinge fingers (finger_m into finger_f), and clips,
  bars and balls on parts LDraw draws without a recognisable primitive. part_info lists every connector a part has.
- list_joints(id) lists a placed part's joints and what is connected to each.
- attach_joint connects a new part's joint to a placed part's joint. For a ball joint,
  bend / swing tilt it (up to 45 degrees combined) and twist turns it about its axis;
  for every other joint, bend is the angle about its axis. Parts attached to a tilted part follow its tilt,
  so build a module (arm, tail segment, panel) outward from its joint.
- check_model also lists parts whose real shapes interpenetrate, so tilted modules never
  pass through each other unnoticed.

Finding the right part (the whole LDraw library, about 25,000 parts, is indexed):
- find_parts searches by words AND by shape: footprint ('2x2'), height in plates,
  bottom_width / top_width in studs, and tags such as round, narrows_upward,
  widens_upward, curved, inverted, dome, cone, wedge, smooth_top, side_studs. Example:
  find_parts(tags=['widens_upward'], bottom_width='1-2', top_width='2-4') finds parts
  that flare out going up. Printed variants are hidden unless asked for.
- preview_part renders one part from several angles, so you can see its real shape
  before building with it; part_info gives its connectors and width at four heights.
"""

mcp = MCPServer("brickbuilder", instructions=INSTRUCTIONS)

# Limits that keep a single tool call from exhausting memory or CPU.
MAX_RENDER_SIZE = 1600
MAX_VIEWS = 9
MAX_GRID = 256
MAX_FILL_CELLS = 200_000
MAX_PARTS_PER_CALL = 5_000
# Refuse decompression bombs outright instead of just warning.
PILImage.MAX_IMAGE_PIXELS = 40_000_000
warnings.simplefilter("error", PILImage.DecompressionBombWarning)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}


def _image_path(path: str) -> str:
    """Only picture files may be read by the image tools."""
    p = Path(path).expanduser()
    if p.suffix.lower() not in IMAGE_SUFFIXES:
        raise BuildError(f"Not an image file: {path} (expected one of {', '.join(sorted(IMAGE_SUFFIXES))})")
    if not p.is_file():
        raise BuildError(f"Image not found: {path}")
    return str(p)


def _check_grid(width: int, height: int | None) -> None:
    if not 1 <= width <= MAX_GRID or (height is not None and not 1 <= height <= MAX_GRID):
        raise BuildError(f"width and height must be between 1 and {MAX_GRID}")
_state: dict[str, Model] = {}


def _model() -> Model:
    if "current" not in _state:
        raise BuildError("No model open. Call new_model or open_model first.")
    return _state["current"]


def _save(m: Model) -> None:
    m.save(MODELS_DIR)


def _require_library() -> None:
    if not ldraw.library_available():
        raise BuildError(f"LDraw library not found at {ldraw.LDRAW_DIR}. Run scripts/fetch_ldraw.sh.")


class PartSpec(BaseModel):
    part: str = Field(description="LDraw part id, e.g. '3001' (brick 2x4)")
    color: int | str = Field(description="LDraw colour code or name, e.g. 4 or 'Red'")
    x: int = 0
    y: int = Field(0, description="Bottom level in plates (brick = 3)")
    z: int = 0
    rot: int | str = Field(0, description="0/90/180/270 or front/right/back/left (spin about the part's own top)")
    up: str = Field("up", description="Direction the part's top/studs face: up, down, front, back, right, left")
    ldu: list[float] | None = Field(None, description="Exact LDraw origin [x, y, z] in LDU (overrides x/y/z)")


class AttachSpec(BaseModel):
    part: str = Field(description="LDraw part id of the new part")
    color: int | str
    to_id: int = Field(description="Placed part whose stud the new part presses onto")
    stud: int = Field(description="Stud index on to_id (see list_studs)")
    receiver: int = Field(0, description="Which receiver of the new part goes on that stud (see part_info)")
    rot: int | str = Field(0, description="Spin about the stud direction: 0/90/180/270")
    turn: float = Field(0, description="Extra turn about the stud, any angle in degrees (e.g. 45). "
                        "For a part held by one stud, such as a window on an angled bay face")


class InsertSpec(BaseModel):
    part: str = Field(description="LDraw part id of the insert, e.g. 60601 glass for window 60592")
    color: int | str
    frame_id: int = Field(description="Placed frame the insert goes into")


class JointSpec(BaseModel):
    part: str = Field(description="LDraw part id of the new part (it must have a ball, socket or hinge)")
    color: int | str
    to_id: int = Field(description="Placed part whose joint the new part connects to")
    to_joint: int = Field(0, description="Joint index on to_id (see list_joints)")
    joint: int = Field(0, description="Which joint of the new part (see part_info)")
    bend: float = Field(0, description="Degrees. Ball joint: tilt about the joint's X axis. "
                        "Hinge, clip/bar, turntable: the angle about the joint's axis")
    swing: float = Field(0, description="Degrees, ball joint only: tilt about the joint's Y axis")
    twist: float = Field(0, description="Degrees, ball joint only: turn about the joint's axis")
    slide: float = Field(0, description="Clip on bar only: LDU along the bar from its centre "
                         "(20 LDU = 1 stud; list_joints shows how far each bar allows)")
    flip: bool = Field(False, description="Clip on bar only: turn the new part end for end on the bar")


class Region(BaseModel):
    x0: int
    x1: int
    y0: int
    y1: int
    z0: int
    z1: int


# ---------------------------------------------------------------- models


@mcp.tool()
def new_model(name: str, description: str = "") -> str:
    """Start a new empty model (replaces the open one; models autosave)."""
    _require_library()
    _state["current"] = Model(name, description)
    _save(_state["current"])
    return f"Created model '{name}'. Saved automatically to {MODELS_DIR}/{safe_name(name)}.json"


@mcp.tool()
def open_model(name: str) -> str:
    """Open a previously saved model by name."""
    _require_library()
    path = MODELS_DIR / f"{safe_name(name)}.json"
    if not path.exists():
        raise BuildError(f"No saved model '{name}'. Available: {', '.join(list_models_raw()) or 'none'}")
    _state["current"] = Model.from_json(json.loads(path.read_text()))
    return f"Opened '{name}' with {len(_state['current'].parts)} parts."


def list_models_raw() -> list[str]:
    return sorted(p.stem for p in MODELS_DIR.glob("*.json")) if MODELS_DIR.exists() else []


@mcp.tool()
def list_models() -> str:
    """List saved models."""
    return "\n".join(list_models_raw()) or "No saved models."


# ---------------------------------------------------------------- reference data


@mcp.tool()
def list_parts(category: str | None = None, search: str | None = None) -> str:
    """List the curated parts (brick, plate, tile, slope, round, misc) with their size,
    or search the whole LDraw library by words in the part title (e.g. 'window 1 x 2').
    Size is studs along x x studs along z at rot 0, and height in plates."""
    _require_library()
    lines = []
    if search:
        for pid, title in ldraw.search_library(search):
            try:
                sx, sz, h = catalog.footprint(pid)
                note = "" if pid in catalog.CATALOG else " (box in simple previews)"
                lines.append(f"{pid:10} {sx}x{sz} h{h}  {title}{note}")
            except ldraw.LDrawError:
                continue
        return "\n".join(lines) or "No matches."
    for pid, entry in catalog.CATALOG.items():
        if category and entry.category != category:
            continue
        sx, sz, h = catalog.footprint(pid)
        extra = ""
        if entry.shape.kind in ("slope", "slope_inv"):
            extra = " [slope face points front at rot 0]"
        lines.append(f"{entry.category:6} {pid:8} {sx}x{sz} h{h}  {ldraw.part_title(pid)}{extra}")
    return "\n".join(lines)


@mcp.tool()
def list_colors(search: str | None = None, include_special: bool = False) -> str:
    """List LDraw colours (code, name, hex). Solid colours only unless include_special."""
    _require_library()
    out = []
    for c in ldraw.colours().values():
        if c.code in (16, 24) or (not include_special and c.material != "solid"):
            continue
        if search and search.lower() not in c.name.lower():
            continue
        common = " *" if c.code in packing.STANDARD_PALETTE else ""
        out.append(f"{c.code:5} {c.hex} {c.name}{common}")
    return "\n".join(out) + "\n(* = common, widely available colour)"


# ---------------------------------------------------------------- building


@mcp.tool()
def add_parts(parts: list[PartSpec]) -> str:
    """Place one or more parts. Parts that collide or are invalid are skipped and reported;
    the rest are placed. Returns the new part ids."""
    m = _model()
    if len(parts) > MAX_PARTS_PER_CALL:
        raise BuildError(f"add_parts is limited to {MAX_PARTS_PER_CALL} parts per call")
    m.checkpoint()
    ok, errors = [], []
    for spec in parts:
        try:
            p = m.add(spec.part, spec.color, spec.x, spec.y, spec.z, spec.rot, spec.up, spec.ldu)
            ok.append(p.id)
        except (BuildError, ldraw.LDrawError) as e:
            errors.append(str(e))
    _save(m)
    msg = f"Placed {len(ok)} part(s): ids {_ranges(ok)}." if ok else "Placed nothing."
    if errors:
        msg += "\nErrors:\n- " + "\n- ".join(errors)
    return msg


@mcp.tool()
def insert_parts(parts: list[InsertSpec]) -> str:
    """Seat inserts in placed frames: window glass (60601 in 60592, two 60601 in the round
    corner window 73878, 60602 in 60593, 60603 in
    60594, 57895 in 57894). The insert takes its frame's exact position and rotation and
    counts as connected to it, so check_model does not report the glass as floating."""
    m = _model()
    if len(parts) > MAX_PARTS_PER_CALL:
        raise BuildError(f"insert_parts is limited to {MAX_PARTS_PER_CALL} parts per call")
    m.checkpoint()
    ok, errors = [], []
    for spec in parts:
        try:
            ok.append(m.add_insert(spec.part, spec.color, spec.frame_id).id)
        except (BuildError, ldraw.LDrawError) as e:
            errors.append(f"{spec.part} in #{spec.frame_id}: {e}")
    _save(m)
    msg = f"Seated {len(ok)} insert(s): ids {_ranges(ok)}." if ok else "Seated nothing."
    if errors:
        msg += "\nErrors:\n- " + "\n- ".join(errors)
    return msg


@mcp.tool()
def attach_parts(parts: list[AttachSpec]) -> str:
    """Attach parts onto studs of placed parts, in any direction (SNOT). Each new part's
    receiver (underside stud hole) `receiver` is pressed onto stud `stud` of part `to_id`;
    the new part's top then faces the way that stud points, spun by `rot`; `turn` adds
    any angle (a part held by a single stud can turn freely, e.g. 45 degrees). Parts are
    attached in order, so later ones can attach to earlier ones (use the ids returned by
    earlier calls). Collisions are checked against real part shapes."""
    m = _model()
    if len(parts) > MAX_PARTS_PER_CALL:
        raise BuildError(f"attach_parts is limited to {MAX_PARTS_PER_CALL} parts per call")
    m.checkpoint()
    ok, errors = [], []
    for spec in parts:
        try:
            p = m.attach(spec.part, spec.color, spec.to_id, spec.stud, spec.receiver, spec.rot, spec.turn)
            ok.append(f"#{p.id} {p.part} " + ("tilted (follows its base)" if p.matrix is not None else f"facing {p.up}"))
        except (BuildError, ldraw.LDrawError) as e:
            errors.append(f"{spec.part} on #{spec.to_id} stud {spec.stud}: {e}")
    _save(m)
    msg = ("Attached:\n- " + "\n- ".join(ok)) if ok else "Attached nothing."
    if errors:
        msg += "\nErrors:\n- " + "\n- ".join(errors)
    return msg


@mcp.tool()
def list_studs(id: int, free_only: bool = False) -> str:
    """List a placed part's studs: index (for attach_parts), the way it points, its position
    (x, z in studs, y in plates, as on the grid) and what is plugged onto it, if anything."""
    from .model import direction_name
    m = _model()
    if id not in m.parts:
        raise BuildError(f"No part #{id}")
    g = m.geometry(id)
    used = m.stud_usage(id)
    lines = [f"#{id} {m.parts[id].part} ({ldraw.part_title(m.parts[id].part)}) facing {m.parts[id].up}:"]
    for i, ((pos, d), who) in enumerate(zip(g.studs(), used)):
        if free_only and who is not None:
            continue
        where = f"x={pos[0] / 20 + 0:g} y={-pos[1] / 8 + 0:g} z={pos[2] / 20 + 0:g}"
        lines.append(f"  stud {i:2}: points {direction_name(d, strict=False):5}  at {where}" +
                     (f"  <- #{who} {m.parts[who].part}" if who is not None else "  free"))
    return "\n".join(lines) if len(lines) > 1 else lines[0] + " no studs"


@mcp.tool()
def attach_joint(parts: list[JointSpec]) -> str:
    """Connect parts by joints at any angle. Each new part's joint `joint` goes onto joint
    `to_joint` of placed part `to_id`: ball into socket (joint-8, towball, large 2x2 ball),
    clip onto bar, pin or axle into a hole, hinge fingers into each other, or one half of a
    hinge, hinge plate or turntable onto the other. Ball
    joints: bend and swing tilt the new part (45 degrees combined, 60 for towballs), twist
    turns it about the joint axis. Hinges, clips and turntables: bend is the angle about the
    axis; a clip also takes slide (LDU along the bar) and flip. Pins and axles: bend turns
    them in the hole (axles in cross holes: 90 degree steps), flip turns them end for end,
    slide moves an axle along a hole.
    Then attach_parts onto the tilted part to build the module outward; everything on it
    follows the tilt. Collisions are checked against real part shapes."""
    m = _model()
    if len(parts) > MAX_PARTS_PER_CALL:
        raise BuildError(f"attach_joint is limited to {MAX_PARTS_PER_CALL} parts per call")
    m.checkpoint()
    ok, errors = [], []
    for spec in parts:
        try:
            p = m.attach_joint(spec.part, spec.color, spec.to_id, spec.to_joint, spec.joint,
                               spec.bend, spec.swing, spec.twist, spec.slide, spec.flip)
            ok.append(f"#{p.id} {p.part}")
        except (BuildError, ldraw.LDrawError) as e:
            errors.append(f"{spec.part} on #{spec.to_id} joint {spec.to_joint}: {e}")
    _save(m)
    msg = ("Connected:\n- " + "\n- ".join(ok)) if ok else "Connected nothing."
    if errors:
        msg += "\nErrors:\n- " + "\n- ".join(errors)
    return msg


@mcp.tool()
def list_joints(id: int) -> str:
    """List a placed part's joints (balls, sockets, hinges, clips, bars, turntables): index
    (for attach_joint), kind, position (x, z in studs, y in plates), the direction its axis
    points, how far a clip can slide on a bar, and what is connected to it."""
    from . import geometry
    from .model import direction_name
    m = _model()
    if id not in m.parts:
        raise BuildError(f"No part #{id}")
    js = m.geometry(id).joints_full()
    if not js:
        return f"#{id} {m.parts[id].part} has no joints"
    used = m.joint_usage(id)
    lines = [f"#{id} {m.parts[id].part} ({ldraw.part_title(m.parts[id].part)}):"]
    for i, ((kind, c, f, s), who) in enumerate(zip(js, used)):
        axis = f[:, 2] if kind in geometry.BALL_KINDS else f[:, 0]
        where = f"x={c[0] / 20 + 0:.2f} y={-c[1] / 8 + 0:.2f} z={c[2] / 20 + 0:.2f}"
        room = f"  slide +-{s:g} LDU" if kind == "bar" else ""
        lines.append(f"  joint {i}: {kind:10} at {where}  axis {direction_name(axis, strict=False)}{room}" +
                     (f"  <- #{who} {m.parts[who].part}" if who is not None else "  free"))
    return "\n".join(lines)


@mcp.tool()
def part_info(part: str) -> str:
    """Describe a part's connectors: its studs (which way they point at up='up', rot=0) and
    its receivers (underside stud holes, numbered for attach_parts), with positions in studs
    relative to the part origin (x right, z back; y in plates, down is negative)."""
    from . import geometry
    from .model import direction_name
    _require_library()
    pid, shape, cat = catalog.lookup(part)
    sx, sz, h = catalog.footprint(pid)
    lines = [f"{pid}: {ldraw.part_title(pid)}  ({sx}x{sz} studs, {h} plates tall)"]
    st = geometry.studs(pid)
    counts = Counter(direction_name(d) for _, d in st)
    lines.append("studs: " + (", ".join(f"{n} pointing {k}" for k, n in counts.items()) if st else "none"))
    rc = geometry.receivers(pid)
    if rc:
        lines.append("receivers (index: x, z in studs, height in plates):")
        for i, (pos, _) in enumerate(rc):
            lines.append(f"  {i:2}: x={pos[0] / 20 + 0:g} z={pos[2] / 20 + 0:g} y={-pos[1] / 8 + 0:g}")
    else:
        lines.append("receivers: none (cannot be pressed onto a stud)")
    js = geometry.joints(pid)
    if js:
        lines.append("joints (index: kind, x, z in studs, height in plates):")
        for i, (kind, o, f) in enumerate(js):
            lines.append(f"  {i:2}: {kind} at x={o[0] / 20 + 0:g} z={o[2] / 20 + 0:g} y={-o[1] / 8 + 0:g}")
    rec = part_index.record(pid) or {}
    shape = rec if "widths" in rec else _shape_or_none(pid)
    if shape and shape.get("widths"):
        w = shape["widths"]
        lines.append("shape: width in studs at 4 heights, bottom to top: " + " -> ".join(f"{v:g}" for v in w))
    if shape and shape.get("tags"):
        lines.append("tags: " + ", ".join(shape["tags"]))
    from . import snaps
    if snaps.available():
        conn = snaps.summary(pid)
        if conn:
            lines.append("connectors (LDCad snap data): " + ", ".join(f"{n} {k}" for k, n in sorted(conn.items())))
    from . import rebrickable
    if rebrickable.available():
        lines.append(rebrickable.summary(pid))
    return "\n".join(lines)


def _shape_or_none(pid: str) -> dict | None:
    try:
        return part_index._shape(pid)
    except Exception:
        return None


@mcp.tool()
def find_parts(query: str = "", footprint: str | None = None, height: str | None = None,
               tags: list[str] | None = None, joints: list[str] | None = None,
               bottom_width: str | None = None, top_width: str | None = None,
               include_prints: bool = False, color: int | str | None = None, limit: int = 25) -> str:
    """Search the whole LDraw library (about 25,000 parts) by words and by shape.
    query: words from the part name, category or keywords ('curved slope', 'bracket',
      'dome'); builder words work too: 'snot'/'sideways' (side studs), 'smooth' (no top
      studs), 'tapered' (narrows upward), 'flared' (widens upward), 'printed'.
    footprint: 'AxB' in studs, either orientation. height: plates, '3' or a range '2-6'.
    tags: all must match, from: round, narrows_upward, widens_upward, curved, slope,
      inverted, dome, cone, wedge, arch, tile, quarter, corner, half, half_round,
      quarter_round, ridge, smooth_top,
      side_studs, down_studs, no_underside, bracket, hinge, clip, bar, ball, socket,
      technic, offset, printed, pin, pin_hole, axle, axle_hole, hinge_fingers.
    joints: joint kinds the part must have, any of: ball, socket, towball, towball_socket,
      large_ball, large_socket, hinge_base, hinge_top, clip, bar, swivel_base, swivel_top,
      click_hinge_1, click_hinge_2, turntable_base, turntable_top, flat_turntable, snapstud,
      pin, pin_hole, axle, axle_hole, bar_hole, tyre, tyre_seat, finger_m, finger_f.
    bottom_width / top_width: the part's width in studs at its bottom / top quarter, a
      number or range ('1-2'), to find parts that taper or flare between two sizes.
    color: only parts LEGO really produced in this colour (name or code), from the
      Rebrickable catalogue (scripts/fetch_rebrickable.sh).
    Each result: id, footprint and height, width bottom->top, tags, connectors, name."""
    _require_library()
    if not part_index.available():
        return ("The part index has not been built yet. Call build_part_index (takes a few "
                "minutes, once), or run: uv run python scripts/build_part_index.py")
    try:
        want = None
        if color is not None and color != "":
            from . import rebrickable
            if not rebrickable.available():
                return "The colour filter needs the Rebrickable catalogue: run scripts/fetch_rebrickable.sh."
            want = ldraw.resolve_colour(color).code
        hits = part_index.search(query, footprint, height, tags, joints, bottom_width, top_width,
                                 include_prints, 200 if want is not None else limit)
        if want is not None:
            hits = [h for h in hits if want in rebrickable.colours_of(h["id"])][:max(1, int(limit))]
    except ValueError as e:
        raise BuildError(str(e)) from None
    if not hits:
        return "No matches. Try fewer words, a wider range, or fewer tags."
    return "\n".join(part_index.describe(r) for r in hits)


@mcp.tool()
def build_part_index() -> str:
    """Build (or rebuild) the search index that find_parts uses: analyses every part's
    size, connectors and shape. Takes a few minutes, using all CPU cores. Needed once
    after setup, and again after updating the LDraw library."""
    import subprocess
    import sys
    _require_library()
    # a separate process, so the worker pool never re-launches this server
    run = subprocess.run([sys.executable, "-c", "from brickbuilder import part_index; part_index.build()"],
                         capture_output=True, text=True, timeout=3600, env=os.environ.copy())
    if run.returncode != 0:
        raise BuildError("Index build failed: " + (run.stderr or run.stdout)[-800:])
    part_index._load.cache_clear()
    return (run.stdout.strip().splitlines() or ["Index built."])[-1]


@mcp.tool()
def preview_part(part: str, color: int | str = "light bluish gray", views: list[str] | None = None,
                 size: int = 300) -> Image:
    """Render a single part on its own so you can see its real shape before using it.
    views: as in render_model; default front, right, top and iso_front_left."""
    _require_library()
    pid = ldraw.resolve_moved(ldraw.normalize_part_id(part))
    if ldraw.part_title(pid) is None:
        raise BuildError(f"Part '{part}' not found in the LDraw library")
    m = Model("preview")
    for lift in range(0, 2000, 8):                       # lift it until no part of it is below the ground
        try:
            m.add(pid, color, 0, 0, 0, 0, "up", [0.0, -float(lift), 0.0])
            break
        except BuildError as e:
            if "below the ground" not in str(e):
                raise
    views = (views or ["front", "right", "top", "iso_front_left"])[:MAX_VIEWS]
    size = max(64, min(int(size), MAX_RENDER_SIZE))
    return Image(data=render.render(m, views, size), format="png")


@mcp.tool()
def remove_parts(ids: list[int] | None = None, region: Region | None = None) -> str:
    """Remove parts by id and/or every part touching an inclusive grid region."""
    m = _model()
    m.checkpoint()
    targets = set(ids or [])
    if region:
        targets |= set(m.parts_in_region(region.x0, region.x1, region.y0, region.y1, region.z0, region.z1))
    removed = m.remove(sorted(targets))
    _save(m)
    return f"Removed {len(removed)} part(s)."


@mcp.tool()
def fill_layers(layers: list[list[str]], legend: dict[str, int | str], x: int = 0, y: int = 0, z: int = 0,
                kind: Literal["brick", "plate", "tile"] = "brick", upright: bool = False) -> str:
    """Build volume from colour maps, automatically packed into bricks/plates/tiles.

    layers: bottom-to-top list of layers; each layer is a list of equal-length rows seen
    from ABOVE, first row = back, last row = front. Each character is a cell of 1 stud;
    '.' = empty. legend maps characters to colours, e.g. {"R": "Red", "W": 15}.
    Each layer is one brick (3 plates) or one plate tall depending on kind; layer i sits
    at y + i*height. (x, z) is the front-left corner of the map.

    upright=True: each layer is instead a front-facing wall picture (first row = top,
    last row = bottom), one course per row, at depth z + layer index. Handy for mosaics
    and facades.

    Cells already occupied are skipped. Seams are staggered between courses."""
    m = _model()
    cells = sum(len(row) for layer in layers for row in layer)
    if cells > MAX_FILL_CELLS:
        raise BuildError(f"fill_layers is limited to {MAX_FILL_CELLS} cells per call (got {cells}); split it up")
    m.checkpoint()
    try:
        res = packing.fill_layers(m, layers, legend, x, y, z, kind, upright)
    except (BuildError, ldraw.LDrawError):
        m.undo()
        raise
    _save(m)
    msg = f"Placed {len(res['placed'])} part(s): ids {_ranges(res['placed'])}."
    if res["skipped_occupied_cells"]:
        msg += f" Skipped {len(res['skipped_occupied_cells'])} already-occupied cells."
    return msg


@mcp.tool()
def image_to_grid(image_path: str, width: int, height: int | None = None, max_colors: int = 10,
                  palette: list[int | str] | None = None, crop: list[float] | None = None,
                  cell: Literal["stud", "brick", "plate"] = "stud") -> str:
    """Downsample a picture into rows of colour letters using LEGO colours, ready for
    fill_layers. crop = [left, top, right, bottom] fractions (0-1) to focus on the subject.
    cell sets the cell's aspect ratio when height is omitted: 'stud' for top-down maps,
    'brick' or 'plate' for upright walls. Transparent pixels become '.'."""
    _require_library()
    _check_grid(width, height)
    aspect = {"stud": 1.0, "brick": 1.2, "plate": 0.4}[cell]
    res = packing.image_to_grid(_image_path(image_path), width, height, max_colors, palette, crop, aspect)
    table = ldraw.colours()
    legend = "\n".join(f"  {ch} = {code} {table[code].name}" for ch, code in res["legend"].items())
    return (f"{res['width']}x{res['height']} grid (first row = top of image)\n" + "\n".join(res["rows"]) +
            f"\nlegend:\n{legend}\nlegend json: {json.dumps(res['legend'])}")


@mcp.tool()
def build_mosaic(image_path: str, width: int, orientation: Literal["upright", "flat"] = "upright",
                 height: int | None = None, max_colors: int = 10, crop: list[float] | None = None,
                 kind: Literal["brick", "plate"] = "plate", x: int = 0, y: int = 0, z: int = 0) -> str:
    """Build a picture directly as a mosaic in the current model.
    upright: a wall facing the front, 1 stud deep (kind=plate gives fine vertical detail,
    kind=brick is sturdier). flat: lying on the ground, one plate thick, image top = back."""
    m = _model()
    if orientation == "flat":
        kind = "plate"
    _check_grid(width, height)
    aspect = 1.0 if orientation == "flat" else (1.2 if kind == "brick" else 0.4)
    res = packing.image_to_grid(_image_path(image_path), width, height, max_colors, None, crop, aspect)
    m.checkpoint()
    try:
        out = packing.fill_layers(m, [res["rows"]], res["legend"], x, y, z, kind,
                                  upright=orientation == "upright")
    except (BuildError, ldraw.LDrawError):
        m.undo()
        raise
    _save(m)
    return f"Mosaic {res['width']}x{res['height']} built from {len(out['placed'])} parts, {len(res['legend'])} colours."


@mcp.tool()
def undo() -> str:
    """Undo the last building action."""
    m = _model()
    ok = m.undo()
    _save(m)
    return "Undone." if ok else "Nothing to undo."


# ---------------------------------------------------------------- inspection


@mcp.tool()
def describe_model(levels: list[int] | None = None, all_levels: bool = False, list_all_parts: bool = False) -> str:
    """Summarise the model: bounds, part counts, and top-down colour maps of plate levels
    (first row = back, last = front; uppercase letters = colours in the legend).
    Maps are shown for `levels`, or every level when all_levels is set."""
    m = _model()
    table = ldraw.colours()
    b = m.bounds()
    if b is None:
        return f"Model '{m.name}' is empty."
    x0, x1, y0, y1, z0, z1 = b
    out = [f"Model '{m.name}': {len(m.parts)} parts, bounds x {x0}..{x1}, y {y0}..{y1} (plates), z {z0}..{z1}",
           f"size: {x1 - x0 + 1} x {z1 - z0 + 1} studs, {(y1 - y0 + 1) / 3:.1f} bricks tall"]
    counts = Counter((p.part, p.color) for p in m.parts.values())
    out.append("parts:")
    for (pid, col), n in counts.most_common():
        out.append(f"  {n:4} x {pid:8} {table[col].name:24} {ldraw.part_title(pid)}")
    show = list(range(y0, y1 + 1)) if all_levels else (levels or [])
    legend: dict[int, str] = {}
    for yy in show:
        out.append(f"level y={yy} (map origin x={x0}, z={z0} at bottom-left):")
        out += ["  " + row for row in m.layer_map(yy, legend)]
    if legend:
        out.append("legend: " + ", ".join(f"{ch}={table[c].name}" for c, ch in legend.items()))
    if list_all_parts:
        out.append("placements (id part color x y z rot [up] [ldu]):")
        out += [f"  {p.id} {p.part} {p.color} {p.x} {p.y} {p.z} {p.rot}" +
                (f" up={p.up}" if p.up != "up" else "") + (f" ldu={p.ldu}" if p.ldu is not None else "") +
                (" tilted" if p.matrix is not None else "")
                for p in m.parts.values()]
    return "\n".join(out)


@mcp.tool()
def check_model() -> str:
    """Check structure: floating groups (not connected to anything touching the ground),
    loose groups (standing on the ground but not attached to the main body), and parts whose
    real shapes pass into each other. Connections count studs in any direction and every
    joint (balls, hinges, clips on bars, turntables)."""
    m = _model()
    r = m.check()
    lines = [f"{r['parts']} parts in {r['connected_groups']} stud-connected group(s); largest: {r['group_sizes']}"]
    for g in r["floating_groups"]:
        lines.append(f"FLOATING group of {len(g)} part(s): ids {_ranges(g)}")
    for g in r["loose_grounded_groups"]:
        lines.append(f"loose group on the ground ({len(g)} part(s)): ids {_ranges(g)}")
    if not r["floating_groups"] and not r["loose_grounded_groups"]:
        lines.append("OK: everything is connected.")
    clashes = m.overlaps()
    for i, j, n in clashes:
        lines.append(f"OVERLAP: #{i} {m.parts[i].part} and #{j} {m.parts[j].part} pass into each other ({n} sample points)")
    if not clashes:
        lines.append("OK: no parts pass into each other.")
    lines.append("(check_strength shows where the model would break: sections hanging on one weak link.)")
    return "\n".join(lines)


@mcp.tool()
def check_colors() -> str:
    """Are the model's colours real? Lists every part used in a colour LEGO never produced
    for that part (from Rebrickable's set inventories), with the closest real colours.
    Needs scripts/fetch_rebrickable.sh."""
    from . import rebrickable
    if not rebrickable.available():
        return "Needs the Rebrickable catalogue: run scripts/fetch_rebrickable.sh (about 17 MB)."
    m = _model()
    probs = rebrickable.colour_problems(m)
    if not probs:
        return f"OK: all {len(m.parts)} parts come in real colours."
    return f"{len(probs)} part/colour combination(s) LEGO never made:\n- " + "\n- ".join(probs)


@mcp.tool()
def export_parts_list(path: str | None = None) -> str:
    """Write the model's parts list: a CSV in Rebrickable's import format (Part, Color,
    Quantity) and a readable .txt next to it. To buy the parts: on rebrickable.com, import
    the CSV as a part list, then export it as a BrickLink wanted list (or see which of your
    own sets already have the parts)."""
    from . import rebrickable
    m = _model()
    out = Path(path).expanduser() if path else EXPORTS_DIR / f"{safe_name(m.name)}_parts.csv"
    if out.suffix.lower() != ".csv":
        raise BuildError("path must end in .csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    csv_text, readable = rebrickable.parts_list(m)
    out.write_text(csv_text)
    out.with_suffix(".txt").write_text(readable + "\n")
    kinds = len(csv_text.strip().splitlines()) - 1
    note = "" if rebrickable.available() else " (run scripts/fetch_rebrickable.sh for part names and Rebrickable numbers)"
    return (f"Wrote {out} and {out.with_suffix('.txt').name}: {len(m.parts)} parts in {kinds} part/colour "
            f"lines{note}.\nTo buy them: import the CSV as a part list on rebrickable.com, then export a "
            "BrickLink wanted list.")


@mcp.tool()
def export_bricklink(path: str | None = None) -> str:
    """Write a BrickLink wanted list (XML) for the model's parts. To buy them: on
    bricklink.com go to Want > Upload, paste or upload this file into a new wanted list,
    then use "Buy All" to find sellers that cover the whole list."""
    from . import bricklink
    m = _model()
    out = Path(path).expanduser() if path else EXPORTS_DIR / f"{safe_name(m.name)}_bricklink.xml"
    if out.suffix.lower() != ".xml":
        raise BuildError("path must end in .xml")
    out.parent.mkdir(parents=True, exist_ok=True)
    xml, problems = bricklink.wanted_list(m)
    out.write_text(xml)
    lines = xml.count("<ITEM>")
    msg = f"Wrote {out}: {len(m.parts)} parts in {lines} lines. Upload it on bricklink.com: Want > Upload."
    if problems:
        msg += "\nLeft out (no BrickLink colour id known):\n- " + "\n- ".join(problems)
    return msg


@mcp.tool()
def export_build_pack(out_dir: str, title: str | None = None, max_parts: int = 40, story: str = "",
                      theme: str = "Modular Buildings") -> str:
    """Everything to buy and build the model, in one folder: the model (.ldr), a BrickLink
    wanted list (XML), a Rebrickable parts list (CSV, plus a readable .txt), the
    instructions as a phone PDF and a print-and-fold booklet PDF, and HOW_TO_BUY.md with the
    steps for BrickLink and Rebrickable, plus a Rebrickable MOC kit: publishing-quality
    pictures (rebrickable_moc/) and REBRICKABLE_MOC.md with every field of Rebrickable's
    "Submit a MOC" form filled in. story: the opening of the MOC description (what the
    model is, its highlights); the facts (parts, size in inches, colours) are added."""
    from . import buildpack
    m = _model()
    info = buildpack.export(m, Path(out_dir).expanduser(), title, max_parts=max_parts, story=story,
                            theme=theme)
    msg = (f"Build pack in {out_dir}: {len(m.parts)} parts, {info['steps']} steps, booklet "
           f"{info['sheets']} sheets.\n- " + "\n- ".join(Path(f).name for f in info["files"].values()))
    if info["problems"]:
        msg += "\nLeft out of the BrickLink list:\n- " + "\n- ".join(info["problems"])
    return msg


@mcp.tool()
def export_instructions(out_dir: str | None = None, title: str | None = None, max_parts: int = 40) -> str:
    """Write building instructions as two PDFs: one page per step for reading on a phone,
    and a booklet to print on US letter paper both sides (flip on long edge), staple across
    the middle and fold in half (each half sheet is one page; the top half of the outside
    sheet is the cover). Steps go bottom to top; a step has at most max_parts new parts."""
    from . import instructions
    m = _model()
    out = Path(out_dir).expanduser() if out_dir else EXPORTS_DIR / f"{safe_name(m.name)}_instructions"
    info = instructions.export(m, out, title or m.name.replace("_", " ").title(),
                               f"{len(m.parts)} parts", max_parts=max_parts)
    return (f"{info['steps']} steps, {info['pages']} pages.\nPhone: {info['phone']}\n"
            f"Booklet: {info['booklet']} ({info['sheets']} sheets of letter paper: print both sides, "
            "flip on long edge; stack in order, staple across the middle, fold in half)")


@mcp.tool()
def check_strength(limit: int = 15) -> str:
    """Where would the built model break? Finds every single connection that, if it broke,
    would let a section fall off, and ranks them by risk: the weight of that section
    (in 1x1-brick units), how far it sticks out (studs), and how strong the link is (1 per
    stud; joints by type). Weight resting straight on stud connections only counts its
    leverage; hinges, balls, clips and turntables are held by friction and count fully.
    Use it after building anything tall, sideways or posed; reinforce what it flags."""
    from . import strength
    m = _model()
    if not m.parts:
        return "The model is empty."
    return strength.describe(m, strength.report(m, max(1, min(int(limit), 100))))


@mcp.tool()
def render_model(views: list[str] | None = None, size: int = 480, reference_image: str | None = None,
                 detail: Literal["real", "simple"] = "real") -> Image:
    """Render a preview sheet. views: any of front, back, left, right, top, iso_front_left,
    iso_front_right, iso_back_left, iso_back_right, or 'azimuth,elevation' in degrees.
    Default: iso_front_left, iso_back_right, front, top. reference_image adds the source
    picture as the first panel for side-by-side comparison. detail='real' draws every
    part's true LDraw shape (curves, side studs, sideways parts); 'simple' draws quick
    boxes and slope prisms."""
    m = _model()
    views = (views or None) and views[:MAX_VIEWS]
    size = max(64, min(int(size), MAX_RENDER_SIZE))
    return Image(data=render.render(m, views, size, _image_path(reference_image) if reference_image else None,
                                    detail), format="png")


@mcp.tool()
def export_ldr(path: str | None = None, legacy_ids: bool = False) -> str:
    """Write the model as an LDraw .ldr file (one build step per level).
    Import it in Mecabricks via Workshop > File > Import. If some parts come in missing,
    re-export with legacy_ids=True (uses e.g. 3023 instead of 3023b)."""
    m = _model()
    out = Path(path).expanduser() if path else EXPORTS_DIR / f"{safe_name(m.name)}.ldr"
    if out.suffix.lower() not in (".ldr", ".mpd"):
        raise BuildError("export path must end in .ldr (or .mpd)")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(m.to_ldr(legacy_ids))
    ids = sorted({legacy_part_id(p.part) if legacy_ids else p.part for p in m.parts.values()})
    return (f"Wrote {out} ({len(m.parts)} parts, {len(ids)} distinct part types: {', '.join(ids)}).\n"
            "Mecabricks: open the Workshop, File > Import, choose LDraw, pick this file.")


def _ranges(ids: list[int]) -> str:
    ids = sorted(ids)
    if not ids:
        return "none"
    out, start, prev = [], ids[0], ids[0]
    for i in ids[1:] + [None]:
        if i is not None and i == prev + 1:
            prev = i
            continue
        out.append(f"{start}" if start == prev else f"{start}-{prev}")
        if i is not None:
            start = prev = i
    return ", ".join(out)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
