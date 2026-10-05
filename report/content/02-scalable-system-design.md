# 2. Scalable System Design

## 2.1 Services, data and architecture

MaltaShop is decomposed by business capability (Newman, 2021): each service owns one area of the business and its data, so a change to that area touches one service and one team. Table 3 lists the eight services and Figure 1 shows how they fit together. PostgreSQL is the default store because the team already knows relational databases; MongoDB suits Notification's varied message documents, and Redis serves recommendations in milliseconds.

Table: Table 3 — MaltaShop services
| Service | Responsibility | Data owned | Data store |
|---|---|---|---|
| Catalogue | Products, prices, search; publishes ProductViewed | Products, categories, prices | PostgreSQL + Redis cache |
| Customer | Accounts, addresses, consent, GDPR requests | Customer profiles, consent records | PostgreSQL, personal data encrypted |
| Order | Places orders; owns order status; starts the saga | Orders, order lines, outbox | PostgreSQL |
| Inventory | Stock levels and reservations | Stock, reservations | PostgreSQL |
| Payment | Authorises and refunds through providers, one adapter each; never stores card numbers | Payment records, provider references | PostgreSQL |
| Notification | E-mail, SMS and push messages triggered by events | Messages sent, templates | MongoDB (messages vary in shape) |
| Partner | API for the 30 retailers and the courier: stock feeds, shipment updates | Partner accounts, feed history, shipments | PostgreSQL |
| Recommendation | "You may also like"; runs the data team's Python model | Features, event history | Redis (serving) + object storage (history) |

![Figure 1 — Container-level architecture of the target platform. Clients reach the services only through the API gateway, which checks tokens issued by the identity provider. Checkout-critical services are outlined in red; dashed arrows are events through RabbitMQ. Each service owns its data store; to save money, low-traffic services may share one managed PostgreSQL server with a separate database and credentials each, while Order and Payment have their own.](diagrams/out/architecture.png)

The AI Recommendation service sits beside checkout, not inside it. Browsing data (ProductViewed, from Catalogue) and order data (OrderPlaced) reach it as events on its own queue, so it receives a copy in near real time and can fall behind or fail without anyone waiting for it. The storefront asks it for suggestions through the gateway with a 200 ms timeout and shows best-sellers if it does not answer; checkout never calls it.

Authentication happens at the gateway. Customers log in through the identity provider (OpenID Connect) and send a short-lived token with each request. Each of the 30 retailers gets its own OAuth 2.0 client with scopes such as `stock:write` or `orders:read` and its own rate limit. Services check the scopes again, so one gateway mistake does not expose data.

## 2.2 Design patterns and service interactions

Table: Table 4 — Design patterns and why they were chosen
| Pattern | Where | How it keeps services decoupled and robust |
|---|---|---|
| API gateway | In front of all services | One entry point for web, app and partners; authentication, rate limits and routing in one place; services can be split or moved without clients noticing |
| Database per service | Every service | No shared schema, so teams change their own tables freely; removes the shared-MySQL bottleneck; enforced by credentials and network rules |
| Publish–subscribe | OrderPlaced, StockReserved, ProductViewed and others | Producers do not know their consumers; Recommendation is added without changing Order; a slow consumer does not slow the producer |
| Saga with transactional outbox | Place-order flow | Keeps Order, Inventory and Payment consistent without a distributed transaction (Section 6.1) |
| Circuit breaker with timeouts | Gateway to Recommendation; Payment to providers | Stops waiting on a failing dependency and returns a fallback, preventing cascading failure (Nygard, 2018) |
| Strangler fig | Migration | The gateway moves one route at a time from the monolith to a new service; rolling back means routing back |

The patterns in Table 4 come from Richardson (2018), but the case decides which ones matter: publish–subscribe answers the March incident and the AI requirement, database per service removes the MySQL bottleneck, and the strangler fig limits the risk of migration for a team new to microservices. Table 5 states whether each interaction is synchronous or asynchronous. The rule is simple: a call is synchronous only when the caller cannot answer its own user without the reply.

Table: Table 5 — Interaction matrix
| From → to | Interaction | Style | Why |
|---|---|---|---|
| Storefront → Catalogue | Browse products | Sync (REST) | The customer is waiting for the page; answers are cached |
| Storefront → Order | Place order | Sync (REST); replies PENDING | The customer needs an order number at once |
| Order → Inventory | OrderPlaced | Async | Reserving stock must not hold the customer's request open |
| Inventory → Payment | StockReserved | Async | Payment is taken only once stock is held |
| Payment → Order, Inventory | PaymentAuthorised / PaymentFailed | Async | The saga's outcome: confirmation or compensation |
| Payment → payment provider | Authorise, refund | Sync (HTTPS), timeout and circuit breaker | External API; the idempotency key is the order ID |
| Order, Payment → Notification | Order events | Async | An e-mail must never slow or break checkout |
| Catalogue, Order → Recommendation | ProductViewed, OrderPlaced | Async | Near-real-time data without coupling to checkout |
| Storefront → Recommendation | Get suggestions | Sync, 200 ms timeout, fallback | Best-sellers are shown if it is slow |
| Partner → Inventory | StockUpdated | Async | Retailer feeds arrive in bursts; the queue smooths them |
| Customer → all | CustomerErased | Async | A GDPR erasure reaches every service holding personal data |

## 2.3 Twelve-factor assessment

Table 6 assesses the design against seven of the twelve factors (Wiggins, 2017), with the evidence in the prototype.

Table: Table 6 — Twelve-factor assessment
| Factor | How the design satisfies it | Evidence in the prototype |
|---|---|---|
| III Config | All settings come from environment variables; secrets from a secrets manager in production | `config.py` reads only environment variables; `.env.example` |
| IV Backing services | Databases and the broker are attached resources addressed by URL, so a local container can become a managed service without code changes | `DATABASE_URL`, `MONGO_URL`, `RABBITMQ_URL` |
| V Build, release, run | One image per commit; a release is that image plus environment configuration | CI builds one image per commit and tests that same image |
| VI Processes | Services keep no state in memory; any replica can serve any request | The outbox is in PostgreSQL, not in memory |
| IX Disposability | Fast start, safe stop: unacknowledged messages are redelivered and unsent outbox rows are retried | Manual acknowledgements; the resilience test in Section 6.3 |
| X Dev/prod parity | The same images and the same database and broker engines everywhere | Compose runs PostgreSQL, MongoDB and RabbitMQ, as production will |
| XI Logs | Logs are an event stream to standard output, collected by the platform | JSON logs to stdout, read with `docker compose logs` |

Twelve-factor services are what cloud-native infrastructure expects. Kubernetes can start, stop and replace any replica because none holds state (VI, IX); the autoscaler can add replicas because configuration is external (III); and the platform, not the code, decides where logs go (XI). The main gap is admin processes (XII): the prototype creates its tables at start-up, and this must become a versioned migration job before production.
