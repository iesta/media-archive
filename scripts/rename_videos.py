#!/usr/bin/env python3
"""Renomme les fichiers d'un dossier d'après meta.json/meta_photos.json + mots-clés.

    ./rename_videos.py keywords.json [--meta meta.json] [--out DIR] [--csv NAME] [--dry]

keywords.json : {"GH012137": "chambre-piscine-palmiers", ...}   (clé = basename d'origine)
Nom : 2016-04-28_gopro-hero6_145_mexique-holbox_chevaux-balade-flaques.mp4
   -> {date}_{device}_{num}_{pays-ville}_{mots-cles}.{ext}
Écrit une table CSV (--csv, défaut rename.csv) : réversible fichier par fichier.
"""
import csv
import json
import os
import re
import sys
import unicodedata

TEMPLATE = "{date}_{device}_{num}_{place}_{keywords}"
FR = {"Mexico": "mexique", "México": "mexique", "Spain": "espagne", "España": "espagne"}
# codes modèle EXIF trop opaques pour un nom de fichier
MODELS = {"AC004": "DJI OsmoAction5 Pro"}


def slug(s):
    s = unicodedata.normalize("NFKD", str(s).lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def device_slug(name):
    """'GoPro Hero6 Black' -> 'gopro-hero6' ; 'DJI OsmoAction5 Pro' -> 'osmo-action5'."""
    raw = MODELS.get(str(name).strip(), str(name))
    brand = "gopro" if "gopro" in raw.lower() else ""
    s = re.sub(r"^(DJI|GoPro)\s+", "", raw, flags=re.I)
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)  # camelCase -> mots
    s = slug(s).replace("-black", "").replace("-pro", "")
    if not s:
        return "camera"
    return f"{brand}-{s}" if brand else s


def main():
    kw_path = next((a for a in sys.argv[1:] if not a.startswith("--")), "keywords.json")
    opt = lambda k, d: (sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d)  # noqa: E731
    meta_path = opt("--meta", "meta.json")
    out_dir = opt("--out", ".")
    csv_path = opt("--csv", "rename.csv")
    dry = "--dry" in sys.argv

    keywords = json.load(open(kw_path))
    meta = json.load(open(meta_path))
    rows, used = [], set()

    for f, e in sorted(meta.items(), key=lambda kv: (kv[1].get("creation_time") or kv[1]["date"], kv[0])):
        base, ext = os.path.splitext(f)
        if base not in keywords:
            print("pas de mots-clés pour", base)
            continue
        country = FR.get(e.get("country", ""), slug(e.get("country", "")))
        city = slug(e.get("city", ""))
        place = "-".join(p for p in (country, city or slug(e.get("state", ""))) if p)
        name = (TEMPLATE.format(date=(e.get("creation_time") or e["date"])[:10],
                                device=device_slug(e.get("device", "")),
                                num=re.sub(r"\D", "", base)[-3:],
                                place=place, keywords=slug(keywords[base]))
                + ext.lower())
        name = re.sub(r"_{2,}", "_", name).strip("_")
        n = 2
        while name in used:
            stem, e2 = os.path.splitext(name)
            name = f"{stem}-{n}{e2}"
            n += 1
        used.add(name)
        rows.append((base, os.path.join(out_dir, base + ext), name))

    with open(csv_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["gopro", "nom", "final"])
        w.writerows(rows)

    if dry:
        for _, _, n in rows:
            print(n)
        print(f"{len(rows)} noms proposés (dry-run, rien renommé)")
        return

    done = 0
    for _, cur, name in rows:
        src = cur if os.path.exists(cur) else os.path.join(out_dir, os.path.basename(cur))
        src = cur if os.path.exists(cur) else src
        if os.path.exists(src):
            os.rename(src, os.path.join(out_dir, name))
            done += 1
        else:
            print("absent:", src)
    print(f"{done}/{len(rows)} fichiers renommés — table: {csv_path}")


if __name__ == "__main__":
    main()
