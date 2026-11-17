# Round shapes: the Lowell sphere and a sausage-shaped car

Notes from two builds by Bruce Lowell, reviewed 2026-11-17:
- **The Lowell sphere:** his well-known way to build a ball from plain plates.
- **The Wienermobile**, at two sizes:
  - a large model (photos only), whose sausage body is studs-out and Lowell-sphere style;
  - a micro model (instructions, 2022), about 60 parts.

## Techniques

### 1. The Lowell sphere: six identical caps around a cube of side studs
- **Core:** 8 bricks 1x1 with studs on four sides (4733), so there are studs facing all six directions.
- **Caps:** six identical caps, each three layers of plates that step in like a low pyramid. Each cap uses:
  - 4 corner plates (2x2 L-shaped);
  - 4 plates 1x2;
  - 2 plates 1x4;
  - 1 plate 2x2.
- **Assembly:** the top and bottom caps stack normally. The four side caps press onto the side studs. The caps' stepped edges interlock at the corners, so the ball is closed and strong.
- **Why it works:** every cap is the same, so it's easy to build. Steps of one plate (a third of a brick) on all six faces read as round from a little distance.

The same idea stretches into other shapes: make the core longer, or make the caps unequal, and you get an egg, a capsule or a sausage.

### 2. Studs left showing as surface texture
The large model's sausage is covered in exposed studs on every side, built the Lowell-sphere way. At that size the studs read as a texture, not as unfinished building. Then one smooth band in another colour (the yellow label, in curved slopes and tiles) contrasts with the studded body around it.

Takeaway: a studded surface can be a deliberate look. Mix it with one smooth feature so the eye has something to rest on.

### 3. A bendy tube of round plates on a flexible rod (the micro model)
- **The beads:** round 2x2 plates and bricks with a hole in the middle (4032, 3941) are threaded onto a flexible rod or hose.
- **The bend:** each plate sits at a small angle to the next, so the stack bends into a smooth curve, like beads on a string.
- **The ends:** a 2x2 dome (553) closes each end.

It's the simplest way to get a smooth, organic bend at a small size: no hinges, just round plates fanned along a curve.

### 4. Tiny details on side studs
- **Wheels:** 1x1 round black tiles on side studs.
- **Body:** a core of bricks with studs on all sides. The car's sides are plates pressed on sideways.
- **Pins as studs:** Technic bricks 1x1 with a hole (6541) hold short pins, and plates press onto the pins sideways.

### 5. Graphics as stickers or printed tiles
The logo, the "yellow band" text and the grille are stickers on tiles. A single printed or stickered piece does the job of a lot of tiny bricks (the same lesson as faces in [organic_sculpting.md](organic_sculpting.md)).

## What the server supports

| Technique | How |
|---|---|
| Lowell sphere (core of 4733 with stepped plate caps) | `lowell_sphere()` in [examples/organic_sculpting/lowell_sphere.py](../examples/organic_sculpting/lowell_sphere.py) builds one in a single call ([render](../examples/organic_sculpting/renders/lowell_sphere.png)) |
| Studs-out surfaces | ordinary stud placement |
| Round plates threaded on a rod | 4032 and 3941 have an axle hole. Each plate can be placed tilted with an exact position (`ldu` and `matrix`). There is no bendable hose: LDraw draws hoses in fixed shapes |
| 1x1 round tiles on side studs | `attach_parts` |
| Stickers | not modelled: use printed tiles, or plain tiles as stand-ins |

**The sphere helper:** `lowell_sphere(model, centre, color, core_color)` builds a ball about 6.5 studs across from 62 parts:
- 6 caps of 9 plates: 4 corner plates, 2 1x4, 2 1x2 and 1 2x2;
- 8 core bricks 4733.

It's a close variant of the original, which uses two more 1x2 plates per cap. Everything is connected, nothing overlaps, and all the parts exist in red and black.

The geometry works out like this:
- **The core:** the 4733's side studs sit 10 LDU below its top. With the top and bottom halves mirrored, their caps sit 40 LDU from the centre.
- **The side caps:** that puts the core's side studs exactly 3 studs apart, matching the corners of a 4 x 4 cap.

Not built yet: a helper that fans round plates along a curve.
