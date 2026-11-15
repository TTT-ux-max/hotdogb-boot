#!/usr/bin/env python3
"""把新编的 Image-dtb 重打包成可直接 fastboot flash 的 boot.img。

与「全量重编 ROM」无关，只替换 boot 分区的 kernel 段：
  - cmdline / ramdisk / header-v2 dtb 段 / 全部 mkbootimg 参数：与原版逐字节一致
  - kernel 段 = 新编 Image（含 UNCOMPRESSED_IMG 头） + 原版逐字节 appended DTB 区
  - AVB hash footer：image_size / vbmeta_offset / root_digest 全部按新 payload 重算
  - 输出仍是 96 MiB、AVBf hash footer 自洽，无需重新签名（test-keys 无签名 hash footer）

用法:
  python3 tools/pack-boot.py [--kernel out/arch/arm64/boot/Image-dtb]
                             [--profile clean] [--out dist/boot-clean.img]
                             [--verify]
"""
import argparse
import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / 'boot-ref'
TOOLS = ROOT / 'tools'
MKBOOTIMG = TOOLS / 'mkbootimg.py'
UNPACK_BOOTIMG = TOOLS / 'unpack_bootimg.py'


def die(msg):
    print(f'[pack-boot] 失败: {msg}', file=sys.stderr)
    sys.exit(1)


def img_end(data: bytes) -> int:
    if data[:16] != b'UNCOMPRESSED_IMG':
        die('kernel 段缺少 UNCOMPRESSED_IMG 魔数（需要 Image-dtb，不是 Image.gz）')
    return 20 + struct.unpack('<I', data[16:20])[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--kernel', default=str(ROOT / 'out/arch/arm64/boot/Image-dtb'))
    ap.add_argument('--profile', default='clean')
    ap.add_argument('--out', default='')
    ap.add_argument('--verify', action='store_true', help='额外用 unpack_bootimg.py 解包复核')
    args = ap.parse_args()

    params = json.loads((REF / 'boot-params.json').read_text())
    avb = params['avb']
    part_size = params['partition_size']

    new_kernel = Path(args.kernel)
    if not new_kernel.is_file():
        die(f'新内核不存在: {new_kernel}（先运行 scripts/build.sh 或 build-kernel.sh image）')
    out = Path(args.out) if args.out else ROOT / 'dist' / f"boot-{args.profile}.img"
    out.parent.mkdir(parents=True, exist_ok=True)

    footer = bytearray((REF / 'avb/footer.bin').read_bytes())
    blob = bytearray((REF / 'avb/vbmeta-blob.bin').read_bytes())
    if footer[:4] != b'AVBf' or blob[:4] != b'AVB0':
        die('boot-ref/avb 模板损坏')
    salt = bytes.fromhex(avb['salt_hex'])
    digest_off = avb['digest_offset_in_blob']
    digest_len = avb['digest_len']
    vb_sz = avb['vbmeta_size']
    assert len(blob) == vb_sz, (len(blob), vb_sz)
    assert bytes(blob[avb['digest_offset_in_blob'] - len(salt):digest_off]) == salt, 'salt 偏移不符'

    # ---- 1) kernel 段 = 新 Image + 原版逐字节 appended DTB 区 ----
    k_new = new_kernel.read_bytes()
    appended = (REF / 'dtb-appended.bin').read_bytes()
    if len(appended) != params['dtb_appended_size']:
        die('dtb-appended.bin 长度与 boot-params.json 不符')
    kernel_seg = k_new[:img_end(k_new)] + appended
    print(f'[pack-boot] 新 Image 区 {img_end(k_new)} B + 原版 DTB 区 {len(appended)} B '
          f'= kernel 段 {len(kernel_seg)} B')

    # ---- 2) 按原版参数生成裸 boot.img ----
    raw = out.with_suffix('.raw.img')
    cmd = [
        sys.executable, str(MKBOOTIMG),
        '--kernel', str(_write_tmp(kernel_seg, out.parent / '.kernel-seg.tmp')),
        '--ramdisk', str(REF / 'ramdisk.img'),
        '--dtb', str(REF / 'dtb.img'),
        '--cmdline', params['cmdline'],
        '--base', params['kernel']['base'],
        '--kernel_offset', params['kernel']['offset'],
        '--ramdisk_offset', params['ramdisk']['offset'],
        '--tags_offset', params['tags_offset'],
        '--dtb_offset', params['dtb']['offset'],
        '--pagesize', str(params['page_size']),
        '--header_version', str(params['header_version']),
        '--os_version', params['os_version'],
        '--os_patch_level', params['os_patch_level'],
        '-o', str(raw),
    ]
    if params.get('product_name'):
        cmd += ['--name', params['product_name']]
    subprocess.run(cmd, check=True)
    payload = raw.read_bytes()
    pay_len = len(payload)
    print(f'[pack-boot] 裸镜像 {pay_len} B = {pay_len / 1048576:.2f} MiB')

    # ---- 3) 更新 vbmeta hash descriptor 与 footer ----
    struct.pack_into('!Q', blob, avb['image_size_offset_in_blob'], pay_len)
    new_dig = hashlib.sha256(salt + payload).digest()
    blob[digest_off:digest_off + digest_len] = new_dig
    struct.pack_into('>QQQ', footer, avb['footer']['original_image_size_offset'],
                     pay_len, pay_len, vb_sz)

    # ---- 4) 组装 96 MiB: payload + vbmeta + 零填充 + footer ----
    pad = part_size - avb['footer_size'] - pay_len - vb_sz
    if pad < 0:
        die(f'payload 过大: {pay_len} + {vb_sz} + {avb["footer_size"]} > {part_size}')
    final = payload + bytes(blob) + b'\0' * pad + bytes(footer)
    assert len(final) == part_size
    out.write_bytes(final)
    print(f'[pack-boot] 零填充 {pad} B，最终 {out.stat().st_size} B')

    # ---- 5) 自校验 ----
    chk = out.read_bytes()
    f2 = chk[-avb['footer_size']:]
    s2, off2, sz2 = struct.unpack('>QQQ', bytes(f2[12:36]))
    assert f2[:4] == b'AVBf' and (s2, off2, sz2) == (pay_len, pay_len, vb_sz), 'footer 不自洽'
    assert chk[off2:off2 + 4] == b'AVB0', 'vbmeta blob 位置错误'
    b2 = chk[off2:off2 + sz2]
    assert struct.unpack_from('!Q', b2, avb['image_size_offset_in_blob'])[0] == pay_len
    assert bytes(b2[digest_off:digest_off + digest_len]) == new_dig
    assert hashlib.sha256(salt + chk[:pay_len]).digest() == new_dig
    print('[pack-boot] AVB footer / descriptor / sha256(salt||payload) 自洽 OK')

    # ---- 6) 解包复核（可选） ----
    if args.verify:
        vr = out.parent / f'.verify-{out.stem}'
        subprocess.run(['rm', '-rf', str(vr)])
        vr.mkdir(parents=True)
        subprocess.run([sys.executable, str(UNPACK_BOOTIMG), '--boot_img', str(out),
                        '--out', str(vr)], check=True, capture_output=True)
        checks = {
            'kernel 段': ((vr / 'kernel').read_bytes(), kernel_seg),
            'ramdisk': ((vr / 'ramdisk').read_bytes(), (REF / 'ramdisk.img').read_bytes()),
            'header-v2 dtb 段': ((vr / 'dtb').read_bytes(), (REF / 'dtb.img').read_bytes()),
        }
        for name, (a, b) in checks.items():
            print(f'[verify] {name}: {"一致" if a == b else "不一致"}')
            if a != b:
                die(f'{name} 与原版不符')
        k_chk = (vr / 'kernel').read_bytes()
        assert k_chk[img_end(k_chk):] == appended, 'kernel 内嵌 DTB 区被改动'
        subprocess.run(['rm', '-rf', str(vr)])

    raw.unlink(missing_ok=True)
    (out.parent / '.kernel-seg.tmp').unlink(missing_ok=True)
    sha = hashlib.sha256(chk).hexdigest()
    (out.with_suffix('.img.sha256')).write_text(f'{sha}  {out.name}\n')
    print(f'[pack-boot] 完成: {out}')
    print(f'[pack-boot] sha256: {sha}')


def _write_tmp(data: bytes, path: Path) -> Path:
    path.write_bytes(data)
    return path


if __name__ == '__main__':
    main()
