# patches：内核源码相对 LineageOS 官方的改动

`kernel/` 目录已经是**应用过改动**的源码树，直接可编译。这里的 patch 只是留档与追溯用，
正常编译**不需要手动打补丁**。

| 文件 | 说明 |
|---|---|
| `kernel-custom.patch` | `git diff` 快照，2 个文件 / +121 −1 行 |

## 改动内容

1. **`arch/arm64/configs/vendor/sm8150-perf_defconfig`**（+120 行）
   - `CONFIG_HIDRAW=y`、`CONFIG_HID=y`、`USB_HID`、`HID_GENERIC` 等 HID 栈
   - 华为 VR Glass 相关：BT HIDP / BT LE、`DRM_MSM`、`POWER_SUPPLY`、USB PD 栈显式声明
   - Docker / 容器能力：namespaces、`IP_VS`、`VETH`、`BRIDGE`、netfilter、`POSIX_MQUEUE`
   - 因 VINTF 兼容性检查冲突，关闭了 `CONFIG_SYSVIPC` / `CONFIG_SYSVIPC_SYSCTL`
   - 对应 `defconfig/sm8150-perf_defconfig.custom`

2. **`scripts/mkcompile_h`**（1 行）
   - 用 `head -n1` 取编译环境版本号，避免本机 CUDA/nvcc 版本字符串污染内核 version magic
   - 纯构建环境修复，不改变运行时行为，三档配置都保留

## 三档 defconfig 的关系

```
sm8150-perf_defconfig.stock   官方原版（794 行）
        │  + CONFIG_HIDRAW=y
        ▼
sm8150-perf_defconfig.clean   官方 + 仅 hidraw（798 行，默认档，已实测可开机）
        │  + 120 行 VR/Docker/供电定制
        ▼
sm8150-perf_defconfig.custom  当前定制版（914 行）
```

`scripts/build-kernel.sh` 每次编译前把所选档位覆盖到
`kernel/arch/arm64/configs/vendor/sm8150-perf_defconfig`，所以 `kernel/` 里那份
defconfig 的内容不影响构建结果。

## 想回到纯官方

```bash
cp defconfig/sm8150-perf_defconfig.stock kernel/arch/arm64/configs/vendor/sm8150-perf_defconfig
git -C /path/to/original/kernel show HEAD:scripts/mkcompile_h > kernel/scripts/mkcompile_h
```
