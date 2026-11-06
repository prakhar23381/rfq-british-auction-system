from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import BuyerUser
from app.api.errors import register_exception_handlers
from app.core.clock import FrozenClock
from app.domain.enums import UserRole
from tests.factories import make_user


def test_list_users_buyers_first(client: TestClient, db: Session) -> None:
    make_user(db, UserRole.SUPPLIER, company="Zeta Freight")
    make_user(db, UserRole.BUYER, company="Acme Exports")
    db.commit()

    body = client.get("/api/users").json()
    assert [u["role"] for u in body["items"]] == ["BUYER", "SUPPLIER"]
    assert body["items"][0]["company_name"] == "Acme Exports"
    assert body["server_time"]


def test_me_returns_acting_user(client: TestClient, db: Session) -> None:
    user = make_user(db, UserRole.SUPPLIER)
    db.commit()

    res = client.get("/api/users/me", headers={"X-User-Id": str(user.id)})
    assert res.status_code == 200
    assert res.json()["user"]["id"] == str(user.id)


def test_me_requires_a_known_user(client: TestClient) -> None:
    cases = {
        "missing": {},
        "malformed": {"X-User-Id": "not-a-uuid"},
        "unknown": {"X-User-Id": "00000000-0000-0000-0000-000000000000"},
    }
    for name, headers in cases.items():
        res = client.get("/api/users/me", headers=headers)
        assert res.status_code == 401, name
        body = res.json()
        assert body["error"]["code"] == "UNAUTHENTICATED", name
        assert body["server_time"], name


def test_role_guard_rejects_wrong_role(db: Session) -> None:
    supplier = make_user(db, UserRole.SUPPLIER)
    buyer = make_user(db, UserRole.BUYER)
    db.commit()

    guarded = FastAPI()
    register_exception_handlers(guarded)

    @guarded.post("/buyer-only")
    def buyer_only(user: BuyerUser) -> dict[str, str]:
        return {"ok": user.company_name}

    test_client = TestClient(guarded)
    forbidden = test_client.post("/buyer-only", headers={"X-User-Id": str(supplier.id)})
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"
    allowed = test_client.post("/buyer-only", headers={"X-User-Id": str(buyer.id)})
    assert allowed.status_code == 200


def test_server_time_uses_injected_clock(client: TestClient, clock: FrozenClock) -> None:
    clock.set(datetime(2026, 11, 10, 17, 59, 30, tzinfo=UTC))
    body = client.get("/api/meta/time").json()
    assert body["server_time"].startswith("2026-11-10T17:59:30")


def test_unknown_route_and_method_use_error_envelope(client: TestClient) -> None:
    not_found = client.get("/api/nope")
    assert not_found.status_code == 404
    assert not_found.json()["error"]["code"] == "NOT_FOUND"

    not_allowed = client.delete("/api/users")
    assert not_allowed.status_code == 405
    assert not_allowed.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
