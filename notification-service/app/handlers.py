"""Turns an OrderPlaced event into a notification record (a pure function, easy to test).

It reads only the fields it needs and ignores the rest (a "tolerant reader"), so the
Order team can add fields to the event without breaking this service.
"""
from datetime import datetime, timezone


class MalformedEvent(ValueError):
    """The message can never be processed, so it goes to the dead-letter queue."""


def build_notification(event: dict) -> dict:
    try:
        if event["event_type"] != "OrderPlaced":
            raise MalformedEvent(f"unexpected event type {event['event_type']!r}")
        data = event["data"]
        return {
            "event_id": event["event_id"],
            "order_id": data["order_id"],
            "customer_id": data["customer_id"],
            "channel": "email",
            "template": "order-confirmation",
            "summary": (f"Order {data['order_id'][:8]} received: {len(data['items'])} item(s), "
                        f"{data['total_amount']} {data['currency']}"),
            "status": "SENT",  # the prototype records the e-mail instead of sending it
            "correlation_id": event["correlation_id"],
            "created_at": datetime.now(timezone.utc),
        }
    except (KeyError, TypeError) as missing:
        raise MalformedEvent(f"OrderPlaced event is missing {missing}") from missing
