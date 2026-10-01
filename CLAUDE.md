# 1080 Snowboarding — clean-room web build

You are running **unattended overnight**. The user prompts once (decomp link, ROM path) and checks in the morning. Work autonomously: decide with the defaults below, log every decision in `STATUS.md`, and never stop to ask unless something is truly blocking (then write the question in STATUS.md and continue with anything else).

## Goal
A playable **web build** of 1080 Snowboarding, built from the community decomp, where **every asset the decomp extracts from the ROM is regenerated** (clean room), published as `andrewnakas/1080-cleanroom` + GitHub Pages. Same result as Super Mario 64 (https://andrewnakas.github.io/sm64-cleanroom/) and Pilotwings 64.

## Priorities tonight (user's words: "get all the visuals and gameplay and images/sprites correct")
1. Game boots and is playable in the browser (keyboard + gamepad), audio engine working (no dropouts).
2. **Everything readable**: fonts, HUD, dialog, text inside textures (re-typeset).
3. **Faces, sprites, pictures correct**: eyes/mouths/portraits/icons/sprites via briefs (`cleanroom.gfx.facepaint`), illustrations via renders of the game's own geometry (`cleanroom.gfx.c_render`), HUD widgets drawn per state.
4. Textures: kept colour grid + alpha outline (default), better where it matters.
5. Voices: **placeholder** TTS character voices only; build the practice pack so the user can record in the morning. Do not spend long on voices.

## Pre-answered scope (same as SM64; do not ask)
- Keep as facts: decomp code/geometry/text, texture format+size+4x4 grid+2-bit alpha, sample length/rate/loops/coarse outline/median pitch, **note sequences** (melodies), demo inputs.
- Regenerate everything else. No retail pixels/samples in outputs. Taint scan must be 0 failing.
- **No voice cloning** of real actors, no models trained on retail audio (placeholders = Piper TTS, see cleanroom.voice.voices).
- Web route: see docs/DECOMP_PLAYBOOK.md §4. Prefer a PC port with Emscripten; otherwise **clean ROM + WASM N64 emulator**; N64Recomp+ports/wasm only as last resort. Decide within the first hour and log why.
- Publish when it boots, plays and taint passes: new public repo + gh-pages (gh CLI is logged in as andrewnakas). Push updates as you improve. Never publish dirty trees, dev builds, ROMs or retail clips.

## Where things are
- This folder: your repo. `cleanroom/` shared library (copy; extend freely here), `ports/`, `tools/`, `docs/DECOMP_PLAYBOOK.md` (**read first**, it is the checklist of traps), `docs/HARNESS.md` (PW64 lessons), `reference/sm64/` (the finished SM64 game module to copy patterns from: generate.py, drawn.py, facepaint briefs, paintings.py, level_render.py, voices).
- Work dirs: `D:/n64work/1080/` (pristine, dirty, clean, build). Build on D: (C: is nearly full). **E: is unplugged**: the emsdk that lived at E:/n64web/emsdk is gone; if the chosen web route needs Emscripten, install emsdk once into the shared `D:/n64work/emsdk` (reuse it if another session already did).
- Toolchain: `tools/setup_winbin.sh` (zig cc as gcc, clang as `as`, llvm-objcopy, hexdump, python3, make). IDO 5.3 native: `C:/Users/andre/n64work/idowin` (see PW64 `tools/idowin`); IDO 7.1 if needed from ido-static-recomp releases (Windows builds). Zig: `~/.local/zig-x86_64-windows-0.16.0`, LLVM: `~/.local/clang+llvm-23.1.2-x86_64-pc-windows-msvc`.
- Python 3.12 with numpy, scipy, librosa, pyworld, piper-tts (voices: `C:/Users/andre/n64work/piper_voices`), faster-whisper, av, websocket-client.
- Browser checks: `python ports/wasm/serve.py <site> <port>` + `python ports/wasm/headless_shot.py <out> --base http://localhost:<port>/index.html --secs 5,10 --query "keys=..." --webgl`; hangs: `ports/wasm/cdp_stack.py`. Page template with dev hooks: `ports/web/shell.html`.

## How to work (token-minimal)
- Scripts print one-screen summaries; background long jobs and wait for the notification; one contact sheet per question; fixes as patch lists / JSON briefs.
- Clone decomps with `-c core.autocrlf=false -c core.eol=lf`.
- Keep `STATUS.md` current: what works, decisions, what's next, and a short "for the morning" list (what to record, what to look at).
- Commit often (end commit messages with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`).

## ROM / decomp
- ROM: C:/Users/andre/Downloads/1080 Snowboarding (Japan, USA) (En,Ja).zip (unzip first; not on disk yet as of 2026-10-01)
- Decomp: https://github.com/bigyoshi51/1080-decomp (matching decomp, about 38 percent, ROM-exact build)

## Machine budget (many sessions share this PC)
- **Disk:** D: has about 33 GB free for everyone. Keep this game under ~5 GB (`git clone --depth 1`, one dirty + one clean tree, delete stale build variants). Run `df -h /d` before big steps; under 10 GB free: stop heavy work, note "blocked on disk" in STATUS.md, do light work only.
- **D: is an external drive that dropped off once (2026-10-01 15:04).** If paths under D:/ stop existing, do not recreate anything elsewhere: wait and re-check every 10 minutes. Commit often so work survives.
- **Memory:** the PC ran out of RAM with ten sessions. Use `make -j3`, one headless browser at a time, close servers when done, avoid loading whole ROM-sized arrays repeatedly.
- **ROM missing?** The user is fetching it: look for any matching file in C:/Users/andre/Downloads and in D:/ (root) each loop. Until it is there, do everything that needs no ROM (clone, toolchain, read the decomp's asset layout, choose the web route, write the game module), write "BLOCKED: ROM" plus the exact ROM revision / sha1 the decomp needs at the top of STATUS.md, and re-check every 20 minutes. Never download a ROM.
- **Partial decomp is fine:** the clean-ROM route only needs the decomp to build a matching ROM; undecompiled code stays as asm. If the decomp does not build a matching ROM, patch the regenerated assets straight into a copy of the ROM image at their known offsets (the Pilotwings 64 "clean image" way) and prove with the taint scan that only spec regions differ. Donkey Kong 64 and Conker (D:/n64work/dk64-cleanroom, D:/n64work/conker-cleanroom, read-only reference) were done from partial decomps.
- **Voices:** build the practice pack as `D:/n64work/<id>/practice/` in the standard layout (`practice_<who>_call_and_response.wav`: clip, 0.3 s, 80 ms 880 Hz beep, gap 1.5x+1.5 s; `SCRIPT.txt` with `== <who>` sections). The user records with the Mac voice kit (D:/n64work/voicekit), which reads exactly that.
