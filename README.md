# GetX Minecraft Sync

只读取 X（原 Twitter） 公开动态，并同步到两个 QQ 频道。

## 功能

- 每天中国时间 08:00–11:00 随机读取一次；
- 以 X 推文 ID 去重；
- 获取正文和图片；
- 删除 X 原始链接后再发布；
- 每条内容发送到 QQ 频道 
- 有积存时每 3 小时最多发送一条；
- 没有积存时，新抓到的内容立即发送；
- 不点赞、不关注、不转发、不评论。

## 数据流

```text
X 
    ↓
GetX 抓取器
    ↓
runtime/getx_post_queue
    ↓
QQ Bot + NapCat 图片中转
    ↓
QQ 频道 705599603、727155781
```

## 安装

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# 填入 QQ AppID、AppSecret 和 NapCat 上传账号
```

Android/proot 环境可以使用已有的 Python：

```bash
export GETX_PYTHON=/root/igmon/bin/python
```

## 配置 X

X 公开时间线通常可以匿名读取。若当前网络触发登录墙，可以准备独立的只读 X 账号：

```bash
$GETX_PYTHON getx/login_session.py
```

登录态只保存在 `runtime/getx_browser_profile`，不要上传或提交该目录。建议不要使用个人主账号。

## 使用

只抓取并写入 GetX 队列：

```bash
./scripts/getx_once.sh
```

按照积存规则执行一次：

```bash
./scripts/start_getx_scheduler.sh --once
```

查看下一次随机抓取时间：

```bash
./scripts/start_getx_scheduler.sh --dry-run
```

启动常驻调度：

```bash
./scripts/start_getx_scheduler.sh
```

## 安全说明

本仓库不包含：

- QQ AppSecret、Access Token；
- X Cookie、浏览器登录态；
- NapCat 凭据；
- 历史队列、图片、视频和日志。

真实配置写入 `.env`，运行数据写入 `runtime/`，两者均已加入 `.gitignore`。

## QQ 发帖规则

QQ 正文只发送文字和图片，不发送 X 原始链接。图片经 NapCat 私聊中转到腾讯 CDN，再使用 QQ Bot RichJSON 发帖。

## 许可证

当前未附带额外许可证。
