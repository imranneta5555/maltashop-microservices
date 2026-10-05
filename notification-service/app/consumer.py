"""Consumes OrderPlaced events from RabbitMQ in a background thread.

A message is acknowledged only after its notification is stored (manual ack), so if the
service crashes first, RabbitMQ delivers the message again. Messages that can never be
processed go to a dead-letter queue instead of being retried for ever.
"""
import json
import logging
import threading
import time

import pika
from pymongo.errors import PyMongoError

from . import config, store
from .handlers import MalformedEvent, build_notification
from .logging_setup import correlation_id, log_event

log = logging.getLogger("notification.consumer")
DEAD_LETTER_EXCHANGE = f"{config.EVENTS_EXCHANGE}.dlx"
DEAD_LETTER_QUEUE = f"{config.QUEUE_NAME}.dlq"


class OrderPlacedConsumer(threading.Thread):
    def __init__(self) -> None:
        super().__init__(name="order-placed-consumer", daemon=True)
        self.connected = False

    def run(self) -> None:
        while True:
            try:
                connection = pika.BlockingConnection(pika.URLParameters(config.RABBITMQ_URL))
                channel = connection.channel()
                self.declare_topology(channel)
                channel.basic_qos(prefetch_count=10)  # at most 10 unacknowledged messages at a time
                channel.basic_consume(queue=config.QUEUE_NAME, on_message_callback=self.on_message)
                self.connected = True
                log_event(log, logging.INFO, "consumer.started", f"Consuming from {config.QUEUE_NAME}")
                channel.start_consuming()
            except pika.exceptions.AMQPError as error:
                self.connected = False
                log_event(log, logging.WARNING, "consumer.reconnect",
                          f"Broker connection lost, retrying in 3 s: {error!r}")
                time.sleep(3)

    @staticmethod
    def declare_topology(channel) -> None:
        """The consumer owns its queue: durable, bound to order.placed, with a dead-letter queue."""
        channel.exchange_declare(config.EVENTS_EXCHANGE, exchange_type="topic", durable=True)
        channel.exchange_declare(DEAD_LETTER_EXCHANGE, exchange_type="fanout", durable=True)
        channel.queue_declare(DEAD_LETTER_QUEUE, durable=True)
        channel.queue_bind(DEAD_LETTER_QUEUE, DEAD_LETTER_EXCHANGE)
        channel.queue_declare(config.QUEUE_NAME, durable=True,
                              arguments={"x-dead-letter-exchange": DEAD_LETTER_EXCHANGE})
        channel.queue_bind(config.QUEUE_NAME, config.EVENTS_EXCHANGE, routing_key="order.placed")

    def on_message(self, channel, method, properties, body) -> None:
        token = correlation_id.set(properties.correlation_id)  # same ID the Order service logged
        try:
            event = json.loads(body)
            log_event(log, logging.INFO, "event.received", f"Received {event.get('event_type')}",
                      event_id=event.get("event_id"), order_id=event.get("data", {}).get("order_id"))
            notification = build_notification(event)
            if store.save(notification):
                log_event(log, logging.INFO, "notification.sent",
                          f"Order confirmation recorded for customer {notification['customer_id']}",
                          order_id=notification["order_id"], event_id=notification["event_id"])
            else:
                log_event(log, logging.INFO, "event.duplicate",
                          "Event already processed, ignored (idempotent consumer)",
                          event_id=notification["event_id"])
            channel.basic_ack(method.delivery_tag)
        except (ValueError, MalformedEvent) as bad:  # bad JSON or missing fields: never retry
            log_event(log, logging.ERROR, "event.rejected", f"Sent to dead-letter queue: {bad}")
            channel.basic_nack(method.delivery_tag, requeue=False)
        except PyMongoError as error:  # temporary: put it back and try again shortly
            log_event(log, logging.WARNING, "store.unavailable", f"Will be redelivered: {error!r}")
            time.sleep(2)
            channel.basic_nack(method.delivery_tag, requeue=True)
        finally:
            correlation_id.reset(token)
