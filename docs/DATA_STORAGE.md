# MindShow 数据与资产存储约定

本文定义当前项目里账号、故事、会话、图片/音频/视频资产分别存在哪里，以及哪些内容不能提交到 GitHub。

## 总原则

- GitHub 只保存源码、脚本、契约、轻量配置和官方故事的结构化文本元数据。
- 用户账号、用户会话、运行时数据库、上传文件、生成图片、生成音频、下载视频、API key 都不进入 Git。
- 本地开发默认使用 SQLite + `outputs/`。生产环境建议使用服务器数据库（SQLite/Postgres）+ OSS/S3/R2 等对象存储。
- 可共享的大图片资产通过 GitHub Release tar 包、服务器对象存储或 OSS 分发，不直接 push 到仓库。

## GitHub 仓库保存的内容

保存：

- `apps/api/`、`apps/web/`、`packages/`、`contracts/`、`scripts/` 等源码和脚本。
- `scenes/` 下的官方故事 JSON / 文本结构文件，例如 `story_scenes.json`。
- `docs/`、`README.md`、`AGENTS.md` 等协作文档。

不保存：

- `outputs/` 下的所有运行时数据。
- `*.db`、`*.sqlite*` 数据库文件。
- `*.png`、`*.jpg`、`*.svg`、`*.mp3`、`*.mp4` 等大媒体文件。
- `.env`、`start_webdemo.keys.*`、任何真实 API key。
- `apps/web/dist/`、`node_modules/`、缓存、日志。

这些规则已在 `.gitignore` 中配置。

## 账号数据

当前实现：SQLite。

路径：

- `outputs/mindshow.db`

表：

- `users`
  - `id`
  - `nickname`
  - `password_hash`
  - `token`
  - `created_at`
  - `last_login_at`

新账号注册时：

1. 后端在 `users` 表创建一行。
2. 密码只保存 hash，不保存明文。
3. 登录后 token 存在 `users.token`，前端保存到 `localStorage` 的 `mindshow_token`。
4. 新账号初始没有用户故事、用户资产和会话记录；这些数据在用户创建或游玩后再写入。

生产建议：

- 小规模可以继续使用服务器磁盘上的 SQLite，并定时备份 `outputs/mindshow.db`。
- 多用户并发或正式部署建议迁移到 Postgres。

## 官方故事与官方图片资产

官方故事结构：

- `scenes/story_scenes.json`
- `scenes/<scene_id>/scene.json` 或同类结构化元数据

官方图片/角色/道具资源：

- 本地目录仍放在 `scenes/` 下对应位置。
- 但图片和 SVG 不进入 Git。
- 使用 `scripts/pack_assets.sh` 打包成 `outputs/releases/scenes-assets-YYYY-MM-DD.tar.gz`。
- 协作者使用 `scripts/fetch_assets.sh` 从 GitHub Release、本地 tar 或另一台机器恢复。

当前默认官方故事 id：

- `little_red_riding_hood`

公共平台：

- 当前 `/api/public/stories` 只返回官方公开故事。
- 用户自定义故事默认不进入公共热门故事池。

## 用户自定义故事

当前实现：文件 registry + 运行时目录。

路径：

- `outputs/webdemo/stories/registry.json`
- `outputs/webdemo/stories/<story_id>/scenes/...`

registry 字段包含：

- `id`
- `title`
- `summary`
- `input_text`
- `scene_count`
- `cover_url`
- `status`
- `owner_user_id`
- `public`
- `progress`
- `progress_label`
- `created_at`
- `updated_at`

归属规则：

- 登录用户创建的故事写入 `owner_user_id`。
- `/api/stories` 只返回官方故事 + 当前用户自己的自定义故事。
- 未登录创建的故事仅作为本地运行时数据存在，不作为公共数据共享。

生产建议：

- registry 应迁移到数据库表，例如 `stories` / `story_scenes`。
- 故事图片、封面、生成结果放 OSS/S3，对数据库只保存 URL 和元数据。

## 用户会话

当前实现：前端 localStorage 快照 + 后端 SQLite 持久化。

前端本地：

- key 前缀：`mindshow_<user_or_guest>_`
- 会话列表：`mindshow_<scope>_sessions`
- 进行中状态：`mindshow_<scope>_play_states`
- token：`mindshow_token`

后端 SQLite 表：

- `sessions`
  - `id`
  - `user_id`
  - `story_id`
  - `play_state`
  - `status`
  - `created_at`
  - `updated_at`

会话隔离规则：

- 每次游玩都有 `story_id` + `session_id`。
- 互动记录、动态生成段落、缩略图、道具、聊天记录都必须绑定到 `session_id`。
- 打开故事时只检测同一用户、同一 `story_id` 下未完成的会话。
- 同一个故事同一用户最多保留一个正在进行的未完成会话。
- 阅读完所有场景后，该会话视为完成；再次打开同一故事应创建新会话。

## 用户资产、上传和生成图片

当前用户资产元数据：SQLite。

表：

- `user_assets`
  - `id`
  - `user_id`
  - `name`
  - `url`
  - `kind`
  - `origin_story_id`
  - `origin_scene_idx`
  - `created_at`

图片/文件内容：

- 本地默认使用 `apps/api/storage/local.py`。
- 文件实际写入 `outputs/webdemo/<key>`。
- URL 形式为 `/outputs/<key>`。

可切换对象存储：

- `MINDSHOW_STORAGE=local`
- `MINDSHOW_STORAGE=s3`
- `MINDSHOW_STORAGE=oss`

生产建议：

- 上传图片、AI 生成图、TTS 音频、视频下载缓存都放 OSS/S3/R2。
- 数据库保存 URL、owner、来源故事/会话、创建时间等元数据。
- GitHub 不保存这些资产。

## 视频导入临时数据

视频链接导入涉及：

- `yt-dlp` 下载或读取媒体。
- `ffmpeg` 抽音频。
- DashScope ASR 转文字。
- Qwen 生成故事文本。
- 自定义故事构建输出到 `outputs/webdemo/stories/<story_id>/...`。

这些下载文件、音频缓存、生成图都属于运行时数据，不进入 Git。

## 分享与协作分发

当前已有：

- 官方图片资产：GitHub Release tar 包分发。
- 用户资产包：`asset_packs` 表保存分享码和资产 id 列表。

后续建议：

- 用户故事分享不要直接进入公共热门池，使用显式分享码或审核后的公共池。
- 分享数据应由服务器数据库 + OSS 维护。
- GitHub Release 只适合分发官方预置资产包，不适合分发真实用户数据。

## 本地开发清理建议

需要清空本机运行时数据时，可以删除：

- `outputs/webdemo/`
- `outputs/mindshow.db`

删除前确认不需要保留本机账号、故事、会话和生成图片。
