"""Configuration, read only from environment variables (12-factor: config in the environment).

The defaults hold no credentials; docker-compose.yml (or a secrets store) supplies the real values.
"""
import os

SERVICE_NAME = os.getenv("SERVICE_NAME", "notification-service")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "notifications")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://localhost:5672/%2F")
EVENTS_EXCHANGE = os.getenv("EVENTS_EXCHANGE", "maltashop.events")
QUEUE_NAME = os.getenv("QUEUE_NAME", "notification-service.order-placed")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
