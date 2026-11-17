# Techniques from three reference builds

Reviewed 2026-11-16:
- **MF DOOM bust:** BardicBricks, MOC-276763. A bust built on the LEGO Doctor Doom set.
- **31133 alt build:** buildinst / Tomáš Vít. A Moomin-like character made from Creator 31133 parts.
- **White Rabbit Mech:** eric_nunya, MOC-151501.

This file lists the techniques they use for organic, character-style builds, then which of them the brickbuilder server can model.

## Techniques

### 1. Build a section sideways or on its back, then stand it up
- **31133:** the round belly is built lying on its back. A 6x6 round plate (11213) is the base, with quarter domes and 2x2 curved slopes around a white brick core, plus a second half built on top. The finished egg is then tipped upright, so the rounded face points forward.
- **Rabbit mech:** the chest is done the same way. A 4x4 round plate on a 2x4 plate carries 1x2 oval tiles (66857).
- **Why it matters:** shaping parts only curve in their own up direction. Turning a whole sub-assembly lets a dome or curve face any way, which is how these builds get round fronts instead of stepped ones.
- **Built:** `modules.mount_on_stud()`; demo in `snot_demo.py` / `snot_demo.png`.

### 2. A core with studs on every side, clad with shaped panels
- **MF DOOM head:** the core is 1x1 bricks with studs on 4 sides (4733), 2 sides (47905), or 1 side (87087 / 4070), plus 1x2 bricks with studs on the side (11211). Every face then gets a separately built panel. Those panels are plates on door-rail plates (32028), with metallic slopes, wedge tiles, a 3x3 radar dish for the ear, and 1x4 double curved slopes on top.
- **31133 and rabbit mech heads:** the same idea at small scale. 1x2-2x2 brackets (44728) and 1x2-1x2 brackets (99781) are stacked into a cube with studs facing out on all sides. The eyes, muzzle and wedge cheeks clip onto that cube.
- **Use it for:** face bands, bow knots, shoes. It's cleaner than packing bricks around side-stud bricks.

### 3. Small posable joints everywhere
- **MF DOOM:**
  - Shoulder armour (pauldrons) hangs off 1x2 clip hinges and plates with horizontal clips on the sides.
  - The mask is held by a 4L bar through two 1x1 round plates with clips (bar and clip), so the angle can be adjusted.
  - The chin's angle is set by a 1x2 locking hinge (44301/44302).
- **31133:**
  - The ears are angled plates on 1x1 clip plates (61252) gripping 1x2 plates with bars (60478).
  - The arms are 1x2 plates with a clip on the end (63868), gripping a bar.
  - The flower stem is a bar held in a 1x1 clip.
- **Use it for:** clips and bars give any angle on one axis, which suits bow loops, sleeve angles and tilted face plates.

### 4. A large ball-joint system for limbs
- **31133 and rabbit mech:**
  - **Ball side:** 2x2 bricks with two large balls (17114), and plates with a towball (3731, 15456).
  - **Socket side:** 2x2 bricks with a large ball socket and axle hole (92013 / 62712 / 57910 / 67696). These are the white forked pieces at the hips and shoulders.
  - Legs and arms hang off these.
  - The 1x2 plates with a small ball (14417) are used for the fine joints, as we do.
- **Use it for:** large balls carry real weight and look intentional, which suits legs and hips.

### 5. Big single shaping pieces instead of many small ones
- **Rabbit mech feet:** quarter domes (2x2 and 4x4), 1x3x2 curved arches (92903 / 6005), and 4x4 triple-curved wedges (47753).
- **31133 body:** 4x2 curved wedges and the 6x1 / 4x1 curved slopes.
- **Fur:** both builds use the white cloud/fur plate (the tail and shoulders) as one textured piece.
- **Fabric:** MF DOOM uses a soft-goods hood and cape, which can't be modelled in LDraw.

### 6. Half-stud offsets and fine nudges
- **Door-rail plates (32028)** and **jumper plates (15573, 87580)** shift panels by half a stud. They let the MF DOOM side panels and the 31133 face sit centred.
- **Hollow-stud round plates and tiles** stack on bars.
- **Use it for:** this is how a centred mouth or nose sits on an even-width face.

### 7. Turntable and big ball for the head
- **MF DOOM:** the bust base ends in a 4x4 turntable (61485 / 3403). The neck uses a large ball and cup, so the whole head can turn and tilt.

### 8. Single printed pieces for faces
- **31133:** the eyes are two black 1x1 round tiles with a highlight print. The nostrils are black 1x1 cones.
- **Rabbit mech:** the eyes are 1x2 rounded plates with two open studs (that is the whole face!), plus one heart tile on the chest.
- **Takeaway:** faces are one or two simple pieces, not drawn in bricks.

## What the server supports

All of the connections above can be modelled.

| Connection | How |
|---|---|
| Studs on brick sides, brackets, jumper plates | side studs read from the LDraw files |
| Small ball joints (joint-8) | `attach_joint` |
| Large ball joints and towballs | `attach_joint` (17114 into 92013 / 62712 / 57910 / 67696; towballs into 3730) |
| Clips and bars | `attach_joint`, with `bend`, `slide` and `flip` |
| Hinges, hinge plates, locking hinges, hinge fingers | `attach_joint` |
| Turntables | `attach_joint` |
| Technic pins and axles | `attach_joint`, from the LDCad connection data |
| Bars into holes, wheels on axle pins and wheel holders | `attach_joint` (`bar_hole`); see [vehicle_builds_techniques.md](vehicle_builds_techniques.md) |
| Sub-assembly built in any direction | `modules.mount_on_stud` |

[part_support_probe.txt](part_support_probe.txt) is the check made before these were added. It shows which connections were missing at that time.
