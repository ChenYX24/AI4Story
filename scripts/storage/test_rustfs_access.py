from __future__ import annotations

import time
import uuid

from minio import Minio
from minio.error import S3Error


ENDPOINT = "110.40.183.254:9000"
BUCKET = "mindshow"
ACCESS_KEY = ""
SECRET_KEY = ""
SECURE = False
PREFIX = "debug/access-test"


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    secure = _as_bool(str(SECURE).lower(), default=False)
    client = Minio(
        ENDPOINT,
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        secure=secure,
    )

    scheme = "https" if secure else "http"
    key = f"{PREFIX.strip('/')}/{int(time.time())}-{uuid.uuid4().hex}.txt"
    body = f"rustfs access test at {int(time.time())}\n".encode("utf-8")

    print(f"[INFO] endpoint={scheme}://{ENDPOINT} bucket={BUCKET}")
    print(f"[INFO] test_key={key}")

    try:
        if not client.bucket_exists(BUCKET):
            print(f"[FAIL] bucket does not exist: {BUCKET}")
            return 2

        client.put_object(
            BUCKET,
            key,
            data=__import__("io").BytesIO(body),
            length=len(body),
            content_type="text/plain",
        )
        print("[OK] upload")

        obj = client.get_object(BUCKET, key)
        try:
            got = obj.read()
        finally:
            obj.close()
            obj.release_conn()

        if got != body:
            print("[FAIL] downloaded content mismatch")
            return 3
        print("[OK] download-verify")

        client.remove_object(BUCKET, key)
        print("[OK] delete")
        print("[PASS] RustFS credential is valid and upload path works")
        return 0

    except S3Error as e:
        print(f"[FAIL] S3Error code={e.code} message={e.message}")
        if e.code in {"InvalidAccessKeyId", "AccessDenied", "SignatureDoesNotMatch"}:
            print("[HINT] AccessKey/SecretKey 可能不正确，或该账号对 bucket 没有 put/get/delete 权限")
        return 4
    except Exception as e:
        print(f"[FAIL] Unexpected error: {e}")
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
