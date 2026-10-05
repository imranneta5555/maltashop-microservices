"""API tests that need no database: validation happens before any data is written."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)  # used without `with`, so the startup hook (database) is not run


def test_liveness():
    assert client.get("/health/live").json() == {"status": "ok"}


def test_invalid_order_is_rejected_with_422_and_correlation_id_echoed():
    response = client.post("/orders", json={"customer_id": "C-1001",
                                            "items": [{"sku": "NOT-A-PRODUCT", "quantity": 1}]},
                           headers={"X-Correlation-ID": "test-correlation-1"})
    assert response.status_code == 422
    assert response.headers["X-Correlation-ID"] == "test-correlation-1"


def test_correlation_id_is_created_when_the_caller_sends_none():
    response = client.post("/orders", json={"customer_id": "C-1001", "items": []})
    assert response.status_code == 422
    assert len(response.headers["X-Correlation-ID"]) == 36  # a UUID
