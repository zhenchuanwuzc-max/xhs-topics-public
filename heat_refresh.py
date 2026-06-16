#!/usr/bin/env python3
"""外部热度刷新（cron 每天跑 / 前端"立即刷新"触发）。

诚实原则（Ocean 拍板 + plan-reviewer 必修）：
- 抓 Google Trends 大盘搜索热度，写入 topic.ext_heat
- 这是"全网搜索热度"，不是"小红书站内潜力"——字段语义已在前端注明
- 抓不到 / 0 / 报错 → 写 None（空着），绝不映射成分数、绝不编造
- ext_heat 不进综合分，只当参考
- 失败保留旧值，不阻塞

只刷新 status 为 idea/todo/shot 的选题（已发布/弃用的不刷）。
"""
import os, sys, json, time, tempfile
from datetime import datetime

os.environ.setdefault("HTTPS_PROXY", "http://127.0.0.1:7897")
os.environ.setdefault("HTTP_PROXY", "http://127.0.0.1:7897")

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    TZ = None

# 数据目录走 XHS_DATA_DIR env，回退 ~/xhs-topics-data 再回退 ~/xhs-topics（与 server.py 一致）
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
LOG = "/tmp/xhs-topics-heat.log"
ACTIVE = {"idea", "todo", "shot"}


def log(msg):
    line = f"[heat {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def now_iso():
    n = datetime.now(TZ) if TZ else datetime.now()
    return n.isoformat(timespec="seconds")


def fetch_heat(pt, keyword, retries=3):
    """返回 int(0-100) 或 None。抓不到/0/报错一律 None（空着，不编造）。"""
    for i in range(retries):
        try:
            pt.build_payload([keyword], timeframe="now 7-d", geo="")
            df = pt.interest_over_time()
            if df.empty or keyword not in df.columns:
                return None  # 无数据 → 空
            vals = [int(x) for x in df[keyword].tolist()]
            nz = [v for v in vals if v > 0]
            if not nz:
                return None  # 全 0 → 空（不写 0 分）
            return round(sum(vals) / len(vals))  # 近7天平均 0-100
        except Exception as e:
            en = type(e).__name__
            if i < retries - 1:
                wait = 15 * (i + 1)
                log(f"  retry {keyword}: {en}, wait {wait}s")
                time.sleep(wait)
                continue
            log(f"  FAIL {keyword}: {en} → 保留旧值")
            return "KEEP"  # 抓取失败 → 保留旧值（区别于"确认无数据"的 None）
    return "KEEP"


def main():
    if not os.path.exists(DATA_FILE):
        log("topics.json 不存在，退出")
        return
    try:
        from pytrends.request import TrendReq
    except ImportError:
        log("pytrends 未装（venv/bin/pip install pytrends），退出")
        return

    data = json.load(open(DATA_FILE, encoding="utf-8"))
    topics = data.get("topics", [])
    targets = [t for t in topics if t.get("status") in ACTIVE]
    log(f"开始刷新 {len(targets)}/{len(topics)} 条活跃选题")

    pt = TrendReq(hl="zh-CN", tz=480, timeout=(10, 25))
    n_ok = n_empty = n_keep = 0
    for t in targets:
        kw = (t.get("keyword") or "").strip() or t.get("title", "").strip()
        if not kw:
            continue
        v = fetch_heat(pt, kw)
        if v == "KEEP":
            n_keep += 1  # 不动 ext_heat
        else:
            t["ext_heat"] = v          # int 或 None（空着）
            t["ext_heat_updated"] = now_iso()
            if v is None:
                n_empty += 1
                log(f"  空  | {kw}")
            else:
                n_ok += 1
                log(f"  {v:>3} | {kw}")
        time.sleep(8)  # 防 429

    # 原子写回
    tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=DATA_DIR,
                                      delete=False, suffix=".tmp")
    try:
        data["updated"] = now_iso()
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp.flush(); os.fsync(tmp.fileno()); tmp.close()
        os.replace(tmp.name, DATA_FILE)
    except Exception as e:
        os.unlink(tmp.name)
        log(f"写回失败: {e}")
        return
    log(f"完成：有值 {n_ok} / 空着 {n_empty} / 抓失败保留 {n_keep}")

    # 触发 git 同步
    sync = os.path.join(DATA_DIR, "sync.sh")
    if os.path.exists(sync):
        import subprocess
        subprocess.Popen(["/bin/bash", sync], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, cwd=DATA_DIR, start_new_session=True)


if __name__ == "__main__":
    main()
