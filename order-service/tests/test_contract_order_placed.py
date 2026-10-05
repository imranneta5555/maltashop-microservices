"""Contract test, provider side: the event the Order service builds must satisfy the
OrderPlaced contract that the Notification service (the consumer) depends on."""
import json
import uuid
from decimal import Decimal
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from app.domain import OrderLine, order_placed_event, order_total, price_lines

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
SCHEMA = json.loads((CONTRACTS / "order-placed.v1.schema.json").read_text())


def test_order_placed_event_satisfies_the_consumer_contract():
    lines = [OrderLine(sku="TV-55-4K", quantity=1), OrderLine(sku="KETTLE-1.7L", quantity=2)]
    order = {"order_id": uuid.uuid4(), "customer_id": "C-1001", "status": "PENDING",
             "total_amount": order_total(lines), "currency": "EUR", "items": price_lines(lines)}

    event = json.loads(json.dumps(order_placed_event(order, correlation_id=str(uuid.uuid4()))))

    Draft202012Validator(SCHEMA, format_checker=FormatChecker()).validate(event)  # raises if broken
    assert event["data"]["total_amount"] == str(Decimal("628.98"))
