#!/bin/sh
# Build the Russian PlayStation image.
#
#   sh ru/build_ru.sh [build.py ps1 options...]     e.g. --no-fmv, --release
#
# 1. merge the Russian (work/ru/out) into ps1/translation, if present
# 2. assign letter-pair glyphs for the Russian text, re-fit, re-assign
#    (the fit of a string depends on the table and the table on the text)
# 3. the ordinary build
set -e
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
if [ -d work/ru/out ]; then
    $PY ru/rutools.py merge --all
fi
$PY ps1/tools/rebuild_pairs.py --fresh
for i in 1 2; do
    if [ -d work/ru/out ]; then $PY ru/rutools.py merge --all; fi
    $PY ps1/tools/rebuild_pairs.py
done
$PY build.py ps1 "$@"
