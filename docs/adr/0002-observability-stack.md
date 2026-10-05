# ADR-002: Observability stack: OpenTelemetry with Grafana Cloud

**Status:** accepted, October 2026

## Context

Logs are local files and customers report incidents. The team needs logs, metrics, traces and alerts
in one place, on a limited budget, run by two operations staff, with personal data kept in the EU.

## Decision

Instrument every service with OpenTelemetry and use Grafana Cloud (Loki, Prometheus, Tempo, Grafana
Alerting) in an EU region. Every service writes structured JSON logs with a `correlation_id` (as the
prototype's `logging_setup.py` does).

Criteria: cost at MaltaShop's volume, operational effort, vendor neutrality, all three signals in one
tool, and EU data residency.

| Alternative | Why rejected |
|---|---|
| Self-hosted Elastic (ELK) stack | Powerful search, but running Elasticsearch clusters needs time and skills the operations staff do not have |
| Datadog | Excellent, but per-host and per-gigabyte pricing grows fast and its agents increase lock-in |
| Cloud provider tools only (CloudWatch) | Cheaper, but weaker tracing and dashboards, and tied to one provider |

## Consequences

- Nothing to operate, and OpenTelemetry lets the backend change without touching service code.
- The bill grows with log volume, so production logs exclude DEBUG, are kept 30 days, and only 10% of
  normal traces are stored (all error traces are kept).
- Technical debt accepted: dashboards and alerts are first built by hand and must later move into
  code (Terraform) to be reviewed and versioned like the services.
