from typing import Any

import pytest

from scripts import serve


def test_migrates_and_seeds_before_serving(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []
    monkeypatch.setenv("PORT", "10000")
    serve.main(
        serve=lambda target, **kw: calls.append(("serve", target, kw["port"], kw["proxy_headers"])),
        steps=(lambda: calls.append("migrate"), lambda: calls.append("seed")),
    )
    assert calls == ["migrate", "seed", ("serve", "app.main:app", 10000, True)]
