# Organic sculpting: what works

These lessons come from sculpting a cartoon character from a picture with this server.
Every rule below is backed by a build that was rejected or approved. The reusable code is in
[`examples/organic_sculpting/`](../examples/organic_sculpting/).

## The standard to aim for

The reference is the Charmander MOC (rebrickable MOC-283014): smooth curves, shapes that taper in and swell back out, and nothing that reads like a box or a device. It doesn't have to match the picture exactly, but it must look organic.

Approaches that don't work:
- **Same-brick stacks:** a column of identical bricks reads as a pipe.
- **Pancakes:** layers of discs stacked and shifted a little each time look stepped, not curved.
- **A straight tube tilted on one pivot:** it still reads as straight.
- **Square skirts:** a skirt must be at least round, and ideally it undulates.
- **Thin legs:** a 1x1 ankle looks odd, and anything joined by a single stud would break.
- **Faces drawn in bricks:** eyes made from a pattern of small plates look like texture noise. Use one printed piece per feature instead.
- **Anything overlapping:** every model must pass the overlap check before it's shown.

## Techniques that work

### Curves: a chain of short segments, each turned a small angle
Build the shape as short round segments joined by joints, each bent the same small angle, so the angles add up to an even arc. This is the Charmander tail method.

`body_chain.py` builds one ([render](../examples/organic_sculpting/renders/body_curve_3deg.png)):
- **Joints:** segments on hinge bricks (3937 base / 6134 top), each bent a few degrees.
- **Segment shape:**
  - On the inside of the bend: a half-round plate and a narrow 2x6 plate, so the next segment can tip without hitting.
  - Through the middle: a full disc plate.
  - On the top: solid quarter-round bricks (2577) on the outside and hollow quarter rings (48092) on the inside, which hold the next hinge.
- **Hinge pivot:** it sits 1.5 studs from the axis. That clears the ring lip, which would collide at 2.
- **Seams:** solid quarter bricks on the outside of the bend hide the seams.
- **Strength:** a hinge is held only by friction. A light tail can hang on a chain of single hinges, but a big body would sag. `check_strength` flags it. For a heavy curved body:
  - **Rigid base:** build the lower part as a solid stack of quarter-round bricks (each clutches 16 studs), with no hinge at the bottom.
  - **Gentle curve:** curve only the upper part, a few degrees per joint, so its weight sits nearly over the pivots.
  - **Doubled joints:** put two hinges side by side on the same pivot line at every joint (`segment(double=True)`). When mounting, pass the second pair to `mount(..., partners=...)`.

  Done this way, a 330-part character's body dropped off the risk list entirely (worst risk 434 → 66).

### Tapers that are also strong
Taper with parts that share one centre line and clutch 4 studs at every joint. For a leg:
- 2x2 round brick (3941) at the ankle.
- 3x3 cone (6233), which narrows upward, for the calf.
- 2x2 round brick for the knee.
- Another 3x3 cone for the thigh.
- A 4x4 round brick at the hip.

A 3x3 part sitting on a 2x2 part lands half a stud off-centre. That offset gives the leg a natural S-bend for free.

To widen upward, use inverted curved slopes (24201) in a pinwheel around a 2x2 core. This flares an arm into a sleeve with no gap.

### Ball-joint rings for skirts and ruffles
- **Ring:** 12 small ball plates (14417) around a round core, one every 30°.
- **Pleats:** each pleat is a pair of mirrored wedge plates (41769a + 41770a, 2 studs wide at the root and 4 at the hem) on a socket plate (14704).
- **Movement:** alternate the droop (18° / 34°) and the roll (±7°) so the hem rises and falls.
- **Second tier:** a lower ring, 6 plates down and turned 15°, with longer wedges (41767/41768), fills the gaps.
- **Pose search:** `modules.place_best` finds each joint's angles. It scores every pose, then mounts the best one that fits.

### Faces: single printed pieces
- **Eyes:** 2x2 round eye tiles (14769p0d, in the body colour so the lid blends in).
- **Mouth:** a 1x2 smile tile (3069bp69).
- **Mounting:** side-stud bricks (22885, 11211) in a band of the body.

The library also has a 1x1 closed eye with eyelashes (98138p2d), but it's small on a large body.

### Sub-assemblies in any direction
- **Joints:** `modules.mount()` mounts a separately built module on a ball joint or hinge.
- **Studs:** `modules.mount_on_stud()` presses a module onto any stud, sideways or upside down. Use it to build a belly on its back, a face panel or an ear, then stand it up. [Demo render](../examples/organic_sculpting/renders/snot_demo.png).

### Real colours
Check every build with `check_colors`. Many shaping parts were only made in a few colours. For example, the small ball-joint plates 14417 / 14704 only exist in dark bluish gray, so they'll be grey in real bricks: hide them under skirts and inside sleeves. `find_parts(color=...)` only lists parts that exist in that colour.

## Ideas from other builds

[reference_builds_techniques.md](reference_builds_techniques.md) covers the MF DOOM bust, the LEGO 31133 alt build and the white rabbit mech. They use:
- cores with studs on every side;
- clips and bars;
- large ball joints;
- hinge plates;
- turntables.

The server supports all of these now.
