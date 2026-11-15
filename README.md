# hotdogb-boot-source

OnePlus 7T（`hotdogb` / sm8150）**独立 boot.img 编译工程**。

从 LineageOS 18.1 / Android 11 的完整源码树里，把「编译 boot 分区」这一件事单独抽出来：
只编内核、只换 `boot.img` 的 kernel 段，**不跑 `brunch`、不重编 system/vendor**。
可以直接 push 到 GitHub，用 Actions 一键产出可刷的 `boot.img`。

> 详细的上云步骤见 **[GitHub编译指南.md](GitHub编译指南.md)**。

---

## 快速开始

### 本地（已有 AOSP / LineageOS 源码树）

```bash
# 解压交付包后进入工程目录
cd hotdogb-boot-github

# 复用本地工具链，一键编出 dist/boot-clean.img
LOCAL_PREBUILTS=/root/lineage-18.1 ./scripts/build.sh --profile clean --jobs 4

# 刷机
fastboot flash boot dist/boot-clean.img && fastboot reboot
```

### GitHub Actions

1. 把本目录整个 push 到 GitHub 仓库（含 `kernel/` 与 `.github/`）。
2. Actions → **Build hotdogb boot.img** → Run workflow。
3. 下载 artifact `hotdogb-boot-clean`，里面就是 `boot-clean.img`。

---

## 三档内核配置

| 档位 | 内容 | 用途 |
|---|---|---|
| `stock` | LineageOS 官方原版 `vendor/sm8150-perf_defconfig`（794 行） | 基线对照 |
| `clean` | 官方原版 **+ 仅 `CONFIG_HIDRAW=y`**（798 行）**← 默认** | 已实测可开机的纯净内核 |
| `custom` | 当前定制版（914 行）：hidraw + VR/供电 + Docker/容器项，`SYSVIPC=n` | 完整功能，用于继续排查/开发 |

切换只需 `--profile <档位>`，脚本会把对应 defconfig 覆盖到内核源码目录再编译。

---

## 目录结构

```
.github/workflows/build-boot.yml   GitHub Actions：下载工具链 → 编内核 → 出 boot.img
config/build.env                  可覆盖的默认参数（档位/并发/工具链 URL）
defconfig/                        三档 defconfig + 完整 .config 参考
kernel/                           sm8150 4.14 完整内核源码（70,584 文件 / 1.1 GiB）
boot-ref/                         重建 boot.img 所需的原版参考资产（≈9 MiB）
  ├─ boot-params.json             全部 mkbootimg + AVB 参数
  ├─ ramdisk.img / dtb.img        header-v2 的两段
  ├─ dtb-appended.bin             kernel 段内嵌 DTB 区
  └─ avb/{footer,vbmeta-blob}.bin  AVB hash footer 模板
tools/                            mkbootimg.py / unpack_bootimg.py / pack-boot.py / verify-boot.py
scripts/                          fetch-toolchain.sh / build-kernel.sh / build.sh / verify.sh
patches/                          源码树相对官方的改动记录（kernel-custom.patch）
out/  dist/  toolchain/           运行时生成，已被 .gitignore 排除
```

---

## 产物是什么

`dist/boot-<profile>.img` 是 **96 MiB 的 A/B 分区 boot 镜像**，header v2、`AVBf` hash footer 自洽，
可直接 `fastboot flash boot`。它与原版 `boot.img` 的差异**只有 kernel 段**：

| 部分 | 处理 |
|---|---|
| `cmdline`、ramdisk、header-v2 `--dtb` 段、base/offset、os_version | 与原版逐字节一致 |
| kernel 段 | 新编 `Image`（含 `UNCOMPRESSED_IMG` 头）+ **原版逐字节** appended DTB 区 |
| AVB | `image_size` / `vbmeta_offset` / `root_digest` 按新 payload 重算（test-keys 无签名 hash footer，无需私钥） |

> ⚠️ `boot-ref/dtb.img`（header-v2 段）与 `boot-ref/dtb-appended.bin`（kernel 内嵌区）
> **长度相同但内容不同**，不可互换。详见 `boot-ref/README.md`。

刷机前自检：

```bash
./scripts/verify.sh dist/boot-clean.img
```

会逐项核对分区大小、cmdline、AVB digest、ramdisk、两段 DTB，并输出 `dist/verify-*.json`。

---

## 前置与边界

- 手机需 **OOS 11 / Android 11 固件、A/B 双槽一致、Bootloader 已解锁**；固件分区（modem/xbl/abl/dsp）不在本工程内。
- 本工程**只产出 boot 分区镜像**，不是完整刷机包。系统主体仍用
  `lineage-18.1-20261114-UNOFFICIAL-hotdogb.zip` 或完整线刷包。
- **禁止与 LOS 24 / Android 14 世代的镜像混刷**。
- 已知：`clean` 档内核本身清白；此前「刷完无法进系统」的根因在 `system.img` 的
  VR 用户态脚本与 dm-verity，不在内核，详见线刷包内的 `启动失败排障.md`。

---

## 实测记录

- 用同一份 `Image-dtb` 走本工程重打包链路，产出的 `boot-clean.img` 与已交付镜像
  **sha256 完全一致**：`a217e5146adefc9306152123bf53f7e25ef1e46b17a9b1dc0dcd28706dbde5f2`。
- `verify-boot.py` 的 16 项检查全部通过（含 `sha256(salt||payload) == root_digest`）。
- 从零完整重编内核（`defconfig → dtbs → Image-dtb → 打包`）也已跑通，`EXIT=0`。
  重编产物的 sha256 与上一条不同（`scripts/mkcompile_h` 写入编译时间戳），属正常现象，
  不影响可刷性；详见 `GitHub编译指南.md` 第八节。
- 三档 defconfig 均由 LineageOS 官方 `sm8150-perf_defconfig` 派生，改动可追溯。
