#!/usr/bin/env python3
"""Prepare a visible X login session for GetX.
Run this interactively once. It opens the same isolated persistent browser
profile used by the scheduler; no Instagram cookies are read or modified.
"""
from __future__ import annotations
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
PROFILE = Path(os.environ.get("GETX_BROWSER_PROFILE", str(ROOT.parent / "runtime" / "getx_browser_profile")))
URL = os.environ.get("GETX_X_PROFILE", "https://x.com/Minecraft")
PROXY = os.environ.get("HTTPS_PROXY", os.environ.get("HTTP_PROXY", "http://127.0.0.1:7890"))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
PROFILE.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    kwargs = {"headless": False, "user_agent": UA}
    if PROXY:
        kwargs["proxy"] = {"server": PROXY}
    ctx = p.chromium.launch_persistent_context(str(PROFILE), **kwargs)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    print("请在打开的 X 页面完成登录。完成后回到终端按 Enter 保存会话。", flush=True)
    input()
    print("当前页面:", page.url, flush=True)
    ctx.close()
print("GetX 会话已保存:", PROFILE)
