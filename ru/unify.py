"""Make the parallel translators' output consistent (work/ru/out, in place).

1. Menu labels (task items with a `max`): one Russian label per English
   label, PREFERRED below when it fits the item's limit, else the most
   common variant that fits.
2. Terms the translators spelled differently, by regular expression.

    python ru/unify.py          # report
    python ru/unify.py --write
"""
import collections, glob, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(ROOT, "work", "ru", "out")
TASKS = os.path.join(ROOT, "work", "ru", "tasks")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# English label -> preferred Russian labels, best first
PREFERRED = {
    # Menu labels may be longer than their slot: like the English ("Check" ->
    # "Investigate"), a label that does not fit rides a `long`. The verb menu
    # takes 14 letters ("Shooting range"), so full words, no abbreviations.
    "Look": ["Осмотреть"], "Ask": ["Спросить"], "Talk": ["Говорить"],
    "Item": ["Предметы"], "Move": ["Идти"], "Use": ["Использовать"],
    "Show": ["Показать"], "Investigate": ["Изучить"], "Funds": ["Деньги"],
    "Give candy": ["Угостить"], "Call": ["Позвать"], "Back": ["Назад"],
    "Use Metal Gear": ["Позвать Метала"], "Use Gaudi": ["Спросить Гауди"],
    "JUNKER ID": ["Удостоверение"], "Around": ["Вокруг"],
    "Sunblock": ["Защитный крем"], "Disk": ["Диск"],
    "Outer Heaven": ['"Аутер Хэвен"'], "Joy Division": ['"Джой Дивижн"'],
    "Altamira": ['"Альтамира"'], "Snatchers": ["Снатчеры"],
    "Computer": ["Компьютер"], "Computer room": ["Компьютерная"],
    "Front Pod": ["Стойка-капсула"], "Hair": ["Волосы"],
    **{f"Hair {i}": [f"Волосы {i}"] for i in range(1, 7)},
    "Snow cedar": ["Снежный кедр"], "Knock": ["Стучать"], "Sneeze": ["Чихать"],
    "Train": ["Тренировка"], "Black taxi": ["Бомбила"], "Montage": ["Фоторобот"],
    "Answer": ["Ответить"], "Liquid Sky": ['"Ликвид Скай"'],
    "Roof": ["Крыша"], "Door": ["Дверь"], "Work": ["Работа"], "Zoo": ["Зоопарк"],
    "Drug": ["Наркотик"], "Map": ["Карта"], "Peek": ["Подсмотреть"],
    "Take": ["Взять"], "Age": ["Возраст"], "Duct": ["Вентиляция"],
    "Hit wall": ["Удар в стену"], "Body": ["Кузов"], "Dancer": ["Танцовщица"],
    "Exit": ["Выход"], "Feet": ["Под ногами"], "Dirt": ["Грязь"],
    "Yell": ["Крикнуть"], "Cold": ["Простуда"],
}
MENU_MAX = 14

# (pattern, replacement) over every translated line
TERMS = [
    (r"Жидкое небо|Жидкого неба|Жидким небом|Жидкому небу|Жидком небе|Ликвид скай", "Ликвид Скай"),
    (r"Би Ленд|Би-Лэнд|Би Лэнд", "Би-Ленд"),
    (r"сонограф(а|ом|е|у|ы|ов)?\b", lambda m: "дрим-кодер" + (m.group(1) or "")),
    (r"Сонограф(а|ом|е|у|ы|ов)?\b", lambda m: "Дрим-кодер" + (m.group(1) or "")),
    (r"Домитль\b", "Домитл"),
]


def main():
    write = "--write" in sys.argv
    parts = {}
    for p in glob.glob(os.path.join(OUT, "*", "*.json")):
        parts[p] = json.load(open(p, encoding="utf-8"))
    where = {}                        # (bank, id) -> part path
    for p, d in parts.items():
        b = os.path.basename(os.path.dirname(p))
        for k in d:
            where[(b, k)] = p
    labels = collections.defaultdict(list)    # en -> [(bank, id, max)]
    variants = collections.defaultdict(collections.Counter)
    for tp in glob.glob(os.path.join(TASKS, "*.json")):
        b = os.path.basename(tp)[:-5]
        for it in json.load(open(tp, encoding="utf-8"))["items"]:
            if "max" in it and (b, it["id"]) in where:
                labels[it["en"]].append((b, it["id"], it["max"]))
                variants[it["en"]][parts[where[(b, it["id"])]][it["id"]]] += 1
    changed = 0
    for en, uses in labels.items():
        if en not in PREFERRED:           # replies and one-off labels read
            continue                      # in context: left as translated
        for b, k, mx in uses:
            p = where[(b, k)]
            cur = parts[p][k]
            pick = next((r for r in PREFERRED.get(en, []) if len(r) <= MENU_MAX), None)
            if pick is None:
                pick = cur
            if pick != cur:
                print(f"label {b} {k} {en!r}: {cur!r} -> {pick!r}")
                parts[p][k] = pick
                changed += 1
    for p, d in parts.items():
        for k, v in d.items():
            n = v
            for pat, rep in TERMS:
                n = re.sub(pat, rep, n)
            if n != v:
                print(f"term {os.path.basename(os.path.dirname(p))} {k}: {v[:70]!r} -> {n[:70]!r}")
                d[k] = n
                changed += 1
    print(f"{changed} changes")
    if write:
        for p, d in parts.items():
            with open(p, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
