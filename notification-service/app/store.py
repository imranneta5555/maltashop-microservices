"""The Notification service's own MongoDB database. No other service connects to it."""
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError

from . import config

_client = MongoClient(config.MONGO_URL, serverSelectionTimeoutMS=3000, tz_aware=True)
_notifications = _client[config.MONGO_DB]["notifications"]


def create_indexes() -> None:
    # A unique event_id means a redelivered event cannot create a second notification.
    _notifications.create_index([("event_id", ASCENDING)], unique=True)
    _notifications.create_index([("order_id", ASCENDING)])


def save(notification: dict) -> bool:
    """Stores the notification. Returns False if this event was already processed."""
    try:
        _notifications.insert_one(notification)
        return True
    except DuplicateKeyError:
        return False


def find(order_id: str | None = None, limit: int = 50) -> list[dict]:
    query = {"order_id": order_id} if order_id else {}
    return list(_notifications.find(query, {"_id": 0}).sort("created_at", DESCENDING).limit(limit))


def ping() -> None:
    _client.admin.command("ping")
