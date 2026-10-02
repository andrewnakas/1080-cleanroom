"""Spoken clips: placeholder speech by Piper TTS (offline stock voices, our own performance of the words; no
cloning, nothing trained on the original audio).  Recorded takes (games/ten80/takes/<clip>.wav) win over TTS.

Facts used (spec/voices.json, written by the dirty-room `transcribe` step): per clip its words (speech
recognition); from spec/audio.json its length, rate and median pitch.

    python -m games.ten80.voices transcribe <rom> [cuda|cpu] [model]   DIRTY: words per clip -> spec/voices.json
    python -m games.ten80.voices build                                 TTS -> games/ten80/voices/<clip>.wav
    python -m games.ten80.voices practice <rom> <out dir>              DIRTY practice pack (personal use only)
    python -m games.ten80.voices cut <recording.wav> <track>           user's recording -> games/ten80/takes/
"""
import json
import os
import re
import struct
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "spec", "voices.json")
CACHE = os.path.join(HERE, "voices")
TAKES = os.path.join(HERE, "takes")
PIPER_DIR = os.environ.get("PIPER_VOICES", "C:/Users/andre/n64work/piper_voices")
HZ = 22050
MIN_S = 0.45

# one stock voice per sample bank (a bank holds one speaker): track name -> (Piper model, semitones)
VOICES = {"rider4": ("en_US-ryan-high", -3.0), "rider5": ("en_US-amy-medium", 1.0), "rider6": ("en_US-joe-medium", 4.0),
          "rider7": ("en_US-joe-medium", 1.5), "rider8": ("en_US-ryan-high", 0.0), "rider9": ("en_US-joe-medium", -2.0),
          "announcer": ("en_US-ryan-high", 1.5), "vocals": ("en_US-amy-medium", 0.0)}
# speech recognition slips, corrected by ear-free common sense (mode names are in the menu text)
FIX = {"Vibish!": "Finish!", "METRACE!": "Match Race!", "TRADING!": "Training!", "2 players.": "Two players!",
       "Fuck you, dude.": "Later, dude!", "Shit.": "Sweet!", "I- Thi-": "Hey!", "What that that?": "What was that?",
       "Done now!": "Come on!", "Yada!": "Yeah!", "Hola!": "Whoa!", "testing": "Testing.", "MAN!": "Man!",
       "Ricky Winterborg": "Ricky Winterborn!", "RICKY WINTERBOARD!": "Ricky Winterborn!", "Rob Heywood!": "Rob Haywood!",
       "I'm Curry Hayami!": "Akari Hayami!", "LEAD AIR!": "Lien Air!", "FROOD FLIP": "Front Flip!", "method": "Method!",
       "Shifty": "Shifty!", "tail grab": "Tail Grab!", "versus.": "Versus!", "NOSEGRAB": "Nose Grab!"}
MIN_BANK = 4                 # banks 0-3 are instruments and effects (recognition there is noise)
_V = {}


def track(key):
    b = int(key.split(":")[0])
    return "rider%d" % b if b < 10 else ("announcer" if b < 12 else "vocals")      # bank 12: sung phrases in the music


def band(who):
    m, st = VOICES.get(who, VOICES["announcer"])
    return who, m, st


def tidy(key, text):
    """-> cleaned words, or None when the clip is not speech."""
    if int(key.split(":")[0]) < MIN_BANK:
        return None
    text = FIX.get(text, text)
    if text.isupper() and len(text) > 5 and " " not in text and text.rstrip("!") not in ("OPTIONS", "WELCOME"):
        return None                                   # "CHEERING", "MMMMMMMM": sound tags
    if text.isupper():
        text = text.title()
    return text


def fname(key):
    return key.replace(":", "_") + ".wav"


def lines():
    return json.load(open(SPEC)) if os.path.exists(SPEC) else {}


def wav_read(path, rate=HZ):
    with wave.open(path) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768
        if w.getnchannels() == 2:
            x = x.reshape(-1, 2).mean(1)
        if w.getframerate() != rate:
            import librosa
            x = librosa.resample(x, orig_sr=w.getframerate(), target_sr=rate)
        return x


def wav_write(path, x, rate=HZ):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def trim(x, thr=0.006):
    idx = np.nonzero(np.abs(x) > thr)[0]
    return x[max(0, idx[0] - 300):idx[-1] + 300] if len(idx) else x[:0]


def piper(model, text, length):
    from piper import PiperVoice, SynthesisConfig
    if model not in _V:
        _V[model] = PiperVoice.load(os.path.join(PIPER_DIR, model + ".onnx"))
    v = _V[model]
    cfg = SynthesisConfig(length_scale=length, noise_scale=0.7, noise_w_scale=0.8)
    x = np.concatenate([c.audio_float_array for c in v.synthesize(text, syn_config=cfg)]).astype(np.float32)
    return x, v.config.sample_rate


def say(text, who, secs):
    """One phrase fitted to `secs`: float32 at HZ."""
    import librosa
    _, model, semis = band(who)
    f = 2 ** (semis / 12)
    length = 1.0 * f
    y = np.zeros(0, np.float32)
    for _ in range(4):
        x, sr = piper(model, text, length)
        x = trim(x)
        if not len(x):
            break
        y = librosa.resample(x, orig_sr=sr * f, target_sr=HZ).astype(np.float32)
        if len(y) <= secs * HZ * 1.03 or length < 0.5 * f:
            break
        length *= max(0.5, secs * HZ / len(y) * 0.97)
    peak = np.abs(y).max() if len(y) else 0
    return (y / peak * 0.8).astype(np.float32) if peak else y


def clip(key, d):
    """Clean room: the speech for one sample slot at the slot's rate, or None (not a spoken clip)."""
    for folder in (TAKES, CACHE):
        p = os.path.join(folder, fname(key))
        if os.path.exists(p):
            x = wav_read(p, d["rate"])[:d["nframes"]]
            n = len(x)
            fade = min(n, int(0.01 * d["rate"]))
            if fade:
                x[n - fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
            return np.pad(x, (0, d["nframes"] - n))
    return None


def stamp():
    """Changes whenever a take or a TTS clip changes (part of the audio cache key)."""
    out = []
    for folder in (TAKES, CACHE):
        if os.path.isdir(folder):
            for n in sorted(os.listdir(folder)):
                st = os.stat(os.path.join(folder, n))
                out.append((n, st.st_size, int(st.st_mtime)))
    return out


def build():
    spec = json.load(open(os.path.join(HERE, "spec", "audio.json")))["waves"]
    os.makedirs(CACHE, exist_ok=True)
    L = lines()
    n = 0
    for key, v in L.items():
        p = os.path.join(CACHE, fname(key))
        if os.path.exists(p):
            continue
        d = spec[key]
        x = say(v["text"], v["who"], d["nframes"] / d["rate"])
        wav_write(p, x)
        n += 1
    print(f"voices: {len(L)} spoken clips, {n} newly synthesised -> {CACHE}")


# ------------------------------------------------------------------ dirty room

def retail_clips(rom):
    """-> {key: (float32 at 16 kHz, facts)} for every non-looping clip of MIN_S or more."""
    import pickle
    from . import audio
    cache = "D:/n64work/1080/work/retail_clips.pkl"          # dirty, dev only (decoding is slow)
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    P = audio.parse(rom)
    B0, W0 = P["sec"]["bank"][0], P["sec"]["wave"][0]
    spec = audio.load_spec()["waves"]
    out = {}
    for (wb, addr), w in sorted(P["waves"].items()):
        key = f"{wb}:{addr:X}"
        d = spec[key]
        if d["loop"][2] or d["nframes"] / d["rate"] < MIN_S:
            continue
        codec = w["flags"] >> 4
        coefs = list(struct.unpack_from(">%dh" % (16 * w["npred"]), rom, B0 + w["books"][0] + 8))
        raw = bytes(rom[W0 + w["base"]:W0 + w["base"] + (w["len"] // audio.FRAME[codec]) * audio.FRAME[codec]])
        pcm = audio.decode(raw, coefs, w["npred"], codec).astype(np.float32) / 32768
        out[key] = (pcm, d)
    if os.path.isdir(os.path.dirname(cache)):
        pickle.dump(out, open(cache, "wb"))
    return out


def transcribe(rom, dev="cuda", name="medium.en"):
    import librosa
    from faster_whisper import WhisperModel
    model = WhisperModel(name, device=dev, compute_type="float16" if dev == "cuda" else "int8", cpu_threads=3)
    out, done = {}, set()
    part = SPEC + ".partial"                 # resumable: one JSON line per clip already heard
    if os.path.exists(part):
        for ln in open(part):
            k, v = json.loads(ln)
            done.add(k)
            if v:
                out[k] = v
    clips = retail_clips(rom)
    log = open(part, "a")
    for key, (pcm, d) in clips.items():
        if key in done:
            continue
        x = librosa.resample(pcm, orig_sr=d["rate"], target_sr=16000)
        segs, _ = model.transcribe(x, language="en", beam_size=5, condition_on_previous_text=False)
        segs = [s for s in segs if s.no_speech_prob < 0.6 and s.avg_logprob > -0.9]
        text = " ".join(s.text.strip() for s in segs).strip()
        v = None
        if len(re.sub(r"[^A-Za-z]", "", text)) >= 2:
            v = out[key] = {"text": text, "secs": round(d["nframes"] / d["rate"], 2)}
        log.write(json.dumps([key, v]) + "\n")
        log.flush()
    log.close()
    final = {}
    for key, v in out.items():
        t = tidy(key, v["text"])
        if t:
            final[key] = {"text": t, "who": track(key), "secs": v["secs"]}
    out = final
    json.dump(out, open(SPEC, "w"), indent=0)
    print(f"transcribed: {len(out)} of {len(clips)} clips have words -> {SPEC}")


def plan():
    out = {}
    for key, v in lines().items():
        out.setdefault(v["who"], []).append((key, v))
    return out


def practice(rom, out):
    import librosa
    clips = retail_clips(rom)
    os.makedirs(out, exist_ok=True)
    beep = (0.2 * np.sin(2 * np.pi * 880 * np.arange(int(0.08 * HZ)) / HZ)).astype(np.float32)
    script = ["1080 Snowboarding voice practice. One track per voice register: listen, speak after each beep, in character.",
              "Record each track as one file, then: python -m games.ten80.voices cut <file> <track>",
              "These clips come from your own ROM: practice only, never share or commit them.", ""]
    for who, items in sorted(plan().items()):
        parts = []
        script.append(f"== {who}  (practice_{who}_call_and_response.wav)")
        for key, v in items:
            pcm, d = clips[key]
            x = librosa.resample(pcm, orig_sr=d["rate"], target_sr=HZ).astype(np.float32)
            gap = np.zeros(int((len(x) / HZ * 1.5 + 1.5) * HZ), np.float32)
            parts += [x, np.zeros(int(0.3 * HZ), np.float32), beep, gap]
            script.append(f"  {key.replace(':', '_'):10s} max {len(x) / HZ:.1f}s  \"{v['text']}\"")
        wav_write(os.path.join(out, f"practice_{who}_call_and_response.wav"), np.concatenate(parts))
    open(os.path.join(out, "SCRIPT.txt"), "w", encoding="utf8").write("\n".join(script))
    print(f"practice pack: {sum(len(v) for v in plan().values())} clips, tracks {sorted(plan())} -> {out}")


def cut(recording, track):
    """Cut the user's recording of one track into takes, using only the spec's clip lengths."""
    spec = json.load(open(os.path.join(HERE, "spec", "audio.json")))["waves"]
    x = wav_read(recording)
    os.makedirs(TAKES, exist_ok=True)
    o = n = 0
    for key, v in plan()[track]:
        d = spec[key]
        ln = int(round(d["nframes"] / d["rate"] * HZ))
        o += ln + int(0.3 * HZ) + int(0.08 * HZ)
        gap = int((ln / HZ * 1.5 + 1.5) * HZ)
        seg = trim(x[o:o + gap], 0.02)
        if len(seg) > HZ // 10:
            wav_write(os.path.join(TAKES, fname(key)), seg / (np.abs(seg).max() or 1) * 0.8)
            n += 1
        o += gap
    print(f"takes: {n} cut for track {track} -> {TAKES}")


if __name__ == "__main__":
    a = sys.argv
    if a[1] == "transcribe":
        transcribe(open(a[2], "rb").read(), *a[3:5])
    elif a[1] == "build":
        build()
    elif a[1] == "practice":
        practice(open(a[2], "rb").read(), a[3])
    elif a[1] == "cut":
        cut(a[2], a[3])
