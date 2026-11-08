#!/usr/bin/env python3
"""Build the Russian translation of Snatcher (PlayStation, SLPS-00154), uncensored.

    python build.py doctor                 what is installed, which discs are in place
    python build.py discs PATH [PATH...]   copy your dumps into discs/ (files, folders or .zip)
    python build.py ps1 [--no-fmv] [--release]

Discs (your own dumps, redump.org BIN/CUE layout; never committed):
  discs/iso_ps1_jp/     Snatcher (Japan).bin + .cue                  PlayStation, SLPS-00154 (required)
  discs/iso_saturn_jp/  Snatcher (Japan) (Track 1|2|3).bin + .cue   Saturn, T-9508G (optional)

The image is the uncensored one: the factory-ruins corpse and the maggot-covered
body come from art left on the PS1 disc itself; the locker-room picture comes
from the Saturn disc, and stays as the PS1 shows it when no Saturn dump is given.

Outputs: patched/Snatcher (Japan).bin + .cue; with --release also
release/Snatcher-PS1-RU-v<ver>.zip (xdelta patch, cue, README.txt).

Tools: Python 3.10+ with numpy, Pillow and capstone (opencv-python and scipy for
the intro movie's first build), xdelta3 for --release, Java 8+ for the intro
movie (jPSXdec is fetched into lib/jpsxdec/), the TrueType fonts in lib/sysfont.py.
"""
import argparse, hashlib, json, os, shutil, subprocess, sys, time, urllib.request, zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(ROOT, "work")
DISCS = os.path.join(ROOT, "discs")
PATCHED = os.path.join(ROOT, "patched")
RELEASE = os.path.join(ROOT, "release")
sys.path[:0] = [os.path.join(ROOT, d) for d in ("lib",)]

PY = sys.executable
JPSXDEC_URL = "https://github.com/m35/jpsxdec/releases/download/v2.0/jpsxdec_v2.0.zip"
JPSXDEC_JAR = os.path.join(ROOT, "lib", "jpsxdec", "jpsxdec_v2.0", "jpsxdec.jar")
XDELTA_URL = "https://github.com/jmacd/xdelta-gpl/releases/download/v3.1.0/xdelta3-3.1.0-x86_64.exe.zip"

PS1_DIR = os.path.join(DISCS, "iso_ps1_jp")
PS1_BIN = os.path.join(PS1_DIR, "Snatcher (Japan).bin")
PS1_SHA1 = "e6cd330feb594b3951089da866db1a400f0173f6"
SAT_DIR = os.path.join(DISCS, "iso_saturn_jp")
SAT_TRACKS = [os.path.join(SAT_DIR, f"Snatcher (Japan) (Track {n}).bin") for n in (1, 2, 3)]
SAT_SHA1 = "a3ebab5b07a2b9a17aa68554072585be8839aba3"          # track 1
SAT_LISA_PNG = os.path.join(WORK, "saturn", "sat_433.png")

PS1_SCENES = ["INTRO"] + [f"B{n:02X}0" for n in range(0x00, 0x27)]
IMG = "Snatcher (Japan)"
RU_VERSION = open(os.path.join(ROOT, "ru", "VERSION")).read().strip()


def log(msg):
    print(f"\n=== {msg}", flush=True)


def run(args, env=None, check=True):
    """A chain step: python scripts by path, from the repo root, stop on failure."""
    if args and args[0].endswith(".py"):
        args = [PY] + args
    e = dict(os.environ)
    e.setdefault("PYTHONIOENCODING", "utf-8")
    if env:
        for k, v in env.items():
            if v is None:
                e.pop(k, None)
            else:
                e[k] = v
    print("+ " + " ".join(f'"{a}"' if " " in a else a for a in args), flush=True)
    r = subprocess.run(args, cwd=ROOT, env=e)
    if check and r.returncode:
        sys.exit(f"build step failed (exit {r.returncode}): {' '.join(args)}")
    return r.returncode


def sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 22):
            h.update(chunk)
    return h.hexdigest()


def verified(path, want):
    """SHA1 check, remembered per (size, mtime) in work/verified.json."""
    cache_path = os.path.join(WORK, "verified.json")
    cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
    st = os.stat(path)
    key = f"{os.path.relpath(path, ROOT)}|{st.st_size}|{int(st.st_mtime)}"
    if cache.get(key) == want:
        return True
    print(f"checking {os.path.relpath(path, ROOT)} ...", flush=True)
    got = sha1(path)
    if got != want:
        return False
    cache[key] = want
    os.makedirs(WORK, exist_ok=True)
    json.dump(cache, open(cache_path, "w"), indent=1)
    return True


class keep:
    """Snapshot files a preparation tool rewrites as a side effect (committed
    data), and put them back after it: dump_strings.py rewrites
    ps1/translation/ISZ_*.json, satcarry.py saturn/translation/SAT_*.json,
    extract_ps1.py work/lba_map.json."""

    def __init__(self, *paths):
        self.paths = paths
        self.saved = {}

    def __enter__(self):
        for p in self.paths:
            full = os.path.join(ROOT, p)
            files = [full] if os.path.isfile(full) else [
                os.path.join(d, f) for d, _, fs in os.walk(full) for f in fs] if os.path.isdir(full) else []
            for f in files:
                self.saved[f] = open(f, "rb").read()

    def __exit__(self, *exc):
        for f, data in self.saved.items():
            if not os.path.exists(f) or open(f, "rb").read() != data:
                open(f, "wb").write(data)


# --- tools --------------------------------------------------------------------

def tool(name, required=True):
    """xdelta3 / chdman: lib/<name>/<name>.exe on Windows, else PATH."""
    exe = os.path.join(ROOT, "lib", {"xdelta3": "xdelta"}.get(name, name), name + ".exe")
    if os.name == "nt" and os.path.exists(exe):
        return exe
    found = shutil.which(name)
    if not found and required and os.name == "nt" and name == "xdelta3":
        fetch_xdelta()
        return exe
    if not found and required:
        sys.exit(f"{name} not found on PATH (Debian/Ubuntu: apt install {'xdelta3' if name == 'xdelta3' else 'mame-tools'})")
    return found


def download(url, dest):
    print(f"downloading {url}", flush=True)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with urllib.request.urlopen(url) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def fetch_xdelta():
    """Windows: the official xdelta3 build into lib/xdelta/xdelta3.exe."""
    d = os.path.join(ROOT, "lib", "xdelta")
    z = os.path.join(d, "xdelta3.zip")
    download(XDELTA_URL, z)
    with zipfile.ZipFile(z) as zf:
        member = next(n for n in zf.namelist() if n.lower().endswith(".exe"))
        with zf.open(member) as src, open(os.path.join(d, "xdelta3.exe"), "wb") as dst:
            shutil.copyfileobj(src, dst)
    os.remove(z)


def ensure_jpsxdec():
    if os.path.exists(JPSXDEC_JAR):
        return
    base = os.path.dirname(os.path.dirname(JPSXDEC_JAR))      # lib/jpsxdec; the zip holds jpsxdec_v2.0/
    z = os.path.join(base, "jpsxdec.zip")
    download(JPSXDEC_URL, z)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(base)
    if not os.path.exists(JPSXDEC_JAR):
        sys.exit(f"jPSXdec: {JPSXDEC_JAR} not in {JPSXDEC_URL}")


# --- discs --------------------------------------------------------------------

def cmd_discs(paths):
    """Copy dumps into discs/, by file name: a folder or .zip is searched."""
    want = {os.path.basename(PS1_BIN): PS1_DIR}
    for t in SAT_TRACKS:
        want[os.path.basename(t)] = SAT_DIR
    found = 0

    def place(base, dest, read):
        nonlocal found
        os.makedirs(dest, exist_ok=True)
        with open(os.path.join(dest, base), "wb") as dst:
            read(dst)
        print(f"{base} -> {os.path.relpath(dest, ROOT)}")
        found += 1

    for p in paths:
        p = os.path.abspath(p)
        if p.lower().endswith(".zip"):
            with zipfile.ZipFile(p) as zf:
                names = zf.namelist()
                sat = any("(Track 1).bin" in n for n in names)
                for n in names:
                    base = os.path.basename(n)
                    dest = (SAT_DIR if sat else PS1_DIR) if base == "Snatcher (Japan).cue" else want.get(base)
                    if dest:
                        place(base, dest, lambda dst, n=n: shutil.copyfileobj(zf.open(n), dst))
            continue
        files = [p] if os.path.isfile(p) else [os.path.join(dp, f) for dp, _, fs in os.walk(p) for f in fs]
        sat = any(f.endswith("(Track 1).bin") for f in files)
        for f in files:
            base = os.path.basename(f)
            dest = (SAT_DIR if sat else PS1_DIR) if base == "Snatcher (Japan).cue" else want.get(base)
            if not dest or os.path.abspath(os.path.join(dest, base)) == f:
                continue
            place(base, dest, lambda dst, f=f: shutil.copyfileobj(open(f, "rb"), dst))
    if not found:
        sys.exit("no Snatcher dump files found (names must be the redump ones)")
    cmd_doctor(fonts=False)


def have_saturn():
    return all(os.path.exists(t) for t in SAT_TRACKS) or os.path.exists(SAT_LISA_PNG)


def cmd_doctor(fonts=True):
    ok = True
    log("Python")
    print(f"  {sys.version.split()[0]} at {PY}")
    for mod, need in (("numpy", "all"), ("PIL", "all"), ("capstone", "all"),
                      ("cv2", "intro movie, first build"), ("scipy", "intro movie, first build")):
        try:
            __import__(mod)
            print(f"  {mod:<8} ok")
        except ImportError:
            print(f"  {mod:<8} MISSING ({need})")
            ok &= need != "all"
    log("Tools")
    for name, need in (("xdelta3", "--release"), ("java", "intro movie")):
        p = tool(name, required=False) if name != "java" else shutil.which("java")
        print(f"  {name:<8} {p or 'MISSING (' + need + ')'}")
    print(f"  jPSXdec  {JPSXDEC_JAR if os.path.exists(JPSXDEC_JAR) else 'fetched on first build'}")
    if fonts:
        log("Fonts (lib/sysfont.py)")
        import sysfont
        ok &= sysfont.report() == 0
    log("Discs")
    if not os.path.exists(PS1_BIN):
        print(f"  PlayStation  missing: {os.path.relpath(PS1_BIN, ROOT)}")
        ok = False
    else:
        print(f"  PlayStation  {'ok' if verified(PS1_BIN, PS1_SHA1) else 'WRONG DUMP (SHA1)'}")
    if os.path.exists(SAT_TRACKS[0]):
        print(f"  Saturn       {'ok' if verified(SAT_TRACKS[0], SAT_SHA1) else 'WRONG DUMP (SHA1)'}")
    else:
        print("  Saturn       not given (optional: the locker-room picture stays censored)")
    return ok


def need_ps1():
    if not os.path.exists(PS1_BIN):
        sys.exit(f"PlayStation disc missing: {os.path.relpath(PS1_BIN, ROOT)} (+ .cue) - see `build.py discs`")
    if not verified(PS1_BIN, PS1_SHA1):
        sys.exit(f"{PS1_BIN} is not the redump dump (SHA1 {PS1_SHA1})")


# --- preparation --------------------------------------------------------------

def prep_ps1():
    """Extracted files, the Snatcher art the boot screens borrow, the text refs."""
    need_ps1()
    if not os.path.exists(os.path.join(DISCS, "extracted_ps1", "SLPS_001.54")):
        log("PS1: extracting the disc")
        with keep("work/lba_map.json"):
            run(["ps1/tools/extract_ps1.py"])
    parts = os.path.join(WORK, "gfx", "all", "CXE_B0D0_items", "CXE_B0D0_g1_00_8bpp.png")
    if not os.path.exists(parts):
        log("PS1: rendering CXE_B0D0 (the boot screens' Snatcher)")
        d = os.path.join(WORK, "gfx", "all")
        os.makedirs(d, exist_ok=True)
        shutil.copyfile(os.path.join(DISCS, "extracted_ps1", "DES", "CXE", "CXE_B0D0.BIN"),
                        os.path.join(d, "CXE_B0D0.BIN"))
        run(["ps1/tools/gfx.py", "render", os.path.join(d, "CXE_B0D0.BIN")])
        if not os.path.exists(parts):
            sys.exit(f"gfx.py render did not write {parts}")
    if not os.path.exists(os.path.join(WORK, "ref", "ISZ_B260.json")):
        log("PS1: the Japanese text references (work/ref)")
        with keep("ps1/translation"):
            run(["ps1/tools/dump_strings.py"])


def prep_saturn_picture():
    """The one Saturn picture the uncensored image uses (DATA.BIN chunk 433)."""
    if os.path.exists(SAT_LISA_PNG):
        return
    for t in SAT_TRACKS:
        if not os.path.exists(t):
            sys.exit(f"Saturn disc incomplete: {os.path.relpath(t, ROOT)} missing")
    if not verified(SAT_TRACKS[0], SAT_SHA1):
        sys.exit(f"{SAT_TRACKS[0]} is not the redump dump (SHA1 {SAT_SHA1})")
    if not os.path.exists(os.path.join(DISCS, "extracted_saturn", "DATA.BIN")):
        log("Saturn: extracting the disc (for one picture)")
        run(["ps1/tools/sat_extract.py"])


# --- PlayStation --------------------------------------------------------------

def ps1_chain(lisa):
    """The translated, uncensored image."""
    run(["ps1/tools/check_strings.py", "--all", "--quiet"], check=False)
    for step in (["apply_translation.py"], ["keytable.py", "apply"], ["repoint.py"],
                 ["patch_keyboard.py"], ["kbdfaces.py", "apply"], ["specialmenu.py", "apply"],
                 ["specialitem.py", "apply"], ["gfxpages.py", "apply"], ["gfxlabels.py", "apply"],
                 ["disclaimer.py", "apply"], ["staffroll.py", "apply"], ["introcaption.py", "apply"],
                 ["introdiagram.py", "apply"]):
        run(["ps1/tools/" + step[0]] + step[1:])
    for s in PS1_SCENES:
        run(["ps1/subs/subs_cue.py", "on", f"ps1/translation/subs_{s}.json", "--scene", s])
    run(["ps1/tools/uncensor.py"] + (["--lisa-saturn"] if lisa else []))
    for step in (["wordwrap.py", "apply"], ["pageplate.py", "apply"], ["bootcard.py", "apply"],
                 ["patch_disc.py"]):
        run(["ps1/tools/" + step[0]] + step[1:])


def ps1_fmv(image_env):
    """The intro movie's English credits: frames repainted once (cached in
    work/gfx/str/out), re-encoded into the image by jPSXdec."""
    ensure_jpsxdec()
    if not shutil.which("java"):
        sys.exit("java not found: the PS1 intro movie needs it (or build with --no-fmv)")
    out = os.path.join(WORK, "gfx", "str", "out")
    if not (os.path.isdir(out) and any(n.endswith(".png") for n in os.listdir(out))):
        log("PS1: repainting the intro movie's frames (once; needs opencv-python and scipy)")
        run(["ps1/tools/fmvtext.py", "frames"], env=image_env)
        run(["ps1/tools/fmvtext.py", "build"], env=image_env)
    run(["ps1/tools/fmvtext.py", "apply"], env=image_env)


def cmd_ps1(a):
    prep_ps1()
    lisa = have_saturn()
    if lisa:
        prep_saturn_picture()
    else:
        log("no Saturn dump: the locker-room picture stays as the PS1 shows it")
    os.environ["SNATCHER_IMAGE"] = IMG             # patch_disc.py and fmvtext.py read it
    bin_path = os.path.join(PATCHED, IMG + ".bin")
    if os.path.exists(bin_path):
        os.remove(bin_path)              # patch_disc copies pristine only when the image is absent
    log(f"PS1: building patched/{IMG}.bin (Russian, uncensored)")
    ps1_chain(lisa)
    if not a.no_fmv:
        ps1_fmv({"SNATCHER_IMAGE": IMG})
    if a.release:
        release(lisa)


def release(lisa):
    """release/Snatcher-PS1-RU-v<ver>.zip: the xdelta patch, a cue, README.txt."""
    log("PS1: the release")
    x = tool("xdelta3")
    os.makedirs(RELEASE, exist_ok=True)
    name = f"Snatcher (Japan) [T-Ru v{RU_VERSION}]"
    patch = os.path.join(RELEASE, name + ".xdelta")
    run([x, "-e", "-9", "-f", "-s", PS1_BIN, os.path.join(PATCHED, IMG + ".bin"), patch])
    out_sha1 = sha1(os.path.join(PATCHED, IMG + ".bin"))
    readme = open(os.path.join(ROOT, "ru", "RELEASE_README.txt"), encoding="utf-8").read().format(
        version=RU_VERSION, name=name, src_sha1=PS1_SHA1, out_sha1=out_sha1,
        lisa="да" if lisa else "нет (собрано без диска Saturn)")
    cue = f'FILE "{name}.bin" BINARY\r\n  TRACK 01 MODE2/2352\r\n    INDEX 01 00:00:00\r\n'
    z = os.path.join(RELEASE, f"Snatcher-PS1-RU-v{RU_VERSION}.zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(patch, os.path.basename(patch))
        zf.writestr(name + ".cue", cue)
        zf.writestr("README.txt", readme.replace("\n", "\r\n"))
    print(f"{os.path.relpath(z, ROOT)}  (patched image SHA1 {out_sha1})")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    sub.add_parser("fetch", help="download jPSXdec (and xdelta3.exe on Windows) into lib/")
    p = sub.add_parser("discs")
    p.add_argument("paths", nargs="+")
    p = sub.add_parser("ps1")
    p.add_argument("--release", action="store_true", help="also make the xdelta patch and the zip")
    p.add_argument("--no-fmv", action="store_true", help="skip the intro movie (faster test builds)")
    a = ap.parse_args()
    t0 = time.time()
    if a.cmd == "doctor":
        sys.exit(0 if cmd_doctor() else 1)
    if a.cmd == "discs":
        return cmd_discs(a.paths)
    if a.cmd == "fetch":
        if os.name == "nt" and not os.path.exists(os.path.join(ROOT, "lib", "xdelta", "xdelta3.exe")):
            fetch_xdelta()
        ensure_jpsxdec()
        return
    cmd_ps1(a)
    log(f"done in {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
