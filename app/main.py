"""律问 · FastAPI 主应用"""
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, database, ratelimit, retrieval
from .config import ACCESS_PASSWORD, ASK_RATE_LIMIT, WEB_DIR
from .llm import stream_answer

SUGGESTIONS = [
    "小区里被高空抛物砸伤，找谁赔偿？",
    "试用期被辞退有经济补偿吗？",
    "什么情况属于正当防卫？",
    "网购商品七天无理由退货有什么条件？",
    "协议离婚的冷静期是多久？",
    "借钱不还的诉讼时效是几年？",
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        retrieval.load()
        print("律问：BM25 索引已加载")
    except FileNotFoundError:
        print("律问：警告——未找到 BM25 索引，请先运行 python scripts/build_corpus.py")
    yield


app = FastAPI(title="律问 · 法律检索问答", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


def client_ip(request: Request) -> str:
    return request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For", request.client.host or "?").split(",")[0].strip()


def require_token(request: Request, x_token: str | None) -> None:
    token = x_token or request.query_params.get("token")
    if not auth.verify_token(token):
        raise HTTPException(401, "需要登录：请先输入访问口令")


class LoginBody(BaseModel):
    password: str = ""


class AskBody(BaseModel):
    question: str


@app.post("/api/login")
def login(body: LoginBody):
    if not auth.check_password(body.password.strip()):
        raise HTTPException(401, "口令不正确")
    return {"token": auth.issue_token(), "protected": bool(ACCESS_PASSWORD)}


@app.get("/api/health")
def health():
    return {"ok": True, "protected": bool(ACCESS_PASSWORD)}


@app.get("/api/stats")
def stats(request: Request, x_token: str | None = Header(None)):
    require_token(request, x_token)
    return database.get_stats()


@app.get("/api/suggest")
def suggest():
    return {"questions": SUGGESTIONS}


@app.get("/api/laws")
def laws(request: Request, department: str | None = None, q: str | None = None,
         x_token: str | None = Header(None)):
    require_token(request, x_token)
    return {"laws": database.list_laws(department=department, q=q)}


@app.get("/api/laws/{law_id}")
def law_articles(law_id: str):
    return {"articles": database.list_articles(law_id)}


@app.get("/api/search")
def search_articles(request: Request, q: str, x_token: str | None = Header(None)):
    require_token(request, x_token)
    q = q.strip()
    if not q:
        return {"articles": []}
    return {"articles": database.search_articles(q, limit=200)}


@app.post("/api/ask")
def ask(body: AskBody, request: Request, x_token: str | None = Header(None)):
    require_token(request, x_token)
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "问题不能为空")
    if len(question) > 500:
        raise HTTPException(400, "问题太长了（≤500 字）")
    if not ratelimit.allow(f"ask:{client_ip(request)}", ASK_RATE_LIMIT[0], ASK_RATE_LIMIT[1]):
        raise HTTPException(429, "提问太频繁，请稍候再试")

    def gen() -> AsyncIterator[str]:
        def event(obj: dict) -> str:
            return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

        try:
            hits = retrieval.search(question)
            hits_public = [
                {
                    "law_name": h["law_name"], "article_no": h["article_no"],
                    "article_text": h["article_text"], "chapter": h["chapter"],
                    "law_department": h["law_department"], "level": h["level"],
                    "status": h["status"], "score": h["score"], "via": h["via"],
                }
                for h in hits
            ]
            yield event({"type": "hits", "hits": hits_public})
            n = 0
            for delta in stream_answer(question, hits):
                n += len(delta)
                yield event({"type": "delta", "text": delta})
            yield event({"type": "done", "chars": n})
        except Exception as e:  # 流中断也要给前端明确信号
            yield event({"type": "error", "message": str(e)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
