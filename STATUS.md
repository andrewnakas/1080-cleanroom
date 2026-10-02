# 1080 Snowboarding clean room: status

**LIVE: https://andrewnakas.github.io/1080-cleanroom/** (source: https://github.com/andrewnakas/1080-cleanroom)
Boots, menus readable, a race plays start to finish, audio flows (no dropouts in headless runs), taint scan 0 failing.

## Decisions (logged as made)
- 2026-10-01 16:08 ROM arrived (`D:/1080 Snowboarding (Japan, USA) (En,Ja).zip`), sha1 79cd1166… / md5 fa27089c… = exactly the
  decomp's target. Unpacked to `D:/n64work/1080/baserom.z64` (dirty, never committed).
- Decomp `bigyoshi51/1080-decomp` cloned LF to `D:/n64work/1080/pristine` (a file named `" "` in the repo cannot exist on
  Windows; it is an empty blob and was skipped).
- **Web route = 3: clean ROM + WASM N64 emulator** (EmulatorJS 4.2.3 + mupen64plus_next/GLideN64, `ports/ejs` reused from the
  DK64/Conker sessions). Why: no PC port exists, the decomp is 38 % C and only targets a matching ROM. The core's ROM-DB
  entry "1080 Snowboarding (JU) (M2) [b1]" is re-pointed at our ROM's MD5 (SRAM save + rumble settings).
- **The decomp does not split assets** (they are `bin` segments). Our own tool does: `games/ten80/romfs.py` walks the ROM's
  two section streams (131 named files, some Yay0).
- **Clean ROM = retail code bytes + regenerated assets patched in place** (the "clean image" way; code is a kept fact and the
  decomp's build is byte-identical anyway). Yay0 sections are re-packed with our encoder and must fit their slot: a ladder
  lowers detail noise / dither until they do (5 map files needed it).
- Image catalog (1011 images): material tag lists, `flowimgs.bin` records (447 named menu/HUD images), palette pictures,
  plus hand-found code-drawn blobs: HUD digit strips (`gamegfx`), two UI fonts (`n64proc`, `titproc`), snow textures, the
  boot module's inline textures and 8x8 debug font. Everything else in the data sections is geometry / tables (kept).
- **All text re-typeset** with open fonts (Rubik, Lilita One, Luckiest Guy, Press Start 2P; licences in
  `games/ten80/fonts`). The Japanese-language image set (`j_*`) is typeset in English too (no open Japanese font here yet).
- Trademark art is not redrawn: the N64 logo, the sponsor logo screen, the Nintendo ending logo, the Lamar jacket
  logos and the "© Nintendo" line are replaced by plain "1080 CLEAN ROOM" style cards / "1080" decals.
- Quantisation dither: random for RGBA16 textures, 4x4 ordered for palette pictures (keeps skies compressible).
  Taint rule for decoded palette pictures is 32 texels (64 bytes), as in the Conker clean room; raw bytes keep 32.
- Voices: Whisper (small.en, CPU, offline; the GPU run crashed silently and medium.en stalled on a download) transcribes
  the words of the non-looping clips (dirty room, words only): 171 of 292 clips have words. Piper placeholder speech, one
  stock voice per sample bank (banks 4-9 = riders, 10-11 = announcer, 12 = sung phrases in the music). No cloning.
  Obvious mis-hearings are corrected in `voices.FIX` (names, trick names); two lines recognised as profanity were
  replaced by guesses ("Later, dude!", "Sweet!"). Takes in `games/ten80/takes/` override TTS.

## Works
- Boot -> title -> mode menu -> level / rider / board select -> race -> pause menu, keyboard + gamepad.
- 1011 images regenerated: 302 text images and fonts typeset, 107 colour pictures drawn (logo, name plates with flags,
  8 portraits x3 sizes, course banners, button / stick icons, rider face textures with eyes and mouths), rest = kept
  colour grid + alpha outline with our noise.
- 516 sound samples resynthesised (4-bit and 2-bit VADPCM, our books and loop states), sequences untouched.
- 171 spoken clips are placeholder TTS (`games/ten80/voices/*.wav`, our own output); practice pack built.
- `games/ten80/taint.py`: 0 failing, 0 bytes changed outside regenerated regions.
- `games/ten80/publish.sh`: generate -> taint gate -> site -> push.

## Known issues
- **Loading screens show white + coloured noise** for a second or two (title intro, course load). The emulator's video
  plugin shows memory the game is still filling; the original ROM does the same in this emulator. Core options
  (`EnableFBEmulation`, `EnableCopyColorToRDRAM`) did not help. Gameplay and menus are unaffected.
- Level-select pass cards for Hard / Expert are black (same on the original until unlocked).
- Backgrounds of the lodge (rider select) are soft: 16x16 colour grid of a 256x256 picture.
- HUD bottom-left icon is a blurred cube (not yet identified which texture it is).

## Next
- Sharper lodge / course preview pictures (render from the game's own geometry or briefs).
- Sign textures in `charsps` (difficulty pass cards), helicopter decals, map banners with text.

## For the morning
- Play: https://andrewnakas.github.io/1080-cleanroom/ (arrows, X = A, C = B, Z = Z, Enter = Start).
- Look at: menu text, rider portraits and name plates (select rider), rider faces in game, HUD digits.
- Record: practice pack in `D:/n64work/1080/practice/` (8 tracks: announcer 74 clips, vocals 33, rider4-9; `SCRIPT.txt`
  lists the words). Then `python -m games.ten80.voices cut <recording.wav> <track>` and `bash games/ten80/publish.sh`.
- Check the words in `games/ten80/spec/voices.json`: they are speech recognition, some rider shouts will be wrong.
