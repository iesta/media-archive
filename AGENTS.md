# AGENTS.md

Agent instructions for this repository (media-archive skill).
Codex/Claude Code/OpenCode all end up here; the skill itself is `SKILL.md`.

## What this repo is

A portable agent skill: compress and organize a video/photo library (GoPro, action-cam,
drone, phone). Markdown = the instructions the agent reads; `scripts/` = the deterministic
parts (ffmpeg/ImageMagick/Python). No build step, no dependencies beyond the tools listed
in `SKILL.md` § 0 bis.

```
SKILL.md              agent-facing workflow (source of truth)
README.md             human-facing doc (install, quick start, measurements)
scripts/encode.sh     video batch re-encode (1080p HEVC, keeps gpmd telemetry)
scripts/fix_meta.sh   restore capture date + GoPro udta atoms + mtime
scripts/gopro_meta.py mp4 atom patch (moov/udta insert + stco/co64 offsets)
scripts/gps.py        GPMF telemetry parser -> lat/lon
scripts/build_meta.py date, device, GPS, reverse geocode, 3-frame sheets
scripts/photos.py     JPEG EXIF/GPS + labelled contact sheets
scripts/rename_videos.py  rename from meta + keywords, writes rollback CSV
```

## How an agent should use it

1. Read `SKILL.md` top to bottom before acting — the order of steps matters (measure →
   encode → metadata → geo → keywords → rename → tidy).
2. Check dependencies first (`SKILL.md` § 0 bis); install missing ones with brew/pip
   yourself, announcing what you install.
3. Never delete originals without an explicit user request; renaming is always reversible
   through the CSV.
4. Ask the user to eyeball 2–3 outputs before any deletion.

## Conventions when editing this repo

- Keep instructions in French in `SKILL.md` (the user's language), scripts/comments in
  French, code identifiers in English.
- `SKILL.md` frontmatter: `name` + `description` only; description must carry the trigger
  phrases (that is what the agent matches on).
- Scripts: macOS-first (BSD `stat -f`), note the Linux equivalent inline. `set -u` in bash,
  no bashisms beyond arrays/exports.
- Every non-trivial script keeps a way to be checked: `python3 -m py_compile`, `bash -n`,
  and a smoke run on 1–2 tiny files in a temp dir.
- Never commit user media or run artefacts (see `.gitignore`): no `meta*.json`,
  `keywords*.json`, `rename*.csv`, `geocode_cache.json`, `Movies/`, `Images/`.
- New pitfall discovered during a real run → add one row to the table in `SKILL.md`.

## Smoke test (no media needed)

```bash
bash -n scripts/encode.sh scripts/fix_meta.sh
python3 -m py_compile scripts/*.py
scripts/encode.sh /tmp/empty /tmp/empty/out    # doit afficher "ok: 0/0, echecs: 0"
```
