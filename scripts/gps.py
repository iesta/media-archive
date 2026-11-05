#!/usr/bin/env python3
"""Extrait lat/lon de la télémétrie GPMF (piste GoPro MET) d'un .MP4.

Usage: gps.py FILE.MP4 [...]   ->  "file,lat,lon,nb_samples" (vide si pas de fix)

GPMF = KLV récursif : key(4) type(1) size(1) count(2), aligné sur 4 octets.
type 0x00 = conteneur, count = taille du payload en octets.
SCAL précède les données qu'il met à l'échelle.
"""
import json
import struct
import subprocess
import sys

TYPES = {"c": ("b", 1), "B": ("B", 1), "b": ("b", 1), "U": ("H", 2), "u": ("h", 2),
         "L": ("I", 4), "l": ("i", 4), "F": ("f", 4), "f": ("f", 4),
         "J": ("Q", 8), "j": ("q", 8), "Q": ("Q", 8), "q": ("q", 8),
         "d": ("d", 8), "s": ("h", 2), "S": ("H", 2)}

GPS_SCALE = [10_000_000, 10_000_000, 1000, 1000, 1000]  # lat, lon, alt, v2d, v3d


def parse(buf, start, end):
    out = []
    p = start
    while p + 8 <= end:
        key = buf[p:p + 4]
        typ = buf[p + 4]
        size, cnt = struct.unpack(">BH", buf[p + 5:p + 8])
        if typ == 0:  # conteneur
            if p + 8 + cnt > end:
                break
            children, _ = parse(buf, p + 8, p + 8 + cnt)
            out.append((key, None, 0, cnt, children))
            p = p + 8 + cnt + 3 & ~3
        else:
            n = size * cnt
            if size == 0 or n == 0 or p + 8 + n > end:
                break
            out.append((key, typ, size, cnt, buf[p + 8:p + 8 + n]))
            p = p + 8 + n + 3 & ~3
    return out, p


def values(typ, size, count, payload):
    fmt, w = TYPES.get(chr(typ), (None, 0))
    if not fmt or size % w:
        return None
    per = size // w
    v = struct.unpack(">%d%s" % (per * count, fmt), payload)
    return [v[i * per:(i + 1) * per] for i in range(count)]


def find_gps(items, pts=None):
    if pts is None:
        pts = []
    scale = None
    for key, typ, size, count, payload in items:
        if typ is None:
            find_gps(payload, pts)
            continue
        if key == b"SCAL":
            v = values(typ, size, count, payload)
            scale = v[0] if v else None
        elif key in (b"GPS5", b"GPS9"):
            samples = values(typ, size, count, payload)
            if not samples:
                continue
            per = len(samples[0])
            sc = scale if scale and len(scale) >= 2 else GPS_SCALE[:per]
            pts.extend((s[0] / sc[0], s[1] / sc[1]) for s in samples)
    pts = [(a, b) for a, b in pts if abs(a) > 0.01 and abs(b) > 0.01]
    if not pts:
        return None
    lat = sorted(p[0] for p in pts)[len(pts) // 2]
    lon = sorted(p[1] for p in pts)[len(pts) // 2]
    return (lat, lon, len(pts))


def read_gpmf(path):
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "d",
         "-show_entries", "stream=index,codec_tag_string", "-of", "json", path],
        capture_output=True, check=True).stdout)
    idx = next((s["index"] for s in probe["streams"]
                if s.get("codec_tag_string") == "gpmd"), None)
    if idx is None:
        raise RuntimeError("pas de piste gpmd: " + path)
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-map", f"0:{idx}",
                        "-c", "copy", "-f", "rawvideo", "-"], capture_output=True)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError("extraction gpmd échouée: " + path)
    return r.stdout


def gps(path):
    raw = read_gpmf(path)
    items, _ = parse(raw, 0, len(raw))
    return find_gps(items)


if __name__ == "__main__":
    for f in sys.argv[1:]:
        try:
            r = gps(f)
        except Exception:
            r = None
        print(f"{f},{r[0]:.6f},{r[1]:.6f},{r[2]}" if r else f"{f},,,")
