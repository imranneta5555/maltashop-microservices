"""Notification service: consumes OrderPlaced events; a small REST API shows what was sent."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool

from . import store
from .consumer import OrderPlacedConsumer
from .logging_setup import log_event, setup_logging

setup_logging()
log = logging.getLogger("notification.api")
consumer = OrderPlacedConsumer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(store.create_indexes)
    consumer.start()
    log_event(log, logging.INFO, "service.started", "Notification service started")
    yield


app = FastAPI(title="MaltaShop Notification Service", version="0.1.0", lifespan=lifespan)


@app.get("/notifications")
def list_notifications(order_id: str | None = None) -> list[dict]:
    return store.find(order_id)


@app.get("/health/live")
def live() -> dict:
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> dict:
    try:
        store.ping()
    except Exception as error:
        raise HTTPException(status_code=503, detail="database unavailable") from error
    if not consumer.connected:
        raise HTTPException(status_code=503, detail="not connected to the message broker")
    return {"status": "ready"}
