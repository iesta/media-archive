---
name: gallery-cleanup
description: >
  Compress and rename a video library (GoPro/action-cam/drone/phone clips) into a searchable
  archive: measure before re-encoding, 1080p HEVC, preserve GoPro telemetry/EXIF metadata,
  derive country/city from GPS, describe frames for keywords, and rename with a reversible CSV.
  Trigger: "optimize/recompress my GoPro videos", "these MP4s are huge", "rename clips by
  place and date", "add keywords to my videos", cleaning up a GoPro SD card dump.
---

# gallery-archive — compresser + nommer une bibliothèque vidéo

Scripts dans `~/.agents/skills/media-archive/scripts/` (`$S` dans la suite).
Écrits et testés sur macOS (BSD `stat -f`, `qlmanage`) ; sous Linux remplacer `stat -f%z`
par `stat -c%s`.

## 0 bis. Dépendances (vérifier avant de commencer)

| Outil | Pour | Vérification |
|---|---|---|
| `ffmpeg` + `ffprobe` avec **libx265** et **libvmaf** | encodage + contrôle qualité | `ffmpeg -hide_banner -encoders \| grep libx265` et `-filters \| grep vmaf` |
| ImageMagick (`magick`) | recompression des JPEG sans perdre l'EXIF | `magick -version` |
| Pillow | lecture EXIF/GPS des photos (`photos.py`) | `python3 -c "import PIL; print(PIL.__version__)"` |
| `curl` | reverse geocoding Nominatim | `curl -sI https://nominatim.openstreetmap.org \| head -1` |

Check rapide :

```bash
for b in ffmpeg ffprobe magick curl; do command -v "$b" >/dev/null || echo "MANQUE $b"; done
ffmpeg -hide_banner -encoders 2>/dev/null | grep -q libx265 || echo "MANQUE libx265"
ffmpeg -hide_banner -filters 2>/dev/null | grep -q libvmaf || echo "MANQUE libvmaf"
python3 -c "import PIL" 2>/dev/null || echo "MANQUE Pillow"
```

**Si un outil manque : installer soi-même** (Homebrew macOS, une seule commande, pas besoin de
demander à l'utilisateur de le faire à la main) — annoncer ce qui va être installé, puis :

```bash
brew install ffmpeg imagemagick          # ffmpeg Homebrew inclut libx265 + libvmaf
python3 -m pip install --user Pillow     # pyenv/venv ; sinon: brew install pillow
```

Linux (Debian/Ubuntu) : `sudo apt install ffmpeg imagemagick python3-pil curl` — mais le
`ffmpeg` distro n'a souvent **pas** libvmaf : sans lui, sauter l'étape VMAF et comparer à
l'œil (`ffplay`), ou compiler/ utiliser un build statique.
Vérifier après installation en relançant le check ci-dessus. Les scripts sont déjà
exécutables ; sinon `chmod +x $S/*.sh $S/*.py`.

**Règle n°1 : mesurer avant de promettre.** Ne jamais annoncer « on va gagner 5x » sans
un encodage test + VMAF. Sur du GoPro 2.7K/4K déjà bien encodé, un réencodage **à
résolution égale et qualité égale ne gagne rien** (mesuré : x265 CRF 24 = même bitrate
que le H.264 d'origine). Le gain vient de la résolution, pas du codec.

**Règle n°2 : rien n'est supprimé.** Originaux conservés jusqu'à validation visuelle par
l'utilisateur. Les renommages sont réversibles via `rename.csv`.

## 0. Reconnaissance (toujours)

```bash
for f in *.MP4; do ffprobe -v error -select_streams v:0 \
  -show_entries stream=codec_name,width,height,r_frame_rate,bit_rate \
  -show_entries format=duration,size -of csv=p=0 "$f"; done | sort | uniq -c
du -ch *.MP4 | tail -1
ls | sed 's/.*\.//' | sort | uniq -c      # .LRV/.THM = proxies + vignettes GoPro
```

- GoPro : `GXnnnnnn.MP4` (X=H vidéo, L proxy `.LRV`, T vignette `.THM`). Les `.LRV`
  (848×480) ne servent qu'à Quik/Studio → supprimables si l'utilisateur ne monte pas.
- Pistes typiques : `0` vidéo, `1` audio, `2` `tmcd` (timecode), `3` `gpmd` (télémétrie),
  `4` `fdsc` — l'ordre varie selon le modèle et la réécriture.
- `moov/udta` contient `FIRM` `LENS` `CAME` `SETT` `MUID` `HMMT` `BCID` `GUMI` `GPMF`.

## 1. Test de compression (obligatoire avant le batch)

Encoder ~13 s d'un clip représentatif, puis VMAF :

```bash
S=~/.agents/skills/media-archive/scripts
ffmpeg -ss 60 -t 13 -i CLIP.MP4 -map 0:v:0 -map 0:a:0 -c copy /tmp/src.mkv
# candidats : 1080p crf 27 / 1080p crf 30 / 2.7K crf 30 / x264 1080p crf 23
ffmpeg -i /tmp/src.mkv -vf scale=1920:1080:flags=lanczos -c:v libx265 -preset medium \
  -crf 27 -pix_fmt yuv420p -an /tmp/t.mp4
# VMAF : normaliser les timestamps, sinon score faux (~21 au lieu de ~98)
ffmpeg -i /tmp/t.mp4 -i /tmp/src.mkv -lavfi "\
[0:v]scale=1920:1080:flags=lanczos,format=yuv420p,setpts=N/FRAME_RATE/TB[d];\
[1:v]scale=1920:1080:flags=lanczos,format=yuv420p,setpts=N/FRAME_RATE/TB[r];\
[d][r]libvmaf=n_threads=8" -f null -
```

Repères mesurés (GoPro HERO6 2.7K 33 Mbps, contenu dense) : 1080p CRF 27 ≈ 14 Mbps
VMAF 98 ; CRF 30 ≈ 10 Mbps VMAF 92 ; 2.7K CRF 30 ≈ 16 Mbps VMAF 94. Présenter le
tableau, laisser choisir, ne pas décider seul du compromis qualité.

## 2. Batch

```bash
$S/encode.sh SRC_DIR OUT_DIR            # CRF=27 MODE=1080p JOBS=4 par défaut
$S/fix_meta.sh SRC_DIR OUT_DIR          # date + atomes GoPro + mtime
```

`encode.sh` : HEVC 1080p, AAC 128k, `+faststart`, `hvc1`, **copie la piste gpmd**
(sinon plus d'overlays GPS/vitesse dans Quik). Relançable, log dans `OUT_DIR/progress.log`.

`fix_meta.sh` : ffmpeg perd `creation_time` et tout `moov/udta` propriétaire →
`gopro_meta.py` réinsère les atomes GoPro et **corrige les offsets `stco/co64`**
(mdat se décale). Vérifier après coup : atomes byte-identiques, durée égale,
décodage propre, thumbnail Quick Look.

```bash
python3 - <<'EOF'   # contrôle atomes + date
import glob, json, subprocess, struct
GOPRO={b'FIRM',b'LENS',b'CAME',b'SETT',b'MUID',b'HMMT',b'BCID',b'GUMI',b'GPMF'}
def meta(p):
    d=open(p,'rb').read(); i=d.find(b'udta'); out={}
    if i<0: return out
    q=i+4
    while q+8<=len(d):
        n,t=struct.unpack('>I4s',d[q:q+8])
        if n<8 or q+n>len(d): break
        if t in GOPRO: out[t]=d[q:q+n]
        q+=n
    return out
for f in sorted(glob.glob('*.MP4')):
    o='compressed_1080p/'+f[:-4]+'.mp4'
    assert meta(f)==meta(o), f
EOF
```

## 2 bis. Photos (JPEG)

```bash
magick photo.JPG -quality 85 /tmp/x.jpg   # PSNR 44-46 dB, EXIF+GPS conservés ~55 % du poids
python3 $S/photos.py IMG_DIR meta.json /tmp/sheets   # -> meta_photos.json + planches 3x2
python3 $S/rename_videos.py keywords_photos.json --meta meta_photos.json \
  --out IMG_DIR --csv rename_photos.csv --dry
```

`magick` conserve EXIF/IPTC par défaut — **ne jamais utiliser `-strip`**. Vérifier après
coup que `DateTime`, `Model` et l'IFD GPS sont présents. `photos.py` lit DateTime (306),
Model (272) et l'IFD GPS (0x8825) ; photos sans GPS → ville du clip vidéo le plus proche
dans le temps (`meta.json` de l'étape 3).

## 3. Métadonnées → pays, ville, date, appareil

```bash
python3 $S/build_meta.py SRC_DIR OUT_DIR /tmp/sheets
```

- **Date** : `creation_time` du conteneur (GoPro écrit l'heure locale avec suffixe `Z`).
- **Appareil** : clé `DVNM` de la télémétrie (`Hero6 Black`, `HERO11 Black`…). Fallback : `CAME` (binaire, illisible).
- **GPS** : `gps.py` parse GPMF (KLV récursif, `GPS5`, `SCAL`). Clips sans fix → héritage
  du clip le plus proche en temps, tracé dans `geo_inherited_from`. Ne jamais inventer un lieu.
- **Lieu** : lancer depuis le dossier de travail (`meta.json` y est écrit, idem
  `meta_photos.json` et `geocode_cache.json`). Nominatim/OSM en cascade zoom 18 → 16 → 14 (18 seul renvoie parfois juste le
  comté), 1 req/s, cache `geocode_cache.json`. Coordonnées ~0.5° d'écart = vérifier le pays,
  pas la ville.

## 4. Mots-clés visuels

`build_meta.py` produit une planche-contact par clip : 3 frames à 2/10/30 s (écrêtées à la
durée) en `hstack`. **Les lire une par une** (`read` sur le jpg) et écrire 3-4 mots-clés
français, minuscules, sans accents, séparés par `-` : `chevaux-plage-mangrove`,
`ponton-hamac-famille`. Décrire ce qu'on voit (sujet + lieu + action), pas d'interprétation.
Un sous-agent peut traiter un lot de planches si la bibliothèque est grosse.

## 5. Renommage

```bash
# keywords.json : {"GH012137": "chambre-piscine-palmiers"} — sans extension
python3 $S/rename_videos.py keywords.json --out OUT_DIR --csv rename_videos.csv --dry
python3 $S/rename_videos.py keywords.json --out OUT_DIR --csv rename_videos.csv
```

Nom par défaut : `2016-04-28_gopro-hero6_145_mexique-holbox_chevaux-balade-flaques.mp4`
→ `{date}_{device}_{num}_{pays-ville}_{mots-cles}`. Adapter `TEMPLATE` si l'utilisateur
veut un autre ordre (beaucoup préfèrent la date en premier : elle trie chronologiquement).
Pays traduits en français dans `FR` ; ville sinon région. Toujours passer `--csv` pour que
les passes vidéo et photo ne s'écrasent pas la table (`rename_videos.csv` / `rename_photos.csv`).

## 6. Rangement final

Une fois les fichiers validés (l'agent a fait relire 2-3 clips à l'utilisateur) :

```bash
rm -f *.THM                      # vignettes GoPro 160x120, orphelines après renommage
rm -f *.LRV                      # proxies 848x480, seulement si pas de montage Quik prévu
mkdir -p Movies Images
mv *.mp4 Movies/ ; mv *.jpg Images/
```

- **Vidéos et photos dans des dossiers séparés** : c'est ce que l'utilisateur veut presque
  toujours (bibliothèque, Photos.app, Plex, sauvegardes).
- Les `.THM`/`.LRV` gardent l'ancienne numérotation GoPro et ne pointent plus sur rien :
  les supprimer, jamais les renommer (aucun outil moderne ne les lit).
- Garder à la racine les tables CSV et `meta*.json` : ce sont les seules traces des noms
  d'origine une fois les originaux supprimés.
- Supprimer les originaux **seulement** sur demande explicite, et seulement après les
  contrôles de l'étape 2.

## Pièges (chacun a coûté un run)

| Piège | Effet | Correctif |
|---|---|---|
| `-map 0` | `Could not find tag for codec none` : pistes `tmcd`/`fdsc` non muxables en mp4 | mapper `0:v:0`, `0:a:0`, index `gpmd` |
| `-map 0:d:0` | pointe sur `tmcd` (4 octets) au lieu de la télémétrie | trouver l'index par `codec_tag_string == gpmd` |
| `-f data -` | sortie vide/tronquée | `-f rawvideo -` vers stdout |
| GPMF sans alignement 4 octets | clés décalées, `DEVC` géant | aligner `p` à 4 après chaque élément |
| GPMF : conteneur = compteur d'éléments | parse cassé | conteneur : `type=0`, `count` = **taille du payload en octets** |
| VMAF sans `setpts=N/FRAME_RATE/TB` | score ~21, comparaison inutile | normaliser les deux entrées |
| `-pix_fmt yuv420p` sans attention | GoPro est `yuvj420p` (full range) | laisser swscale convertir, vérifier VMAF |
| `ffmpeg -map_metadata 0` seul | `FIRM`/`LENS`/`CAME` perdus quand même | patch binaire `udta` + `stco` |
| suppression des `.LRV` avant accord | proxies utiles pour un montage Quik | demander |
| `.THM`/`.LRV` renommés avec les vidéos | doublons inutiles, aucun outil ne les lit | supprimer, ne pas renommer |
| deux passes de renommage | la 2e écrase `rename.csv` | `--csv rename_videos.csv` / `--csv rename_photos.csv` |

## Livrables attendus

1. Tableau avant/après (Mbps, VMAF, taille totale).
2. `OUT_DIR` + `progress.log` + `meta.json`/`meta_photos.json` + tables `rename_*.csv`.
3. `Movies/` + `Images/` rangés, `.THM`/`.LRV` supprimés.
4. Originaux intacts jusqu'à validation, suppression faite uniquement sur demande.
