"""Reusable TAP login flow built on Playwright."""

import logging
import time
import sys
import os
import csv
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any
from playwright.sync_api import sync_playwright

# Ensure absolute imports resolve when running as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.email_code import GmailVerificationCode  # noqa: E402
from utils.credentials import get_default_account_from_env, MissingDefaultAccountError  # noqa: E402

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Login:
    """Perform partner portal login and expose simple helpers."""

    def __init__(self, account_info=None):
        if account_info:
            self.login_email = account_info.get('login_email')
            self.login_password = account_info.get('login_password')
            self.gmail_username = account_info.get('gmail_username')
            self.gmail_app_password = account_info.get('gmail_app_password')
            self.account_name = account_info.get('name', 'Unknown')
            self.account_id = account_info.get('id', -1)
            logger.info(f"Using account: {self.account_name} ({self.login_email})")
        else:
            try:
                fallback = get_default_account_from_env()
            except MissingDefaultAccountError as exc:
                raise MissingDefaultAccountError(
                    "Provide account_info or configure DEFAULT_* environment variables."
                ) from exc

            self.login_email = fallback['login_email']
            self.login_password = fallback['login_password']
            self.gmail_username = fallback['gmail_username']
            self.gmail_app_password = fallback['gmail_app_password']
            self.account_name = fallback.get('name', 'Default Account')
            self.account_id = fallback.get('id', -1)
            logger.warning("Account info not provided; using fallback credentials from the environment.")

        # Gmail verification helper
        self.gmail_verifier = GmailVerificationCode(
            username=self.gmail_username,
            app_password=self.gmail_app_password
        )

        self.browser = None
        self.context = None
        self.page = None

    def delay(self, seconds: float):
        """Basic sleep helper."""
        time.sleep(seconds)

    def login(self, page) -> bool:
        """Log in to the TikTok Shop partner portal with retries."""
        max_retries = 5
        for i in range(max_retries):
            logger.info(f"Starting login attempt {i + 1}/{max_retries} ...")
            try:
                page.goto(
                    "https://partner-sso.tiktok.com/account/login?from=ttspc_logout&redirectURL=%2F%2Fpartner.tiktokshop.com%2Fhome&lang=en",
                    wait_until="networkidle",
                )

                logger.info("Switching to email login mode...")
                email_login_btn = page.get_by_text("Log in with code").first
                email_login_btn.click()

                logger.info(f"Filling email field with {self.login_email}")
                page.fill('#email input', self.login_email)

                try:
                    send_code_btn = page.locator('div[starling-key="profile_edit_userinfo_send_code"]').first
                    send_code_btn.wait_for(state="visible", timeout=5000)
                    send_code_btn.click()
                    logger.info("Send code button clicked")
                except Exception as exc:
                    logger.error(f"Failed to click Send code: {exc}")

                logger.info("Waiting for Gmail verification code...")
                verification_code = self.gmail_verifier.get_verification_code()
                if not verification_code:
                    logger.error("Verification code could not be retrieved")
                    continue

                logger.info(f"Verification code received: {verification_code}")
                page.fill('#emailCode_input', verification_code)

                login_btn = page.locator('button[starling-key="account_login_btn_loginform_login_text"]').first
                login_btn.click()

                if "partner.tiktokshop.com" in page.url:
                    logger.info("Login successful")
                    return True

                logger.error("Login failed; unexpected redirect state")
                time.sleep(3)

            except Exception as exc:  # noqa: BLE001
                logger.error(f"Login flow failed: {exc}")
                if i < max_retries - 1:
                    logger.warning("Retrying in 3 seconds...")
                    time.sleep(3)

        logger.error(f"Login failed after {max_retries} attempts")
        return False

    def check_welcome_page(self, page) -> bool:
        """Return True if the welcome banner was detected."""
        logger.info("Checking whether the welcome page is rendered...")
        time.sleep(3)

        try:
            page.wait_for_selector('text=Welcome to TikTok Shop Partner Center', timeout=20000)
            logger.info("Welcome text detected")
            return True
        except Exception:
            logger.warning("Welcome page detection failed")
            return False

    def run(self) -> bool:
        """Execute the login workflow and clean up Playwright objects."""
        logger.info("=" * 50)
        logger.info("TikTok Chat History Crawler - Login")
        logger.info("=" * 50)

        with sync_playwright() as playwright:
            try:
                self.playwright_context_active = True
                self.browser = playwright.chromium.launch(headless=True, timeout=60000)
                self.context = self.browser.new_context(viewport={'width': 1920, 'height': 1080})
                self.context.set_default_timeout(60000)
                self.page = self.context.new_page()

                max_login_attempts = 3
                for attempt in range(1, max_login_attempts + 1):
                    logger.info(f"=== Login attempt {attempt}/{max_login_attempts} ===")
                    if not self.login(self.page):
                        logger.error("Login attempt failed")
                    else:
                        if self.check_welcome_page(self.page):
                            logger.info("Welcome page reached successfully")
                            break

                        logger.warning("Welcome page mismatch; retrying login flow")

                    if attempt < max_login_attempts:
                        try:
                            self.page.goto("https://partner-sso.tiktok.com/account/login", wait_until="networkidle")
                            self.delay(3)
                        except Exception:
                            pass
                    else:
                        logger.error("Unable to reach welcome page after maximum attempts")
                        return False

                return True

            except Exception as exc:  # noqa: BLE001
                logger.error(f"Fatal error during login run: {exc}")
                return False
            finally:
                if self.page:
                    self.page.close()
                if self.context:
                    self.context.close()
                if self.browser:
                    self.browser.close()
                logger.info("Browser resources released")


if __name__ == '__main__':
    Login().run()
