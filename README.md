# media-archive — compress & organize a video/photo library

An agent skill (Claude Code, Codex, OpenCode, …) that turns a raw GoPro / action-cam / drone /
phone dump into a compact, searchable archive:

- **measure first** — test-encode + VMAF before promising any size win
- **1080p HEVC re-encode** (~3× smaller on a 2.7K GoPro library, visually transparent)
- **metadata preserved** — capture date, GoPro `moov/udta` atoms (`FIRM`, `LENS`, `CAME`,
  `SETT`, `MUID`, `GPMF`) restored by binary patch, telemetry (`gpmd`) kept
- **GPS → place** — parses the GPMF telemetry track, reverse-geocodes with Nominatim/OSM
- **keywords** — the agent reads 3 frames per clip (2/10/30 s) and writes 3–4 tags,
  using the cheapest vision model available (Haiku / Flash-Lite / nano class, never a
  flagship: same result at 20–40× the price)
- **reversible rename** — `2016-04-28_gopro-hero6_145_mexique-holbox_chevaux-balade-flaques.mp4`,
  every mapping kept in a CSV
- **JPEG pass** — quality-85 re-encode, EXIF + GPS preserved (~55 % of the weight)
- **final layout** — `Movies/` + `Images/`, `.THM`/`.LRV` gone

## Requirements

| Tool | Used for | Check |
|---|---|---|
| `ffmpeg` + `ffprobe` (with **libx265**, **libvmaf**) | encode, metadata, VMAF | `ffmpeg -hide_banner -encoders \| grep libx265` |
| ImageMagick `magick` | JPEG re-encode without losing EXIF | `magick -version` |
| Pillow | EXIF/GPS of photos | `python3 -c "import PIL"` |
| `curl` | Nominatim reverse geocoding | `curl -sI https://nominatim.openstreetmap.org` |

macOS: `brew install ffmpeg imagemagick` and `python3 -m pip install --user Pillow`
(or `brew install pillow`).
Debian/Ubuntu: `sudo apt install ffmpeg imagemagick python3-pil curl` — distro ffmpeg often
lacks libvmaf, in which case skip the VMAF step and eyeball the result.

Scripts are macOS-first (`stat -f`, `qlmanage`); on Linux replace `stat -f%z` by `stat -c%s`.

## Install

Clone anywhere, then link it into the skills directory of each agent you use:

```bash
git clone <this repo> ~/skills/media-archive

# OpenCode / shared convention
mkdir -p ~/.agents/skills && ln -sfn ~/skills/media-archive ~/.agents/skills/media-archive
# Claude Code
mkdir -p ~/.claude/skills && ln -sfn ~/skills/media-archive ~/.claude/skills/media-archive
# Codex
mkdir -p ~/.codex/skills && ln -sfn ~/skills/media-archive ~/.codex/skills/media-archive
```

Skills are discovered at session start — restart the agent after linking.

## Use

Just ask: *"optimise and rename this GoPro folder"* / *"recompress these videos"*.
The agent loads the skill and follows `SKILL.md`.

Manual run, in the media directory:

```bash
S=~/skills/media-archive/scripts

$S/encode.sh  SRC_DIR OUT_DIR                    # CRF=27 MODE=1080p JOBS=4
$S/fix_meta.sh SRC_DIR OUT_DIR                   # capture date + GoPro atoms + mtime
python3 $S/build_meta.py SRC_DIR OUT_DIR /tmp/sheets   # date, device, GPS, city, frames

# write keywords.json = {"GH012137": "chevaux-plage-mer", ...}  (no extension)
python3 $S/rename_videos.py keywords.json --out OUT_DIR --csv rename_videos.csv --dry
python3 $S/rename_videos.py keywords.json --out OUT_DIR --csv rename_videos.csv

# photos
magick photo.JPG -quality 85 out.jpg
python3 $S/photos.py IMG_DIR meta.json /tmp/sheets
python3 $S/rename_videos.py keywords_photos.json --meta meta_photos.json \
    --out IMG_DIR --csv rename_photos.csv --dry
```

Options: `CRF=27`, `PRESET=medium`, `JOBS=4`, `MODE=source` (keep resolution, ~2× smaller
instead of ~3×). Every step is resumable and logs to `OUT_DIR/progress.log`.

## Outputs

```
SRC/            originals — untouched until you explicitly delete them
OUT/            encoded files + progress.log
meta.json       per clip: duration, creation_time, device, lat/lon, country/state/city
meta_photos.json
rename_videos.csv, rename_photos.csv     old name → new name (your rollback path)
logs/
```

## Measured reference (GoPro HERO6, 2.7K 23.976p, 33 Mbps source)

| Recipe | Mbps | VMAF | Size vs source |
|---|---|---|---|
| source H.264 2.7K | 33.1 | 100 | 100 % |
| x265 2.7K CRF 24 | 32.0 | 99.96 | ~97 % (pointless) |
| x265 2.7K CRF 30 | 16.4 | 93.9 | 50 % |
| **x265 1080p CRF 27** | **14.4** | **98.6** | **~43 %** |
| x265 1080p CRF 30 | 9.8 | 92.3 | 30 % |
| x264 1080p CRF 23 (max compat) | 23.8 | 99.96 | 72 % |

Re-encoding GoPro footage **at the same resolution and quality saves nothing** — the gain
comes from resolution, not from the codec.

## Cost of the keyword step

Perception, not reasoning: use the cheapest vision model of the family you have.
One contact sheet ≈ 700–1500 input tokens, so a 36-clip library is a few cents on a
Haiku/Flash-Lite-class model versus a few dollars on a flagship. If the session model is
already cheap, read the sheets inline; if it is expensive, delegate to sub-agents pinned to
a cheap vision model, one sub-agent per batch of 6–10 sheets — never one per image.
Details: `SKILL.md` § 4.

## Notes & gotchas

- `-map 0` fails on GoPro files (`tmcd`/`fdsc` tracks can't be muxed into mp4): map `0:v:0`,
  `0:a:0` and the `gpmd` index explicitly.
- `0:d:0` is the timecode track, not telemetry — find the index whose `codec_tag_string` is `gpmd`.
- ffmpeg drops `moov/udta` and `creation_time`; `gopro_meta.py` re-inserts the atoms and fixes
  `stco/co64` chunk offsets.
- VMAF must be computed with `setpts=N/FRAME_RATE/TB` on both inputs, otherwise the score is
  meaningless (~21).
- `.THM` (160×120 thumbnails) and `.LRV` (848×480 proxies) are GoPro-only artifacts: delete
  them, never rename them.
- Nothing is deleted without explicit confirmation; renaming is always reversible via the CSV.

Full agent-facing instructions: [`SKILL.md`](SKILL.md).
