# Сборка патча из исходников

`build.py` собирает русский uncensored-образ PlayStation-версии из ваших
собственных образов дисков, а с `--release` — xdelta-патч и архив для
публикации. Данных игры в репозитории нет.

## Что нужно

| Диск | Файлы | Зачем |
|---|---|---|
| Snatcher (Japan), PlayStation, SLPS-00154 | `Snatcher (Japan).bin` + `.cue` | обязательно |
| Snatcher (Japan), Saturn, T-9508G | `Snatcher (Japan) (Track 1).bin`, `(Track 2)`, `(Track 3)` + `.cue` | по желанию: одна картинка (снатчер в раздевалке) берётся отсюда; без диска Saturn она остаётся цензурированной |

Программы:

- Python 3.10+ и пакеты из `requirements.txt` (numpy, Pillow, capstone;
  opencv-python и scipy — для первой сборки вступительного ролика);
- Java 8+ — для вступительного ролика (jPSXdec скачивается в `lib/jpsxdec`
  сам); `--no-fmv` пропускает ролик;
- xdelta3 — для `--release` (Linux: `apt install xdelta3`, macOS:
  `brew install xdelta`; на Windows скачивается сам);
- TrueType-шрифты для загрузочных экранов, положить в `fonts/` в корне:
  `arial.ttf`, `arialbd.ttf`, `impact.ttf` (кириллица
  обязательна). Подойдут шрифты Windows или свободные замены: Liberation
  Sans (под именами arial.ttf и arialbd.ttf) и PT Sans Narrow Bold
  (под именем impact.ttf). С другими шрифтами контрольные суммы образа не
  совпадут с релизом, на игру это не влияет.

Растровые шрифты для текста игры (X11 misc-fixed с кириллицей, Tamzen)
лежат в `lib/fonts`.

## Сборка

```sh
pip install -r requirements.txt
python3 build.py discs /путь/к/ps1 /путь/к/saturn.zip   # раскладывает образы по discs/
python3 build.py doctor                                 # что установлено, какие диски на месте
python3 build.py ps1                                    # patched/Snatcher (Japan).bin + .cue
python3 build.py ps1 --no-fmv                           # быстрее, без вступительного ролика
python3 build.py ps1 --release                          # + release/Snatcher-PS1-RU-v<версия>.zip
```

`build.py discs` принимает папки, отдельные файлы или zip от redump и
копирует узнанные файлы:

```
discs/iso_ps1_jp/Snatcher (Japan).bin, .cue
discs/iso_saturn_jp/Snatcher (Japan) (Track 1).bin, (Track 2), (Track 3), Snatcher (Japan).cue
```

Первая сборка распаковывает диск и перерисовывает кадры ролика (несколько
минут); следующие используют кеш в `work/`.

## После правки перевода

```sh
sh ru/build_ru.sh            # переносит work/ru/out (если есть) в ps1/translation,
                             # перераспределяет пары букв по шрифту, собирает образ
sh ru/build_ru.sh --no-fmv
```

Таблица пар букв `work/pair_table.json` хранится в репозитории: после
изменения текста её нужно пересобрать (`ru/build_ru.sh` делает это сам) и
закоммитить вместе с текстом.

## Docker

```sh
docker build -t snatcher-build .
mkdir -p discs fonts out/patched out/release out/work
docker run --rm \
    -v "$PWD/discs:/src/discs" -v "$PWD/fonts:/src/fonts:ro" \
    -v "$PWD/out/patched:/src/patched" -v "$PWD/out/release:/src/release" \
    -v "$PWD/out/work:/src/work-cache" \
    snatcher-build ps1 --release
```
