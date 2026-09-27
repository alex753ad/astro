"""offsite_s3.py — копия бэкапов вне сервера (S3-совместимое хранилище).

Только стандартная библиотека, намеренно. Файл работает в двух местах:
  * на ХОСТЕ из 07-backup-cron.sh — `python3 app/backend/offsite_s3.py put <файл>`;
    там нет ни boto3, ни aws-cli (в новых Ubuntu aws-cli из apt убран), а ставить
    их на хост ради одного PUT — лишняя зависимость вне контроля lock-файла;
  * в worker — самопроверка спрашивает список, когда лёг последний бэкап.

Ключи доступа обязаны уметь ровно две вещи: PutObject и ListBucket (политика
бакета, TASKS/CLAUDE.md «Копия вне сервера»). Ни читать, ни удалять копии с
сервера нельзя — иначе взломанный сервер уносит или стирает и их. Хранение
30 дней держит правило жизненного цикла бакета, а не этот код.

Настройка — переменные BACKUP_S3_* в /opt/astro/.env:
  BACKUP_S3_ENDPOINT          https://storage.yandexcloud.net
  BACKUP_S3_REGION            ru-central1
  BACKUP_S3_BUCKET            имя бакета
  BACKUP_S3_ACCESS_KEY_ID     статический ключ сервисного аккаунта
  BACKUP_S3_SECRET_ACCESS_KEY его секрет

Подпись — AWS Signature V4, path-style (`https://endpoint/bucket/key`).
Проверена эталонными примерами из документации AWS (test_offsite_s3.py).
"""
from __future__ import annotations

import hashlib
import hmac
import http.client
import os
import re
import sys
import urllib.parse
from datetime import datetime, timezone

PREFIX = "daily_"
_KEYS = ("ENDPOINT", "REGION", "BUCKET", "ACCESS_KEY_ID", "SECRET_ACCESS_KEY")


def config_from_env(env=os.environ) -> dict | None:
    """Все пять переменных заданы — конфиг; хоть одной нет — None (не настроено)."""
    cfg = {k.lower(): (env.get("BACKUP_S3_" + k) or "").strip() for k in _KEYS}
    return cfg if all(cfg.values()) else None


def _quote(s: str, safe: str = "-_.~") -> str:
    return urllib.parse.quote(s, safe=safe)


def sign_v4(method: str, host: str, path: str, query: dict, headers: dict, payload_hash: str,
            access_key: str, secret_key: str, region: str, now: datetime, service: str = "s3") -> dict:
    """Заголовки запроса с Authorization по SigV4. `headers` — без host/x-amz-*: их добавим сами."""
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day = amz_date[:8]
    all_headers = {k.lower(): str(v).strip() for k, v in headers.items()}
    all_headers.update({"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date})
    signed = sorted(all_headers)
    canonical = "\n".join([
        method,
        _quote(path, safe="/-_.~"),
        "&".join(f"{_quote(k)}={_quote(str(v))}" for k, v in sorted(query.items())),
        "".join(f"{k}:{all_headers[k]}\n" for k in signed),
        ";".join(signed),
        payload_hash,
    ])
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    k = ("AWS4" + secret_key).encode()
    for part in (day, region, service, "aws4_request"):
        k = hmac.new(k, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    out = dict(all_headers)
    out["authorization"] = (f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
                            f"SignedHeaders={';'.join(signed)}, Signature={signature}")
    return out


def _request(cfg: dict, method: str, key: str = "", query: dict | None = None, body: bytes = b"",
             timeout: float = 60.0) -> bytes:
    u = urllib.parse.urlsplit(cfg["endpoint"])
    # Только HTTPS и http.client, а не urlopen: urlopen открыл бы и file://
    # (bandit B310 в CI), а ключи и бэкапы в открытом виде не ходят.
    if u.scheme != "https":
        raise RuntimeError(f"BACKUP_S3_ENDPOINT должен быть https://, а не {u.scheme}://")
    path = "/" + cfg["bucket"] + ("/" + key if key else "")
    query = query or {}
    headers = sign_v4(method, u.netloc, path, query, {}, hashlib.sha256(body).hexdigest(),
                      cfg["access_key_id"], cfg["secret_access_key"], cfg["region"], datetime.now(timezone.utc))
    target = _quote(path, safe="/-_.~")
    if query:
        target += "?" + "&".join(f"{_quote(k)}={_quote(str(v))}" for k, v in sorted(query.items()))
    headers.pop("host")
    conn = http.client.HTTPSConnection(u.netloc, timeout=timeout)
    try:
        conn.request(method, target, body=body if method == "PUT" else None, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
    finally:
        conn.close()
    if resp.status >= 300:
        # Текст ошибки хранилища (AccessDenied, NoSuchBucket…) — без него
        # «HTTP 403» ничего не объясняет. Секретов в ответе нет.
        raise RuntimeError(f"HTTP {resp.status}: {data[:300].decode('utf-8', 'replace')}")
    return data


def put_object(cfg: dict, key: str, data: bytes) -> None:
    _request(cfg, "PUT", key, body=data)


def list_objects(cfg: dict, prefix: str = PREFIX) -> list[tuple[str, datetime]]:
    """[(ключ, время загрузки UTC)], все страницы."""
    out: list[tuple[str, datetime]] = []
    token = None
    for _ in range(50):
        q = {"list-type": "2", "prefix": prefix}
        if token:
            q["continuation-token"] = token
        # Четыре поля регулярками, без XML-парсера: ElementTree на ответе
        # сети bandit считает небезопасным (B314), а defusedxml — лишняя
        # зависимость на хосте. Имена бэкапов — daily_<дата>…age, без
        # спецсимволов XML; &amp; и прочее в ключах тут не встречается.
        text = _request(cfg, "GET", query=q).decode("utf-8", "replace")
        for block in re.findall(r"<Contents>(.*?)</Contents>", text, re.S):
            key = re.search(r"<Key>(.*?)</Key>", block, re.S).group(1)
            ts = re.search(r"<LastModified>(.*?)</LastModified>", block, re.S).group(1)
            out.append((key, datetime.fromisoformat(ts.replace("Z", "+00:00"))))
        m = re.search(r"<NextContinuationToken>(.*?)</NextContinuationToken>", text, re.S)
        token = m.group(1) if m else None
        truncated = re.search(r"<IsTruncated>\s*true\s*</IsTruncated>", text, re.I)
        if not truncated or not token:
            break
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in ("put", "ls"):
        print("использование: offsite_s3.py put <файл> | ls -", file=sys.stderr)
        return 2
    cfg = config_from_env()
    if cfg is None:
        print("BACKUP_S3_* заданы не все — копия вне сервера не настроена", file=sys.stderr)
        return 2
    if argv[1] == "put":
        path = argv[2]
        with open(path, "rb") as f:
            put_object(cfg, os.path.basename(path), f.read())
        # Убедиться, что объект действительно лёг: PUT мог ответить 200 прокси,
        # а не хранилищу. Для этого ключам и нужен ListBucket.
        names = {k for k, _ in list_objects(cfg, prefix=os.path.basename(path))}
        if os.path.basename(path) not in names:
            print("после загрузки объекта нет в списке хранилища", file=sys.stderr)
            return 1
        print(f"в хранилище: {cfg['bucket']}/{os.path.basename(path)}")
    else:
        for k, ts in sorted(list_objects(cfg)):
            print(f"{ts:%Y-%m-%d %H:%M} {k}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception as e:  # noqa: BLE001 — cron ждёт код возврата и строку причины
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
