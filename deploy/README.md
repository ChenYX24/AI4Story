# 部署说明

> 服务器：`root@115.190.116.57`（host alias `zwh-txy-sever`），目录 `~/hackthron/AI4Story`
> 形态：前后端分离 — nginx 跑前端 dist + 反代 API 到 uvicorn :8000

## 1. SSH 公钥（一次性）

把这条公钥加到服务器 `/root/.ssh/authorized_keys`，让 Claude / CI 能 ssh：
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIh+iloOanqu9IVRsUWjbqufLTxtEqfG9lwpT2FKkpTM 2501212885@stu.pku.edu.cn
```

## 2. 首次部署

ssh 到服务器后：
```bash
mkdir -p /root/hackthron && cd /root/hackthron
git clone https://github.com/ChenYX24/AI4Story.git
cd AI4Story

# 复制 .env 模板，填真实 secret（OSS Key、ARK_API_KEY、DASHSCOPE_API_KEY、TTS Key、AUTH_SALT）
cp deploy/.env.example .env
nano .env

# 一键部署（首次安装 systemd + nginx + 跑 seed_official）
bash deploy/deploy_server.sh --first-time
```

完成后：
- 前端：http://115.190.116.57:8818/
- 后端：http://115.190.116.57:8818/api/

## 3. 后续升级

代码 push 上 GitHub 后，在服务器：
```bash
cd /root/hackthron/AI4Story
bash deploy/deploy_server.sh
```

或本地直接：
```bash
ssh zwh-txy-sever 'cd /root/hackthron/AI4Story && bash deploy/deploy_server.sh'
```

## 4. 故障排查

```bash
# 后端日志（systemd）
journalctl -u ai4story -f

# 后端单跑（调试）
cd /root/hackthron/AI4Story
source .venv/bin/activate
set -a; . ./.env; set +a
python -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000

# 前端没更新 → 检查 dist 是否同步
ls -la /var/www/ai4story/

# OSS 连通性
python -c "
import os, oss2
os.environ.setdefault('MINDSHOW_STORAGE','oss')
from apps.api.storage import get_storage
s = get_storage()
url = s.save_bytes('debug/ping.txt', b'ok', content_type='text/plain')
print(url)
"

# nginx
nginx -t && systemctl reload nginx
```

## 5. 双模式（local / server）

后端通过 `MINDSHOW_STORAGE` env 控制：
- `MINDSHOW_STORAGE=local`（默认）— 图片落 `outputs/webdemo/...`，URL 形如 `/outputs/...`
- `MINDSHOW_STORAGE=oss` — 图片落 OSS，URL 形如 `https://mindshow-pku.oss-cn-shenzhen.aliyuncs.com/...`

前端通过 `VITE_API_BASE` env 控制（构建时 baked）：
- 空 / 不设 — 走相对路径，由 nginx 同源代理
- `https://api.your-domain.com` — 跨域直连

本地开发：`pnpm dev` 走 vite proxy，没 OSS 也能跑（后端用 `MINDSHOW_STORAGE=local`）。
服务器：用 OSS + 同源 nginx。
