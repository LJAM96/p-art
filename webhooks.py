"""Webhook notifications for P-Art."""

import json
import logging
import requests
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict

log = logging.getLogger("p-art")


@dataclass
class WebhookPayload:
    """Webhook notification payload."""
    event: str
    message: str
    timestamp: float
    details: Optional[Dict] = None


class WebhookNotifier:
    """Send webhook notifications for P-Art events."""

    def __init__(self, webhook_url: Optional[str] = None, enabled: bool = False):
        self.webhook_url = webhook_url
        self.enabled = enabled and bool(webhook_url)

    def send(self, event: str, message: str, details: Optional[Dict] = None):
        """Send a webhook notification."""
        if not self.enabled or not self.webhook_url:
            return

        import time
        payload = WebhookPayload(
            event=event,
            message=message,
            timestamp=time.time(),
            details=details or {}
        )

        try:
            # Support different webhook formats
            if "discord" in self.webhook_url.lower():
                self._send_discord(payload)
            elif "slack" in self.webhook_url.lower():
                self._send_slack(payload)
            else:
                self._send_generic(payload)
        except Exception as e:
            log.warning(f"Failed to send webhook notification: {e}")

    def _send_generic(self, payload: WebhookPayload):
        """Send generic JSON webhook."""
        response = requests.post(
            self.webhook_url,
            json=asdict(payload),
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        response.raise_for_status()

    def _send_discord(self, payload: WebhookPayload):
        """Send Discord webhook."""
        color_map = {
            "started": 0x3498db,  # Blue
            "completed": 0x2ecc71,  # Green
            "error": 0xe74c3c,  # Red
            "warning": 0xf39c12,  # Orange
        }

        embeds = [{
            "title": f"P-Art: {payload.event.title()}",
            "description": payload.message,
            "color": color_map.get(payload.event, 0x95a5a6),
            "timestamp": f"{payload.timestamp}",
            "footer": {"text": "P-Art Notification"}
        }]

        if payload.details:
            fields = []
            for key, value in payload.details.items():
                fields.append({
                    "name": key.replace("_", " ").title(),
                    "value": str(value),
                    "inline": True
                })
            embeds[0]["fields"] = fields

        response = requests.post(
            self.webhook_url,
            json={"embeds": embeds},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        response.raise_for_status()

    def _send_slack(self, payload: WebhookPayload):
        """Send Slack webhook."""
        color_map = {
            "started": "#3498db",
            "completed": "#2ecc71",
            "error": "#e74c3c",
            "warning": "#f39c12",
        }

        attachments = [{
            "color": color_map.get(payload.event, "#95a5a6"),
            "title": f"P-Art: {payload.event.title()}",
            "text": payload.message,
            "ts": int(payload.timestamp)
        }]

        if payload.details:
            fields = []
            for key, value in payload.details.items():
                fields.append({
                    "title": key.replace("_", " ").title(),
                    "value": str(value),
                    "short": True
                })
            attachments[0]["fields"] = fields

        response = requests.post(
            self.webhook_url,
            json={"attachments": attachments},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        response.raise_for_status()

    def notify_started(self, library_count: int, item_count: int):
        """Notify that processing has started."""
        self.send(
            "started",
            f"Started processing {item_count} items across {library_count} libraries",
            {"libraries": library_count, "items": item_count}
        )

    def notify_completed(self, processed: int, changed: int, duration: float):
        """Notify that processing has completed."""
        self.send(
            "completed",
            f"Completed processing {processed} items, {changed} changed in {duration:.1f}s",
            {
                "processed": processed,
                "changed": changed,
                "duration_seconds": round(duration, 1)
            }
        )

    def notify_error(self, error_message: str):
        """Notify that an error occurred."""
        self.send(
            "error",
            f"Error during processing: {error_message}",
            {"error": error_message}
        )
