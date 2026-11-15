#!/usr/bin/env bash
# 准备内核编译工具链，并归一化为工程内固定布局：
#   toolchain/clang/{bin,lib64}          clang-r383902b1
#   toolchain/gcc64/bin                  aarch64-linux-android-4.9
#   toolchain/gcc32/bin                  arm-linux-androideabi-4.9
#   toolchain/build-tools/bin            make/flex/bison/m4
#   toolchain/build-tools/common/bison   BISON_PKGDATADIR
#   toolchain/tools-lineage/{lib,common/perl-base}
#
# 两种来源：
#   LOCAL_PREBUILTS=/path/to/lineage-18.1   直接软链复用本地 AOSP 树（离线、与本地 ROM 构建完全一致）
#   未设置                                 从 AOSP / LineageOS 官方镜像在线下载（GitHub Actions 默认）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/config/build.env"
[[ -f "$ROOT/config/local.env" ]] && source "$ROOT/config/local.env"

TC="$ROOT/toolchain"
mkdir -p "$TC"

log() { printf '\033[1;34m[toolchain]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[toolchain] 失败:\033[0m %s\n' "$*" >&2; exit 1; }

[[ -f "$TC/.ready" ]] && { log "工具链已就绪（$TC/.ready），跳过。删除该文件可强制重建"; exit 0; }

# ---------------------------------------------------------------- 本地模式
if [[ -n "$LOCAL_PREBUILTS" ]]; then
  P="$LOCAL_PREBUILTS/prebuilts"
  [[ -d "$P/clang/host/linux-x86/$CLANG_NAME/bin" ]] || die "未找到 $P/clang/host/linux-x86/$CLANG_NAME/bin"
  log "复用本地 AOSP prebuilts: $LOCAL_PREBUILTS"

  ln -sfn "$P/clang/host/linux-x86/$CLANG_NAME"                 "$TC/clang"
  ln -sfn "$P/gcc/linux-x86/aarch64/aarch64-linux-android-4.9" "$TC/gcc64"
  ln -sfn "$P/gcc/linux-x86/arm/arm-linux-androideabi-4.9"     "$TC/gcc32"
  ln -sfn "$P/build-tools"                                       "$TC/build-tools"
  ln -sfn "$P/tools-lineage"                                     "$TC/tools-lineage"

  cat > "$TC/.ready" <<EOF
mode=local
prebuilts=$LOCAL_PREBUILTS
clang=$CLANG_NAME
EOF
  log "本地工具链归一化完成"
  exit 0
fi

# ---------------------------------------------------------------- 在线模式
log "在线下载工具链（GitHub Actions 推荐）"
mkdir -p "$TC/dl"

fetch() {  # fetch <url> <dest.tar.gz> [soft]
  local url="$1" dest="$2" soft="${3:-0}"
  if [[ -s "$dest" ]]; then log "已缓存 $(basename "$dest")"; return 0; fi
  log "下载 $(basename "$dest") ..."
  if curl -fL --retry 3 --retry-delay 5 --connect-timeout 30 -o "$dest.part" "$url"; then
    mv "$dest.part" "$dest"; return 0
  fi
  rm -f "$dest.part"
  [[ "$soft" = "1" ]] && return 1
  die "下载失败: $url"
}

extract() { # extract <tar.gz> <target-dir> [strip-components]
  local arc="$1" dir="$2" strip="${3:-1}"
  rm -rf "$dir"; mkdir -p "$dir"
  tar -xzf "$arc" -C "$dir" --strip-components="$strip" \
    || die "解压失败: $arc"
}

# 1) clang-r383902b1（gitiles 子目录归档，顶层即 bin/ lib64/，strip=0）
fetch "$CLANG_ARCHIVE_URL" "$TC/dl/clang.tar.gz"
extract "$TC/dl/clang.tar.gz" "$TC/clang" 0

# 2) GCC aarch64 / arm32（codeload 仓库归档，strip=1）
fetch "$GCC64_URL" "$TC/dl/gcc64.tar.gz"
extract "$TC/dl/gcc64.tar.gz" "$TC/gcc64" 1
fetch "$GCC32_URL" "$TC/dl/gcc32.tar.gz"
extract "$TC/dl/gcc32.tar.gz" "$TC/gcc32" 1

# 3) host 工具：优先 AOSP build-tools，失败则回退系统工具
HAVE_BUILDTOOLS=0
if [[ "$USE_SYSTEM_HOST_TOOLS" != "1" ]] && fetch "$BUILDTOOLS_URL" "$TC/dl/build-tools.tar.gz" 1; then
  if extract "$TC/dl/build-tools.tar.gz" "$TC/build-tools" 1 && [[ -x "$TC/build-tools/linux-x86/bin/make" || -x "$TC/build-tools/bin/make" ]]; then
    HAVE_BUILDTOOLS=1
  fi
fi
if [[ "$HAVE_BUILDTOOLS" != "1" ]]; then
  log "使用系统 host 工具（make/flex/bison/m4）"
  mkdir -p "$TC/build-tools/bin"
  for t in make flex bison m4; do
    command -v "$t" >/dev/null || die "系统缺少 $t，请先 apt install make flex bison m4"
    ln -sfn "$(command -v "$t")" "$TC/build-tools/bin/$t"
  done
fi
mkdir -p "$TC/tools-lineage"

# 校验关键可执行文件
[[ -x "$TC/clang/bin/clang" ]] || die "缺少 $TC/clang/bin/clang"
[[ -x "$TC/gcc64/bin/aarch64-linux-android-gcc" ]] || die "缺少 aarch64-linux-android-gcc"
if [[ ! -x "$TC/gcc32/bin/arm-linux-androidkernel-gcc" && ! -x "$TC/gcc32/bin/arm-linux-androideabi-gcc" ]]; then
  die "缺少 arm32 GCC（arm-linux-androidkernel-gcc / arm-linux-androideabi-gcc）"
fi

cat > "$TC/.ready" <<EOF
mode=online
clang=$CLANG_NAME
EOF
log "在线工具链归一化完成"
