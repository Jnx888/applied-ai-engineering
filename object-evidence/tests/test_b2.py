import io
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from object_evidence.engine import EvidenceIndex
from object_evidence.errors import EvidenceError
from object_evidence.sources import B2Config, B2Source, Limits, ObjectMeta


class FakeS3:
    def __init__(self, pages=None, data=b"Restore checksums are verified."):
        self.data = data
        self.pages = pages if pages is not None else [{"IsTruncated": False, "Contents": [self.item()]}]
        self.calls = []
        self.body = None

    def item(self, key="docs/restore.md"):
        return {"Key": key, "Size": len(self.data), "ETag": '"fixture-etag"', "LastModified": "2026-10-22T00:00:00Z"}

    def list_objects_v2(self, **kwargs):
        self.calls.append(("list", kwargs))
        return self.pages.pop(0)

    def get_object(self, **kwargs):
        self.calls.append(("get", kwargs))
        self.body = io.BytesIO(self.data)
        return {"Body": self.body, "ContentLength": len(self.data), "ETag": '"fixture-etag"'}


class B2Tests(unittest.TestCase):
    def setUp(self):
        self.config = B2Config("https://s3.us-west-004.backblazeb2.com", "us-west-004", "fictional-private-bucket", "docs/")

    def assert_code(self, code, callback):
        with self.assertRaises(EvidenceError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code)

    def test_list_get_read_only_contract_and_conditional_read(self):
        client = FakeS3()
        source = B2Source(self.config, client=client)
        objects = source.list_objects(Limits())
        self.assertEqual(source.read_object(objects[0], Limits()), client.data)
        self.assertEqual([call[0] for call in client.calls], ["list", "get"])
        self.assertEqual(client.calls[0][1]["Prefix"], "docs/")
        self.assertEqual(client.calls[1][1]["IfMatch"], '"fixture-etag"')
        self.assertTrue(client.body.closed)

    def test_paginated_listing_must_complete(self):
        client = FakeS3()
        client.pages = [{"IsTruncated": True, "NextContinuationToken": "page2", "Contents": [client.item()]},
                        {"IsTruncated": False, "Contents": [client.item("docs/second.md")]}]
        objects = B2Source(self.config, client=client).list_objects(Limits())
        self.assertEqual(len(objects), 2)
        self.assertEqual(client.calls[1][1]["ContinuationToken"], "page2")

    def test_page_budget_never_publishes_partial_snapshot(self):
        client = FakeS3([{"IsTruncated": True, "NextContinuationToken": "next", "Contents": []}])
        self.assert_code("page_budget_exceeded", lambda: B2Source(self.config, client=client).list_objects(Limits(max_pages=1)))

    def test_repeated_pagination_token_rejected(self):
        client = FakeS3([{"IsTruncated": True, "NextContinuationToken": "next"}] * 2)
        self.assert_code("invalid_pagination", lambda: B2Source(self.config, client=client).list_objects(Limits()))

    def test_missing_pagination_token_rejected(self):
        client = FakeS3([{"IsTruncated": True}])
        self.assert_code("invalid_pagination", lambda: B2Source(self.config, client=client).list_objects(Limits()))

    def test_missing_completion_flag_rejected(self):
        client = FakeS3([{"Contents": []}])
        self.assert_code("invalid_listing_response", lambda: B2Source(self.config, client=client).list_objects(Limits()))

    def test_out_of_prefix_and_unsafe_key_rejected(self):
        for key, code in [("other/secret.md", "out_of_scope_object"), ("docs/../secret.md", "unsafe_object_key")]:
            client = FakeS3()
            client.pages = [{"IsTruncated": False, "Contents": [client.item(key)]}]
            self.assert_code(code, lambda: B2Source(self.config, client=client).list_objects(Limits()))

    def test_duplicate_keys_rejected(self):
        client = FakeS3()
        client.pages = [{"IsTruncated": False, "Contents": [client.item(), client.item()]}]
        self.assert_code("duplicate_object", lambda: B2Source(self.config, client=client).list_objects(Limits()))

    def test_unsupported_object_types_fail_closed(self):
        client = FakeS3()
        client.pages = [{"IsTruncated": False, "Contents": [client.item("docs/archive.zip")]}]
        self.assert_code("unsupported_object_type", lambda: B2Source(self.config, client=client).list_objects(Limits()))

    def test_unavailable_network_has_sanitized_failure(self):
        client = FakeS3()
        with patch.object(client, "list_objects_v2", side_effect=OSError("SENSITIVE_PROVIDER_MESSAGE")):
            self.assert_code("remote_listing_failed", lambda: B2Source(self.config, client=client).list_objects(Limits()))

    def test_b2_read_failure_preserves_successful_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            client = FakeS3()
            index = EvidenceIndex(Path(temp) / "index")
            index.sync(B2Source(self.config, client=client))
            before = index.snapshot_path.read_bytes()
            changed = FakeS3(data=b"Updated object text")
            with patch.object(changed, "get_object", side_effect=TimeoutError("private detail")):
                self.assert_code("remote_read_failed", lambda: index.sync(B2Source(self.config, client=changed)))
            self.assertEqual(before, index.snapshot_path.read_bytes())

    def test_changed_etag_or_length_rejected_and_body_closed(self):
        client = FakeS3()
        source = B2Source(self.config, client=client)
        self.assert_code("object_changed_during_read", lambda: source.read_object(ObjectMeta("docs/x.md", len(client.data), "rev", '"old"'), Limits()))
        self.assertTrue(client.body.closed)

    def test_oversize_remote_manifest_rejected_before_get(self):
        client = FakeS3()
        self.assert_code("object_size_exceeded", lambda: B2Source(self.config, client=client).list_objects(Limits(max_object_bytes=1)))
        self.assertEqual([call[0] for call in client.calls], ["list"])

    def test_deceptive_stream_larger_than_manifest_rejected(self):
        client = FakeS3()
        source = B2Source(self.config, client=client)
        body = io.BytesIO(b"x" * 11)
        with patch.object(client, "get_object", return_value={"Body": body, "ContentLength": 5, "ETag": '"fixture-etag"'}):
            self.assert_code("object_size_exceeded", lambda: source.read_object(ObjectMeta("docs/x.md", 5, "rev", '"fixture-etag"'), Limits(max_object_bytes=10)))
        self.assertTrue(body.closed)

    def test_endpoint_allowlist_rejects_ssrf_and_credentials_in_url(self):
        endpoints = ["http://s3.us-west-004.backblazeb2.com", "https://localhost", "https://169.254.169.254", 
                     "https://s3.us-west-004.backblazeb2.com.evil.test", "https://user:password@s3.us-west-004.backblazeb2.com",
                     "https://s3.us-west-004.backblazeb2.com:443", "https://s3.us-west-004.backblazeb2.com/redirect", 
                     "https://s3.us-west-004.backblazeb2.com?redirect=evil"]
        for endpoint in endpoints:
            self.assert_code("b2_endpoint_not_allowed", lambda: B2Config(endpoint, "us-west-004", "fictional-private-bucket", "docs/"))

    def test_bucket_prefix_and_region_are_explicit(self):
        self.assert_code("prefix_required", lambda: B2Config(self.config.endpoint, self.config.region, self.config.bucket, ""))
        self.assert_code("prefix_must_end_with_slash", lambda: B2Config(self.config.endpoint, self.config.region, self.config.bucket, "docs"))
        self.assert_code("invalid_bucket", lambda: B2Config(self.config.endpoint, self.config.region, "../bad", "docs/"))
        self.assert_code("invalid_b2_region", lambda: B2Config(self.config.endpoint, "localhost", self.config.bucket, "docs/"))

    def test_no_credentials_no_ambient_profile_or_network(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assert_code("b2_credentials_required", lambda: B2Source(self.config))

    def test_missing_boto3_reports_honestly(self):
        with patch.dict(os.environ, {"OBJECT_EVIDENCE_B2_KEY_ID": "fake-id", "OBJECT_EVIDENCE_B2_APPLICATION_KEY": "fake-secret"}), patch.dict("sys.modules", {"boto3": None}):
            self.assert_code("boto3_not_installed", lambda: B2Source(self.config))

    def test_constructor_bounds_and_redirect_guard_without_sdk_network(self):
        captured = {}
        def register(event, handler):
            captured["event"] = event
            captured["handler"] = handler
        def fake_client(service, **kwargs):
            captured["service"] = service
            captured["kwargs"] = kwargs
            return types.SimpleNamespace(meta=types.SimpleNamespace(events=types.SimpleNamespace(register=register)))
        def config(**kwargs):
            captured["config"] = kwargs
            return kwargs
        modules = {"boto3": types.SimpleNamespace(client=fake_client), "botocore.config": types.SimpleNamespace(Config=config)}
        with patch.dict(os.environ, {"OBJECT_EVIDENCE_B2_KEY_ID": "fake-id", "OBJECT_EVIDENCE_B2_APPLICATION_KEY": "fake-secret"}), patch.dict("sys.modules", modules):
            B2Source(self.config)
        self.assertEqual(captured["service"], "s3")
        self.assertEqual(captured["config"]["connect_timeout"], 5)
        self.assertEqual(captured["config"]["read_timeout"], 10)
        self.assertEqual(captured["config"]["retries"]["total_max_attempts"], 3)
        self.assertEqual(captured["config"]["proxies"], {})
        self.assertEqual(captured["config"]["s3"]["addressing_style"], "path")
        self.assertEqual(captured["kwargs"]["aws_access_key_id"], "fake-id")
        self.assertEqual(captured["event"], "before-send.s3")
        captured["handler"](types.SimpleNamespace(url=self.config.endpoint + "/bucket/key"))
        for url in ("https://evil.test", "http://s3.us-west-004.backblazeb2.com/object", "https://169.254.169.254"):
            self.assert_code("b2_redirect_not_allowed", lambda: captured["handler"](types.SimpleNamespace(url=url)))


if __name__ == "__main__":
    unittest.main()
