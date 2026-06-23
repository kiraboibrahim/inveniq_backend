import logging
from abc import ABC, abstractmethod

from django.conf import settings

logger = logging.getLogger(__name__)


class SmsGateway(ABC):
    @abstractmethod
    def send_sms(self, phone: str, message: str) -> bool:
        pass


class ConsoleSmsGateway(SmsGateway):
    def send_sms(self, phone: str, message: str) -> bool:
        logger.info(f"[SMS Console Gateway] Sending message to {phone}: {message}")
        print(f"[SMS GATEWAY] To: {phone} | Msg: {message}")
        return True


class AfricasTalkingGateway(SmsGateway):
    def __init__(self, username, api_key):
        self.username = username
        self.api_key = api_key

    def send_sms(self, phone: str, message: str) -> bool:
        try:
            import africastalking

            africastalking.initialize(self.username, self.api_key)
            sms = africastalking.SMS
            response = sms.send(message, [phone])
            logger.info(f"Africa's Talking SMS response: {response}")
            return True
        except Exception as e:
            logger.error(f"Africa's Talking SMS failed: {e}")
            return False


class TwilioGateway(SmsGateway):
    def __init__(self, account_sid, auth_token, from_number):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number

    def send_sms(self, phone: str, message: str) -> bool:
        try:
            from twilio.rest import Client

            client = Client(self.account_sid, self.auth_token)
            message = client.messages.create(
                body=message, from_=self.from_number, to=phone
            )
            logger.info(f"Twilio SMS message SID: {message.sid}")
            return True
        except Exception as e:
            logger.error(f"Twilio SMS failed: {e}")
            return False


def get_sms_gateway() -> SmsGateway:
    # Read provider from settings, fallback to console logs for local dev/testing
    provider = getattr(settings, "SMS_PROVIDER", "console")
    if provider == "africastalking":
        return AfricasTalkingGateway(
            username=getattr(settings, "AFRICASTALKING_USERNAME", ""),
            api_key=getattr(settings, "AFRICASTALKING_API_KEY", ""),
        )
    elif provider == "twilio":
        return TwilioGateway(
            account_sid=getattr(settings, "TWILIO_ACCOUNT_SID", ""),
            auth_token=getattr(settings, "TWILIO_AUTH_TOKEN", ""),
            from_number=getattr(settings, "TWILIO_FROM_NUMBER", ""),
        )
    return ConsoleSmsGateway()


def send_sms(phone: str, message: str):
    gateway = get_sms_gateway()
    return gateway.send_sms(phone, message)
