#!/usr/bin/env python3
"""xhs-topics 桌面 App 入口（独立原生 WKWebView 窗口，不走浏览器）。
- 确保 8773 server 在跑（launchd 通常已起；没起就自己起一个）
- 用 pywebview 开一个独立窗口指向 localhost:8773
依赖：pywebview + pyobjc（复用 daily-todo 的 venv，见 launch_app.sh）。
"""
import os, sys, time, threading, subprocess, urllib.request

PORT = 8773
URL = f"http://localhost:{PORT}"
DIR = os.path.expanduser("~/xhs-topics")
SERVER = os.path.join(DIR, "server.py")
SYNC_SH = os.path.join(DIR, "sync.sh")


def server_up() -> bool:
    try:
        urllib.request.urlopen(f"{URL}/topics", timeout=1)
        return True
    except Exception:
        return False


def ensure_server() -> None:
    """launchd 通常已常驻 server；万一没起，自己 spawn 一个兜底。"""
    if server_up():
        return
    try:
        subprocess.Popen([sys.executable, SERVER],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         cwd=DIR, start_new_session=True)
    except Exception:
        pass
    for _ in range(25):
        if server_up():
            return
        time.sleep(0.2)


def sync_pull() -> None:
    """开窗口前拉一次远端（其他机的改动），失败不阻塞。"""
    if not os.path.exists(SYNC_SH):
        return
    try:
        subprocess.run(["/bin/bash", SYNC_SH],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       cwd=DIR, timeout=8)
    except Exception:
        pass


# ---------- 检查更新菜单（照抄 quotes-app/daily-todo 的 MenuSetupHelper 范式）----------
# 关键点（之前 PyObjC 直接插菜单失败的原因）：
#  1. NSApp.mainMenu() 的增改必须在主线程，而 webview.start(func) 的 func 跑在 worker
#     线程 → 必须用 performSelectorOnMainThread 切回主线程，否则 silent fail。
#  2. pywebview 建原生菜单的时机不固定 → 用 0.5/1.5/3.0s 多次重试。
#  3. 菜单回调里 evaluate_js 要放子线程，否则主线程等 WKWebView completionHandler 自锁。
_window_ref = [None]
_menu_helper = [None]


def _menu_log(msg: str) -> None:
    try:
        with open("/tmp/xhs-topics-menu.log", "a", encoding="utf-8") as f:
            f.write(f"{msg}\n")
    except Exception:
        pass


def setup_app_menu() -> None:
    """启动后在 macOS App 菜单（最左侧 'T' 菜单）里加「检查更新…」，对齐 Claude.app 位置。"""
    _menu_log("setup_app_menu called")
    try:
        from AppKit import NSApp, NSMenuItem  # type: ignore
        from Foundation import NSObject       # type: ignore
    except Exception as e:
        _menu_log(f"import error: {e}")
        return

    class MenuSetupHelper(NSObject):
        def doSetup_(self, _):  # 主线程执行
            try:
                main_menu = NSApp.mainMenu()
                if not main_menu or main_menu.numberOfItems() < 1:
                    return
                app_menu = main_menu.itemAtIndex_(0).submenu()
                if not app_menu:
                    return
                for i in range(app_menu.numberOfItems()):
                    if app_menu.itemAtIndex_(i).title() == "检查更新…":
                        return  # 已插过
                item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    "检查更新…", "checkForUpdate:", "")
                item.setTarget_(self)
                app_menu.insertItem_atIndex_(item, 1)               # 插在 About 下面
                app_menu.insertItem_atIndex_(NSMenuItem.separatorItem(), 2)
                self._inserted_item = item                          # 留引用防 GC
                _menu_log("INSERTED 检查更新…")
            except Exception as e:
                _menu_log(f"doSetup error: {e}")

        def checkForUpdate_(self, sender):  # 菜单点击回调（主线程）
            def _do():
                try:
                    w = _window_ref[0]
                    if w is not None:
                        w.evaluate_js("if (typeof checkUpdate === 'function') checkUpdate(true);")
                    _menu_log("menu clicked → checkUpdate(true)")
                except Exception as e:
                    _menu_log(f"checkForUpdate error: {e}")
            threading.Thread(target=_do, daemon=True).start()

        def scheduleSetup(self):
            self.performSelectorOnMainThread_withObject_waitUntilDone_("doSetup:", None, False)

    helper = MenuSetupHelper.alloc().init()
    _menu_helper[0] = helper  # 全局 retain 防 GC
    for delay in (0.5, 1.5, 3.0):  # 菜单创建时机不固定，多次尝试
        threading.Timer(delay, helper.scheduleSetup).start()


def main() -> None:
    threading.Thread(target=sync_pull, daemon=True).start()
    ensure_server()
    import webview
    window = webview.create_window(
        "T",                       # 窗口标题（隐蔽：不写"选题"）
        URL,
        width=1100,
        height=820,
        resizable=True,
        min_size=(680, 560),
    )
    _window_ref[0] = window        # 供菜单回调 evaluate_js 用
    # setup_app_menu 在 GUI 事件循环起来后调用，内部再 performSelectorOnMainThread 切主线程插菜单
    webview.start(setup_app_menu)


if __name__ == "__main__":
    main()
