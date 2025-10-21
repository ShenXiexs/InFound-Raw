"""
TAP 登录流程，其他功能实现的基础
"""

import logging
import time
import sys
import os
import csv
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any
from playwright.sync_api import sync_playwright

# 确保路径正确
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.email_code import GmailVerificationCode

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Login: # 根据需求修改类名
    
    def __init__(self, account_info=None):
        # 支持传入账号信息
        if account_info:
            self.login_email = account_info.get('login_email')
            self.login_password = account_info.get('login_password')
            self.gmail_username = account_info.get('gmail_username')
            self.gmail_app_password = account_info.get('gmail_app_password')
            self.account_name = account_info.get('name', 'Unknown')
            self.account_id = account_info.get('id', -1)
            logger.info(f"使用账号: {self.account_name} ({self.login_email})")
        else:
            # 使用默认账号
            self.login_email = "tiktokshopinfoundtest@gmail.com"
            self.login_password = "fyvbyn-hyctu0-Rafqyp"
            self.gmail_username = "tiktokshopinfoundtest@gmail.com"
            self.gmail_app_password = "cfhlfedjqhfbbbhb"
            self.account_name = "默认账号"
            self.account_id = -1
            logger.warning("未提供账号信息,使用默认账号")

        # Gmail验证码配置
        self.gmail_verifier = GmailVerificationCode(
            username=self.gmail_username,
            app_password=self.gmail_app_password
        )
        
        self.browser = None
        self.context = None
        self.page = None
        
    
    def delay(self, seconds: float):
        """延迟"""
        time.sleep(seconds)
    
    def login(self, page) -> bool:
        """登录TikTok商家平台，最多重试5次"""
        max_retries = 5
        for i in range(max_retries):
            logger.info(f"开始登录流程（第 {i + 1} 次尝试）...")
            try:
                page.goto("https://partner-sso.tiktok.com/account/login?from=ttspc_logout&redirectURL=%2F%2Fpartner.tiktokshop.com%2Fhome&lang=en&local_id=localID_Portal_88574979_1758691471679&userID=51267627&is_through_login=1", wait_until="networkidle")
                
                logger.info("进入邮件登录模式...")
                email_login_btn = page.get_by_text("Log in with code").first
                email_login_btn.click()

                logger.info(f"输入邮箱: {self.login_email}")
                page.fill('#email input', self.login_email)
                
                try:
                    send_code_btn = page.locator('div[starling-key="profile_edit_userinfo_send_code"]').first
                    send_code_btn.wait_for(state="visible", timeout=5000)
                    send_code_btn.click()
                    logger.info("已点击 Send code 按钮")
                except Exception as e:
                    logger.error(f"点击 Send code 失败: {e}")

                logger.info("正在从Gmail获取验证码...")
                verification_code = self.gmail_verifier.get_verification_code()
                if not verification_code:
                    logger.error("验证码获取失败")
                    continue

                logger.info(f"成功获取验证码: {verification_code}")
                page.fill('#emailCode_input', verification_code)

                login_btn = page.locator('button[starling-key="account_login_btn_loginform_login_text"]').first
                login_btn.click()

                if "partner.tiktokshop.com" in page.url:
                    logger.info("登录成功")
                    return True
                else:
                    logger.error("登录失败，未跳转到正确页面")
                    time.sleep(3)
                    continue
            
            except Exception as e:
                logger.error(f"登录过程出错：{e}")
                if i < max_retries - 1:
                    logger.warning(f"第 {i + 1} 次尝试失败，等待 3 秒后重试...")
                    time.sleep(3)
        
        logger.error(f"登录失败，已达到最大重试次数 {max_retries}。程序终止。")
        return False
    
    def check_welcome_page(self, page) -> bool:
        """检查是否到达欢迎页面"""
        logger.info("检查欢迎页面...")
        time.sleep(3)
        
        try:
            page.wait_for_selector('text=Welcome to TikTok Shop Partner Center', timeout=20000)
            logger.info(f"✓ 找到欢迎文字，页面已加载")
            return True
        except Exception:
            logger.warning(f"未找到欢迎文字")
            return False

    def run(self) -> bool:
        """运行登录 + 提取Unread消息"""
        logger.info("=" * 50)
        logger.info("TikTok Chat History Crawler - Enhanced")
        logger.info("=" * 50)

        with sync_playwright() as p:
            try:
                self.playwright_context_active = True
                self.browser = p.chromium.launch(headless=True, timeout=60000)
                self.context = self.browser.new_context(viewport={'width': 1920, 'height': 1080})
                self.context.set_default_timeout(60000)
                self.page = self.context.new_page()

                # 登录 + 欢迎页检查
                max_login_attempts = 3
                for attempt in range(1, max_login_attempts + 1):
                    logger.info(f"=== 登录流程尝试 {attempt}/{max_login_attempts} ===")
                    if not self.login(self.page):
                        logger.error("登录失败")
                    else:
                        if self.check_welcome_page(self.page):
                            logger.info("✓ 登录并进入欢迎页面成功")
                            break
                        else:
                            logger.warning("未找到欢迎页面，将重新开始登录")
                    if attempt < max_login_attempts:
                        try:
                            self.page.goto("https://partner-sso.tiktok.com/account/login", wait_until="networkidle")
                            self.delay(3)
                        except:
                            pass
                    else:
                        logger.error("多次尝试后仍未进入欢迎页面，放弃")
                        return False

                return True

            except Exception as e:
                logger.error(f"程序运行出错: {e}")
                return False
            finally:
                if self.page:
                    self.page.close()
                if self.context:
                    self.context.close()
                if self.browser:
                    self.browser.close()
                logger.info("浏览器已关闭")

if __name__ == '__main__':
    login = Login()
    login.run()