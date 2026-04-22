# 漫秀 MindShow · AI4Story

> AI 互动绘本剧场 — 把灵感变成一本属于你的故事书

面向学龄前儿童的多模态互动绘本平台：文字 / 视频 / 音频 / 手绘都能变成故事；小孩可以拖拽角色、创造新道具、和讲故事的人聊天；玩完自动出成长报告给家长看，扫码分享给朋友。

## 一眼看效果

- 首页：电影院胶片 hero + 创作入口 + 公共平台（故事 / 资产 / 官方精选）
- 书架：自己原创的 + 收藏的 + 官方的，☆ 一下加到书架
- 播放：书本翻页 3D 动画 + 旁白朗读 + 和 AI 讲故事人聊天
- 互动：拖角色道具到背景 / 写"做什么" / 一键造新道具（AI / 手绘 / 拍照 / 画板）
- 报告：SSE 流式生成 + 三 tab（分享 / 孩子 / 家长）+ 扫码分享

## 快速开始

**1. 装依赖**
```bash
# 后端 (conda env 'ai4story')
source ~/miniconda3/etc/profile.d/conda.sh && conda activate ai4story
pip install -r requirements.txt

# 前端（Node 20+）
cd apps/web && pnpm install
```

**2. 三个必须的 API key**
```bash
cp start_webdemo.keys.sh.example start_webdemo.keys.sh  # (如无此文件，首次跑脚本自动生成)
# 编辑文件填入：
#   ARK_API_KEY           — Volcengine Seedream (出图)
#   DASHSCOPE_API_KEY     — 阿里云 Qwen (讲故事/报告)
#   XIAOMI_TTS_API_KEY    — 小米 MiMo v2 TTS (朗读)
```

**3. 一键启动**
```bash
bash start_webdemo.sh       # macOS/Linux — 自动 pnpm build + uvicorn
# 或 Windows：
start_webdemo.cmd
```

打开 `http://127.0.0.1:8000` 即可。手机扫首页底部 QR 码可同网体验。

**开发模式（前端热更）**
```bash
cd apps/web && pnpm dev     # http://127.0.0.1:5173
# 后端独立跑 (另一个终端)：bash start_webdemo.sh
```

## Monorepo 结构

```
apps/
  api/                后端 FastAPI — routers/ services/ storage/
  web/                前端 Vite + Vue 3 + TS + Tailwind v4
  web-legacy/         原生 JS 老版本（回退保险）
packages/
  shared/             预留共享类型
contracts/openapi/    API 契约（SSOT 骨架）
scripts/              脚本 (Seedream, 后处理, 故事拆分)
scenes/               预置剧本 + 官方人物道具 (本地, gitignore)
outputs/              运行时产物 (mindshow.db + 生成图 + 上传图, gitignore)
agent-docs/           本地开发文档 (gitignore)
AGENTS.md             对外协作指南 (给 AI / 开发者接手)
```

**开发文档详见 [AGENTS.md](AGENTS.md)** — 架构地图、已完成里程碑、TODO 清单、协作规范。

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | FastAPI + uvicorn + 内置 sqlite3 |
| 前端 | Vite 8 + Vue 3.5 + TypeScript + Pinia + Vue Router + Tailwind v4 |
| AI | Seedream (图) / Qwen (文) / MiMo TTS (音) / webkitSpeechRecognition (ASR) |
| 存储 | 可插拔（local / s3 / oss）—— env `MINDSHOW_STORAGE` |

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `ARK_API_KEY` | — | Seedream（必须） |
| `DASHSCOPE_API_KEY` | — | Qwen（必须） |
| `XIAOMI_TTS_API_KEY` | — | MiMo TTS（必须） |
| `MINDSHOW_STORAGE` | `local` | `local` / `s3` / `oss` |
| `MINDSHOW_AUTH_SALT` | dev-salt | 密码 hash salt（生产必改） |
| `MINDSHOW_S3_BUCKET` 等 | — | S3 相关，见 AGENTS.md §8 |
| `MINDSHOW_OSS_BUCKET` 等 | — | OSS 相关，见 AGENTS.md §8 |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | |

## 主要功能（已交付）

### 创作
- **文字描述** — 输入一段 → 后台拆章节 + 生成角色/场景 ✓
- **视频导入** — B站/抖音/YouTube/mp4 → 抽帧 + 字幕 → 剧本 🚧（开发中）
- **语音讲述** — 录音 → ASR → 剧本 🚧
- **手绘上传** — 上传图 + 描述 → AI 补全 ✓

### 播放
- 书本翻页 3D 动画 + 书脊阴影 + 书架列表 ✓
- 旁白逐句朗读（TTS 预载零延迟） ✓
- 和"讲故事的人"聊天 + 语音输入（非 iOS） ✓

### 互动
- 拖角色道具到背景，点击选中两物体 + 写"做什么"（ops 序列） ✓
- 选中后右下角落拖拽 → 同时缩放 + 旋转 ✓
- 双指 pinch（触屏） ✓
- 工具条 / 键盘：`−` `+` `↺` `↻` `✕` `Delete` `r` ✓
- 造新道具 4 种方式：✨ AI / 📁 上传 / 📷 拍照 / 🎨 画板 ✓
- 图生图 Modal：上传后加文字描述 → 选 AI 再画 / 直接用原图 ✓
- Seedream 出图期间：金色覆盖 + 5 条 hint 轮播 ✓

### 账号
- 真 SQLite + 密码 hash + Bearer token ✓
- 登录 / 注册切换；刷新自动恢复会话 ✓

### 个人页
- 🔖 书架（公共平台加到书架的）
- 📘 我的原创（自己创建的）
- 🎮 历史会话（按故事分组，点进去看报告）
- 🎨 资产（官方库预览，个人上传的 TODO）
- 全部可增删

### 报告
- SSE 流式 — 三阶段灯 + per-scene 进度条 + hint 轮播 ✓
- 渐进卡片：share → kid → parent 一块块出现 ✓
- 最终三 tab：分享页（QR+漫画条）/ 孩子报告 / 家长报告（含能力维度画像） ✓
- 局域网 IP 自动探测 — 扫码手机同网可看 ✓

### PWA
- 金色"漫"字 SVG favicon + manifest + theme-color ✓

## 演进 & 贡献

项目由 AI 辅助迭代开发（Claude）。如接手请读 [AGENTS.md](AGENTS.md)：

- 架构地图（每个文件职责）
- 今日完成的 feature（时间线）
- 未完成的 TODO（按优先级 + 难度）
- 命名 / Commit / 构建 / 风格规范
- 已知坑 & 不要踩的雷

## License

未定。内部项目。
