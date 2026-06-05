import time
from loguru import logger
from ..config import Settings


class PyWhatKitNotifier:
    """Sends WhatsApp messages via pywhatkit (requires WhatsApp Web open and logged in)."""

    MAX_MSG_LEN = 4096

    def __init__(self, settings: Settings) -> None:
        self.recipient = settings.whatsapp_recipient
        self.dry_run = settings.dry_run

    def send(self, message: str, recipient: str | None = None) -> bool:
        phone = recipient or self.recipient
        if not phone:
            logger.error("WHATSAPP_RECIPIENT not set. Cannot send via pywhatkit.")
            return False

        if self.dry_run:
            logger.info("[DRY_RUN] pywhatkit — message NOT sent")
            _print_preview(phone, message)
            return True

        chunks = _split(message, self.MAX_MSG_LEN)
        try:
            import pywhatkit
            for i, chunk in enumerate(chunks):
                if i > 0:
                    time.sleep(5)
                pywhatkit.sendwhatmsg_instantly(phone, chunk, wait_time=15, tab_close=True)
                logger.info(f"pywhatkit sent chunk {i + 1}/{len(chunks)} to {phone}")
            return True
        except ImportError:
            logger.error("pywhatkit not installed. pip install pywhatkit==5.4")
            return False
        except Exception as e:
            logger.error(f"pywhatkit send failed: {e}")
            return False


def _split(text: str, max_len: int) -> list[str]:
    if len(text) <= max_len:
        return [text]
    return [text[:max_len], text[max_len:]]


def _print_preview(phone: str, message: str) -> None:
    sep = "=" * 60
    print(f"\n{sep}\n[DRY RUN / PYWHATKIT] TO: {phone}\n{sep}\n{message}\n{sep}\n")
