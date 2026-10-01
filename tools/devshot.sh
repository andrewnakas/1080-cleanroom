#!/bin/sh
# Dev check: put a ROM in the local dev site, run the headless browser script, make one contact sheet.
#   sh tools/devshot.sh <rom> <name> "<cdp script>" [extra cdp_shot args]
set -e
W=/d/n64work/1080
ROM=$1; NAME=$2; SCRIPT=$3; shift 3
cd /d/n64work/1080-cleanroom
cp ports/ejs/index.html $W/devsite/index.html
cp "$ROM" $W/devsite/dev.z64
python ports/ejs/patch_core.py "$ROM" C:/Users/andre/n64work/mk64/emu/cores_orig $W/emu/cores_dev | tail -1
cp $W/emu/cores_dev/*.data $W/devsite/data/cores/
curl -s -o /dev/null http://localhost:8171/index.html || (python ports/wasm/serve.py $W/devsite 8171 > $W/serve.log 2>&1 &)
sleep 1
CDP_MUTE=1 python ports/ejs/cdp_shot.py $W/shots/$NAME --url "http://localhost:8171/index.html?rom=dev.z64&audiolog=1" --script "$SCRIPT" --gpu --port 9371 "$@" | tail -1
grep TENAUDIO $W/shots/$NAME/console.txt | tail -1
python tools/sheet.py $W/shots/$NAME
