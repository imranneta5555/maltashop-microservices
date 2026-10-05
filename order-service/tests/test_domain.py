"""Unit tests: order rules, with no database or broker."""
import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain import OrderLine, PlaceOrderRequest, order_placed_event, order_total, price_lines


def test_total_is_priced_from_the_price_list():
    lines = [OrderLine(sku="TV-55-4K", quantity=2), OrderLine(sku="KETTLE-1.7L", quantity=1)]
    assert order_total(lines) == Decimal("1137.99")


def test_unknown_sku_is_rejected():
    with pytest.raises(ValidationError, match="unknown sku"):
        OrderLine(sku="NOT-A-PRODUCT", quantity=1)


@pytest.mark.parametrize("quantity", [0, -1, 21])
def test_quantity_must_be_between_1_and_20(quantity):
    with pytest.raises(ValidationError):
        OrderLine(sku="TV-55-4K", quantity=quantity)


def test_order_needs_at_least_one_item():
    with pytest.raises(ValidationError):
        PlaceOrderRequest(customer_id="C-1001", items=[])


def test_event_carries_correlation_id_and_a_fresh_event_id():
    order = {"order_id": uuid.uuid4(), "customer_id": "C-1001", "status": "PENDING",
             "total_amount": Decimal("549.00"), "currency": "EUR",
             "items": price_lines([OrderLine(sku="TV-55-4K", quantity=1)])}
    first = order_placed_event(order, correlation_id="abc-123")
    second = order_placed_event(order, correlation_id="abc-123")
    assert first["correlation_id"] == "abc-123"
    assert first["data"]["order_id"] == str(order["order_id"])
    assert first["event_id"] != second["event_id"]


def test_event_does_not_carry_personal_data():
    order = {"order_id": uuid.uuid4(), "customer_id": "C-1001", "status": "PENDING",
             "total_amount": Decimal("39.99"), "currency": "EUR", "items": []}
    data = order_placed_event(order, correlation_id="abc-123")["data"]
    assert not {"email", "name", "address", "phone"} & set(data)
