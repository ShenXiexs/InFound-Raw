"""Legacy docstring removed for English-only repo."""

import logging
import time
import socket
import re
import imaplib
import email
from email.header import decode_header
from email.message import Message
from typing import Optional

logger = logging.getLogger(__name__)

class GmailVerificationCode:
    """Legacy docstring removed for English-only repo."""
    
    def __init__(self, username: str, app_password: str):
        """Legacy docstring removed for English-only repo."""
        self.gmail_username = username
        self.gmail_app_password = app_password
        self._mail_connection = None  # NOTE: legacy comment removed for English-only repo.
        self._last_activity = 0  # NOTE: legacy comment removed for English-only repo.
        self._connection_lifetime = 3600
    
    def connect_gmail(self, timeout: int = 5, max_retries: int = 5) -> Optional[imaplib.IMAP4_SSL]:
        """Legacy docstring removed for English-only repo."""
        # NOTE: legacy comment removed for English-only repo.
        imap_servers = [
            ('imap.gmail.com', 993)
        ]
        
        for server_idx, (server_host, server_port) in enumerate(imap_servers):
            for retry in range(max_retries):
                try:
                    logger.info(f"尝试连接 {server_host}:{server_port} (尝试 {retry+1}/{max_retries})")
                    
                    # NOTE: legacy comment removed for English-only repo.
                    original_timeout = socket.getdefaulttimeout()
                    socket.setdefaulttimeout(timeout)
                    
                    # NOTE: legacy comment removed for English-only repo.
                    mail = imaplib.IMAP4_SSL(server_host, server_port)
                    
                    # NOTE: legacy comment removed for English-only repo.
                    mail.login(self.gmail_username, self.gmail_app_password)
                    
                    # NOTE: legacy comment removed for English-only repo.
                    socket.setdefaulttimeout(original_timeout)
                    
                    logger.info(f"成功连接到Gmail: {self.gmail_username} via {server_host}")
                    return mail
                    
                except (socket.timeout, socket.error) as e:
                    logger.warning(f"网络错误 ({server_host}): {e}")
                    if retry < max_retries - 1:
                        wait_time = (retry + 1) * 2  # NOTE: legacy comment removed for English-only repo.
                        logger.info(f"等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                        
                except imaplib.IMAP4.error as e:
                    error_msg = str(e)
                    if 'AUTHENTICATIONFAILED' in error_msg:
                        logger.error(f"认证失败: {error_msg}")
                        return None  # NOTE: legacy comment removed for English-only repo.
                    elif 'Too many login failures' in error_msg:
                        logger.error(f"登录失败次数过多，请稍后再试")
                        return None
                    else:
                        logger.warning(f"IMAP错误 ({server_host}): {e}")
                        if retry < max_retries - 1:
                            time.sleep(2)
                            
                except Exception as e:
                    logger.error(f"未知错误 ({server_host}): {e}")
                    if retry < max_retries - 1:
                        time.sleep(2)
        
        logger.error(f"所有连接尝试均失败")
        return None
    
    def safe_logout(self, mail: Optional[imaplib.IMAP4_SSL]) -> None:
        """Legacy docstring removed for English-only repo."""
        if mail:
            try:
                mail.noop()
                mail.logout()
                logger.info("Gmail连接已安全断开")
            except (OSError, imaplib.IMAP4.abort, imaplib.IMAP4.error):
                try:
                    mail.sock.close()
                except:
                    pass
            except Exception as e:
                logger.error(f"断开连接时出错: {e}")
    
    def extract_verification_code(self, text: str) -> Optional[str]:
        """Legacy docstring removed for English-only repo."""
        if not text:
            return None
        
        # NOTE: legacy comment removed for English-only repo.
        if '<html' in text.lower() or '<!doctype' in text.lower():
            # NOTE: legacy comment removed for English-only repo.
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
            # NOTE: legacy comment removed for English-only repo.
            text = re.sub(r'<[^>]+>', ' ', text)
            # NOTE: legacy comment removed for English-only repo.
            import html
            text = html.unescape(text)
        
        # NOTE: legacy comment removed for English-only repo.
        cleaned = text.replace("\u200b", "").replace("\r", "").strip()
        
        # NOTE: legacy comment removed for English-only repo.
        logger.debug(f"原始文本: {repr(cleaned[:500])}")
        logger.debug(f"文本最后200字符: {repr(cleaned[-200:])}")  # NOTE: legacy comment removed for English-only repo.
        
        # NOTE: legacy comment removed for English-only repo.
        # NOTE: legacy comment removed for English-only repo.
        patterns = [
            # NOTE: legacy comment removed for English-only repo.
            r'enter\s+this\s+code\s+in\s+TikTok\s+Shop\s+Partner\s+Center\s*:\s*([A-Z0-9]{6})',
            # NOTE: legacy comment removed for English-only repo.
            r'enter\s+this\s+code\s+in\s+TikTok\s+Shop\s+Partner\s+Center\s*:\s*\n\s*([A-Z0-9]{6})',
            # NOTE: legacy comment removed for English-only repo.
            r'enter\s+this\s+code.*?:\s*([A-Z0-9]{6})',
            # NOTE: legacy comment removed for English-only repo.
            r'verification\s+code.*?:\s*([A-Z0-9]{6})',
            r'code\s+in.*?:\s*([A-Z0-9]{6})',
            # NOTE: legacy comment removed for English-only repo.
            r'([A-Z0-9]{6})(?:\s*$|\s*[^\w])',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, cleaned, re.MULTILINE | re.DOTALL)
            if matches:
                code = matches[-1].strip().upper()
                # NOTE: legacy comment removed for English-only repo.
                if len(code) == 6 and code.isalnum():  # NOTE: legacy comment removed for English-only repo.
                    logger.info(f"使用模式找到验证码: {code}")
                    return code
        
        # NOTE: legacy comment removed for English-only repo.
        all_codes = re.findall(r'\b([A-Z0-9]{6})\b', cleaned)
        if all_codes:
            # NOTE: legacy comment removed for English-only repo.
            stopwords = {'PUBLIC', 'PRIVATE', 'NOTICE', 'PLEASE', 'THANKS', 'REGARD',
                        'TIKTOK', 'PARTNER', 'CENTER', 'SECURE', 'SIGNIN', 'SIGNUP',
                        'BOTTOM', 'CLICK', 'HERE', 'LINK', 'CODE', 'VERIFY', 'MARGIN',
                        'BORDER', 'HEIGHT', 'WIDTH', 'COLOR', 'FONT', 'FAMILY', 'SIZE',
                        'ANYONE', 'EVERYY', 'SOMETHING', 'NOTHING', 'ALWAYS', 'NEVER',
                        'EXPIRE', 'EXPIRED', 'VALID', 'INVALID'}
            
            valid_codes = []
            for code in all_codes:
                code_upper = code.upper()
                # NOTE: legacy comment removed for English-only repo.
                if code_upper not in stopwords:
                    valid_codes.append(code_upper)
            
            if valid_codes:
                # NOTE: legacy comment removed for English-only repo.
                logger.info(f"通过搜索找到验证码: {valid_codes[-1]}")
                return valid_codes[-1]
        
        logger.warning("未能提取到验证码")
        return None
        
    def get_email_content(self, msg: Message) -> str:
        """Legacy docstring removed for English-only repo."""
        content = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type in ["text/plain", "text/html"]:
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            decoded = payload.decode('utf-8', errors='ignore')
                            content += decoded + "\n"
                    except Exception as e:
                        logger.warning(f"解码邮件部分失败: {e}")
        else:
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    content = payload.decode('utf-8', errors='ignore')
            except Exception as e:
                logger.warning(f"解码邮件内容失败: {e}")
        
        return content
    
    def decode_email_subject(self, msg: Message) -> str:
        """Legacy docstring removed for English-only repo."""
        subject = "无主题"
        if msg["Subject"]:
            try:
                subject_parts = decode_header(msg["Subject"])
                subject = ""
                for part, encoding in subject_parts:
                    if isinstance(part, bytes):
                        subject += part.decode(encoding or 'utf-8', errors='ignore')
                    else:
                        subject += part
            except Exception as e:
                logger.warning(f"解码邮件主题失败: {e}")
                subject = str(msg["Subject"])
        
        return subject
    
    def get_latest_verification_code_from_email(self, mail: imaplib.IMAP4_SSL) -> Optional[str]:
        """Legacy docstring removed for English-only repo."""
        try:
            mail.noop()
            mail.select('inbox')
            
            # NOTE: legacy comment removed for English-only repo.
            search_criteria = '(OR SUBJECT "TikTok Shop Partner Center" BODY "TikTok Shop Partner Center")'
            status, messages = mail.search(None, search_criteria)
            
            if status != 'OK':
                # NOTE: legacy comment removed for English-only repo.
                logger.warning("特定搜索失败，尝试搜索所有邮件")
                status, messages = mail.search(None, 'ALL')
            
            if status != 'OK':
                logger.error("搜索邮件失败")
                return None
            
            email_ids = messages[0].split()
            
            if not email_ids or email_ids == [b'']:
                logger.warning("收件箱为空或未找到相关邮件")
                return None
            
            # NOTE: legacy comment removed for English-only repo.
            latest_id = email_ids[-1]
            logger.info(f"正在获取邮件 ID: {latest_id}")
            
            status, msg_data = mail.fetch(latest_id, '(RFC822)')
            
            if status != 'OK':
                logger.error("获取邮件失败")
                return None
            
            # NOTE: legacy comment removed for English-only repo.
            msg = email.message_from_bytes(msg_data[0][1])
            
            # NOTE: legacy comment removed for English-only repo.
            subject = self.decode_email_subject(msg)
            logger.info(f"最新邮件主题: {subject}")
            
            # NOTE: legacy comment removed for English-only repo.
            content = self.get_email_content(msg)
            logger.debug(f"邮件内容前200字符: {content[:200]}")
            
            # NOTE: legacy comment removed for English-only repo.
            verification_code = self.extract_verification_code(content)
            
            # NOTE: legacy comment removed for English-only repo.
            if not verification_code:
                verification_code = self.extract_verification_code(subject)
            
            if verification_code:
                logger.info(f"从邮件中找到验证码: {verification_code}")
            else:
                logger.warning("未能从邮件中提取验证码")
                # NOTE: legacy comment removed for English-only repo.
                logger.debug(f"邮件完整内容: {content[:500]}")
            
            return verification_code
            
        except Exception as e:
            logger.error(f"获取邮件时出错: {e}", exc_info=True)
            return None
    
    def get_connection(self, force_new: bool = False) -> Optional[imaplib.IMAP4_SSL]:
        """Legacy docstring removed for English-only repo."""
        current_time = time.time()
        
        # NOTE: legacy comment removed for English-only repo.
        need_new_connection = (
            force_new or 
            self._mail_connection is None or
            (current_time - self._last_activity) > self._connection_lifetime
        )
        
        if need_new_connection:
            # NOTE: legacy comment removed for English-only repo.
            if self._mail_connection:
                self.safe_logout(self._mail_connection)
                self._mail_connection = None
            
            # NOTE: legacy comment removed for English-only repo.
            self._mail_connection = self.connect_gmail(timeout=15, max_retries=3)
            
        elif self._mail_connection:
            # NOTE: legacy comment removed for English-only repo.
            try:
                self._mail_connection.noop()  # NOTE: legacy comment removed for English-only repo.
                logger.debug("连接保活成功")
            except:
                logger.info("连接已断开，重新连接...")
                self._mail_connection = None
                return self.get_connection(force_new=True)
        
        self._last_activity = current_time
        return self._mail_connection
    
    def get_verification_code(self, 
                            max_attempts: int = 4, 
                            check_interval: int = 15, 
                            connection_timeout: int = 80) -> Optional[str]:
        """Legacy docstring removed for English-only repo."""
        logger.info("开始获取Gmail验证码...")
        
        attempt = 0
        previous_code = None
        consecutive_failures = 0  # NOTE: legacy comment removed for English-only repo.
        
        try:
            while attempt < max_attempts:
                attempt += 1
                logger.info(f"第 {attempt}/{max_attempts} 次检查验证码...")
                
                # NOTE: legacy comment removed for English-only repo.
                mail = self.get_connection(force_new=(consecutive_failures >= 2))
                
                if not mail:
                    consecutive_failures += 1
                    logger.warning(f"无法获取Gmail连接（连续失败 {consecutive_failures} 次）")
                    
                    if consecutive_failures >= 3:
                        logger.error("连续3次连接失败，可能是网络或认证问题")
                        # NOTE: legacy comment removed for English-only repo.
                        time.sleep(10)
                        consecutive_failures = 0  # NOTE: legacy comment removed for English-only repo.
                    else:
                        time.sleep(check_interval)
                    continue
                
                try:
                    code = self.get_latest_verification_code_from_email(mail)
                    consecutive_failures = 0  # NOTE: legacy comment removed for English-only repo.
                    
                    if code:
                        logger.info(f"发现验证码: {code}")
                        
                        # NOTE: legacy comment removed for English-only repo.
                        if previous_code == code:
                            logger.info(f"✓ 验证码确认成功（连续2次一致）: {code}")
                            return code
                        else:
                            previous_code = code
                            logger.info("验证码变化，等待下次检查以确认...")
                    else:
                        logger.info("暂未发现验证码...")
                        previous_code = None
                        
                except Exception as e:
                    consecutive_failures += 1
                    logger.error(f"获取邮件时出错: {e}")
                    # NOTE: legacy comment removed for English-only repo.
                    self._mail_connection = None
                
                if attempt < max_attempts:
                    time.sleep(check_interval)
            
            logger.error(f"验证码获取超时（尝试 {max_attempts} 次）")
            return None
            
        finally:
            # NOTE: legacy comment removed for English-only repo.
            pass
    
    def wait_for_new_code(self, old_code: Optional[str] = None, max_wait: int = 60) -> Optional[str]:
        """Legacy docstring removed for English-only repo."""
        logger.info(f"等待新的验证码（旧验证码: {old_code}）...")
        
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            code = self.get_verification_code(max_attempts=1)
            
            if code and code != old_code:
                logger.info(f"=获取到新验证码: {code}")
                return code
            
            time.sleep(3)
        
        logger.error("等待新验证码超时")
        return None


    def __del__(self):
        """Legacy docstring removed for English-only repo."""
        if hasattr(self, '_mail_connection') and self._mail_connection:
            try:
                self.safe_logout(self._mail_connection)
            except:
                pass


# NOTE: legacy comment removed for English-only repo.
def get_tiktok_verification_code(username: str = "user@example.com", 
                                 app_password: str = "<GMAIL_APP_PASSWORD>") -> Optional[str]:
    """Legacy docstring removed for English-only repo."""
    gmail = GmailVerificationCode(username, app_password)
    return gmail.get_verification_code()



if __name__ == "__main__":
    # NOTE: legacy comment removed for English-only repo.
    logging.basicConfig(
        level=logging.DEBUG,  # NOTE: legacy comment removed for English-only repo.
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # NOTE: legacy comment removed for English-only repo.
    test_email_content = """Dear Partner,
To verify your account, enter this code in TikTok Shop Partner Center :
NNQS6M"""
    
    gmail = GmailVerificationCode("test", "test")
    code = gmail.extract_verification_code(test_email_content)
    print(f"测试提取结果: {code}")
    
    # NOTE: legacy comment removed for English-only repo.
    print("\n开始实际测试...")
    code = get_tiktok_verification_code()
    
    if code:
        print(f"成功获取验证码: {code}")
    else:
        print("获取验证码失败")
