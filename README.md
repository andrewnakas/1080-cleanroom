# 1080 Snowboarding: clean-room web build

Play: https://andrewnakas.github.io/1080-cleanroom/

The game code, geometry, animation, parameters, text and note sequences are the facts documented by the
community decompilation ([bigyoshi51/1080-decomp](https://github.com/bigyoshi51/1080-decomp)).
**Every texture, picture, font and sound sample is regenerated** from coarse facts only:

| Asset | Kept fact | Regenerated |
|---|---|---|
| Textures, backgrounds | format, size, 4x4 colour grid (16x16 for large pictures), 2-bit alpha outline | all texels |
| Text images, fonts, HUD digits | size, where the ink sits | re-typeset with open fonts (Rubik, Lilita One, Luckiest Guy, Press Start 2P) |
| Sound samples | length, rate, loop points, coarse spectral outline, median pitch | waveform, ADPCM books, loop states |
| Voices | none of the performance | placeholder synthetic voices |

No ROM, no retail pixels and no retail samples are in this repository or on the site. `games/ten80/taint.py`
compares the published image against the original and must report `0 failing` before anything is pushed.

## Layout
- `games/ten80/` game module: ROM file-system walker (`romfs`, `usofile`), image catalog (`images`), dirty-room
  fact extraction (`extract_spec`, `audio`), clean generation (`generate`, `drawn`), taint scan, publish script.
- `cleanroom/` shared library (texture grid, glyphs, audio descriptors, VADPCM, voices, taint).
- `ports/ejs/` web page: EmulatorJS + mupen64plus-next (third-party, see the site's `THIRD_PARTY.md`).

## Build (needs your own cartridge dump, sha1 79cd1166c365e5809dec9b62e6d40d6032d5db3a)
    python -m games.ten80.generate <your rom> out.z64
    python -m games.ten80.taint <your rom> out.z64

Keys: arrows move, X = A (jump), C = B, Z = Z (crouch), S = R, Enter = Start, I J K L = C buttons. Gamepads work.

This is a fan preservation and research project, not affiliated with or endorsed by Nintendo.
