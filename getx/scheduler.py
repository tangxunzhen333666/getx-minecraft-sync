#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GetX scheduler: fetch once 08:00-11:00; deliver backlog one item/3h."""
from __future__ import annotations
import argparse, datetime as dt, json, os, random, subprocess, sys, time
from pathlib import Path
from zoneinfo import ZoneInfo
BASE=Path(os.environ.get("GETX_DIR",os.path.dirname(__file__))).resolve(); ROOT=BASE.parent
RUNTIME=Path(os.environ.get("RUNTIME_DIR",str(ROOT/"runtime"))).resolve()
FETCH=Path(os.environ.get("GETX_FETCH",str(BASE/"getx_fetch.py"))).resolve(); POSTER=Path(os.environ.get("QQ_POSTER",str(ROOT/"qq"/"qq_channel_post.py"))).resolve()
QUEUE=Path(os.environ.get("GETX_QUEUE_DIR",str(RUNTIME/"getx_post_queue"))).resolve(); SCHED=Path(os.environ.get("GETX_SCHEDULER_STATE",str(RUNTIME/"getx_scheduler_state.json"))).resolve(); DELIVERY=Path(os.environ.get("GETX_DELIVERY_STATE",str(RUNTIME/"getx_delivery_state.json"))).resolve(); LOG=Path(os.environ.get("GETX_SCHEDULER_LOG",str(RUNTIME/"getx_scheduler.log"))).resolve()
PYTHON=os.environ.get("GETX_PYTHON",sys.executable); TZ=ZoneInfo(os.environ.get("TIMEZONE","Asia/Shanghai")); GAP=int(os.environ.get("GETX_DELIVERY_GAP",str(3*3600)))
def now(): return dt.datetime.now(TZ)
def log(s):
 line=f"[{now().isoformat(timespec='seconds')}] {s}"; print(line,flush=True); LOG.parent.mkdir(parents=True,exist_ok=True); LOG.open("a",encoding="utf-8").write(line+"\n")
def read(p,d):
 try:return json.loads(p.read_text(encoding="utf-8"))
 except Exception:return d
def save(p,v):
 p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix(p.suffix+".tmp"); t.write_text(json.dumps(v,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); os.replace(t,p)
def slot(day): return dt.datetime.combine(day,dt.time(8),TZ)+dt.timedelta(seconds=random.randrange(10800))
def next_slot(n):
 try:
  x=dt.datetime.fromisoformat(read(SCHED,{}).get("next_run")).astimezone(TZ)
  if x>n:return x
 except Exception:pass
 a=dt.datetime.combine(n.date(),dt.time(8),TZ); b=dt.datetime.combine(n.date(),dt.time(11),TZ)
 if n<a:return slot(n.date())
 if n<b:return n+dt.timedelta(seconds=random.randrange(max(1,int((b-n).total_seconds()))))
 return slot(n.date()+dt.timedelta(days=1))
def pending():
 out=[]
 if not QUEUE.is_dir():return out
 for name in sorted(os.listdir(QUEUE)):
  p=QUEUE/name/"task.json"
  if p.is_file():
   try:
    if json.loads(p.read_text(encoding="utf-8")).get("status")!="posted":out.append(name)
   except Exception:pass
 return out
def due():
 x=read(DELIVERY,{}).get("next_delivery_at")
 if not x:return True
 try:return dt.datetime.fromisoformat(x).astimezone(TZ)<=now()
 except Exception:return True
def set_next():
 p=pending(); save(DELIVERY,{"timezone":"Asia/Shanghai","next_delivery_at":(now()+dt.timedelta(seconds=GAP)).isoformat() if p else None,"pending":len(p)})
def deliver(force=False):
 p=pending()
 if not p or (not force and not due()):return False
 env=os.environ.copy(); env.update(GETX_QUEUE_DIR=str(QUEUE),QUEUE_DIR=str(QUEUE),QQ_MAX_TASKS="1")
 log("发送一条积存，发送前剩余=%d"%len(p)); r=subprocess.run([PYTHON,str(POSTER)],cwd=str(ROOT),env=env,capture_output=True,text=True,timeout=600)
 for x in (r.stdout or "").splitlines():log("[qq] "+x)
 for x in (r.stderr or "").splitlines():log("[qq err] "+x)
 if r.returncode:raise RuntimeError(f"QQ发帖失败 exit={r.returncode}")
 set_next();return True
def fetch_once():
 before=len(pending()); env=os.environ.copy();env.update(GETX_DIR=str(BASE),GETX_QUEUE_DIR=str(QUEUE),QUEUE_DIR=str(QUEUE))
 log("开始抓取，抓取前积存=%d"%before);r=subprocess.run([PYTHON,str(FETCH),"--once"],cwd=str(ROOT),env=env,capture_output=True,text=True,timeout=360)
 for x in (r.stdout or "").splitlines():log("[fetch] "+x)
 for x in (r.stderr or "").splitlines():log("[fetch err] "+x)
 if r.returncode:raise RuntimeError(f"GetX抓取失败 exit={r.returncode}")
 after=len(pending());log("抓取后积存=%d，新增加=%d"%(after,max(0,after-before)))
 if before==0 and after:deliver(True)
 elif due():deliver(True)
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--once",action="store_true");ap.add_argument("--dry-run",action="store_true");a=ap.parse_args()
 if a.once:
  try:
   if pending():deliver(True)
   else:fetch_once()
   return 0
  except Exception as e:log(f"单次失败：{type(e).__name__}: {str(e)[:300]}");return 1
 while True:
  n=now(); target=next_slot(n);save(SCHED,{"timezone":"Asia/Shanghai","next_run":target.isoformat()});log("下次随机获取时间："+target.isoformat())
  if a.dry_run:return 0
  try:
   if due():deliver()
  except Exception as e:log(f"积存发送失败：{type(e).__name__}: {str(e)[:200]}")
  while True:
   wait=(target-now()).total_seconds()
   if wait<=0:break
   time.sleep(min(60,max(1,wait)))
   try:
    if due():deliver()
   except Exception as e:log(f"积存发送失败：{type(e).__name__}: {str(e)[:200]}")
  try:fetch_once()
  except Exception as e:log(f"本次获取失败：{type(e).__name__}: {str(e)[:200]}")
  save(SCHED,{"timezone":"Asia/Shanghai","next_run":slot(now().date()+dt.timedelta(days=1)).isoformat()});time.sleep(2)
if __name__=="__main__":raise SystemExit(main())