"""律问 · 检索引擎：BM25 + 同义词扩展 + 覆盖率/短语重排 + 法条直查"""
import pickle
import re
import threading

import jieba

from . import database
from .config import INDEX_PATH, TOP_K

_lock = threading.Lock()
_index: dict | None = None
_law_names: set[str] = set()
_alias_map: dict[str, str] = {}

CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}

STOPWORDS = set("的了是在和与对于由从被把及或并等请问我你他它这那个之其什么怎么怎样如何"
                "咨询一下有关关于应该可以是否有没有如果因为所以但是然后因此出现进行予以上"
                "最久几多年多月内情况下时候属于属于".split())

# 口语/惯用语 → 法言法语扩展词：命中 key 时把扩展词并入查询
SYNONYMS = {
    "高空抛物": ["抛掷", "坠落", "建筑物"], "高空坠物": ["抛掷", "坠落", "建筑物"],
    "坠物": ["坠落", "建筑物"], "抛物": ["抛掷"],
    "酒驾": ["饮酒", "醉酒", "驾驶", "机动车"], "醉驾": ["醉酒", "驾驶", "机动车"],
    "酒后开车": ["饮酒", "驾驶", "机动车"], "喝酒开车": ["饮酒", "驾驶", "机动车"],
    "开车": ["机动车", "驾驶"],
    "冷静期": ["离婚", "三十日", "婚姻登记机关"],
    "试用期": ["劳动合同", "用人单位"], "辞退": ["解除", "劳动合同", "用人单位"],
    "开除": ["解除", "劳动合同"], "离职": ["解除", "劳动合同"],
    "正当防卫": ["不法侵害", "防卫", "制止"],
    "无理由退货": ["退货", "七日"], "退货": ["退货", "七日"],
    "借钱": ["借款", "返还"], "欠钱": ["借款", "返还"], "借钱不还": ["借款", "返还", "时效"],
    "砸伤": ["损害", "伤害", "赔偿"], "砸到": ["损害", "赔偿"],
    "维权": ["权利", "责任"], "赔偿": ["损害", "赔偿"],
    "泄露": ["泄露", "提供"], "隐私": ["隐私权", "个人信息"],
    "出资": ["认缴", "出资额", "股东"], "股东": ["股东", "出资"],
    "诉讼时效": ["诉讼时效", "时效"], "时效": ["诉讼时效"],
    "网上购物": ["网络", "经营者"], "网购": ["网络", "经营者"],
    "房子": ["不动产", "房屋"], "租房": ["租赁", "出租人", "承租人"],
    "彩礼": ["婚约", "返还"], "加班": ["加班", "工资"], "拖欠工资": ["劳动报酬", "工资"],
    "诈骗": ["诈骗", "骗取"], "偷": ["盗窃"], "偷窃": ["盗窃"], "抢劫": ["抢劫", "暴力"],
    "打架": ["殴打", "伤害"], "骂人": ["侮辱", "诽谤"],
}

_ARTICLE_RE = re.compile(r"([\u4e00-\u9fff]{2,20}?)第([一二三四五六七八九十百千零〇0-9]+)条")
_RECALL_K = 60  # 先粗召回，再重排


def cn2num(s: str) -> int | None:
    s = s.strip()
    if s.isdigit():
        return int(s)
    total, num = 0, 0
    for ch in s:
        if ch in CN_DIGITS:
            num = CN_DIGITS[ch]
        elif ch in CN_UNITS:
            if num == 0:
                num = 1
            if CN_UNITS[ch] == 10000:
                total = (total + num) * 10000
            else:
                total += num * CN_UNITS[ch]
            num = 0
        else:
            return None
    return total + num


def load(force: bool = False) -> dict:
    global _index, _law_names, _alias_map
    if _index is not None and not force:
        return _index
    with _lock:
        if _index is not None and not force:
            return _index
        with open(INDEX_PATH, "rb") as f:
            idx = pickle.load(f)
        with database.get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT law_name FROM articles "
                "WHERE status IN ('现行有效','已被修改')"
            ).fetchall()
        _law_names = {r["law_name"] for r in rows}
        alias: dict[str, str] = {
            "民诉法": "中华人民共和国民事诉讼法", "刑诉法": "中华人民共和国刑事诉讼法",
            "行诉法": "中华人民共和国行政诉讼法", "消保法": "中华人民共和国消费者权益保护法",
            "个保法": "中华人民共和国个人信息保护法", "道交法": "中华人民共和国道路交通安全法",
            "破产法": "中华人民共和国企业破产法", "网安法": "中华人民共和国网络安全法",
        }
        for name in _law_names:
            if name.startswith("中华人民共和国") and len(name) > 8:
                alias.setdefault(name[7:], name)
        _alias_map = {k: v for k, v in alias.items() if v in _law_names}
        _index = idx
        return _index


def _resolve_law(raw: str) -> str | None:
    name = raw.strip("《》 ").strip()
    if name in _alias_map:
        return _alias_map[name]
    if name in _law_names:
        return name
    for full in _law_names:  # 《民法典》… 完整引用里夹着简称
        short = full[7:] if full.startswith("中华人民共和国") else full
        if short and short in name:
            return full
    return None


def _expand(tokens: list[str], question: str) -> list[str]:
    out = list(tokens)
    for key, extra in SYNONYMS.items():
        if key in question:
            out.extend(extra)
    return out


def _tokenize(q: str) -> list[str]:
    return [t for t in jieba.lcut(q) if t.strip() and t not in STOPWORDS]


def _phrase_bonus(question_core: str, text: str) -> float:
    """查询去标点后，与条文连续共现的最长子串（≥4字）占比 → 短语级相关性。"""
    best = 0
    n = len(question_core)
    for i in range(n):
        for j in range(n, i + 3, -1):  # 子串长度 ≥4
            if j - i > best and question_core[i:j] in text:
                best = j - i
    return min(best, 12) / 12


def _direct_hits(question: str) -> list[dict]:
    hits: list[dict] = []
    for m in _ARTICLE_RE.finditer(question):
        law_name, no = _resolve_law(m.group(1)), cn2num(m.group(2))
        if not law_name or no is None:
            continue
        with database.get_conn() as conn:
            row = conn.execute(
                "SELECT id FROM articles WHERE law_name=? AND article_no_arabic=? "
                "AND status IN ('现行有效','已被修改') ORDER BY id LIMIT 1",
                (law_name, no),
            ).fetchone()
        if not row:
            continue
        rec = database.get_articles_by_ids([row["id"]]).get(row["id"])
        if rec:
            rec["score"], rec["via"] = 999.0, "直查"
            hits.append(rec)
    return hits


def search(question: str, top_k: int = TOP_K) -> list[dict]:
    load()
    direct = _direct_hits(question)

    tokens = _expand(_tokenize(question), question)
    qset = {t for t in tokens if len(t) >= 1}
    core = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", question)

    boost_law = None
    for alias, full in sorted(_alias_map.items(), key=lambda x: -len(x[0])):
        if alias in question:
            boost_law = full
            break

    # 查询里较长词恰是某法律名的一部分（如「个人信息」→ 个人信息保护法）→ 该法加权
    name_laws = set()
    for t in qset:
        if len(t) >= 4:
            for full in _law_names:
                if t in full:
                    name_laws.add(full)

    candidates: dict[int, dict] = {h["id"]: h for h in direct}
    if tokens:
        scores = _index["bm25"].get_scores(tokens)
        ranked = sorted(zip(_index["ids"], scores), key=lambda x: -x[1])[:_RECALL_K]
        arts = database.get_articles_by_ids([i for i, _ in ranked])
        max_sc = max((s for _, s in ranked), default=1.0) or 1.0
        for art_id, sc in ranked:
            rec = arts.get(art_id)
            if not rec or sc <= 0:
                continue
            text = rec["article_text"] or ""
            cov = sum(1 for t in qset if t in text) / max(len(qset), 1)
            fb = _phrase_bonus(core, text) if len(core) >= 4 else 0.0
            name_hit = 0.25 if (rec["law_name"] in name_laws or rec["law_name"] == boost_law) else 0.0
            norm = float(sc) / max_sc
            rec["score"] = round(norm + 0.9 * cov + 1.1 * fb + name_hit, 4)
            rec["via"] = "检索"
            candidates[art_id] = rec

    if boost_law and not any(h["law_name"] == boost_law for h in candidates.values()):
        best = None
        if tokens:
            for art_id, sc in sorted(
                zip(_index["ids"], _index["bm25"].get_scores(tokens)),
                key=lambda x: -x[1],
            ):
                rec = database.get_articles_by_ids([art_id]).get(art_id)
                if rec and rec["law_name"] == boost_law:
                    best = rec
                    break
        if best:
            best["score"], best["via"] = 0.5, "检索"
            candidates[best["id"]] = best

    hits = sorted(candidates.values(), key=lambda h: -h["score"])
    return hits[:top_k]
