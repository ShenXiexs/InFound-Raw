"""
TikTok Chat History Crawler 
根据creator_db.xlsx逐个爬取聊天记录

nohup python -u chat_history/chat_creator.py \
  --creator-db data/chat_history_data/creator_20251101_MX.xlsx \
  --history-file data/chat_history_data/chat_history_MX_1112.xlsx \
  --accounts-config config/accounts.json \
  --account-name MX2 \
  --restart-interval 300 \
  > logs/chat_history_MX_1112.log 2>&1 &

nohup python -u chat_history/chat_creator.py \
  --creator-db data/chat_history_data/creator_20251101_FR.xlsx \
  --history-file data/chat_history_data/chat_history_FR_1112.xlsx \
  --accounts-config config/accounts.json \
  --account-name FR1 \
  --restart-interval 300 \
  > logs/chat_history_FR_1112.log 2>&1 &
"""
import argparse
import json
import logging
import time
import sys
import os
import shutil
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from zipfile import BadZipFile
from playwright.sync_api import sync_playwright, Error as PlaywrightError

# Ensure direct script execution resolves imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.email_code import GmailVerificationCode
from utils.credentials import get_default_account_from_env, MissingDefaultAccountError

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ChatPageCrashError(Exception):
    """Raised when the Playwright page/context unexpectedly closes."""
    pass


class ChatHistoryCrawler:
    """
    TikTok聊天记录爬虫
    支持提取Unread消息的历史记录
    """
    
    def __init__(
        self,
        account_info=None,
        restart_interval=300,
        creator_db_path: Optional[str] = None,
        history_file_path: Optional[str] = None,
        accounts_config_path: Optional[str] = None,
        account_name: Optional[str] = None,
    ):
        self.accounts_config = self._load_accounts_config(accounts_config_path)
        self.account_override_name = account_name
        self.manual_account_info = account_info
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

        # Gmail验证码配置
        self.gmail_verifier = GmailVerificationCode(
            username=self.gmail_username,
            app_password=self.gmail_app_password
        )
        
        self.browser = None
        self.context = None
        self.page = None
        base_dir = Path(__file__).resolve().parent.parent
        self.csv_data_dir = str(base_dir / "data" / "chat_history_data")
        default_creator_db = base_dir / "data" / "creator_db.xlsx"
        self.creator_db_path = (
            Path(creator_db_path).expanduser().resolve()
            if creator_db_path
            else default_creator_db
        )
        default_history_file = base_dir / "data" / "chat_history_data" / "chat_creator_history.xlsx"
        self.history_file_path = (
            Path(history_file_path).expanduser().resolve()
            if history_file_path
            else default_history_file
        )
        
        # 确保目录存在
        os.makedirs(self.csv_data_dir, exist_ok=True)
        self.history_file_path.parent.mkdir(parents=True, exist_ok=True)
        self.restart_interval = restart_interval  # 每处理多少个达人后重启
        logger.info(f"浏览器重启间隔设置为: 每 {self.restart_interval} 个达人")
        logger.info(f"聊天历史将保存到: {self.history_file_path}")
        self._initialize_processed_creators()
    
    def _close_playwright_obj(self, obj, label: str):
        """安全关闭 Playwright 对象，忽略已被关闭的异常"""
        if not obj:
            return
        try:
            obj.close()
        except PlaywrightError as exc:
            logger.debug(f"{label} 关闭时忽略错误: {exc}")
        except Exception as exc:  # pragma: no cover
            logger.warning(f"{label} 关闭时遇到异常: {exc}")

    
    def delay(self, seconds: float):
        """延迟"""
        time.sleep(seconds)
    
    def _load_accounts_config(self, config_path: Optional[str]) -> Dict[str, List[Dict[str, Any]]]:
        """加载账号配置，支持自定义路径"""
        default_accounts = {
            "accounts": [
                {
                    "name": "SampleAccount-MX",
                    "login_email": "mx-account@example.com",
                    "login_password": "CHANGE_ME",
                    "gmail_username": "mx-notifications@example.com",
                    "gmail_app_password": "CHANGE_ME",
                    "region": "MX",
                    "enabled": True,
                    "notes": "Placeholder MX account; replace with a real credential set."
                },
                {
                    "name": "SampleAccount-FR",
                    "login_email": "fr-account@example.com",
                    "login_password": "CHANGE_ME",
                    "gmail_username": "fr-notifications@example.com",
                    "gmail_app_password": "CHANGE_ME",
                    "region": "FR",
                    "enabled": True,
                    "notes": "Placeholder FR account; replace before running."
                }
            ]
        }
        base_dir = Path(__file__).resolve().parent.parent
        default_path = base_dir / "config" / "accounts.json"
        path = Path(config_path).expanduser().resolve() if config_path else default_path
        if not path.exists():
            logger.warning(f"未找到账号配置文件 {path} ，使用内置默认配置")
            return default_accounts
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            if not isinstance(data, dict) or "accounts" not in data:
                raise ValueError("配置格式错误，缺少 'accounts' 字段")
            logger.info(f"已从 {path} 加载 {len(data['accounts'])} 个账号配置")
            return data
        except Exception as exc:
            logger.error(f"读取账号配置失败: {exc}，将使用内置默认配置")
            return default_accounts

    def _load_history_dataframe(self) -> Tuple[pd.DataFrame, bool]:
        """读取历史聊天记录文件，自动处理损坏的Excel"""
        filepath = self.history_file_path
        if not filepath.exists():
            return pd.DataFrame(), False
        try:
            df = pd.read_excel(str(filepath), engine='openpyxl')
            return df, True
        except (BadZipFile, ValueError, OSError) as exc:
            if isinstance(exc, BadZipFile) or "Bad magic number" in str(exc):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup = filepath.with_suffix(f"{filepath.suffix}.corrupted_{timestamp}")
                shutil.move(str(filepath), str(backup))
                logger.warning(
                    f"检测到历史文件损坏 ({exc}); 已将原文件备份为 {backup.name} 并重新创建"
                )
                return pd.DataFrame(), False
            logger.error(f"读取历史文件失败: {exc}")
            return pd.DataFrame(), False
    
    def _initialize_processed_creators(self):
        """初始化已处理达人集合，用于快速去重"""
        self.processed_creators = set()
        df, existed = self._load_history_dataframe()
        if existed and not df.empty and 'creator_name' in df.columns:
            loaded = set(
                str(name).strip()
                for name in df['creator_name'].dropna().astype(str).tolist()
            )
            self.processed_creators.update(loaded)
            logger.info(f"历史文件中已包含 {len(self.processed_creators)} 位达人，将自动跳过")

    def get_region_from_excel(self) -> str:
        """从creator_db.xlsx读取第一行的region列"""
        logger.info(f"读取Excel第一行的region列: %s", self.creator_db_path)
        
        try:
            df = pd.read_excel(self.creator_db_path, engine='openpyxl')
            
            if 'region' not in df.columns:
                logger.error("creator_db.xlsx中缺少region列")
                return "MX"  # 默认使用MX
            
            if len(df) == 0:
                logger.error("Excel文件为空")
                return "MX"
            
            region = df.iloc[0]['region']
            logger.info(f"✓ 检测到region: {region}")
            return str(region).upper()
            
        except Exception as e:
            logger.error(f"读取region失败: {e}")
            return "MX"  # 默认使用MX

    def select_account_by_region(self, region: str) -> Dict[str, str]:
        """根据region选择对应的账号"""
        logger.info(f"根据region={region}选择账号...")
        
        for account in self.accounts_config['accounts']:
            if account['region'] == region and account['enabled']:
                logger.info(f"✓ 选择账号: {account['name']}")
                return account
        
        # 如果没找到匹配的,使用第一个启用的账号
        for account in self.accounts_config['accounts']:
            if account['enabled']:
                logger.warning(f"未找到region={region}的账号,使用默认账号: {account['name']}")
                return account
        
        logger.error("没有可用的账号配置")
        return None
    
    def select_account_by_name(self, name: str) -> Optional[Dict[str, str]]:
        """根据账号名称精准选择"""
        target = name.strip().lower()
        for account in self.accounts_config['accounts']:
            if account.get('name', '').strip().lower() == target:
                if not account.get('enabled', False):
                    logger.error(f"账号 {name} 已被禁用，无法使用")
                    return None
                logger.info(f"✓ 根据账号名称选择账号: {account['name']}")
                return account
        logger.error(f"未在配置中找到名称为 {name} 的账号")
        return None

    def setup_account_by_region(self):
        """根据Excel的region自动设置账号"""
        if self.manual_account_info:
            logger.info("检测到自定义账号信息，跳过自动账号选择")
            return
        region = self.get_region_from_excel()
        if self.account_override_name:
            logger.info(f"使用命令行指定账号: {self.account_override_name}")
            selected_account = self.select_account_by_name(self.account_override_name)
        else:
            selected_account = self.select_account_by_region(region)
        
        if not selected_account:
            raise Exception("无法选择账号")
        
        # 设置账号信息
        self.login_email = selected_account['login_email']
        self.login_password = selected_account['login_password']
        self.gmail_username = selected_account['gmail_username']
        self.gmail_app_password = selected_account['gmail_app_password']
        self.account_name = selected_account['name']
        self.account_region = selected_account['region']
        
        # 重新初始化Gmail验证器
        self.gmail_verifier = GmailVerificationCode(
            username=self.gmail_username,
            app_password=self.gmail_app_password
        )
        
        logger.info("=" * 60)
        logger.info(f"账号配置完成:")
        logger.info(f"  账号名称: {self.account_name}")
        logger.info(f"  登录邮箱: {self.login_email}")
        logger.info(f"  区域: {self.account_region}")
        logger.info("=" * 60)

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
        logger.info("等待页面加载，查找欢迎文字...")

        try:
            page.wait_for_selector('text=Welcome to TikTok Shop Partner Center', timeout=20000)
            logger.info("✓ 找到欢迎文字：Welcome to TikTok Shop Partner Center，页面已加载")
            return True

        except Exception:
            # 第一层没找到，依次检查其他候选词
            try:
                page.wait_for_selector('text=Account GMV trend', timeout=20000)
                logger.info("✓ 找到欢迎文字：Account GMV trend，页面已加载")
                return True

            except Exception:
                try:
                    page.wait_for_selector('text=View your data and facilitate seller authorizations', timeout=20000)
                    logger.info("✓ 找到欢迎文字：View your data and facilitate seller authorizations，页面已加载")
                    return True

                except Exception:
                    try:
                        page.wait_for_selector('text=Hi', timeout=20000)
                        logger.info("✓ 找到欢迎文字：Hi，页面已加载")
                        return True

                    except Exception:
                        logger.warning("未找到任何欢迎文字，页面可能未正确加载")
                        return False
        
    def load_creator_urls(self) -> List[Dict[str, str]]:
        """从creator_db.xlsx读取达人聊天URL列表"""
        logger.info(f"读取达人数据库: {self.creator_db_path}")
        
        try:
            df = pd.read_excel(self.creator_db_path, engine='openpyxl')
            
            # 检查必需的列
            if 'creator_chaturl' not in df.columns:
                logger.error("creator_db.xlsx中缺少creator_chaturl列")
                return []
            
            if 'creator_name' not in df.columns:
                logger.error("creator_db.xlsx中缺少creator_name列")
                return []
            
            # 过滤掉空URL的行
            df = df.dropna(subset=['creator_chaturl'])
            
            creators = []
            for idx, row in df.iterrows():
                creator_dict = {
                    'url': row['creator_chaturl'],
                    'name': row.get('creator_name', f'Unknown_{idx}'),  # 新增
                    'row_index': idx + 2,  # Excel行号(从2开始,仅用于日志)
                    'list_index': idx
                }
                # 如果有region列,也添加进去
                if 'region' in df.columns:
                    creator_dict['region'] = row.get('region', '')
                
                creators.append(creator_dict)
            
            logger.info(f"✓ 成功读取 {len(creators)} 个达人的聊天URL")
            return creators
            
        except Exception as e:
            logger.error(f"读取creator_db.xlsx失败: {e}")
            return []

    def is_creator_already_processed(self, creator_name: str) -> bool:
        """检查指定达人是否已经被处理过"""
        if not getattr(self, "processed_creators", None):
            self.processed_creators = set()
        normalized = str(creator_name).strip()
        return normalized in self.processed_creators

    def open_chat_url(self, page, chat_url: str, max_retries: int = 3) -> bool:
        """根据chat_url直接跳转到聊天页面"""
        logger.info(f"准备跳转聊天页面: {chat_url}")
        
        for attempt in range(1, max_retries + 1):
            logger.info(f"加载聊天页面 - 尝试 {attempt}/{max_retries}")
            try:
                page.goto(chat_url, wait_until="networkidle", timeout=60000)
            except PlaywrightError as e:
                if "Target page, context or browser has been closed" in str(e):
                    logger.error(f"goto 失败（浏览器上下文已关闭）: {e}")
                    raise ChatPageCrashError(str(e))
                logger.error(f"goto 失败: {e}")
                if attempt < max_retries:
                    time.sleep(2)
                    continue
                return False
            
            self.delay(2)
            
            current_url = page.url
            if "login" in current_url.lower() or "signin" in current_url.lower():
                logger.error("被重定向回登录页")
                return False
            
            if self._wait_chat_ready(page, timeout_ms=60000):
                logger.info(f"✓ 聊天页面加载完成")
                return True
            
            if attempt < max_retries:
                logger.warning("未等到聊天输入框，准备重试...")
                try:
                    page.reload(wait_until="networkidle", timeout=40000)
                except Exception:
                    pass
                self.delay(2)
        
        logger.error("多次尝试后仍未成功加载聊天页面")
        return False

    def _wait_chat_ready(self, page, timeout_ms=60000) -> bool:
        """等待聊天页面的输入区域或"Send message"字样可见"""
        logger.info(f"等待聊天输入框或 'Send message' 字样（<= {timeout_ms/1000:.0f}s）...")
        start = time.time()
        check_interval = 1.5

        def found_in_page(p) -> bool:
            selectors = [
                'textarea[placeholder*="Send a message"]',
                'textarea[placeholder*="发送消息"]',
                'textarea[placeholder*="message" i]',
                '#im_sdk_chat_input textarea',
                'textarea'
            ]
            for sel in selectors:
                try:
                    el = p.locator(sel).first
                    if el.count() > 0 and el.is_visible():
                        logger.info(f"✓ 发现输入框：{sel}")
                        return True
                except Exception:
                    pass

            try:
                btn = p.get_by_text("Send message", exact=False)
                if btn and btn.count() > 0 and btn.first.is_visible():
                    logger.info("✓ 发现 'Send message' 文案")
                    return True
            except Exception:
                pass

            return False

        while (time.time() - start) * 1000 < timeout_ms:
            try:
                if found_in_page(page):
                    return True
            except Exception:
                pass

            try:
                for fr in page.frames:
                    try:
                        if found_in_page(fr):
                            logger.info("✓ 在 iframe 中找到输入框/文案")
                            return True
                    except Exception:
                        continue
            except Exception:
                pass

            time.sleep(check_interval)

        logger.warning("等待聊天区域超时")
        return False

    def extract_chat_history(self, page, username: str) -> List[Dict[str, Any]]:
        """提取指定达人的聊天历史记录"""
        logger.info(f"开始提取用户 {username} 的聊天记录...")
        
        self.delay(2)
        
        # 查找聊天消息容器
        chat_container = page.evaluate("""
            () => {
                const selectors = [
                    'div.messageList-k_OG24',
                    'div.chatd-scrollView',
                    'div[class*="messageList"]',
                    'div[class*="chatd-scrollView"]'
                ];
                
                for (const selector of selectors) {
                    const container = document.querySelector(selector);
                    if (container && container.offsetParent !== null) {
                        return selector;
                    }
                }
                return null;
            }
        """)
        
        if not chat_container:
            logger.error(f" 未找到 {username} 的聊天容器")
            return []
        
        logger.info(f"✓ 找到聊天容器: {chat_container}")
        
        # 滚动加载历史消息
        logger.info(f"开始滚动加载 {username} 的历史消息...")
        
        # 先滚动到顶部
        page.evaluate(f"""
            () => {{
                const container = document.querySelector('{chat_container}');
                if (container) {{
                    container.scrollTop = 0;
                }}
            }}
        """)
        self.delay(2)
        
        # 向上滚动多次加载历史消息
        for i in range(50):
            page.evaluate(f"""
                () => {{
                    const container = document.querySelector('{chat_container}');
                    if (container) {{
                        container.scrollTop = container.scrollTop - 300;
                    }}
                }}
            """)
            
            self.delay(0.3)
            
            # 检查是否到达顶部
            is_at_top = page.evaluate(f"""
                () => {{
                    const container = document.querySelector('{chat_container}');
                    if (container) {{
                        return container.scrollTop <= 0;
                    }}
                    return true;
                }}
            """)
            
            if is_at_top:
                logger.info(f"✓ 已滚动到 {username} 聊天记录的顶部 (滚动了 {i+1} 次)")
                break
            
            if (i + 1) % 10 == 0:
                message_count = page.evaluate(f"""
                    () => {{
                        const container = document.querySelector('{chat_container}');
                        if (container) {{
                            const messages = container.querySelectorAll('div[class*="message"], div[class*="bubble"], pre[class*="content"]');
                            return messages.length;
                        }}
                        return 0;
                    }}
                """)
                logger.info(f"已滚动 {i+1} 次，当前找到 {message_count} 条消息")
        
        # 等待消息完全加载
        self.delay(3)
        
        logger.info(f"开始从 {username} 的聊天框中提取消息...")
        
        # 提取消息
        messages = page.evaluate("""
            () => {
                const container = document.querySelector('div.index-module__messageList--GBz6X');
                if (!container) return [];

                const msgNodes = container.querySelectorAll('div.chatd-message');
                const results = [];
                
                msgNodes.forEach((msgNode, idx) => {
                    const isRight = msgNode.className.includes('chatd-message--right');
                    const isLeft = msgNode.className.includes('chatd-message--left');
                    
                    // 获取发送者名称
                    let sender = 'Creator';
                    if (isRight) {
                        sender = 'Merchant';
                    }
                    
                    const isFromMerchant = isRight;
                    const isReply = !isRight;

                    const timeEl = msgNode.querySelector('time.chatd-time');
                    const timestamp = timeEl ? timeEl.textContent.trim() : '';

                    const contentEl = msgNode.querySelector('pre.index-module__content--QKRoB');
                    const content = contentEl ? contentEl.textContent.trim() : '';

                    // 过滤空消息或系统提示
                    if (!content || content.startsWith('im_sdk') || content.length < 2) return;

                    let messageType = 'text';
                    if (content.includes('http')) messageType = 'link';
                    else if (content.includes('[image]')) messageType = 'image';
                    else if (content.includes('[video]')) messageType = 'video';

                    // 检测read状态 - 仅针对商家发送的消息
                    let readStatus = '';
                    if (isFromMerchant) {
                        const statusEl = msgNode.querySelector('span.chatd-message-status-content--read');
                        readStatus = statusEl ? 'TRUE' : 'FALSE';
                    }

                    results.push({
                        message_id: `msg_${idx}_${Date.now()}`,
                        sender_name: sender,
                        content: content,
                        timestamp: timestamp,
                        message_type: messageType,
                        is_from_merchant: isFromMerchant,
                        is_reply: isReply,
                        is_read: readStatus,
                        extracted_at: new Date().toISOString()
                    });
                });

                return results;
            }
        """)
        
        logger.info(f"从用户 {username} 提取到 {len(messages)} 条消息")
        
        if messages:
            logger.info(f"消息预览 (前3条):")
            for i, msg in enumerate(messages[:3]):
                logger.info(f"  {i+1}. [{msg['sender_name']}] {msg['content'][:60]}...")
        
        return messages
    
    def save_final_summary(self, new_messages: List[Dict[str, Any]]) -> str:
        """追加保存新消息到 chat_creator_history.xlsx"""
        if not new_messages:
            logger.warning("没有新消息需要保存")
            return ""
        
        filepath = str(self.history_file_path)
        
        try:
            existing_df, history_exists = self._load_history_dataframe()
            if history_exists:
                logger.info(f"读取现有文件，已有 {len(existing_df)} 条记录")
            else:
                logger.info("历史文件不存在或已重建，创建新文件")
            
            # 新数据
            new_df = pd.DataFrame(new_messages)
            
            # 合并数据
            if not existing_df.empty:
                df = pd.concat([existing_df, new_df], ignore_index=True)
            else:
                df = new_df
            
            # 重新排列列顺序
            preferred_order = [
                'creator_name',  # 改为creator_name在前
                'creator_url',
                'message_id',
                'sender_name',
                'content',
                'timestamp',
                'message_type',
                'is_from_merchant',
                'is_reply',
                'is_read',
                'extracted_at'
            ]
            
            existing_columns = [col for col in preferred_order if col in df.columns]
            other_columns = [col for col in df.columns if col not in preferred_order]
            final_columns = existing_columns + other_columns
            
            df = df[final_columns]
            
            # 保存到Excel
            df.to_excel(filepath, index=False, engine='openpyxl')
            
            logger.info(f"✓ 已追加保存 {len(new_messages)} 条新消息，文件总记录数: {len(df)}")
            
            if 'creator_name' in new_df.columns:
                if not getattr(self, "processed_creators", None):
                    self.processed_creators = set()
                for name in new_df['creator_name'].dropna().astype(str).str.strip().unique():
                    self.processed_creators.add(name)
            
            return filepath
            
        except Exception as e:
            logger.error(f"保存汇总文件失败: {e}")
            return ""
    
    def record_failed_creator(self, creator_name: str, creator_url: str, reason: str) -> None:
        """将无法处理的达人写入历史文件方便排查"""
        logger.warning(f"记录失败达人 {creator_name}: {reason}")
        stub = {
            'creator_name': creator_name,
            'creator_url': creator_url,
            'message_id': '',
            'sender_name': '',
            'content': '',
            'timestamp': '',
            'message_type': '',
            'is_from_merchant': '',
            'is_reply': '',
            'is_read': '',
            'extracted_at': datetime.utcnow().isoformat(),
        }
        self.save_final_summary([stub])
    
    def _process_creators_batch(self, page, creators: List[Dict[str, str]], start_index: int = 0) -> Dict[str, Any]:
        """核心处理逻辑，支持浏览器重启与宕机后的重试"""
        results: Dict[str, int] = {}
        total_messages = 0
        skipped_count = 0
        processed_count = 0
        i = start_index
        pending_creator: Optional[Dict[str, Any]] = None
        pending_index: Optional[int] = None
        waiting_for_retry = False
        retry_in_progress = False

        def finalize_creator(success: bool, from_pending: bool):
            nonlocal processed_count, pending_creator, pending_index, retry_in_progress, waiting_for_retry
            processed_count += 1
            if from_pending:
                pending_creator = None
                pending_index = None
                retry_in_progress = False
            if success and pending_creator and waiting_for_retry and not retry_in_progress:
                retry_in_progress = True
                waiting_for_retry = False

        while i < len(creators) or (retry_in_progress and pending_creator):
            if retry_in_progress and pending_creator:
                creator_info = pending_creator
                current_index = pending_index if pending_index is not None else creator_info.get('list_index', start_index)
                from_pending = True
            else:
                if i >= len(creators):
                    break
                creator_info = creators[i]
                current_index = creator_info.get('list_index', i)
                i += 1
                from_pending = False
            
            chat_url = creator_info['url']
            creator_name = str(creator_info.get('name', f'Unknown_{current_index}'))
            row_index = creator_info.get('row_index', current_index + 2)
            
            logger.info(f"\n{'='*60}")
            logger.info(f"处理达人 {current_index + 1}/{len(creators)}: {creator_name} (Excel第{row_index}行)")
            logger.info(f"URL: {chat_url}")
            if from_pending:
                logger.info("当前达人为上次失败后等待重试的对象")
            logger.info(f"{'='*60}")

            if self.is_creator_already_processed(creator_name):
                logger.info(f"⊗ 达人 {creator_name} 已处理过，跳过")
                results[creator_name] = -1
                skipped_count += 1
                continue

            if (not from_pending) and processed_count > 0 and processed_count % self.restart_interval == 0:
                logger.info("=" * 60)
                logger.info(f"已处理 {processed_count} 个达人，准备重启浏览器...")
                logger.info("=" * 60)
                return {
                    'status': 'need_restart',
                    'processed': processed_count,
                    'results': results,
                    'total_messages': total_messages,
                    'skipped_count': skipped_count,
                    'current_index': current_index
                }

            try:
                load_ok = self.open_chat_url(page, chat_url)
            except ChatPageCrashError as crash_err:
                logger.error(f"✗ 浏览器上下文异常，暂存达人 {creator_name}: {crash_err}")
                if retry_in_progress:
                    logger.warning("重试期间再次失败，准备重启浏览器")
                    return {
                        'status': 'need_restart',
                        'processed': processed_count,
                        'results': results,
                        'total_messages': total_messages,
                        'skipped_count': skipped_count,
                        'current_index': pending_index if pending_index is not None else current_index
                    }
                if pending_creator:
                    logger.warning("连续两个达人无法打开聊天页面，准备重启浏览器")
                    return {
                        'status': 'need_restart',
                        'processed': processed_count,
                        'results': results,
                        'total_messages': total_messages,
                        'skipped_count': skipped_count,
                        'current_index': pending_index if pending_index is not None else current_index
                    }
                pending_creator = creator_info
                pending_index = current_index
                waiting_for_retry = True
                continue

            if not load_ok:
                logger.warning(f"✗ 无法加载聊天页面，准备稍后重试 {creator_name}")
                if from_pending:
                    logger.warning("重试期间仍无法加载，跳过该达人")
                    self.record_failed_creator(creator_name, chat_url, "多次重试后仍无法加载聊天页面")
                    results[creator_name] = 0
                    finalize_creator(True, from_pending)
                    self.delay(2)
                    continue
                if pending_creator:
                    logger.warning("连续两个达人无法加载聊天页面，准备重启浏览器")
                    return {
                        'status': 'need_restart',
                        'processed': processed_count,
                        'results': results,
                        'total_messages': total_messages,
                        'skipped_count': skipped_count,
                        'current_index': pending_index if pending_index is not None else current_index
                    }
                pending_creator = creator_info
                pending_index = current_index
                waiting_for_retry = True
                continue

            try:
                messages = self.extract_chat_history(page, creator_name)
            except Exception as e:
                logger.error(f"✗ 提取聊天记录时出错: {e}")
                results[creator_name] = 0
                finalize_creator(False, from_pending)
                self.delay(2)
                continue

            if messages:
                for msg in messages:
                    msg['creator_name'] = creator_name
                    msg['creator_url'] = chat_url
                
                self.save_final_summary(messages)
                
                results[creator_name] = len(messages)
                total_messages += len(messages)
                logger.info(f"✓ 成功提取并保存 {len(messages)} 条消息")
            else:
                logger.warning(f"✗ 没有提取到消息")
                results[creator_name] = 0
                if not getattr(self, "processed_creators", None):
                    self.processed_creators = set()
                self.processed_creators.add(creator_name.strip())

            finalize_creator(True, from_pending)
            self.delay(2)

        if pending_creator:
            logger.warning("仍有等待重试的达人，准备重启浏览器")
            return {
                'status': 'need_restart',
                'processed': processed_count,
                'results': results,
                'total_messages': total_messages,
                'skipped_count': skipped_count,
                'current_index': pending_index if pending_index is not None else start_index
            }

        return {
            'status': 'completed',
            'processed': processed_count,
            'results': results,
            'total_messages': total_messages,
            'skipped_count': skipped_count
        }

    def extract_all_chat_history_from_urls(self, page) -> Dict[str, int]:
        """根据creator_db.xlsx中的URL逐个提取聊天记录"""
        logger.info("=" * 60)
        logger.info("开始根据URL列表提取所有达人的聊天历史记录")
        logger.info("=" * 60)
        
        creators = self.load_creator_urls()
        if not creators:
            logger.error("✗ 未读取到任何达人URL")
            return {}
        
        result = self._process_creators_batch(page, creators, start_index=0)
        
        if result.get('status') == 'completed':
            logger.info("\n" + "=" * 60)
            logger.info("提取完成！统计信息：")
            logger.info("=" * 60)
            logger.info(f"总达人数: {len(creators)}")
            logger.info(f"已跳过(重复): {result.get('skipped_count', 0)}")
            logger.info(f"成功提取: {sum(1 for v in result.get('results', {}).values() if v > 0)}")
            logger.info(f"提取失败: {sum(1 for v in result.get('results', {}).values() if v == 0)}")
            logger.info(f"总消息数: {result.get('total_messages', 0)}")
            logger.info("=" * 60)
        
        return result

    def extract_all_chat_history_from_urls_with_restart(self, page, start_index: int = 0) -> Dict:
        """根据creator_db.xlsx中的URL逐个提取聊天记录（支持从指定位置开始）"""
        logger.info("=" * 60)
        logger.info(f"开始提取聊天历史记录（从第 {start_index + 1} 个达人开始）")
        logger.info("=" * 60)
        
        creators = self.load_creator_urls()
        if not creators:
            logger.error("✗ 未读取到任何达人URL")
            return {'status': 'completed', 'results': {}, 'total_messages': 0, 'skipped_count': 0}
        
        result = self._process_creators_batch(page, creators, start_index=start_index)
        
        if result.get('status') == 'completed':
            logger.info("\n" + "=" * 60)
            logger.info("本轮提取完成！")
            logger.info("=" * 60)
        
        return result

    def run(self) -> bool:
        """运行登录 + 提取所有达人聊天记录（支持自动重启）"""
        logger.info("=" * 50)
        logger.info("TikTok Chat History Crawler - URL Based")
        logger.info("=" * 50)
        
        # 根据Excel的region选择账号
        self.setup_account_by_region()
        
        start_index = 0  # 从第几个达人开始处理
        all_results = {}
        total_messages_all = 0
        total_skipped_all = 0
        result: Dict[str, Any] = {
            'status': 'failed',
            'results': {},
            'total_messages': 0,
            'skipped_count': 0,
            'current_index': start_index,
        }
        
        while True:
            with sync_playwright() as p:
                try:
                    logger.info(f"\n启动浏览器（从第 {start_index + 1} 个达人开始）...")
                    self.browser = p.chromium.launch(headless=True, timeout=60000)
                    self.context = self.browser.new_context(viewport={'width': 1920, 'height': 1080})
                    self.context.set_default_timeout(60000)
                    self.page = self.context.new_page()

                    # 登录 + 欢迎页检查
                    max_login_attempts = 3
                    login_success = False
                    
                    for attempt in range(1, max_login_attempts + 1):
                        logger.info(f"=== 登录流程尝试 {attempt}/{max_login_attempts} ===")
                        if not self.login(self.page):
                            logger.error("登录失败")
                        else:
                            if self.check_welcome_page(self.page):
                                logger.info("✓ 登录并进入欢迎页面成功")
                                login_success = True
                                break
                            else:
                                logger.warning("未找到欢迎页面，将重新开始登录")
                        
                        if attempt < max_login_attempts:
                            try:
                                self.page.goto("https://partner-sso.tiktok.com/account/login", wait_until="networkidle")
                                self.delay(3)
                            except:
                                pass
                    
                    if not login_success:
                        logger.error("多次尝试后仍未登录成功，程序终止")
                        return False

                    # 开始根据URL列表提取聊天记录（从start_index开始）
                    result = self.extract_all_chat_history_from_urls_with_restart(
                        self.page, 
                        start_index=start_index
                    )
                    
                    # 累计统计
                    if 'results' in result:
                        all_results.update(result['results'])
                    if 'total_messages' in result:
                        total_messages_all += result['total_messages']
                    if 'skipped_count' in result:
                        total_skipped_all += result['skipped_count']
                    
                    # 检查是否需要重启
                    if result.get('status') == 'need_restart':
                        start_index = result.get('current_index', 0)
                        logger.info(f"准备重启浏览器，下次从第 {start_index + 1} 个达人继续...")
                        # 关闭当前浏览器，循环会重新启动
                    elif result.get('status') == 'completed':
                        logger.info("=" * 50)
                        logger.info("✓ 所有达人的聊天记录提取完成")
                        logger.info(f"  总计处理: {len(all_results)} 个达人")
                        logger.info(f"  总计消息: {total_messages_all} 条")
                        logger.info(f"  总计跳过: {total_skipped_all} 个")
                        logger.info("=" * 50)
                        return True
                    
                except Exception as e:
                    logger.error(f"程序运行出错: {e}")
                    return False
                finally:
                    self._close_playwright_obj(self.page, "页面")
                    self._close_playwright_obj(self.context, "浏览器上下文")
                    self._close_playwright_obj(self.browser, "浏览器")
                    logger.info("浏览器已关闭")
                    
                    # 如果不需要重启，退出循环
                    if result.get('status') == 'completed':
                        break

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="TikTok Chat History Crawler")
    parser.add_argument(
        "--creator-db",
        type=str,
        default=None,
        help="自定义 creator_db.xlsx 路径，未提供时使用 data/creator_db.xlsx",
    )
    parser.add_argument(
        "--restart-interval",
        type=int,
        default=300,
        help="每处理多少个达人后重启浏览器，默认 300",
    )
    parser.add_argument(
        "--history-file",
        type=str,
        default=None,
        help="自定义聊天记录输出xlsx，未提供时使用 data/chat_history_data/chat_creator_history.xlsx",
    )
    parser.add_argument(
        "--accounts-config",
        type=str,
        default=None,
        help="账号配置JSON路径，未提供时使用 config/accounts.json",
    )
    parser.add_argument(
        "--account-name",
        type=str,
        default=None,
        help="强制使用指定名称的账号（需在配置中开启 enabled）",
    )
    args = parser.parse_args()

    crawler = ChatHistoryCrawler(
        restart_interval=args.restart_interval,
        creator_db_path=args.creator_db,
        history_file_path=args.history_file,
        accounts_config_path=args.accounts_config,
        account_name=args.account_name,
    )
    crawler.run()
