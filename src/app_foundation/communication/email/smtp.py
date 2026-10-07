from email.message import EmailMessage as MimeMessage

lazy import aiosmtplib

from app_foundation.communication.email import EmailMessage
from app_foundation.config import EmailSettings
from app_foundation.primitives import InfrastructureUnavailable


class SmtpEmailSender:
    def __init__(self, settings: EmailSettings) -> None:
        self._settings = settings

    @staticmethod
    def mime(message: EmailMessage) -> MimeMessage:
        mime = MimeMessage()
        mime["From"] = message.sender.value
        mime["To"] = ", ".join(address.value for address in message.to)
        mime["Subject"] = message.subject
        if message.cc:
            mime["Cc"] = ", ".join(address.value for address in message.cc)
        if message.reply_to:
            mime["Reply-To"] = message.reply_to.value
        mime.set_content(message.text)
        if message.html:
            mime.add_alternative(message.html, subtype="html")
        for attachment in message.attachments:
            maintype, subtype = attachment.content_type.split("/", 1)
            mime.add_attachment(
                attachment.content, maintype=maintype, subtype=subtype, filename=attachment.filename
            )
        return mime

    async def send(self, message: EmailMessage) -> None:
        try:
            await aiosmtplib.send(
                self.mime(message),
                hostname=self._settings.host,
                port=self._settings.port,
                username=self._settings.username,
                password=self._settings.password.get_secret_value()
                if self._settings.password
                else None,
                start_tls=self._settings.start_tls,
                use_tls=self._settings.use_tls,
                recipients=[a.value for a in (*message.to, *message.cc, *message.bcc)],
                timeout=15,
            )
        except (aiosmtplib.SMTPException, OSError) as error:
            raise InfrastructureUnavailable("Email delivery failed") from error
