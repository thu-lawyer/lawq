#!/usr/bin/env python3
"""律问 · 截图脚本：首页 / 问答结果 / 法条库 / 夜间模式"""
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8790"
OUT = Path(__file__).resolve().parent.parent / "screenshots"
Q = "小区里被高空抛物砸伤，找谁赔偿？"


async def main() -> None:
    OUT.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1380, "height": 900})

        await page.goto(BASE, wait_until="networkidle")
        await page.wait_for_timeout(600)
        await page.screenshot(path=OUT / "01-首页.png")

        await page.fill("#q", Q)
        await page.click("#send")
        await page.wait_for_selector(".hit-card", timeout=30000)
        await page.wait_for_selector(".msg.assistant .bubble p:not(:first-child)", timeout=60000)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=OUT / "02-问答与法条引用.png")

        # 展开第一条法条原文
        await page.click("#hits .hit-card .hit-text")
        await page.wait_for_timeout(400)
        await page.screenshot(path=OUT / "03-法条原文展开.png")

        # 法条库
        await page.click('.tab-btn[data-tab="laws"]')
        await page.wait_for_timeout(800)
        await page.screenshot(path=OUT / "04-法条库.png")
        await page.click("#deptList .dept-item:nth-child(3)")
        await page.wait_for_timeout(800)
        await page.click("#lawList .law-card")
        await page.wait_for_timeout(1200)
        await page.screenshot(path=OUT / "05-法条原文浏览.png", full_page=False)

        # 夜间模式
        await page.click("#themeBtn")
        await page.wait_for_timeout(400)
        await page.screenshot(path=OUT / "06-夜间模式.png")

        # 移动端
        mobile = await browser.new_page(viewport={"width": 390, "height": 844})
        await mobile.goto(f"{BASE}/?q={Q}", wait_until="networkidle")
        await mobile.wait_for_selector(".hit-card", timeout=30000)
        await mobile.wait_for_timeout(15000)
        await mobile.screenshot(path=OUT / "07-移动端问答.png")

        await browser.close()
    print(f"截图完成 → {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
