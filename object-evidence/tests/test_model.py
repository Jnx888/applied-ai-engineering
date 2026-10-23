import json
import unittest
from unittest.mock import MagicMock, patch

from object_evidence.errors import EvidenceError
from object_evidence.ollama_extractor import extract, validate_selection


class LocalModelTests(unittest.TestCase):
    def setUp(self):
        self.retrieval = {"query": "How do I restore?", "generation": "fixture-generation", "stale": False,
                          "matches": [{"citation_id": "oe_fixture", "text": "Verify the checksum before a restore.",
                                       "key": "restore.md", "sha256": "fixture-hash", "start_line": 1, "end_line": 1}]}
        self.selection = {"citation_id": "oe_fixture", "quote": "Verify the checksum before a restore."}

    def assert_code(self, code, callback):
        with self.assertRaises(EvidenceError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code)

    def test_verified_quote_only(self):
        self.assertTrue(validate_selection(self.selection, self.retrieval)["supported"])

    def test_fabricated_quote_rejected(self):
        self.assert_code("model_quote_not_in_source", lambda: validate_selection({**self.selection, "quote": "Run this unsafe fabricated command."}, self.retrieval))

    def test_unknown_citation_rejected(self):
        self.assert_code("model_citation_rejected", lambda: validate_selection({**self.selection, "citation_id": "forged"}, self.retrieval))

    def test_extra_fields_rejected(self):
        self.assert_code("model_output_schema_rejected", lambda: validate_selection({**self.selection, "action": "delete"}, self.retrieval))

    def test_empty_selection_abstains(self):
        self.assertTrue(validate_selection({"citation_id": "", "quote": ""}, self.retrieval)["abstained"])

    def test_no_results_never_calls_model(self):
        with patch("http.client.HTTPConnection", side_effect=AssertionError("unexpected model request")):
            self.assertEqual(extract({**self.retrieval, "matches": []})["model_calls"], 0)

    def test_stale_context_rejected(self):
        self.assert_code("stale_context_rejected", lambda: extract({**self.retrieval, "stale": True}))

    def test_explicit_cloud_model_name_rejected(self):
        self.assert_code("cloud_model_not_allowed", lambda: extract(self.retrieval, model="example:cloud"))

    def test_local_request_is_bounded_structured_and_closed(self):
        response = MagicMock()
        response.status = 200
        response.read.return_value = json.dumps({"done": True, "message": {"content": json.dumps(self.selection)}}).encode()
        connection = MagicMock()
        connection.getresponse.return_value = response
        with patch("http.client.HTTPConnection", return_value=connection) as factory:
            result = extract(self.retrieval)
        factory.assert_called_once_with("127.0.0.1", 11434, timeout=45)
        args, kwargs = connection.request.call_args
        self.assertEqual(args, ("POST", "/api/chat"))
        payload = json.loads(kwargs["body"])
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["options"]["num_predict"], 384)
        self.assertFalse(payload["format"]["additionalProperties"])
        self.assertEqual(result["model_calls"], 1)
        connection.close.assert_called_once()

    def test_redirect_never_followed(self):
        connection = MagicMock()
        connection.getresponse.return_value.status = 302
        with patch("http.client.HTTPConnection", return_value=connection):
            self.assert_code("local_model_unavailable", lambda: extract(self.retrieval))
        self.assertEqual(connection.request.call_count, 1)

    def test_timeout_sanitized(self):
        connection = MagicMock()
        connection.request.side_effect = TimeoutError("private detail")
        with patch("http.client.HTTPConnection", return_value=connection):
            self.assert_code("local_model_connection_failed", lambda: extract(self.retrieval))
        connection.close.assert_called_once()

    def test_oversize_and_invalid_model_json_rejected(self):
        for raw, expected in [(b"x" * 128001, "model_response_size_exceeded"), (b"not-json", "model_output_schema_rejected"),
                              (b"[]", "model_output_schema_rejected"), (b"null", "model_output_schema_rejected"),
                              (b'"string"', "model_output_schema_rejected")]:
            connection = MagicMock()
            connection.getresponse.return_value.status = 200
            connection.getresponse.return_value.read.return_value = raw
            with patch("http.client.HTTPConnection", return_value=connection):
                self.assert_code(expected, lambda: extract(self.retrieval))

    def test_quote_outside_supplied_context_is_rejected(self):
        retrieval = {**self.retrieval, "matches": [{**self.retrieval["matches"][0], "text": "x" * 6000 + self.selection["quote"]}]}
        connection = MagicMock()
        connection.getresponse.return_value.status = 200
        connection.getresponse.return_value.read.return_value = json.dumps({"done": True, "message": {"content": json.dumps(self.selection)}}).encode()
        with patch("http.client.HTTPConnection", return_value=connection):
            self.assert_code("model_quote_not_in_source", lambda: extract(retrieval))
