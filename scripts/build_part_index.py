"""Build (or rebuild) the part search index used by find_parts and part_info.

Run from the brickbuilder-mcp folder:  uv run python scripts/build_part_index.py
Takes a few minutes; uses all CPU cores. Writes data/part_index.json.
"""
from brickbuilder import ldraw, part_index

if __name__ == "__main__":
    if not ldraw.library_available():
        raise SystemExit("The LDraw library is missing: run scripts/fetch_ldraw.sh first.")
    part_index.build()
