#!/usr/bin/env python3
"""Construit meta.json pour une bibliothèque vidéo + planches-contact de 3 frames.

    ./build_meta.py [SRC_DIR] [ENC_DIR] [SHEETS_DIR]

SRC_DIR  : vidéos d'origine (télémétrie, date de prise de vue)   défaut "."
ENC_DIR  : versions réencodées                                    défaut "compressed_1080p"
SHEETS_DIR : images de contrôle (défaut: temp dir)

Champs produits par fichier : duration, creation_time, device, lat, lon,
country, state, city, geo_inherited_from, sheet.
"""
import datetime
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gps as gpsmod  # noqa: E402

SRC = sys.argv[1] if len(sys.argv) > 1 else "."
ENC = sys.argv[2] if len(sys.argv) > 2 else "compressed_1080p"
SHEETS = sys.argv[3] if len(sys.argv) > 3 else os.path.join(tempfile.gettempdir(), "sheets")
CACHE = "geocode_cache.json"
VIDEO_EXT = (".mp4", ".mov", ".m4v")


def probe(path):
    d = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:format_tags=creation_time", "-of", "json", path],
        capture_output=True, check=True).stdout)
    return (float(d["format"]["duration"]),
            d["format"].get("tags", {}).get("creation_time", ""))


def device(path):
    """Nom du modèle lu dans la télémétrie (DVNM) — 'Hero6 Black', 'HERO11 Black'..."""
    try:
        raw = gpsmod.read_gpmf(path)
        items, _ = gpsmod.parse(raw, 0, len(raw))
    except Exception:
        items = []

    def find(it):
        for k, t, s, c, p in it:
            if t is None:
                r = find(p)
                if r:
                    return r
            elif k == b"DVNM":
                return p.rstrip(b"\x00").decode("latin1", "replace")
    return find(items) or ""


def encoder_name(path):
    """Fallback hors GoPro (DJI…) : le tag encoder du conteneur, ex. 'DJI OsmoAction5 Pro'."""
    d = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format_tags=encoder:stream_tags=encoder", "-of", "json", path],
        capture_output=True).stdout or b"{}")
    for s in d.get("streams", []):
        if s.get("tags", {}).get("encoder"):
            return s["tags"]["encoder"]
    return d.get("format", {}).get("tags", {}).get("encoder", "")


def geocode(lat, lon, precision=3):
    """OSM/Nominatim : zoom 18 -> 16 -> 14, on garde la 1re localité trouvée."""
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    key = f"{lat:.{precision}f},{lon:.{precision}f}"
    if key in cache:
        return cache[key]
    out = {"country": "", "state": "", "city": ""}
    for zoom in (18, 16, 14):
        q = {"lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "format": "jsonv2",
             "zoom": zoom, "addressdetails": 1}
        r = subprocess.run(["curl", "-s", "-m", "20", "-A", "media-archive/1.0",
                            "https://nominatim.openstreetmap.org/reverse?"
                            + urllib.parse.urlencode(q)],
                           capture_output=True, text=True)
        time.sleep(1.1)  # politique d'usage Nominatim : 1 req/s max
        try:
            a = json.loads(r.stdout).get("address", {})
        except Exception:
            continue
        out["country"] = out["country"] or a.get("country", "")
        out["state"] = out["state"] or a.get("state", "")
        city = next((a[k] for k in ("city", "town", "village", "hamlet", "suburb")
                     if a.get(k)), "")
        if city:
            out["city"] = city
            break
        out["city"] = out["city"] or a.get("municipality") or a.get("county", "")
    cache[key] = out
    json.dump(cache, open(CACHE, "w"), ensure_ascii=False, indent=1)
    return out


def frames(encoded, dur, base):
    """3 frames (2/10/30 s, écrêtées à la durée) collées horizontalement."""
    os.makedirs(SHEETS, exist_ok=True)
    times = [t for t in (2, 10, 30) if t < dur - 0.3] or [max(0.5, dur / 2)]
    parts = []
    for i, t in enumerate(times):
        p = f"{SHEETS}/{base}_{i}.jpg"
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t}", "-i", encoded,
                            "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "4", p],
                           capture_output=True)
        if r.returncode or not os.path.exists(p):
            continue  # clip illisible / frame manquante
        parts.append(p)
    if not parts:
        return None
    sheet = f"{SHEETS}/{base}.jpg"
    args = ["ffmpeg", "-v", "error", "-y"]
    for p in parts:
        args += ["-i", p]
    if len(parts) == 1:
        subprocess.run(args + ["-map", "0:v", sheet], check=True)
    else:
        pads = "".join(f"[{i}:v]" for i in range(len(parts)))
        args += ["-filter_complex", f"{pads}hstack=inputs={len(parts)}[v]",
                 "-map", "[v]", sheet]
        subprocess.run(args, check=True)
    return sheet


def main():
    meta = {}
    for f in sorted(os.listdir(SRC)):
        if not f.lower().endswith(VIDEO_EXT):
            continue
        path = os.path.join(SRC, f)
        dur, ct = probe(path)
        try:
            r = gpsmod.gps(path)
        except Exception:
            r = None  # pas de piste GPMF (DJI, caméra tierce)
        e = {"file": f, "duration": dur, "creation_time": ct,
             "device": device(path) or encoder_name(path),
             "lat": r[0] if r else None, "lon": r[1] if r else None}
        if r:
            e.update(geocode(r[0], r[1]))
        meta[f] = e
        print(f, ct[:10], f"{dur:.1f}s", e["device"], e.get("city"), flush=True)

    # pas de fix GPS -> hérite du clip le plus proche dans le temps
    def ts(e):
        return datetime.datetime.strptime(e["creation_time"][:19], "%Y-%m-%dT%H:%M:%S")

    have = [k for k in meta if meta[k]["lat"]]
    for k, e in meta.items():
        if e["lat"] or not have:
            continue
        src = min((meta[h] for h in have),
                  key=lambda h: abs((ts(h) - ts(e)).total_seconds()))
        for key in ("lat", "lon", "country", "state", "city"):
            e[key] = src[key]
        e["geo_inherited_from"] = src["file"]

    # point GPS mal tombé dans un polygone municipal -> reprend la ville du voisin
    for e in meta.values():
        if e.get("city", "").count(" ") and e["lat"]:
            near = [x for x in meta.values()
                    if x is not e and x["lat"] and " " not in x.get("city", "")
                    and abs(x["lat"] - e["lat"]) < 0.03
                    and abs(x["lon"] - e["lon"]) < 0.03]
            if near:
                e["city"] = near[0]["city"]

    for f, e in meta.items():
        enc = os.path.join(ENC, os.path.splitext(f)[0] + ".mp4")
        if os.path.exists(enc):
            e["sheet"] = frames(enc, e["duration"], os.path.splitext(f)[0])

    json.dump(meta, open("meta.json", "w"), ensure_ascii=False, indent=1)
    print("written meta.json")


if __name__ == "__main__":
    main()
