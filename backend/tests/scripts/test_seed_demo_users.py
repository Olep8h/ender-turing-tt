import pytest

from app import seed_demo_users
from app.core.config import settings


def test_seed_refuses_to_run_outside_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*_args: object) -> None:
        raise AssertionError("demo users were seeded outside development")

    monkeypatch.setattr(settings, "FASTAPI_ENV", None)
    monkeypatch.setattr(seed_demo_users, "seed_demo_users", fail_if_called)

    with pytest.raises(SystemExit):
        seed_demo_users.main()
