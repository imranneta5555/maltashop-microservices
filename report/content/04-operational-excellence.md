# 4. Operational Excellence and Monitoring

## 4.1 Keeping checkout reliable at ten times normal traffic

Kubernetes keeps checkout reliable by constantly making the cluster match a declared state (Burns *et al.*, 2022). Order, Payment and Inventory each run as a **Deployment**, which manages a **ReplicaSet**: if a pod crashes or its node fails, the ReplicaSet starts a replacement. Pods are spread across three availability zones, so losing a zone leaves two-thirds of the capacity.

**Probes** decide which pods receive traffic (Kubernetes, n.d.a). The readiness probe calls `/health/ready`, which checks the database; a pod that is starting, overloaded or cut off is removed from the load balancer instead of returning errors. The liveness probe calls `/health/live` and restarts a pod that hangs. **Resource requests** reserve CPU and memory so the scheduler only places pods where they fit, and **limits** cap each pod: the March memory leak would now restart one Notification pod, not take down checkout.

For the peak, the **Horizontal Pod Autoscaler** adds Order replicas when average CPU use passes 60%, from 3 up to 30 (Kubernetes, n.d.b), and the cluster autoscaler adds nodes when pods do not fit. Because autoscaling takes minutes, the minimum is raised before a planned sale, after a k6 test at ten times normal traffic on staging. Listing 3 shows these settings for the Order service.

Listing: Listing 3 — Order service Deployment and autoscaler (excerpt)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata: {name: order-service}
spec:
  replicas: 3
  selector: {matchLabels: {app: order-service}}
  template:
    metadata: {labels: {app: order-service}}
    spec:
      topologySpreadConstraints:          # spread replicas over three zones
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: ScheduleAnyway
          labelSelector: {matchLabels: {app: order-service}}
      containers:
        - name: order-service
          # the exact image digest that passed the pipeline
          image: ghcr.io/imranneta5555/maltashop-order-service@sha256:...
          envFrom: [{secretRef: {name: order-service-config}}]
          ports: [{containerPort: 8000}]
          resources:
            requests: {cpu: 250m, memory: 256Mi}
            limits: {memory: 512Mi}       # a leak ends in a restart
          readinessProbe:
            httpGet: {path: /health/ready, port: 8000}
            periodSeconds: 5
            failureThreshold: 2
          livenessProbe:
            httpGet: {path: /health/live, port: 8000}
            periodSeconds: 10
            failureThreshold: 3
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata: {name: order-service}
spec:
  scaleTargetRef: {apiVersion: apps/v1, kind: Deployment, name: order-service}
  minReplicas: 3
  maxReplicas: 30
  metrics:
    - type: Resource
      resource: {name: cpu, target: {type: Utilization, averageUtilization: 60}}
```

All eight services and the gateway are stateless and run as Deployments. The stateful parts (PostgreSQL, MongoDB, Redis and RabbitMQ) stay outside the cluster as managed services, such as Amazon RDS with a standby in a second zone, so the team does not operate databases on Kubernetes in its first year.

Because nobody has run Kubernetes in production, the risk is reduced in steps: a managed control plane (Amazon EKS) in an EU region; all cluster configuration in Git, applied by Argo CD; training for the operations staff and one developer per team; an external specialist for set-up and the first three months of on-call; and Notification as the first service in production, because its failure does the least harm.

## 4.2 Centralised logging and observability

Today each server writes its own log file and nobody is alerted. Now every service must write one JSON object per line to standard output with the fields in Table 10, as the prototype already does (Figure 10).

Table: Table 10 — Mandatory log schema
| Field | Example | Rule |
|---|---|---|
| `timestamp` | 2026-10-05T04:28:58.666Z | UTC, ISO 8601, milliseconds |
| `level` | INFO | DEBUG, INFO, WARNING or ERROR |
| `service`, `version`, `environment` | order-service, 1f3c9a2, production | Identify what logged it and which release |
| `correlation_id` | 8f2bdf1c-d1c3-… | From the X-Correlation-ID header, or created at the gateway; copied into every event and outgoing call |
| `trace_id`, `span_id` | 4bf92f3577b34da6… | From OpenTelemetry; links the log line to its trace |
| `event` | order.placed | Stable, searchable name |
| `message` | Order saved as PENDING | For people |
| Context | `order_id`, `event_id`, `duration_ms` | IDs only: no names, e-mail addresses or card data (European Parliament and Council of the European Union, 2016; PCI Security Standards Council, 2022) |

Every service is instrumented with OpenTelemetry (OpenTelemetry, n.d.), and a Collector on each node removes personal-data fields and samples traces. Logs go to Loki, metrics to Prometheus and traces to Tempo, all viewed in Grafana and hosted by Grafana Cloud in an EU region (Figure 4; ADR-002 in Section 5.3).

![Figure 4 — The observability pipeline. Services send JSON logs, metrics and traces through an OpenTelemetry Collector to Loki, Prometheus and Tempo; Grafana shows them together and its alert rules page the on-call engineer of the owning team, with a link to the runbook.](diagrams/out/observability.png)

**Checkout SLO:** 99.9% of checkout requests (placing an order and confirming payment) succeed, without a server error and within 2 seconds, measured at the gateway over a rolling 30 days. This leaves an error budget of 0.1%, about 43 minutes of failure a month. The two alerts in Table 11 use the burn-rate method (Beyer *et al.*, 2018).

Table: Table 11 — Checkout alerts
| Alert | Metric | Threshold and duration | Severity | First runbook step |
|---|---|---|---|---|
| Checkout fast burn | Share of failed or slow checkout requests | Over 1.44% (budget burning 14.4× too fast) for both the last hour and the last 5 minutes | Critical: page on-call | Open the checkout dashboard; if anything was deployed in the last hour, roll it back first |
| Checkout slow burn | Same | Over 0.6% (6× too fast) for both the last 6 hours and the last 30 minutes | Warning: ticket for the owning team | Find which service's error rate rose on the RED dashboard, then search its logs by correlation ID |

Replaying the **March incident** with this design shows the difference:

1. Notification's memory grows after a release. Kubernetes restarts each pod at its 512 Mi limit, and an alert fires on more than three restarts in 15 minutes. Checkout is unaffected: orders are accepted and their events wait in RabbitMQ (Section 6.3), so the checkout alerts stay silent.
2. The Notification dashboard shows memory climbing from the moment version 1.8 was deployed (deployments are marked on the graphs).
3. In Loki the engineer filters Notification's ERROR lines and finds out-of-memory errors in the template renderer; following one correlation ID to its trace shows rendering time growing with every message.
4. They roll Notification back to the previous image digest. The waiting events are then processed, and because the consumer ignores repeated event IDs, no customer receives a duplicate e-mail.

Detection takes minutes instead of waiting for complaints, and the failure costs e-mails, not sales.

## 4.3 Service mesh or resilience patterns first

A service mesh places a sidecar proxy (Envoy, in Istio) next to every pod, so all traffic between services passes through proxies that are configured centrally (Istio, n.d.). It adds fault tolerance without code changes: **mutual TLS** encrypts and authenticates every call; **retries** (with a budget) and **timeouts** are set per route; **circuit breaking** ejects failing instances; and **traffic shifting** sends, for example, 10% of calls to a new version, which is how canary releases are routed.

MaltaShop should **not adopt a mesh now**, but build resilience into the services and the gateway first. Most traffic between services goes asynchronously through RabbitMQ, which a mesh does not manage. The few synchronous calls (gateway to services, Payment to its providers) are protected by timeouts, retries with idempotency keys and circuit breakers (Nygard, 2018), and Argo Rollouts already handles canary traffic. A mesh would add a proxy to every pod, more memory and a complex control plane for two operations staff who are still learning Kubernetes. Revisit this after twelve months, or sooner if synchronous calls multiply or an auditor requires encryption inside the cluster; Linkerd or Istio's sidecar-free ambient mode would then be the lighter options.
