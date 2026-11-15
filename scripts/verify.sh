#!/usr/bin/env bash
# 校验已生成的 boot.img（刷机前自检）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMG="${1:-$ROOT/dist/boot-clean.img}"
python3 "$ROOT/tools/verify-boot.py" "$IMG" --json "$ROOT/dist/verify-$(basename "$IMG" .img).json"
