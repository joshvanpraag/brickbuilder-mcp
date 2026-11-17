# Techniques from two car builds

Notes from two 8-wide, minifig-scale car MOCs (the Speed Champions style):
- **'69 Mustang** (Rebrickable MOC-95701, by w35wvi): a 1960s fastback.
- **Police SUV** (Rebrickable MOC-245342, by Linse, from Gamma Bricks): a modern police utility vehicle with a push bar and a light bar.

Both are built mostly sideways and in small sub-assemblies, like the character builds in
[reference_builds_techniques.md](reference_builds_techniques.md). The ideas below carry over
to any model, not just cars.

## Techniques

### 1. A plate chassis with wheels on axle pins
- **Chassis:** a flat layer of plates. Technic bricks 1 x 2 with a hole (3700) sit where the wheels go.
- **Wheels:** an axle pin (3749, usually tan) goes into each hole. A rim with tyre goes on its axle end.
- **Body:** the chassis is narrower than the wheel track, so the wheel hubs clear it.
- **Wheel arches:** arched mudguard pieces sit over the wheels. Curved slopes under the sills round off the bottom edge.

The server can do all of this ([demo](../examples/vehicles/wheels_demo.py), [render](../examples/vehicles/renders/wheels_demo.png)).

### 2. Side stripes and doors as flat panels, built separately
- **Stripes:** the SUV's blue-and-white stripes are thin stacks of plates, with small slopes at the ends. They're built on their own, then pressed onto side studs (bricks with studs on the side, 1x4 bricks with 4 side studs).
- **Doors:** the Mustang's door panels are flat stacks of plates and tiles. They're mounted on brackets, then turned a few degrees on a single stud, so the body narrows towards the back when seen from above.

The point: a flat panel on side studs gives a smooth, stud-free side in any colour pattern. Turning it on one stud gives a gentle angle without hinges.

### 3. Lights from small transparent pieces
- **Taillights and headlights:** 1x1 round trans-red or trans-clear plates on side studs, or a trans-clear 1x1 plate tucked under a tile so only its edge shows.
- **Light bar:** a stack of 1x1 round plates alternating trans-red and trans-clear, on a wedge plate. It reads as a lit bar from a distance.
- **Grilles:** 1x2 grille tiles and slopes with a grille print.

### 4. Bodywork at an angle with hinges
The Mustang's sloping fastback is a hinge brick and hinge plate assembly set to the roof angle. The spoiler clips onto a bar. On the SUV, the windscreen is a transparent 1 x 4 x 2 panel tilted back, held at the top by bar holders with clips.

### 5. Push bar from clips and bars
The SUV's push bar is plates with clips, holding 4L bars and Technic connectors. It hangs on the nose by its clips, so its angle can be set.

### 6. A removable roof on door-rail plates
The SUV's roof is one sub-assembly: a large plate, tiles, curved slopes at the front, and the light bar. Plates with a door rail (32028) along its edges let it sit on the window pillars and lift off, so the interior stays reachable.

### 7. Underbody pieces built upside down
The nose and tail undersides are each built upside down as a separate piece (plates, wedge plates, curved slopes, quarter-round tiles), then flipped and pressed on from below. Curved pieces then face down and round off the bottom edge.

### 8. Interiors on brackets
The dashboard is a plate with printed gauge tiles and a steering wheel, mounted upright on a bracket. Seats are hinge bricks or seat pieces on the floor plates.

## What the server supports

| Technique | How |
|---|---|
| Wheels on axle pins in bricks with holes | `attach_joint`: the pin's `pin` into the brick's `pin_hole`, then the wheel's `axle_hole` onto the pin's `axle` |
| Wheels on wheel-holder plates (4600, 6157) | `attach_joint`: the wheel's `bar_hole` onto the holder's pin (`bar`), `flip` so the tyre faces out |
| Rims with tyres | use the LDraw rim + tyre parts (rim number + `c01`, e.g. `18976c01`, `6014ac01`). There's no tyre-on-rim joint, so these combined parts are the way to fit a tyre |
| Panels on side studs, turned on one stud | `attach_parts` / `modules.mount_on_stud` |
| Light stacks, tiles over trans plates | ordinary stud placement |
| Hinge bodywork, clips and bars, door rails | `attach_joint` (hinges, clips and bars), studs for the rail plates |
| Bars into hollow studs or tubes | `attach_joint` with `bar_hole` |
| Underbody built upside down | `modules.mount_on_stud` |

Known limits:
- **Wheels with no connection data:** the newer wheel rim 6014b has none in the LDCad data, so it can't be joined. The older 6014a (same size) can.
- **Grid placement of parts that stick out:** for a part whose pins stick out past its body, like the wheel holder 4600, placing it by grid corner (`x, y, z`) puts it half a stud off. Place it with an exact `ldu` position instead, as the demo does.
- **Door-rail plates** (32028) join by their studs; sliding along the rail isn't modelled.
