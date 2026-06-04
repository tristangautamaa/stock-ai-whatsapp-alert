import httpx
from loguru import logger
from ..config import Settings


class WhatsAppCloudNotifier:
    """Meta WhatsApp Cloud API sender.

    Reads credentials from Settings. Supports dry-run mode (prints instead of sending).
    Docs: https://developers.facebook.com/docs/whatsapp/cloud-api
    """

    _GRAPH_BASE = "https://graph.facebook.com"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._url = (
            f"{self._GRAPH_BASE}/{settings.whatsapp_api_version}"
            f"/{settings.whatsapp_phone_number_id}/messages"
        )
        self._headers = {
            "Authorization": f"Bearer {settings.whatsapp_cloud_api_token}",
            "Content-Type": "application/json",
        }

    def send(self, message: str, recipient: str | None = None) -> bool:
        to = recipient or self.settings.whatsapp_recipient_number

        if self.settings.dry_run:
            logger.info("[DRY_RUN] WhatsApp Cloud API — message NOT sent")
            _print_preview(to, message)
            return True

        if not self.settings.has_whatsapp_meta:
            logger.error("WhatsApp Cloud API credentials incomplete. Check .env")
            return False

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": message, "preview_url": False},
        }

        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(self._url, json=payload, headers=self._headers)
            resp.raise_for_status()
            data = resp.json()
            msg_id = data.get("messages", [{}])[0].get("id", "?")
            logger.info(f"WhatsApp sent to {to} — message_id={msg_id}")
            return True
        except httpx.HTTPStatusError as e:
            logger.error(f"WhatsApp Cloud API {e.response.status_code}: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"WhatsApp Cloud send failed: {e}")
            return False


def _print_preview(to: str, message: str) -> None:
    sep = "=" * 60
    print(f"\n{sep}\n[DRY RUN] TO: {to}\n{sep}\n{message}\n{sep}\n")
