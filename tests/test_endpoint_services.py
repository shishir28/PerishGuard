from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import functions.alert_activity as alert_activity
import functions.batch_detail as batch_detail
from functions import _http


class FakeHttpResponse:
    def __init__(self, body, status_code=200, mimetype=None):
        self.body = body
        self.status_code = status_code
        self.mimetype = mimetype

    def json(self):
        return json.loads(self.body)


class FakeRequest:
    method = "GET"
    headers = {}

    def __init__(self, route_params=None):
        self.route_params = route_params or {}


class EndpointServiceTests(unittest.TestCase):
    def setUp(self):
        self.func_patcher = patch.object(_http, "func", SimpleNamespace(HttpResponse=FakeHttpResponse))
        self.func_patcher.start()

    def tearDown(self):
        self.func_patcher.stop()

    def test_batch_detail_uses_shared_operations_service_factory(self):
        service = SimpleNamespace(batch_detail=lambda customer_id, batch_id: {
            "customerId": customer_id,
            "batchId": batch_id,
        })
        ctx = SimpleNamespace(active_customer_id="C010")

        with (
            patch.object(_http, "require_session", return_value=ctx),
            patch.object(batch_detail, "operations_service", return_value=service) as service_factory,
        ):
            response = batch_detail.main(FakeRequest({"batchId": "B-123"}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"customerId": "C010", "batchId": "B-123"})
        service_factory.assert_called_once_with()
        self.assertFalse(hasattr(batch_detail, "_SERVICE"))

    def test_alert_activity_uses_shared_operations_service_factory(self):
        service = SimpleNamespace(alert_activity=lambda customer_id: {
            "customerId": customer_id,
            "window": "7d",
        })
        ctx = SimpleNamespace(active_customer_id="C010")

        with (
            patch.object(_http, "require_session", return_value=ctx),
            patch.object(alert_activity, "operations_service", return_value=service) as service_factory,
        ):
            response = alert_activity.main(FakeRequest())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"customerId": "C010", "window": "7d"})
        service_factory.assert_called_once_with()
        self.assertFalse(hasattr(alert_activity, "_SERVICE"))


if __name__ == "__main__":
    unittest.main()
