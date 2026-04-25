from __future__ import annotations

import io
import time

import oss2
from minio import Minio


# ===== 1) 源 OSS 配置 =====
OSS_ENDPOINT = "https://oss-cn-shenzhen.aliyuncs.com"
OSS_BUCKET = "mindshow-pku"
OSS_ACCESS_KEY = ""
OSS_SECRET_KEY = ""
OSS_PREFIX = "mindshow/"  # 只迁这个前缀；整桶迁移可改成 ""

# ===== 2) 目标 RustFS(MinIO 兼容) 配置 =====
MINIO_ENDPOINT = "110.40.183.254:9000"
MINIO_BUCKET = "mindshow"
MINIO_ACCESS_KEY = ""
MINIO_SECRET_KEY = ""
MINIO_SECURE = False
MINIO_PREFIX = "mindshow/"  # 目标前缀

# ===== 3) 同步策略 =====
SKIP_EXISTING = True
RETRIES = 8
RETRY_BACKOFF_SECONDS = 2.0
LIMIT = 0  # 0 表示不限；调试可设 20


def norm_prefix(prefix: str) -> str:
    p = (prefix or "").strip("/")
    return f"{p}/" if p else ""


def map_key(src_key: str, src_prefix: str, dst_prefix: str) -> str:
    if src_prefix and src_key.startswith(src_prefix):
        tail = src_key[len(src_prefix) :]
    else:
        tail = src_key
    return f"{dst_prefix}{tail.lstrip('/')}" if dst_prefix else tail.lstrip("/")


def main() -> int:
    src_prefix = norm_prefix(OSS_PREFIX)
    dst_prefix = norm_prefix(MINIO_PREFIX)

    auth = oss2.Auth(OSS_ACCESS_KEY, OSS_SECRET_KEY)
    oss_bucket = oss2.Bucket(auth, OSS_ENDPOINT, OSS_BUCKET)

    minio = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )

    if not minio.bucket_exists(MINIO_BUCKET):
        minio.make_bucket(MINIO_BUCKET)
        print(f"[INFO] created bucket: {MINIO_BUCKET}")

    scanned = 0
    copied = 0
    skipped = 0
    failed = 0

    print(f"[SYNC] oss://{OSS_BUCKET}/{src_prefix or '/'} -> minio://{MINIO_BUCKET}/{dst_prefix or '/'}")

    for obj in oss2.ObjectIterator(oss_bucket, prefix=src_prefix):
        scanned += 1
        src_key = obj.key
        dst_key = map_key(src_key, src_prefix, dst_prefix)

        if SKIP_EXISTING:
            try:
                minio.stat_object(MINIO_BUCKET, dst_key)
                skipped += 1
                continue
            except Exception:
                pass

        ok = False
        last_error = None
        for attempt in range(1, RETRIES + 2):
            response = None
            try:
                response = oss_bucket.get_object(src_key)
                data = response.read()
                minio.put_object(
                    MINIO_BUCKET,
                    dst_key,
                    data=io.BytesIO(data),
                    length=len(data),
                    content_type=(getattr(obj, "content_type", None) or "application/octet-stream"),
                )
                copied += 1
                print(f"[OK] {src_key} -> {dst_key}")
                ok = True
                break
            except Exception as e:
                last_error = e
                if attempt <= RETRIES:
                    delay = RETRY_BACKOFF_SECONDS * attempt
                    print(f"[WARN] retry {attempt}/{RETRIES}: {src_key} ({e}), sleep {delay:.1f}s")
                    time.sleep(delay)
            finally:
                if response is not None:
                    try:
                        response.close()
                    except Exception:
                        pass

        if not ok:
            failed += 1
            print(f"[ERR] {src_key} -> {dst_key}: {last_error}")

        if scanned % 100 == 0:
            print(f"[PROGRESS] scanned={scanned} copied={copied} skipped={skipped} failed={failed}")

        if LIMIT > 0 and scanned >= LIMIT:
            print(f"[INFO] hit LIMIT={LIMIT}, stop")
            break

    print(f"[DONE] scanned={scanned} copied={copied} skipped={skipped} failed={failed}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
