"""Unit tests: turning an OrderPlaced event into a notification."""
import pytest

from app.handlers import MalformedEvent, build_notification

EVENT = {
    "event_id": "6f1c9a52-0d5e-4d43-9a43-0c2b4f6a8e11",
    "event_type": "OrderPlaced",
    "event_version": 1,
    "correlation_id": "corr-123",
    "data": {"order_id": "1b7e2c3a-9a51-4a3e-8f0e-5d2f6c7b8a90", "customer_id": "C-1001",
             "status": "PENDING", "total_amount": "549.00", "currency": "EUR",
             "items": [{"sku": "TV-55-4K", "quantity": 1, "unit_price": "549.00"}]},
}


def test_notification_keeps_ids_for_tracing_and_deduplication():
    notification = build_notification(EVENT)
    assert notification["event_id"] == EVENT["event_id"]
    assert notification["order_id"] == EVENT["data"]["order_id"]
    assert notification["correlation_id"] == "corr-123"
    assert notification["template"] == "order-confirmation"


def test_unknown_extra_fields_are_ignored():
    event = {**EVENT, "data": {**EVENT["data"], "loyalty_points": 55}}
    assert build_notification(event)["customer_id"] == "C-1001"


def test_missing_field_is_reported_as_malformed():
    event = {**EVENT, "data": {k: v for k, v in EVENT["data"].items() if k != "order_id"}}
    with pytest.raises(MalformedEvent, match="order_id"):
        build_notification(event)


def test_other_event_types_are_rejected():
    with pytest.raises(MalformedEvent):
        build_notification({**EVENT, "event_type": "OrderCancelled"})
