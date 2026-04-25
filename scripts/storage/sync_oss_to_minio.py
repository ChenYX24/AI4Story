from __future__ import annotations

import argparse
import io
import os
import sys
import time
from dataclasses import dataclass


@dataclass
class OSSConfig:
    endpoint: str
    bucket: str
    access_key: str
    secret_key: str
    prefix: str


@dataclass
class MinIOConfig:
    endpoint: str
    bucket: str
    access_key: str
    secret_key: str
    secure: bool
    prefix: str
    create_bucket: bool


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        if default is None:
            raise RuntimeError(f"missing env: {name}")
        return default
    return value


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _norm_prefix(prefix: str) -> str:
    p = (prefix or "").strip("/")
    return f"{p}/" if p else ""


def _build_oss_config() -> OSSConfig:
    return OSSConfig(
        endpoint=_env("MINDSHOW_OSS_ENDPOINT"),
        bucket=_env("MINDSHOW_OSS_BUCKET"),
        access_key=_env("MINDSHOW_OSS_AK_ID"),
        secret_key=_env("MINDSHOW_OSS_AK_SECRET"),
        prefix=_norm_prefix(os.getenv("MINDSHOW_OSS_PREFIX", "")),
    )


def _build_minio_config() -> MinIOConfig:
    endpoint_raw = _env("MINDSHOW_MINIO_ENDPOINT")
    secure = _as_bool(os.getenv("MINDSHOW_MINIO_SECURE"), False)
    if endpoint_raw.startswith("https://"):
        endpoint_raw = endpoint_raw[len("https://") :]
        secure = True
    elif endpoint_raw.startswith("http://"):
        endpoint_raw = endpoint_raw[len("http://") :]
        secure = False

    return MinIOConfig(
        endpoint=endpoint_raw,
        bucket=_env("MINDSHOW_MINIO_BUCKET"),
        access_key=_env("MINDSHOW_MINIO_ACCESS_KEY"),
        secret_key=_env("MINDSHOW_MINIO_SECRET_KEY"),
        secure=secure,
        prefix=_norm_prefix(os.getenv("MINDSHOW_MINIO_PREFIX", os.getenv("MINDSHOW_OSS_PREFIX", ""))),
        create_bucket=_as_bool(os.getenv("MINDSHOW_MINIO_CREATE_BUCKET"), True),
    )


def _make_oss_bucket(cfg: OSSConfig):
    try:
        import oss2  # type: ignore
    except ImportError as e:
        raise RuntimeError("oss2 not installed. run: pip install oss2") from e

    auth = oss2.Auth(cfg.access_key, cfg.secret_key)
    return oss2.Bucket(auth, cfg.endpoint, cfg.bucket)


def _make_minio_client(cfg: MinIOConfig):
    try:
        from minio import Minio  # type: ignore
    except ImportError as e:
        raise RuntimeError("minio not installed. run: pip install minio") from e

    client = Minio(
        cfg.endpoint,
        access_key=cfg.access_key,
        secret_key=cfg.secret_key,
        secure=cfg.secure,
    )
    if cfg.create_bucket and not client.bucket_exists(cfg.bucket):
        client.make_bucket(cfg.bucket)
    return client


def _strip_prefix(key: str, prefix: str) -> str:
    if prefix and key.startswith(prefix):
        return key[len(prefix) :]
    return key


def _join_prefix(prefix: str, key: str) -> str:
    k = key.lstrip("/")
    return f"{prefix}{k}" if prefix else k


def _copy_with_retry(
    *,
    oss_bucket,
    minio_client,
    src_key: str,
    dst_bucket: str,
    dst_key: str,
    content_type: str,
    retries: int,
    retry_backoff: float,
) -> None:
    last_error: Exception | None = None
    attempts = max(1, retries + 1)
    for attempt in range(1, attempts + 1):
        response = None
        try:
            response = oss_bucket.get_object(src_key)
            data = response.read()
            minio_client.put_object(
                dst_bucket,
                dst_key,
                data=io.BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
            return
        except Exception as e:
            last_error = e
            if attempt < attempts:
                delay = retry_backoff * attempt
                print(f"[WARN] copy retry {attempt}/{attempts - 1}: {src_key} ({e}), sleep {delay:.1f}s")
                time.sleep(delay)
            continue
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass

    raise RuntimeError(f"copy failed after {attempts} attempts: {src_key}; last_error={last_error}")


def sync(
    dry_run: bool,
    skip_existing: bool,
    limit: int | None,
    retries: int,
    retry_backoff: float,
) -> int:
    oss_cfg = _build_oss_config()
    minio_cfg = _build_minio_config()

    oss_bucket = _make_oss_bucket(oss_cfg)
    minio_client = _make_minio_client(minio_cfg)

    scanned = 0
    copied = 0
    skipped = 0
    failed = 0

    print("[sync] source:")
    print(f"  OSS endpoint={oss_cfg.endpoint} bucket={oss_cfg.bucket} prefix={oss_cfg.prefix or '/'}")
    print("[sync] target:")
    scheme = "https" if minio_cfg.secure else "http"
    print(
        f"  MinIO endpoint={scheme}://{minio_cfg.endpoint} bucket={minio_cfg.bucket} prefix={minio_cfg.prefix or '/'}"
    )

    import oss2  # type: ignore

    for obj in oss2.ObjectIterator(oss_bucket, prefix=oss_cfg.prefix):
        scanned += 1
        src_key = obj.key
        rel_key = _strip_prefix(src_key, oss_cfg.prefix)
        dst_key = _join_prefix(minio_cfg.prefix, rel_key)

        if skip_existing:
            try:
                minio_client.stat_object(minio_cfg.bucket, dst_key)
                skipped += 1
                if scanned % 200 == 0:
                    print(f"[sync] scanned={scanned} copied={copied} skipped={skipped} failed={failed}")
                if limit and copied >= limit:
                    break
                continue
            except Exception:
                pass

        if dry_run:
            copied += 1
            if copied <= 20:
                print(f"[dry-run] {src_key} -> {dst_key}")
            if limit and copied >= limit:
                break
            continue

        try:
            _copy_with_retry(
                oss_bucket=oss_bucket,
                minio_client=minio_client,
                src_key=src_key,
                dst_bucket=minio_cfg.bucket,
                dst_key=dst_key,
                content_type=getattr(obj, "content_type", None) or "application/octet-stream",
                retries=retries,
                retry_backoff=retry_backoff,
            )
            copied += 1
        except Exception as e:
            failed += 1
            print(f"[ERR] {src_key} -> {dst_key}: {e}")

        if scanned % 100 == 0:
            print(f"[sync] scanned={scanned} copied={copied} skipped={skipped} failed={failed}")

        if limit and copied >= limit:
            break

    print("[done]")
    print(f"  scanned={scanned}")
    print(f"  copied={copied}")
    print(f"  skipped={skipped}")
    print(f"  failed={failed}")

    return 0 if failed == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync all objects from Aliyun OSS bucket to MinIO/RustFS")
    parser.add_argument("--dry-run", action="store_true", help="Only list objects to be copied")
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Re-copy objects even if target object exists",
    )
    parser.add_argument("--limit", type=int, default=None, help="Only copy first N objects")
    parser.add_argument("--retries", type=int, default=5, help="Retry times for each failed object copy")
    parser.add_argument("--retry-backoff", type=float, default=1.5, help="Backoff seconds multiplier")
    args = parser.parse_args()

    try:
        return sync(
            dry_run=args.dry_run,
            skip_existing=not args.no_skip_existing,
            limit=args.limit,
            retries=max(0, args.retries),
            retry_backoff=max(0.1, args.retry_backoff),
        )
    except Exception as e:
        print(f"[fatal] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
