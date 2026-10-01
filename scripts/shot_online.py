#!/usr/bin/env python3
"""线上部署验证截图：登录 → 问答 → 存 screenshots/08-线上部署.png"""
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

import os
BASE = os.getenv("LAWQ_BASE_URL", "http://127.0.0.1:8790")
OUT = Path(__file__).resolve().parent.parent / "screenshots" / "08-线上部署.png"


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1380, "height": 900})
        await page.goto(BASE, wait_until="networkidle")
        await page.fill("#pwdInput", os.getenv("LAWQ_PASSWORD", ""))
        await page.click("#pwdGo")
        await page.wait_for_timeout(1200)
        await page.fill("#q", "小区里被高空抛物砸伤，找谁赔偿？")
        await page.click("#send")
        await page.wait_for_selector(".hit-card", timeout=30000)
        await page.wait_for_timeout(15000)
        await page.screenshot(path=OUT)
        await browser.close()
    print(f"✓ 线上截图 → {OUT}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
