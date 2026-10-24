"""
Notification service: sends SMS via Twilio when configured,
otherwise falls back to logging the message.
"""
import os
import logging

try:
    from twilio.rest import Client
    TWILIO_AVAILABLE = True
except Exception:
    TWILIO_AVAILABLE = False

LOG = logging.getLogger('notification_service')


def send_sms(to_number: str, message: str) -> bool:
    """Send SMS to `to_number` with `message`.

    Uses Twilio when `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` are set.
    Falls back to logging and returns False when delivery is not configured.
    """
    to_number = (to_number or '').strip()
    if not to_number:
        LOG.warning('No phone number provided for SMS')
        return False

    sid = os.getenv('TWILIO_ACCOUNT_SID')
    token = os.getenv('TWILIO_AUTH_TOKEN')
    from_number = os.getenv('TWILIO_FROM_NUMBER')

    if sid and token and from_number and TWILIO_AVAILABLE:
        try:
            client = Client(sid, token)
            client.messages.create(body=message, from_=from_number, to=to_number)
            LOG.info('SMS sent to %s via Twilio', to_number)
            return True
        except Exception as e:
            LOG.error('Twilio SMS send failed: %s', e)
            return False

    # Fallback: log the message (useful for local testing)
    LOG.info('SMS (logged) -> %s: %s', to_number, message)
    return False
