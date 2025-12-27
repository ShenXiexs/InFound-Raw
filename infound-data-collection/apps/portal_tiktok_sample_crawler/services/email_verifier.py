"""Gmail verification code helper (HTML/text parsing, retries, connection reuse)."""

from __future__ import annotations

import email
import html
import imaplib
import logging
import re
import socket
import time
from email.header import decode_header
from typing import Optional

logger = logging.getLogger(__name__)


class GmailVerificationCode:
    """Fetch TikTok login verification codes."""

    def __init__(self, username: str, app_password: str):
        self.gmail_username = username
        self.gmail_app_password = app_password
        self._mail_connection: Optional[imaplib.IMAP4_SSL] = None
        self._last_activity = 0.0
        self._connection_lifetime = 3600  # seconds

    # ---------------------- Connection management ---------------------- #
    def connect_gmail(self, timeout: int = 10, max_retries: int = 5) -> Optional[imaplib.IMAP4_SSL]:
        servers = [("imap.gmail.com", 993)]
        for server_host, server_port in servers:
            for retry in range(max_retries):
                try:
                    logger.info("Connecting to %s:%s (attempt %s/%s)", server_host, server_port, retry + 1, max_retries)
                    original_timeout = socket.getdefaulttimeout()
                    socket.setdefaulttimeout(timeout)
                    mail = imaplib.IMAP4_SSL(server_host, server_port)
                    mail.login(self.gmail_username, self.gmail_app_password)
                    socket.setdefaulttimeout(original_timeout)
                    logger.info("Connected to Gmail: %s via %s", self.gmail_username, server_host)
                    return mail
                except (socket.timeout, socket.error) as exc:
                    logger.warning("Network error (%s): %s", server_host, exc)
                    if retry < max_retries - 1:
                        time.sleep((retry + 1) * 2)
                except imaplib.IMAP4.error as exc:
                    msg = str(exc)
                    if "AUTHENTICATIONFAILED" in msg or "Too many login failures" in msg:
                        logger.error("Authentication failed or too many login attempts: %s", msg)
                        return None
                    logger.warning("IMAP error (%s): %s", server_host, msg)
                    if retry < max_retries - 1:
                        time.sleep(2)
                except Exception as exc:
                    logger.error("Unknown error (%s): %s", server_host, exc)
                    if retry < max_retries - 1:
                        time.sleep(2)
        logger.error("All connection attempts failed")
        return None

    def safe_logout(self, mail: Optional[imaplib.IMAP4_SSL]) -> None:
        if mail:
            try:
                mail.noop()
                mail.logout()
                logger.info("Gmail connection closed safely")
            except Exception:
                try:
                    mail.sock.close()
                except Exception:
                    pass

    def get_connection(self, force_new: bool = False) -> Optional[imaplib.IMAP4_SSL]:
        now = time.time()
        need_new = (
                force_new
                or self._mail_connection is None
                or (now - self._last_activity) > self._connection_lifetime
        )
        if need_new:
            if self._mail_connection:
                self.safe_logout(self._mail_connection)
            self._mail_connection = self.connect_gmail(timeout=15, max_retries=3)
        elif self._mail_connection:
            try:
                self._mail_connection.noop()
            except Exception:
                self._mail_connection = self.connect_gmail(timeout=15, max_retries=3)
        self._last_activity = now
        return self._mail_connection

    # ---------------------- Email parsing ---------------------- #
    @staticmethod
    def decode_email_subject(msg: email.message.Message) -> str:
        subject = "No subject"
        if msg["Subject"]:
            try:
                parts = decode_header(msg["Subject"])
                subject = ""
                for part, encoding in parts:
                    if isinstance(part, bytes):
                        subject += part.decode(encoding or "utf-8", errors="ignore")
                    else:
                        subject += part
            except Exception:
                subject = str(msg["Subject"])
        return subject

    def get_email_content(self, msg: email.message.Message) -> str:
        content = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype in ["text/plain", "text/html"]:
                    payload = part.get_payload(decode=True)
                    if payload:
                        try:
                            content += payload.decode("utf-8", errors="ignore") + "\n"
                        except Exception:
                            continue
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                try:
                    content = payload.decode("utf-8", errors="ignore")
                except Exception:
                    content = ""
        return content

    def extract_verification_code(self, text: str) -> Optional[str]:
        if not text:
            return None
        if "<html" in text.lower() or "<!doctype" in text.lower():
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = html.unescape(text)
        cleaned = text.replace("\u200b", "").replace("\r", "").strip()

        patterns = [
            r"enter\s+this\s+code\s+in\s+TikTok\s+Shop\s+Partner\s+Center\s*:\s*([A-Z0-9]{6})",
            r"enter\s+this\s+code.*?:\s*([A-Z0-9]{6})",
            r"verification\s+code.*?:\s*([A-Z0-9]{6})",
            r"([A-Z0-9]{6})(?:\s*$|\s*[^\w])",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, cleaned, re.MULTILINE | re.DOTALL | re.IGNORECASE)
            if matches:
                code = matches[-1].strip().upper()
                if len(code) == 6 and code.isalnum():
                    logger.info("Verification code matched pattern: %s", code)
                    return code

        all_codes = re.findall(r"\b([A-Z0-9]{6})\b", cleaned)
        if all_codes:
            stopwords = {
                "PUBLIC", "PRIVATE", "NOTICE", "PLEASE", "THANKS", "REGARD",
                "TIKTOK", "PARTNER", "CENTER", "SECURE", "SIGNIN", "SIGNUP",
                "EXPIRE", "EXPIRED", "VALID", "INVALID",
            }
            valid = [code.upper() for code in all_codes if code.upper() not in stopwords]
            if valid:
                logger.info("Verification code found by search: %s", valid[-1])
                return valid[-1]
        logger.warning("Failed to extract verification code")
        return None

    # ---------------------- Main flow ---------------------- #
    def get_latest_verification_code_from_email(self, mail: imaplib.IMAP4_SSL) -> Optional[str]:
        try:
            mail.noop()
            mail.select("inbox")
            status, messages = mail.search(None, '(OR SUBJECT "TikTok Shop Partner Center" BODY "TikTok Shop Partner Center")')
            if status != "OK":
                status, messages = mail.search(None, "ALL")
            if status != "OK":
                logger.error("Email search failed")
                return None
            email_ids = messages[0].split()
            if not email_ids or email_ids == [b""]:
                logger.warning("Inbox empty or no matching email found")
                return None
            latest_id = email_ids[-1]
            status, msg_data = mail.fetch(latest_id, "(RFC822)")
            if status != "OK":
                logger.error("Failed to fetch email")
                return None
            msg = email.message_from_bytes(msg_data[0][1])
            subject = self.decode_email_subject(msg)
            content = self.get_email_content(msg)
            code = self.extract_verification_code(content) or self.extract_verification_code(subject)
            return code
        except Exception as exc:
            logger.error("Error while fetching email: %s", exc, exc_info=True)
            return None

    def get_verification_code(
            self,
            max_attempts: int = 4,
            check_interval: int = 10,
            connection_timeout: int = 80,
    ) -> Optional[str]:
        logger.info("Fetching Gmail verification code...")
        attempt = 0
        previous_code: Optional[str] = None
        consecutive_failures = 0

        while attempt < max_attempts:
            attempt += 1
            logger.info("Check attempt %s/%s...", attempt, max_attempts)
            mail = self.get_connection(force_new=(consecutive_failures >= 2))
            if not mail:
                consecutive_failures += 1
                time.sleep(check_interval)
                continue
            try:
                code = self.get_latest_verification_code_from_email(mail)
                consecutive_failures = 0
                if code:
                    if previous_code == code:
                        logger.info("✓ Code confirmed: %s", code)
                        return code
                    previous_code = code
                    logger.info("Code changed; waiting for next confirmation...")
                else:
                    previous_code = None
            except Exception as exc:
                consecutive_failures += 1
                logger.error("Error while fetching email: %s", exc)
                self._mail_connection = None
            if attempt < max_attempts:
                time.sleep(check_interval)

        logger.error("Verification code timeout (attempts: %s)", max_attempts)
        return None
