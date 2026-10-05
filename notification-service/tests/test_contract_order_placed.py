"""Contract test, consumer side: the Notification service can handle any event that
matches the OrderPlaced contract, using the example published with the contract."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from app.handlers import build_notification

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
SCHEMA = json.loads((CONTRACTS / "order-placed.v1.schema.json").read_text())
EXAMPLE = json.loads((CONTRACTS / "examples" / "order-placed.v1.json").read_text())


def test_contract_example_is_valid():
    Draft202012Validator(SCHEMA, format_checker=FormatChecker()).validate(EXAMPLE)


def test_consumer_handles_the_contract_example():
    notification = build_notification(EXAMPLE)
    assert notification["order_id"] == EXAMPLE["data"]["order_id"]
    assert notification["correlation_id"] == EXAMPLE["correlation_id"]
