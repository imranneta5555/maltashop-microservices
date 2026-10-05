#!/usr/bin/env python3
"""Draws the report's diagrams as SVG files in diagrams/src/ (render.sh turns them into PNGs).

Every figure is drawn at a design width of 880 units, which the report scales to the full
text width, so a font size of 14 here prints at about 7.5 pt.
"""
from pathlib import Path

OUT = Path(__file__).parent / "src"

FONT = "Helvetica, Arial, sans-serif"
INK = "#1f2328"
GREY = "#6e7781"
LIGHT = "#f3f5f7"
WHITE = "#ffffff"
ACCENT = "#b42318"       # checkout-critical, gates, compensation
AMBER = "#9a5b00"        # message broker and events
AMBER_FILL = "#fdf3e1"
BLUE = "#1f5f99"         # observability and prototype marks
BLUE_FILL = "#e8f1fa"
COLOURS = {"ink": INK, "grey": GREY, "accent": ACCENT, "amber": AMBER, "blue": BLUE}


# ------------------------------------------------------------------ primitives

def svg(width, height, body):
    markers = "".join(
        f'<marker id="arrow-{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse"><path d="M0,1 L9,5 L0,9 z" fill="{colour}"/></marker>'
        for name, colour in COLOURS.items())
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" font-family="{FONT}">\n<defs>{markers}</defs>\n'
            f'<rect width="{width}" height="{height}" fill="white"/>\n{body}\n</svg>\n')


def esc(content):
    return str(content).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, content, size=14, anchor="middle", colour=INK, bold=False, italic=False):
    style = (' font-weight="bold"' if bold else "") + (' font-style="italic"' if italic else "")
    return (f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" fill="{colour}"{style}>'
            f'{esc(content)}</text>')


def text_lines(x, y, rows, size=13.5, gap=17, **kw):
    return "\n".join(text(x, y + i * gap, row, size=size, **kw) for i, row in enumerate(rows))


def rect(x, y, w, h, fill=LIGHT, stroke=INK, width=1.4, rx=7, dashed=False):
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{width}"{dash}/>')


def box(x, y, w, h, title, rows=(), fill=LIGHT, stroke=INK, width=1.4, title_size=15, size=13.5,
        dashed=False, title_colour=INK, top=None):
    """A rounded box with a bold title and centred lines under it."""
    parts = [rect(x, y, w, h, fill, stroke, width, dashed=dashed)]
    block = 18 + len(rows) * 17
    first = top if top is not None else y + (h - block) / 2 + 14
    parts.append(text(x + w / 2, first, title, size=title_size, bold=True, colour=title_colour))
    parts.append(text_lines(x + w / 2, first + 19, rows, size=size))
    return "\n".join(parts)


def arrow(x1, y1, x2, y2, colour="ink", dashed=False, both=False, width=1.5):
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    start = f' marker-start="url(#arrow-{colour})"' if both else ""
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{COLOURS[colour]}" stroke-width="{width}"'
            f'{dash}{start} marker-end="url(#arrow-{colour})"/>')


def polyline(points, colour="ink", dashed=False, end_arrow=True, width=1.5):
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    marker = f' marker-end="url(#arrow-{colour})"' if end_arrow else ""
    pts = " ".join(f"{x},{y}" for x, y in points)
    return (f'<polyline points="{pts}" fill="none" stroke="{COLOURS[colour]}" stroke-width="{width}"'
            f'{dash}{marker}/>')


def line(x1, y1, x2, y2, colour=INK, width=1.2, dashed=False):
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{colour}" stroke-width="{width}"{dash}/>'


def cylinder(x, y, w=18, h=22, colour=INK):
    """A small database symbol with its top-left corner at (x, y)."""
    ry = 4
    return (f'<path d="M{x},{y + ry} v{h - 2 * ry} a{w / 2},{ry} 0 0 0 {w},0 v{-(h - 2 * ry)}" '
            f'fill="white" stroke="{colour}" stroke-width="1.2"/>'
            f'<ellipse cx="{x + w / 2}" cy="{y + ry}" rx="{w / 2}" ry="{ry}" fill="white" stroke="{colour}" '
            f'stroke-width="1.2"/>')


def service(x, y, w, h, name, stores, critical=False, extra=None):
    """A service box: name on top, its own data store(s) in a lower compartment."""
    stroke = ACCENT if critical else INK
    parts = [rect(x, y, w, h, WHITE, stroke, 2.0 if critical else 1.4)]
    parts.append(text(x + w / 2, y + 22, name, size=15, bold=True, colour=stroke))
    if extra:
        parts.append(text(x + w / 2, y + 38, extra, size=12.5, colour=GREY, italic=True))
    divider = y + (46 if extra else 32)
    parts.append(line(x, divider, x + w, divider, colour=stroke, width=1.0))
    parts.append(cylinder(x + 10, divider + 8))
    for i, store in enumerate(stores):
        parts.append(text(x + 36, divider + 22 + i * 16, store, size=13, anchor="start"))
    return "\n".join(parts)


# -------------------------------------------------------------------- figures

def architecture():
    """Figure: container-level architecture of the target MaltaShop platform."""
    b = []
    # clients
    for cx, title, rows in ((120, "Web storefront", ["browser"]), (330, "Mobile app", ["iOS and Android"]),
                            (540, "Partner systems", ["30 retailers, courier"])):
        b.append(box(cx - 90, 12, 180, 54, title, rows, fill=WHITE))
        b.append(arrow(cx, 66, cx, 106))
    # gateway and identity provider
    b.append(box(30, 108, 610, 64, "API gateway (Kong)",
                 ["HTTPS, checks every token, per-partner scopes and rate limits, routing"], fill=LIGHT))
    b.append(box(672, 100, 190, 80, "Identity provider", ["Keycloak: OIDC for", "customers, OAuth 2.0", "for partners"],
                 fill=WHITE, size=12.5, top=121))
    b.append(arrow(642, 140, 670, 140, colour="grey", dashed=True, both=True))
    # cluster boundary
    b.append(rect(12, 194, 856, 410, fill="none", stroke=GREY, width=1.2, rx=10, dashed=True))
    b.append(text(26, 214, "Kubernetes cluster (managed, EU region)", size=13, anchor="start", colour=GREY,
                  italic=True))
    # fan-out from the gateway to the synchronous services
    centres = [110, 275, 440, 605, 770]
    b.append(line(335, 172, 335, 228))
    b.append(line(centres[0], 228, centres[-1], 228))
    top = [("Catalogue", ["PostgreSQL", "+ Redis cache"], False, None),
           ("Customer", ["PostgreSQL", "(PII encrypted)"], False, None),
           ("Order", ["PostgreSQL"], True, None),
           ("Partner", ["PostgreSQL"], False, None),
           ("Recommendation", ["Redis + object", "storage"], False, "AI model, Python")]
    for cx, (name, stores, critical, extra) in zip(centres, top):
        b.append(arrow(cx, 228, cx, 250))
        b.append(service(cx - 77, 252, 154, 98, name, stores, critical, extra))
    # broker
    b.append(rect(30, 398, 820, 50, fill=AMBER_FILL, stroke=AMBER, width=1.6))
    b.append(text(440, 419, "RabbitMQ message broker: topic exchange maltashop.events", size=15, bold=True,
                  colour=AMBER))
    b.append(text(440, 438, "OrderPlaced, StockReserved, PaymentAuthorised, PaymentFailed, ProductViewed, "
                            "StockUpdated, CustomerErased", size=12.5, colour=AMBER))
    for cx, mode in zip(centres, ("pub", "pub", "both", "both", "sub")):
        if mode == "sub":
            b.append(arrow(cx, 397, cx, 352, colour="amber", dashed=True))
        else:
            b.append(arrow(cx, 351, cx, 396, colour="amber", dashed=True, both=mode == "both"))
    # asynchronous-only services
    bottom = [(190, "Inventory", ["PostgreSQL"], True, "both"),
              (440, "Payment", ["PostgreSQL"], True, "both"),
              (690, "Notification", ["MongoDB"], False, "sub")]
    for cx, name, stores, critical, mode in bottom:
        b.append(service(cx - 77, 488, 154, 80, name, stores, critical))
        b.append(arrow(cx, 450, cx, 486, colour="amber", dashed=True, both=mode == "both"))
    # external providers
    b.append(box(350, 626, 180, 56, "Payment providers", ["card data stays with them"], fill=WHITE, dashed=True))
    b.append(box(600, 626, 180, 56, "E-mail and SMS", ["provider"], fill=WHITE, dashed=True))
    b.append(arrow(440, 568, 440, 624))
    b.append(arrow(690, 568, 690, 624))
    # legend
    b.append(arrow(20, 640, 62, 640))
    b.append(text(70, 645, "synchronous HTTPS", size=12.5, anchor="start"))
    b.append(arrow(20, 662, 62, 662, colour="amber", dashed=True))
    b.append(text(70, 667, "asynchronous event", size=12.5, anchor="start"))
    b.append(rect(22, 676, 38, 14, WHITE, ACCENT, 2.0, rx=3))
    b.append(text(70, 688, "checkout-critical", size=12.5, anchor="start"))
    b.append(cylinder(268, 652))
    b.append(text(292, 662, "own data", size=12.5, anchor="start"))
    b.append(text(292, 677, "store", size=12.5, anchor="start"))
    return svg(880, 700, "\n".join(b))


def pipeline():
    """Figure: CI/CD pipeline for the Order service, with the gate on each stage."""
    b = []
    w, h, gap, x0 = 152, 128, 18, 17
    rows = [
        ("Pull request (every push to a short-lived branch)", 34, [
            ("1 Push", ["git push of a", "feature branch,", "pull request opened"], "no secrets", False),
            ("2 Fast checks", ["lint (ruff) and", "unit tests"], "all pass", True),
            ("3 Contract tests", ["Order vs Notification", "and Payment", "(Pact / schema)"], "can-i-deploy", True),
            ("4 Code review", ["owning team", "(CODEOWNERS)"], "1 approval", False),
            ("5 Merge", ["squash merge", "into main"], "up to date", False)]),
        ("Main branch (every merge)", 252, [
            ("6 Build once", ["image tagged with", "commit SHA, scanned,", "pushed to registry"], "no critical CVE", True),
            ("7 Staging", ["Argo CD deploys", "the same image", "digest"], "pods ready", False),
            ("8 Staging tests", ["integration and", "smoke tests; k6", "load test weekly"], "all pass", True),
            ("9 Approve", ["one click by the", "release owner", "(continuous delivery)"], "approved", False),
            ("10 Canary", ["production 10%", "then 50%, 100%", "(Argo Rollouts)"], "SLO metrics OK", False)]),
    ]
    for label, y, stages in rows:
        b.append(text(863 if y > 100 else x0, y - 12, label, size=13.5, anchor="end" if y > 100 else "start",
                      colour=GREY, italic=True))
        for i, (title, lines_, gate, in_prototype) in enumerate(stages):
            x = x0 + i * (w + gap)
            b.append(rect(x, y, w, h, LIGHT, INK, 1.4))
            b.append(text(x + w / 2, y + 22, title, size=14.5, bold=True))
            b.append(text_lines(x + w / 2, y + 42, lines_, size=12.5, gap=15.5))
            b.append(line(x, y + h - 28, x + w, y + h - 28, colour=ACCENT, width=1.0))
            b.append(text(x + w / 2, y + h - 9, f"Gate: {gate}", size=12.5, bold=True, colour=ACCENT))
            if in_prototype:
                b.append(rect(x + w - 30, y - 9, 40, 18, BLUE_FILL, BLUE, 1.1, rx=9))
                b.append(text(x + w - 10, y + 4.5, "CI ✓", size=11, bold=True, colour=BLUE))
            if i < len(stages) - 1:
                b.append(arrow(x + w + 1, y + h / 2, x + w + gap - 1, y + h / 2))
    # from merge (end of row 1) to build (start of row 2)
    last_x = x0 + 4 * (w + gap) + w / 2
    b.append(polyline([(last_x, 34 + h), (last_x, 205), (x0 + w / 2, 205), (x0 + w / 2, 250)]))
    # rollback path
    b.append(polyline([(x0 + 4 * (w + gap) + w / 2, 252 + h), (x0 + 4 * (w + gap) + w / 2, 412),
                       (x0 + 1 * (w + gap) + w / 2, 412)], colour="accent", dashed=True))
    b.append(text(x0 + 2.5 * (w + gap) + w / 2 - 10, 405, "gate fails: automatic rollback to the previous "
                  "image digest, team alerted", size=12.5, colour=ACCENT, bold=True))
    # build once, promote everywhere band
    b.append(rect(x0, 428, 4 * (w + gap) + w, 46, BLUE_FILL, BLUE, 1.2))
    b.append(text(440, 447, "Build once, promote everywhere: one image, ghcr.io/…/maltashop-order-service@sha256:…,",
                  size=13, colour=BLUE, bold=True))
    b.append(text(440, 465, "moves from stage 6 to production unchanged; only environment variables and secrets "
                            "differ.", size=13, colour=BLUE))
    b.append(rect(x0, 486, 40, 18, BLUE_FILL, BLUE, 1.1, rx=9))
    b.append(text(x0 + 20, 499.5, "CI ✓", size=11, bold=True, colour=BLUE))
    b.append(text(x0 + 50, 500, "stage implemented in the prototype's .github/workflows/ci.yml (stage 8 runs "
                                "on the CI runner)", size=12.5, anchor="start", colour=BLUE))
    return svg(880, 516, "\n".join(b))


def observability():
    """Figure: how logs, metrics and traces flow from the services to the on-call engineer."""
    b = []
    b.append(text(105, 24, "Services (8)", size=13.5, colour=GREY, italic=True))
    for i, name in enumerate(("order-service", "payment-service", "notification-service", "… other services")):
        y = 36 + i * 52
        b.append(box(20, y, 170, 42, name, [], fill=WHITE, title_size=13.5))
        b.append(arrow(191, y + 21, 236, 140))
    b.append(text(105, 254, "OpenTelemetry SDK; JSON logs", size=12.5, colour=GREY))
    b.append(text(105, 270, "with correlation_id, trace_id", size=12.5, colour=GREY))
    b.append(box(238, 80, 160, 120, "OTel Collector", ["one per node", "batches, removes", "PII fields, samples", "traces"],
                 fill=LIGHT))
    b.append(rect(436, 30, 186, 232, fill="none", stroke=BLUE, width=1.2, rx=10, dashed=True))
    b.append(text(529, 50, "Grafana Cloud, EU region", size=12.5, colour=BLUE, italic=True))
    for i, (name, rows) in enumerate((("Loki", ["logs, 30 days"]), ("Prometheus", ["metrics, 13 months"]),
                                      ("Tempo", ["traces, 14 days"]))):
        y = 62 + i * 66
        b.append(box(452, y, 154, 54, name, rows, fill=BLUE_FILL, stroke=BLUE))
        b.append(arrow(399, 140, 450, y + 27, colour="blue"))
        b.append(arrow(607, y + 27, 672, 72 + i * 22, colour="blue"))
    b.append(box(674, 54, 190, 74, "Grafana", ["dashboards: checkout SLO,", "per-service RED metrics"], fill=WHITE))
    b.append(box(674, 150, 190, 74, "Grafana Alerting", ["SLO burn-rate rules,", "routed by service owner"], fill=WHITE))
    b.append(arrow(769, 129, 769, 148))
    b.append(box(674, 246, 190, 58, "On-call engineer", ["phone + Slack, runbook link"], fill=WHITE,
                 stroke=ACCENT, title_colour=ACCENT))
    b.append(arrow(769, 225, 769, 244, colour="accent"))
    b.append(text(430, 300, "A log line, its trace and its metrics are linked by trace_id and correlation_id.",
                  size=12.5, colour=GREY, italic=True))
    return svg(880, 316, "\n".join(b))


def saga():
    """Figure: the place-order saga (choreography), with the compensation path in red."""
    b = []
    lanes = {"Storefront": 80, "Order": 250, "Inventory": 430, "Payment": 610, "Notification": 785}
    for name, x in lanes.items():
        critical = name in ("Order", "Inventory", "Payment")
        b.append(line(x, 50, x, 532, colour=GREY, width=1.0, dashed=True))
        b.append(box(x - 70, 12, 140, 38, name, [], fill=WHITE, stroke=ACCENT if critical else INK,
                     title_colour=ACCENT if critical else INK, title_size=14.5))
    S, O, I, P, N = lanes.values()

    def note(x, y, content, colour=INK, fill=LIGHT, w=None):
        width = w or (len(content) * 7.0 + 22)
        return "\n".join([rect(x - width / 2, y - 15, width, 24, fill, colour, 1.1, rx=5),
                          text(x, y + 2, content, size=12.5, colour=colour)])

    def msg(x1, x2, y, label, colour="ink", dashed=False, through=(), label_x=None):
        parts = [arrow(x1, y, x2, y, colour=colour, dashed=dashed)]
        for xt in through:  # this service also consumes the event
            direction = 1 if x2 > x1 else -1
            parts.append(polyline([(xt - 8 * direction, y - 5), (xt, y), (xt - 8 * direction, y + 5)],
                                  colour=colour, end_arrow=False, width=1.8))
        mid = label_x or ((x1 + x2) / 2 if not through else (x1 + through[0]) / 2)
        parts.append(text(mid, y - 7, label, size=12.5, colour=COLOURS[colour], bold=True))
        return "\n".join(parts)

    b.append(msg(S, O, 84, "1  POST /orders + Idempotency-Key"))
    b.append(note(O + 150, 116, "2  save order (PENDING) and OrderPlaced in the outbox: one local transaction",
                  w=540))
    b.append(msg(O, S, 152, "3  201 Created (PENDING)", colour="grey"))
    b.append(msg(O, N, 194, "4  OrderPlaced", colour="amber", dashed=True, through=(I,)))
    b.append(text((P + N) / 2, 187, "(“order received” e-mail)", size=12, colour=AMBER, italic=True))
    b.append(note(I, 226, "5  reserve stock for order_id"))
    b.append(msg(I, P, 262, "6  StockReserved", colour="amber", dashed=True))
    b.append(note(P, 294, "7  charge via provider, idempotency key = order_id", w=330))
    b.append(line(14, 320, 866, 320, colour=INK, width=0.8))
    b.append(text(20, 338, "if payment succeeds", size=12.5, anchor="start", bold=True))
    b.append(msg(P, O, 368, "8a  PaymentAuthorised", colour="amber", dashed=True, through=(I,)))
    b.append(arrow(P, 368, N, 368, colour="amber", dashed=True))
    b.append(note(O, 398, "order CONFIRMED", w=150))
    b.append(note(I, 398, "reservation kept", w=140))
    b.append(note(N, 398, "confirmation e-mail", w=150))
    b.append(line(14, 424, 866, 424, colour=ACCENT, width=0.8))
    b.append(text(20, 442, "if payment is declined: compensating actions", size=12.5, anchor="start", bold=True,
                  colour=ACCENT))
    b.append(msg(P, O, 472, "8b  PaymentFailed", colour="accent", dashed=True, through=(I,)))
    b.append(arrow(P, 472, N, 472, colour="accent", dashed=True))
    b.append(note(O, 504, "order CANCELLED", colour=ACCENT, fill="#fdecea", w=150))
    b.append(note(I, 504, "release the reservation", colour=ACCENT, fill="#fdecea", w=172))
    b.append(note(N, 504, "“payment failed” e-mail", colour=ACCENT, fill="#fdecea", w=172))
    b.append(text(440, 556, "If stock cannot be reserved, Inventory publishes StockReservationFailed and Order "
                            "cancels the order (no payment is taken).", size=12.5, colour=GREY, italic=True))
    b.append(text(440, 576, "Every step is idempotent: events carry event_id and order_id, and a repeated "
                            "event changes nothing.", size=12.5, colour=GREY, italic=True))
    b.append(arrow(220, 600, 260, 600, colour="amber", dashed=True))
    b.append(text(266, 604, "event through RabbitMQ", size=12.5, anchor="start"))
    b.append(arrow(470, 600, 510, 600))
    b.append(text(516, 604, "synchronous HTTPS", size=12.5, anchor="start"))
    return svg(880, 616, "\n".join(b))


def prototype():
    """Figure: the prototype's containers and networks under Docker Compose."""
    b = []
    b.append(rect(10, 60, 860, 230, fill="none", stroke=GREY, width=1.2, rx=10))
    b.append(text(22, 80, "docker compose up: one host, five containers", size=12.5, anchor="start", colour=GREY,
                  italic=True))
    b.append(rect(22, 96, 344, 176, fill="#f6f8fa", stroke=INK, width=1.0, rx=8, dashed=True))
    b.append(text(34, 264, "order-net", size=12.5, anchor="start", bold=True))
    b.append(rect(514, 96, 344, 176, fill="#f6f8fa", stroke=INK, width=1.0, rx=8, dashed=True))
    b.append(text(846, 264, "notification-net", size=12.5, anchor="end", bold=True))
    b.append(rect(190, 112, 500, 128, fill="none", stroke=AMBER, width=1.3, rx=8, dashed=True))
    b.append(text(440, 232, "events-net", size=12.5, bold=True, colour=AMBER))
    b.append(box(34, 140, 130, 64, "order-db", ["postgres:16"], fill=WHITE))
    b.append(box(200, 140, 154, 64, "order-service", ["FastAPI, port 8000"], fill=WHITE, stroke=ACCENT,
                 title_colour=ACCENT, title_size=14))
    b.append(box(380, 140, 120, 64, "rabbitmq", ["4-management"], fill=AMBER_FILL, stroke=AMBER,
                 title_colour=AMBER))
    b.append(box(526, 140, 160, 64, "notification-service", ["FastAPI, port 8000"], fill=WHITE, title_size=13.5))
    b.append(box(716, 140, 130, 64, "notification-db", ["mongo:7"], fill=WHITE, title_size=13.5))
    b.append(arrow(199, 172, 166, 172))
    b.append(arrow(355, 172, 378, 172, colour="amber", dashed=True))
    b.append(arrow(501, 172, 524, 172, colour="amber", dashed=True))
    b.append(arrow(687, 172, 714, 172))
    b.append(text(366, 132, "OrderPlaced", size=12.5, colour=AMBER, bold=True, anchor="end"))
    for x, label in ((277, "host :8001  POST /orders"), (440, "host :15672  broker UI"),
                     (606, "host :8002  GET /notifications")):
        b.append(arrow(x, 30, x, 138, colour="grey"))
        b.append(text(x, 22, label, size=12.5, colour=GREY))
    return svg(880, 300, "\n".join(b))


FIGURES = {
    "architecture": architecture,
    "pipeline": pipeline,
    "observability": observability,
    "saga": saga,
    "prototype": prototype,
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, draw in FIGURES.items():
        (OUT / f"{name}.svg").write_text(draw(), encoding="utf-8")
        print(f"  wrote src/{name}.svg")


if __name__ == "__main__":
    main()
