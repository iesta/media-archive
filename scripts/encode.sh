#!/bin/bash
# Réencodage 1080p HEVC d'une bibliothèque vidéo (GoPro / action-cam / drone).
#
#   ./encode.sh [SRC_DIR] [OUT_DIR]
#   CRF=27 PRESET=medium JOBS=4 MODE=1080p ./encode.sh ~/Videos/gopro ~/Videos/gopro/1080p
#
# MODE=1080p (défaut, recommandé) | MODE=source (même résolution, ~2x plus petit)
# Progression : OUT_DIR/progress.log   |   relançable : les fichiers déjà faits sont sautés.
#
# Préserver les pistes de données (télémétrie GoPro gpmd) : indispensable pour les overlays.
set -u
SRC=${1:-.}
OUT=${2:-$SRC/compressed_1080p}
CRF=${CRF:-27}
PRESET=${PRESET:-medium}
JOBS=${JOBS:-4}
MODE=${MODE:-1080p}
LOG=$OUT/progress.log
mkdir -p "$OUT"
cd "$SRC" || exit 1
FILES=$(ls -1 *.MP4 *.mp4 *.MOV *.mov 2>/dev/null)
TOTAL=$(printf '%s\n' "$FILES" | grep -c .)

# index de la piste gpmd (télémétrie) : 0:d:0 = timecode, piège classique
gpmd_index() {
  ffprobe -v error -select_streams d -show_entries stream=index,codec_tag_string \
    -of csv=p=0 "$1" | awk -F, '$2=="gpmd"{print $1; exit}'
}

: >"$LOG"
enc() {
  f=$1
  base=$(basename "$f")
  base=${base%.*}
  dst="$OUT/$base.mp4"
  [ -s "$dst" ] && return 0
  idx=$(gpmd_index "$f")
  maps=(-map 0:v:0 -map 0:a:0?)
  [ -n "$idx" ] && maps+=(-map "0:$idx")
  vf=()
  [ "$MODE" = 1080p ] && vf=(-vf scale=1920:1080:flags=lanczos)

  t0=$(date +%s)
  if ffmpeg -nostdin -v error -y -i "$f" "${maps[@]}" "${vf[@]}" \
      -c:v libx265 -preset "$PRESET" -crf "$CRF" -pix_fmt yuv420p \
      -x265-params log-level=error \
      -c:a aac -b:a 128k -c:d copy \
      -movflags +faststart -tag:v hvc1 \
      "$OUT/.$base.tmp.mp4"; then
    mv "$OUT/.$base.tmp.mp4" "$dst"
    dt=$(( $(date +%s) - t0 ))
    s=$(stat -f%z "$f"); d=$(stat -f%z "$dst")
    n=$(grep -c '^OK' "$LOG")
    printf 'OK    %-16s %6dMB -> %5dMB (%2d%%)  %3ds  [%d/%d]\n' \
      "$base" "$((s / 1048576))" "$((d / 1048576))" "$((100 * d / s))" \
      "$dt" "$((n + 1))" "$TOTAL" >>"$LOG"
  else
    echo "FAIL  $base" >>"$LOG"
    rm -f "$OUT/.$base.tmp.mp4"
  fi
}
export -f enc gpmd_index
export OUT CRF PRESET MODE LOG TOTAL

printf '%s\n' "$FILES" | grep . | xargs -P "$JOBS" -I{} bash -c 'enc "$@"' _ {}

{
  echo "--- fin $(date '+%F %T') ---"
  echo "ok: $(ls -1 "$OUT"/*.mp4 2>/dev/null | wc -l | tr -d ' ')/$TOTAL  echecs: $(grep -c '^FAIL' "$LOG")"
} | tee -a "$LOG"
