"""Session auth helpers for dashboard-facing HTTP functions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    import azure.functions as func
except ModuleNotFoundError:
    func = None

try:
    import psycopg
except ModuleNotFoundError:
    psycopg = None


DEFAULT_SESSION_HOURS = 12


@dataclass(frozen=True)
class CustomerAccess:
    customer_id: str
    customer_name: str


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    email: str
    display_name: str
    is_admin: bool
    active_customer_id: str
    customers: list[CustomerAccess]
    expires_at: datetime


def _require_psycopg() -> None:
    if psycopg is None:
        raise RuntimeError("psycopg is required for Postgres access. Install functions/requirements.txt.")


def _connection_string() -> str:
    return os.environ["SQL_CONNECTION_STRING"]


def _session_hours() -> int:
    return int(os.getenv("AUTH_SESSION_HOURS", str(DEFAULT_SESSION_HOURS)))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _pbkdf2_hash(password: str, salt: str, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations, salt, digest = encoded_hash.split("$", 3)
    except ValueError as exc:
        raise ValueError("Stored password hash has an invalid format") from exc
    if algorithm != "pbkdf2_sha256":
        raise ValueError(f"Unsupported password hash algorithm: {algorithm}")
    expected = base64.b64decode(digest.encode("utf-8"))
    actual = _pbkdf2_hash(password, salt, int(iterations))
    return hmac.compare_digest(actual, expected)


def bearer_token(req: "func.HttpRequest") -> str:
    header = req.headers.get("Authorization", "").strip()
    if not header.lower().startswith("bearer "):
        raise PermissionError("Missing bearer token")
    token = header[7:].strip()
    if not token:
        raise PermissionError("Missing bearer token")
    return token


class AuthService:
    def __init__(self, connection_string: str, session_hours: int = DEFAULT_SESSION_HOURS) -> None:
        self.connection_string = connection_string
        self.session_hours = session_hours

    @classmethod
    def from_environment(cls) -> "AuthService":
        return cls(_connection_string(), _session_hours())

    def login(self, email: str, password: str) -> dict[str, Any]:
        _require_psycopg()
        normalized_email = email.strip().lower()
        if not normalized_email or not password:
            raise ValueError("email and password are required")

        with psycopg.connect(self.connection_string, autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT "UserId", "Email", "DisplayName", "PasswordHash", "IsAdmin", "DefaultCustomerId"
                    FROM "AppUsers"
                    WHERE LOWER("Email") = %s
                    """,
                    (normalized_email,),
                )
                row = cur.fetchone()
                if row is None or not verify_password(password, str(row[3])):
                    raise PermissionError("Invalid email or password")

                customers = self._load_customer_access(
                    cur,
                    str(row[0]),
                    is_admin=bool(row[4]),
                    default_customer_id=str(row[5]) if row[5] is not None else "",
                )
                default_customer_id = str(row[5]) if row[5] is not None else ""
                active_customer_id = self._pick_active_customer(default_customer_id, customers)
                token = secrets.token_urlsafe(32)
                expires_at = _utc_now() + timedelta(hours=self.session_hours)
                cur.execute(
                    """
                    INSERT INTO "UserSessions" ("SessionTokenHash", "UserId", "ActiveCustomerId", "ExpiresAt")
                    VALUES (%s, %s, %s, %s)
                    """,
                    (_hash_token(token), row[0], active_customer_id, expires_at),
                )
            conn.commit()

        context = self.session_from_token(token)
        return {"token": token, "session": serialize_context(context)}

    def session_from_token(self, token: str) -> AuthContext:
        _require_psycopg()
        with psycopg.connect(self.connection_string, autocommit=False) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        s."UserId",
                        s."ActiveCustomerId",
                        s."ExpiresAt",
                        u."Email",
                        u."DisplayName",
                        u."IsAdmin",
                        u."DefaultCustomerId"
                    FROM "UserSessions" s
                    JOIN "AppUsers" u ON u."UserId" = s."UserId"
                    WHERE s."SessionTokenHash" = %s
                    """,
                    (_hash_token(token),),
                )
                row = cur.fetchone()
                if row is None:
                    raise PermissionError("Session not found")
                expires_at = _ensure_aware(row[2])
                if expires_at <= _utc_now():
                    cur.execute('DELETE FROM "UserSessions" WHERE "SessionTokenHash" = %s', (_hash_token(token),))
                    conn.commit()
                    raise PermissionError("Session has expired")
                customers = self._load_customer_access(
                    cur,
                    str(row[0]),
                    is_admin=bool(row[5]),
                    default_customer_id=str(row[6]) if row[6] is not None else "",
                )
                if not any(customer.customer_id == str(row[1]) for customer in customers):
                    raise PermissionError("Session customer access is no longer valid")
                cur.execute(
                    'UPDATE "UserSessions" SET "LastSeenAt" = %s WHERE "SessionTokenHash" = %s',
                    (_utc_now(), _hash_token(token)),
                )
            conn.commit()

        return AuthContext(
            user_id=str(row[0]),
            email=str(row[3]),
            display_name=str(row[4]),
            is_admin=bool(row[5]),
            active_customer_id=str(row[1]),
            customers=customers,
            expires_at=expires_at,
        )

    def switch_customer(self, token: str, customer_id: str) -> AuthContext:
        _require_psycopg()
        desired_customer = customer_id.strip()
        if not desired_customer:
            raise ValueError("customerId is required")
        context = self.session_from_token(token)
        if not any(customer.customer_id == desired_customer for customer in context.customers):
            raise PermissionError("Not allowed to access this customer")
        with psycopg.connect(self.connection_string, autocommit=False) as conn:
            conn.execute(
                """
                UPDATE "UserSessions"
                SET "ActiveCustomerId" = %s, "LastSeenAt" = %s
                WHERE "SessionTokenHash" = %s
                """,
                (desired_customer, _utc_now(), _hash_token(token)),
            )
            conn.commit()
        return self.session_from_token(token)

    def logout(self, token: str) -> None:
        _require_psycopg()
        with psycopg.connect(self.connection_string, autocommit=True) as conn:
            conn.execute('DELETE FROM "UserSessions" WHERE "SessionTokenHash" = %s', (_hash_token(token),))

    def _load_customer_access(
        self,
        cur: "psycopg.Cursor[Any]",
        user_id: str,
        *,
        is_admin: bool = False,
        default_customer_id: str = "",
    ) -> list[CustomerAccess]:
        customers = self._fetch_customer_access(cur, user_id)
        if customers:
            return customers

        if is_admin:
            cur.execute(
                """
                INSERT INTO "UserCustomerAccess" ("UserId", "CustomerId")
                SELECT %s, c."CustomerId"
                FROM "Customers" c
                WHERE c."IsActive" = 1
                ON CONFLICT ("UserId", "CustomerId") DO NOTHING
                """,
                (user_id,),
            )
            return self._fetch_customer_access(cur, user_id)

        if default_customer_id:
            cur.execute(
                """
                INSERT INTO "UserCustomerAccess" ("UserId", "CustomerId")
                SELECT %s, c."CustomerId"
                FROM "Customers" c
                WHERE c."CustomerId" = %s AND c."IsActive" = 1
                ON CONFLICT ("UserId", "CustomerId") DO NOTHING
                """,
                (user_id, default_customer_id),
            )
            return self._fetch_customer_access(cur, user_id)

        return customers

    @staticmethod
    def _fetch_customer_access(cur: "psycopg.Cursor[Any]", user_id: str) -> list[CustomerAccess]:
        cur.execute(
            """
            SELECT c."CustomerId", c."CustomerName"
            FROM "UserCustomerAccess" uca
            JOIN "Customers" c ON c."CustomerId" = uca."CustomerId"
            WHERE uca."UserId" = %s AND c."IsActive" = 1
            ORDER BY c."CustomerId"
            """,
            (user_id,),
        )
        return [CustomerAccess(customer_id=str(row[0]), customer_name=str(row[1])) for row in cur.fetchall()]

    @staticmethod
    def _pick_active_customer(default_customer_id: str, customers: list[CustomerAccess]) -> str:
        if not customers:
            raise PermissionError("This user does not have access to any customers")
        if default_customer_id and any(customer.customer_id == default_customer_id for customer in customers):
            return default_customer_id
        return customers[0].customer_id


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def serialize_context(context: AuthContext) -> dict[str, Any]:
    return {
        "userId": context.user_id,
        "email": context.email,
        "displayName": context.display_name,
        "isAdmin": context.is_admin,
        "activeCustomerId": context.active_customer_id,
        "expiresAt": context.expires_at.isoformat(),
        "customers": [
            {"customerId": customer.customer_id, "customerName": customer.customer_name}
            for customer in context.customers
        ],
    }


def require_session(req: "func.HttpRequest") -> AuthContext:
    service = AuthService.from_environment()
    return service.session_from_token(bearer_token(req))
