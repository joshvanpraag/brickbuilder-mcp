#!/usr/bin/env bash
# Downloads the LDCad shadow library (connection "snap" data for LDraw parts, by Roland
# Melkert, CC BY-SA 4.0) into data/ldcad_shadow. It tells the server where every stud,
# anti-stud, bar, clip, pin, axle, hole, ball and hinge finger of a part is.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data
curl -L --fail -o data/ldcad_shadow.zip \
  https://github.com/RolandMelkert/LDCadShadowLibrary/archive/refs/heads/main.zip
rm -rf data/ldcad_shadow data/LDCadShadowLibrary-main
(cd data && unzip -oq ldcad_shadow.zip 'LDCadShadowLibrary-main/p/*' 'LDCadShadowLibrary-main/parts/*' \
  'LDCadShadowLibrary-main/LICENSE.md' && mv LDCadShadowLibrary-main ldcad_shadow && rm ldcad_shadow.zip)
echo "LDCad shadow library installed in data/ldcad_shadow"
