"""Error envelope behaviour, using a throwaway app so no database is needed."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, model_validator
from pydantic_core import PydanticCustomError

from app.api.errors import register_exception_handlers
from app.core.errors import AppError, ErrorCode


class Window(BaseModel):
    close: int
    forced: int

    @model_validator(mode="after")
    def forced_after_close(self) -> "Window":
        if self.forced <= self.close:
            raise PydanticCustomError(
                "forced_close_not_after_close", "Forced close must be later than bid close"
            )
        return self


def _client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/window")
    def window(body: Window) -> dict[str, int]:
        return {"close": body.close}

    @app.get("/conflict")
    def conflict() -> None:
        raise AppError(ErrorCode.AUCTION_CLOSED, "Auction closed", details=[{"message": "late"}])

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("unexpected")

    return TestClient(app, raise_server_exceptions=False)


def test_field_validation_error_lists_fields() -> None:
    res = _client().post("/window", json={"close": "x"})
    assert res.status_code == 422
    body = res.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    fields = {d["field"] for d in body["error"]["details"]}
    assert fields == {"close", "forced"}


def test_custom_validator_error_surfaces_its_own_code() -> None:
    res = _client().post("/window", json={"close": 10, "forced": 10})
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "FORCED_CLOSE_NOT_AFTER_CLOSE"
    assert error["message"] == "Forced close must be later than bid close"


def test_app_error_uses_default_status_and_details() -> None:
    res = _client().get("/conflict")
    assert res.status_code == 409
    assert res.json()["error"] == {
        "code": "AUCTION_CLOSED",
        "message": "Auction closed",
        "details": [{"field": None, "message": "late"}],
    }


def test_unhandled_error_is_hidden_behind_500() -> None:
    res = _client().get("/boom")
    assert res.status_code == 500
    assert res.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "unexpected" not in res.text
