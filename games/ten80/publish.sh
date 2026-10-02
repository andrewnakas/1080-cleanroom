#!/usr/bin/env bash
# Build the clean ROM, gate on the taint scan, assemble the EmulatorJS site and push it to gh-pages.
#   games/ten80/publish.sh [--no-push]
# Never publishes when the taint scan fails. The retail ROM, dev builds and practice clips stay on D:.
set -euo pipefail
cd "$(dirname "$0")/../.."
W=D:/n64work/1080
RETAIL=$W/baserom.z64
CLEAN=$W/build/ten80_clean.z64
SITE=$W/site
EJS=$W/devsite            # holds data/ (EmulatorJS 4.2.3 runtime)
CORES=C:/Users/andre/n64work/mk64/emu/cores_orig
mkdir -p $W/build

python -m games.ten80.generate $RETAIL $CLEAN | tail -2
python -m games.ten80.taint $RETAIL $CLEAN | tail -3
python -m games.ten80.taint $RETAIL $CLEAN > /dev/null || { echo "TAINT FAILED: not publishing"; exit 1; }

if [ ! -d $SITE/.git ]; then
  mkdir -p $SITE && git -C $SITE init -q -b gh-pages
  git -C $SITE remote add origin https://github.com/andrewnakas/1080-cleanroom.git
fi
[ -f $EJS/LICENSE ] || cp /d/n64work/bk/site/data/LICENSE.EmulatorJS $EJS/LICENSE
python ports/ejs/make_site.py $CLEAN $EJS $SITE
python ports/ejs/patch_core.py $CLEAN $CORES $SITE/data/cores | tail -1
[ "${1:-}" = "--no-push" ] && { echo "site ready (not pushed): $SITE"; exit 0; }
cd $SITE
git add -A 2>/dev/null
git -c user.name="andrewnakas" -c user.email="andrewnakas@users.noreply.github.com" commit -qm "site: $(date +%F\ %H:%M)" || true
git push -f -q origin gh-pages
echo "pushed gh-pages"
