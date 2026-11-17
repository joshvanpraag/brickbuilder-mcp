# Organic sculpting helpers

Reusable pieces for building curvy, character-style models with brickbuilder's Python API.
Read [docs/organic_sculpting.md](../../docs/organic_sculpting.md) first for the rules behind them.

| File | What it is |
|---|---|
| `modules.py` | Helpers. `mount()` attaches a separately built sub-assembly on a joint (`partners=` for doubled hinges); `mount_on_stud()` attaches one on any stud, sideways or upside down; `place_best()` searches ball-joint poses for the one that best fits a goal. |
| `body_chain.py` | A curved body: round segments on hinges, each bent a few degrees, with optional shoulder ball joints, printed-tile face bands and doubled hinges. |
| `lowell_sphere.py` | `lowell_sphere()` builds a round ball from 62 plain parts: six stepped plate caps on a core of bricks with side studs. |
| `snot_demo.py` | A small demo of `mount_on_stud()`: a dome built on its back, pressed onto sideways studs. |
| `renders/` | Pictures of what the demos build. |

## Run them

Run these from the `brickbuilder-mcp` folder, after setup (see [RESTORE.md](../../RESTORE.md)):

```
uv run python examples/organic_sculpting/snot_demo.py snot.png
uv run python examples/organic_sculpting/body_chain.py chain.png 3 8
uv run python examples/organic_sculpting/lowell_sphere.py sphere.png
```

Each one writes a picture to the file name you give it. For `body_chain.py`, the numbers
are the bend per joint in degrees and the number of segments. Or open the folder in
Claude Code and ask Claude to run them.
