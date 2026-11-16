import pytest
from fastapi.testclient import TestClient

from app.main import app, reset_store


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    """Fresh catalog and no artificial delay for every test."""
    reset_store()
    monkeypatch.setenv("CHECKOUT_MIN_DELAY", "0")
    monkeypatch.setenv("CHECKOUT_MAX_DELAY", "0")


@pytest.fixture
def client():
    return TestClient(app)
