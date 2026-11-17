#!/usr/bin/env bash
# Downloads Rebrickable's free catalogue files (parts, colours, sets and which parts came in
# which colours) into data/rebrickable, then builds data/rebrickable_index.json from them.
# About 17 MB. Data from rebrickable.com; see their terms of use.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/rebrickable
for f in colors parts part_categories part_relationships elements inventory_parts inventories sets; do
  curl -L --fail -s -o "data/rebrickable/$f.csv.gz" "https://cdn.rebrickable.com/media/downloads/$f.csv.gz"
done
echo "Rebrickable catalogue downloaded to data/rebrickable"
if command -v uv >/dev/null; then
  uv run python -c "from brickbuilder import rebrickable; print(rebrickable.build())"
fi
