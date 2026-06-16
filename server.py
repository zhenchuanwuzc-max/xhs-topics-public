#!/usr/bin/env python3
"""
xhs-topics 小红书选题看板 本地 HTTP 服务
- GET    /              → 返回 index.html
- GET    /topics        → 返回 topics.json
- POST   /topics/add    → 单条新增（锁内安全写 + 去重 + git 同步）
- PATCH  /topics/{id}   → 改 status / score / stats / 任意字段
- DELETE /topics/{id}   → 删除
- 数据源：~/xhs-topics/topics.json
数据结构：{ "updated": ISO8601, "topics": [ {...}, ... ] }

设计参考 daily-todo：原子写（备份+tmp+fsync+rename）+ _write_lock + 防抖 git 同步。
"""
import json
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    TZ = None

PORT = 8773

# 代码目录 = server.py 所在（代码仓）；数据目录走 XHS_DATA_DIR env，回退 ~/xhs-topics-data 再回退 ~/xhs-topics
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("XHS_DATA_DIR", "")
if not DATA_DIR:
    for _cand in ("~/xhs-topics-data", "~/xhs-topics"):
        _p = os.path.expanduser(_cand)
        if os.path.isdir(_p):
            DATA_DIR = _p
            break
    else:
        DATA_DIR = "~/xhs-topics-data"
DATA_DIR = os.path.expanduser(DATA_DIR)
DATA_FILE = os.path.join(DATA_DIR, "topics.json")

APP_SUPPORT_DIR = os.path.expanduser("~/Library/Application Support/xhs-topics")
BACKUP_DIR = os.path.join(APP_SUPPORT_DIR, "backups")
BACKUP_KEEP = 7

# 状态流转合法值（看板 5 列）
STATUSES = ["idea", "todo", "shot", "published", "dropped"]
PLATFORMS = ["xhs", "ins", "both"]


def now_iso() -> str:
    now = datetime.now(TZ) if TZ else datetime.now()
    return now.isoformat(timespec="seconds")


def new_id() -> str:
    """跨机 UUID id，避免两台 Mac 同时新增撞 id"""
    return f"x-{uuid.uuid4().hex[:12]}"


# ---------- 资源定位 ----------
def get_resource_path(name: str) -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    full = os.path.join(here, name)
    if os.path.exists(full):
        return full
    return os.path.join(DATA_DIR, name)


HTML_FILE = get_resource_path("index.html")


# ---------- 备份 ----------
def backup_data() -> None:
    """写前时间戳备份，保留最近 BACKUP_KEEP 份。失败不阻断主流程。"""
    if not os.path.exists(DATA_FILE):
        return
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(DATA_FILE, os.path.join(BACKUP_DIR, f"topics-{ts}.json"))
        backups = sorted(
            f for f in os.listdir(BACKUP_DIR)
            if f.startswith("topics-") and f.endswith(".json")
        )
        for old in backups[:-BACKUP_KEEP]:
            try:
                os.unlink(os.path.join(BACKUP_DIR, old))
            except Exception:
                pass
    except Exception:
        pass


# ---------- 读 ----------
def read_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {"updated": now_iso(), "topics": []}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    # 用文件 mtime 覆盖 updated → 外部直接改文件也能被页面 polling 感知
    mtime = os.path.getmtime(DATA_FILE)
    data["updated"] = datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
    if "topics" not in data:
        data["topics"] = []
    return data


# ---------- 防抖 git 同步 ----------
_sync_timer = None
_sync_lock = threading.Lock()


def schedule_sync(delay: float = 5.0) -> None:
    global _sync_timer
    sync_sh = os.path.join(DATA_DIR, "sync.sh")
    if not os.path.exists(sync_sh):
        return
    with _sync_lock:
        if _sync_timer is not None:
            _sync_timer.cancel()
        _sync_timer = threading.Timer(delay, _run_sync, args=[sync_sh])
        _sync_timer.daemon = True
        _sync_timer.start()


def _run_sync(sync_sh: str) -> None:
    try:
        subprocess.Popen(
            ["/bin/bash", sync_sh],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=DATA_DIR,
            start_new_session=True,
        )
    except Exception:
        pass


# ---------- 原子写 ----------
_write_lock = threading.RLock()


def _atomic_write(data: dict) -> None:
    """假定调用方已持有 _write_lock。备份 → tmp + fsync + rename。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    data["updated"] = now_iso()
    backup_data()
    tmp = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=DATA_DIR, delete=False, suffix=".tmp"
    )
    try:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp.name, DATA_FILE)
    except Exception:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
        raise


def _load_locked() -> dict:
    """锁内读最新磁盘内容（不走 read_data 的 mtime 覆盖，保留真实 updated）"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"updated": None, "topics": []}
    if "topics" not in data:
        data["topics"] = []
    return data


# ---------- 业务：新增 ----------
def add_topic(item: dict):
    """锁内 read-append-write。同标题未弃用 → 幂等去重。返回 (topic, existed)。"""
    title = (item.get("title") or "").strip()
    if not title:
        raise ValueError("title required")
    platform = item.get("platform") if item.get("platform") in PLATFORMS else "xhs"
    with _write_lock:
        data = _load_locked()
        topics = data["topics"]
        norm = title.replace(" ", "").lower()
        for t in topics:
            if t.get("status") != "dropped" and \
               t.get("title", "").replace(" ", "").lower() == norm:
                return t, True  # 已存在未弃用 → 幂等
        topic = {
            "id": new_id(),
            "title": title,
            "note": str(item.get("note") or ""),
            "platform": platform,
            "status": "idea",
            # 默认 null = 未打分（不再默认 3，避免被误读为"已评估的真实分"）
            "score_heat": None,
            "score_fit": None,
            "score_money": None,
            "tags": item.get("tags") or [],
            "keyword": str(item.get("keyword") or ""),  # 空则刷新时用标题
            "ext_heat": None,                            # 外部热度(Google搜索大盘)，抓不到就 None=空着
            "ext_heat_updated": None,                    # 上次刷新时间
            "created": now_iso(),
            "published_at": None,
            "stats": {"views": None, "clicks": None, "likes": None,
                      "follows": None, "comments": None},
        }
        topics.append(topic)
        data["topics"] = topics
        _atomic_write(data)
    schedule_sync()
    return topic, False


# ---------- 业务：改字段 ----------
ALLOWED_FIELDS = {"title", "note", "platform", "status", "tags",
                  "score_heat", "score_fit", "score_money", "keyword"}


def patch_topic(topic_id: str, patch: dict) -> dict:
    """锁内 read-modify-write。支持顶层字段 + stats 子字段。
    status 改为 published 且原本没 published_at → 自动盖 published_at。
    找不到 id raises KeyError。"""
    if not topic_id:
        raise ValueError("topic_id required")
    with _write_lock:
        data = _load_locked()
        target = None
        for t in data["topics"]:
            if t.get("id") == topic_id:
                target = t
                break
        if target is None:
            raise KeyError(topic_id)

        for k, v in patch.items():
            if k in ALLOWED_FIELDS:
                if k in ("score_heat", "score_fit", "score_money"):
                    # null = 取消打分（回到未打分态）；有值则 clamp 1-5
                    target[k] = None if v is None else max(1, min(5, int(v)))
                    # 手动改流量分 → 清掉 AI 标记（变成 Ocean 的手打分，不再是 AI 建议）
                    if k == "score_heat":
                        target["score_heat_source"] = None
                        target["score_heat_reason"] = None
                elif k == "status" and v not in STATUSES:
                    continue
                elif k == "platform" and v not in PLATFORMS:
                    continue
                else:
                    target[k] = v
            elif k == "stats" and isinstance(v, dict):
                cur = target.get("stats") or {}
                for sk in ("views", "clicks", "likes", "follows", "comments"):
                    if sk in v:
                        cur[sk] = v[sk]
                target["stats"] = cur

        # status → published 自动盖发布时间
        if target.get("status") == "published" and not target.get("published_at"):
            target["published_at"] = now_iso()

        _atomic_write(data)
    schedule_sync()
    return target


# ---------- 业务：删除 ----------
def delete_topic(topic_id: str) -> bool:
    with _write_lock:
        data = _load_locked()
        before = len(data["topics"])
        data["topics"] = [t for t in data["topics"] if t.get("id") != topic_id]
        if len(data["topics"]) == before:
            return False
        _atomic_write(data)
    schedule_sync()
    return True


# ---------- 业务：AI 评「流量」分 ----------
# ⚠️ 只评流量（会不会火），不评契合/变现（AI 不懂 Ocean 账号定位/产品，会瞎猜 = 假数据）。
# ⚠️ AI 给的流量分是"主观建议"不是"客观真值"：写回时标 score_heat_source="ai"，前端强区分。
# 调本机 claude CLI 绝对路径（plan-reviewer 反对外挂 CLI 但 Ocean 拍板用 CLI）：
#   - 绝对路径优先，找不到再退 PATH
#   - 失败/超时/解析失败 → 明确报错，绝不静默写假分
import re

CLAUDE_BIN_CANDIDATES = [
    os.path.expanduser("~/.local/bin/claude"),
    "/opt/homebrew/bin/claude",
    "/usr/local/bin/claude",
]


def _find_claude():
    for p in CLAUDE_BIN_CANDIDATES:
        if os.path.exists(p):
            return p
    return shutil.which("claude")


def ai_score_heat(topic_id: str) -> dict:
    """拿 title+note 调 claude，只给流量打 1-5 分 + 理由。返回 {ok, score, reason} 或 {ok:False, error}。"""
    data = _load_locked()
    target = next((t for t in data["topics"] if t.get("id") == topic_id), None)
    if target is None:
        return {"ok": False, "error": "选题不存在"}

    claude = _find_claude()
    if not claude:
        return {"ok": False, "error": "找不到 claude CLI（沙箱内常见，浏览器版可用）"}

    title = target.get("title", "")
    note = target.get("note", "")
    prompt = (
        "你是小红书爆款判断助手。只评估这条选题的【流量潜力】（会不会火/有没有爆款相），"
        "不要评其他维度。考虑标题钩子、话题热度、受众规模。\n"
        f"标题：{title}\n角度：{note or '（无）'}\n"
        "严格只输出一行 JSON，不要任何解释或代码围栏，格式："
        '{"score": <1到5的整数>, "reason": "<20字以内中文理由>"}'
    )
    try:
        proc = subprocess.run(
            [claude, "-p", prompt],
            capture_output=True, text=True, timeout=60, cwd=DATA_DIR,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "AI 评分超时（60s）"}
    except Exception as e:
        return {"ok": False, "error": f"调用 claude 失败：{e}"}

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:160]
        return {"ok": False, "error": f"claude 报错：{err or '未登录？(401)'}"}

    out = (proc.stdout or "").strip()
    m = re.search(r"\{.*\}", out, re.DOTALL)  # 抠出 JSON，容忍前后废话/围栏
    if not m:
        return {"ok": False, "error": f"AI 输出无法解析：{out[:80]}"}
    try:
        parsed = json.loads(m.group(0))
        score = int(parsed["score"])
        score = max(1, min(5, score))
        reason = str(parsed.get("reason", ""))[:40]
    except Exception:
        return {"ok": False, "error": f"AI 输出格式错误：{out[:80]}"}

    # 写回 score + AI 标记（一个写块；不走 patch_topic 因为它会清 AI 标记）
    with _write_lock:
        d2 = _load_locked()
        for t in d2["topics"]:
            if t.get("id") == topic_id:
                t["score_heat"] = score
                t["score_heat_source"] = "ai"
                t["score_heat_reason"] = reason
                break
        _atomic_write(d2)
    schedule_sync()
    return {"ok": True, "score": score, "reason": reason}


# ---------- 业务：检查更新（git pull 拉远端最新代码）----------
# T.app 是本地壳 + git 同步：没有安装包服务器，"检查更新" = 从远端拉最新代码。
# 代码文件（index.html / server.py 等）有变化 → updated=True，提示用户重启 App 生效。
CODE_FILES = ("index.html", "server.py", "desktop_app.py", "heat_refresh.py")


def check_update() -> dict:
    """git fetch+pull origin。返回 {updated, before, after, changed_files, message}。
    topics.json 走合并驱动不算代码更新，只看代码文件是否变。"""
    if not os.path.isdir(os.path.join(SCRIPT_DIR, ".git")):
        return {"ok": False, "error": "不是 git 仓库，无法检查更新"}

    def git(*args, timeout=20):
        return subprocess.run(["git", *args], cwd=SCRIPT_DIR, capture_output=True,
                              text=True, timeout=timeout)

    try:
        before = git("rev-parse", "HEAD").stdout.strip()
        fetch = git("fetch", "origin", timeout=30)
        if fetch.returncode != 0:
            return {"ok": False, "error": "拉取远端失败（网络/代理？）：" + (fetch.stderr or "").strip()[:200]}
        # 当前分支
        branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "main"
        pull = git("pull", "--ff-only", "origin", branch, timeout=30)
        after = git("rev-parse", "HEAD").stdout.strip()
        if after == before:
            return {"ok": True, "updated": False, "before": before[:7], "after": after[:7],
                    "message": "已是最新版本"}
        # 算改了哪些代码文件
        diff = git("diff", "--name-only", before, after).stdout.split()
        changed_code = [f for f in diff if f in CODE_FILES]
        return {"ok": True, "updated": True, "before": before[:7], "after": after[:7],
                "changed_files": diff, "changed_code": changed_code,
                "needs_restart": bool(changed_code),
                "message": f"已更新到最新（{before[:7]} → {after[:7]}）"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "检查更新超时（网络慢/代理未通）"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------- HTTP ----------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # 静默

    def _send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            try:
                with open(HTML_FILE, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        elif self.path == "/topics":
            try:
                self._send_json(read_data())
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/topics/add":
            try:
                item = self._read_body()
                topic, existed = add_topic(item)
                self._send_json({"ok": True, "topic": topic, "existed": existed})
            except ValueError as e:
                self._send_json({"error": str(e)}, 400)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        elif self.path == "/refresh-heat":
            # 异步触发外部热度刷新脚本，立即返回（不阻塞页面）
            try:
                script = os.path.join(SCRIPT_DIR, "heat_refresh.py")
                py = os.path.join(SCRIPT_DIR, "venv", "bin", "python")
                if not os.path.exists(py):
                    py = "python3"
                if os.path.exists(script):
                    subprocess.Popen([py, script],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     cwd=SCRIPT_DIR, start_new_session=True)
                    self._send_json({"ok": True, "started": True})
                else:
                    self._send_json({"error": "heat_refresh.py 不存在"}, 404)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        elif self.path.startswith("/ai-score/") and self.path.count("/") == 2:
            # AI 评流量分：POST /ai-score/{id}，调 claude CLI 只评流量
            topic_id = self.path.split("/")[-1]
            try:
                self._send_json(ai_score_heat(topic_id))
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        elif self.path == "/check-update":
            # 检查更新：git pull 拉远端最新代码。供桌面 App 菜单「Check for Updates」调用。
            try:
                self._send_json(check_update())
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        else:
            self._send_json({"error": "not found"}, 404)

    def do_PATCH(self):
        # PATCH /topics/{id}
        if self.path.startswith("/topics/") and self.path.count("/") == 2:
            topic_id = self.path.split("/")[-1]
            try:
                patch = self._read_body()
                topic = patch_topic(topic_id, patch)
                self._send_json({"ok": True, "topic": topic})
            except KeyError:
                self._send_json({"error": "not found"}, 404)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        else:
            self._send_json({"error": "not found"}, 404)

    def do_DELETE(self):
        if self.path.startswith("/topics/") and self.path.count("/") == 2:
            topic_id = self.path.split("/")[-1]
            try:
                ok = delete_topic(topic_id)
                self._send_json({"ok": ok})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        else:
            self._send_json({"error": "not found"}, 404)


def main():
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print(f"xhs-topics already running on {PORT}, skip.")
        return
    print(f"xhs-topics running at http://localhost:{PORT}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
