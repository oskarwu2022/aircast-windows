# 第三方组件与许可证

本仓库自身的代码是 MIT（见 LICENSE）。发行包（Release 里的 zip）中**包含**下列第三方二进制，
它们各有自己的许可证，发布/分发时必须保留其声明。

| 组件 | 版本（本仓库验证过） | 许可证 | 说明 |
|---|---|---|---|
| [UxPlay](https://github.com/FDH2/UxPlay) | 1.74 | **GPLv3** | AirPlay 2 接收实现，编译产物为 `runtime/uxplay.exe`。网页/README 中引用并分发其二进制时需遵守 GPLv3（附源码链接即可满足分发要求：源码随上游公开）。 |
| [GStreamer](https://gstreamer.freedesktop.org/) 及其插件 | 1.28.x（MSYS2 `mingw-w64-ucrt-x86_64-gstreamer*`） | **LGPL-2.1+**（部分插件为 GPL / 其他） | `runtime/gstreamer-1.0/` 与相关 DLL。 |
| FFmpeg（经 gst-libav 引入） | 7.x | LGPL/GPL（视编译选项） | `runtime/av*.dll`、`swscale`、`swresample`。 |
| [qrcode](https://github.com/lincolnloop/python-qrcode) | 8.2（`app/vendor/qrcode`） | BSD-3-Clause | 纯 Python，仅用于在界面里画二维码。 |
| Python / Tcl-Tk | 3.12 / 8.6 | PSF / BSD 风格 | 由 PyInstaller 打进 `_internal/`。 |

## 关于 GPLv3 的合规提示

`AirCast.exe`（MIT）通过**独立的进程调用** `runtime/uxplay.exe`（GPLv3），两者不链接、
不共享地址空间，因此本仓库的 Python 外壳可以继续使用 MIT。

但 **如果你打包并分发包含 `uxplay.exe` 与 GStreamer 的 zip**：

1. 保留本文件与 LICENSE；
2. 明确标注 zip 内含 GPLv3（UxPlay）与 LGPL（GStreamer）组件，并给出上游源码链接；
3. 不要声称整个发行包都是 MIT。

若不想承担 GPL 分发义务，Release 中只提供**源码 + 构建脚本**，让用户在自己的机器上自行构建
（本仓库的 GitHub Actions 默认会构建，但你可以关闭“上传 zip 到 Release”的步骤）。
