#!/usr/bin/env python3
"""律问 · 语料构建：宪法法律_条文.jsonl → data/laws.db + data/bm25.pkl

用法：
    python scripts/build_corpus.py [源文件.jsonl]

默认源文件：项目上级目录下的 宪法法律_条文.jsonl（课堂提供语料）。
产物：
    data/laws.db   —— SQLite：laws(法元数据) + articles(逐条条文，全量含历史/废止)
    data/bm25.pkl  —— BM25 索引（仅现行有效的 宪法/法律/立法解释 条文）
"""
import json
import pickle
import sqlite3
import sys
import time
from pathlib import Path

import jieba
from rank_bm25 import BM25Okapi

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "laws.db"
INDEX_PATH = DATA_DIR / "bm25.pkl"

DEFAULT_SOURCE = PROJECT_ROOT.parent / "宪法法律_条文.jsonl"

# 进入 BM25 问答索引的类型与状态：
#   修正案/修改决定是修订过程文本，正文已并入现行法，不进索引；
#   「已被修改」= 库内因存在修正案等文件而保守标注，条文本身是库内最新现行文本，应进索引
INDEX_DOC_TYPES = {"宪法", "法律", "立法解释"}
INDEX_STATUSES = {"现行有效", "已被修改"}


def tokenize(text: str) -> list[str]:
    import re
    return [t for t in jieba.lcut(text) if re.fullmatch(r"[\u4e00-\u9fff\w]+", t)]


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    if not source.exists():
        sys.exit(f"找不到源文件：{source}（可传入路径参数指定）")

    DATA_DIR.mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        """
        CREATE TABLE laws (
            law_id TEXT PRIMARY KEY, law_name TEXT NOT NULL, doc_type TEXT,
            level TEXT, issuing_body TEXT, publish_date TEXT, effective_date TEXT,
            version_date TEXT, status TEXT, law_department TEXT
        );
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY, law_id TEXT NOT NULL, law_name TEXT NOT NULL,
            law_department TEXT, level TEXT, status TEXT, chapter TEXT, section TEXT,
            article_no TEXT, article_no_arabic INTEGER, article_text TEXT, char_count INTEGER
        );
        CREATE INDEX idx_articles_law ON articles(law_id);
        CREATE INDEX idx_articles_status ON articles(status);
        """
    )

    t0 = time.time()
    n_rows = n_index = 0
    laws_latest: dict[str, dict] = {}
    index_ids: list[int] = []
    index_tokens: list[list[str]] = []

    insert_art = "INSERT INTO articles VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"

    with open(source, encoding="utf-8") as f:
        for row_id, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            n_rows += 1
            conn.execute(
                insert_art,
                (
                    row_id, r["law_id"], r["law_name"], r.get("law_department"),
                    r.get("level"), r.get("status"), r.get("chapter"), r.get("section"),
                    r.get("article_no"), r.get("article_no_arabic"), r.get("article_text"),
                    r.get("char_count"),
                ),
            )
            prev = laws_latest.get(r["law_id"])
            if prev is None or (r.get("version_date") or "") >= (prev.get("version_date") or ""):
                laws_latest[r["law_id"]] = r
            if r.get("status") in INDEX_STATUSES and r.get("doc_type") in INDEX_DOC_TYPES:
                n_index += 1
                index_ids.append(row_id)
                index_tokens.append(tokenize(r.get("embed_text") or r.get("article_text") or ""))
            if n_rows % 5000 == 0:
                print(f"  已解析 {n_rows} 行… ({time.time()-t0:.0f}s)")

    for r in laws_latest.values():
        conn.execute(
            "INSERT INTO laws VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                r["law_id"], r["law_name"], r.get("doc_type"), r.get("level"),
                r.get("issuing_body"), r.get("publish_date"), r.get("effective_date"),
                r.get("version_date"), r.get("status"), r.get("law_department"),
            ),
        )
    conn.commit()

    print(f"语料解析完成：{n_rows} 条，进索引 {n_index} 条，耗时 {time.time()-t0:.0f}s，开始建 BM25…")
    bm25 = BM25Okapi(index_tokens)
    with open(INDEX_PATH, "wb") as f:
        pickle.dump({"ids": index_ids, "bm25": bm25, "built_at": time.strftime("%F")}, f)
    print(f"BM25 索引完成 → {INDEX_PATH} ({INDEX_PATH.stat().st_size/1e6:.0f} MB)")

    # ---- 校验 ----
    def check(name: str, no: int) -> None:
        row = conn.execute(
            "SELECT law_name, article_no, status FROM articles "
            "WHERE law_name LIKE ? AND article_no_arabic=? "
            "AND status IN ('现行有效','已被修改') LIMIT 1",
            (f"%{name}%", no),
        ).fetchone()
        print(f"  校验 {name}第{no}条：{'✓ ' + row[0] + ' ' + row[1] if row else '✗ 未找到'}")

    print("抽样校验：")
    check("民法典", 1254)
    check("刑法", 20)
    check("劳动合同法", 19)
    check("消费者权益保护法", 24)
    stats = conn.execute(
        "SELECT status, COUNT(*) FROM articles GROUP BY status ORDER BY 2 DESC"
    ).fetchall()
    print("条数按状态：", dict(stats))
    conn.close()
    print(f"全部完成，总耗时 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
