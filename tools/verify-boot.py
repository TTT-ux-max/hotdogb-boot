#!/usr/bin/env python3
"""独立校验任意由本工程生成的 boot.img（可在刷机前跑）。

检查项：分区大小 / AVBf footer / hash descriptor / sha256(salt||payload) /
        mkbootimg 参数 / ramdisk / header-v2 dtb 段 / kernel 内嵌 DTB 区。

用法: python3 tools/verify-boot.py dist/boot-clean.img [--json dist/verify.json]
"""
import argparse
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / 'boot-ref'
UNPACK = ROOT / 'tools/unpack_bootimg.py'
HDR_FMT = '<8sIIIIIIIIII16s512s32s1024sIQIIQ'


def img_end(data):
    return 20 + struct.unpack('<I', data[16:20])[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('boot_img')
    ap.add_argument('--json', default='')
    args = ap.parse_args()

    p = json.loads((REF / 'boot-params.json').read_text())
    avb = p['avb']
    img = Path(args.boot_img)
    d = img.read_bytes()
    r = {'file': str(img), 'checks': {}}

    def chk(name, ok, detail=''):
        r['checks'][name] = {'ok': bool(ok), 'detail': detail}
        print(f'  [{"OK" if ok else "FAIL"}] {name}{": " + detail if detail else ""}')

    print(f'校验 {img} ({len(d)} B)')
    chk('分区大小 = 96 MiB', len(d) == p['partition_size'], str(len(d)))

    (magic, kernel_sz, kernel_addr, ramdisk_sz, ramdisk_addr, second_sz,
     second_addr, tags_addr, page_size, hdr_ver, os_ver, name, cmdline,
     img_id, extra, dtbo_sz, dtbo_off, hdr_size, dtb_sz, dtb_addr) = \
        struct.unpack_from(HDR_FMT, d, 0)
    chk('ANDROID! 魔数', magic == b'ANDROID!')
    chk('header_version = 2', hdr_ver == p['header_version'])
    chk('page_size = 4096', page_size == p['page_size'])
    chk('cmdline 与原版一致', cmdline.rstrip(b'\0').decode() == p['cmdline'])
    chk('kernel/ramdisk/tags/dtb 地址一致',
        (kernel_addr, ramdisk_addr, tags_addr, dtb_addr) ==
        tuple(int(x, 16) for x in (p['kernel']['offset'], p['ramdisk']['offset'],
                                   p['tags_offset'], p['dtb']['offset'])))

    footer = d[-avb['footer_size']:]
    chk('AVBf footer 魔数', footer[:4] == b'AVBf')
    o_sz, vb_off, vb_sz = struct.unpack('>QQQ', footer[12:36])
    chk('footer 三字段自洽', (o_sz, vb_off, vb_sz) == (o_sz, o_sz, avb['vbmeta_size']),
        f'image_size={o_sz} vbmeta_offset={vb_off} vbmeta_size={vb_sz}')
    blob = d[vb_off:vb_off + vb_sz]
    chk('AVB0 vbmeta 魔数', blob[:4] == b'AVB0')
    desc_sz = struct.unpack_from('!Q', blob, avb['image_size_offset_in_blob'])[0]
    chk('descriptor image_size = payload 长度', desc_sz == o_sz, str(desc_sz))
    salt = bytes.fromhex(avb['salt_hex'])
    digest = blob[avb['digest_offset_in_blob']:avb['digest_offset_in_blob'] + avb['digest_len']]
    calc = hashlib.sha256(salt + d[:o_sz]).digest()
    chk('sha256(salt||payload) = root_digest', digest == calc, calc.hex()[:16] + '…')

    with tempfile.TemporaryDirectory() as td:
        vr = Path(td)
        subprocess.run([sys.executable, str(UNPACK), '--boot_img', str(img), '--out', str(vr)],
                       check=True, capture_output=True)
        k = (vr / 'kernel').read_bytes()
        chk('kernel 段 UNCOMPRESSED_IMG', k[:16] == b'UNCOMPRESSED_IMG')
        chk('kernel 内嵌 DTB 区 = 原版逐字节',
            k[img_end(k):] == (REF / 'dtb-appended.bin').read_bytes())
        chk('ramdisk 与原版逐字节一致',
            (vr / 'ramdisk').read_bytes() == (REF / 'ramdisk.img').read_bytes())
        chk('header-v2 dtb 段与原版逐字节一致',
            (vr / 'dtb').read_bytes() == (REF / 'dtb.img').read_bytes())

    r['sha256'] = hashlib.sha256(d).hexdigest()
    r['all_ok'] = all(v['ok'] for v in r['checks'].values())
    print(f'\n结论: {"全部通过" if r["all_ok"] else "存在失败项"}  sha256={r["sha256"]}')
    if args.json:
        Path(args.json).write_text(json.dumps(r, indent=2, ensure_ascii=False) + '\n')
    sys.exit(0 if r['all_ok'] else 1)


if __name__ == '__main__':
    main()
