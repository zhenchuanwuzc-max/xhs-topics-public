# 小红书选题库（xhs-topics）

> 本地 App，记录小红书/INS 选题：表格管理 → 选题→拍→发 状态流转 → 打分排序（流量/契合/变现）→ 外部热度参考 → 发布后数据回收。
> 技术底座复刻 daily-todo（Python 单文件 + 单页 HTML + JSON + git 多机同步 + launchd 自启）。
> 端口：**8773** ｜ 数据：`~/xhs-topics/topics.json` ｜ 仓库：<your-repo>（私有）

---

## 一、日常怎么用（最常看这段）

**打开**：浏览器访问 → http://localhost:8773
（建议存成书签，开机自启后随时能开）

界面是**表格形态**：一条选题一行，列对齐；顶部按状态 tab 切换，点列头排序。

### 加选题
1. 顶栏输入框填**标题**（必填）+ **一句话角度**（可选）
2. 选**平台**（小红书 / INS / 通用）
3. 回车 或 点「+ 添加」→ 进「💡灵感」

### 打分（三个维度，点圆点打 1-5 分）
| 维度 | 测什么 |
|---|---|
| **流量** | 这选题会不会火 |
| **契合** | 和你账号定位搭不搭 |
| **变现** | 能不能引到产品/私域（直挂你的变现目标）|

- **综合分** = 三项之和（1-15），自动算
- 点列头「综合」排序，一眼看出先拍哪个

### 状态切换（顶部 tab）
顶部 tab 切换看哪类，行内下拉框改状态：

| 状态 | 含义 |
|---|---|
| 💡 灵感 | 随手记的点子 |
| 📋 待拍 | 决定要做、还没拍 |
| 🎬 已拍待发 | 拍完了、还没发 |
| ✅ 已发布 | 发出去了（自动记发布日期）|
| 🗑 弃用 | 不做了（不删，留痕）|

### 外部热度（真实数据参考，每天9点自动抓）
- **外部热度**列 = Google 搜索大盘热度（0-100），每天 9:00 自动刷新，也可点右上「🔄 立即刷新热度」手动抓
- ⚠️ **它是全网搜索热度，不是小红书站内数据**；**只当参考、不进综合分**
- **抓不到就显示「—」（空着），绝不瞎填假分数**——这是刻意的：冷门/长尾词在 Google 上常无数据（正常现象，不代表小红书没潜力）
- 点选题标题下的「🔑 关键词」可改搜索词（默认用标题；改成更通用的词能提高命中，如把「我的AI工作流复盘」改成「AI工作流」）
- 真正能判断"哪类选题在小红书有潜力"的是**下面的发布后数据回收**（那才是站内真实数据）

### 发布后数据回收（站内真实数据）
- 选题状态改「✅已发布」后，行下方点「展开数据」，填 5 个格：
  **曝光 / 点击 / 点赞 / 涨粉 / 评论**
- 直接填数字，填完点别处即自动保存
- 用来复盘：哪类选题数据真的好——**这是你最该看的判断依据**

### 筛选 & 删除
- 顶部平台 chip：只看小红书 / 只看 INS / 全部
- 行尾 ✕ 删除（会二次确认）

---

## 二、开机自启（已配好 ✅）

已通过 launchd 配置：**开机/登录自动启动 + 崩溃自动拉起**（KeepAlive）。
不用手动开，关机重启后浏览器直接开 http://localhost:8773 就有。

### 自启相关命令（一般用不到，排障时用）
```bash
# 看是否在运行
launchctl list | grep xhs-topics

# 手动重启服务
launchctl kickstart -k gui/$(id -u)/com.ocean.xhs-topics

# 临时停掉自启
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.ocean.xhs-topics.plist

# 重新开启自启
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ocean.xhs-topics.plist

# 看日志
cat ~/Library/Logs/xhs-topics.out.log
cat ~/Library/Logs/xhs-topics.err.log
```

### 手动启动（不靠 launchd 时）
```bash
cd ~/xhs-topics && ./start.sh
```

---

## 三、多机 git 同步（⏳ 待你建空仓后启用）

机制和 daily-todo 完全一样：每次改动 5 秒后自动 commit + push；另一台 Mac 拉取时
`topics.json` 走 JSON 并集合并驱动（`json-merge.py`），两台同时加选题也不会冲突。

### 状态：✅ 已启用
- 私仓：<your-repo> （已建好、已推送）
- 这台机每次改动 5 秒后自动 commit + push（防抖）
- 合并驱动已注册，两台 Mac 同时改也不会产生冲突标记

### 换到家里电脑（当前部署在公司电脑 `U-4C2VW2RD-0119`）
```bash
git clone <your-repo>.git ~/xhs-topics
cd ~/xhs-topics
chmod +x *.sh server.py heat_refresh.py json-merge.py desktop_app.py

# 1) 配主服务自启 + 每天9点热度 cron
cp com.ocean.xhs-topics.plist com.ocean.xhs-topics-heat.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ocean.xhs-topics.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ocean.xhs-topics-heat.plist

# 2) 一键重建桌面 App（自动建 venv+装依赖+生成图标+打包+装到 ~/Applications）
./make_app.sh
# 然后把 ~/Applications/T.app 拖进 Dock 即可
```
> ⚠️ 两台机用户名都是 YOUR_USER，`~/` 路径可直接用；若家里电脑用户名不同，先改两个 plist 里的 `/Users/YOUR_USER/...` 路径再 bootstrap。
> ⚠️ 代理端口：`make_app.sh` 和热度 cron plist 里写死 `127.0.0.1:7897`，家里电脑代理端口不同要改。

### 重建/更新桌面 App（同一台机）
改了 `index.html` / `desktop_app.py` 后想让 T.app 生效，跑一次：
```bash
cd ~/xhs-topics && ./make_app.sh
```
> 注：日常改数据/打分**不用**重建——T.app 是个壳，内容实时从 8773 服务读。只有改了 App 本身代码才需重建。

---

## 四、文件说明

| 文件 | 作用 |
|---|---|
| `server.py` | 后端：HTTP 服务 + 原子写 + 锁 + 防抖 git 同步。端口 8773 |
| `index.html` | 前端：单页表格，原生 JS，8 秒轮询（多机改动能看到）|
| `topics.json` | 数据：`{updated, topics:[...]}`，每次写前自动备份 7 份 |
| `heat_refresh.py` | 外部热度抓取（Google Trends），cron 每天9点 / 前端「立即刷新」触发；抓不到就留空不编造 |
| `sync.sh` | git 多机同步脚本（pull 合并 → commit → push）|
| `json-merge.py` | git 合并驱动：topics.json 按 id 并集，永不产生冲突标记 |
| `start.sh` | 启动脚本（命令行起 server）|
| `desktop_app.py` | 桌面 App 入口：pywebview 独立原生窗口（不走浏览器）|
| `setup.py` | py2app 打包配置，产出 `dist/T.app` |
| `make_app.sh` | 一键重建桌面 App（装依赖→生成图标→打包→装 ~/Applications）|
| `launch_app.sh` | 复用 venv 起桌面 App 的启动器 |
| `app-icon.icns` | 红底大写 T 图标 |
| `venv/` | Python 虚拟环境（pytrends 抓热度 + pywebview/py2app 打包）|
| `com.ocean.xhs-topics.plist` | 主服务 launchd 自启（已装到 ~/Library/LaunchAgents/）|
| `com.ocean.xhs-topics-heat.plist` | 每天9点热度刷新 cron（已装）|

### 数据结构（一条选题）
```json
{
  "id": "x-xxxxxxxxxxxx",
  "title": "选题标题",
  "note": "一句话角度",
  "platform": "xhs",          // xhs | ins | both
  "status": "idea",           // idea | todo | shot | published | dropped
  "score_heat": 5,            // 流量 1-5（手动打）
  "score_fit": 5,             // 契合 1-5（手动打）
  "score_money": 3,           // 变现 1-5（手动打）
  "keyword": "",              // 搜索关键词（空则用标题），抓外部热度用
  "ext_heat": null,           // 外部热度 0-100（Google大盘），抓不到=null（空着）
  "ext_heat_updated": null,   // 上次刷新时间
  "tags": [],
  "created": "2026-06-15T14:00:00+08:00",
  "published_at": null,
  "stats": { "views": null, "clicks": null, "likes": null, "follows": null, "comments": null }
}
```

### 数据备份
每次写入前自动备份到 `~/Library/Application Support/xhs-topics/backups/`，保留最近 7 份。
误删/误改可从这里恢复。

---

## 五、排障

| 现象 | 解决 |
|---|---|
| 打不开页面 | `launchctl list \| grep xhs-topics` 看是否在跑；不在就 `launchctl kickstart -k gui/$(id -u)/com.ocean.xhs-topics` |
| 端口被占 | `lsof -nP -iTCP:8773 -sTCP:LISTEN` 看谁占了；本 App 用 8773 |
| 改了数据没同步 | 看 `/tmp/xhs-topics-sync.log` 和 `/tmp/xhs-topics-sync.status` |
| 外部热度全是「—」 | 看 `/tmp/xhs-topics-heat.log`；多半是 Google Trends 429 限频（正常，过会再点刷新）或代理没通；中文长尾词本就常无数据 |
| 热度 cron 没跑 | `launchctl list \| grep xhs-topics-heat`；手动跑：`cd ~/xhs-topics && ./venv/bin/python heat_refresh.py` |
| 想直接改数据 | 编辑 `~/xhs-topics/topics.json`（合法 JSON），页面 8 秒内自动刷新 |
