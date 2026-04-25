from __future__ import annotations

import unittest

from functions.auth_service import AuthService


class FakeCustomerCursor:
    def __init__(self, fetched_rows):
        self.fetched_rows = list(fetched_rows)
        self.executed = []

    def execute(self, query, params=()):
        self.executed.append((query, params))

    def fetchall(self):
        if self.fetched_rows:
            return self.fetched_rows.pop(0)
        return []


class AuthServiceCustomerAccessTests(unittest.TestCase):
    def test_admin_customer_access_repairs_missing_rows(self):
        cur = FakeCustomerCursor([
            [],
            [("C010", "Customer C010"), ("C011", "Customer C011")],
        ])

        customers = AuthService("postgres://example")._load_customer_access(cur, "admin", is_admin=True)

        self.assertEqual([customer.customer_id for customer in customers], ["C010", "C011"])
        self.assertTrue(any("INSERT INTO \"UserCustomerAccess\"" in query for query, _ in cur.executed))

    def test_default_customer_access_repairs_single_tenant_user(self):
        cur = FakeCustomerCursor([
            [],
            [("C010", "Customer C010")],
        ])

        customers = AuthService("postgres://example")._load_customer_access(
            cur,
            "ops-c010",
            default_customer_id="C010",
        )

        self.assertEqual([customer.customer_id for customer in customers], ["C010"])
        self.assertTrue(any(params == ("ops-c010", "C010") for _, params in cur.executed))


if __name__ == "__main__":
    unittest.main()
