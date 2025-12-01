"""
TikTok Chat History Crawler, with Unread Messages
TikTok聊天记录爬虫，提取Unread消息
"""
import logging
import time
import sys
import os
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any
from playwright.sync_api import sync_playwright

# Ensure imports resolve when running as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.email_code import GmailVerificationCode
from utils.credentials import get_default_account_from_env, MissingDefaultAccountError

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ChatHistoryCrawler:
    """
    TikTok聊天记录爬虫
    支持提取Unread消息的历史记录
    """
    
    def __init__(self, account_info=None):
        # Accept caller supplied credentials or load them from the environment
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
            logger.warning("Account info not provided; using fallback credentials defined via environment variables.")

        # Gmail验证码配置
        self.gmail_verifier = GmailVerificationCode(
            username=self.gmail_username,
            app_password=self.gmail_app_password
        )
        
        self.browser = None
        self.context = None
        self.page = None
        self.csv_data_dir = "data/chat_history_data"
        
        # 确保目录存在
        os.makedirs(self.csv_data_dir, exist_ok=True)
        self.all_messages = []
    
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

    def open_chat_and_screenshot(self, page, partner_id: str, creator_id: str,
                                max_retries: int = 3) -> bool:
        """跳转到聊天页面，等待加载完成"""
        if not partner_id or not creator_id:
            logger.error("缺少 partner_id 或 creator_id")
            return False

        chat_url = (
            f"https://partner.tiktokshop.com/partner/im"
            f"?shop_id={partner_id}&creator_id={creator_id}&market=19&enter_from=find_creator_detail"
        )
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
                logger.error("被重定向回登录页，需先确保登录状态")
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

    def open_unread_and_screenshot(self, page, timeout: int = 10000) -> bool:
        """点击左侧菜单的 Unread 项，进入未读消息界面"""
        xpath_unread = '//*[@id="arco-menu-0-submenu-inline-0"]/div[3]'
        logger.info("尝试点击左侧菜单的 Unread 项...")

        try:
            elem = page.wait_for_selector(xpath_unread, timeout=timeout)
            if not elem:
                logger.error("未找到 Unread 元素")
                return False

            elem.click()
            logger.info("✓ 成功点击 Unread，进入未读消息界面")
            self.delay(2)
            return True

        except Exception as e:
            logger.error(f"点击 Unread 失败: {e}")
            return False

    def get_unread_influencers(self, page) -> List[str]:
        """获取Unread页面中的所有达人用户名列表"""
        logger.info("获取Unread页面中的所有达人用户名列表...")
        
        influencers = page.evaluate("""
            () => {
                const influencers = [];
                
                // 根据实际HTML结构，查找用户名
                // 用户名在 <div data-e2e="d68af21d-3c6e-4aa9" class="index-module__uname--xxx">
                const usernameSelectors = [
                    'div[data-e2e="d68af21d-3c6e-4aa9"]',  // 精确匹配data-e2e
                    'div[class*="__uname--"]',              // 类名包含__uname--
                    'div.index-module__uname--iEOPo'        // 完整类名（备用）
                ];
                
                usernameSelectors.forEach(selector => {
                    const elements = document.querySelectorAll(selector);
                    elements.forEach(el => {
                        const username = el.textContent?.trim();
                        if (username && username.length > 0 && !influencers.includes(username)) {
                            // 排除"Not replied"等UI文本
                            if (!username.includes('Not replied') && 
                                !username.includes('AM') && 
                                !username.includes('PM') &&
                                !username.includes(':')) {
                                influencers.push(username);
                            }
                        }
                    });
                });
                
                console.log(`找到 ${influencers.length} 个未读达人:`, influencers);
                return influencers;
            }
        """)
        
        logger.info(f" 找到 {len(influencers)} 个未读达人: {influencers}")
        return influencers

    def click_influencer(self, page, username: str) -> bool:
        """点击指定达人进入聊天界面"""
        logger.info(f"尝试点击达人: {username}")
        
        try:
            # 根据实际HTML结构，点击包含用户名的整个联系人卡片
            # 用户名在 contactCard 内，点击整个 contactCard
            user_element = page.locator(f'div[data-e2e="d68af21d-3c6e-4aa9"]:has-text("{username}")').first
            
            if user_element.count() > 0:
                logger.info(f"找到用户 {username} 的元素")
                user_element.scroll_into_view_if_needed()
                self.delay(1)
                
                # 点击用户名所在的整个卡片区域
                # 向上查找到 contactCard 再点击
                contact_card = user_element.locator('xpath=ancestor::div[@data-e2e="1102f017-9923-1b0c"]').first
                if contact_card.count() > 0:
                    contact_card.click()
                    logger.info(f"✓ 成功点击用户 {username} 的联系人卡片")
                else:
                    # 如果找不到父级卡片，直接点击用户名
                    user_element.click()
                    logger.info(f"✓ 成功点击用户 {username}")
                
                self.delay(3)  # 等待聊天界面加载
                return True
            else:
                logger.error(f"未找到用户 {username}")
                return False
                
        except Exception as e:
            logger.error(f"点击用户失败: {e}")
            return False

    def wait_for_chat_ready(self, page, username: str, timeout_seconds: int = 30) -> bool:
        """等待聊天界面准备就绪"""
        logger.info(f"等待 {username} 的聊天界面准备就绪...")
        
        for i in range(timeout_seconds):
            self.delay(1)
            
            # 检查聊天容器是否出现
            has_chat_container = page.evaluate("""
                () => {
                    const containers = [
                        'div.messageList-k_OG24',
                        'div.chatd-scrollView',
                        'div[class*="messageList"]',
                        'div[class*="chat"]',
                        'textarea[placeholder*="message"]'
                    ];
                    
                    for (const selector of containers) {
                        const element = document.querySelector(selector);
                        if (element && element.offsetParent !== null) {
                            return true;
                        }
                    }
                    return false;
                }
            """)
            
            if has_chat_container:
                logger.info(f" {username} 的聊天界面已准备就绪 (等待了 {i+1} 秒)")
                return True
        
        logger.warning(f" {username} 的聊天界面加载超时")
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
        messages = page.evaluate(f"""
            () => {{
                const username = "{username}";
                const container = document.querySelector('div.index-module__messageList--GBz6X');
                if (!container) return [];

                const msgNodes = container.querySelectorAll('div.chatd-message');
                const results = [];
                msgNodes.forEach((msgNode, idx) => {{
                    const isRight = msgNode.className.includes('chatd-message--right');
                    const isLeft = msgNode.className.includes('chatd-message--left');
                    const sender = isRight ? 'Merchant' : username;
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

                    results.push({{
                        message_id: `${{username}}_${{idx}}_${{Date.now()}}`,
                        sender_name: sender,
                        content: content,
                        timestamp: timestamp,
                        message_type: messageType,
                        is_from_merchant: isFromMerchant,
                        is_reply: isReply,
                        extracted_at: new Date().toISOString()
                    }});
                }});

                return results;
            }}
        """)
        
        logger.info(f"从用户 {username} 提取到 {len(messages)} 条消息")
        
        if messages:
            logger.info(f"消息预览 (前3条):")
            for i, msg in enumerate(messages[:3]):
                logger.info(f"  {i+1}. [{msg['sender_name']}] {msg['content'][:60]}...")
        
        return messages

    def save_messages_to_csv(self, messages: List[Dict[str, Any]], username: str) -> str:
        """保存消息到CSV文件，并添加到汇总列表"""
        if not messages:
            logger.warning(f"用户 {username} 没有消息可保存")
            return ""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{username}_unread_messages_{timestamp}.xlsx"
        filepath = os.path.join(self.csv_data_dir, filename)
        
        try:
            # 1. 保存单个达人的文件
            df = pd.DataFrame(messages)
            df.to_excel(filepath, index=False, engine='openpyxl')
            logger.info(f"✓ 用户 {username} 的 {len(messages)} 条消息已保存到XLSX: {filepath}")
            
            # 2. 添加到汇总列表（为每条消息添加达人标识）
            for msg in messages:
                msg['creator_name'] = username  # 添加达人用户名字段
            self.all_messages.extend(messages)
            
            return filepath
            
        except Exception as e:
            logger.error(f"保存消息到CSV失败: {e}")
            return ""

    def save_summary_excel(self) -> str:
        """将所有达人的消息汇总保存到一个XLSX文件"""
        if not self.all_messages:
            logger.warning("没有消息可汇总")
            return ""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"all_unread_messages_summary_{timestamp}.xlsx"
        filepath = os.path.join(self.csv_data_dir, filename)
        
        try:
            # 调整字段顺序，让达人用户名在前面
            df = pd.DataFrame(self.all_messages)
            
            # 重新排列列顺序（如果字段存在）
            preferred_order = [
                'creator_name',
                'message_id',
                'sender_name',
                'content',
                'timestamp',
                'message_type',
                'is_from_merchant',
                'is_reply',
                'extracted_at'
            ]
            
            # 只保留存在的列
            existing_columns = [col for col in preferred_order if col in df.columns]
            other_columns = [col for col in df.columns if col not in preferred_order]
            final_columns = existing_columns + other_columns
            
            df = df[final_columns]
            
            # 保存到Excel
            df.to_excel(filepath, index=False, engine='openpyxl')
            
            logger.info("=" * 60)
            logger.info(f"✓ 汇总文件已保存！")
            logger.info(f"  文件路径: {filepath}")
            logger.info(f"  总消息数: {len(self.all_messages)}")
            logger.info(f"  涉及达人: {len(set(msg['influencer_username'] for msg in self.all_messages))}")
            logger.info("=" * 60)
            
            return filepath
            
        except Exception as e:
            logger.error(f"保存汇总文件失败: {e}")
            return ""

    def extract_all_unread_messages(self, page) -> Dict[str, int]:
        """提取所有未读达人的聊天历史记录"""
        logger.info("=" * 60)
        logger.info("开始提取所有未读达人的聊天历史记录")
        logger.info("=" * 60)
        
        # 重置汇总列表（如果多次调用此方法）
        self.all_messages = []
        
        # 获取所有未读达人列表
        influencers = self.get_unread_influencers(page)
        
        if not influencers:
            logger.error("✗ 未找到任何未读达人")
            return {}
        
        results = {}
        total_messages = 0
        
        for i, influencer in enumerate(influencers):
            logger.info(f"\n{'='*60}")
            logger.info(f"处理达人 {i+1}/{len(influencers)}: {influencer}")
            logger.info(f"{'='*60}")
            
            try:
                # 1. 点击达人
                if not self.click_influencer(page, influencer):
                    logger.warning(f"✗ 无法点击达人 {influencer}，跳过")
                    results[influencer] = 0
                    continue
                
                # 2. 等待聊天界面准备就绪
                if not self.wait_for_chat_ready(page, influencer):
                    logger.warning(f"✗ {influencer} 的聊天界面未准备就绪，跳过")
                    results[influencer] = 0
                    continue
                
                # 3. 提取聊天历史记录
                messages = self.extract_chat_history(page, influencer)
                
                # 4. 保存消息（会自动添加到汇总列表）
                if messages:
                    self.save_messages_to_csv(messages, influencer)
                    results[influencer] = len(messages)
                    total_messages += len(messages)
                    logger.info(f"✓ {influencer}: 成功提取 {len(messages)} 条消息")
                else:
                    logger.warning(f"✗ {influencer}: 没有提取到消息")
                    results[influencer] = 0
                
                # 短暂延迟
                self.delay(2)
                
            except Exception as e:
                logger.error(f"✗ 处理达人 {influencer} 时出错: {e}")
                results[influencer] = 0
                continue
        
        # 保存汇总文件
        logger.info("\n" + "=" * 60)
        logger.info("开始保存汇总文件...")
        logger.info("=" * 60)
        self.save_summary_excel()
        
        # 输出统计信息
        logger.info("\n" + "=" * 60)
        logger.info("提取完成！统计信息：")
        logger.info("=" * 60)
        logger.info(f"总达人数: {len(influencers)}")
        logger.info(f"成功提取: {sum(1 for v in results.values() if v > 0)}")
        logger.info(f"提取失败: {sum(1 for v in results.values() if v == 0)}")
        logger.info(f"总消息数: {total_messages}")
        logger.info("=" * 60)
        
        return results
        

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

                # 进入聊天页面
                partner_id = "8652450495614453520"
                creator_id = "7493998775814425134"
                logger.info("步骤3: 先进入聊天页面（IM界面）")

                success = self.open_chat_and_screenshot(
                    self.page,
                    partner_id=partner_id,
                    creator_id=creator_id,
                    max_retries=3
                )

                if not success:
                    logger.error("聊天页面未成功加载")
                    return False

                # 进入Unread页面
                success = self.open_unread_and_screenshot(self.page)
                if not success:
                    logger.warning("未能进入 Unread 界面")
                    return False
                
                logger.info("✓ 已进入 Unread 界面，开始提取所有未读达人的聊天记录")
                
                # 提取所有未读达人的聊天历史记录
                results = self.extract_all_unread_messages(self.page)
                
                logger.info("=" * 50)
                logger.info(" 所有未读达人的聊天记录提取完成")
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

if __name__ == '__main__':
    crawler = ChatHistoryCrawler()
    crawler.run()
