"""Bounded, read-only sources. No upload/delete/ACL methods exist here."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import unquote, urlparse

from .errors import EvidenceError


@dataclass(frozen=True)
class Limits:
    max_objects: int = 100
    max_object_bytes: int = 256_000
    max_total_bytes: int = 2_000_000
    max_pages: int = 10
    page_size: int = 100
    max_walk_entries: int = 2_000

    def __post_init__(self):
        for value in self.__dict__.values():
            if type(value) is not int or value <= 0:
                raise EvidenceError("invalid_limits")
        if self.page_size > 1000 or self.max_objects > 10_000 or self.max_total_bytes > 50_000_000:
            raise EvidenceError("limits_too_large")


@dataclass(frozen=True)
class ObjectMeta:
    key: str
    size: int
    revision: str
    etag: str | None = None


class Source(Protocol):
    namespace: str
    prefix: str

    def list_objects(self, limits: Limits) -> list[ObjectMeta]: ...
    def read_object(self, obj: ObjectMeta, limits: Limits) -> bytes: ...


def validate_key(key: str) -> str:
    if not isinstance(key, str) or not key or len(key) > 1024:
        raise EvidenceError("unsafe_object_key")
    for candidate in (key, unquote(key)):
        parts = candidate.split("/")
        if (candidate.startswith("/") or "\\" in candidate or ":" in candidate
                or any(ord(c) < 32 for c in candidate)
                or any(p in ("", ".", "..") for p in parts)):
            raise EvidenceError("unsafe_object_key")
    return key


def validate_prefix(prefix: str, *, required: bool = False) -> str:
    if not prefix:
        if required:
            raise EvidenceError("prefix_required")
        return ""
    if not prefix.endswith("/"):
        raise EvidenceError("prefix_must_end_with_slash")
    validate_key(prefix[:-1])
    return prefix


def check_objects(objects: list[ObjectMeta], prefix: str, limits: Limits) -> None:
    if len(objects) > limits.max_objects:
        raise EvidenceError("object_budget_exceeded")
    seen = set()
    total = 0
    for obj in objects:
        validate_key(obj.key)
        if not obj.key.startswith(prefix):
            raise EvidenceError("out_of_scope_object")
        if obj.key in seen:
            raise EvidenceError("duplicate_object")
        seen.add(obj.key)
        if type(obj.size) is not int or obj.size < 0 or obj.size > limits.max_object_bytes:
            raise EvidenceError("object_size_exceeded")
        total += obj.size
        if total > limits.max_total_bytes:
            raise EvidenceError("total_byte_budget_exceeded")


class LocalSource:
    """A scoped directory of UTF-8 .md/.txt documents. Symlinks are rejected."""

    def __init__(self, root: Path | str, prefix: str = "", namespace: str | None = None):
        original = Path(root).absolute()
        if original.is_symlink():
            raise EvidenceError("symlink_rejected")
        self.root = original.resolve()
        if not self.root.is_dir():
            raise EvidenceError("source_unavailable")
        self.prefix = validate_prefix(prefix)
        namespace = namespace or "local:" + hashlib.sha256(str(self.root).encode()).hexdigest()
        if not re.fullmatch(r"[A-Za-z0-9:_-]{1,120}", namespace):
            raise EvidenceError("invalid_namespace")
        self.namespace = namespace + (":" + prefix if prefix else "")

    def _path(self, key: str) -> Path:
        validate_key(key)
        if not key.startswith(self.prefix):
            raise EvidenceError("out_of_scope_object")
        path = self.root.joinpath(*PurePosixPath(key).parts)
        current = self.root
        for part in PurePosixPath(key).parts:
            current = current / part
            if current.is_symlink():
                raise EvidenceError("symlink_rejected")
        if not path.resolve().is_relative_to(self.root):
            raise EvidenceError("path_escape")
        return path

    @staticmethod
    def _read_file(path: Path, limit: int) -> bytes:
        # Refuse devices/FIFOs; O_NONBLOCK also closes a FIFO replacement race on POSIX.
        if not stat.S_ISREG(path.stat(follow_symlinks=False).st_mode):
            raise EvidenceError("non_regular_file_rejected")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise EvidenceError("non_regular_file_rejected")
            return handle.read(limit + 1)

    def list_objects(self, limits: Limits) -> list[ObjectMeta]:
        objects: list[ObjectMeta] = []
        visited = 0
        # Enumerate the configured prefix only, rather than the entire parent tree.
        scan_root = self.root if not self.prefix else self._path(self.prefix[:-1] + "/_scope").parent
        if not scan_root.is_dir():
            raise EvidenceError("source_unavailable")
        def walk_error(_error):
            raise EvidenceError("source_unavailable")
        try:
            for directory, directories, files in os.walk(scan_root, followlinks=False, onerror=walk_error):
                directories.sort()
                files.sort()
                visited += len(directories) + len(files)
                if visited > limits.max_walk_entries:
                    raise EvidenceError("listing_budget_exceeded")
                for name in directories + files:
                    if (Path(directory) / name).is_symlink():
                        raise EvidenceError("symlink_rejected")
                for name in files:
                    if Path(name).suffix.lower() not in (".txt", ".md"):
                        continue
                    key = (Path(directory) / name).relative_to(self.root).as_posix()
                    path = self._path(key)
                    size = path.stat().st_size
                    if size > limits.max_object_bytes:
                        raise EvidenceError("object_size_exceeded")
                    # Hash the bounded read; mtime alone can hide same-length edits.
                    data = self._read_file(path, limits.max_object_bytes)
                    if len(data) != size:
                        raise EvidenceError("object_changed_during_read")
                    objects.append(ObjectMeta(key, size, hashlib.sha256(data).hexdigest()))
                    check_objects(objects, self.prefix, limits)
        except OSError:
            raise EvidenceError("source_unavailable") from None
        return sorted(objects, key=lambda o: o.key)

    def read_object(self, obj: ObjectMeta, limits: Limits) -> bytes:
        path = self._path(obj.key)
        try:
            data = self._read_file(path, limits.max_object_bytes)
        except OSError:
            raise EvidenceError("source_unavailable") from None
        if len(data) > limits.max_object_bytes:
            raise EvidenceError("object_size_exceeded")
        if len(data) != obj.size or hashlib.sha256(data).hexdigest() != obj.revision:
            raise EvidenceError("object_changed_during_read")
        return data


@dataclass(frozen=True)
class B2Config:
    endpoint: str
    region: str
    bucket: str
    prefix: str

    def __post_init__(self):
        if not re.fullmatch(r"[a-z]{2}-[a-z]+-\d{3}", self.region):
            raise EvidenceError("invalid_b2_region")
        parsed = urlparse(self.endpoint)
        if (parsed.scheme != "https" or parsed.netloc != f"s3.{self.region}.backblazeb2.com"
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or parsed.username or parsed.password):
            raise EvidenceError("b2_endpoint_not_allowed")
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9-]{4,61}[a-zA-Z0-9]", self.bucket):
            raise EvidenceError("invalid_bucket")
        validate_prefix(self.prefix, required=True)


class B2Source:
    """Boto3 integration. A fake client may be injected for offline contract tests."""

    def __init__(self, config: B2Config, *, client=None):
        self.config = config
        self.prefix = config.prefix
        identity = f"{config.endpoint.rstrip('/')}|{config.bucket}|{config.prefix}"
        self.namespace = "b2:" + hashlib.sha256(identity.encode()).hexdigest()
        if client is not None:
            self.client = client
            return
        # Explicit environment keys prevent profile/instance-metadata credential discovery.
        key_id = os.environ.get("OBJECT_EVIDENCE_B2_KEY_ID")
        app_key = os.environ.get("OBJECT_EVIDENCE_B2_APPLICATION_KEY")
        if not key_id or not app_key:
            raise EvidenceError("b2_credentials_required")
        try:
            import boto3
            from botocore.config import Config
        except ImportError:
            raise EvidenceError("boto3_not_installed") from None
        self.client = boto3.client(
            "s3", endpoint_url=config.endpoint.rstrip("/"), region_name=config.region,
            aws_access_key_id=key_id, aws_secret_access_key=app_key,
            config=Config(signature_version="s3v4", connect_timeout=5, read_timeout=10,
                          retries={"total_max_attempts": 3, "mode": "standard"},
                          proxies={}, s3={"addressing_style": "path"}),
        )
        # Refuse cross-origin redirects/region rewrites before credentials are sent.
        allowed_host = urlparse(config.endpoint).netloc
        def validate_request(request, **_kwargs):
            parsed = urlparse(request.url)
            if parsed.scheme != "https" or parsed.netloc != allowed_host:
                raise EvidenceError("b2_redirect_not_allowed")
        self.client.meta.events.register("before-send.s3", validate_request)

    def list_objects(self, limits: Limits) -> list[ObjectMeta]:
        objects: list[ObjectMeta] = []
        token = None
        seen_tokens = set()
        for _ in range(limits.max_pages):
            args = {"Bucket": self.config.bucket, "Prefix": self.prefix, "MaxKeys": limits.page_size}
            if token:
                args["ContinuationToken"] = token
            try:
                page = self.client.list_objects_v2(**args)
            except Exception:
                raise EvidenceError("remote_listing_failed") from None
            if not isinstance(page, dict) or type(page.get("IsTruncated")) is not bool:
                raise EvidenceError("invalid_listing_response")
            contents = page.get("Contents", [])
            if not isinstance(contents, list) or len(contents) > limits.page_size:
                raise EvidenceError("invalid_listing_response")
            for item in contents:
                try:
                    key, size, etag = item["Key"], item["Size"], item["ETag"]
                    validate_key(key)
                    if not key.startswith(self.prefix):
                        raise EvidenceError("out_of_scope_object")
                    # Fail closed on unsupported files; use a dedicated text-doc prefix.
                    if PurePosixPath(key).suffix.lower() not in (".md", ".txt"):
                        raise EvidenceError("unsupported_object_type")
                    if not isinstance(etag, str) or not etag or len(etag) > 256:
                        raise EvidenceError("invalid_listing_response")
                    modified = item.get("LastModified")
                    stamp = modified.isoformat() if hasattr(modified, "isoformat") else str(modified or "")
                    revision = hashlib.sha256(f"{etag}|{size}|{stamp}".encode()).hexdigest()
                    objects.append(ObjectMeta(key, size, revision, etag))
                except (KeyError, TypeError, AttributeError):
                    raise EvidenceError("invalid_listing_response") from None
                check_objects(objects, self.prefix, limits)
            if not page["IsTruncated"]:
                return sorted(objects, key=lambda o: o.key)
            token = page.get("NextContinuationToken")
            if not isinstance(token, str) or not token or token in seen_tokens:
                raise EvidenceError("invalid_pagination")
            seen_tokens.add(token)
        raise EvidenceError("page_budget_exceeded")

    def read_object(self, obj: ObjectMeta, limits: Limits) -> bytes:
        check_objects([obj], self.prefix, limits)
        body = None
        try:
            result = self.client.get_object(Bucket=self.config.bucket, Key=obj.key, IfMatch=obj.etag)
            body = result["Body"]
            if result.get("ContentLength") != obj.size or result.get("ETag") != obj.etag:
                raise EvidenceError("object_changed_during_read")
            data = body.read(limits.max_object_bytes + 1)
            if len(data) > limits.max_object_bytes:
                raise EvidenceError("object_size_exceeded")
            if len(data) != obj.size:
                raise EvidenceError("object_changed_during_read")
            return data
        except EvidenceError:
            raise
        except Exception:
            raise EvidenceError("remote_read_failed") from None
        finally:
            if body is not None:
                try:
                    body.close()
                except Exception:
                    pass
