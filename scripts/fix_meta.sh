#!/bin/bash
# Remet dans les fichiers réencodés ce que ffmpeg perd :
#   - creation_time (date de prise de vue, niveau conteneur + pistes)
#   - date de modification du fichier = date d'origine
#   - atomes GoPro de moov/udta (FIRM, LENS, CAME, SETT, MUID, HMMT, BCID, GUMI, GPMF)
#   - la piste de télémétrie gpmd (déjà copiée par encode.sh)
#
#   ./fix_meta.sh [SRC_DIR] [OUT_DIR]
#
# Sans effet sur les fichiers non-GoPro (pas d'atome udta propriétaire).
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=${1:-.}
OUT=${2:-$SRC/compressed_1080p}
LOG=$OUT/meta.log
cd "$SRC" || exit 1
: >"$LOG"

for f in *.MP4 *.mp4 *.MOV *.mov; do
  [ -e "$f" ] || continue
  base=$(basename "$f"); base=${base%.*}
  out="$OUT/$base.mp4"
  tmp="$OUT/.$base.fix.mp4"
  [ -s "$out" ] || { echo "MISSING $base" >>"$LOG"; continue; }
  ct=$(ffprobe -v error -show_entries format_tags=creation_time -of csv=p=0 "$f")
  is_gopro=$(head -c 20000000 "$f" | grep -c GPMF || true)
  if ! ffmpeg -nostdin -v error -y -i "$out" \
      -map 0 -c copy -map_metadata 0 ${ct:+-metadata creation_time=$ct} \
      -movflags +faststart "$tmp"; then
    echo "FAIL remux $base" >>"$LOG"; rm -f "$tmp"; continue
  fi
  # atomes udta propriétaires : GoPro uniquement
  if [ "$is_gopro" -gt 0 ] && python3 "$HERE/gopro_meta.py" "$f" "$tmp" "$tmp.patched" >/dev/null 2>&1 \
     && [ -s "$tmp.patched" ]; then
    mv "$tmp.patched" "$out"
  else
    mv "$tmp" "$out"
    rm -f "$tmp.patched"
  fi
  rm -f "$tmp"
  touch -r "$f" "$out"
  echo "OK $base $ct" >>"$LOG"
done

echo "--- fin: $(grep -c '^OK' "$LOG") ok, $(grep -c 'FAIL\|MISSING' "$LOG") probleme(s) ---" >>"$LOG"
tail -1 "$LOG"
