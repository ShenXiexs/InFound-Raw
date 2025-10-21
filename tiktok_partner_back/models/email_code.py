"""
Gmail验证码获取模块
可复用的邮箱验证码获取功能
"""

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
    """Gmail验证码获取类"""
    
    def __init__(self, username: str, app_password: str):
        """
        初始化Gmail验证码获取器
        
        Args:
            username: Gmail用户名（邮箱地址）
            app_password: Gmail应用专用密码
        """
        self.gmail_username = username
        self.gmail_app_password = app_password
        self._mail_connection = None  # 持久连接
        self._last_activity = 0  # 上次活动时间
        self._connection_lifetime = 3600
    
    def connect_gmail(self, timeout: int = 5, max_retries: int = 5) -> Optional[imaplib.IMAP4_SSL]:
        """
        连接到Gmail IMAP服务器
        
        Args:
            timeout: 连接超时时间（秒）
            max_retries: 最大重试次数
            
        Returns:
            IMAP4_SSL对象，连接失败返回None
        """
        # Gmail IMAP 服务器列表（主服务器和备用）
        imap_servers = [
            ('imap.gmail.com', 993)
        ]
        
        for server_idx, (server_host, server_port) in enumerate(imap_servers):
            for retry in range(max_retries):
                try:
                    logger.info(f"尝试连接 {server_host}:{server_port} (尝试 {retry+1}/{max_retries})")
                    
                    # 设置socket超时
                    original_timeout = socket.getdefaulttimeout()
                    socket.setdefaulttimeout(timeout)
                    
                    # 创建IMAP连接
                    mail = imaplib.IMAP4_SSL(server_host, server_port)
                    
                    # 尝试登录
                    mail.login(self.gmail_username, self.gmail_app_password)
                    
                    # 恢复原始超时设置
                    socket.setdefaulttimeout(original_timeout)
                    
                    logger.info(f"成功连接到Gmail: {self.gmail_username} via {server_host}")
                    return mail
                    
                except (socket.timeout, socket.error) as e:
                    logger.warning(f"网络错误 ({server_host}): {e}")
                    if retry < max_retries - 1:
                        wait_time = (retry + 1) * 2  # 递增等待时间
                        logger.info(f"等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                        
                except imaplib.IMAP4.error as e:
                    error_msg = str(e)
                    if 'AUTHENTICATIONFAILED' in error_msg:
                        logger.error(f"认证失败: {error_msg}")
                        return None  # 认证失败不重试
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
        """
        安全断开IMAP连接
        
        Args:
            mail: IMAP连接对象
        """
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
        """
        专门针对 TikTok Shop Partner Center 的邮件格式
        """
        if not text:
            return None
        
        # 如果是HTML内容，先提取纯文本
        if '<html' in text.lower() or '<!doctype' in text.lower():
            # 移除style和script标签及其内容
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
            # 移除HTML标签
            text = re.sub(r'<[^>]+>', ' ', text)
            # 解码HTML实体
            import html
            text = html.unescape(text)
        
        # 清理文本：移除零宽字符，规范化空白
        cleaned = text.replace("\u200b", "").replace("\r", "").strip()
        
        # 打印原始文本用于调试
        logger.debug(f"原始文本: {repr(cleaned[:500])}")
        logger.debug(f"文本最后200字符: {repr(cleaned[-200:])}")  # 增加查看末尾内容
        
        # 方法1: 直接查找 "enter this code" 后面的验证码
        # 处理可能的换行和空格
        patterns = [
            # 标准格式：冒号后面直接跟验证码
            r'enter\s+this\s+code\s+in\s+TikTok\s+Shop\s+Partner\s+Center\s*:\s*([A-Z0-9]{6})',
            # 冒号后换行的情况
            r'enter\s+this\s+code\s+in\s+TikTok\s+Shop\s+Partner\s+Center\s*:\s*\n\s*([A-Z0-9]{6})',
            # 更宽松的匹配
            r'enter\s+this\s+code.*?:\s*([A-Z0-9]{6})',
            # 匹配任何 "code" 相关的上下文
            r'verification\s+code.*?:\s*([A-Z0-9]{6})',
            r'code\s+in.*?:\s*([A-Z0-9]{6})',
            # 最后的6位字母数字组合（作为兜底）
            r'([A-Z0-9]{6})(?:\s*$|\s*[^\w])',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, cleaned, re.MULTILINE | re.DOTALL)
            if matches:
                code = matches[-1].strip().upper()
                # 修改：接受所有6位字母数字组合（包括纯数字）
                if len(code) == 6 and code.isalnum():  # ✓ 正确：接受纯数字、纯字母、混合
                    logger.info(f"使用模式找到验证码: {code}")
                    return code
        
        # 方法2: 查找所有6位字母数字组合，取最后一个
        all_codes = re.findall(r'\b([A-Z0-9]{6})\b', cleaned)
        if all_codes:
            # 过滤掉常见的非验证码词汇
            stopwords = {'PUBLIC', 'PRIVATE', 'NOTICE', 'PLEASE', 'THANKS', 'REGARD',
                        'TIKTOK', 'PARTNER', 'CENTER', 'SECURE', 'SIGNIN', 'SIGNUP',
                        'BOTTOM', 'CLICK', 'HERE', 'LINK', 'CODE', 'VERIFY', 'MARGIN',
                        'BORDER', 'HEIGHT', 'WIDTH', 'COLOR', 'FONT', 'FAMILY', 'SIZE',
                        'ANYONE', 'EVERYY', 'SOMETHING', 'NOTHING', 'ALWAYS', 'NEVER',
                        'EXPIRE', 'EXPIRED', 'VALID', 'INVALID'}
            
            valid_codes = []
            for code in all_codes:
                code_upper = code.upper()
                # 接受所有不在停用词中的6位字母数字组合（包括纯数字）
                if code_upper not in stopwords:
                    valid_codes.append(code_upper)
            
            if valid_codes:
                # 返回最后一个有效的验证码
                logger.info(f"通过搜索找到验证码: {valid_codes[-1]}")
                return valid_codes[-1]
        
        logger.warning("未能提取到验证码")
        return None
        
    def get_email_content(self, msg: Message) -> str:
        """
        获取邮件正文内容
        
        Args:
            msg: 邮件消息对象
            
        Returns:
            邮件正文内容
        """
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
        """
        解码邮件主题
        
        Args:
            msg: 邮件消息对象
            
        Returns:
            解码后的邮件主题
        """
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
        """
        从最新的邮件中获取验证码
        
        Args:
            mail: IMAP连接对象
            
        Returns:
            验证码，未找到返回None
        """
        try:
            mail.noop()
            mail.select('inbox')
            
            # 搜索包含TikTok Shop Partner Center的邮件
            search_criteria = '(OR SUBJECT "TikTok Shop Partner Center" BODY "TikTok Shop Partner Center")'
            status, messages = mail.search(None, search_criteria)
            
            if status != 'OK':
                # 如果特定搜索失败，搜索所有邮件
                logger.warning("特定搜索失败，尝试搜索所有邮件")
                status, messages = mail.search(None, 'ALL')
            
            if status != 'OK':
                logger.error("搜索邮件失败")
                return None
            
            email_ids = messages[0].split()
            
            if not email_ids or email_ids == [b'']:
                logger.warning("收件箱为空或未找到相关邮件")
                return None
            
            # 获取最新的邮件
            latest_id = email_ids[-1]
            logger.info(f"正在获取邮件 ID: {latest_id}")
            
            status, msg_data = mail.fetch(latest_id, '(RFC822)')
            
            if status != 'OK':
                logger.error("获取邮件失败")
                return None
            
            # 解析邮件
            msg = email.message_from_bytes(msg_data[0][1])
            
            # 获取邮件主题
            subject = self.decode_email_subject(msg)
            logger.info(f"最新邮件主题: {subject}")
            
            # 获取邮件内容
            content = self.get_email_content(msg)
            logger.debug(f"邮件内容前200字符: {content[:200]}")
            
            # 尝试从内容中提取验证码
            verification_code = self.extract_verification_code(content)
            
            # 如果内容中没有，尝试从主题中提取
            if not verification_code:
                verification_code = self.extract_verification_code(subject)
            
            if verification_code:
                logger.info(f"从邮件中找到验证码: {verification_code}")
            else:
                logger.warning("未能从邮件中提取验证码")
                # 打印更多调试信息
                logger.debug(f"邮件完整内容: {content[:500]}")
            
            return verification_code
            
        except Exception as e:
            logger.error(f"获取邮件时出错: {e}", exc_info=True)
            return None
    
    def get_connection(self, force_new: bool = False) -> Optional[imaplib.IMAP4_SSL]:
        """
        获取或创建IMAP连接
        
        Args:
            force_new: 是否强制创建新连接
            
        Returns:
            IMAP连接对象
        """
        current_time = time.time()
        
        # 检查是否需要新连接
        need_new_connection = (
            force_new or 
            self._mail_connection is None or
            (current_time - self._last_activity) > self._connection_lifetime
        )
        
        if need_new_connection:
            # 关闭旧连接
            if self._mail_connection:
                self.safe_logout(self._mail_connection)
                self._mail_connection = None
            
            # 创建新连接
            self._mail_connection = self.connect_gmail(timeout=15, max_retries=3)
            
        elif self._mail_connection:
            # 检查连接是否还活着
            try:
                self._mail_connection.noop()  # NOOP命令测试连接
                logger.debug("连接保活成功")
            except:
                logger.info("连接已断开，重新连接...")
                self._mail_connection = None
                return self.get_connection(force_new=True)
        
        self._last_activity = current_time
        return self._mail_connection
    
    def get_verification_code(self, 
                            max_attempts: int = 3, 
                            check_interval: int = 3, 
                            connection_timeout: int = 30) -> Optional[str]:
        """
        获取验证码（增强版，支持连接重用）
        
        Args:
            max_attempts: 最大尝试次数
            check_interval: 每次检查的间隔时间（秒）
            connection_timeout: 连接超时时间（秒）
            
        Returns:
            验证码，获取失败返回None
        """
        logger.info("开始获取Gmail验证码...")
        
        attempt = 0
        previous_code = None
        consecutive_failures = 0  # 连续失败次数
        
        try:
            while attempt < max_attempts:
                attempt += 1
                logger.info(f"第 {attempt}/{max_attempts} 次检查验证码...")
                
                # 获取连接（自动管理重连）
                mail = self.get_connection(force_new=(consecutive_failures >= 2))
                
                if not mail:
                    consecutive_failures += 1
                    logger.warning(f"无法获取Gmail连接（连续失败 {consecutive_failures} 次）")
                    
                    if consecutive_failures >= 3:
                        logger.error("连续3次连接失败，可能是网络或认证问题")
                        # 等待更长时间再试
                        time.sleep(10)
                        consecutive_failures = 0  # 重置计数器
                    else:
                        time.sleep(check_interval)
                    continue
                
                try:
                    code = self.get_latest_verification_code_from_email(mail)
                    consecutive_failures = 0  # 成功后重置失败计数
                    
                    if code:
                        logger.info(f"发现验证码: {code}")
                        
                        # 连续两次获取到相同验证码才确认
                        if previous_code == code:
                            logger.info(f"✓ 验证码确认成功（连续两次一致）: {code}")
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
                    # 标记连接为无效，下次会重新连接
                    self._mail_connection = None
                
                if attempt < max_attempts:
                    time.sleep(check_interval)
            
            logger.error(f"验证码获取超时（尝试 {max_attempts} 次）")
            return None
            
        finally:
            # 不立即关闭连接，保持供下次使用
            pass
    
    def wait_for_new_code(self, old_code: Optional[str] = None, max_wait: int = 60) -> Optional[str]:
        """
        等待新的验证码（与旧验证码不同）
        
        Args:
            old_code: 旧的验证码
            max_wait: 最大等待时间（秒）
            
        Returns:
            新的验证码，超时返回None
        """
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
        """析构函数，确保连接被关闭"""
        if hasattr(self, '_mail_connection') and self._mail_connection:
            try:
                self.safe_logout(self._mail_connection)
            except:
                pass


# 便捷函数
def get_tiktok_verification_code(username: str = "tiktokshopinfoundtest@gmail.com", 
                                 app_password: str = "cfhlfedjqhfbbbhb") -> Optional[str]:
    """
    获取TikTok验证码的便捷函数
    
    Args:
        username: Gmail用户名
        app_password: Gmail应用专用密码
        
    Returns:
        验证码，获取失败返回None
    """
    gmail = GmailVerificationCode(username, app_password)
    return gmail.get_verification_code()



if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(
        level=logging.DEBUG,  # 改为DEBUG以查看更多信息
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 测试验证码提取功能
    test_email_content = """Dear Partner,
To verify your account, enter this code in TikTok Shop Partner Center :
NNQS6M"""
    
    gmail = GmailVerificationCode("test", "test")
    code = gmail.extract_verification_code(test_email_content)
    print(f"测试提取结果: {code}")
    
    # 使用默认账号测试实际功能
    print("\n开始实际测试...")
    code = get_tiktok_verification_code()
    
    if code:
        print(f"成功获取验证码: {code}")
    else:
        print("获取验证码失败")