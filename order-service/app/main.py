"""Order service: the REST API for placing orders."""
import logging
import time
import uuid
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool

from . import db
from .domain import PlaceOrderRequest
from .logging_setup import correlation_id, log_event, setup_logging

setup_logging()
log = logging.getLogger("order.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(db.create_schema)
    log_event(log, logging.INFO, "service.started", "Order service started")
    yield


app = FastAPI(title="MaltaShop Order Service", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def correlation_and_access_log(request: Request, call_next):
    """Reuses the caller's X-Correlation-ID (or creates one) and logs every request as JSON."""
    token = correlation_id.set(request.headers.get("X-Correlation-ID") or str(uuid.uuid4()))
    started = time.perf_counter()
    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id.get()
        if not request.url.path.startswith("/health"):
            log_event(log, logging.INFO, "http.request",
                      f"{request.method} {request.url.path} -> {response.status_code}",
                      method=request.method, path=request.url.path, status=response.status_code,
                      duration_ms=round((time.perf_counter() - started) * 1000, 1))
        return response
    finally:
        correlation_id.reset(token)


def to_json(order: dict) -> dict:
    return {
        "order_id": str(order["order_id"]),
        "customer_id": order["customer_id"],
        "status": order["status"],
        "total_amount": str(order["total_amount"]),
        "currency": order["currency"],
        "items": order["items"],
        "created_at": order["created_at"].isoformat(),
    }


@app.post("/orders", status_code=201)
def place_order(body: PlaceOrderRequest, response: Response,
                idempotency_key: str | None = Header(default=None, max_length=100)) -> dict:
    """Places an order. Send an Idempotency-Key header so a retried request cannot create a duplicate."""
    key = idempotency_key or str(uuid.uuid4())
    order, created = db.place_order(body, key, correlation_id.get())
    if created:
        log_event(log, logging.INFO, "order.placed", "Order saved as PENDING; OrderPlaced queued in outbox",
                  order_id=str(order["order_id"]), customer_id=order["customer_id"],
                  total_amount=str(order["total_amount"]))
    else:
        response.status_code = 200
        response.headers["Idempotent-Replayed"] = "true"
        log_event(log, logging.INFO, "order.replayed",
                  "Idempotency-Key seen before: original order returned, nothing written",
                  order_id=str(order["order_id"]))
    return to_json(order)


@app.get("/orders/{order_id}")
def get_order(order_id: UUID) -> dict:
    order = db.get_order(str(order_id))
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return to_json(order)


@app.get("/health/live")
def live() -> dict:
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> dict:
    # Ready means "can take orders": that needs the database. A broker outage does not
    # make the service unready, because new events wait safely in the outbox table.
    try:
        db.ping()
    except Exception as error:
        raise HTTPException(status_code=503, detail="database unavailable") from error
    return {"status": "ready"}
