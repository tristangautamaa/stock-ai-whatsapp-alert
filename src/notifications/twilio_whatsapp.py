from loguru import logger
from ..config import Settings


class TwilioWhatsAppNotifier:
    """Twilio WhatsApp sandbox sender — useful for quick dev testing.

    To enable: set WHATSAPP_PROVIDER=twilio in .env and fill Twilio credentials.
    Sandbox setup: https://www.twilio.com/docs/whatsapp/sandbox
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, message: str, recipient: str | None = None) -> bool:
        to = recipient or self.settings.twilio_whatsapp_to

        if self.settings.dry_run:
            logger.info("[DRY_RUN] Twilio WhatsApp — message NOT sent")
            _print_preview(to, message)
            return True

        if not self.settings.has_whatsapp_twilio:
            logger.error("Twilio credentials incomplete. Check .env")
            return False

        try:
            from twilio.rest import Client
            client = Client(self.settings.twilio_account_sid, self.settings.twilio_auth_token)
            msg = client.messages.create(
                from_=f"whatsapp:{self.settings.twilio_whatsapp_from}",
                to=f"whatsapp:{to}",
                body=message,
            )
            logger.info(f"Twilio WhatsApp sent — sid={msg.sid}")
            return True
        except ImportError:
            logger.error("twilio package not installed. pip install twilio")
            return False
        except Exception as e:
            logger.error(f"Twilio send failed: {e}")
            return False


def _print_preview(to: str, message: str) -> None:
    sep = "=" * 60
    print(f"\n{sep}\n[DRY RUN / TWILIO] TO: {to}\n{sep}\n{message}\n{sep}\n")
