#!/usr/bin/env python3
"""Runs the demonstration behind the report's evidence (Sections 3 and 6.3) and saves it.

    python3 evidence/capture.py demo    # fresh system: order, event, logs, idempotency, resilience
    python3 evidence/capture.py ci      # screenshot of the latest CI run on GitHub

Every terminal screenshot is the real output of the command shown above it; the text is also
kept in evidence/transcripts/. Needs Docker, curl, jq and Python with Playwright (Chromium).
"""
import html
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "evidence"
TRANSCRIPTS = EVIDENCE / "transcripts"
SHOTS = EVIDENCE / "screenshots"
REPO = "imranneta5555/maltashop-microservices"
ORDER = '{"customer_id": "C-1001", "items": [{"sku": "TV-55-4K", "quantity": 1}, {"sku": "KETTLE-1.7L", "quantity": 2}]}'

TERMINAL_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
body {{ margin: 0; padding: 18px; background: #ffffff; }}
.window {{ width: {width}px; border-radius: 9px; overflow: hidden; background: #1e1f22;
          box-shadow: 0 2px 10px rgba(0,0,0,.25); }}
.bar {{ height: 30px; background: #2d2f33; display: flex; align-items: center; padding: 0 12px; }}
.dot {{ width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; }}
.title {{ color: #a9adb3; font: 13px -apple-system, Helvetica, sans-serif; margin-left: 10px; }}
pre {{ margin: 0; padding: 14px 16px 16px; color: #e3e5e8; font: 13.5px/1.45 Menlo, monospace;
       white-space: pre-wrap; word-break: break-all; }}
.cmd {{ color: #7ee787; }} .hl {{ color: #ffd479; font-weight: bold; }}
</style></head><body><div class="window"><div class="bar">
<span class="dot" style="background:#ff5f57"></span><span class="dot" style="background:#febc2e"></span>
<span class="dot" style="background:#28c840"></span><span class="title">{title}</span></div>
<pre>{body}</pre></div></body></html>"""


def sh(command: str, check: bool = True) -> str:
    result = subprocess.run(["bash", "-c", command], cwd=ROOT, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise SystemExit(f"command failed: {command}\n{result.stdout}{result.stderr}")
    return (result.stdout + result.stderr).rstrip("\n")


class Terminal:
    """Runs commands, keeps a transcript and renders it as a terminal screenshot."""

    def __init__(self, browser):
        self.browser = browser

    def capture(self, name: str, title: str, commands: list[str], highlight: str | None = None,
                width: int = 1180) -> str:
        transcript = []
        for command in commands:
            transcript.append(f"$ {command}")
            output = sh(command)
            if output:
                transcript.append(output)
            transcript.append("")
        text = "\n".join(transcript).rstrip("\n")
        (TRANSCRIPTS / f"{name}.txt").write_text(text + "\n", encoding="utf-8")
        body = "\n".join(
            f'<span class="cmd">{html.escape(row)}</span>' if row.startswith("$ ") else html.escape(row)
            for row in text.splitlines())
        if highlight:
            body = body.replace(html.escape(highlight), f'<span class="hl">{html.escape(highlight)}</span>')
        page = self.browser.new_page(device_scale_factor=2, viewport={"width": width + 36, "height": 400})
        page.set_content(TERMINAL_PAGE.format(width=width, title=html.escape(title), body=body))
        page.locator(".window").screenshot(path=str(SHOTS / f"{name}.png"))
        page.close()
        print(f"  saved {name}")
        return text


def place_order_in_swagger(browser, key: str) -> tuple[str, str]:
    """Places an order through the Order service's Swagger UI; returns (order_id, correlation_id)."""
    page = browser.new_page(device_scale_factor=2, viewport={"width": 1100, "height": 1400})
    page.goto("http://localhost:8001/docs")
    block = page.locator("#operations-default-place_order_orders_post")
    block.locator(".opblock-summary").click()
    block.locator("button.try-out__btn").click()
    block.locator("input[placeholder='idempotency-key']").fill(key)
    block.locator("textarea.body-param__text").fill(json.dumps(json.loads(ORDER), indent=2))
    block.locator("button.execute").click()
    live = block.locator(".live-responses-table")
    live.wait_for()
    page.wait_for_timeout(500)
    page_text = live.inner_text()
    correlation = re.search(r"x-correlation-id:\s*([0-9a-f-]{36})", page_text).group(1)
    order_id = re.search(r'"order_id":\s*"([0-9a-f-]{36})"', page_text).group(1)
    top = block.locator(".responses-wrapper").bounding_box()  # from "Responses": the curl request and the reply
    bottom = live.bounding_box()
    page.set_viewport_size({"width": 1100, "height": int(bottom["y"] + bottom["height"] + 40)})
    page.screenshot(path=str(SHOTS / "01_swagger_place_order.png"),
                    clip={"x": top["x"], "y": top["y"], "width": top["width"],
                          "height": bottom["y"] + bottom["height"] - top["y"] + 8})
    page.close()
    print("  saved 01_swagger_place_order")
    return order_id, correlation


def rabbitmq_queues(browser, name: str) -> None:
    page = browser.new_page(device_scale_factor=2, viewport={"width": 1280, "height": 760})
    page.goto("http://localhost:15672/")
    page.fill("input[name=username]", "maltashop")
    page.fill("input[name=password]", "maltashop_dev_password")
    page.click("input[type=submit], button[type=submit]")
    page.wait_for_timeout(1500)
    page.goto("http://localhost:15672/#/queues")
    page.wait_for_timeout(6000)  # let the management UI poll the queue figures
    page.screenshot(path=str(SHOTS / f"{name}.png"), clip={"x": 0, "y": 0, "width": 1280, "height": 424})
    page.close()
    print(f"  saved {name}")


def demo() -> None:
    print("starting a fresh system ...")
    sh("docker compose down -v --remove-orphans", check=False)
    sh("docker compose up -d --build --wait")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        term = Terminal(browser)
        term.capture("00_compose_up", "docker compose", [
            "docker compose ps --format 'table {{.Service}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}'"])

        key = "checkout-2026-10-05-0001"
        order_id, correlation = place_order_in_swagger(browser, key)
        time.sleep(3)

        term.capture("02_notification_consumed", "notification-service: event consumed", [
            f"curl -s 'http://localhost:8002/notifications?order_id={order_id}' | python3 -m json.tool"],
            highlight=correlation)

        term.capture("03_correlation_logs", "logs of both services, filtered by one correlation ID", [
            f"docker compose logs --no-log-prefix order-service notification-service | grep {correlation} "
            "| jq -r '[.timestamp[11:23], .service, .correlation_id, .event, .message] | @tsv' "
            "| sort | column -t -s $'\\t'"], highlight=correlation, width=1240)

        term.capture("04_idempotent_retry", "retrying the same request", [
            f"curl -s -i -X POST http://localhost:8001/orders -H 'Content-Type: application/json' "
            f"-H 'Idempotency-Key: {key}' -d '{ORDER}' | grep -E -i '^HTTP|^idempotent|order_id' "
            "| cut -c1-120",
            f"curl -s 'http://localhost:8002/notifications?order_id={order_id}' | jq length"])

        print("resilience test: notification-service stopped ...")
        sh("docker compose stop notification-service")
        out = term.capture("05a_notification_down", "Notification service stopped: checkout still works", [
            "docker compose stop notification-service",
            "curl -s -o /dev/null -w 'HTTP %{http_code}\\n' -X POST http://localhost:8001/orders "
            f"-H 'Content-Type: application/json' -H 'Idempotency-Key: outage-test-0001' -d '{ORDER}'",
            "sleep 3; docker compose exec -T rabbitmq rabbitmqctl list_queues --quiet name messages_ready "
            "| column -t"])
        assert "HTTP 201" in out, out
        rabbitmq_queues(browser, "05b_rabbitmq_message_waiting")
        term.capture("05c_notification_back", "Notification service restarted: the waiting event is consumed", [
            "docker compose start notification-service",
            "sleep 6; docker compose exec -T rabbitmq rabbitmqctl list_queues --quiet name messages_ready "
            "| column -t",
            "curl -s http://localhost:8002/notifications | jq -r '.[] | [.order_id, .status, .summary] | @tsv'"])
        browser.close()
    (EVIDENCE / "demo.json").write_text(json.dumps({"order_id": order_id, "correlation_id": correlation},
                                                   indent=2) + "\n")


def ci() -> None:
    run = json.loads(sh(f"gh run list -R {REPO} --limit 1 --json databaseId,conclusion,headSha"))[0]
    if run["conclusion"] != "success":
        raise SystemExit(f"latest run is {run['conclusion']}, not success")
    url = f"https://github.com/{REPO}/actions/runs/{run['databaseId']}"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(device_scale_factor=2, viewport={"width": 1400, "height": 860})
        page.goto(url)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        page.screenshot(path=str(SHOTS / "06_ci_passing_run.png"))
        browser.close()
    (EVIDENCE / "ci_run.json").write_text(json.dumps({**run, "url": url}, indent=2) + "\n")
    print(f"  saved 06_ci_passing_run ({url})")


if __name__ == "__main__":
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    {"demo": demo, "ci": ci}[sys.argv[1] if len(sys.argv) > 1 else "demo"]()
