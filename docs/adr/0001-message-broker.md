# ADR-001: Message broker: RabbitMQ (managed)

**Status:** accepted, October 2026

## Context

Order, Inventory, Payment, Notification and Recommendation must exchange events reliably. Even at ten
times normal traffic the volume is modest (assumption: under 200 events per second). The operations
staff have no event-streaming experience, and the broker must run on a laptop as well as in production.

## Decision

RabbitMQ with topic exchanges, durable queues, publisher confirms and dead-letter queues. In
production, managed RabbitMQ (Amazon MQ) in an EU region.

Criteria: operational effort, team skills, cost, delivery guarantees, replay and lock-in.

| Alternative | Why rejected |
|---|---|
| Apache Kafka (managed) | Better replay and throughput, but more concepts to learn (partitions, offsets) and a higher cost than MaltaShop's volume justifies |
| The vendor's ESB | Licence cost, a central team and business logic in the bus |
| Amazon SNS and SQS | Cheap and simple, but ties every service to one cloud provider and cannot run in Docker Compose for development |

## Consequences

- RabbitMQ is well known, runs identically in this prototype and in production, and its per-message
  acknowledgements fit the saga.
- Queues delete messages once consumed, so Recommendation keeps its own event history.
- Technical debt accepted: high-volume streaming or replay for many consumers would need RabbitMQ
  Streams or Kafka. Publishing sits in one small module per service (`order-service/app/outbox.py`)
  to contain that change.
