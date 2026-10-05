# 3. Lifecycle and Delivery Management

## 3.1 CI/CD pipeline for the Order service

![Figure 2 — The CI/CD pipeline for the Order service, from a developer's git push to production. Each stage has a gate (red) that must pass before the change moves on. Blue tags mark the stages already automated in the prototype's GitHub Actions workflow.](diagrams/out/pipeline.png)

Figure 2 has two halves. The pull-request half gives the developer feedback within minutes: lint and unit tests (stage 2), then contract tests (stage 3), which fail the build if Order would break a consumer such as Notification. A reviewer from the owning team must approve (stage 4) before the branch is merged.

The main-branch half produces and promotes the release. Stage 6 builds the container image once, tags it with the commit SHA, scans it and pushes it to the registry. From then on the image is never rebuilt: Argo CD deploys the same digest to staging, the integration and smoke tests (and a weekly load test) run against it, and after approval the same digest goes to production as a canary. This is "build once, promote everywhere" (Humble and Farley, 2010): what was tested is exactly what runs, environments differ only in configuration, and rolling back means redeploying the previous digest. The prototype already works this way: its workflow tests the images it has just built, without rebuilding them (Figure 3).

Branching follows trunk-based development (Hammant, 2017): short-lived feature branches merged at least every two days, with unfinished work hidden behind feature flags. Long-lived branches would bring back the large, risky merges of the three-week release train. The pipeline is itself an attack surface, so third-party actions are pinned to commit SHAs, each job gets only the permissions it needs, push protection blocks committed secrets, and only the pipeline can push images.

MaltaShop should choose **continuous delivery**, not continuous deployment, for now. Every merge produces a release candidate that could go live, but a person approves the production step (stage 9) for Order and Payment, because they handle money and the team is new to the platform. Weekly releases need nothing more. Once three months of DORA metrics show few failed changes, low-risk services such as Notification and Catalogue can move to continuous deployment.

## 3.2 Automated testing strategy for the Order service

Testing follows the test pyramid (Cohn, 2009; Vocke, 2018): many fast unit tests at the base and fewer, slower tests towards the top. Table 7 sets out what each level checks in the Order service and where it runs in Figure 2.

Table: Table 7 — Test pyramid for the Order service
| Level | What is tested | Tools | Pipeline stage |
|---|---|---|---|
| Unit (many, milliseconds) | Pricing and totals; validation (unknown SKU, quantity 1–20); status changes PENDING → CONFIRMED or CANCELLED; events carry no personal data | pytest | 2, every push |
| Component (some, seconds) | The API with a real PostgreSQL and RabbitMQ in containers: idempotency key, outbox written in the same transaction, relay publishes | pytest, Testcontainers | 2, every push |
| Contract (one per pair) | OrderPlaced still meets Notification's needs; Order's calls still match Payment's API | JSON Schema now, Pact later | 3, before merge |
| End-to-end (few) | The whole place-order flow across services | `smoke_test.py` | 8, staging (prototype: CI runner) |
| Load (weekly, before sales) | Ten times normal checkout traffic; p95 latency and error rate | k6 | 8, weekly |

The contract test in Listing 1 is between two named services: **Order** (provider) and **Notification** (consumer). The fields that Notification relies on are written down in `contracts/order-placed.v1.schema.json`. Order's build fails if its event no longer satisfies them, and Notification's build checks that it can handle the contract's example, so each side is tested on its own against the same contract.

Listing: Listing 1 — Provider side of the OrderPlaced contract test (order-service/tests)
```python
def test_order_placed_event_satisfies_the_consumer_contract():
    lines = [OrderLine(sku="TV-55-4K", quantity=1),
             OrderLine(sku="KETTLE-1.7L", quantity=2)]
    order = {"order_id": uuid.uuid4(), "customer_id": "C-1001",
             "status": "PENDING", "total_amount": order_total(lines),
             "currency": "EUR", "items": price_lines(lines)}

    event = json.loads(json.dumps(
        order_placed_event(order, correlation_id=str(uuid.uuid4()))))

    # raises ValidationError if the event breaks the consumer's contract
    Draft202012Validator(SCHEMA, format_checker=FormatChecker()).validate(event)
```

When `customer_id` was renamed as an experiment, this test failed with "'customer_id' is a required property", which is exactly the breaking change it exists to stop. In production the schema files would be replaced by Pact (Pact Foundation, n.d.) and its can-i-deploy check, which also tells the pipeline which versions are safe to release together.

## 3.3 Deployment strategy for the Payment service

Table: Table 8 — Rolling, blue-green and canary deployment for Payment
| Strategy | How it works | Strengths for Payment | Weaknesses for Payment |
|---|---|---|---|
| Rolling | Replaces pods a few at a time (the Kubernetes default) | No extra capacity; simple | No control over who gets the new version; a bad release reaches everyone gradually; rollback is another slow rollout |
| Blue-green | A full new copy runs beside the old one; all traffic switches at once (Fowler, 2010) | Instant switch and instant rollback | Double capacity; every customer meets the new version at the same moment |
| Canary | A small share of traffic goes to the new version and grows while metrics stay healthy (Sato, 2014) | Limits damage to a few payments; decisions based on real data | Needs good metrics and automation (Argo Rollouts); slower |

Of the options in Table 8, **canary** is the right choice for Payment. A faulty payment release costs money directly and damages trust, so exposure should be limited and judged on real data. The canary sends 10% of payment traffic to the new version for 15 minutes, then 50%, then 100%. At each step Argo Rollouts compares the canary with the stable version on payment error rate, provider decline rate and p95 latency. The rollback procedure is:

1. If any metric breaches its threshold, Argo Rollouts aborts automatically, sends all traffic back to the stable version within seconds and pages the on-call engineer.
2. A payment retried during the switch cannot be charged twice, because the provider receives the order ID as its idempotency key.
3. Database changes follow expand-and-contract (new columns first, old ones removed in a later release), so the previous version still works with the current schema.
4. The engineer confirms recovery on the dashboard, records the failed image digest, and the fix goes through the normal pipeline.

Two DORA metrics (Forsgren, Humble and Kim, 2018) will show whether delivery improves (Table 9). Change failure rate cannot yet be baselined, because failed releases are not recorded today; it will be measured from the first pipeline release.

Table: Table 9 — DORA metrics: baseline and target
| Metric | MaltaShop baseline (case facts) | Target within 12 months |
|---|---|---|
| Deployment frequency | Once every three weeks, whole site, 40 minutes offline | At least weekly per service with no downtime; daily for low-risk services |
| Time to restore service | 50 minutes (March) to over two hours (Black Friday); customers notice first | Under 30 minutes for checkout, with an alert before customers notice |

### Evidence: pipeline workflow file and a passing run

Listing 2 is the prototype's `.github/workflows/ci.yml`. It runs on every push and pull request to `main`: tests for both services, one image per service built and pushed once, then an integration test of those exact images.

Listing: Listing 2 — The prototype's CI workflow (.github/workflows/ci.yml)
@file .github/workflows/ci.yml

![Figure 3 — A passing run of the prototype's CI workflow on GitHub Actions. Stage 1 lints and tests both services, stage 2 builds each image once and pushes it to GitHub Container Registry, and stage 3 starts the whole system from those images and runs the smoke test.](evidence/screenshots/06_ci_passing_run.png){w=15.9}
