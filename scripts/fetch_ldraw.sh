#!/usr/bin/env bash
# Downloads the official LDraw parts library into data/ldraw (parts, primitives, colours).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data
curl -L --fail -o data/complete.zip https://library.ldraw.org/library/updates/complete.zip
# extract everything but the example models: sub-folders (parts/s, p/48, p/8) must come
# along, and some unzip builds don't descend into them for a pattern like 'ldraw/parts/*'
(cd data && unzip -oq complete.zip -x 'ldraw/models/*' && rm complete.zip)
for d in parts parts/s p p/48 p/8; do
  [ -d "data/ldraw/$d" ] || { echo "error: data/ldraw/$d is missing after extraction" >&2; exit 1; }
done
echo "LDraw library installed in data/ldraw ($(find data/ldraw/parts -name '*.dat' | wc -l) part files)"
