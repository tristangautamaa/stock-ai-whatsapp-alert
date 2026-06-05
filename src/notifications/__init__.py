from ..config import Settings
from .whatsapp_cloud import WhatsAppCloudNotifier
from .twilio_whatsapp import TwilioWhatsAppNotifier
from .pywhatkit_whatsapp import PyWhatKitNotifier
from .email_notifier import EmailNotifier


def get_notifier(settings: Settings) -> WhatsAppCloudNotifier | TwilioWhatsAppNotifier | PyWhatKitNotifier | EmailNotifier:
    if settings.whatsapp_provider == "twilio":
        return TwilioWhatsAppNotifier(settings)
    if settings.whatsapp_provider == "pywhatkit":
        return PyWhatKitNotifier(settings)
    if settings.whatsapp_provider == "email":
        return EmailNotifier(settings)
    return WhatsAppCloudNotifier(settings)
