"""Outbox relay: publishes the events that place_order() saved, then marks them as sent.

Runs as a background thread. A row is marked as published only after RabbitMQ has
confirmed the message, so a crash can cause a repeat but never a loss (at-least-once
delivery). Consumers therefore ignore an event_id they have already processed.
"""
import json
import logging
import threading

import pika

from . import config, db
from .logging_setup import correlation_id, log_event

log = logging.getLogger("order.outbox")


class OutboxRelay(threading.Thread):
    def __init__(self) -> None:
        super().__init__(name="outbox-relay", daemon=True)
        self._stopping = threading.Event()
        self._connection: pika.BlockingConnection | None = None
        self._channel = None

    def stop(self) -> None:
        self._stopping.set()

    def run(self) -> None:
        while not self._stopping.is_set():
            try:
                self.publish_pending()
            except Exception as error:  # broker or database down: events stay in the outbox
                log_event(log, logging.WARNING, "outbox.retry", f"Publish failed, will retry: {error!r}")
                self._disconnect()
            self._stopping.wait(config.OUTBOX_POLL_SECONDS)
        self._disconnect()

    def publish_pending(self) -> None:
        channel = self._get_channel()
        with db.connect() as conn, conn.transaction():
            rows = conn.execute(
                """SELECT event_id, event_type, routing_key, payload FROM outbox
                   WHERE published_at IS NULL ORDER BY created_at LIMIT 50
                   FOR UPDATE SKIP LOCKED"""
            ).fetchall()
            for row in rows:
                event = row["payload"]
                token = correlation_id.set(event["correlation_id"])
                try:
                    channel.basic_publish(
                        exchange=config.EVENTS_EXCHANGE,
                        routing_key=row["routing_key"],
                        body=json.dumps(event).encode(),
                        properties=pika.BasicProperties(
                            content_type="application/json",
                            delivery_mode=pika.DeliveryMode.Persistent,  # survives a broker restart
                            message_id=str(row["event_id"]),
                            correlation_id=event["correlation_id"],
                            type=row["event_type"],
                        ),
                        mandatory=True,  # fail if no queue is bound, rather than drop the event
                    )  # with publisher confirms on, this returns only once the broker has the message
                    conn.execute("UPDATE outbox SET published_at = now() WHERE event_id = %s",
                                 (row["event_id"],))
                    log_event(log, logging.INFO, "event.published",
                              f"Published {row['event_type']} to {config.EVENTS_EXCHANGE}",
                              event_id=str(row["event_id"]), order_id=event["data"]["order_id"],
                              routing_key=row["routing_key"])
                finally:
                    correlation_id.reset(token)
        self._connection.process_data_events(time_limit=0)  # keeps the AMQP heartbeat alive

    def _get_channel(self):
        if self._channel is None or self._channel.is_closed:
            self._connection = pika.BlockingConnection(pika.URLParameters(config.RABBITMQ_URL))
            self._channel = self._connection.channel()
            self._channel.exchange_declare(exchange=config.EVENTS_EXCHANGE, exchange_type="topic",
                                           durable=True)
            self._channel.confirm_delivery()
        return self._channel

    def _disconnect(self) -> None:
        try:
            if self._connection is not None and self._connection.is_open:
                self._connection.close()
        except Exception:
            pass
        self._connection = self._channel = None
