# 1080 Snowboarding clean room: status

## Decisions (logged as made)
- 2026-10-01 16:08 ROM arrived (`D:/1080 Snowboarding (Japan, USA) (En,Ja).zip`), sha1 79cd1166… / md5 fa27089c… = exactly the
  decomp's target. Unpacked to `D:/n64work/1080/baserom.z64` (dirty, never committed).
- Decomp `bigyoshi51/1080-decomp` cloned LF to `D:/n64work/1080/pristine` (a file named `" "` in the repo cannot exist on
  Windows; it is an empty blob and was skipped).
- **Web route = 3: clean ROM + WASM N64 emulator** (EmulatorJS 4.2.3 + mupen64plus_next/GLideN64, `ports/ejs` reused from the
  DK64/Conker sessions; runtime at `C:/Users/andre/n64work/mk64/emu`). Why: no PC port exists, the decomp is 38 % C and
  only targets a matching ROM. The core's ROM-DB entry "1080 Snowboarding (JU) (M2) [b1]" is re-pointed at our ROM's MD5
  (SRAM save + rumble settings). Dev check: retail boots in headless Edge to the board-select menu, audio buffers flow.
- **The decomp does not split assets** (they are `bin` segments). Our own tool does: `games/ten80/romfs.py` walks the ROM's
  two section streams (131 named files; sections Info/Sym/Reloc/Text/Data/RoData/Bss/Binary, some Yay0).
- **Clean ROM = retail code bytes + regenerated assets patched in place** (the "clean image" way; code is a kept fact and the
  decomp's build is byte-identical anyway).

## Works
- ROM file-system walker, Yay0 decoder.
- Emulator page (`ports/ejs`), dev retail boot check.

## Next
- Texture descriptors (symbols + relocs give boundaries), spec, generator, Yay0 encoder that fits the slots.
- Audio: bank/wave tables, resynthesis.
- Fonts / text-bearing images (`flowimgs.bin`, `charsel`, `gamegfx`), faces (rider portraits), board art.
- Taint, publish.

## Known emulator issues (retail too)
- GLideN64 shows noise frames on the title/intro (framebuffer effect) and line artefacts on the sponsor logos; try core options.

## For the morning
- (nothing yet)
