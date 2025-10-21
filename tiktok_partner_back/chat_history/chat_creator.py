"""
TikTok Chat History Crawler 
根据creator_db.xlsx逐个爬取聊天记录
"""
import logging
import time
import sys
import os
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


class ChatHistoryCrawler:
    """
    TikTok聊天记录爬虫
    支持提取Unread消息的历史记录
    """
    
    def __init__(self, account_info=None, restart_interval=300):
        # 支持传入账号信息
        self.accounts_config = {
            "accounts": [
                {
                    "name": "账号1-MX",
                    "login_email": "tiktokshopinfoundtest@gmail.com",
                    "login_password": "fyvbyn-hyctu0-Rafqyp",
                    "gmail_username": "tiktokshopinfoundtest@gmail.com",
                    "gmail_app_password": "cfhlfedjqhfbbbhb",
                    "region": "MX",
                    "enabled": True,
                    "notes": "MX区域账号"
                },
                {
                    "name": "账号2-FR",
                    "login_email": "tiktokinfoundfrance@gmail.com",
                    "login_password": "dyvvac-coqnYp-sespo0",
                    "gmail_username": "tiktokinfoundfrance@gmail.com",
                    "gmail_app_password": "gnseoovwafbstjbt",
                    "region": "FR",
                    "enabled": True,
                    "notes": "FR区域账号"
                }
            ]
        }
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

        # Gmail验证码配置
        self.gmail_verifier = GmailVerificationCode(
            username=self.gmail_username,
            app_password=self.gmail_app_password
        )
        
        self.browser = None
        self.context = None
        self.page = None
        self.csv_data_dir = "data/chat_history_data"
        self.creator_db_path = "data/creator_db.xlsx"
        
        # 确保目录存在
        os.makedirs(self.csv_data_dir, exist_ok=True)
        self.restart_interval = restart_interval  # 每处理多少个达人后重启
        logger.info(f"浏览器重启间隔设置为: 每 {self.restart_interval} 个达人")

    
    def delay(self, seconds: float):
        """延迟"""
        time.sleep(seconds)

    def get_region_from_excel(self) -> str:
        """从creator_db.xlsx读取第一行的region列"""
        logger.info(f"读取Excel第一行的region列...")
        
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

    def setup_account_by_region(self):
        """根据Excel的region自动设置账号"""
        region = self.get_region_from_excel()
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
        
        try:
            page.wait_for_selector('text=Welcome to TikTok Shop Partner Center', timeout=20000)
            logger.info(f"✓ 找到欢迎文字，页面已加载")
            return True
        except Exception:
            logger.warning(f"未找到欢迎文字")
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
                    'row_index': idx + 2  # Excel行号(从2开始,仅用于日志)
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
        filepath = os.path.join(self.csv_data_dir, "chat_creator_history.xlsx")
        
        if not os.path.exists(filepath):
            return False
        
        try:
            df = pd.read_excel(filepath, engine='openpyxl')
            
            if 'creator_name' not in df.columns or len(df) == 0:
                return False
            
            # 检查creator_name是否存在
            return creator_name in df['creator_name'].values
            
        except Exception as e:
            logger.error(f"检查达人时出错: {e}")
            return False

    def open_chat_url(self, page, chat_url: str, max_retries: int = 3) -> bool:
        """根据chat_url直接跳转到聊天页面"""
        logger.info(f"准备跳转聊天页面: {chat_url}")
        
        for attempt in range(1, max_retries + 1):
            logger.info(f"加载聊天页面 - 尝试 {attempt}/{max_retries}")
            try:
                page.goto(chat_url, wait_until="networkidle", timeout=60000)
            except Exception as e:
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
        
        filepath = os.path.join(self.csv_data_dir, "chat_creator_history.xlsx")
        
        try:
            # 读取现有数据（如果文件存在）
            if os.path.exists(filepath):
                existing_df = pd.read_excel(filepath, engine='openpyxl')
                logger.info(f"读取现有文件，已有 {len(existing_df)} 条记录")
            else:
                existing_df = pd.DataFrame()
                logger.info("创建新文件")
            
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
            
            return filepath
            
        except Exception as e:
            logger.error(f"保存汇总文件失败: {e}")
            return ""

    def extract_all_chat_history_from_urls(self, page) -> Dict[str, int]:
        """根据creator_db.xlsx中的URL逐个提取聊天记录"""
        logger.info("=" * 60)
        logger.info("开始根据URL列表提取所有达人的聊天历史记录")
        logger.info("=" * 60)
        
        # 读取达人URL列表
        creators = self.load_creator_urls()
        
        if not creators:
            logger.error("✗ 未读取到任何达人URL")
            return {}
        
        results = {}
        total_messages = 0
        skipped_count = 0
        processed_count = 0  # 新增：已处理计数器（不含跳过）
        
        for i, creator_info in enumerate(creators):
            chat_url = creator_info['url']
            creator_name = creator_info['name']
            row_index = creator_info['row_index']
            
            logger.info(f"\n{'='*60}")
            logger.info(f"处理达人 {i+1}/{len(creators)}: {creator_name} (Excel第{row_index}行)")
            logger.info(f"URL: {chat_url}")
            logger.info(f"{'='*60}")
            
            # 检查达人是否已处理
            if self.is_creator_already_processed(creator_name):
                logger.info(f"⊗ 达人 {creator_name} 已处理过，跳过")
                results[creator_name] = -1
                skipped_count += 1
                continue
            
            # 检查是否需要重启浏览器
            if processed_count > 0 and processed_count % self.restart_interval == 0:
                logger.info("=" * 60)
                logger.info(f"已处理 {processed_count} 个达人，准备重启浏览器...")
                logger.info("=" * 60)
                return {
                    'status': 'need_restart',
                    'processed': processed_count,
                    'results': results,
                    'total_messages': total_messages,
                    'skipped_count': skipped_count,
                    'current_index': i  # 当前处理到的索引
                }
            
            try:
                # 1. 跳转到聊天页面
                if not self.open_chat_url(page, chat_url):
                    logger.warning(f"✗ 无法加载聊天页面，跳过")
                    results[creator_name] = 0
                    processed_count += 1
                    continue
                
                # 2. 提取聊天历史记录
                messages = self.extract_chat_history(page, creator_name)
                
                # 3. 处理并保存消息
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
                
                processed_count += 1
                self.delay(2)
                
            except Exception as e:
                logger.error(f"✗ 处理达人时出错: {e}")
                results[creator_name] = 0
                processed_count += 1
                continue
        
        # 输出统计信息
        logger.info("\n" + "=" * 60)
        logger.info("提取完成！统计信息：")
        logger.info("=" * 60)
        logger.info(f"总达人数: {len(creators)}")
        logger.info(f"已跳过(重复): {skipped_count}")
        logger.info(f"成功提取: {sum(1 for v in results.values() if v > 0)}")
        logger.info(f"提取失败: {sum(1 for v in results.values() if v == 0)}")
        logger.info(f"总消息数: {total_messages}")
        logger.info("=" * 60)
        
        return {
            'status': 'completed',
            'results': results,
            'total_messages': total_messages,
            'skipped_count': skipped_count
        }

    def extract_all_chat_history_from_urls_with_restart(self, page, start_index: int = 0) -> Dict:
        """根据creator_db.xlsx中的URL逐个提取聊天记录（支持从指定位置开始）"""
        logger.info("=" * 60)
        logger.info(f"开始提取聊天历史记录（从第 {start_index + 1} 个达人开始）")
        logger.info("=" * 60)
        
        # 读取达人URL列表
        creators = self.load_creator_urls()
        
        if not creators:
            logger.error("✗ 未读取到任何达人URL")
            return {'status': 'completed', 'results': {}, 'total_messages': 0, 'skipped_count': 0}
        
        results = {}
        total_messages = 0
        skipped_count = 0
        processed_count = 0
        
        # 从start_index开始处理
        for i in range(start_index, len(creators)):
            creator_info = creators[i]
            chat_url = creator_info['url']
            creator_name = creator_info['name']
            row_index = creator_info['row_index']
            
            logger.info(f"\n{'='*60}")
            logger.info(f"处理达人 {i+1}/{len(creators)}: {creator_name} (Excel第{row_index}行)")
            logger.info(f"URL: {chat_url}")
            logger.info(f"{'='*60}")
            
            # 检查达人是否已处理
            if self.is_creator_already_processed(creator_name):
                logger.info(f"⊗ 达人 {creator_name} 已处理过，跳过")
                results[creator_name] = -1
                skipped_count += 1
                continue
            
            # 检查是否需要重启浏览器（从start_index开始计数）
            if processed_count > 0 and processed_count % self.restart_interval == 0:
                logger.info("=" * 60)
                logger.info(f"已处理 {processed_count} 个达人（本轮），准备重启浏览器...")
                logger.info("=" * 60)
                return {
                    'status': 'need_restart',
                    'processed': processed_count,
                    'results': results,
                    'total_messages': total_messages,
                    'skipped_count': skipped_count,
                    'current_index': i
                }
            
            try:
                if not self.open_chat_url(page, chat_url):
                    logger.warning(f"✗ 无法加载聊天页面，跳过")
                    results[creator_name] = 0
                    processed_count += 1
                    continue
                
                messages = self.extract_chat_history(page, creator_name)
                
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
                
                processed_count += 1
                self.delay(2)
                
            except Exception as e:
                logger.error(f"✗ 处理达人时出错: {e}")
                results[creator_name] = 0
                processed_count += 1
                continue
        
        logger.info("\n" + "=" * 60)
        logger.info("本轮提取完成！")
        logger.info("=" * 60)
        
        return {
            'status': 'completed',
            'results': results,
            'total_messages': total_messages,
            'skipped_count': skipped_count
        }

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
                    if self.page:
                        self.page.close()
                    if self.context:
                        self.context.close()
                    if self.browser:
                        self.browser.close()
                    logger.info("浏览器已关闭")
                    
                    # 如果不需要重启，退出循环
                    if result.get('status') == 'completed':
                        break

if __name__ == '__main__':
    # 可以自定义重启间隔，默认300
    restart_interval = 300  # 每处理300个达人重启一次
    crawler = ChatHistoryCrawler(restart_interval=restart_interval)
    crawler.run()