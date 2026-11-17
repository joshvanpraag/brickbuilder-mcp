# Roofs: rings of slopes, not terraces

Learned from studying a published modular-building MOC's instructions (a mansion with a
dark blue hipped mansard roof), after a generated roof came out as stepped terraces with
studs showing on every step.

## What went wrong first

The first try copied the 3D model's roof height column by column and rounded it to whole
bricks. Every column became its own step, so the roof was a pile of terraces at uneven
heights, with a slope wherever a step happened to be one brick high. Corners had no
corner pieces, and studs showed on every flat bit.

## How a good LEGO roof is built

1. **One ring per brick course.** Each course is a closed ring of 45 degree slopes round
   the roof outline, set one stud in from the course below. A 2x1 slope (3040b) is one
   sloped stud plus one flat stud. The next ring sits on the flat studs, so the sloped
   faces line up into one smooth roof face.
2. **Corner pieces.** Where two edges meet at an outside corner (a hip), use the 2x2
   double convex slope (3045). At an inside corner (a valley, where a wing meets the
   main block), use the 2x2 double concave slope (3046). Without them, corners come out as
   stair steps.
3. **A solid core.** Fill the inside of each course with plain bricks (any colour; hidden),
   so every ring rests on something. The mansion used tan.
4. **A tiled top.** Once the rings stop, cover the flat top with tiles so no studs show.
5. **A cornice ledge.** Start the first ring one stud in from the wall face, so a ledge of
   trim colour runs round the base of the roof.

## Working out the rings from a footprint

- Take the roof outline (the tops of the walls, gables included so the rings run straight
  behind them). Fill in notches up to two studs wide, square off rounded-off corners, then
  set it back one stud for the cornice ledge.
- For every stud, measure how many studs in from the edge it is, counting diagonal steps
  as one (Chebyshev distance). Course k's ring is every stud at distance k. The hips then
  run at exactly 45 degrees.
- Place, in this order: outside corners (a ring stud with open edges on two adjoining
  sides), inside corners (open only diagonally), then straight 2x1 slopes with their high
  end pointing inward. Anything left over in a ring is a plain brick.
- Choose the number of courses from the model's roof height. A wide building ends in a flat
  tiled top (a mansard); a narrow one ends in a ridge.

## Ridges, ridge ends and gables

- **Narrow wings end in a ridge.** Where two ring cells sit side by side, each sloping away
  from the other, cover them two at a time along the ridge with the 2x2 double slope 3043
  (rot 0 runs the ridge along x, rot 90 along z). A 2x2 square left at the end of a ridge
  takes one more 3043. The 2x1 double 3044b would be neater, but it was never made in dark
  blue. Check colours.
- **Roof outline from rectangles.** Build it from clean rectangles (the main range plus one
  per wing), not from the scanned wall tops. A one-stud jog where a wing meets the main
  block makes valley and hip pieces collide.
- **Run the roof into a gable.** In front of a gable, count the roof as carrying on
  (pad the distance field with a virtual strip ahead of the gable), so the rings run straight
  into the back of the gable instead of sloping down toward it. That gives a clean
  cross-gable; sloping toward the gable leaves garbled triangles beside it.
- **Odd-length ridges.** Pairing 3043s two rows at a time leaves one row over on a ridge of
  odd length. Cover it with the one-row double slope 3044c (made in dark blue; rot 90 when
  the slopes face the sides). Run this pass after the ridge-end pass, or it takes cells the
  end pieces need.
- **Where a ridge runs into a slope** (a wing's ridge meeting the side of the main roof)
  there is a T-junction with nothing higher to lean a slope on, so no slope fits. If the cell
  is in the top course it is level with the flat top: tile it and it becomes part of the
  finished top.
- **Gables on the side walls need a cross-gable roof.** Pad the distance field beyond the
  gable across its full width, so a small ridge runs from the gable back into the main roof,
  as high as the gable's middle. Then raise that gable one brick so it stands proud of its
  roof. Padding only the gable's middle gives a ridge too low to see, and the gable looks
  like a loose wall stuck on the roof.
- **Where a cross-gable ridge meets the main slope** two valleys meet, and the last ridge row
  has nothing to lean on. A one-row double slope (3044c) across the pair carries the ridge
  into the valley point.
- **Hidden core colour.** Use the roof colour for the core: round parts on the roof (a round
  plate under a cone) leave their corners open, and the core shows through.

## A trap: separate roofs per wing

Giving each wing and the main block its own hipped roof and taking the highest makes long
gutters wherever two roofs run side by side. 45 degree slopes can't follow a gutter, so
it comes out as a row of jagged teeth. A U- or L-shaped building whose wings are as tall
as the main block has one continuous hip roof, with valleys only at the inside corners.
Use one distance field over the whole outline.

## Part notes

- 3045 at rot 0 slopes toward the right and the front (stud at the back-left). Each 90
  degrees of rot turns that front -> right -> back -> left. 3046 is oriented the same way
  by its open (low) corner.
- Round 2x2 parts (round plates, round bricks) sit flush between 2x2 tiles; the overlap
  check used to flag them because of rounding in their circle outlines (fixed, with a test).
