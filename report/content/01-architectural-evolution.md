# 1. Architectural Evolution and Synthesis

## 1.1 Why the monolith cannot meet MaltaShop's scalability requirements

All of MaltaShop's problems come from one fact: Catalogue, Orders, Payments, Customers and Notifications are built, released, scaled and crash as a single unit. On Black Friday the only way to add checkout capacity was to run more copies of the whole application, and every copy still wrote to one MySQL database, so checkout requests queued behind browsing traffic. The March incident shows the same tight coupling at run time: a fault in a non-essential feature stopped the essential one. Table 1 maps each limitation to the case facts and to the microservices response (Lewis and Fowler, 2014; Newman, 2021).

Table: Table 1 — Limitations of the monolith and how microservices address them
| Limitation | Evidence in the case | Microservices response |
|---|---|---|
| Scaling is all or nothing | 8× traffic on Black Friday; checkout queued; site down for over two hours; one MySQL database on two VMs | Stateless Order, Payment and Inventory replicas scale out on their own; queues absorb bursts; catalogue reads come from a cache; each service has its own database |
| No fault isolation | A memory leak in e-mail notifications crashed checkout for 50 minutes | Notification runs in its own process and receives events; if it fails, orders still succeed and e-mails wait in the queue (proved in Section 6.3) |
| Code and data are entangled | A second payment provider took seven weeks | A Payment service with one adapter per provider behind one standardised contract, so a new provider never touches Order or Customer code |
| Slow, risky releases | Every three weeks, on Friday evening, by hand, 40 minutes offline | Each service is deployed separately by an automated pipeline, with no downtime |
| No visibility | Local log files; no dashboard or alerts; customers report incidents | Central logs, metrics, traces and alerts (Section 4.2) |

The common thread is loose coupling and autonomy: each capability becomes a service that deploys, stores its data and fails on its own, so MaltaShop can scale checkout without scaling e-mails, release Payment without retesting Catalogue, and lose Notification without losing sales.

## 1.2 Monolith, ESB-based SOA or microservices

Table 2 compares the three options.

Table: Table 2 — The three options compared for MaltaShop
| Criterion | Monolith (made modular) | Vendor's ESB-based SOA | Microservices |
|---|---|---|---|
| Scale checkout alone | No; the whole application scales | Partly; the ESB is a shared bottleneck | Yes |
| Fault isolation | Low | Medium; the ESB is a single point of failure | High, if calls are asynchronous or protected |
| Weekly releases | Possible with automation, but every release is the whole site | Limited; changes queue for the ESB team | Yes; each team releases its own service |
| Data | One shared MySQL database | Services often still share databases | Each service owns its data; others use its API or events |
| Where integration logic lives | In-process calls | In a central "smart" bus (Erl, 2005) | Smart endpoints, dumb pipes (Lewis and Fowler, 2014) |
| Governance and security | One team's rules, spread through the code | A strength: security and partner limits enforced centrally | The same policies at a thin API gateway, with no business logic in it |
| Cost and skills | Lowest running cost | Licence fees, proprietary skills, lock-in | Highest running cost: every service adds overhead and needs a platform team |

Organisational factors decide this choice as much as technical ones. Twelve developers is a small team, which usually favours a modular monolith (Fowler, 2015), but MaltaShop's parts need very different scaling, must fail separately and have clear boundaries; twelve also make three teams of four, and Conway's law (Conway, 1968) says the system will mirror that structure. Automation could let even the monolith release weekly, but every release would still risk the whole site. Against microservices: nobody has run Kubernetes, there are only two operations staff, and GDPR and card payments demand strong governance.

An ESB is built to integrate many existing systems, but MaltaShop has one application to split, and the bus would become the new monolith: routing and transformation logic owned by one vendor and one team, with licence costs and a single point of failure. Microservices keep SOA's standardised contracts and loose coupling (Erl, 2005) without the bus, and push autonomy further.

**Recommendation:** move to microservices gradually, not by a rewrite. Using the strangler fig pattern (Fowler, 2004), extract Notification first, build Recommendation and the partner API as new services, and only then move Order, Inventory and Payment; Catalogue and Customer stay in the monolith until the platform has proved itself. The target is about eight services, not hundreds, which answers the CFO's concern.

## 1.3 Distributed-systems principles and the new problems

Three principles shape the recommendation. **Partial failure:** some parts fail while others keep working (Rotem-Gal-Oz, 2006), so the checkout path is kept short and everything else is asynchronous; a failing Notification or Recommendation service cannot block an order. **An unreliable network:** calls time out and messages arrive twice, late or out of order, so every write carries an idempotency key and every consumer ignores events it has already processed (Section 6.1). **Eventual consistency:** without a shared database, Order, Inventory and Payment agree only after events have flowed (Vogels, 2009); MaltaShop accepts a few seconds of "order received, confirming payment".

The price is real: network latency between services, data spread over several databases with no cross-service joins, harder debugging, versioned contracts between teams, the risk of a "distributed monolith" that must still be released together, and a platform that two operations staff must learn. Sections 4 and 5 show how each is managed.
