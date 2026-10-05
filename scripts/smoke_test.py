#!/usr/bin/env python3
"""End-to-end smoke test of the running system (used by CI after `docker compose up`).

Places an order, waits for the Notification service to record it, then repeats the request
with the same Idempotency-Key to prove no duplicate order or notification is created.
Needs only the Python standard library.
"""
import json
import os
import sys
import time
import urllib.request
import uuid

ORDER_URL = os.getenv("ORDER_URL", "http://localhost:8001")
NOTIFICATION_URL = os.getenv("NOTIFICATION_URL", "http://localhost:8002")


def call(method: str, url: str, body: dict | None = None, headers: dict | None = None):
    request = urllib.request.Request(url, method=method, headers={"Content-Type": "application/json",
                                                                  **(headers or {})},
                                     data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, dict(response.headers), json.loads(response.read())


def notifications_for(order_id: str) -> list[dict]:
    return call("GET", f"{NOTIFICATION_URL}/notifications?order_id={order_id}")[2]


def check(condition: bool, message: str) -> None:
    print(("PASS  " if condition else "FAIL  ") + message)
    if not condition:
        sys.exit(1)


def main() -> None:
    key, correlation = f"smoke-{uuid.uuid4()}", str(uuid.uuid4())
    order_request = {"customer_id": "C-1001", "items": [{"sku": "TV-55-4K", "quantity": 1},
                                                        {"sku": "KETTLE-1.7L", "quantity": 2}]}
    headers = {"Idempotency-Key": key, "X-Correlation-ID": correlation}

    status, response_headers, order = call("POST", f"{ORDER_URL}/orders", order_request, headers)
    check(status == 201 and order["status"] == "PENDING", f"order {order['order_id']} created as PENDING")
    check(order["total_amount"] == "628.98", "total priced by the service: 628.98 EUR")
    check(response_headers.get("x-correlation-id") == correlation, "correlation ID echoed in the response")

    deadline = time.time() + 20
    while not (found := notifications_for(order["order_id"])) and time.time() < deadline:
        time.sleep(0.5)
    check(len(found) == 1, "OrderPlaced consumed: one notification recorded")
    check(found[0]["correlation_id"] == correlation, "notification carries the same correlation ID")

    status, response_headers, replay = call("POST", f"{ORDER_URL}/orders", order_request, headers)
    check(status == 200 and replay["order_id"] == order["order_id"], "retry with same Idempotency-Key "
          "returns the original order")
    time.sleep(3)
    check(len(notifications_for(order["order_id"])) == 1, "still exactly one notification after the retry")

    status, _, fetched = call("GET", f"{ORDER_URL}/orders/{order['order_id']}")
    check(status == 200 and fetched["order_id"] == order["order_id"], "GET /orders/{id} returns the order")
    print("Smoke test passed.")


if __name__ == "__main__":
    main()
