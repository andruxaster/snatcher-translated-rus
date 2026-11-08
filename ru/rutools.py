"""Russian translation workflow for the PlayStation port.

    python ru/rutools.py export            # work/ru/tasks/<S>.json, one per bank
    python ru/rutools.py validate B010 ... # check work/ru/out/<S>/*.json
    python ru/rutools.py validate --all
    python ru/rutools.py merge [--all | B010 ...]
                                           # write the Russian into ps1/translation

A task file lists every string of a bank that the English build writes (the
script strings of ISZ_<S>.json and the subtitle cues of subs_<S>.json), with
the Japanese of the script strings from work/ref (built from your own disc;
it never enters the repository). Translators write work/ru/out/<S>/*.json:
plain JSON objects {id: russian}, any number of part files.

`merge` writes the Russian into the translation files in place of the
English, keeping the English beside it (`en_src`, `long_src`) the first
time. A script string that fits its slot goes into `en`; one that does not
goes into `long` (relocated at build time by ps1/tools/repoint.py) with a
shortened `en` kept in the slot. Soft line breaks are recomputed afterwards
by ps1/tools/rewrap.py (see ru/build_ru.sh).
"""
import argparse, glob, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path[:0] = [os.path.join(ROOT, d) for d in ("lib", "ps1/tools", "ps1/subs")]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from textcodec import is_narrow, char_to_code

TR = os.path.join(ROOT, "ps1", "translation")
REF = os.path.join(ROOT, "work", "ref")
RUW = os.path.join(ROOT, "work", "ru")
TASKS = os.path.join(RUW, "tasks")
OUT = os.path.join(RUW, "out")

BANKS = [f"B{n:03X}" for n in range(0, 0x270, 0x10)]
COLOURS = "青赤紫緑水黄白桃Ｃ"
MARKS = "▽★☆○●◆◇■□△▲※"
TERMINAL = ("B030", "B040")

NORMALIZE = {"«": '"', "»": '"', "“": '"', "”": '"', "„": '"', "‘": "'", "’": "'",
             "—": "-", "–": "-", "…": "...", " ": " ", "№": "No."}


def normalize(s):
    for a, b in NORMALIZE.items():
        s = s.replace(a, b)
    s = re.sub(r" {2,}", " ", s)
    return s.strip(" ")


def colour_codes(s):
    return re.findall("＠(.)", s)


def fw_latin_tokens(s):
    return sorted(re.findall("[Ａ-Ｚ０-９]+(?:以外)?", s))


def ideal_bytes(s):
    """Encoded size once every pair has a glyph (pairfont.encode), + null."""
    n, run = 1, 0
    for ch in s:
        if is_narrow(ch):
            run += 1
        else:
            n += 2 * ((run + 1) // 2) + 2
            run = 0
    return n + 2 * ((run + 1) // 2)


def load(p):
    return json.load(open(p, encoding="utf-8"))


def dump(obj, p):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    nl = "\n"
    if os.path.exists(p) and b"\r\n" in open(p, "rb").read(4096):
        nl = "\r\n"                      # the tree is stored byte for byte
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write((json.dumps(obj, ensure_ascii=False, indent=1) + "\n").replace("\n", nl))


def src_text(e):
    """The English a translator works from (the full form)."""
    return e.get("long_src") or e.get("en_src") or e.get("long") or e.get("en") or ""


def isz_items(bank):
    p = os.path.join(TR, f"ISZ_{bank}.json")
    if not os.path.exists(p):
        return []
    spec = load(p)
    ref = {}
    rp = os.path.join(REF, f"ISZ_{bank}.json")
    if os.path.exists(rp):
        ref = {e["off"]: e.get("jp", "") for e in load(rp)["strings"]}
    from lock_data_strings import PUZZLE_TARGETS
    puzzles = PUZZLE_TARGETS.get(f"ISZ_{bank}.json", {})
    items = []
    for spec_idx, e in enumerate(spec["strings"]):
        if "lock" in e or spec_idx in puzzles:   # engine data / typed-puzzle answers
            continue
        en = src_text(e)
        if not en:
            continue
        it = {"id": f"I{e['off']}", "jp": ref.get(e["off"], ""), "en": en}
        if bank in TERMINAL and en.startswith("＠緑"):
            it["note"] = "терминал Гауди: строки по 14 ячеек (28 букв)"
        has_long = bool(e.get("long_src") or e.get("long"))
        if not has_long and e["budget"] <= 24 and "￥" not in en:
            it["max"] = max(e["budget"] - 1, len(en))
        items.append(it)
    return items


def subs_items(bank):
    p = os.path.join(TR, f"subs_{bank}.json")
    if not os.path.exists(p):
        return []
    spec = load(p)
    rows = spec.get("options", {}).get("rows", 3)
    items = []
    for c in spec["cues"]:
        en = c.get("en_src") or c.get("en")
        if not en or not c.get("enabled", True):
            continue
        it = {"id": f"S{c['id']}", "speaker": c.get("speaker", ""), "en": en,
              "sub": f"субтитр: не больше {rows} строк по 24 знака"}
        items.append(it)
    return items


def cmd_export(a):
    os.makedirs(TASKS, exist_ok=True)
    total = 0
    for b in BANKS + ["INTRO"]:
        items = isz_items(b) + subs_items(b)
        if not items:
            continue
        dump({"bank": b, "items": items}, os.path.join(TASKS, f"{b}.json"))
        n = sum(len(i["en"]) for i in items)
        total += n
        print(f"{b}: {len(items)} items, {n} chars")
    print("total chars", total)


def collect(bank):
    out = {}
    for p in sorted(glob.glob(os.path.join(OUT, bank, "*.json"))):
        try:
            d = load(p)
        except Exception as ex:
            print(f"{bank}: {os.path.basename(p)}: BAD JSON {ex}")
            continue
        out.update(d)
    return out


def check_item(bank, it, ru, opts):
    """Return (errors, warnings) for one translated item."""
    err, warn = [], []
    en = it["en"]
    t = normalize(ru)
    if not t.strip():
        return ["пусто"], []
    if it["id"].startswith("S"):
        from consolidate import fits, wrap
        if any(ch in t for ch in "￥＠"):
            err.append("в субтитре не должно быть ￥ или ＠")
        rows = opts.get("rows", 3)
        cols = min(opts.get("cols", 18), 18)
        widths = {cols, 18} if opts.get("faceleft") else {18}
        if not fits(t, rows, widths):
            err.append(f"не помещается в субтитр ({rows} строки по {cols * 2} знака): "
                       f"{' | '.join(wrap(t, cols))}")
    else:
        if colour_codes(t) != colour_codes(en):
            err.append(f"цветовые коды {colour_codes(en)} -> {colour_codes(t)}")
        if fw_latin_tokens(t) != fw_latin_tokens(en):
            err.append(f"полноширинные токены {fw_latin_tokens(en)} -> {fw_latin_tokens(t)}")
        for m in MARKS:
            if en.count(m) != t.count(m):
                warn.append(f"знак {m}: {en.count(m)} -> {t.count(m)}")
        if "max" in it and len(t) > it["max"]:
            err.append(f"длиннее {it['max']} знаков ({len(t)})")
    for ch in set(t):
        if is_narrow(ch) or ch in "￥＠" or ch in COLOURS or ch in MARKS:
            continue
        if ch in en:
            continue
        if char_to_code(ch) is None:
            err.append(f"символ {ch!r} не кодируется")
        else:
            warn.append(f"полноширинный символ {ch!r}")
    latin = re.findall(r"[A-Za-z]{3,}", re.sub("＠.", " ", t))
    if latin:
        allowed = {"ID", "TV", "DNA", "UV", "CIA", "FBI", "UN", "OK", "HQ", "LSD", "PDD", "LCD",
                   "PlayStation", "Konami", "KONAMI", "TwinBee", "Gradius", "STBO", "BGM", "SE", "TEL"}
        odd = [w for w in latin if w not in allowed and w.upper() != w]
        if odd:
            warn.append(f"латиница: {' '.join(odd[:6])}")
    return err, warn


def bank_opts(bank):
    p = os.path.join(TR, f"subs_{bank}.json")
    return load(p).get("options", {}) if os.path.exists(p) else {}


def cmd_validate(a):
    banks = BANKS + ["INTRO"] if a.all else a.banks
    bad = 0
    for b in banks:
        tp = os.path.join(TASKS, f"{b}.json")
        if not os.path.exists(tp):
            continue
        items = load(tp)["items"]
        got = collect(b)
        if not got and a.all:
            continue
        opts = bank_opts(b)
        ids = {i["id"] for i in items}
        missing = [i["id"] for i in items if i["id"] not in got]
        extra = [k for k in got if k not in ids]
        ne = nw = 0
        for it in items:
            if it["id"] not in got:
                continue
            err, warn = check_item(b, it, got[it["id"]], opts)
            for m in err:
                print(f"{b} {it['id']}: ERROR {m}")
            if a.warn:
                for m in warn:
                    print(f"{b} {it['id']}: warn {m}")
            ne += len(err)
            nw += len(warn)
        if extra:
            print(f"{b}: unknown ids {extra[:10]}")
        print(f"== {b}: {len(got)}/{len(items)} translated, {len(missing)} missing, "
              f"{ne} errors, {nw} warnings")
        if a.missing and missing:
            print("   missing:", " ".join(missing[:40]))
        bad += ne + len(extra)
    sys.exit(1 if bad else 0)


def cmd_merge(a):
    """Russian -> en/long. Each script string is broken into rows the way
    ps1/tools/rewrap.py does it for the English (greedy at 18 cells, 14 on
    Gaudi's terminal), so every row starts on a pair boundary. It stays in
    its slot when it fits; otherwise it rides a `long` and the slot keeps
    a three-dot stub (never shown: the remap reads the long). Run again
    after ps1/tools/rebuild_pairs.py - the fit depends on the pair table."""
    import rewrap
    from pairfont import PairFont
    pf = PairFont()
    rewrap.TABLE = pf.table
    banks = BANKS + ["INTRO"] if a.all or not a.banks else a.banks

    def size(s):
        try:
            return len(pf.encode(s)) + 1
        except Exception:
            return 10 ** 6

    from lock_data_strings import PUZZLE_TARGETS
    stats = {"slot": 0, "soft": 0, "long": 0, "kept": 0}
    for b in banks:
        got = {k: normalize(v) for k, v in collect(b).items()}
        if not got:
            continue
        n = 0
        p = os.path.join(TR, f"ISZ_{b}.json")
        if os.path.exists(p):
            spec = load(p)
            puzzles = PUZZLE_TARGETS.get(f"ISZ_{b}.json", {})
            for idx, e in enumerate(spec["strings"]):
                k = f"I{e['off']}"
                if k not in got or "lock" in e:
                    continue
                if idx in puzzles or got[k] == normalize(src_text(e)):
                    # typed-puzzle data and lines left as they were: the
                    # English record exactly as it was
                    if "en_src" in e:
                        e["en"] = e.pop("en_src")
                        if "long_src" in e:
                            e["long"] = e.pop("long_src")
                        else:
                            e.pop("long", None)
                        e.pop("ru", None)
                    stats["kept"] += 1
                    continue
                if "en_src" not in e:
                    e["en_src"] = e.get("en", "")
                    if e.get("long"):
                        e["long_src"] = e["long"]
                ru = got[k]
                width = 14 if b in TERMINAL and ru.startswith("＠緑") else 18
                wrapped = rewrap.rewrap(ru, width) or ru
                soft = rewrap.rewrap(wrapped, 10 ** 6) or wrapped
                e.pop("long", None)
                if size(wrapped) <= e["budget"]:
                    e["en"] = wrapped
                    stats["slot"] += 1
                elif size(soft) <= e["budget"]:
                    e["en"] = soft              # the runtime wrap breaks it
                    stats["soft"] += 1
                else:
                    e["en"] = "."               # 2 bytes + null: fits any slot
                    e["long"] = wrapped
                    stats["long"] += 1
                e["ru"] = True
                n += 1
            dump(spec, p)
        p = os.path.join(TR, f"subs_{b}.json")
        if os.path.exists(p):
            spec = load(p)
            for c in spec["cues"]:
                k = f"S{c['id']}"
                if k not in got:
                    continue
                if "en_src" not in c:
                    c["en_src"] = c.get("en", "")
                c["en"] = got[k]
                n += 1
            dump(spec, p)
        print(f"{b}: merged {n}")
    print(stats)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("export")
    v = sp.add_parser("validate")
    v.add_argument("banks", nargs="*")
    v.add_argument("--all", action="store_true")
    v.add_argument("--warn", action="store_true")
    v.add_argument("--missing", action="store_true")
    m = sp.add_parser("merge")
    m.add_argument("banks", nargs="*")
    m.add_argument("--all", action="store_true")
    a = ap.parse_args()
    {"export": cmd_export, "validate": cmd_validate, "merge": cmd_merge}[a.cmd](a)
