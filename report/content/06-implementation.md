# 6. Implementation and Prototyping

The prototype implements the place-order flow: the **Order service** (FastAPI, PostgreSQL) exposes `POST /orders`, and the **Notification service** (FastAPI, MongoDB) consumes the `OrderPlaced` event through **RabbitMQ**. Each has a Dockerfile, one `docker compose up` starts everything, and the repository's README explains what it is, how to run it and its environment variables (Appendix A).

## 6.1 Keeping the place-order flow consistent

An order touches three databases (Order, Inventory and Payment), so one ACID transaction is impossible, and a two-phase commit would lock all three and fail whenever one is down. The flow is therefore a **saga** (Garcia-Molina and Salem, 1987; Richardson, 2018): a sequence of local transactions, each publishing an event that triggers the next, with a compensating action that undoes a step if a later one fails (Figure 5, Table 15).

I chose **choreography** rather than orchestration. With three participants and one main path, the events are easy to follow and no orchestrator service has to be built and run, while Order still records the state of every order. If the flow grows to include returns or split deliveries, an orchestrator would become easier to manage.

![Figure 5 — The place-order saga (choreography). Each service commits a local transaction and publishes an event; the red path shows the compensating actions taken when payment is declined. Only Order (steps 1–4) and Notification are built in the prototype.](diagrams/out/saga.png)

Table: Table 15 — Saga steps and compensating actions
| Step | Service | Local transaction | Compensating action |
|---|---|---|---|
| 1 | Order | Create order as PENDING and save OrderPlaced in the outbox | Mark the order CANCELLED |
| 2 | Inventory | Reserve stock for the order ID | Release the reservation |
| 3 | Payment | Authorise the payment with the provider | Void or refund the authorisation |
| 4 | Order | Mark the order CONFIRMED | None: the final step |

Three techniques make every step safe to repeat:

1. **Idempotent API.** `POST /orders` takes an `Idempotency-Key` header. The key is a unique column, so a retried request returns the original order and writes nothing (Listing 4; Figure 11).
2. **Transactional outbox.** The order and its event are saved in the same local transaction, so there is never an order without its event or an event without its order (Richardson, n.d.). A relay publishes the event and marks it sent only after RabbitMQ confirms it (Listing 5); a crash in between causes a duplicate, never a loss.
3. **Idempotent consumer.** The consumer acknowledges a message only after its work is saved, and a unique index on `event_id` makes a repeated event harmless (Listing 6).

The framework and broker do much of this work. PostgreSQL provides the transaction, the unique constraint and `ON CONFLICT DO NOTHING`; RabbitMQ provides durable queues, persistent messages, publisher confirms, manual acknowledgements and dead-letter queues (RabbitMQ, n.d.); and FastAPI's pydantic models reject an invalid order before anything is written.

Listing: Listing 4 — Idempotent order creation with the transactional outbox (order-service/app/db.py, annotated excerpt)
```python
# (1) one local PostgreSQL transaction for the order AND its event
with connect() as conn, conn.transaction():
    order = conn.execute(
        """INSERT INTO orders (order_id, idempotency_key, customer_id, status,
                               total_amount, currency, items, correlation_id)
           VALUES (gen_random_uuid(), %s, %s, 'PENDING', %s, %s, %s, %s)
           ON CONFLICT (idempotency_key) DO NOTHING
           RETURNING *""",
        (idempotency_key, request.customer_id, order_total(request.items),
         CURRENCY, Jsonb(price_lines(request.items)), correlation_id),
    ).fetchone()
    # (2) the key was used before: nothing was written, return the original
    if order is None:
        existing = conn.execute("SELECT * FROM orders WHERE idempotency_key = %s",
                                (idempotency_key,)).fetchone()
        return existing, False

    # (3) the OrderPlaced event goes into the outbox in the same transaction
    event = order_placed_event(order, correlation_id)
    conn.execute(
        "INSERT INTO outbox (event_id, event_type, routing_key, payload) "
        "VALUES (%s, %s, %s, %s)",
        (event["event_id"], event["event_type"], "order.placed", Jsonb(event)),
    )
    # (4) commit: both rows are saved, or neither is
    return order, True
```

Listing: Listing 5 — The outbox relay publishes with confirms (order-service/app/outbox.py, annotated excerpt; logging omitted)
```python
# (1) take unsent events and lock them, so two relays never send the same row
rows = conn.execute(
    """SELECT event_id, event_type, routing_key, payload FROM outbox
       WHERE published_at IS NULL ORDER BY created_at LIMIT 50
       FOR UPDATE SKIP LOCKED"""
).fetchall()
for row in rows:
    event = row["payload"]
    channel.basic_publish(
        exchange=config.EVENTS_EXCHANGE,
        routing_key=row["routing_key"],
        body=json.dumps(event).encode(),
        properties=pika.BasicProperties(
            content_type="application/json",
            # (2) persistent: the message survives a broker restart
            delivery_mode=pika.DeliveryMode.Persistent,
            message_id=str(row["event_id"]),
            # (3) the request's correlation ID travels with the event
            correlation_id=event["correlation_id"],
            type=row["event_type"],
        ),
        # (4) with confirm_delivery() on, this returns only once the broker
        #     has stored the message, and fails if no queue would receive it
        mandatory=True,
    )
    # (5) marked as sent only after the broker's confirmation
    conn.execute("UPDATE outbox SET published_at = now() WHERE event_id = %s",
                 (row["event_id"],))
```

Listing: Listing 6 — The idempotent consumer (notification-service/app/consumer.py, annotated excerpt; logging shortened)
```python
def on_message(self, channel, method, properties, body) -> None:
    # (1) log with the correlation ID that came with the event
    token = correlation_id.set(properties.correlation_id)
    try:
        event = json.loads(body)
        notification = build_notification(event)
        # (2) unique index on event_id: save() returns False for a repeat
        if store.save(notification):
            log_event(log, logging.INFO, "notification.sent", ...)
        else:
            log_event(log, logging.INFO, "event.duplicate", ...)
        # (3) acknowledge only after the notification is saved
        channel.basic_ack(method.delivery_tag)
    except (ValueError, MalformedEvent):
        # (4) a message that can never be processed goes to the dead-letter queue
        channel.basic_nack(method.delivery_tag, requeue=False)
    except PyMongoError:
        # (5) the store is down: put the message back and try again later
        time.sleep(2)
        channel.basic_nack(method.delivery_tag, requeue=True)
    finally:
        correlation_id.reset(token)
```

## 6.2 Dockerfile, Compose file and the path to production

Listing: Listing 7 — order-service/Dockerfile (the Notification service's is the same apart from its label)
@file order-service/Dockerfile

The key choices in Listing 7 are:

- **Base image.** `python:3.12-slim` is an official, regularly patched Debian image: small, yet compatible with the ready-built wheels of psycopg and pymongo (Alpine's musl library often forces slow source builds). In production the tag would be pinned to a digest.
- **Multi-stage build.** The first stage installs the dependencies into a virtual environment; the final image copies only that environment and the application code (Docker, n.d.). No pip cache, build files or tests reach production, so the image is smaller and has less to attack.
- **Non-root user.** The process runs as user 10001, so an attacker who compromised the service would not be root in the container.
- **Health checks.** `HEALTHCHECK` calls `/health/ready`; Compose starts each service only when its database and the broker are healthy (`condition: service_healthy`), and Kubernetes will use the same endpoints for its probes.
- **Configuration through environment variables.** Every setting has a development default in Compose and nothing environment-specific is baked into the image, which is what makes "build once, promote everywhere" possible.

Listing: Listing 8 — docker-compose.yml (excerpt, passwords shortened; the full file is in Appendix B.1)
```yaml
services:
  order-service:
    build: ./order-service
    # CI sets IMAGE_REGISTRY and IMAGE_TAG to run the image it has just built
    image: ${IMAGE_REGISTRY:-local}/maltashop-order-service:${IMAGE_TAG:-dev}
    environment:
      SERVICE_NAME: order-service
      DATABASE_URL: postgresql://order_service:<password>@order-db:5432/orders
      RABBITMQ_URL: amqp://maltashop:<password>@rabbitmq:5672/%2F
    ports: ["8001:8000"]
    depends_on:
      order-db: {condition: service_healthy}
      rabbitmq: {condition: service_healthy}
    networks: [order-net, events-net]   # its own database and the broker only
  order-db:
    image: postgres:16-alpine
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U order_service -d orders"]
    networks: [order-net]
networks:
  order-net:
  notification-net:
  events-net:
```

As Listing 8 shows, separate networks enforce database per service: the Order service cannot even reach the Notification service's database (Figure 6). One command starts all five containers, and Compose waits until each is healthy (Figure 7).

![Figure 6 — The prototype under Docker Compose. Each service shares a private network with its own database, and both share an events network with RabbitMQ; only the three ports shown are open to the host.](diagrams/out/prototype.png)

![Figure 7 — After `docker compose up -d --build --wait`, all five containers are running and healthy.](evidence/screenshots/00_compose_up.png){w=15.9}

Table 16 lists the cloud-native tools needed to take the prototype from a laptop to production, and what each adds.

Table: Table 16 — From laptop to production
| Tool | What it adds |
|---|---|
| Container registry (GitHub Container Registry or Amazon ECR) | Stores tested images by digest; scans them for known vulnerabilities |
| Kubernetes (Amazon EKS) | Replicas across zones, self-healing and autoscaling (Section 4.1) |
| Helm charts | One parameterised deployment template per service, replacing Compose |
| Argo CD (GitOps) | Applies what is in Git to the cluster, with an audit trail and easy rollback |
| Argo Rollouts | Canary releases with automatic analysis and rollback (Section 3.3) |
| Managed PostgreSQL, MongoDB and RabbitMQ | Backups, failover and patching without in-house database experts |
| AWS Secrets Manager with External Secrets | Replaces the development passwords in Compose with managed, rotated secrets |
| OpenTelemetry Collector and Grafana Cloud | Central logs, metrics, traces and alerts (Section 4.2) |
| Kong API gateway and Keycloak | Authentication, per-partner scopes and rate limits |
| Terraform | The cluster, databases and broker defined as reviewable code |

## 6.3 Evidence and reflection

Figures 8 to 14 come from one run of `evidence/capture.py` on a freshly started system.

![Figure 8 — An order placed through the Order service's API documentation page (Swagger UI): the request, sent with an Idempotency-Key, and the 201 Created response with the order as PENDING, the total priced by the service, and the generated X-Correlation-ID header.](evidence/screenshots/01_swagger_place_order.png){w=13.5}

![Figure 9 — The Notification service consumed the OrderPlaced event and stored a notification in its own MongoDB database, carrying the same order ID and correlation ID.](evidence/screenshots/02_notification_consumed.png){w=15.9}

![Figure 10 — Log output of both services filtered by one correlation ID: the request, the outbox publish, and the event received and processed by the Notification service.](evidence/screenshots/03_correlation_logs.png){w=15.9}

![Figure 11 — Retrying the same request with the same Idempotency-Key returns the original order (200 OK, Idempotent-Replayed), and there is still exactly one notification.](evidence/screenshots/04_idempotent_retry.png){w=15.9}

![Figure 12 — Resilience test: with the Notification service stopped, an order is still accepted (HTTP 201) and its event waits in the Notification service's queue.](evidence/screenshots/05a_notification_down.png){w=15.9}

![Figure 13 — The RabbitMQ management page during the test: one message ready in notification-service.order-placed, and the dead-letter queue empty.](evidence/screenshots/05b_rabbitmq_message_waiting.png){w=15.9}

![Figure 14 — After the Notification service restarts, the waiting event is consumed: the queue is empty and both orders have a notification.](evidence/screenshots/05c_notification_back.png){w=15.9}

**What the prototype proves.** Two services with separate databases and networks cooperate only through a REST call and an event, which is the core of the design. Figures 12 to 14 show that the March incident cannot recur in the same form: with Notification stopped, orders were still accepted, the event waited in RabbitMQ and was processed when Notification returned. Figure 11 shows that a retried checkout creates no duplicate order or e-mail, and Figure 10 shows one correlation ID following an order across both services, which is what makes the logging design in Section 4.2 work. The CI pipeline tests the exact images it built.

**Where it falls short.** It has two services, not eight: without Inventory and Payment, the saga's compensations are designed (Figure 5) but never executed. There is no gateway, authentication or tracing, only correlation IDs. The outbox is polled every second, so an event can wait up to a second before it is published (compare the order.placed and event.published times in Figure 10). Every container is a single instance, and the passwords are development defaults.

**What I would change before production.** Add Inventory and Payment with their compensations, and test the failure paths automatically; replace polling with PostgreSQL LISTEN/NOTIFY or change-data capture; run schema changes as versioned migrations; add OpenTelemetry tracing, the gateway and Keycloak; move secrets into a secrets manager; and run the load test at ten times normal traffic on Kubernetes before the first sale.
