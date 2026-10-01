"""律问 · 大模型调用：OpenAI 兼容接口，SSE 流式"""
import json
from collections.abc import Iterator

import httpx

from .config import LLM_BASE_URL, LLM_MODEL, ZHIPU_API_KEY

SYSTEM_PROMPT = """你是「律问」法律检索问答助手，回答必须严格依据用户消息中提供的法条。

要求：
1. 只引用【检索到的法条】里出现的条文作为法律依据，引用格式统一为《法律名》第X条；
2. 先给简明结论，再分点说明依据；语言平实，普通用户能看懂；
3. 提供的法条不足以回答时，明确说明"现有检索结果未覆盖"，可给出一般性建议，但严禁编造或凭记忆引用库外法条；
4. 回答使用简体中文；不要写"免责声明"（界面会统一展示）。"""


def build_context(hits: list[dict]) -> str:
    lines = []
    for i, h in enumerate(hits, 1):
        lines.append(f"[{i}]《{h['law_name']}》{h['article_no']}（{h['law_department']}/{h['level']}）：\n{h['article_text']}")
    return "\n\n".join(lines)


def stream_answer(question: str, hits: list[dict]) -> Iterator[str]:
    """流式生成回答；未配置 API Key 时退化为直接返回检索条文。"""
    if not ZHIPU_API_KEY:
        parts = ["（未配置大模型 API Key，以下为检索到的法条原文，可在 .env 中配置 ZHIPU_API_KEY 开启智能问答）\n"]
        for i, h in enumerate(hits, 1):
            parts.append(f"\n**{i}. 《{h['law_name']}》{h['article_no']}**\n{h['article_text']}\n")
        for p in parts:
            yield p
        return

    user_msg = f"【检索到的法条】\n{build_context(hits) if hits else '（未检索到相关法条）'}\n\n【用户问题】\n{question}"
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "stream": True,
        "temperature": 0.3,
    }
    headers = {"Authorization": f"Bearer {ZHIPU_API_KEY}", "Content-Type": "application/json"}
    with httpx.Client(timeout=120) as client:
        with client.stream("POST", f"{LLM_BASE_URL}/chat/completions", json=payload, headers=headers) as resp:
            if resp.status_code != 200:
                body = resp.read().decode("utf-8", "ignore")[:300]
                yield f"\n\n（模型调用失败 {resp.status_code}：{body}）"
                return
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0].get("delta", {}).get("content")
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if delta:
                    yield delta
