"""律问 · SQLite 读取层"""
import sqlite3
from contextlib import contextmanager

from .config import DB_PATH

ARTICLE_COLS = (
    "id, law_id, law_name, law_department, level, status, chapter, section, "
    "article_no, article_no_arabic, article_text, char_count"
)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


CURRENT = "status IN ('现行有效', '已被修改')"


def get_stats() -> dict:
    with get_conn() as conn:
        laws = conn.execute("SELECT COUNT(*) c FROM laws").fetchone()["c"]
        arts = conn.execute(f"SELECT COUNT(*) c FROM articles WHERE {CURRENT}").fetchone()["c"]
        depts = conn.execute(
            f"SELECT law_department d, COUNT(DISTINCT law_id) laws, COUNT(*) arts FROM articles "
            f"WHERE {CURRENT} GROUP BY law_department ORDER BY arts DESC"
        ).fetchall()
        return {
            "laws": laws,
            "articles": arts,
            "departments": [
                {"name": r["d"] or "其他", "laws": r["laws"], "articles": r["arts"]} for r in depts
            ],
        }


def list_laws(department: str | None = None, q: str | None = None) -> list[dict]:
    sql = (
        "SELECT l.law_id, l.law_name, l.law_department, l.doc_type, l.issuing_body, "
        "l.version_date, l.status, "
        "(SELECT COUNT(*) FROM articles a WHERE a.law_id=l.law_id AND a.status IN ('现行有效','已被修改')) arts "
        "FROM laws l WHERE l.law_id IN (SELECT DISTINCT law_id FROM articles)"
    )
    args: list = []
    if department:
        sql += " AND l.law_department=?"
        args.append(department)
    if q:
        sql += " AND l.law_name LIKE ?"
        args.append(f"%{q}%")
    sql += " ORDER BY l.law_department, arts DESC, l.law_name"
    with get_conn() as conn:
        rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]


def list_articles(law_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT {ARTICLE_COLS} FROM articles WHERE law_id=? ORDER BY id", (law_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def search_articles(q: str, limit: int = 200, current_only: bool = True) -> list[dict]:
    like = f"%{q.strip()}%"
    sql = f"SELECT {ARTICLE_COLS} FROM articles WHERE article_text LIKE ?"
    if current_only:
        sql += f" AND {CURRENT}"
    sql += " ORDER BY char_count LIMIT ?"
    with get_conn() as conn:
        rows = conn.execute(sql, (like, limit)).fetchall()
        return [dict(r) for r in rows]


def get_articles_by_ids(ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT {ARTICLE_COLS} FROM articles WHERE id IN ({marks})", ids
        ).fetchall()
        return {r["id"]: dict(r) for r in rows}
