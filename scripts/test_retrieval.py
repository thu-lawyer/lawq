#!/usr/bin/env python3
"""律问 · 检索自测：典型问题应命中正确的法律与条文"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import retrieval  # noqa: E402

CASES = [
    # (问题, 期望命中的法律关键词, 期望条号(可选，直查/高分), 说明)
    ("小区里被高空抛物砸伤，找谁赔偿？", "民法典", 1254, "高空抛物"),
    ("试用期被辞退有经济补偿吗", "劳动合同法", None, "试用期"),
    ("什么情况属于正当防卫", "刑法", 20, "正当防卫"),
    ("网购的商品有质量问题，可以七天无理由退货吗", "消费者权益保护法", None, "七日无理由"),
    ("协议离婚有冷静期吗，多久", "民法典", 1077, "离婚冷静期"),
    ("有限责任公司股东的出资最长期限是多久", "公司法", None, "股东出资"),
    ("酒后开车会受什么处罚", "道路交通安全法", None, "酒驾"),
    ("我的个人信息被APP泄露了怎么维权", "个人信息保护法", None, "个人信息"),
    ("民法典第1254条说了什么", "民法典", 1254, "直查：法名+条号"),
    ("借钱不还的诉讼时效是几年", "民法典", 188, "诉讼时效"),
]


def main() -> None:
    ok = 0
    for q, expect_law, expect_no, note in CASES:
        hits = retrieval.search(q, top_k=6)
        top = hits[0] if hits else None
        laws_in_hits = [h["law_name"] for h in hits]
        nos = [h.get("article_no_arabic") for h in hits]

        hit_law = any(expect_law in ln for ln in laws_in_hits)
        hit_no = expect_no is None or expect_no in nos
        rank = next((i + 1 for i, ln in enumerate(laws_in_hits) if expect_law in ln), None)
        passed = hit_law and hit_no and (rank or 99) <= 3
        ok += passed
        print(f"{'✓' if passed else '✗'} [{note}] {q}")
        print(f"   期望 {expect_law}" + (f"第{expect_no}条" if expect_no else "")
              + f" → 实际 Top1: {top['law_name'] if top else '-'}"
              f"第{top['article_no'] if top else '-'}条 (score={top['score'] if top else 0})，"
              f"{expect_law} 排名 {rank}")
    print(f"\n{ok}/{len(CASES)} 通过")
    sys.exit(0 if ok == len(CASES) else 1)


if __name__ == "__main__":
    main()
