"""The Order service's own PostgreSQL database. No other service connects to it."""
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from . import config
from .domain import CURRENCY, PlaceOrderRequest, order_placed_event, order_total, price_lines

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id        UUID PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    customer_id     TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('PENDING', 'CONFIRMED', 'CANCELLED')),
    total_amount    NUMERIC(10, 2) NOT NULL,
    currency        CHAR(3) NOT NULL,
    items           JSONB NOT NULL,
    correlation_id  TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS outbox (
    event_id      UUID PRIMARY KEY,
    event_type    TEXT NOT NULL,
    routing_key   TEXT NOT NULL,
    payload       JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS outbox_unpublished ON outbox (created_at) WHERE published_at IS NULL;
"""


def connect() -> psycopg.Connection:
    return psycopg.connect(config.DATABASE_URL, row_factory=dict_row, connect_timeout=5)


def create_schema() -> None:
    with connect() as conn:
        conn.execute(SCHEMA)


def ping() -> None:
    with connect() as conn:
        conn.execute("SELECT 1")


def place_order(request: PlaceOrderRequest, idempotency_key: str, correlation_id: str) -> tuple[dict, bool]:
    """Saves a PENDING order and its OrderPlaced event in ONE local transaction (transactional outbox).

    Returns (order, created). If the idempotency key was seen before, the original order is
    returned with created=False and nothing new is written, so a retried request is harmless.
    """
    with connect() as conn, conn.transaction():
        order = conn.execute(
            """INSERT INTO orders (order_id, idempotency_key, customer_id, status,
                                   total_amount, currency, items, correlation_id)
               VALUES (gen_random_uuid(), %s, %s, 'PENDING', %s, %s, %s, %s)
               ON CONFLICT (idempotency_key) DO NOTHING
               RETURNING *""",
            (idempotency_key, request.customer_id, order_total(request.items), CURRENCY,
             Jsonb(price_lines(request.items)), correlation_id),
        ).fetchone()
        if order is None:  # a retry of a request that was already handled
            existing = conn.execute("SELECT * FROM orders WHERE idempotency_key = %s",
                                    (idempotency_key,)).fetchone()
            return existing, False

        event = order_placed_event(order, correlation_id)
        conn.execute(
            "INSERT INTO outbox (event_id, event_type, routing_key, payload) VALUES (%s, %s, %s, %s)",
            (event["event_id"], event["event_type"], "order.placed", Jsonb(event)),
        )
        return order, True


def get_order(order_id: str) -> dict | None:
    with connect() as conn:
        return conn.execute("SELECT * FROM orders WHERE order_id = %s", (order_id,)).fetchone()
