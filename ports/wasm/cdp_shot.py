"""Dev tool: open a page in headless Edge/Chrome with WebGPU, save CDP screenshots.

    python ports/wasm/cdp_shot.py <out dir> --url http://localhost:8090/index.html [--secs 5,10]
        [--keys "KeyW@6-9,Space@7"] [--webgl] [--wait N]

Unlike headless_shot.py this needs no ?dump= hook in the page: screenshots come
from Page.captureScreenshot, so WebGPU canvases work. Writes shot_<secs>.png and
console.txt (console messages, exceptions, and browser log entries).
--keys holds a key (DOM code) over a time window: "KeyW@6-9" presses at 6 s and
releases at 9 s; "Space@7" taps at 7 s.
"""
import argparse
import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request

import websocket

BROWSERS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]

KEYS = {"Space": (" ", 32), "Enter": ("Enter", 13), "Escape": ("Escape", 27), "ShiftLeft": ("Shift", 16),
        "ArrowUp": ("ArrowUp", 38), "ArrowDown": ("ArrowDown", 40), "ArrowLeft": ("ArrowLeft", 37),
        "ArrowRight": ("ArrowRight", 39), "Backspace": ("Backspace", 8)}


def key_info(code):
    if code in KEYS:
        return KEYS[code]
    if code.startswith("Key"):
        return code[3:].lower(), ord(code[3:])
    if code[:1] == "F" and code[1:].isdigit():
        return code, 0x6F + int(code[1:])
    if code.startswith("Digit"):
        return code[5:], ord(code[5:])
    return code, 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--url", required=True)
    ap.add_argument("--secs", default="5,10")
    ap.add_argument("--keys", default="")
    ap.add_argument("--wait", type=float, default=None, help="total seconds (default: last shot + 1)")
    ap.add_argument("--webgl", action="store_true", help="software GL instead of the real GPU")
    ap.add_argument("--port", type=int, default=9471)
    ap.add_argument("--size", default="1280,800")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    exe = next(b for b in BROWSERS if os.path.exists(b))
    secs = sorted(float(s) for s in a.secs.split(",") if s)
    events = []  # (time, kind, code)
    for spec in filter(None, a.keys.split(",")):
        code, when = spec.split("@")
        start, _, end = when.partition("-")
        events.append((float(start), "keyDown", code))
        events.append((float(end) if end else float(start) + 0.15, "keyUp", code))
    events.sort()
    total = a.wait or (max(secs + [e[0] for e in events]) + 1)
    try:  # never attach to another job's browser
        urllib.request.urlopen(f"http://127.0.0.1:{a.port}/json/version", timeout=1)
        raise SystemExit(f"port {a.port} already has a debugging browser; pass --port")
    except OSError:
        pass
    prof = tempfile.mkdtemp(prefix="cdpshot_")
    args = [exe, "--headless=new", f"--user-data-dir={prof}", f"--remote-debugging-port={a.port}",
            "--remote-allow-origins=*", "--no-first-run", "--autoplay-policy=no-user-gesture-required",
            f"--window-size={a.size}", "--enable-unsafe-webgpu", "--ignore-gpu-blocklist",
            "--enable-gpu-rasterization", "--js-flags=--max-old-space-size=8192"]
    if a.webgl:
        args += ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"]
    p = subprocess.Popen(args + ["about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    console = []
    shots = 0
    try:
        for _ in range(100):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{a.port}/json"))
                break
            except OSError:
                time.sleep(0.2)
        tab = next(t for t in tabs if t.get("type") == "page")
        ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=60, suppress_origin=True)
        n = [0]
        pending = {}

        def send(method, **params):
            n[0] += 1
            ws.send(json.dumps({"id": n[0], "method": method, "params": params}))
            return n[0]

        def handle(m):
            meth = m.get("method")
            if meth == "Runtime.consoleAPICalled":
                text = " ".join(str(x.get("value", x.get("description", ""))) for x in m["params"]["args"])
                console.append(f"[{m['params']['type']}] {text[:2000]}")
            elif meth == "Runtime.exceptionThrown":
                ed = m["params"]["exceptionDetails"]
                console.append("EXCEPTION: " + (ed.get("exception", {}).get("description") or ed.get("text", ""))[:2000])
            elif meth == "Log.entryAdded":
                e = m["params"]["entry"]
                console.append(f"[log.{e['level']}] {e['text'][:2000]}")
            elif "id" in m and m["id"] in pending:
                pending[m["id"]](m)

        send("Runtime.enable")
        send("Log.enable")
        send("Page.enable")
        t0 = time.time()
        send("Page.navigate", url=a.url)
        todo = [(s, "shot", None) for s in secs] + [(t, k, c) for t, k, c in events]
        todo.sort(key=lambda x: x[0])
        ws.settimeout(0.2)
        while time.time() - t0 < total:
            now = time.time() - t0
            while todo and todo[0][0] <= now:
                t, kind, code = todo.pop(0)
                if kind == "shot":
                    label = f"{t:g}"

                    def save(m, label=label):
                        nonlocal shots
                        data = m.get("result", {}).get("data")
                        if data:
                            with open(os.path.join(a.out, f"shot_{label}.png"), "wb") as f:
                                f.write(base64.b64decode(data))
                            shots += 1
                    pending[send("Page.captureScreenshot", format="png")] = save
                else:
                    key, vk = key_info(code)
                    send("Input.dispatchKeyEvent", type=kind, code=code, key=key, windowsVirtualKeyCode=vk)
            try:
                handle(json.loads(ws.recv()))
            except websocket.WebSocketTimeoutException:
                pass
        ws.settimeout(10)
        deadline = time.time() + 10
        while pending and shots < len(secs) and time.time() < deadline:
            try:
                handle(json.loads(ws.recv()))
            except websocket.WebSocketTimeoutException:
                break
    finally:
        p.kill()
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        shutil.rmtree(prof, ignore_errors=True)
        with open(os.path.join(a.out, "console.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(console))
    print(f"{shots} screenshots, {len(console)} console lines -> {a.out}")


if __name__ == "__main__":
    main()
