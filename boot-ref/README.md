# boot-ref：重建 boot.img 所需的原版参考资产

这些文件从 **已编译成功的 LineageOS 18.1 `boot.img`**（sha256 `016c1b97…b28657`）中提取，
目的是让本工程**不需要携带 96 MiB 的原版 boot.img** 也能逐字节复刻其布局。

| 文件 | 大小 | 用途 |
|---|---|---|
| `boot-params.json` | — | 全部 mkbootimg 参数 + AVB hash footer 结构参数 |
| `ramdisk.img` | 829,310 B | header v2 的 ramdisk 段，原样复用 |
| `dtb.img` | 4,255,649 B | header v2 的 `--dtb` 段，原样复用 |
| `dtb-appended.bin` | 4,255,649 B | kernel 段内 appended DTB 区，原样复用 |
| `avb/footer.bin` | 64 B | `AVBf` footer 模板（末 64 字节） |
| `avb/vbmeta-blob.bin` | 704 B | `AVB0` vbmeta hash blob（含 salt、descriptor、root_digest 槽位） |

> ⚠️ **`dtb.img` 与 `dtb-appended.bin` 长度相同但内容不同**（sha256 分别是
> `8f211ce3…` 和 `5a47f624…`）。前者进 header v2 的 dtb 段，后者拼在 kernel 尾部，
> 二者不可互换。这是本工程最容易踩的坑。

## 为什么这样做

原版 `boot.img` 是 96 MiB 的 AVB hash-footer 镜像：

```
[0 .. 57,933,824)          mkbootimg 生成的裸镜像（payload）
[57,933,824 .. +704)       AVB0 vbmeta blob（sha256 hash descriptor）
[ … 零填充 … ]             到 96 MiB - 64
[最后 64 B]                AVBf footer
```

`pack-boot.py` 只替换 payload 里的 kernel 段，其余字节全部来自本目录；
然后按新 payload 长度重算 descriptor 的 `image_size` 与 `root_digest`，
以及 footer 的 `original_image_size` / `vbmeta_offset`。因为使用的是
test-keys 的**无签名 hash footer**，重算 digest 即可，无需私钥。

## 更换基线

若将来 OOS/LineageOS 基线 boot 变了，用 `unpack_bootimg.py` 解出新 boot，
重新生成这 5 个资产并更新 `boot-params.json` 即可（生成脚本见
`GitHub编译指南.md` 的「更新基线」一节）。
