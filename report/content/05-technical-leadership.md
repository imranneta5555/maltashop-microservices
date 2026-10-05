# 5. Technical Leadership and Collaboration

## 5.1 Board briefing

**To:** the CEO and CFO. **From:** the Lead Solutions Architect. **Subject:** replacing the MaltaShop platform.

**What I recommend.** Today the shop is one large program: when one part fails or gets busy, everything fails: two hours offline last Black Friday, 50 minutes in March because of the e-mail feature, and 40 minutes offline for every update. I recommend splitting it, step by step, into about eight smaller parts, such as checkout, payments and e-mails, that run and fail separately.

**What we gain.**

- Checkout keeps working at ten times normal traffic, because we can strengthen checkout alone.
- A fault in e-mails or recommendations no longer stops sales.
- Weekly updates with no downtime (updates alone now cost about 11 hours offline a year).
- AI recommendations, 30 partner connections and new payment providers take weeks, not months.

**What it costs (estimates).** About €2,500 a month more for rented cloud services and monitoring, and about €30,000 in the first year for training and an outside expert. We rent ready-made services and avoid the integration vendor's licence fees.

**The CFO's concern.** It is right: this approach is overkill for small companies that rewrite everything into hundreds of parts. We will not do that. We split off only the parts causing our problems, one at a time, while the current shop keeps running. After the first part (e-mails, about three months) the board reviews the results and can stop with little lost.

**Risks.** The team must learn new tools, so we pay for training and help. For a while we pay for old and new systems together. More parts mean more to watch, so monitoring comes first.

**Keeping the current system** costs less this year, but cannot meet next year's goals.

## 5.2 Organising the developers and operations staff

The twelve developers become three stream-aligned teams of four, each owning whole business capabilities, and the two operations staff become a small platform team (Skelton and Pais, 2019):

- **Checkout team:** Order, Payment and Inventory.
- **Storefront team:** Catalogue, Customer, and Recommendation, built with the data team.
- **Integrations team:** Partner API, Notification, gateway routes, and the remaining monolith until it is retired.
- **Platform team (two operations staff):** the cluster, pipeline templates, observability, and second-line on-call support.

**Service ownership.** Every service has exactly one owning team, recorded in a service catalogue and a CODEOWNERS file. That team builds it, runs it and is paged for it.

**Git workflow and code review.** Trunk-based development with pull requests; one approval from the owning team and a green pipeline before merging; a change to another team's service is reviewed by that team.

**API contracts.** REST APIs are described in OpenAPI and events in JSON Schema, stored with the code. A breaking change needs a new version and the old one is kept for at least one release cycle; contract tests enforce this (Section 3.2).

**Shared documentation.** Each repository has a README, runbooks and Architecture Decision Records, linked from the service catalogue.

**On-call and post-incident review.** Each team has a weekly business-hours rota for its services, with the platform team as second line, and one shared rota out of hours; alerts are routed by owner label and link to a runbook. Reviews are blameless, held within five working days, built on a timeline from logs and traces, and their actions are tracked to completion. Table 12 lists three operational complexities this way of working creates, and how each is managed.

Table: Table 12 — Operational complexities and how each is managed
| Complexity | Strategy |
|---|---|
| Debugging across team boundaries: one order passes through services owned by two or three teams | Mandatory correlation IDs and tracing (Section 4.2); one shared checkout dashboard; the team that owns the failing SLO leads the incident |
| Contract drift: one team changes an event or API and breaks another team's service | Consumer-driven contract tests in CI, a versioning policy, and contract changes reviewed by both teams |
| On-call load and knowledge silos: fourteen people now run eight services, more than two operations staff can carry | "You build it, you run it" rotas, a runbook for every alert, shared pipeline and deployment templates, and new on-call engineers paired with experienced ones |

## 5.3 Architecture Decision Records

The two ADRs follow Nygard's (2011) format.

**ADR-001: Message broker: RabbitMQ (managed). Status: accepted, October 2026.**

**Context.** Order, Inventory, Payment, Notification and Recommendation must exchange events reliably. Even at ten times normal traffic the volume is modest (assumption: under 200 events per second), the operations staff have no event-streaming experience, and the broker must run on a laptop as well as in production.

**Decision.** RabbitMQ with topic exchanges, durable queues, publisher confirms and dead-letter queues; in production, managed RabbitMQ (Amazon MQ) in an EU region. Criteria: operational effort, team skills, cost, delivery guarantees, replay and lock-in; Table 13 shows the alternatives rejected.

Table: Table 13 — ADR-001: alternatives rejected
| Alternative | Why rejected |
|---|---|
| Apache Kafka (managed) | Better replay and throughput, but more concepts to learn (partitions, offsets) and a higher cost than MaltaShop's volume justifies |
| The vendor's ESB | Licence cost, a central team and business logic in the bus (Section 1.2) |
| Amazon SNS and SQS | Cheap and simple, but ties every service to one cloud provider and cannot run in Docker Compose for development |

**Consequences.** RabbitMQ is well known, runs identically in the prototype and in production, and its per-message acknowledgements fit the saga. Queues delete messages once consumed, so Recommendation keeps its own event history. *Technical debt accepted:* high-volume streaming or replay for many consumers would need RabbitMQ Streams or Kafka; publishing sits in one small module per service to contain that change.

**ADR-002: Observability stack: OpenTelemetry with Grafana Cloud. Status: accepted, October 2026.**

**Context.** Logs are local files and customers report incidents. The team needs logs, metrics, traces and alerts in one place, on a limited budget, run by two operations staff, with personal data kept in the EU.

**Decision.** Instrument every service with OpenTelemetry and use Grafana Cloud (Loki, Prometheus, Tempo, Grafana Alerting) in an EU region. Criteria: cost at MaltaShop's volume, operational effort, vendor neutrality, all three signals in one tool, and EU data residency; Table 14 shows the alternatives rejected.

Table: Table 14 — ADR-002: alternatives rejected
| Alternative | Why rejected |
|---|---|
| Self-hosted Elastic (ELK) stack | Powerful search, but running Elasticsearch clusters needs time and skills the operations staff do not have |
| Datadog | Excellent, but per-host and per-gigabyte pricing grows fast and its agents increase lock-in |
| Cloud provider tools only (CloudWatch) | Cheaper, but weaker tracing and dashboards, and tied to one provider |

**Consequences.** There is nothing to operate, and OpenTelemetry lets the backend change without touching service code. The bill grows with log volume, so production logs exclude DEBUG, are kept 30 days, and only 10% of normal traces are stored (all error traces are kept). *Technical debt accepted:* dashboards and alerts are first built by hand and must later move into code (Terraform) to be reviewed and versioned like the services.

**Effect on the project.** Both decisions favour tools the team can run now over the most powerful option, which raises the chance of meeting the 12-month goals: MaltaShop's scarcest resource is operations time, not technology. The debt is deliberate and written down, so future teams know what was traded and when to revisit it, instead of discovering it during an incident.
