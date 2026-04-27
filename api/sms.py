"""
SMS service for sending and receiving messages via Twilio.
"""
import structlog
from typing import Optional
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from api.config import settings

logger = structlog.get_logger()


class SMSService:
    def __init__(self):
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            logger.warning("twilio_credentials_not_configured")
            self.client = None
        else:
            self.client = Client(
                settings.twilio_account_sid,
                settings.twilio_auth_token
            )
    
    def send_message(
        self,
        to_phone: str,
        body: str,
    ) -> Optional[str]:
        if not self.client:
            logger.error("twilio_client_not_initialized", to_phone=to_phone)
            return None
        
        try:
            message = self.client.messages.create(
                body=body,
                from_=settings.twilio_phone_number,
                to=to_phone
            )
            
            logger.info(
                "sms_sent",
                to_phone=to_phone,
                message_sid=message.sid,
                status=message.status
            )
            
            return message.sid
            
        except TwilioRestException as e:
            logger.error(
                "sms_send_failed",
                to_phone=to_phone,
                error_code=e.code,
                error_message=e.msg
            )
            return None
        except Exception as e:
            logger.error(
                "sms_send_unexpected_error",
                to_phone=to_phone,
                error=str(e)
            )
            return None


# Global SMS service instance
sms_service = SMSService()
