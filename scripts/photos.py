#!/usr/bin/env python3
"""Métadonnées + planches-contact pour des photos (JPEG GoPro/appareil).

    ./photos.py [IMG_DIR] [VIDEO_META.json] [SHEETS_DIR]

Produit meta_photos.json :
  date, device, lat, lon, country, state, city, geo_inherited_from, sheet

Photos sans GPS -> ville du clip vidéo le plus proche dans le temps (VIDEO_META.json,
produit par build_meta.py). Planches de 6 photos (3x2) avec libellé du nom de fichier.
"""
import json
import os
import sys
import tempfile
from datetime import datetime

from PIL import Image, ImageDraw, ExifTags

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_meta import geocode  # noqa: E402

IMG = sys.argv[1] if len(sys.argv) > 1 else "."
VMETA = sys.argv[2] if len(sys.argv) > 2 else "meta.json"
SHEETS = sys.argv[3] if len(sys.argv) > 3 else os.path.join(tempfile.gettempdir(), "sheets")
EXT = (".jpg", ".jpeg")


def dms(v, ref):
    d, m, s = [float(x) for x in v]
    dec = d + m / 60 + s / 3600
    return -dec if ref in ("S", "W") else dec


def read(path):
    im = Image.open(path)
    ex = im.getexif()
    g = ex.get_ifd(0x8825)
    lat = lon = None
    if g.get(2) and g.get(4):
        la, lo = g[2], g[4]
        lar, lor = g.get(1) or "N", g.get(3) or "E"
        if isinstance(lar, bytes):
            lar = lar.decode()
        if isinstance(lor, bytes):
            lor = lor.decode()
        lat, lon = dms(la, lar), dms(lo, lor)
        if abs(lat) < 0.01 and abs(lon) < 0.01:
            lat = lon = None
    dt = ex.get(306) or ex.get(36867) or ""  # DateTime / DateTimeOriginal
    return {
        "date": dt.replace(":", "-", 2),
        "device": (ex.get(272) or "").rstrip(" \x00"),
        "lat": lat, "lon": lon,
        "width": Image.open(path).size[0], "height": Image.open(path).size[1],
    }


def sheet(paths, out):
    tw, th = 480, 360
    img = Image.new("RGB", (tw * 3, th * 2), "white")
    d = ImageDraw.Draw(img)
    for i, p in enumerate(paths):
        t = Image.open(p)
        t.thumbnail((tw, th))
        x, y = (i % 3) * tw, (i // 3) * th
        img.paste(t, (x + (tw - t.width) // 2, y + (th - t.height) // 2))
        d.text((x + 4, y + 4), os.path.basename(p), fill="red")
    img.save(out, quality=85)
    return out


def main():
    files = sorted(f for f in os.listdir(IMG) if f.lower().endswith(EXT))
    photos = {}
    for f in files:
        photos[f] = read(os.path.join(IMG, f))
        print(f, photos[f]["date"], photos[f]["device"], flush=True)

    videos = json.load(open(VMETA)) if os.path.exists(VMETA) else {}
    vts = [(datetime.strptime(v["creation_time"][:19], "%Y-%m-%dT%H:%M:%S"), v)
           for v in videos.values() if v.get("creation_time") and v.get("city")]

    for p in photos.values():
        if p["lat"]:
            p.update(geocode(p["lat"], p["lon"], 2))
        elif v_src := (min(vts, key=lambda t: abs((t[0] - datetime.strptime(
                p["date"], "%Y-%m-%d %H:%M:%S")).total_seconds()))[1] if vts else None):
            for k in ("lat", "lon", "country", "state", "city"):
                p[k] = v_src.get(k)
            p["geo_inherited_from"] = v_src["file"]

    os.makedirs(SHEETS, exist_ok=True)
    by_day = {}
    for f in files:
        by_day.setdefault(photos[f]["date"][:10], []).append(f)
    for day, group in by_day.items():
        for i in range(0, len(group), 6):
            chunk = group[i:i + 6]
            photos[chunk[0]]["sheet"] = sheet(
                [os.path.join(IMG, c) for c in chunk], f"{SHEETS}/{day}_{i // 6}.jpg")
            for c in chunk[1:]:
                photos[c]["sheet"] = photos[chunk[0]]["sheet"]

    json.dump(photos, open("meta_photos.json", "w"), ensure_ascii=False, indent=1)
    print("written meta_photos.json")


if __name__ == "__main__":
    main()
