"""py2app 打包脚本（独立原生窗口 App）。
用法：
    cd ~/xhs-topics
    rm -rf build dist
    ./venv/bin/python setup.py py2app
产物：dist/T.app
"""
from setuptools import setup

APP = ["desktop_app.py"]
DATA_FILES = ["index.html", "server.py"]

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "app-icon.icns",
    "plist": {
        "CFBundleName": "T",
        "CFBundleDisplayName": "T",
        "CFBundleIdentifier": "com.ocean.xhs-topics",
        "CFBundleVersion": "1.1.0",
        "CFBundleShortVersionString": "1.1.0",
        "NSHighResolutionCapable": True,
        "LSUIElement": False,
        "LSMinimumSystemVersion": "11.0",
    },
    "packages": ["webview"],
    "includes": [
        "server", "json", "http.server", "urllib.request",
        "Foundation", "WebKit", "AppKit", "zoneinfo",
    ],
    "excludes": ["tkinter", "test", "unittest", "pytrends", "pandas", "numpy"],
}

setup(
    app=APP,
    name="T",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
