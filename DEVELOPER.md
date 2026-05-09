# DEVELOPER.md — 开发运维手册

> 快速上手 + 部署指南 + 关键信息速查。配合 `AGENTS.md`（架构/TODO）使用。

## 1. 服务器

| 项目 | 值 |
|---|---|
| IP | **115.190.116.57** |
| 用户 | `root` |
| 项目路径 | `/root/hackthron/AI4Story` |
| 端口 | `8818`（nginx → uvicorn `:8000`） |
| 前端入口 | http://115.190.116.57:8818/ |
| 后端入口 | http://115.190.116.57:8818/api/ |

**SSH 公钥**（已配置在服务器 `authorized_keys`）：
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIh+iloOanqu9IVRsUWjbqufLTxtEqfG9lwpT2FKkpTM 2501212885@stu.pku.edu.cn
```

本地可配置 `~/.ssh/config` 别名：
```
Host zwh-txy
    HostName 115.190.116.57
    User root
```

## 2. 技术栈速览

| 层 | 技术 | 备注 |
|---|---|---|
| 后端 | FastAPI + uvicorn (Python 3.13) | SQLite 内置账号库，无 ORM |
| 前端 | Vite 8 + Vue 3.5 + TS + Pinia + Tailwind v4 | SPA，Vite 代理到后端 |
| AI 出图 | Volcengine **Seedream** (Ark API) | 四格漫画 / 道具生成 |
| AI 文本 | **Qwen** via DashScope / mikaovo (gpt-5-4) | 故事拆分、报告、聊天、ASR |
| TTS | 小米 **MiMo v2** | 逐句朗读 |
| 存储 | 可插拔：local / s3 / minio | env `MINDSHOW_STORAGE` 切换 |

## 3. 项目结构

```
AI4Story/
├── apps/
│   ├── api/                     # 后端 FastAPI
│   │   ├── main.py              # 入口，挂路由 + SPA fallback
│   │   ├── routers/             # 路由：auth/story/interact/tts/report/share/retell/...
│   │   ├── services/            # 业务：narrative_generator, qwen_service, tts_service, retell_service...
│   │   ├── storage/             # 可插拔存储：local / s3 / minio
│   │   ├── db.py                # SQLite users/sessions/stories/scenes/assets 表
│   │   ├── scene_loader.py      # 场景数据加载（DB 优先 → 文件回落）
│   │   └── asset_resolver.py    # 资源路径解析
│   └── web/                     # 前端 Vue 3
│       ├── src/
│       │   ├── pages/           # Landing / Library / Story / Report / Retell / Profile
│       │   ├── components/      # InteractiveView (互动舞台) / RetellXxx / TopBar / ...
│       │   ├── composables/     # useASR / useTTSPreload / useRetell / ...
│       │   ├── stores/          # Pinia: user / story / session / interact / ...
│       │   └── api/             # client.ts (fetch wrapper + thumbUrl) / endpoints.ts / types.ts
│       └── dist/                # 构建产物
├── scenes/                      # 预置剧本 + 官方 PNG 资产（不入 git，通过 scripts/fetch_assets.sh 拉取）
├── outputs/                     # 运行时产物（DB + 图片 + 会话）
├── deploy/                      # 部署脚本 + systemd + nginx 配置
├── scripts/                     # seed_official / fetch_assets / pack_assets / ...
├── start_webdemo.sh             # 一键本地启动
└── AGENTS.md                    # AI 协作者指南（架构详情 + TODO 清单）
```

## 4. 本地开发

```bash
# 1) 拉资产
bash scripts/fetch_assets.sh

# 2) Python 环境
conda activate ai4story
pip install -r requirements.txt

# 3) 设置 API Key
export ARK_API_KEY=ark-xxx
export DASHSCOPE_API_KEY=sk-xxx
export XIAOMI_TTS_API_KEY=sk-xxx

# 4) 一键启动（后端 :8000 + 前端 build + serve）
bash start_webdemo.sh

# 5) 或前端热更新开发模式（:5173 代理 /api → :8000）
cd apps/web && pnpm dev
```

## 5. 部署

### 5.1 首次部署

```bash
ssh root@115.190.116.57
mkdir -p /root/hackthron && cd /root/hackthron
git clone https://github.com/ChenYX24/AI4Story.git
cd AI4Story

# 配置 .env（填真实 API Key / MinIO 凭证 / AUTH_SALT）
cp deploy/.env.example .env
nano .env

# 一键部署
bash deploy/deploy_server.sh --first-time
```

### 5.2 日常升级

方式一 — SSH 到服务器：
```bash
ssh root@115.190.116.57 'cd /root/hackthron/AI4Story && bash deploy/deploy_server.sh'
```

方式二 — push 到 main 分支自动触发 GitHub Actions CI 部署（`.github/workflows/deploy.yml`）。

### 5.3 部署流程（deploy_server.sh 做了什么）

1. `git fetch + reset --hard origin/main`
2. 杀掉旧 uvicorn 进程
3. 安装/更新 venv + pip 依赖
4. 首次：`python -m scripts.seed_official`（录入官方场景到 DB + MinIO）
5. `pnpm install + pnpm build` 构建前端
6. `rsync dist/ → /var/www/ai4story`
7. 首次：安装 systemd unit + nginx 配置
8. `systemctl restart ai4story && nginx reload`

### 5.4 环境变量

| 变量 | 用途 | 必填 |
|---|---|---|
| `ARK_API_KEY` | Seedream 出图 | ✅ |
| `LLM_API_KEY` | 主语言模型 (mikaovo) | ✅ |
| `DASHSCOPE_API_KEY` | Qwen ASR 语音识别 | ✅ |
| `XIAOMI_TTS_API_KEY` | 小米 TTS | ✅ |
| `MINDSHOW_STORAGE` | `local` / `minio` | ✅ |
| `MINDSHOW_MINIO_*` | MinIO 连接参数 | 仅 minio 模式 |
| `MINDSHOW_AUTH_SALT` | 密码 hash salt | ✅ |
| `VITE_API_BASE` | 前端 API 地址（空=同源） | — |

## 6. 图片加载架构

```
前端请求 thumbUrl(url, width) → /api/image/proxy?path=...&width=320
                                      │
                                      ▼
                              image_proxy.py
                              ├── 读原始图片 (scenes/ 或 outputs/)
                              ├── PIL resize + WebP encode (quality 80)
                              ├── 磁盘缓存 → outputs/.thumbs/<hash>.webp
                              └── 返回 WebP + Cache-Control: max-age=31536000, immutable
```

**前端使用规范**：
- Sidebar 缩略图：`thumbUrl(url, 128)`
- 舞台道具：`thumbUrl(url, 320)`
- 背景图：`thumbUrl(url, 900)`
- 漫画图：`thumbUrl(url, 700)`
- 所有 `<img>` 加 `loading="lazy"` + `decoding="async"`（背景除外用 `eager`）

## 7. 当前功能状态

### 已完成
- 视频导入（B 站链接 → yt-dlp → ASR → Qwen 改编 → 绘本生成）
- Storage backend 迁移（narrative_generator 走 get_storage）
- 账号系统入 DB（users/sessions/stories/scenes/assets 表）
- 图生图（Seedream reference_images）
- 公共分享（QR + /view/:id）
- Retell 复述模式（AI 引导提示 + 语音反馈 + 进度条 + 总结）
- 图片 WebP 代理 + 缩略图 + lazy loading
- 互动舞台渐进式引导提示

### 待完成
- **语音讲述 tab 真功能**（独立 `/api/audio/transcribe` 端点）
- **真正的 per-scene LLM 报告**（分场景并发 LLM call）
- ESLint + Prettier + CI 检查
- Vitest 单元测试
- 移动端触摸全面测试

## 8. 故障排查

```bash
# 后端日志
ssh root@115.190.116.57 'journalctl -u ai4story -f'

# 后端手动调试
ssh root@115.190.116.57
cd /root/hackthron/AI4Story
source .venv/bin/activate
set -a; . ./.env; set +a
python -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000

# 前端没更新 → 检查 dist
ls -la /var/www/ai4story/

# nginx 重载
ssh root@115.190.116.57 'nginx -t && systemctl reload nginx'

# MinIO 连通性
python -c "
import os
os.environ.setdefault('MINDSHOW_STORAGE','minio')
from apps.api.storage import get_storage
s = get_storage()
url = s.save_bytes('debug/ping.txt', b'ok', content_type='text/plain')
print(url)
"

# 重启服务
ssh root@115.190.116.57 'systemctl restart ai4story && systemctl reload nginx'
```

## 9. Git 仓库

- 远端：https://github.com/ChenYX24/AI4Story
- 分支策略：`main` 直接 push，CI 自动部署
- Commit 格式：`feat(scope): ...` / `fix(scope): ...` / `refactor(scope): ...`
- 图片不入 git（通过 GitHub Release 分发：`assets-2026-04-22`）

---

**Last updated**: 2026-05-09
