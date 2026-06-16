#!/bin/bash
# 一条命令重建 T.app（独立原生窗口版）并装到 ~/Applications。
# 换新机器时跑这个：先 clone 仓库 + 建好 venv 装依赖，再跑本脚本。
#
# 用法：
#   cd ~/xhs-topics
#   ./make_app.sh
set -e
cd "$(dirname "$0")"
DIR="$(pwd)"
PY="$DIR/venv/bin/python"
PROXY=""

echo "==> 1/5 检查 venv 与依赖"
if [ ! -x "$PY" ]; then
    echo "  venv 不存在，新建并装依赖（走代理 $PROXY）"
    python3 -m venv venv
    HTTPS_PROXY="$PROXY" HTTP_PROXY="$PROXY" "$PY" -m pip install -q \
        py2app pywebview pyobjc-framework-WebKit pyobjc-framework-Cocoa pytrends pillow
else
    # 确保打包依赖在（含画图标用的 pillow）
    if ! "$PY" -c "import webview, py2app, PIL" 2>/dev/null; then
        echo "  补装 py2app/pywebview/pillow（走代理）"
        HTTPS_PROXY="$PROXY" HTTP_PROXY="$PROXY" "$PY" -m pip install -q \
            py2app pywebview pyobjc-framework-WebKit pyobjc-framework-Cocoa pillow
    fi
fi

echo "==> 2/5 生成图标（红底大写 T）"
"$PY" - <<'PY'
from PIL import Image, ImageDraw, ImageFont
import os
S = 1024
img = Image.new("RGBA", (S, S), (0,0,0,0))
d = ImageDraw.Draw(img)
margin, radius = 96, 230
d.rounded_rectangle([margin, margin, S-margin, S-margin], radius=radius, fill=(255,46,77,255))
hl = Image.new("RGBA", (S, S), (0,0,0,0))
ImageDraw.Draw(hl).rounded_rectangle([margin,margin,S-margin,S-margin], radius=radius, fill=(255,255,255,28))
img.alpha_composite(hl.crop((0,0,S,int(S*0.46))), (0,0))
d = ImageDraw.Draw(img)
def font(sz):
    for p in ["/System/Library/Fonts/Supplemental/Georgia.ttf",
              "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
              "/System/Library/Fonts/Helvetica.ttc"]:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, sz)
            except: pass
    return ImageFont.load_default()
f = font(620); t = "T"
b = d.textbbox((0,0), t, font=f); tw, th = b[2]-b[0], b[3]-b[1]
d.text(((S-tw)/2-b[0], (S-th)/2-b[1]-20), t, font=f, fill=(255,255,255,255))
img.save("/tmp/xhs-icon-1024.png")
print("  icon png ok")
PY
ICONSET=/tmp/xhs.iconset; rm -rf "$ICONSET"; mkdir -p "$ICONSET"
for sz in 16 32 64 128 256 512 1024; do
    sips -z $sz $sz /tmp/xhs-icon-1024.png --out "$ICONSET/icon_${sz}x${sz}.png" >/dev/null 2>&1
done
cp "$ICONSET/icon_32x32.png"     "$ICONSET/icon_16x16@2x.png"
cp "$ICONSET/icon_64x64.png"     "$ICONSET/icon_32x32@2x.png"
cp "$ICONSET/icon_256x256.png"   "$ICONSET/icon_128x128@2x.png"
cp "$ICONSET/icon_512x512.png"   "$ICONSET/icon_256x256@2x.png"
cp "$ICONSET/icon_1024x1024.png" "$ICONSET/icon_512x512@2x.png"
iconutil -c icns "$ICONSET" -o "$DIR/app-icon.icns"
echo "  app-icon.icns ok"

echo "==> 3/5 py2app 打包"
rm -rf build dist
"$PY" setup.py py2app >/tmp/xhs-py2app.log 2>&1
[ -d dist/T.app ] || { echo "  打包失败，看 /tmp/xhs-py2app.log"; exit 1; }
echo "  dist/T.app ok"

echo "==> 4/5 装到 ~/Applications"
mkdir -p ~/Applications
[ -d ~/Applications/T.app ] && mv ~/Applications/T.app "/tmp/T.app.old.$(date +%s)"
cp -R dist/T.app ~/Applications/T.app
touch ~/Applications/T.app
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f ~/Applications/T.app 2>/dev/null || true

echo "==> 5/5 完成"
echo "  T.app 已装到 ~/Applications/T.app"
echo "  把它拖进 Dock 即可（或：open ~/Applications/T.app 测试）"
