# AI 法学日报 · 自动化推送

> 部署在云服务器上的每日自动化任务：抓取 AI / 计算法学相关的**论文、外网热议、科技动态、开源项目** → LLM 整理成日报 → 邮件推送。systemd timer 定时触发，纯 Python 标准库实现，**零第三方依赖**。

## 工作流

```
每天 08:00 (systemd timer)
   ├─ arXiv API        论文：computational law / legal AI / AI governance 等检索式
   ├─ Hacker News      外网社区热议（Algolia API，按热度）
   ├─ Solidot RSS      科技动态（关键词过滤）
   ├─ GitHub Search    开源动态（legal-ai 等话题新建仓库）
   └─ Twitter RSS      预留接口（TWITTER_RSS_URLS 配置即启用）
        ↓
   去重（90 天滑窗）→ glm LLM 生成「今日要点 + 逐条中文点评」
        ↓
   HTML 邮件推送 + 本地 Markdown 存档
```

LLM 只做增强，失败时自动退化为原始摘要；任一数据源失败不影响整体。

## 快速开始

```bash
cp aidigest.env.example aidigest.env   # 填 SMTP 授权码与 LLM Key
python3 aidigest.py --dry-run          # 试跑：抓取+整理+存档，不发信
python3 aidigest.py                    # 正式运行：抓取+整理+发邮件
python3 aidigest.py --no-llm           # 跳过 LLM，直接用原始摘要
```

配置项（`aidigest.env`）：收件邮箱、SMTP（465/587 自动适配）、LLM Key、回看时间窗（`LOOKBACK_HOURS`）、条数上限（`MAX_ITEMS`）、推特 RSS 源。

## 服务器部署（systemd）

```ini
# /etc/systemd/system/aidigest.service
[Unit]
Description=AI法学日报：抓取-整理-推送
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/aidigest
ExecStart=/usr/bin/python3 /opt/aidigest/aidigest.py
```

```ini
# /etc/systemd/system/aidigest.timer
[Timer]
OnCalendar=*-*-* 08:00:00
Persistent=true
RandomizedDelaySec=300
```

```bash
sudo systemctl enable --now aidigest.timer   # 每日 08:00 自动运行
systemctl list-timers aidigest*              # 查看下次运行时间
journalctl -u aidigest -n 50                 # 运行日志
```

## 日报样例

```markdown
# AI 法学日报 · 2026-09-30

## 🔎 今日要点
- 海外AI争议密集：AI安全人士依加州反黑客法起诉OpenAI……
- 开源法律AI集中亮相：政府采购合规审查、合同审查助手……

## 🌍 外网热议
### AI tools generated nearly $1B in extra costs, Blue Cross insurers say
- HackerNews(19分) · https://reuters.com/...
- 保险公司披露的近10亿美元额外成本，为AI应用成本核算提供实际案例。
...
```

## 说明

- 邮件走 SMTP 465/587（阿里云等封 25 端口的环境可用），推荐 QQ/163 邮箱授权码
- 去重状态存 `state.json`（90 天窗口自动清理），日报存档在 `digests/`
- 大陆服务器直连 Twitter 不通，故外网内容以 HN/Solidot 覆盖；有 RSSHub 等代理源时填入配置即并入
