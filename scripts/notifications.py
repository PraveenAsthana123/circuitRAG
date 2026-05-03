"""Notifications — Tier 5 #5.13.

Multi-channel notification adapter for the autonomous-fix-bot.
Slack / email / WhatsApp / generic webhook. Channels enabled via
env vars; each channel is a no-op when its env vars are missing
(daemon never crashes from a missing channel).

WHY THIS MODULE EXISTS
=======================

The daemon emits events to stdout (`daemon:applied`, `daemon:rejected`,
etc.) which are tailed via `.loop/daemon_cron.log`. That works for a
single operator at a single terminal. Multi-operator / on-call /
production setups need PUSH notifications instead of pull-tails.

This module is the push layer. NOT in the daemon hot path — daemon
calls dispatch() opportunistically (after apply / after escalation /
on apply-rate drift). Channel failures NEVER block the daemon.

§42 / §54 BOUNDARIES
====================

  - No secrets in code. All credentials from env vars.
  - Notification body MUST NOT contain operator PII unless explicitly
    set by the daemon (the schema's `body` field allows it but the
    daemon's notification helpers will redact by default).
  - Notifications are FIRE-AND-FORGET — channel failure does not
    fail the daemon's parent operation. Logged, then continued.

CHANNELS
========

  slack       — Slack incoming webhook URL via $SLACK_WEBHOOK_URL
  email       — Gmail SMTP via $EMAIL_SMTP_USER + $EMAIL_SMTP_APP_PASSWORD
                + $EMAIL_TO (comma-separated)
  whatsapp    — Twilio WhatsApp via $TWILIO_ACCOUNT_SID +
                $TWILIO_AUTH_TOKEN + $TWILIO_WHATSAPP_FROM + $WHATSAPP_TO
  webhook     — generic POST to $GENERIC_WEBHOOK_URL

USAGE
=====

  from notifications import Notification, dispatch
  dispatch(Notification(
      channel="slack",
      severity="info",
      title="Daemon applied 3 fixes",
      body="UP035 / E702 / F401 — see .loop/daemon_cron.log",
      link="https://github.com/PraveenAsthana123/repo/commits/main",
  ))

Drilled by mcp/tests/drill_notifications.py.
"""

from __future__ import annotations

import json
import os
import smtplib
import subprocess
from dataclasses import dataclass
from email.mime.text import MIMEText
from typing import ClassVar, Literal

from pydantic import BaseModel, Field, ValidationError


Channel = Literal["slack", "email", "whatsapp", "webhook"]
Severity = Literal["info", "warn", "error", "critical"]

ALL_CHANNELS: tuple[Channel, ...] = ("slack", "email", "whatsapp", "webhook")


class Notification(BaseModel):
    """Wire format. Same shape across channels; adapters render per-channel."""

    channel: Channel
    severity: Severity
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)
    link: str | None = Field(default=None, max_length=2000)

    model_config: ClassVar[dict] = {"extra": "forbid"}


@dataclass(frozen=True)
class DispatchResult:
    """Outcome of a single channel send. Aggregated by dispatch()."""

    channel: str
    sent: bool
    error: str | None
    skipped_reason: str | None  # "env vars missing" / etc.


# ---------------------------------------------------------------------
# Adapters — one per channel
# ---------------------------------------------------------------------

def _send_slack(notification: Notification) -> DispatchResult:
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return DispatchResult("slack", sent=False, error=None,
                              skipped_reason="SLACK_WEBHOOK_URL not set")
    color_map = {"info": "#36a64f", "warn": "#FFA500",
                 "error": "#FF0000", "critical": "#8B0000"}
    payload = {
        "attachments": [{
            "color": color_map.get(notification.severity, "#808080"),
            "title": notification.title,
            "text": notification.body,
            "fields": [{"title": "severity", "value": notification.severity, "short": True}],
        }],
    }
    if notification.link:
        payload["attachments"][0]["title_link"] = notification.link
    try:
        proc = subprocess.run(
            ["curl", "-s", "--max-time", "10", "-X", "POST",
             webhook_url, "-H", "Content-Type: application/json",
             "-d", json.dumps(payload)],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode != 0:
            return DispatchResult("slack", sent=False,
                                  error=f"curl exit {proc.returncode}: {proc.stderr.strip()[:120]}",
                                  skipped_reason=None)
        if proc.stdout.strip().lower() not in ("ok", ""):
            return DispatchResult("slack", sent=False,
                                  error=f"slack response: {proc.stdout.strip()[:120]}",
                                  skipped_reason=None)
        return DispatchResult("slack", sent=True, error=None, skipped_reason=None)
    except subprocess.TimeoutExpired:
        return DispatchResult("slack", sent=False,
                              error="curl timed out (>15s)",
                              skipped_reason=None)


def _send_email(notification: Notification) -> DispatchResult:
    smtp_user = os.environ.get("EMAIL_SMTP_USER", "").strip()
    smtp_pass = os.environ.get("EMAIL_SMTP_APP_PASSWORD", "").strip()
    to_addrs = os.environ.get("EMAIL_TO", "").strip()
    if not smtp_user or not smtp_pass or not to_addrs:
        return DispatchResult("email", sent=False, error=None,
                              skipped_reason="EMAIL_SMTP_USER/PASSWORD/TO not all set")
    smtp_host = os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("EMAIL_SMTP_PORT", "587"))
    body_lines = [notification.body]
    if notification.link:
        body_lines.append("")
        body_lines.append(f"Link: {notification.link}")
    body_lines.append("")
    body_lines.append(f"Severity: {notification.severity}")
    body_lines.append("(Sent by autonomous-fix-bot — do not reply)")
    msg = MIMEText("\n".join(body_lines))
    msg["Subject"] = f"[{notification.severity.upper()}] {notification.title[:160]}"
    msg["From"] = smtp_user
    msg["To"] = to_addrs
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        return DispatchResult("email", sent=True, error=None, skipped_reason=None)
    except (smtplib.SMTPException, OSError, TimeoutError) as exc:
        return DispatchResult("email", sent=False,
                              error=f"{type(exc).__name__}: {exc}",
                              skipped_reason=None)


def _send_whatsapp(notification: Notification) -> DispatchResult:
    sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    from_num = os.environ.get("TWILIO_WHATSAPP_FROM", "").strip()
    to_num = os.environ.get("WHATSAPP_TO", "").strip()
    if not sid or not token or not from_num or not to_num:
        return DispatchResult("whatsapp", sent=False, error=None,
                              skipped_reason="TWILIO_* / WHATSAPP_TO not all set")
    # Twilio WhatsApp API endpoint
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    short_body = f"{notification.severity.upper()} {notification.title}\n{notification.body[:1400]}"
    if notification.link:
        short_body += f"\n{notification.link}"
    try:
        proc = subprocess.run(
            ["curl", "-s", "--max-time", "15",
             "-X", "POST", url,
             "-u", f"{sid}:{token}",
             "--data-urlencode", f"From={from_num}",
             "--data-urlencode", f"To={to_num}",
             "--data-urlencode", f"Body={short_body[:1500]}"],
            capture_output=True, text=True, timeout=20,
        )
        if proc.returncode != 0:
            return DispatchResult("whatsapp", sent=False,
                                  error=f"curl exit {proc.returncode}",
                                  skipped_reason=None)
        # Twilio returns JSON with sid on success; "code" on error
        try:
            body = json.loads(proc.stdout) if proc.stdout else {}
        except json.JSONDecodeError:
            return DispatchResult("whatsapp", sent=False,
                                  error=f"non-JSON response from twilio",
                                  skipped_reason=None)
        if "sid" in body:
            return DispatchResult("whatsapp", sent=True, error=None, skipped_reason=None)
        return DispatchResult("whatsapp", sent=False,
                              error=f"twilio: code={body.get('code')} msg={body.get('message', '')[:120]}",
                              skipped_reason=None)
    except subprocess.TimeoutExpired:
        return DispatchResult("whatsapp", sent=False,
                              error="twilio call timed out",
                              skipped_reason=None)


def _send_webhook(notification: Notification) -> DispatchResult:
    url = os.environ.get("GENERIC_WEBHOOK_URL", "").strip()
    if not url:
        return DispatchResult("webhook", sent=False, error=None,
                              skipped_reason="GENERIC_WEBHOOK_URL not set")
    payload = notification.model_dump(mode="json")
    try:
        proc = subprocess.run(
            ["curl", "-s", "--max-time", "10", "-X", "POST",
             url, "-H", "Content-Type: application/json",
             "-d", json.dumps(payload)],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode != 0:
            return DispatchResult("webhook", sent=False,
                                  error=f"curl exit {proc.returncode}",
                                  skipped_reason=None)
        return DispatchResult("webhook", sent=True, error=None, skipped_reason=None)
    except subprocess.TimeoutExpired:
        return DispatchResult("webhook", sent=False,
                              error="webhook timed out",
                              skipped_reason=None)


_ADAPTERS = {
    "slack": _send_slack,
    "email": _send_email,
    "whatsapp": _send_whatsapp,
    "webhook": _send_webhook,
}


def dispatch(notification: Notification) -> DispatchResult:
    """Send a notification through ONE channel (notification.channel)."""
    adapter = _ADAPTERS.get(notification.channel)
    if adapter is None:
        return DispatchResult(notification.channel, sent=False,
                              error=f"unknown channel: {notification.channel}",
                              skipped_reason=None)
    return adapter(notification)


def fan_out(*, severity: Severity, title: str, body: str, link: str | None = None,
            channels: tuple[Channel, ...] = ALL_CHANNELS) -> list[DispatchResult]:
    """Send the same notification to multiple channels.

    Channels with missing env vars are skipped silently (skipped_reason
    populated; sent=False; error=None). Channels that fail at send time
    return error populated. Either way: this function NEVER raises.
    """
    results = []
    for ch in channels:
        try:
            n = Notification(channel=ch, severity=severity, title=title, body=body, link=link)
            results.append(dispatch(n))
        except ValidationError as ve:
            results.append(DispatchResult(ch, sent=False,
                                          error=f"schema invalid: {ve.errors()[:1]}",
                                          skipped_reason=None))
    return results


def main() -> int:
    """CLI: send a test notification through all enabled channels."""
    import argparse
    parser = argparse.ArgumentParser(prog="notifications.py")
    parser.add_argument("--severity", default="info",
                        choices=["info", "warn", "error", "critical"])
    parser.add_argument("--title", default="autonomous-fix-bot test notification")
    parser.add_argument("--body", default="If you see this, notifications are wired correctly.")
    parser.add_argument("--link", default=None)
    parser.add_argument("--channels", default=",".join(ALL_CHANNELS),
                        help="Comma-separated subset of: slack,email,whatsapp,webhook")
    args = parser.parse_args()
    channels = tuple(c.strip() for c in args.channels.split(",") if c.strip())
    results = fan_out(
        severity=args.severity, title=args.title, body=args.body,
        link=args.link, channels=channels,  # type: ignore[arg-type]
    )
    print(f"=== Dispatch results ({len(results)} channels) ===")
    for r in results:
        if r.sent:
            print(f"  ✓ {r.channel:<10} sent")
        elif r.skipped_reason:
            print(f"  ⏸ {r.channel:<10} skipped: {r.skipped_reason}")
        else:
            print(f"  ✗ {r.channel:<10} failed: {r.error}")
    return 0 if any(r.sent for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
