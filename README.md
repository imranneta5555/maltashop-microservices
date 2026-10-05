# MaltaShop microservices prototype

Learn Key Institute, Undergraduate Diploma in Software Design (MQF Level 5).
Unit 5: Service-Oriented Architecture and Microservices Fundamentals.

## What the system is

A small, working prototype of the **"place an order"** flow for MaltaShop Ltd, the case study in the
assignment brief. It shows the core ideas of the proposed architecture on a laptop:

- **Two services, each owning its own data store.** The Order service keeps orders in PostgreSQL. The
  Notification service keeps notifications in MongoDB. Neither can reach the other's database
  (separate Docker networks).
- **One REST endpoint and one asynchronous event.** `POST /orders` saves the order, and an
  `OrderPlaced` event goes through **RabbitMQ** to the Notification service. Checkout never waits for
  the e-mail.
- **Reliability.** An idempotency key on the API, a transactional outbox, publisher confirms, manual
  acknowledgements, a dead-letter queue and a consumer that ignores repeats. Orders are not lost and
  are not duplicated.
- **Traceability.** JSON logs with a correlation ID that travels from the HTTP request, through the
  event, into the Notification service's logs.

```
 client ──POST /orders──▶ order-service ──▶ order-db (PostgreSQL)
                               │  (outbox relay)
                               ▼
                    RabbitMQ  exchange "maltashop.events"  ── routing key order.placed
                               │
                               ▼
                     notification-service ──▶ notification-db (MongoDB)
```

The full design, and the reasons behind it, are in the report (Sections 2 and 6).

## How to run it

Needs Docker with Docker Compose v2.

```bash
docker compose up --build        # add -d --wait to run in the background until all are healthy
```

Five containers start: `order-service` (port 8001), `notification-service` (port 8002), `order-db`,
`notification-db` and `rabbitmq` (management UI on http://localhost:15672, user `maltashop`,
password `maltashop_dev_password`).

Place an order:

```bash
curl -i -X POST http://localhost:8001/orders \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-0001" \
  -H "X-Correlation-ID: demo-corr-0001" \
  -d '{"customer_id": "C-1001", "items": [{"sku": "TV-55-4K", "quantity": 1}, {"sku": "KETTLE-1.7L", "quantity": 2}]}'
```

See that the Notification service consumed the event, and follow the correlation ID in both logs:

```bash
curl http://localhost:8002/notifications
docker compose logs order-service notification-service | grep demo-corr-0001
```

Sending the same request again, with the same `Idempotency-Key`, returns the original order with
`200 OK` and `Idempotent-Replayed: true`. No second order and no second notification are created.

Run the end-to-end smoke test (the same one CI runs): `python3 scripts/smoke_test.py`.

Stop and delete the data: `docker compose down -v`.

### Endpoints

| Service | Method and path | Purpose |
|---|---|---|
| order-service | `POST /orders` | Place an order. Headers: `Idempotency-Key` (recommended), `X-Correlation-ID` (optional) |
| order-service | `GET /orders/{order_id}` | Read one order |
| notification-service | `GET /notifications?order_id=` | Notifications recorded (to check that the event arrived) |
| both | `GET /health/live`, `GET /health/ready` | Liveness and readiness (used by the Docker health check) |

Interactive API docs: http://localhost:8001/docs and http://localhost:8002/docs.

Products in the stand-in price list: `TV-55-4K`, `LAPTOP-14-PRO`, `KETTLE-1.7L`, `FRIDGE-A-450`.

## Environment variables

All configuration comes from environment variables (12-factor). `docker-compose.yml` sets working
defaults. To change them, copy `.env.example` to `.env` and edit it.

| Variable | Used by | Default | Meaning |
|---|---|---|---|
| `SERVICE_NAME` | both | `order-service` / `notification-service` | Name written in every log line |
| `DATABASE_URL` | order | `postgresql://order_service:…@order-db:5432/orders` | Order service's PostgreSQL |
| `MONGO_URL` | notification | `mongodb://notification_service:…@notification-db:27017/?authSource=admin` | Notification service's MongoDB |
| `MONGO_DB` | notification | `notifications` | MongoDB database name |
| `RABBITMQ_URL` | both | `amqp://maltashop:…@rabbitmq:5672/%2F` | Message broker |
| `EVENTS_EXCHANGE` | both | `maltashop.events` | Topic exchange that events are published to |
| `QUEUE_NAME` | notification | `notification-service.order-placed` | The Notification service's own queue |
| `OUTBOX_POLL_SECONDS` | order | `1` | How often the outbox relay looks for unsent events |
| `LOG_LEVEL` | both | `INFO` | Python log level |
| `ORDER_DB_PASSWORD`, `NOTIFICATION_DB_PASSWORD`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD` | compose | dev values | Credentials (development only; use a secrets manager in production) |
| `IMAGE_REGISTRY`, `IMAGE_TAG` | compose | `local`, `dev` | Which images to run; CI sets them to the images it built |

## Tests and CI

```bash
cd order-service && pip install -r requirements.txt -r requirements-dev.txt && pytest -v
cd notification-service && pip install -r requirements.txt -r requirements-dev.txt && pytest -v
```

- **Unit tests:** the order rules (`order-service/tests/test_domain.py`) and event handling
  (`notification-service/tests/test_handlers.py`).
- **Contract tests:** `contracts/order-placed.v1.schema.json` is the `OrderPlaced` contract. The
  Order service (provider) checks that its events satisfy it. The Notification service (consumer)
  checks that it can handle the contract example.
- **End-to-end:** `scripts/smoke_test.py` runs against the running system.

`.github/workflows/ci.yml` runs on every push and pull request to `main`:

1. Lint, then unit and contract tests, for each service.
2. Build each image **once**, tag it with the commit SHA and push it to GitHub Container Registry.
3. Start the whole system from those exact images and run the smoke test.

## Project structure

| Path | What it holds |
|---|---|
| `order-service/` | FastAPI app (`app/`), tests, `Dockerfile` |
| `notification-service/` | FastAPI app with a RabbitMQ consumer (`app/`), tests, `Dockerfile` |
| `contracts/` | The `OrderPlaced` event contract (JSON Schema) and an example event |
| `scripts/smoke_test.py` | End-to-end test of the place-order flow |
| `docker-compose.yml`, `.env.example` | Runs the whole system |
| `.github/workflows/ci.yml` | The CI pipeline |

## Limits of the prototype

The prototype runs the Order and Notification services only. Payment and Inventory, the API gateway
and authentication, distributed tracing and Kubernetes manifests are designed in the report but not
built here. Credentials in `docker-compose.yml` are development defaults.

## Author

Imran Hossain Chowdhury, registration no. 11248.
