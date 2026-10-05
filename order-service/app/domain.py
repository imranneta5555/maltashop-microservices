"""Order rules that need no database: validation, pricing and the OrderPlaced event."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

# Stand-in for the Catalogue service. Prices come from here, never from the client.
PRICE_LIST = {
    "TV-55-4K": Decimal("549.00"),
    "LAPTOP-14-PRO": Decimal("1199.00"),
    "KETTLE-1.7L": Decimal("39.99"),
    "FRIDGE-A-450": Decimal("899.00"),
}
CURRENCY = "EUR"


class OrderLine(BaseModel):
    sku: str = Field(min_length=1, max_length=40, examples=["TV-55-4K"])
    quantity: int = Field(gt=0, le=20, examples=[1])

    @field_validator("sku")
    @classmethod
    def sku_must_exist(cls, sku: str) -> str:
        if sku not in PRICE_LIST:
            raise ValueError(f"unknown sku {sku!r}")
        return sku


class PlaceOrderRequest(BaseModel):
    customer_id: str = Field(min_length=1, max_length=40, examples=["C-1001"])
    items: list[OrderLine] = Field(min_length=1, max_length=50)


def price_lines(lines: list[OrderLine]) -> list[dict]:
    return [{"sku": line.sku, "quantity": line.quantity, "unit_price": str(PRICE_LIST[line.sku])}
            for line in lines]


def order_total(lines: list[OrderLine]) -> Decimal:
    total = sum((PRICE_LIST[line.sku] * line.quantity for line in lines), Decimal("0"))
    return total.quantize(Decimal("0.01"))


def order_placed_event(order: dict, correlation_id: str) -> dict:
    """Builds the OrderPlaced event; its shape is the contract in contracts/order-placed.v1.schema.json.

    Only the customer ID travels on the bus, never a name or e-mail address (GDPR data minimisation).
    """
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "OrderPlaced",
        "event_version": 1,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "source": "order-service",
        "correlation_id": correlation_id,
        "data": {
            "order_id": str(order["order_id"]),
            "customer_id": order["customer_id"],
            "status": order["status"],
            "total_amount": str(order["total_amount"]),
            "currency": order["currency"],
            "items": order["items"],
        },
    }
