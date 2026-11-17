# Getting brickbuilder back on a new computer

This guide is for someone who doesn't write code. It gets the whole tool, plus everything we built and learned, back from GitHub and working with Claude again.

## Where everything lives

- **Your copy:** https://github.com/joshvanpraag/brickbuilder-mcp. This is the backup.
- **Original project:** brickbuilder-mcp was started by someone else, at https://github.com/ElRashoMacuin24/brickbuilder-mcp. Your copy is a fork of it, so the original author's credit and MIT license stay with it.
- **Branches:** the `main` branch has everything. Work in progress sometimes sits on the `sideways-building` branch first, and is then copied to `main`.

| Folder | What's in it |
|---|---|
| `src/brickbuilder/` | The tool itself (the MCP server Claude talks to). |
| `examples/organic_sculpting/` | Reusable helpers for curvy, character-style builds, with demos. |
| `docs/organic_sculpting.md` | What we learned about making LEGO look organic. |
| `docs/reference_builds_techniques.md` | Notes from the MF DOOM, 31133 and rabbit-mech builds. |
| `docs/vehicle_builds_techniques.md` | Notes from two minifig-scale car builds (wheels, side panels, lights). |
| `examples/vehicles/` | A small demo of putting wheels on a car chassis. |
| `README.md` | What the tool does, and every tool it gives Claude. |

**Not in the backup (on purpose):**
- **The LEGO parts library** (`data/ldraw`, about 145 MB): it's free, and setup re-downloads it.
- **The LDCad connection data** (`data/ldcad_shadow`), the Rebrickable catalogue (`data/rebrickable`) and the indexes built from them (`data/*.json`): setup downloads or rebuilds them.
- **Saved models** (`models/`): `.ldr` files you want to keep belong in `examples/`.
- **Claude's private memory notes** on your computer: the important lessons are copied into `docs/organic_sculpting.md`.

## The easy way: let Claude do it

1. Install the **Claude desktop app** and sign in.
2. Install **GitHub Desktop** (https://desktop.github.com) and sign in as `joshvanpraag`.
3. In GitHub Desktop, choose **File → Clone repository**, pick `joshvanpraag/brickbuilder-mcp`, and clone it. Note the folder it goes into.
4. In the Claude desktop app, open the **Code** tab, choose that folder, and say:
   > Set this project up following RESTORE.md, then register the brickbuilder MCP server and check it works.

Claude will install what's missing and run the steps below. Approve its prompts as they come up.

## The manual way (Windows)

1. **Install Git for Windows** (https://git-scm.com/download/win). It includes "Git Bash", the terminal used below.
2. **Install uv**, the tool that sets up Python. Open PowerShell and paste:
   ```
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
3. **Get the code.** Open Git Bash and paste:
   ```
   cd ~
   git clone https://github.com/joshvanpraag/brickbuilder-mcp.git
   cd brickbuilder-mcp
   ```
4. **Download the LEGO parts library and connection data, and set up Python.** This takes a few minutes:
   ```
   bash scripts/fetch_ldraw.sh
   bash scripts/fetch_ldcad_snaps.sh
   uv sync
   uv run python scripts/build_part_index.py
   bash scripts/fetch_rebrickable.sh
   ```
   - The second command downloads the LDCad connection data (about 2 MB). It lets the tool join pins, axles, clips and hinges.
   - The fourth command builds the part search index (a few minutes).
   - The last command downloads Rebrickable's catalogue (about 17 MB), so the tool knows which colours each part was really made in.
   - None of these are backed up, because they're downloaded or rebuilt.
5. **Tell Claude about the tool:**
   ```
   claude mcp add brickbuilder -s user -- uv --directory "$(pwd -W)" run brickbuilder-mcp
   ```
   If the `claude` command isn't found, do this step the easy way instead: ask Claude in the Code tab to register it.
6. Restart Claude. In a new Code session, ask: *"list the brickbuilder tools"*. If it lists `new_model`, `add_parts`, `render_model` and so on, everything is back.

## Check that it works

From the `brickbuilder-mcp` folder, in Git Bash:
```
uv run python examples/organic_sculpting/snot_demo.py test.png
```
It should print `overlaps []` and write `test.png`, a red block with a white dome on its front.
To check wheels too, run `uv run python examples/vehicles/wheels_demo.py wheels.png`.

## If something goes wrong

- **`uv sync` says "Missing expected target directory for Python minor version link"**:
  uv's shortcut to its Python copy is broken.
  1. Open the folder `%APPDATA%\uv\python`.
  2. Delete only the shortcut named `cpython-3.12-windows-x86_64-none`. Keep the folder whose name has the full version, like `cpython-3.12.13-…`.
  3. Run `uv sync` again from PowerShell.
- **A download script stops with "error: … is missing after extraction"**: the download was cut short or unpacked badly. Run the same script again.
- **A test fails**: from the `brickbuilder-mcp` folder, run them all:
  ```
  uv run python tests/test_joints.py
  uv run python tests/test_snaps.py
  uv run python tests/test_part_search.py
  uv run python tests/test_strength.py
  uv run python tests/test_rebrickable.py
  uv run python tests/test_wheels.py
  ```
  Then show Claude the output.

## Keeping the backup up to date

Nothing goes to GitHub until it's committed and pushed. At the end of a work session, ask Claude:
> Commit and push everything to my GitHub (origin), and update main.

In this folder, `origin` means your copy (joshvanpraag). `upstream` means the original author's; never push there. To pull in the original author's later improvements, ask Claude to "merge the latest from upstream".
