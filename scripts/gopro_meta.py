#!/usr/bin/env python3
"""Copie les atomes GoPro de moov/udta de la source vers une version réencodée,
et décale les offsets stco/co64 en conséquence (mdat est déplacé).

Usage: gopro_meta.py SOURCE.MP4 CIBLE.mp4 [SORTIE.mp4]
Sans SORTIE: écrit CIBLE.mp4.patched puis remplace CIBLE.mp4 si la vérif passe.
"""
import struct
import sys
import os

GOPRO = {b"FIRM", b"LENS", b"CAME", b"SETT", b"MUID", b"HMMT", b"BCID", b"GUMI", b"GPMF"}
CONTAINERS = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"udta", b"edts", b"dinf", b"meta"}


def atoms(buf, start, end):
    p = start
    while p + 8 <= end:
        size, typ = struct.unpack(">I4s", buf[p:p + 8])
        hdr = 8
        if size == 1:
            size = struct.unpack(">Q", buf[p + 8:p + 16])[0]
            hdr = 16
        if size < hdr or p + size > end:
            return
        yield typ, p, size, hdr
        p += size


def find(buf, path, start=0, end=None):
    end = len(buf) if end is None else end
    if not path:
        return None
    for typ, pos, size, hdr in atoms(buf, start, end):
        if typ == path[0]:
            if len(path) == 1:
                return pos, size, hdr
            if typ in CONTAINERS:
                inner = pos + hdr + (4 if typ == b"meta" else 0)
                r = find(buf, path[1:], inner, pos + size)
                if r:
                    return r
    return None


def gopro_udta(src):
    hit = find(src, [b"moov", b"udta"])
    if not hit:
        return b""
    pos, size, hdr = hit
    out = b""
    for typ, p, n, _ in atoms(src, pos + hdr, pos + size):
        if typ in GOPRO:
            out += src[p:p + n]
    return out


def patch_stco(moov, delta):
    """Ajoute delta à chaque offset de chunk (stco 32 bits / co64 64 bits)."""
    out = bytearray(moov)

    def rec(start, end):
        for typ, pos, size, hdr in atoms(moov, start, end):
            if typ in (b"stco", b"co64"):
                n = struct.unpack(">I", moov[pos + hdr + 4:pos + hdr + 8])[0]
                fmt, w = (">I", 4) if typ == b"stco" else (">Q", 8)
                base = pos + hdr + 8
                for i in range(n):
                    o = base + i * w
                    out[o:o + w] = struct.pack(fmt, struct.unpack(fmt, moov[o:o + w])[0] + delta)
            elif typ in CONTAINERS:
                rec(pos + hdr, pos + size)
    rec(0, len(moov))
    return bytes(out)


def main():
    src_path, dst_path = sys.argv[1], sys.argv[2]
    src = open(src_path, "rb").read()
    dst = open(dst_path, "rb").read()

    extra = gopro_udta(src)
    if not extra:
        print("no gopro udta in source")
        return 1

    moov_hit = find(dst, [b"moov"])
    if not moov_hit:
        print("no moov")
        return 1
    moov_pos, moov_size, moov_hdr = moov_hit
    moov = bytearray(dst[moov_pos:moov_pos + moov_size])

    udta_hit = find(dst, [b"moov", b"udta"])
    if udta_hit:
        u_pos = udta_hit[0] - moov_pos
        u_size = udta_hit[1]
        # insérer les atomes GoPro juste avant la fin de udta
        moov[u_pos + u_size:u_pos + u_size] = extra
        struct.pack_into(">I", moov, u_pos, u_size + len(extra))
    else:
        new_udta = struct.pack(">I4s", 8 + len(extra), b"udta") + extra
        moov += new_udta
    struct.pack_into(">I", moov, 0, len(moov))

    delta = len(moov) - moov_size
    moov = patch_stco(bytes(moov), delta)

    out = dst[:moov_pos] + bytes(moov) + dst[moov_pos + moov_size:]

    if len(sys.argv) > 3:
        open(sys.argv[3], "wb").write(out)
    else:
        tmp = dst_path + ".patched"
        open(tmp, "wb").write(out)
        os.replace(tmp, dst_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
