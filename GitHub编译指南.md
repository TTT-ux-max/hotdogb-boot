# GitHub 编译指南（hotdogb boot.img）

本工程把「编译 OnePlus 7T 的 boot 分区」从 LineageOS 全量源码里独立出来。
在 GitHub Actions 上一次编译约 **10~20 分钟**，只产出 `boot.img`，不需要 43 GiB 的
AOSP `prebuilts/`，也不需要 8 GiB 内存墙下的全量 `brunch`。

---

## 一、先选仓库形态

| | **模式 A：完整仓库**（推荐，最简单） | **模式 B：轻量仓库 + Release 源码分卷** |
|---|---|---|
| 仓库内容 | 整个工程，含 `kernel/`（70,584 文件 / 1.1 GiB） | 只放脚本、workflow、boot-ref、文档（≈10 MiB） |
| push 体积 | 首次较大（git 压缩后约 250~350 MiB） | 很小，几秒完成 |
| 内核源码 | checkout 后就在 `kernel/` | 由 workflow 从 Release 下载 `kernel-src.7z.*` 合并解压 |
| 适用场景 | 网络好、想直接改内核源码并提交 | 国内网络 / 不想 push 1 GiB |

> 两种模式共用同一个 workflow，产物完全一致。模式 B 需要在 Actions 表单里填 Release tag。

---

## 二、模式 A：完整仓库

### 1. 解压交付包

```bash
7z x -mmt=2 hotdogb-boot-github.7z.001      # 所有分卷必须放在同一目录
cd hotdogb-boot-github
sha256sum -c SHA256SUMS.txt                  # 校验
```

解压后目录里已有 `.github/workflows/build-boot.yml`，**不需要额外配置**。

### 2. 建仓库并推送

```bash
git init -b main
git config user.name  "your-name"
git config user.email "you@example.com"
git add .
git commit -m "hotdogb boot source: kernel + defconfig + boot-ref + CI"
git remote add origin https://github.com/<you>/hotdogb-boot-source.git
git push -u origin main
```

`out/`、`dist/`、`toolchain/`、`config/local.env` 已被 `.gitignore` 排除，不会误传编译产物。

> 首次 push 文件数很多，建议用 SSH、保持网络稳定；若中途失败重跑 `git push` 即可（git 会续传）。
> GitHub 建议仓库 < 1 GiB，本工程约 1.1 GiB 源码（git 压缩后远小于此），公开仓库可用。

### 3. 触发编译

Actions → **Build hotdogb boot.img** → **Run workflow**：

| 输入 | 说明 |
|---|---|
| `profile` | `clean`（默认，已验证可开机）/ `stock` / `custom` |
| `jobs` | 并发数，4 核 runner 填 `4`~`6` |
| `kernel_src_release` | **留空**（模式 A） |
| `use_system_host_tools` | 一般不勾；仅当在线 build-tools 下载失败时勾选 |

push 到 `main` 也会自动触发（默认 `clean` 档）。

### 4. 取产物

编译完成后在 run 页面下载 artifact `hotdogb-boot-clean`，包含：

| 文件 | 说明 |
|---|---|
| `boot-clean.img` | **96 MiB，直接 `fastboot flash boot`** |
| `boot-clean.img.sha256` | 校验值 |
| `verify-clean.json` | 16 项自检报告 |
| `Image-dtb` | 新编内核镜像（供本地二次打包） |
| `.config` | 本次实际生效的完整内核配置 |
| `build-kernel.log` | 编译日志 |

---

## 三、模式 B：轻量仓库

### 1. 生成内核源码分卷

从解压后的完整工程里，只把 `kernel/` 单独压成分卷（**归档内不含 `kernel/` 顶层目录**）：

```bash
cd hotdogb-boot-github/kernel
7z a -v90m -mx=5 -mmt=2 ../kernel-src.7z .
cd ..
ls -lh kernel-src.7z.*
```

每个分卷 90 MiB < GitHub 单文件 100 MiB 限制。

### 2. 建仓库（不含 kernel/）

```bash
# 先临时移走 kernel，push 完再移回来（本地仍可编译）
mv kernel /tmp/hotdogb-kernel
git init -b main && git add . && git commit -m "hotdogb boot CI (lightweight)"
git remote add origin https://github.com/<you>/hotdogb-boot-source.git
git push -u origin main
mv /tmp/hotdogb-kernel kernel
```

### 3. 上传源码分卷到 Release

```bash
gh release create src-v1 --title "kernel source" kernel-src.7z.*
# 或在 GitHub 网页新建 Release，把 kernel-src.7z.001 … .00N 全部拖进去
```

### 4. 触发时填写 tag

`kernel_src_release` 填 `src-v1`。workflow 会执行：

```bash
gh release download src-v1 -p 'kernel-src.7z.*' -D /tmp/ksrc
7z x -mmt=2 /tmp/ksrc/kernel-src.7z.001 -okernel
```

然后照常编译。Release asset 下载走 GitHub 内网，比 push 大仓库稳定。

---

## 四、工具链（最容易卡住的一步）

编译内核需要 4 组工具链，由 `scripts/fetch-toolchain.sh` 自动下载并归一化到 `toolchain/`：

| 组件 | 默认来源 | 备注 |
|---|---|---|
| clang `r383902b1` | AOSP `android11-qpr3-release` 归档 | Android R-QPR2 官方内核编译器 |
| aarch64 GCC 4.9 | `LineageOS/android_prebuilts_gcc_linux-x86_aarch64_...` | 分支 `lineage-19.1` |
| arm32 GCC 4.9 | `LineageOS/android_prebuilts_gcc_linux-x86_arm_...` | 分支 `lineage-19.1` |
| build-tools | `LineageOS/android_prebuilts_build-tools` | make/flex/bison/m4；失败自动回退系统工具 |

### 官方源不可达怎么办

在仓库 **Settings → Secrets and variables → Actions → Variables** 添加同名变量覆盖：

```
CLANG_ARCHIVE_URL = https://<你的镜像>/clang-r383902b1.tar.gz
GCC64_URL        = https://<你的镜像>/gcc64.tar.gz
GCC32_URL        = https://<你的镜像>/gcc32.tar.gz
BUILDTOOLS_URL   = https://<你的镜像>/build-tools.tar.gz
```

也可以是同一仓库 Release asset 的浏览器下载直链。变量为空时脚本自动用内置默认值，不会踩空。

**完全离线**：把准备好的 `toolchain/` 目录（含 `.ready` 标记）缓存进 Actions
（workflow 已配 `actions/cache`），或设置 `USE_SYSTEM_HOST_TOOLS=1` 并自备 clang。

### 本地复现（不用联网）

```bash
LOCAL_PREBUILTS=/root/lineage-18.1 ./scripts/build.sh --profile clean --jobs 4
```

该模式直接软链复用本地 AOSP 树的 `prebuilts/`，与当初编译完整 ROM 时的工具链**逐字节相同**。

---

## 五、改内核配置 / 改源码

- **只改配置**：编辑 `defconfig/sm8150-perf_defconfig.<profile>`，提交后重跑 workflow。
  `build-kernel.sh` 会在每次编译前把它覆盖到 `kernel/arch/arm64/configs/vendor/sm8150-perf_defconfig`。
- **改源码**：直接改 `kernel/` 下的文件并提交（模式 B 需重新生成 `kernel-src.7z.*`）。
- **加新档位**：在 `defconfig/` 放 `sm8150-perf_defconfig.<名字>`，并同步 workflow 的
  `options:` 与 `scripts/build.sh` 的 `case` 白名单。

局部命令（本地调试用）：

```bash
./scripts/build.sh --kernel-only --profile clean          # 只编内核不出 boot.img
./scripts/build.sh --skip-kernel  --profile clean          # 已有 out/.../Image-dtb，只重打包
./scripts/build.sh --skip-toolchain --no-verify            # 跳过工具链准备与复核
python3 tools/pack-boot.py --kernel /path/Image-dtb --profile custom --out dist/x.img --verify
./scripts/verify.sh dist/boot-clean.img                     # 单独自检任意 boot.img
```

---

## 六、更新基线 boot-ref

换 OOS/LineageOS 基线后，`boot-ref/` 需要重做，否则打包出的 cmdline/ramdisk/AVB 结构会与
新系统不匹配。步骤：

```bash
# 1) 从新 ROM 的 payload.bin 解出 boot.img（或用线刷包里的 images/boot.img）
python3 tools/unpack_bootimg.py --boot_img NEW_boot.img --out /tmp/newunpack

# 2) 用本工程附带思路重新提取 5 个资产与 boot-params.json
#    参考 boot-ref/README.md 的布局说明；关键字段：
#    partition_size / page_size / header_version / cmdline / 各 offset /
#    os_version / os_patch_level / AVB salt / descriptor 与 footer 偏移

# 3) 更新后跑一次自检
./scripts/verify.sh dist/boot-clean.img
```

> 若新基线改成 **init_boot / vendor_boot / generic kernel image（GKI）** 布局，
> 本工程的 header-v2 重组方式不再适用，需要另写打包逻辑。

---

## 七、排障

| 现象 | 原因 / 处理 |
|---|---|
| Actions 卡在 `下载 clang.tar.gz` | 官方源超时；按第四节配置 `CLANG_ARCHIVE_URL` 镜像，或勾选 `use_system_host_tools`（仍需 clang） |
| `缺少 arm32 GCC` | LineageOS 镜像分支变动；改用 `GCC32_URL` 指定可用 tarball，或检查 tarball 内前缀是 `arm-linux-androideabi-` 还是 `arm-linux-androidkernel-`（脚本已自动探测两种） |
| `bison`/`flex` 报 Kconfig 语法错 | 勾选 `use_system_host_tools` 前先确认系统版本；老内核 4.14 建议用 AOSP build-tools 的 bison |
| `gen_kheaders.sh: cpio: command not found`（`kheaders_data.tar.xz Error 127`） | `CONFIG_IKHEADERS` 需要 `cpio`。本地模式请用 `--local-prebuilts`（脚本会把 `prebuilts/tools-lineage/linux-x86/bin` 加入 PATH）；Actions 的 workflow 已 `apt install cpio`，自建 runner 需自行安装 |
| 编译被 kill / OOM | 降低 `jobs` 到 2~4；free runner 内存 16 GiB，内核单编一般够 |
| `kernel 段缺少 UNCOMPRESSED_IMG 魔数` | 用了 `Image.gz` 或 `Image`；本工程要的是 `Image-dtb`（`BOARD_KERNEL_IMAGE_NAME := Image-dtb`） |
| `payload 过大` | kernel 段超过 96 MiB 分区；检查是否误把 DTB 又拼了一次 |
| 产物刷进去不亮屏 | 先 `fastboot flash boot boot-stock.img` 还原；内核之外的 system 层问题见线刷包 `启动失败排障.md` |
| `verify-boot.py` 报两段 DTB 不一致 | `dtb.img` 与 `dtb-appended.bin` 放反了；二者内容不同，见 `boot-ref/README.md` |

---

## 八、一致性说明

本工程用原始 `Image-dtb` 走完整重打包链路，产出的 `boot-clean.img` 与已交付镜像
**sha256 完全一致**：`a217e5146adefc9306152123bf53f7e25ef1e46b17a9b1dc0dcd28706dbde5f2`。

注意：内核编译时 `scripts/mkcompile_h` 会写入编译时间戳，因此**不同时间重编的 Image 可能相差数字节**，
进而 boot.img 的 sha256 不同——这是正常的，不影响可刷性。若需要字节级复现，
用同一份 `Image-dtb` 走 `--skip-kernel` 打包即可。
