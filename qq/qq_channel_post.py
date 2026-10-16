#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IG队列 -> QQ频道论坛发帖（仅文字+图片，正文零链接）
队列: /root/ig_post_queue/<code>/task.json {code,caption,link,images:[本地路径]}
流程: 每图经 NapCat 私聊上传 -> 取腾讯CDN URL -> RichJSON 富文本 PUT 发帖
状态: 成功写 task.json status=posted；失败保留待下轮重试；日志 /root/qq_post.log
"""
import json, os, re, time, base64, html, urllib.request

APPID = os.environ.get("QQ_APP_ID", "").strip()
SECRET = os.environ.get("QQ_APP_SECRET", "").strip()
if not APPID or not SECRET:
    raise RuntimeError("QQ_APP_ID and QQ_APP_SECRET are required")
CHANNEL = os.environ.get("QQ_DEFAULT_CHANNEL", "").strip()
NAPCAT = os.environ.get("NAPCAT_URL", "http://127.0.0.1:3001").rstrip("/")
ADMIN = int(os.environ.get("NAPCAT_UPLOAD_USER_ID", "0"))
QUEUE = os.environ.get("QUEUE_DIR", os.path.join(os.path.dirname(__file__), "..", "runtime", "ig_post_queue"))
TOKEN_FILE = os.environ.get("QQ_TOKEN_FILE", os.path.join(os.path.dirname(__file__), "..", "runtime", "qq_bot_token.json"))
LOG = os.environ.get("QQ_LOG_FILE", os.path.join(os.path.dirname(__file__), "..", "runtime", "qq_post.log"))
MAX_TASKS = int(os.environ.get("QQ_MAX_TASKS", "0") or "0")

if not CHANNEL or not ADMIN:
    raise RuntimeError("QQ_DEFAULT_CHANNEL and NAPCAT_UPLOAD_USER_ID are required")

def log(msg):
    line = time.strftime("%m-%d %H:%M:%S ") + str(msg)
    print(line)
    try: open(LOG, "a").write(line + "\n")
    except Exception: pass

def http(method, url, body=None, headers=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items(): req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode()
    return json.loads(raw) if raw.strip() else {}

def get_token():
    if os.path.exists(TOKEN_FILE):
        try:
            c = json.load(open(TOKEN_FILE))
            if time.time() - c["ts"] < 7000: return c["token"]
        except Exception: pass
    r = http("POST", "https://bots.qq.com/app/getAppAccessToken",
             {"appId": APPID, "clientSecret": SECRET})
    tok = r["access_token"]
    json.dump({"token": tok, "ts": time.time()}, open(TOKEN_FILE, "w"))
    return tok

def api(method, path, body=None):
    return http(method, "https://api.sgroup.qq.com" + path, body,
                {"Authorization": "QQBot " + get_token()})

def napcat(endpoint, body):
    return http("POST", NAPCAT + endpoint, body, timeout=60)

def upload_image(fp):
    b64 = base64.b64encode(open(fp, "rb").read()).decode()
    r = napcat("/send_private_msg", {"user_id": ADMIN,
        "message": [{"type": "image", "data": {"file": "base64://" + b64}}]})
    if r.get("retcode") != 0: raise RuntimeError("send fail " + str(r)[:120])
    mid = r["data"]["message_id"]
    time.sleep(1.5)
    d = napcat("/get_msg", {"message_id": mid})
    for seg in d["data"]["message"]:
        if seg.get("type") == "image":
            return html.unescape(seg["data"]["url"])
    raise RuntimeError("no image url in msg " + str(mid))

URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.I)

def clean_caption(cap):
    cap = URL_RE.sub("", cap or "")
    cap = re.sub(r"[ \t]+", " ", cap)
    cap = re.sub(r"\n{3,}", "\n\n", cap)
    return cap.strip()

def build_title(cap):
    line = (cap or "").split("\n")[0].strip()
    line = re.sub(r"#\S+", "", line).strip()
    return (line[:30] or "Minecraft 官方动态")

def build_richjson(cap, urls):
    paras = []
    if cap:
        for seg in [s.strip() for s in cap.split("\n\n") if s.strip()]:
            paras.append({"elems": [{"type": 1, "text": {"text": seg}}], "props": {}})
    if urls:
        para = {"elems": [{"type": 2, "image": {"third_url": u, "width_percent": 1.0}} for u in urls], "props": {}}
        paras.append(para)
    return json.dumps({"paragraphs": paras}, ensure_ascii=False)

def mark_posted(d, posted_map):
    task = json.load(open(os.path.join(d, "task.json")))
    task["posted_channels"] = posted_map
    task["status"] = "posted" if len(posted_map) >= len(task.get("targets") or [CHANNEL]) else task.get("status", "partial")
    task["posted_ts"] = int(time.time())
    json.dump(task, open(os.path.join(d, "task.json"), "w"), ensure_ascii=False)

def process(d):
    tf = os.path.join(d, "task.json")
    task = json.load(open(tf))
    if task.get("status") == "posted": return False
    targets = task.get("targets") or [CHANNEL]
    posted_map = task.get("posted_channels") or {}
    todo = [t for t in targets if not posted_map.get(t)]
    if not todo: return False
    cap = clean_caption(task.get("caption", ""))
    urls = []
    for fp in (task.get("images") or [])[:9]:
        if not os.path.exists(fp):
            log("  img missing: " + fp); continue
        try:
            urls.append(upload_image(fp)); log("  img ok: " + os.path.basename(fp))
            time.sleep(1)
        except Exception as e:
            log("  img FAIL %s: %s" % (os.path.basename(fp), str(e)[:100]))
    if not cap and not urls:
        log("  empty task, skip " + d); return False
    title = build_title(cap)
    body = {"title": title, "content": build_richjson(cap, urls), "format": 4}
    n = 0
    for ch in todo:
        try:
            r = api("PUT", "/channels/%s/threads" % ch, body)
            posted_map[ch] = r.get("task_id", "")
            log("POSTED %s -> ch=%s task_id=%s (imgs=%d)" % (task.get("code"), ch, r.get("task_id"), len(urls)))
            n += 1; time.sleep(2)
        except Exception as e:
            log("  POST FAIL %s ch=%s: %s" % (task.get("code"), ch, str(e)[:120]))
    if posted_map: mark_posted(d, posted_map)
    return n > 0

def main():
    log("=== runner start ===")
    n = 0
    if not os.path.isdir(QUEUE):
        log("no queue dir"); return
    for code in sorted(os.listdir(QUEUE)):
        if MAX_TASKS and n >= MAX_TASKS:
            log("达到本轮任务上限=%d，剩余任务留待下轮" % MAX_TASKS)
            break
        d = os.path.join(QUEUE, code)
        if not os.path.isdir(d): continue
        if not os.path.exists(os.path.join(d, "task.json")): continue
        try:
            if process(d): n += 1; time.sleep(2)
        except Exception as e:
            log("TASK FAIL %s: %s" % (code, str(e)[:200]))
    log("=== done, posted=%d ===" % n)

if __name__ == "__main__":
    main()
