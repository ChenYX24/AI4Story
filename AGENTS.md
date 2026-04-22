# AGENTS.md — AI 协作开发者指南

> 读这份文件：你能在 30 分钟内接手这个项目继续开发。  
> 对话式迭代的项目节奏快，很多决策没写进 ADR；这份文件给你"状态快照 + 意图 + 未完成清单"。

## 1. 项目一句话

**漫秀 MindShow** — 面向学龄前儿童的 AI 互动绘本剧场：文字/视频/音频/手绘 → AI 拆章节生成绘本 → 小孩参与互动（拖拽角色道具 + 说话 + 创造新道具）→ 自动出成长报告给家长。

- 远端：https://github.com/ChenYX24/AI4Story
- 本地主工作目录：`/Users/cyx/projects/AI4Story_v2/`
- 原版备份：`/Users/cyx/projects/AI4Story/`（KuanweiLin910730 remote，不动）

## 2. 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI + uvicorn（Python 3.13）; 内置 `sqlite3` 作账号库; 无 SQLAlchemy |
| 前端 | Vite 8 + Vue 3.5 + TypeScript + Pinia 3 + Vue Router 5 + Tailwind v4（`@theme` tokens） |
| AI | Volcengine **Seedream**（Ark API）出图；阿里云 **DashScope / Qwen** 讲故事 / 报告；小米 **MiMo v2 TTS** 语音合成；浏览器 **webkitSpeechRecognition** ASR |
| 存储 | 抽象可插拔（`apps/api/storage/`）：local（默认）/ s3 / oss，env `MINDSHOW_STORAGE` 切 |
| 账号 | SQLite（`outputs/mindshow.db`）+ hashlib sha256 + secrets token；Authorization Bearer 头部 |

## 3. 快速开始

```bash
# 0) 克隆
git clone https://github.com/ChenYX24/AI4Story.git
cd AI4Story

# 1) 拉预置图片资产 (scenes/ 下 128M, 不在 git 里)
bash scripts/fetch_assets.sh \
  --from-url https://github.com/ChenYX24/AI4Story/releases/download/assets-2026-04-22/scenes-assets-2026-04-22.tar.gz

# 2) Python env（conda 'ai4story' 已就绪）
source ~/miniconda3/etc/profile.d/conda.sh && conda activate ai4story
pip install -r requirements.txt

# 3) 三个 API key（必须）— 写到 start_webdemo.keys.sh 或直接 export
export ARK_API_KEY=ark-xxx              # Volcengine Seedream
export DASHSCOPE_API_KEY=sk-xxx         # Qwen 文本
export XIAOMI_TTS_API_KEY=sk-xxx        # 小米 MiMo v2 TTS

# 4) 一键启动（会自动 pnpm install + vite build 前端 → uvicorn 起后端）
bash start_webdemo.sh

# 5) 开发模式前端（Vite dev server 实时热更）
cd apps/web && pnpm dev   # http://127.0.0.1:5173  — 代理 /api /outputs 到 :8000
```

### 资产分发机制

- **图片永不入 git** — 45 PNG + 31 SVG + 128M 太大，历史会爆炸
- **GitHub Release** 作为分发点：每次更新 `scenes/` 后用 `scripts/pack_assets.sh` 打包，`gh release create assets-YYYY-MM-DD` 发布
- **协作者** 用 `scripts/fetch_assets.sh` 三选一恢复：
  - `--from <tar>`：本地 tar.gz（U 盘 / IM 收到的）
  - `--from-url <url>`：GitHub Release 下载
  - `--from-dir <path>`：rsync 自另一台机器
  - `MINDSHOW_ASSETS_URL` env 作为 `--from-url` 默认
- **当前 Release**：`assets-2026-04-22` — 116 条目，128M

## 4. 架构地图

```
apps/
├── api/                          # 后端 (FastAPI)
│   ├── main.py                   # 入口; 挂 routers + 静态 + SPA fallback
│   ├── config.py                 # 路径 / env 常量
│   ├── db.py                     # 内置 sqlite3 users 表（无 ORM）
│   ├── models.py                 # pydantic schema
│   ├── scene_loader.py           # 读 scenes/001/... 到 dict
│   ├── story_registry.py         # 自定义故事的 json registry
│   ├── asset_resolver.py         # 把 scenes/xx/xxx.png → url
│   ├── storage/                  # 图片/文件存储抽象
│   │   ├── base.py               #   接口
│   │   ├── local.py              #   本机 outputs/...
│   │   ├── s3.py                 #   AWS S3 / R2 / MinIO (lazy import boto3)
│   │   └── oss.py                #   阿里云 OSS (lazy import oss2)
│   ├── routers/
│   │   ├── auth.py               # register / login / me / logout
│   │   ├── public.py             # /public/stories /public/assets
│   │   ├── upload.py             # 图片上传 (base64 → storage)
│   │   ├── story.py              # /story + /scene/{idx}
│   │   ├── stories.py            # /stories CRUD for custom
│   │   ├── interact.py           # /interact → seedream → dynamic narrative
│   │   ├── create_prop.py        # /create_prop (+ reference_image_url / skip_ai)
│   │   ├── placements.py         # 默认布局
│   │   ├── chat.py               # /chat → qwen
│   │   ├── tts.py                # /tts 流 mp3/wav
│   │   ├── report.py             # /report + /report/stream (SSE)
│   │   └── share.py              # /share + /share/{id}/qr.svg + /view/{id}
│   └── services/…                # 业务实现
├── web/                          # 前端 (Vite + Vue 3 + TS)
│   ├── index.html
│   ├── vite.config.ts            # /api /outputs /assets 代理; dist assetsDir=bundle
│   ├── src/
│   │   ├── main.ts               # pinia + router + errorHandler + user.boot()
│   │   ├── App.vue               # RouterView + AppToast
│   │   ├── style.css             # Tailwind v4 @theme + tokens + shimmer + scrollbar
│   │   ├── router/index.ts       # / /library /story/:id /story/:id/report /profile
│   │   ├── api/
│   │   │   ├── client.ts         # fetch wrapper + Authorization Bearer 注入
│   │   │   ├── endpoints.ts      # 各 API 的 named export
│   │   │   └── types.ts          # TS schema
│   │   ├── stores/               # pinia: user / story / session / shelf / toast
│   │   ├── composables/          # useReportStream / useTTSPreload / useASR / useKeyboardShortcuts
│   │   ├── components/           # Base* / TopBar / CinemaHero / InteractiveView / SketchPadModal / CustomPropCreateModal / Skeleton / AppToast
│   │   └── pages/                # Landing / Library / Story / Report / Profile / NotFound
│   └── dist/                     # 构建产物；main.py 优先 serve，缺则退 web-legacy
└── web-legacy/                   # 原生 JS 老版本（参考 / 回滚保险）
contracts/openapi/openapi.yaml   # SSOT 骨架（阶段 1 需补）
scenes/                          # 预置剧本 + 官方人物道具 PNG；.gitignore
outputs/                         # 运行时产物（mindshow.db + 图片 + 会话）；.gitignore
agent-docs/                      # 本地开发文档（plan / adr / check_report）；.gitignore
```

## 5. 已完成里程碑

### 2026-04-22 Day 1 — M0 基建
- 从 `KuanweiLin910730/AI4Story` 迁移到 `ChenYX24/AI4Story`
- `git filter-repo` 洗掉 96 张图片的历史（.git 189M → 472K）
- `apps/api` + `apps/web` + `packages/shared` + `contracts/openapi` monorepo 布局
- 初始 agent-docs（主计划 + 4 份 ADR + 模板）

### 2026-04-22 Day 1 — M1 Feature 骨架（原生 JS 版）
- F5 书本翻页 UI
- F7 新首页（胶片 hero + MindShow 品牌）
- F1 假登录 + 三 tab 个人页骨架
- F8 报告流水线 SSE 骨架

### 2026-04-22 Day 1 — Vue 重构（大改）
- 整个前端换成 Vite + Vue 3 + TS + Tailwind v4
- 5 个页面、7+ 基础组件、3 个 composable、4 个 pinia store
- 后端 main.py 服务 dist + SPA fallback + 自动 build 脚本

### 2026-04-22 Day 1 — 真功能（Round "占位变真"）
- **互动场景**：InteractiveView 300+ 行，拖拽 / ops 序列 / 自定义道具
- **聊天 + ASR**：`useASR` + `postChat` + TTS 朗读 reply
- **报告 SSE**：`useReportStream` + 三阶段 + per-scene + chunk 可视化
- **Profile**：真数据（story list + session localStorage）
- **API 字段对齐**：scene.type（不是 kind）/ character.default_x/y / 等，修"图片不加载"bug
- **TTS 预载、下一幕 prefetch、分享 QR + 漫画条、Library 编辑标题 + 红点**（补齐 legacy parity）

### 2026-04-22 Day 2 — 打磨 + 体验
- 键盘快捷键 / 骨架屏 / 切故事 reset / 404 / PWA favicon + manifest / 图片 lazy / Cinema 鼠标视差
- 旁白移右侧 / 解锁 bug / timeline 真缩略图
- 互动场景：初始只角色 / 金色 loading 覆盖 / 3 按钮（上传/拍照/画板）
- **SketchPadModal**：画板（7 色 + 粗细 + 橡皮 + 撤销 + 清空）
- **公共平台真后端**：`/api/public/stories` + `/api/public/assets`（10 件官方道具）
- **账号系统真实现**：sqlite3 + auth（register/login/me/logout）+ Bearer 拦截器
- **Vue 图片上传**：`/api/upload/image` + 手绘 tab 能真创建故事
- 互动物体：工具条 + 角落 `⇲` 拖拽（scale+rotate）+ 双指 pinch 手势 + 选中外框
- 热门故事 tab 含小红帽（按 likes 排序）
- **Profile CRUD**：书架 ☆/★ 切换、stories 拆"收藏/原创"、会话删除
- **图生图模态**：上传/拍/画的原图 → `CustomPropCreateModal` → 填名称+描述 → 选"AI 再画"或"直接用原图"
- **Storage backend 可插拔**：local / s3 / oss（当前 upload.py 已用，其余待迁）

## 6. 未完成的 TODO（按优先级 + 预估）

### 🔴 高（用户体验 blocker）
- [ ] **视频导入 tab 真功能**（Landing）  
  依赖：`yt-dlp` 拉视频 → `ffmpeg` 抽帧 → `whisper` / DashScope ASR 出字幕 → qwen 生成剧本；`requirements.txt` 加 `yt-dlp`  
  难度：大（~1 天）
- [ ] **语音讲述 tab 真功能**  
  前端：`MediaRecorder` → 录音 blob → 后端 ASR → 文本喂 `createCustomStory`  
  后端：新 `/api/audio/transcribe`，DashScope ASR 或 whisper-api  
  难度：中（半天）

### 🟠 中（功能完整性）
- [ ] **Seedream / narrative_generator 迁移到 storage backend**  
  当前 `services/narrative_generator.py`、`services/prop_generator.py` 里都是直接写 `OUTPUTS_ROOT`，要改为 `get_storage().save_bytes(key, bytes)`  
  难度：中
- [ ] **账号系统把 stories/sessions/shelf 搬进 DB**  
  现在 shelf 是 localStorage，stories 是文件 json，sessions 是 localStorage。阶段 2 要入 users 关联表：`user_stories`、`user_sessions`、`user_assets`  
  难度：中（ADR-002 有 schema 设计）
- [ ] **图生图真做**（不是 prompt 里加一句提示）  
  Volcengine Seedream 有 image-to-image 接口，要改 `seedream_client.py` 支持"参考图 + 描述"模式  
  难度：中
- [ ] **真正的 per-scene LLM 总结**（报告 SSE 升级）  
  目前 per-scene 是前端视觉假进度，后端仍然整体计算。要改 `services/report_service.py` 做真正的分场景并发 LLM call  
  难度：中
- [ ] **公共平台真"大家分享"**  
  现在 `/api/public/stories` 只是列本机所有故事。真产品需要"分享码"机制：用户主动分享 → 入分享池 → 他人看到  
  难度：大（依赖账号完整性）

### 🟡 低（打磨）
- [ ] **交互场景"故事书纸纹"装饰**（纸张纹理 + 墨水边框）
- [ ] **ESLint + Prettier + CI**（GitHub Actions 跑 lint + build）
- [ ] **Vitest 基础单元测试**
- [ ] **报告页按 scene 分段回顾**（每幕一张小漫画 + 孩子那幕做了什么）
- [ ] **分享页增强**：分不同分享目标（整故事 / 小孩成就 / 家长报告）生成不同 QR
- [ ] **移动端触摸交互全面测试**（特别是 iPad 用画板）

## 7. Agent 协作规范

### 命名
- 新组件 `PascalCase.vue` 放 `src/components/`；页面放 `src/pages/*Page.vue`
- Pinia store：`use*Store`
- Composable：`use*`
- API 函数：动词式（`fetchX` / `postX` / `deleteX`）
- Python：snake_case；新 router 在 `apps/api/routers/`，service 在 `apps/api/services/`

### Commit
- `feat(scope): ...` / `fix(scope): ...` / `refactor(scope): ...`
- 中文描述可以，但 subject 建议短（< 70 字），细节写 body
- Co-authored-By 保留 Claude 署名

### 构建
```bash
cd apps/web && pnpm build    # 必须通过 vue-tsc + vite build
# 后端无 build step
```

### 本地文档
- `agent-docs/plan/`        — 计划（Markdown）
- `agent-docs/adr/`         — ADR-NNN 决策记录
- `agent-docs/check_report/` — 阶段验收
- `agent-docs/debug_fix/`    — 调试记录
- 所有 `agent-docs/*` 都 `.gitignore`，不入远端。要留给协作的文档放**仓库根**（如本文件）。

### API 合约
目前 `contracts/openapi/openapi.yaml` 是骨架，未全量。若加 endpoint，至少记到这里作为参考；全量 schema 由 M 后阶段（见 ADR-004）。

### 风格
- 设计 token 在 `apps/web/src/style.css` 的 `@theme` 块里；颜色走 `bg-paper / text-ink / border-gold` 等 utility，**不硬编码 hex**
- 深色胶片风 (landing hero) 是品牌调性；故事内用暖色童话风
- 动画尊重 `prefers-reduced-motion`

### 数据持久化
- 后端：`apps/api/storage/` 抽象（**新代码都走这层**）
- 前端本地：`useLocalStorage`（@vueuse）+ Pinia；key 统一加 `mindshow_` 前缀
- Token 存 `mindshow_token`，由 `api/client.ts` 自动带

## 8. 关键环境变量

| 变量 | 默认 | 用途 |
|---|---|---|
| `ARK_API_KEY` | — | Seedream 出图（必须） |
| `DASHSCOPE_API_KEY` | — | Qwen 文本（必须） |
| `XIAOMI_TTS_API_KEY` | — | 小米 MiMo v2 TTS（必须） |
| `MINDSHOW_STORAGE` | `local` | `local` / `s3` / `oss` |
| `MINDSHOW_AUTH_SALT` | `mindshow-dev-salt-2026-04` | 密码 hash salt（生产必须改） |
| `MINDSHOW_S3_BUCKET` | — | S3 桶名（MINDSHOW_STORAGE=s3 时） |
| `MINDSHOW_S3_REGION` | `us-east-1` | |
| `MINDSHOW_S3_ENDPOINT` | — | S3 兼容端点（R2/MinIO/DO Spaces） |
| `MINDSHOW_S3_PREFIX` | `mindshow/` | |
| `MINDSHOW_S3_PUBLIC_BASE` | — | CDN/自定义域 |
| `MINDSHOW_S3_ACL` | `public-read` | |
| `MINDSHOW_OSS_BUCKET` | — | OSS bucket |
| `MINDSHOW_OSS_ENDPOINT` | — | OSS endpoint |
| `MINDSHOW_OSS_AK_ID` / `_AK_SECRET` | — | 凭证 |
| `MINDSHOW_OSS_PREFIX` | `mindshow/` | |
| `MINDSHOW_OSS_PUBLIC_BASE` | — | CDN |
| `AI4STORY_PYTHON` | — | start_webdemo.sh 选 python 可执行 |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | uvicorn |

## 9. 已知坑

- `user_by_token` 每次查 DB，qps 高时会成瓶颈 — 阶段 2 加 in-process 缓存或 Redis
- SQLite 单写锁，多并发注册/生成会卡；换 Postgres 即可
- Seedream 出图 30-90s，无超时重试机制；失败用户只能重试整幕
- TTS preload 并发拉所有句子音频，小流量但带宽占用明显 — 可 lazy load
- `agent-docs/` 是 local-only，本仓库根的 `AGENTS.md` 才是对外的协作入口
- Vue dev server 和 uvicorn 同时跑：前端在 5173，后端在 8000；Vite 代理 `/api`、`/outputs`、`/assets/scenes` 到 8000（见 `vite.config.ts`）

## 10. 联系 / 决策记录

- 本对话历史有所有细节，但不可见。实际关键决策在 `agent-docs/adr/ADR-001~004`（本地）
- 仓库提交历史按功能分 commit，粒度细，可以 `git log --oneline` 看整个演进
- 设计风格参考：温暖童话 + 胶片金色 accent（ADR-003）

---

**Last updated**: 2026-04-22
