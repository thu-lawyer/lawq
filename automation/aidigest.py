#!/usr/bin/env python3
"""AI 法学日报 · 每日抓取 AI/计算法学资讯与论文，LLM 整理后邮件推送

数据源（均已验证可从阿里云北京服务器直连）：
  arXiv API        论文：computational law / legal AI / AI regulation 等
  Hacker News      外网社区热议（Algolia API）
  Solidot          外网科技动态中文报道（关键词过滤）
  GitHub           开源动态（legal-ai 相关新建仓库）
  Twitter RSS stub 预留：在 aidigest.env 配 TWITTER_RSS_URLS 即启用（大陆服务器直连推特不通）

用法：
  python3 aidigest.py                # 抓取→LLM整理→存档→发邮件
  python3 aidigest.py --dry-run      # 只抓取整理并存档，不发邮件、不更新去重状态
  python3 aidigest.py --no-llm       # 跳过 LLM，直接用原始摘要
仅用 Python 标准库，无第三方依赖。
"""
import hashlib
import html
import json
import re
import smtplib
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parsedate_to_datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
ENV_FILE = BASE / "aidigest.env"
STATE_FILE = BASE / "state.json"
DIGEST_DIR = BASE / "digests"

UA = "Mozilla/5.0 (X11; Linux x86_64) lawq-aidigest/1.0"
TIMEOUT = 25

# ---------------- 配置 ----------------

def load_env() -> dict:
    cfg = {
        "MAIL_TO": "", "SMTP_HOST": "smtp.qq.com", "SMTP_PORT": "465",
        "SMTP_USER": "", "SMTP_PASS": "", "MAIL_FROM_NAME": "AI法学日报",
        "ZHIPU_API_KEY": "", "LLM_BASE_URL": "https://open.bigmodel.cn/api/paas/v4",
        "LLM_MODEL": "glm-5.3-flash",
        "LOOKBACK_HOURS": "30", "MAX_ITEMS": "22", "TWITTER_RSS_URLS": "",
    }
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip()
    return cfg


CFG = load_env()
LOOKBACK = timedelta(hours=float(CFG["LOOKBACK_HOURS"]))
NOW = datetime.now(timezone.utc)

# ---------------- 抓取工具 ----------------

def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


class Item(dict):
    """keys: id, section, source, title, url, summary, published"""

    def __init__(self, **kw):
        super().__init__(**kw)
        self["id"] = hashlib.md5(kw["url"].encode()).hexdigest()[:16]


# ---------------- 各数据源 ----------------

LAW_WORDS = re.compile(r"law|legal|regulat|judicial|justice|court|compliance|legislat|governance|statute|attorney|contract", re.I)


def fetch_arxiv() -> list:
    queries = [
        'all:"computational law"',
        'all:"legal artificial intelligence" OR all:"legal AI"',
        'all:"AI regulation" OR all:"AI governance"',
        'all:"large language model" AND cat:cs.CL AND all:legal',
        'all:"algorithmic" AND all:"due process"',
    ]
    items, seen = [], set()
    for q in queries:
        url = ("https://export.arxiv.org/api/query?search_query=" + urllib.parse.quote(q)
               + "&sortBy=submittedDate&sortOrder=descending&max_results=25")
        try:
            root = ET.fromstring(http_get(url))
        except Exception as e:
            log(f"arxiv {q!r} 失败: {e}")
            continue
        ns = "{http://www.w3.org/2005/Atom}"
        for entry in root.findall(f"{ns}entry"):
            try:
                link = entry.find(f"{ns}id").text.strip()
                title = re.sub(r"\s+", " ", entry.find(f"{ns}title").text.strip())
                summary = re.sub(r"\s+", " ", entry.find(f"{ns}summary").text.strip())
                pub = datetime.fromisoformat(entry.find(f"{ns}published").text)
                aid = link.rsplit("/", 1)[-1]
                if aid in seen or NOW - pub > LOOKBACK * 2:
                    continue
                if not LAW_WORDS.search(title + " " + summary[:400]):
                    continue
                seen.add(aid)
                items.append(Item(section="papers", source="arXiv", title=title,
                                  url=link, summary=summary[:400],
                                  published=pub.astimezone(timezone.utc).isoformat()))
            except Exception:
                continue
    log(f"arXiv: {len(items)} 条")
    return items


def fetch_hn() -> list:
    queries = ["AI law", "AI regulation", "legal AI", "AI policy court", "computational law"]
    since = int((NOW - LOOKBACK).timestamp())
    items, seen = [], set()
    for q in queries:
        url = ("https://hn.algolia.com/api/v1/search_by_date?tags=story&hitsPerPage=30"
               f"&numericFilters=created_at_i>{since}&query={urllib.parse.quote(q)}")
        try:
            data = json.loads(http_get(url))
        except Exception as e:
            log(f"HN {q!r} 失败: {e}")
            continue
        for h in data.get("hits", []):
            if not h.get("url") or h["objectID"] in seen:
                continue
            if (h.get("points") or 0) < 2:
                continue
            seen.add(h["objectID"])
            items.append(Item(section="oversea", source=f"HackerNews({h.get('points', 0)}分)",
                              title=h["title"], url=h["url"],
                              summary=(h.get("story_text") or "")[:300] or f"HN 讨论 {h.get('num_comments', 0)} 条",
                              published=datetime.fromtimestamp(h["created_at_i"], timezone.utc).isoformat()))
    # 按热度取前 8
    items.sort(key=lambda x: -int(re.search(r"\((\d+)分\)", x["source"]).group(1)))
    log(f"HackerNews: {len(items[:8])} 条")
    return items[:8]


def fetch_solidot() -> list:
    kw = re.compile(r"AI|人工智能|大模型|LLM|GPT|机器学习|算法|法律|监管|隐私|数据|版权|开源", re.I)
    items = []
    try:
        root = ET.fromstring(http_get("https://www.solidot.org/index.rss"))
    except Exception as e:
        log(f"solidot 失败: {e}")
        return items
    for it in root.iter("item"):
        try:
            title = strip_html(it.findtext("title") or "")
            pub = parsedate_to_datetime(it.findtext("pubDate"))
            if NOW - pub > LOOKBACK * 2 or not kw.search(title):
                continue
            items.append(Item(section="news", source="Solidot", title=title,
                              url=it.findtext("link").strip(),
                              summary=strip_html(it.findtext("description") or "")[:300],
                              published=pub.astimezone(timezone.utc).isoformat()))
        except Exception:
            continue
    log(f"Solidot: {len(items)} 条")
    return items[:6]


def fetch_github() -> list:
    since = (NOW - LOOKBACK * 2).date().isoformat()
    queries = [f"topic:legal-ai created:>{since}", f"topic:computational-law created:>{since}",
               f"law llm created:>{since}"]
    items, seen = [], set()
    for q in queries:
        url = ("https://api.github.com/search/repositories?q=" + urllib.parse.quote(q)
               + "&sort=updated&per_page=10")
        try:
            data = json.loads(http_get(url))
        except Exception as e:
            log(f"github {q!r} 失败: {e}")
            continue
        for r in data.get("items", []):
            if r["id"] in seen or not r.get("description"):
                continue
            seen.add(r["id"])
            items.append(Item(section="opensource", source="GitHub",
                              title=f"{r['full_name']} ★{r['stargazers_count']}",
                              url=r["html_url"], summary=r["description"][:300],
                              published=r["created_at"]))
    log(f"GitHub: {len(items[:6])} 条")
    return items[:6]


def fetch_twitter() -> list:
    urls = [u.strip() for u in CFG.get("TWITTER_RSS_URLS", "").split(",") if u.strip()]
    items = []
    for u in urls:
        try:
            root = ET.fromstring(http_get(u))
            for it in root.iter("item"):
                title = strip_html(it.findtext("title") or "")
                if not title:
                    continue
                items.append(Item(section="oversea", source="X/Twitter", title=title,
                                  url=(it.findtext("link") or u).strip(),
                                  summary=strip_html(it.findtext("description") or "")[:300],
                                  published=NOW.isoformat()))
        except Exception as e:
            log(f"twitter rss {u} 失败: {e}")
    return items[:8]


FETCHERS = [("论文 · arXiv", fetch_arxiv), ("外网热议", fetch_hn), ("科技动态", fetch_solidot),
            ("开源动态", fetch_github), ("推特", fetch_twitter)]

# ---------------- 去重 ----------------

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {"seen": {}}


def filter_seen(items: list, state: dict) -> list:
    seen = state.setdefault("seen", {})
    fresh = [it for it in items if it["id"] not in seen]
    cut = (NOW - timedelta(days=90)).isoformat()
    for k in [k for k, v in seen.items() if v < cut]:
        del seen[k]
    return fresh


# ---------------- LLM 整理 ----------------

def llm_polish(items: list) -> dict:
    """返回 {"digest": [...], "notes": [...]}；失败返回空 dict。"""
    if not CFG.get("ZHIPU_API_KEY") or not items:
        return {}
    payload_items = [{"i": i + 1, "板块": it["section"], "来源": it["source"],
                      "标题": it["title"], "摘要": it["summary"][:280]}
                     for i, it in enumerate(items)]
    sys_p = ("你是 AI 与计算法学领域研究助理。根据给定条目生成中文日报增强内容。"
             "只返回严格 JSON：{\"digest\": [\"今日要点1\", ...3~5条], "
             "\"notes\": [\"第1条的中文点评(说明其价值/意义,≤40字)\", ...与条目等长]}。"
             "要点跨板块提炼；点评客观平实，不夸张。")
    user_p = json.dumps(payload_items, ensure_ascii=False)
    body = json.dumps({"model": CFG["LLM_MODEL"], "temperature": 0.2,
                       "messages": [{"role": "system", "content": sys_p},
                                    {"role": "user", "content": user_p}]},
                      ensure_ascii=False).encode()
    req = urllib.request.Request(
        CFG["LLM_BASE_URL"].rstrip("/") + "/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + CFG["ZHIPU_API_KEY"]})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            text = json.loads(r.read())["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", text, re.S)
        out = json.loads(m.group(0))
        if isinstance(out.get("notes"), list) and len(out["notes"]) >= len(items):
            return out
    except Exception as e:
        log(f"LLM 整理失败（用原始摘要兜底）: {e}")
    return {}


# ---------------- 渲染与发送 ----------------

SECTION_NAMES = [("papers", "📄 论文动态"), ("oversea", "🌍 外网热议"),
                 ("news", "📰 科技动态"), ("opensource", "🛠 开源动态")]


def render_md(items: list, polish: dict) -> str:
    lines = [f"# AI 法学日报 · {NOW.astimezone().strftime('%Y-%m-%d %H:%M')}", ""]
    if polish.get("digest"):
        lines += ["## 🔎 今日要点", ""] + [f"- {d}" for d in polish["digest"]] + [""]
    idx = 0
    for key, name in SECTION_NAMES:
        sec = [it for it in items if it["section"] == key]
        if not sec:
            continue
        lines += [f"## {name}", ""]
        for it in sec:
            note = (polish.get("notes") or [""] * len(items))[idx] if polish else ""
            lines.append(f"### {it['title']}")
            lines.append(f"- {it['source']} · {it['url']}")
            body = note or it["summary"]
            if body:
                lines.append(f"- {body}")
            lines.append("")
            idx += 1
    lines += ["---", "*由服务器自动抓取（arXiv/HN/Solidot/GitHub），glm-5.3-flash 整理。内容仅供参考。*"]
    return "\n".join(lines)


def linkify(esc_line: str) -> str:
    return re.sub(r"(https?://[^\s<]+)", r"<a href='\1'>\1</a>", esc_line)


def md_to_html(md_text: str) -> str:
    """我们生成的 Markdown 格式固定，直接做小型转换，避免第三方依赖。"""
    out, in_list = [], False
    for ln in md_text.splitlines():
        esc = html.escape(ln, quote=False)
        if ln.startswith("### "):
            if in_list: out.append("</ul>"); in_list = False
            out.append(f"<h4 style='margin:16px 0 4px;font-size:16px'>{linkify(esc[4:])}</h4>")
        elif ln.startswith("## "):
            if in_list: out.append("</ul>"); in_list = False
            out.append(f"<h3 style='margin:24px 0 8px;border-bottom:1px solid #eee;padding-bottom:4px'>{esc[3:]}</h3>")
        elif ln.startswith("# "):
            out.append(f"<h2 style='margin:6px 0 14px'>{esc[2:]}</h2>")
        elif ln.startswith("- "):
            if not in_list:
                out.append("<ul style='padding-left:20px;margin:6px 0'>"); in_list = True
            out.append(f"<li style='margin:5px 0'>{linkify(esc[2:])}</li>")
        elif ln.startswith("---"):
            if in_list: out.append("</ul>"); in_list = False
            out.append("<hr style='border:none;border-top:1px solid #eee;margin:18px 0'>")
        elif ln.strip():
            if in_list: out.append("</ul>"); in_list = False
            out.append(f"<p style='margin:6px 0;color:#555'>{linkify(esc)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def render_html(items: list, polish: dict) -> str:
    body = md_to_html(render_md(items, polish))
    return ("<!doctype html><meta charset='utf-8'>"
            "<body style='font-family:-apple-system,Segoe UI,PingFang SC,sans-serif;"
            "max-width:720px;margin:0 auto;line-height:1.7;color:#222;font-size:15px'>"
            + body + "</body>")


def send_mail(subject: str, html_body: str, plain: str) -> None:
    host, port = CFG["SMTP_HOST"], int(CFG["SMTP_PORT"])
    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header(CFG["MAIL_FROM_NAME"], "utf-8")), CFG["SMTP_USER"]))
    msg["To"] = CFG["MAIL_TO"]
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    if port == 465:
        smtp = smtplib.SMTP_SSL(host, port, timeout=40)
    else:
        smtp = smtplib.SMTP(host, port, timeout=40)
        smtp.starttls()
    try:
        smtp.login(CFG["SMTP_USER"], CFG["SMTP_PASS"])
        smtp.sendmail(CFG["SMTP_USER"], [CFG["MAIL_TO"]], msg.as_string())
    finally:
        smtp.quit()


# ---------------- 主流程 ----------------

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def main() -> int:
    dry = "--dry-run" in sys.argv
    no_llm = "--no-llm" in sys.argv

    items: list = []
    failures = 0
    for _, fn in FETCHERS:
        try:
            items += fn()
        except Exception as e:
            failures += 1
            log(f"数据源 {fn.__name__} 整体失败: {e}")

    state = {} if dry else load_state()
    items = filter_seen(items, state)
    if not items:
        log("今日无新增内容，跳过发送")
        return 0
    order = {k: i for i, (k, _) in enumerate(SECTION_NAMES)}
    items.sort(key=lambda x: order.get(x["section"], 99))
    cap = int(CFG["MAX_ITEMS"])
    if len(items) > cap:
        # 每板块均衡截断
        per = {}
        kept = []
        for it in items:
            if per.get(it["section"], 0) < max(2, cap // 4):
                kept.append(it)
                per[it["section"]] = per.get(it["section"], 0) + 1
        items = kept[:cap]
    log(f"去重后 {len(items)} 条，开始整理")

    polish = {} if no_llm else llm_polish(items)
    md = render_md(items, polish)
    DIGEST_DIR.mkdir(exist_ok=True)
    out = DIGEST_DIR / f"{NOW.astimezone().strftime('%Y-%m-%d')}.md"
    out.write_text(md, encoding="utf-8")
    log(f"已存档 {out}")

    if dry:
        print("\n===== 日报预览（dry-run 不发信）=====\n")
        print(md[:2000])
        return 0

    if not (CFG["SMTP_USER"] and CFG["SMTP_PASS"] and CFG["MAIL_TO"]):
        log("未配置 SMTP（aidigest.env），邮件未发送；日报已存档")
        return 0
    subject = f"【AI法学日报】{NOW.astimezone().strftime('%m-%d')} · {len(items)} 条"
    try:
        send_mail(subject, render_html(items, polish), md)
        log(f"✓ 已发送至 {CFG['MAIL_TO']}")
    except Exception as e:
        log(f"✗ 邮件发送失败: {e}")
        return 1

    if not dry:
        for it in items:
            state["seen"][it["id"]] = NOW.isoformat()
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    log(f"完成（数据源失败 {failures} 个）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
