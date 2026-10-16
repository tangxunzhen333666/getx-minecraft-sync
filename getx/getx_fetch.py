#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only GetX bridge for X @Minecraft."""
from __future__ import annotations
import argparse, datetime as dt, json, os, re, time
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, ProxyHandler, build_opener

BASE = Path(os.environ.get("GETX_DIR", os.path.dirname(__file__))).resolve()
ROOT = BASE.parent
RUNTIME = Path(os.environ.get("RUNTIME_DIR", str(ROOT / "runtime"))).resolve()
QUEUE = Path(os.environ.get("GETX_QUEUE_DIR", str(RUNTIME / "getx_post_queue"))).resolve()
SEEN_FILE = Path(os.environ.get("GETX_SEEN_FILE", str(RUNTIME / "getx_seen_posts.json"))).resolve()
LOG_FILE = Path(os.environ.get("GETX_LOG_FILE", str(RUNTIME / "getx.log"))).resolve()
PROFILE = os.environ.get("GETX_X_PROFILE", "https://x.com/Minecraft")
PROXY = os.environ.get("HTTPS_PROXY", os.environ.get("HTTP_PROXY", "http://127.0.0.1:7890"))
MAX_TWEETS = int(os.environ.get("GETX_MAX_TWEETS", "20"))
MAX_IMAGES = 9
TIMEOUT = int(os.environ.get("GETX_TIMEOUT", "60000"))
TARGETS = [x.strip() for x in os.environ.get("QQ_TARGET_CHANNELS", "705599603,727155781").split(",") if x.strip()]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
OPENER = build_opener(ProxyHandler({"http": PROXY, "https": PROXY}))
URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.I)

def log(message):
    line = f"[{dt.datetime.now().astimezone().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True); LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f: f.write(line + "\n")

def read_json(path, default):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default

def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True); tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); os.replace(tmp, path)

def clean_caption(value):
    value = re.sub(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f]", "", value or "")
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", URL_RE.sub("", value))).strip()

def media_url(url):
    url = url.replace("\\/", "/"); url = re.sub(r"([?&])name=[^&]+", r"\1name=large", url)
    return url + ("&name=large" if "name=" not in url and "?" in url else "?name=large" if "name=" not in url else "")

def download(url, target):
    with OPENER.open(Request(media_url(url), headers={"User-Agent": UA, "Referer": "https://x.com/"}), timeout=TIMEOUT / 1000) as r: data = r.read()
    if len(data) < 1500: raise RuntimeError(f"媒体过小: {len(data)} bytes")
    target.write_bytes(data); return len(data)

class ScriptParser(HTMLParser):
    def __init__(self): super().__init__(); self.items=[]; self.active=False; self.buf=""
    def handle_starttag(self, tag, attrs):
        if tag == "script": self.active=True; self.buf=""
    def handle_endtag(self, tag):
        if tag == "script" and self.active: self.items.append(self.buf); self.active=False
    def handle_data(self, data):
        if self.active: self.buf += data

def parse_public_html(raw):
    p=ScriptParser(); p.feed(raw.decode("utf-8", "replace"))
    script=next((x for x in p.items if "full_text" in x and "rest_id" in x), "")
    if not script: return []
    entry_marker = '\\"entry_id\\":\\"'
    text_re=re.compile(r'\\"full_text\\":\\"((?:\\\\.|[^"\\])*)\\"', re.S)
    id_re=re.compile(r'\\"rest_id\\":\\"(\d{10,})\\"')
    media_re=re.compile(r'\\"media_url_https\\":\\"(https:[^"\\]+)\\"')
    out=[]
    for tm in text_re.finditer(script):
        left=script.rfind(entry_marker, 0, tm.start())
        right=script.find(entry_marker, tm.end())
        segment=script[left if left >= 0 else 0:right if right >= 0 else len(script)]
        ids=list(id_re.finditer(segment))
        if not ids: continue
        tid=ids[-1].group(1)
        encoded=tm.group(1)
        try: caption=json.loads('"'+encoded+'"')
        except Exception: caption=encoded.replace('\\\\n','\n').replace('\\\\"','"').replace('\\\\/','/')
        media=[]
        for u in media_re.findall(segment):
            u=u.replace('\\/','/')
            if u not in media: media.append(u)
        out.append({"tweet_id":tid,"caption":clean_caption(caption),"media":media[:MAX_IMAGES]})
    unique={}
    for x in out: unique.setdefault(x["tweet_id"], x)
    return list(unique.values())[:MAX_TWEETS]

def write_tasks(records, source):
    seen=read_json(SEEN_FILE,{})
    if not isinstance(seen,dict): seen={}
    queued=0
    for x in records:
        tid=x["tweet_id"]
        if tid in seen: continue
        d=QUEUE/("x_"+tid); d.mkdir(parents=True,exist_ok=True); files=[]
        for i,u in enumerate(x.get("media",[])[:MAX_IMAGES]):
            fp=d/f"img_{i}.jpg"
            try: size=download(u,fp); files.append(str(fp)); log(f"图片下载成功 {tid} img_{i} {size} bytes")
            except Exception as e: log(f"图片下载失败 {tid}: {str(e)[:100]}")
        cap=x.get("caption","")
        if not cap and not files: seen[tid]={"status":"empty","ts":int(time.time())}; continue
        atomic_json(d/"task.json", {"code":"x_"+tid,"tweet_id":tid,"caption":cap,"link":"","images":files,"source":source,"from_bot":False,"targets":TARGETS,"status":"pending","created_ts":int(time.time()),"media_type":"image" if files else "text"})
        seen[tid]={"status":"queued","ts":int(time.time()),"images":len(files)}; queued+=1; log(f"已写入 GetX 队列 {tid}: text={len(cap)} chars, images={len(files)}")
    atomic_json(SEEN_FILE,seen); return queued

def fetch_public():
    with OPENER.open(Request(PROFILE,headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml"}),timeout=TIMEOUT/1000) as r: records=parse_public_html(r.read())
    if not records: log("X 匿名页面没有可解析的时间线数据"); return 3
    q=write_tasks(records,"x_getx_public"); log(f"GetX 匿名模式完成: candidates={len(records)}, queued={q}"); return 0

def fetch_browser():
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    profile=RUNTIME/"getx_browser_profile"; profile.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        kw={"headless":True,"user_agent":UA};
        if PROXY: kw["proxy"]={"server":PROXY}
        ctx=p.chromium.launch_persistent_context(str(profile),**kw); page=ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(PROFILE,wait_until="domcontentloaded",timeout=TIMEOUT); page.wait_for_timeout(5000)
            try: page.wait_for_selector('article[data-testid="tweet"]',timeout=15000)
            except PlaywrightTimeoutError: log("X 浏览器页面没有出现推文"); return 2
            articles=page.locator('article[data-testid="tweet"]'); records=[]
            for i in range(min(articles.count(),MAX_TWEETS)):
                a=articles.nth(i); hrefs=[a.locator("a").nth(j).get_attribute("href") or "" for j in range(a.locator("a").count())]; ids=re.findall(r"/status/(\d+)"," ".join(hrefs))
                if not ids: continue
                loc=a.locator('[data-testid="tweetText"]'); cap=loc.first.inner_text() if loc.count() else ""; imgs=a.locator('img[src*="pbs.twimg.com/media/"]')
                records.append({"tweet_id":ids[0],"caption":clean_caption(cap),"media":[imgs.nth(j).get_attribute("src") for j in range(min(imgs.count(),MAX_IMAGES))]})
            q=write_tasks(records,"x_getx_browser"); log(f"GetX 浏览器模式完成: candidates={len(records)}, queued={q}"); return 0
        finally: ctx.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.parse_args()
    try:
        result=fetch_public()
        return 0 if result==0 else fetch_browser()
    except Exception as e: log(f"GetX 获取失败: {type(e).__name__}: {str(e)[:300]}"); return 1

if __name__ == "__main__": raise SystemExit(main())