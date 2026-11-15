#!/usr/bin/env bash
# 一键编译 hotdogb boot.img（只编内核 + 重打包 boot 分区，不做全量 ROM 编译）
#
#   ./scripts/build.sh                          # 默认 clean 档，走完整流程
#   ./scripts/build.sh --profile custom        # VR/Docker 全开档
#   ./scripts/build.sh --profile stock         # 官方原版档
#   ./scripts/build.sh --local-prebuilts /root/lineage-18.1   # 复用本地 AOSP 工具链（离线）
#   ./scripts/build.sh --jobs 8               # 指定并发
#   ./scripts/build.sh --skip-kernel          # 已有 out/.../Image-dtb，只重打包
#   ./scripts/build.sh --kernel-only          # 只编内核，不生成 boot.img
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/config/build.env"
[[ -f "$ROOT/config/local.env" ]] && source "$ROOT/config/local.env"

SKIP_KERNEL=0
KERNEL_ONLY=0
DO_VERIFY=1

usage() { sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)        PROFILE="$2"; shift 2 ;;
    --jobs)           JOBS="$2"; shift 2 ;;
    --local-prebuilts) export LOCAL_PREBUILTS="$2"; shift 2 ;;
    --skip-toolchain) SKIP_TOOLCHAIN=1; shift ;;
    --skip-kernel)    SKIP_KERNEL=1; shift ;;
    --kernel-only)    KERNEL_ONLY=1; shift ;;
    --no-verify)      DO_VERIFY=0; shift ;;
    -h|--help)        usage 0 ;;
    *) echo "未知参数: $1" >&2; usage 2 ;;
  esac
done
SKIP_TOOLCHAIN="${SKIP_TOOLCHAIN:-0}"

export PROFILE JOBS LOCAL_PREBUILTS USE_SYSTEM_HOST_TOOLS \
       CLANG_ARCHIVE_URL GCC64_URL GCC32_URL BUILDTOOLS_URL CLANG_NAME
log() { printf '\033[1;36m[build]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[build] 失败:\033[0m %s\n' "$*" >&2; exit 1; }

case "$PROFILE" in stock|clean|custom) ;; *) die "PROFILE 必须是 stock/clean/custom，当前=$PROFILE" ;; esac

log "档位=$PROFILE  并发=$JOBS  工具链=${LOCAL_PREBUILTS:-在线下载}"

# 1) 工具链
if [[ "$SKIP_TOOLCHAIN" = "1" ]]; then
  [[ -f "$ROOT/toolchain/.ready" ]] || die "--skip-toolchain 但 toolchain/.ready 不存在"
  log "跳过工具链准备"
else
  bash "$ROOT/scripts/fetch-toolchain.sh"
fi

# 2) 内核
IMG="$ROOT/out/arch/arm64/boot/Image-dtb"
if [[ "$SKIP_KERNEL" = "1" ]]; then
  [[ -f "$IMG" ]] || die "--skip-kernel 但 $IMG 不存在"
  log "跳过内核编译，使用现有 $IMG"
else
  bash "$ROOT/scripts/build-kernel.sh" all "$PROFILE"
  [[ -f "$IMG" ]] || die "内核编译后未找到 $IMG"
fi

if [[ "$KERNEL_ONLY" = "1" ]]; then
  log "仅编译内核完成：$IMG"
  exit 0
fi

# 3) 重打包 boot.img
OUT="$ROOT/dist/boot-$PROFILE.img"
log "重打包 → $OUT"
python3 "$ROOT/tools/pack-boot.py" --kernel "$IMG" --profile "$PROFILE" --out "$OUT" --verify

# 4) 独立复核
if [[ "$DO_VERIFY" = "1" ]]; then
  python3 "$ROOT/tools/verify-boot.py" "$OUT" --json "$ROOT/dist/verify-$PROFILE.json"
fi

log "完成：$OUT ($(stat -c%s "$OUT") B)"
log "刷机: fastboot flash boot $OUT && fastboot reboot"
