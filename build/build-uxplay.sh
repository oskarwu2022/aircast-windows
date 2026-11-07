#!/bin/bash
# 编译 UxPlay（Windows 下的 AirPlay 接收内核），需要 MSYS2 UCRT64 环境
# 用法（在 MSYS2 UCRT64 终端里）：  bash build/build-uxplay.sh
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$REPO_ROOT/.work"
mkdir -p "$WORK"
cd "$WORK"

if [ ! -d UxPlay ]; then
    echo "== 拉取 UxPlay 源码 =="
    # 直连 github 失败时改用镜像：https://ghproxy.net/https://github.com/FDH2/UxPlay.git
    git clone --depth 1 https://github.com/FDH2/UxPlay.git
fi

cd UxPlay
rm -rf build
mkdir -p build
cd build

# -DUSE_MDNS=1 : 用 UxPlay 内置 mDNS 广播，无需安装 Bonjour
cmake .. -G Ninja -DCMAKE_BUILD_TYPE=Release -DUSE_MDNS=1
ninja

echo "== 完成 =="
ls -l uxplay.exe
echo "下一步：bash build/make-runtime.sh"
