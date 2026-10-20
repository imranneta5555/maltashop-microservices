"""Configuration, read only from environment variables (12-factor: config in the environment).

The defaults hold no credentials; docker-compose.yml (or a secrets store) supplies the real values.
"""
import os

SERVICE_NAME = os.getenv("SERVICE_NAME", "order-service")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/orders")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://localhost:5672/%2F")
EVENTS_EXCHANGE = os.getenv("EVENTS_EXCHANGE", "maltashop.events")
OUTBOX_POLL_SECONDS = float(os.getenv("OUTBOX_POLL_SECONDS", "1.0"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
