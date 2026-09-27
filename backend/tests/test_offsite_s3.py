"""Подпись SigV4 в offsite_s3.py — по эталонным примерам документации AWS.

Свой подписчик вместо boto3 (см. докстринг модуля) допустим только с этой
проверкой: неверная подпись выглядит как «403 SignatureDoesNotMatch» у
хранилища, то есть бэкап молча не уезжает вне сервера.
Примеры: AWS S3 API Reference, «Signature Calculations for the Authorization
Header: Transferring Payload in a Single Chunk (AWS Signature Version 4)».
"""
from datetime import datetime, timezone

from backend import offsite_s3 as s3

AK = "AKIAIOSFODNN7EXAMPLE"
SK = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
NOW = datetime(2013, 5, 24, tzinfo=timezone.utc)
EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _sig(h):
    return h["authorization"].rsplit("Signature=", 1)[1]


def test_get_object_example():
    h = s3.sign_v4("GET", "examplebucket.s3.amazonaws.com", "/test.txt", {}, {"Range": "bytes=0-9"},
                   EMPTY, AK, SK, "us-east-1", NOW)
    assert "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date" in h["authorization"]
    assert _sig(h) == "f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"


def test_list_objects_example():
    h = s3.sign_v4("GET", "examplebucket.s3.amazonaws.com", "/", {"max-keys": "2", "prefix": "J"}, {},
                   EMPTY, AK, SK, "us-east-1", NOW)
    assert _sig(h) == "34b48302e7b5fa45bde8084f4b7868a86f0a534bc59db6670ed5711ef69dc6f7"


def test_config_requires_all_five():
    env = {f"BACKUP_S3_{k}": "x" for k in ("ENDPOINT", "REGION", "BUCKET", "ACCESS_KEY_ID", "SECRET_ACCESS_KEY")}
    assert s3.config_from_env(env) is not None
    env["BACKUP_S3_BUCKET"] = " "
    assert s3.config_from_env(env) is None


def test_list_parses_pages(monkeypatch):
    pages = [
        b'<?xml version="1.0"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        b"<IsTruncated>true</IsTruncated><NextContinuationToken>t1</NextContinuationToken>"
        b"<Contents><Key>daily_1.age</Key><LastModified>2026-09-26T03:31:00.000Z</LastModified></Contents>"
        b"</ListBucketResult>",
        b'<?xml version="1.0"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        b"<IsTruncated>false</IsTruncated>"
        b"<Contents><Key>daily_2.age</Key><LastModified>2026-09-27T03:44:00.000Z</LastModified></Contents>"
        b"</ListBucketResult>",
    ]
    seen = []
    monkeypatch.setattr(s3, "_request", lambda cfg, m, key="", query=None, body=b"": (seen.append(query), pages.pop(0))[1])
    items = s3.list_objects({})
    assert [k for k, _ in items] == ["daily_1.age", "daily_2.age"]
    assert items[1][1] == datetime(2026, 9, 27, 3, 44, tzinfo=timezone.utc)
    assert seen[1]["continuation-token"] == "t1"
