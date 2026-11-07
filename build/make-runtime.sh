#!/bin/bash
# 把 uxplay.exe 及其 DLL 依赖 + GStreamer 插件收集成可移植的 runtime/ 目录
# 用法（MSYS2 UCRT64 终端）： bash build/make-runtime.sh
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RT="$REPO_ROOT/runtime"
SRC=/ucrt64
UXPLAY_EXE="$REPO_ROOT/.work/UxPlay/build/uxplay.exe"

if [ ! -f "$UXPLAY_EXE" ]; then
    echo "找不到 $UXPLAY_EXE，请先运行 build/build-uxplay.sh" >&2
    exit 1
fi

rm -rf "$RT"
mkdir -p "$RT/gstreamer-1.0"

cp "$UXPLAY_EXE" "$RT/"
# 可选：带上排查工具（体积很小）
for t in gst-launch-1.0.exe gst-inspect-1.0.exe gst-device-monitor-1.0.exe gst-plugin-scanner.exe; do
    [ -f "$SRC/bin/$t" ] && cp "$SRC/bin/$t" "$RT/"
done
cp "$SRC/lib/gstreamer-1.0/"*.dll "$RT/gstreamer-1.0/"

echo "== 收集 DLL 依赖 =="
cd "$RT"
{
    ldd "$UXPLAY_EXE"
    for t in ./gst-*.exe; do [ -f "$t" ] && ldd "$t"; done
    for f in ./gstreamer-1.0/*.dll; do ldd "$f"; done
} 2>/dev/null | grep -oiE '/ucrt64/bin/[A-Za-z0-9._+-]+\.dll' | sort -u > /tmp/aircast-deps.txt

count=0
while read -r p; do
    [ -z "$p" ] && continue
    base=$(basename "$p")
    [ -f "$RT/$base" ] && continue
    cp "$p" "$RT/$base" && count=$((count + 1))
done < /tmp/aircast-deps.txt
echo "复制了 $count 个依赖 DLL"

# 少数插件的依赖可能没被 ldd 解析出来（缺了只会在日志里报一条 warning），直接剔除
for p in libgstcodec2json.dll; do
    rm -f "$RT/gstreamer-1.0/$p"
done

echo "== runtime 体积 =="
du -sh "$RT"
echo "下一步：build/build-exe.ps1"
