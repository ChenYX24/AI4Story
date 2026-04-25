import base64
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..config import ARK_API_KEY, DASHSCOPE_API_KEY
from ..story_registry import create_custom_story_record, custom_story_workspace, update_custom_story_record
from .custom_story_service import schedule_custom_story_build
from .qwen_service import QwenError, call_asr_audio, call_json

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="video-import")
_FUTURES: dict[str, Future] = {}

MAX_DURATION_SECONDS = int(os.getenv("MINDSHOW_VIDEO_MAX_SECONDS", "600"))
MAX_AUDIO_BYTES = int(os.getenv("MINDSHOW_ASR_MAX_AUDIO_BYTES", str(9 * 1024 * 1024)))
YTDLP_SOCKET_TIMEOUT = int(os.getenv("MINDSHOW_YTDLP_SOCKET_TIMEOUT", "60"))
YTDLP_RETRIES = int(os.getenv("MINDSHOW_YTDLP_RETRIES", "5"))
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_BILIBILI_HEADERS = {
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "User-Agent": _BROWSER_UA,
}


def submit_video_story(url: str, title: str = "", owner_user_id: str | None = None) -> dict[str, Any]:
    clean_url = _validate_bilibili_url(url)
    if not ARK_API_KEY:
        raise RuntimeError("服务器未配置 ARK_API_KEY，暂时不能生成视频故事。")
    if not DASHSCOPE_API_KEY:
        raise RuntimeError("服务器未配置 DASHSCOPE_API_KEY，暂时不能识别视频音频。")

    record = create_custom_story_record(
        f"视频导入：{clean_url}",
        title=title or "视频导入故事",
        owner_user_id=owner_user_id,
    )
    story_id = record["id"]
    future = _EXECUTOR.submit(_build_from_video, story_id, clean_url, title.strip())
    _FUTURES[story_id] = future
    future.add_done_callback(lambda _: _FUTURES.pop(story_id, None))
    return record


def _build_from_video(story_id: str, url: str, requested_title: str) -> None:
    workspace = custom_story_workspace(story_id) / "video_import"
    if workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True, exist_ok=True)

    try:
        _set_progress(story_id, 3, "解析视频链接")
        metadata = _fetch_metadata(url)
        duration = int(float(metadata.get("duration") or 0))
        if duration > MAX_DURATION_SECONDS:
            raise RuntimeError(f"视频过长：当前 {duration} 秒，最多支持 {MAX_DURATION_SECONDS} 秒。")

        source_title = requested_title or str(metadata.get("title") or "视频导入故事").strip()
        update_custom_story_record(story_id, title=source_title, source_url=url, source_type="bilibili")

        _set_progress(story_id, 12, "读取视频字幕")
        transcript = _download_subtitles(url, workspace / "subtitles")
        if len(transcript) < 30:
            _set_progress(story_id, 20, "下载视频音频")
            source_audio = _download_audio(url, workspace / "audio")

            _set_progress(story_id, 30, "压缩音频")
            asr_audio = _prepare_audio_for_asr(source_audio, workspace / "asr.mp3")

            _set_progress(story_id, 40, "识别视频音频")
            transcript = _transcribe_audio(asr_audio)

        if len(transcript.strip()) < 20:
            raise RuntimeError("没有识别到足够的字幕或语音内容。")

        _set_progress(story_id, 50, "整理绘本故事")
        story_seed = _story_seed_from_transcript(transcript, source_title, metadata)
        story_text = story_seed["story_text"].strip()
        if len(story_text) < 80:
            story_text = transcript.strip()

        update_custom_story_record(
            story_id,
            title=(requested_title or story_seed.get("title") or source_title)[:32],
            summary=story_seed.get("summary") or story_text[:88],
            input_text=story_text,
            transcript=transcript[:20000],
            progress=55,
            progress_label="生成绘本资产",
        )
        schedule_custom_story_build(story_id, story_text)
    except Exception as exc:
        update_custom_story_record(
            story_id,
            status="failed",
            error_message=str(exc),
            progress=0,
            progress_label="",
        )


def _set_progress(story_id: str, progress: int, label: str) -> None:
    update_custom_story_record(story_id, progress=progress, progress_label=label)


def _validate_bilibili_url(url: str) -> str:
    value = (url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("请填写 http/https 开头的 B 站视频链接。")
    host = (parsed.hostname or "").lower()
    if not (host == "b23.tv" or host.endswith("bilibili.com")):
        raise ValueError("当前视频导入仅支持公开 B 站链接。")
    return value


def _fetch_metadata(url: str) -> dict[str, Any]:
    data = _run_yt_dlp(["--dump-single-json", "--no-playlist", url], timeout=60).stdout
    try:
        return json.loads(data)
    except Exception as exc:
        raise RuntimeError(f"视频信息解析失败：{exc}") from exc


def _download_subtitles(url: str, output_dir: Path) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        _run_yt_dlp(
            [
                "--skip-download",
                "--no-playlist",
                "--write-subs",
                "--write-auto-subs",
                "--sub-langs",
                "all",
                "--sub-format",
                "vtt/srt/json3/best",
                "-o",
                str(output_dir / "subtitle.%(ext)s"),
                url,
            ],
            timeout=120,
        )
    except RuntimeError:
        return ""

    files = sorted(
        [p for p in output_dir.iterdir() if p.is_file()],
        key=lambda p: (0 if any(x in p.name.lower() for x in ("zh", "cn", "hans")) else 1, p.name),
    )
    for path in files:
        text = _parse_subtitle_file(path)
        if len(text) >= 30:
            return text
    return ""


def _download_audio(url: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    _run_yt_dlp(
        [
            "--no-playlist",
            "-f",
            "bestaudio/best",
            "--ffmpeg-location",
            _ffmpeg_exe(),
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "6",
            "-o",
            str(output_dir / "source.%(ext)s"),
            url,
        ],
        timeout=240,
    )
    files = sorted(p for p in output_dir.iterdir() if p.is_file())
    if not files:
        raise RuntimeError("音频下载失败。")
    return files[0]


def _prepare_audio_for_asr(source: Path, target: Path) -> Path:
    ffmpeg = _ffmpeg_exe()
    _run_cmd(
        [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "24k",
            str(target),
        ],
        timeout=180,
    )
    if not target.exists():
        raise RuntimeError("音频转码失败。")
    if target.stat().st_size > MAX_AUDIO_BYTES:
        raise RuntimeError("音频仍然过大，请换一个更短的视频。")
    return target


def _ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError("服务器未安装 ffmpeg，且 imageio-ffmpeg 不可用，无法从视频音频中转写。") from exc


def _transcribe_audio(audio_path: Path) -> str:
    data = base64.b64encode(audio_path.read_bytes()).decode("ascii")
    data_url = f"data:audio/mpeg;base64,{data}"
    text = call_asr_audio(data_url, timeout=240)
    return _clean_text(text)


def _story_seed_from_transcript(transcript: str, title: str, metadata: dict[str, Any]) -> dict[str, str]:
    prompt = f"""
你是“漫秀 MindShow”的儿童绘本改编助手。
请把下面来自 B 站视频的字幕/语音转写，改编成适合 3-6 岁儿童互动绘本生成的故事种子稿。

要求：
- 保留视频里的主要人物、事件顺序、情绪变化和结局。
- 弱化成人化表达、广告口播、弹幕、无意义口头禅。
- 用温暖、清楚、适合绘本拆分的中文叙事。
- 故事文本 600-1200 字，适合后续拆成 5-8 幕。
- 只输出 JSON，不要 Markdown。

视频标题：{title}
视频简介：{str(metadata.get("description") or "")[:1000]}
转写内容：
{transcript[:12000]}

JSON 格式：
{{
  "title": "32 字以内标题",
  "summary": "80 字以内简介",
  "story_text": "完整故事种子稿"
}}
""".strip()
    try:
        data = call_json(prompt, temperature=0.25, timeout=120, retries=1)
    except QwenError:
        data = {}
    story_text = str(data.get("story_text") or "").strip()
    return {
        "title": str(data.get("title") or title or "视频导入故事").strip(),
        "summary": str(data.get("summary") or transcript[:88]).strip(),
        "story_text": story_text or f"根据视频《{title}》改编：\n{transcript}",
    }


def _parse_subtitle_file(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    suffix = path.suffix.lower()
    if suffix in {".json", ".json3"}:
        try:
            return _clean_text(_text_from_subtitle_json(json.loads(raw)))
        except Exception:
            return ""
    return _clean_text(_text_from_timed_subtitle(raw))


def _text_from_subtitle_json(data: Any) -> str:
    parts: list[str] = []
    if isinstance(data, dict):
        if isinstance(data.get("body"), list):
            for item in data["body"]:
                if isinstance(item, dict) and item.get("content"):
                    parts.append(str(item["content"]))
        if isinstance(data.get("events"), list):
            for event in data["events"]:
                for seg in event.get("segs") or []:
                    if isinstance(seg, dict) and seg.get("utf8"):
                        parts.append(str(seg["utf8"]))
    return "\n".join(parts)


def _text_from_timed_subtitle(raw: str) -> str:
    lines: list[str] = []
    for line in raw.splitlines():
        value = line.strip()
        if not value or value.upper().startswith("WEBVTT"):
            continue
        if "-->" in value or value.isdigit():
            continue
        value = re.sub(r"<[^>]+>", "", value)
        lines.append(value)
    return "\n".join(lines)


def _clean_text(text: str) -> str:
    parts: list[str] = []
    last = ""
    for line in (text or "").splitlines():
        value = re.sub(r"\s+", " ", line).strip()
        if not value or value == last:
            continue
        parts.append(value)
        last = value
    return "\n".join(parts).strip()


def _run_yt_dlp(args: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    common: list[str] = [
        "--socket-timeout",
        str(YTDLP_SOCKET_TIMEOUT),
        "--retries",
        str(YTDLP_RETRIES),
        "--fragment-retries",
        str(YTDLP_RETRIES),
        "--retry-sleep",
        "linear=2::2",
    ]
    for key, value in _BILIBILI_HEADERS.items():
        common.extend(["--add-header", f"{key}:{value}"])

    cookies_file = os.getenv("MINDSHOW_BILIBILI_COOKIES", "").strip()
    if cookies_file:
        common.extend(["--cookies", cookies_file])

    browser_cookies = os.getenv("MINDSHOW_BILIBILI_COOKIES_FROM_BROWSER", "").strip()
    if browser_cookies:
        common.extend(["--cookies-from-browser", browser_cookies])

    cookie_header = os.getenv("MINDSHOW_BILIBILI_COOKIE", "").strip()
    if cookie_header:
        common.extend(["--add-header", f"Cookie:{cookie_header}"])

    try:
        return _run_cmd([sys.executable, "-m", "yt_dlp", *common, *args], timeout=timeout)
    except RuntimeError as exc:
        detail = str(exc)
        if "HTTP Error 412" in detail and "BiliBili" in detail:
            raise RuntimeError(
                "B 站拒绝了视频元数据请求（HTTP 412）。请配置登录后的 B 站 Cookie："
                "推荐设置 MINDSHOW_BILIBILI_COOKIES=/path/to/cookies.txt，"
                "或 MINDSHOW_BILIBILI_COOKIES_FROM_BROWSER=chrome/safari/firefox，"
                "然后重启后端再试。"
            ) from exc
        raise


def _run_cmd(args: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        args,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(detail[-800:] or f"command failed: {args[0]}")
    return proc
