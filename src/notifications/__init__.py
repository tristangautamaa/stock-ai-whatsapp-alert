from ..config import Settings
from .whatsapp_cloud import WhatsAppCloudNotifier
from .twilio_whatsapp import TwilioWhatsAppNotifier


def get_notifier(settings: Settings) -> WhatsAppCloudNotifier | TwilioWhatsAppNotifier:
    if settings.whatsapp_provider == "twilio":
        return TwilioWhatsAppNotifier(settings)
    return WhatsAppCloudNotifier(settings)
