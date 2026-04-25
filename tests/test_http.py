from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from functions import _http


class FakeHttpResponse:
    def __init__(self, body, status_code=200, mimetype=None):
        self.body = body
        self.status_code = status_code
        self.mimetype = mimetype

    def json(self):
        return json.loads(self.body)


class FakeRequest:
    def __init__(self, body=b"", *, json_payload=None, json_error=None, method="GET", route_params=None):
        self._body = body
        self._json_payload = json_payload
        self._json_error = json_error
        self.method = method
        self.route_params = route_params or {}
        self.headers = {}

    def get_body(self):
        return self._body

    def get_json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._json_payload


class HttpHelperTests(unittest.TestCase):
    def setUp(self):
        self.func_patcher = patch.object(_http, "func", SimpleNamespace(HttpResponse=FakeHttpResponse))
        self.func_patcher.start()

    def tearDown(self):
        self.func_patcher.stop()

    def test_authenticated_passes_context_to_handler(self):
        ctx = SimpleNamespace(active_customer_id="C010")

        with patch.object(_http, "require_session", return_value=ctx):
            @_http.authenticated
            def handler(req):
                auth_context = _http.current_session()
                return _http.json_response({"customerId": auth_context.active_customer_id})

            response = handler(FakeRequest())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"customerId": "C010"})

    def test_authenticated_maps_permission_error_to_401(self):
        with patch.object(_http, "require_session", side_effect=PermissionError("Missing bearer token")):
            @_http.authenticated
            def handler(req):
                return _http.json_response({"ok": True})

            response = handler(FakeRequest())

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "Missing bearer token"})

    def test_authenticated_maps_value_error_to_400(self):
        with patch.object(_http, "require_session", return_value=SimpleNamespace()):
            @_http.authenticated
            def handler(req):
                raise ValueError("bad payload")

            response = handler(FakeRequest())

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "bad payload"})

    def test_authenticated_logs_unexpected_errors_and_returns_500(self):
        with patch.object(_http, "require_session", return_value=SimpleNamespace()):
            @_http.authenticated
            def handler(req):
                raise RuntimeError("database exploded")

            with self.assertLogs(handler.__module__, level="ERROR"):
                response = handler(FakeRequest())

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"error": "Internal server error"})

    def test_parse_json_rejects_invalid_json(self):
        req = FakeRequest(b"{", json_error=ValueError("invalid"))

        with self.assertRaisesRegex(ValueError, "valid JSON"):
            _http.parse_json(req)

    def test_parse_json_rejects_non_object_json(self):
        req = FakeRequest(b"[]", json_payload=[])

        with self.assertRaisesRegex(ValueError, "JSON object"):
            _http.parse_json(req)

    def test_parse_json_rejects_missing_required_fields(self):
        req = FakeRequest(b"{}", json_payload={})

        with self.assertRaisesRegex(ValueError, "missing required field"):
            _http.parse_json(req, required=("question",))

    def test_parse_json_allows_empty_body_when_requested(self):
        req = FakeRequest(b"")

        self.assertEqual(_http.parse_json(req, allow_empty=True), {})


if __name__ == "__main__":
    unittest.main()
