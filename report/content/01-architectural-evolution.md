# 1. Architectural Evolution and Synthesis

## 1.1 Why the monolith cannot meet MaltaShop's scalability requirements

All of MaltaShop's problems come from one fact: Catalogue, Orders, Payments, Customers and Notifications are built, released, scaled and crash as a single unit. On Black Friday the only way to add checkout capacity was to run more copies of the whole application, and every copy still wrote to one MySQL database, so checkout requests queued behind browsing traffic. The March incident shows the same coupling at run time: a fault in a non-essential feature stopped the essential one. Table 1 maps each limitation to the case facts and to the microservices response (Lewis and Fowler, 2014; Newman, 2021).

Table: Table 1 — Limitations of the monolith and how microservices address them
| Limitation | Evidence in the case | Microservices response |
|---|---|---|
| Scaling is all or nothing | 8× traffic on Black Friday; checkout queued; site down for over two hours; one MySQL database on two VMs | Order, Payment and Inventory scale out on their own; catalogue reads come from a cache; each service has its own database, so browsing no longer competes with checkout |
| No fault isolation | A memory leak in e-mail notifications crashed checkout for 50 minutes | Notification runs in its own process and receives events; if it fails, orders still succeed and e-mails wait in the queue (proved in Section 6.3) |
| Code and data are entangled | A second payment provider took seven weeks | A Payment service with one adapter per provider behind a stable interface |
| Slow, risky releases | Every three weeks, on Friday evening, by hand, 40 minutes offline | Each service is deployed separately by an automated pipeline, with no downtime |
| No visibility | Local log files; no dashboard or alerts; customers report incidents | Central logs, metrics, traces and alerts (Section 4.2) |

The common thread is independence. Microservices give each business capability its own process, data and release cycle, so MaltaShop can scale checkout without scaling e-mails, release Payment without retesting Catalogue, and lose Notification without losing sales.

## 1.2 Monolith, ESB-based SOA or microservices

Table 2 compares the three options for MaltaShop.

Table: Table 2 — The three options compared for MaltaShop
| Criterion | Monolith (made modular) | Vendor's ESB-based SOA | Microservices |
|---|---|---|---|
| Scale checkout alone | No | Partly; the ESB is a shared bottleneck | Yes |
| Fault isolation | Low | Medium; the ESB is a single point of failure | High, if calls are asynchronous or protected |
| Weekly, independent releases | No; one release train | Limited; changes queue for the ESB team | Yes, per service |
| Where integration logic lives | In-process calls | In a central "smart" bus (Erl, 2005) | Smart endpoints, dumb pipes (Lewis and Fowler, 2014) |
| Cost and skills | Lowest | Licence fees, proprietary skills, lock-in | Containers, Kubernetes and monitoring; open-source tools |

Organisational factors decide this choice as much as technical ones. Twelve developers are too many for one codebase but enough for three teams of four, each owning a few services, and Conway's law (Conway, 1968) says the system will mirror that structure anyway. The weekly release goal needs independent deployment, which neither the monolith nor a central bus provides. Against microservices: nobody has run Kubernetes, there are only two operations staff, and GDPR and card payments demand strong governance.

The ESB would recreate the original problem elsewhere: routing and transformation logic would move into a shared bus owned by one vendor and one team, adding licence cost and a new single point of failure. SOA's useful ideas, service contracts and reuse, survive in microservices without the bus.

**Recommendation:** move to microservices gradually, not by a rewrite. Using the strangler fig pattern (Fowler, 2004), extract Notification first, then Order, Inventory and Payment, and build Recommendation and the partner API as new services; Catalogue and Customer stay in the monolith until the platform has proved itself. The target is about eight services, not hundreds, which answers the CFO's concern (Fowler, 2015).

## 1.3 Distributed-systems principles and the new problems

Three principles shape the recommendation. **Partial failure:** some parts fail while others keep working (Rotem-Gal-Oz, 2006), so the checkout path is kept short and everything else is asynchronous; a failing Notification or Recommendation service cannot block an order. **An unreliable network:** calls time out and messages arrive twice, so every write carries an idempotency key and every consumer ignores events it has already processed (Section 6.1). **Eventual consistency:** without a shared database, Order, Inventory and Payment agree only after events have flowed (Vogels, 2009); MaltaShop accepts a few seconds of "order received, confirming payment", which customers already know from card payments.

The price is real: network latency between services, data spread over several databases with no cross-service joins, harder debugging, versioned contracts between teams, and a platform that two operations staff must learn. Sections 4 and 5 show how each is managed.
