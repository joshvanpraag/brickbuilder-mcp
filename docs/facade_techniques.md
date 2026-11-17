# Facades: finished surfaces, not voxels

Learned from studying a published modular-building MOC's instructions (a three-storey
mansion), after a generated building came out as plain stacked bricks with coloured cells
for windows and trim. Good LEGO buildings use real architectural parts. The generator now
adds these as a "facade kit" after the voxel design and before packing.

## What good modular buildings do

| Feature | How it is built | Parts |
|---|---|---|
| Windows | Real frames with glass, not coloured bricks. A plate or tile sill below, a lintel above. | Window 1x2x2 60592 + glass 60601; 1x2x3 60593 + glass 60602 |
| Doors | A door frame, or a tall window frame with dark glass for a glazed door. | 60596 + door; 60593 + 60602 |
| Stone base | Masonry-profile bricks, with the profile turned to the outside. | 98283 (1x2), 15533 (1x4) |
| String courses | Masonry bricks or plates in a contrasting colour, run round every wall. | 98283, plates |
| Pilasters | Built sideways: a column of studs-on-the-side bricks in the wall, a long plate stood upright on their studs, and half-round curved-top bricks along the plate. | 87087, 1x12 plate 60479, 79756 (or 3563) |
| Porch columns | Round 1x1 bricks stacked, or a 1x1x6 pillar on a square base, capped by a round brick. | 3062b, 43888 |
| Porch canopy / rotunda | Round plates (4x4) and half-round plates, edged with curved tiles and curved bricks. | 60474, 27925, 5152 |
| Round bays | Two quarter-round corner bricks with a straight middle make a half-round bay. Curved corner windows give a glazed floor, and quarter-round plates and tiles cap it. | 5152, 73878, 30357, 27925 |
| Ledges and cornices | Tiles on top, so no studs show. Inverted slopes under an overhang. | 3069b, 2431, 3665 |
| Steps | Plates and tiles with round corners, with slopes for the cheeks. | 27925, 60481 |
| Wall texture | Panels with vertical grooves and 1x2x3 bricks for flat runs. | 59349, 22886 |

## Architecture is a system

A building is not organic: windows, bays and gables follow a grid and mirror each other.
Tracing windows from a scan or picture gives a scattered, uneven look even when every
window is in roughly the right place. Generate them instead:

- **Floors first.** Fix the bottom row of each floor's windows once and use it on every
  wall.
- **Even spacing.** On each straight run of wall: windows 2 studs wide, 1-stud piers,
  at least 1 stud from each end (clear of corners and pilasters). Lay them inward from both
  ends so each run is its own mirror image; an odd stud left over widens the middle pier.
  An odd number of windows needs a true centre stud, otherwise use one fewer.
- **Mirror the whole design.** If the real building is symmetric, mirror the height map
  before anything else (take the larger of each column and its mirror). Scans are never
  exactly symmetric, and small differences break every mirrored pair later.
- **Twins only.** Keep a window only if its mirror twin also fits. The front and back are
  each symmetric left to right, and the two side walls carry the same layout.
- **Generate gables too.** A stepped gable that rises one brick per stud from each side of
  its pavilion stands exactly one brick above a 45-degree roof behind it. Give each step a
  trim-colour top course and a tile, and put a window in the middle. Scanned gables come out
  lumpy and lopsided.

- **Square the outer corners.** Scans often round a building's corners off, leaving a
  one-stud notch up the whole wall. Fill only the corners of the building's bounding box.
  A general "fill any corner" rule cannot tell an outer corner from the inside corner of a
  courtyard, and it will fill the courtyard in.
- **Stay true to the model.** Borrow techniques from other builds, not features: a porch or
  rotunda the real building doesn't have reads as out of place. A framed door with tan
  jambs, an arch and a keystone gives the entrance an accent instead.

- **Lines run unbroken.** A horizontal band carries on round every wall, corners and
  courtyards included, until something real stops it: a window, a pilaster, a bay or a
  doorway. Scanned colours leave random gaps in a band; repaint every band row the full way
  round after tidying the scan, so no line breaks for no reason.
- **Mirror one-sided parts.** A part with a one-sided curve (a curved-top brick, a
  quarter-round) used on both sides of a symmetric building must be turned the opposite way
  on the other side, so the two sides are mirror images.
- **Close the bottom with a fitted floor.** Fill exactly the inside of the walls (not a
  courtyard, not under bays) with two layers of plates at the bottom, the second laid across
  the seams of the first. The bottom layer joins the plate course under the walls, so the
  floor locks to the building and to itself. Check that no plate pokes past a curved wall.
- **No arches over doors in a hollow building.** An arch brick (3659) is open underneath, and
  over a door frame that opening looks straight into the empty inside. Use a solid lintel
  instead: a masonry 1x4 (15533) with a curved keystone (37352) on top.

## Rules of thumb

- **Trim should be deliberate.** Tan or cream only where the building has a band, sill,
  lintel, quoin or cornice. Scattered trim cells from a depth scan read as noise. Keep a
  trim row only if it runs along most of the walls.
- **One stud of depth is enough for a window.** The frame sits in the wall plane; its glass
  is seated in it.
- **Pilasters stand proud of the wall.** A plate plus a curved brick sticks out about one
  and a half studs, which casts a real shadow.
- **Side studs are 24 LDU apart up a column and plate studs are 20.** A long plate on a
  column of side-stud bricks lines up every 5 bricks (120 LDU = 6 plate studs), so use two
  side-stud bricks 5 bricks apart.

## Placing these with brickbuilder

- **Window glass:** place the frame on the grid, then `insert_parts` (or
  `Model.add_insert`) seats the glass at the frame's exact position. The pair counts as
  connected and is not reported as overlapping. The round corner window 73878 takes two
  60601 panes at angles; call `insert_parts` twice on it.
- **Clear glass** (trans-clear 60601) reads best. Dark glass renders as flat grey.
- **Pilaster:** `attach_parts` a 60479 plate onto the side stud of an 87087 brick with
  `rot` 90 so it stands upright. Then attach a half-round curved-top brick onto every fourth
  plate stud with receiver 0 and `rot` 270 so it lies along the plate: 79756 (1x4 x 2/3), or
  its 1x2 version 3563. These are half-round across their one-stud width. 37352 (1x2 curved
  top) looks similar but is a quarter-round, curved on one edge only, and gives a lopsided
  column.
- **Quarter-round parts (5152, 73878, 27925):** at rot 0 the curve bulges to the front-right;
  rot 270 puts it front-left. The 3x3 plate 30357 has its rounded corner back-right at rot 0,
  so use rot 270 for front-right and 180 for front-left.
- **Masonry 98283:** the profile faces front at rot 0, back at 180, right at 90, left at 270.
- **Find the right curve by shape, not name:** `find_parts(tags=["half_round"], ...)` or
  `tags=["quarter_round"]`. Many curved parts have near-identical names; the tags are measured
  from each part's real geometry. Still look at the render: a lopsided or cut-off shape on a
  visible accent means the wrong part.
- **Check colours early.** Many of these parts were made in few colours: the curved corner
  window 73878 only in white or dark blue, glass 60602 only clear, trans-black or gray.
  `find_parts(color=...)` and `check_colors` tell you.
