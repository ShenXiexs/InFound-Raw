"""
TikTok Chat Send and Product Card
TikTok发送聊天信息与商品卡
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


class CardSender:
    """
    TikTok发送聊天信息与商品卡
    """
    
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
        self.send_records = []
    
    def delay(self, seconds: float):
        """延迟"""
        time.sleep(seconds)
    
    def load_card_send_data(self) -> List[Dict[str, Any]]:
        """从JSON文件加载发送卡片的数据（支持单个或列表）"""
        json_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data', 'card', 'card_send_list.json'
        )
        logger.info(f"读取配置文件: {json_path}")
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                import json
                data = json.load(f)
                
                # 统一转为列表格式
                if isinstance(data, dict):
                    data = [data]
                
                logger.info(f"成功加载 {len(data)} 个达人配置")
                return data
        except Exception as e:
            logger.error(f"读取JSON文件失败: {e}")
            return []

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
            logger.info(f"找到欢迎文字，页面已加载")
            return True
        except Exception:
            logger.warning(f"未找到欢迎文字")
            return False

    def navigate_to_campaign_page(self, page, creator_id: str) -> bool:
        """跳转到活动页面（最多3次重试）"""
        logger.info("跳转到活动页面...")

        campaign_url = "https://partner.tiktokshop.com/affiliate-campaign/campaign?"

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"第 {attempt}/{max_retries} 次尝试跳转活动页面...")
                page.goto(campaign_url, wait_until="networkidle", timeout=15000)
                self.delay(3)

                # 等待特征文本出现
                page.wait_for_selector('text=Start an affiliate campaign in 3 steps', timeout=20000)
                logger.info("活动页面已加载")
                return True

            except Exception as e:
                logger.error(f"跳转活动页面失败（尝试 {attempt}/{max_retries}）：{e}")
                if attempt < max_retries:
                    wait_time = 3 * attempt
                    logger.warning(f"等待 {wait_time}s 后重试...")
                    self.delay(wait_time)
                else:
                    logger.error("已达到最大重试次数，跳转活动页面失败")
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
                        logger.info(f"发现输入框：{sel}")
                        return True
                except Exception:
                    pass

            try:
                btn = p.get_by_text("Send message", exact=False)
                if btn and btn.count() > 0 and btn.first.is_visible():
                    logger.info("发现 'Send message' 文案")
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
                            logger.info("在 iframe 中找到输入框/文案")
                            return True
                    except Exception:
                        continue
            except Exception:
                pass

            time.sleep(check_interval)

        logger.warning("等待聊天区域超时")
        return False

    def open_chat_and_screenshot(self, page, creator_id: str,
                                max_retries: int = 3) -> bool:
        """跳转到聊天页面，等待加载完成"""
        if not creator_id:
            logger.error("缺少 creator_id")
            return False

        chat_url = (
            f"https://partner.tiktokshop.com/partner/im"
            f"?creator_id={creator_id}&market=19&enter_from=find_creator_detail"
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
                logger.info(f"聊天页面加载完成")
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

    def check_and_send_message(self, page, message: str) -> bool:
        """检查消息历史并发送消息（如果不存在）"""
        if not message or not message.strip():
            logger.info("没有消息内容，跳过")
            return False
        
        message = message.strip()
        logger.info("检查消息历史并准备发送...")
        
        try:
            # 等待聊天消息加载
            page.wait_for_load_state("networkidle")
            self.delay(3)
            
            # 查找聊天消息容器
            chat_container = page.evaluate("""
                () => {
                    const selectors = [
                        'div.index-module__messageList--GBz6X',
                        'div.messageList-k_OG24',
                        'div.chatd-scrollView',
                        'div[class*="messageList"]'
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
            
            # 提取历史消息
            messages = []
            if chat_container:
                messages = page.evaluate(f"""
                    () => {{
                        const container = document.querySelector('{chat_container}');
                        if (!container) return [];

                        const msgNodes = container.querySelectorAll('div.chatd-message');
                        const results = [];
                        
                        msgNodes.forEach(msgNode => {{
                            const contentEl = msgNode.querySelector('pre.index-module__content--QKRoB');
                            const content = contentEl ? contentEl.textContent.trim() : '';
                            if (content && content.length >= 2) {{
                                results.push(content);
                            }}
                        }});
                        
                        return results;
                    }}
                """)
            
            logger.info(f"找到 {len(messages)} 条历史消息")
            
            # 检查消息是否已存在
            if message in messages:
                logger.info("消息已存在于聊天历史中，跳过发送")
                return False
            
            logger.info("消息不存在，开始填充...")
            
            # 填充消息
            selectors = [
                'textarea#imTextarea',
                'textarea[placeholder="Send a message"]',
                'textarea[placeholder*="Send a message"]',
                'textarea[placeholder*="message" i]',
                '#im_sdk_chat_input textarea',
                'div[data-e2e="cda68c25-5112-89c2"] textarea',
                'textarea.index-module__textarea--qYh62',
                'textarea'
            ]
            
            for sel in selectors:
                try:
                    el = page.locator(sel).first
                    if el.count() > 0:
                        el.wait_for(state="visible", timeout=5000)
                        el.click()
                        self.delay(0.5)
                        
                        el.fill(message)
                        logger.info("消息已填入输入框")
                        
                        # 自动发送
                        self.delay(0.5)  # 填充后等待
                        el.press("Enter")
                        logger.info("消息已发送")
                        return True
                except Exception as e:
                    logger.debug(f"尝试选择器 {sel} 失败：{e}")
            
            logger.warning("未能填入消息")
            return False
            
        except Exception as e:
            logger.error(f"检查/发送消息失败: {e}")
            return False
    
    def search_and_open_campaign(self, page, campaign_id: str) -> bool:
        """搜索并打开指定的活动"""
        logger.info(f"搜索活动ID: {campaign_id}")
        
        try:
            # 定位搜索框并输入
            search_input = page.locator('input[data-tid="m4b_input_search"]').first
            search_input.wait_for(state="visible", timeout=10000)
            search_input.click()
            self.delay(0.5)
            
            search_input.fill(campaign_id)
            logger.info(f"已输入活动ID: {campaign_id}")
            
            # 按回车搜索
            search_input.press("Enter")
            logger.info("已按回车搜索")
            self.delay(3)
            
            # 点击 View details
            view_details_link = page.locator('span.arco-link[data-e2e="7924f760-0b3e-22f5"]:has-text("View details")').first
            view_details_link.wait_for(state="visible", timeout=10000)
            view_details_link.click()
            logger.info("已点击 View details")
            self.delay(3)
            
            # 点击 Approved 标签
            approved_tab = page.locator('div.arco-tabs-header-title[role="tab"]:has-text("Approved")').first
            approved_tab.wait_for(state="visible", timeout=10000)
            approved_tab.click()
            logger.info("已点击 Approved 标签")
            self.delay(3)
            
            return True
            
        except Exception as e:
            logger.error(f"搜索打开活动失败: {e}")
            return False

    def send_product_cards(self, page, product_ids: List[str], rate: int, creator_name: str, creator_id: str, campaign_id: str) -> bool:
        """发送产品卡片到达人"""
        logger.info(f"准备发送 {len(product_ids)} 个产品卡片，佣金率: {rate}%")

        # === 新增逻辑：读取历史发送记录，避免重复发送 ===
        sent_product_ids = set()
        excel_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data', 'card', 'product_send.xlsx'
        )
        if os.path.exists(excel_path):
            try:
                df = pd.read_excel(excel_path)
                sent_product_ids = set(df['product_id'].astype(str).tolist())
                logger.info(f"检测到历史发送记录，共 {len(sent_product_ids)} 条，已加载")
            except Exception as e:
                logger.warning(f"读取历史记录失败：{e}")
        else:
            logger.info("未发现历史发送记录文件，全部产品将正常发送")
        
        first_product = True

        for idx, product_id in enumerate(product_ids, 1):
            logger.info(f"发送第 {idx}/{len(product_ids)} 个产品: {product_id}")
            product_id = str(product_id).strip()
            if product_id in sent_product_ids:
                logger.info(f"产品 {product_id} 已存在于历史记录中，跳过发送")
                continue

            try:
                # 仅第一次需要选择“Product name” -> “Product ID”
                if first_product:
                    product_dropdown = page.locator('div.arco-select-view:has-text("Product name")').first
                    product_dropdown.wait_for(state="visible", timeout=10000)
                    product_dropdown.click()
                    self.delay(1)
                    
                    product_id_option = page.locator('li.arco-select-option:has-text("Product ID")').first
                    product_id_option.wait_for(state="visible", timeout=5000)
                    product_id_option.click()
                    self.delay(1)
                    
                    first_product = False
                
                # 3. 输入产品ID并搜索
                search_input = page.locator('input[placeholder="Search Product ID"]').first
                search_input.wait_for(state="visible", timeout=5000)
                search_input.fill(product_id)
                search_input.press("Enter")
                logger.info(f"已搜索产品ID: {product_id}")
                self.delay(3)
                
                # 4. 点击Share按钮
                share_btn = page.locator('button:has-text("Share")').first
                share_btn.wait_for(state="visible", timeout=10000)
                share_btn.click()
                self.delay(2)
                
                # 5. 输入佣金率
                rate_input = page.locator('input[id="standardCommission_input"]').first
                rate_input.wait_for(state="visible", timeout=5000)
                rate_input.fill(str(rate))
                logger.info(f"已输入佣金率: {rate}%")
                self.delay(1)
                
                # 6. 点击Send in chat
                send_in_chat_btn = page.locator('button:has-text("Send in chat")').first
                send_in_chat_btn.wait_for(state="visible", timeout=5000)
                

                # 等待新页面打开
                with page.context.expect_page() as new_page_info:
                    send_in_chat_btn.click()
                
                new_page = new_page_info.value
                new_page.wait_for_load_state("domcontentloaded")
                logger.info("新页面已打开")
                self.delay(2)

                try:
                    new_page.wait_for_selector('text=Share a product with creators', timeout=10000)
                    logger.info("确认进入产品分享页面")
                except Exception as e:
                    logger.error(f"未找到产品分享页面标识: {e}")
                    new_page.close()
                    return False

                # 7. 点击"Search for a creator"标签
                search_tab = new_page.locator('div[role="tab"]:has-text("Search for a creator")').first
                search_tab.wait_for(state="visible", timeout=10000)
                search_tab.click()
                self.delay(1)

                # 8. 搜索达人
                creator_search = new_page.locator('input[placeholder="Search for creator"]').first
                creator_search.wait_for(state="visible", timeout=5000)
                creator_search.fill(creator_name)
                logger.info(f"已输入达人名称: {creator_name}")
                self.delay(1)  # 等待搜索结果
                # 点击放大镜搜索图标（唯一标识：svg.alliance-icon.alliance-icon-Search）
                try:
                    search_svg = new_page.locator('svg.alliance-icon.alliance-icon-Search').first
                    search_svg.wait_for(state="visible", timeout=5000)
                    try:
                        search_svg.scroll_into_view_if_needed()
                    except Exception:
                        pass
                    search_svg.click()
                    logger.info("已点击搜索 SVG 图标")
                except Exception as e:
                    logger.warning(f"直接点击 SVG 失败，尝试点击父级: {e}")
                    try:
                        parent = new_page.locator('svg.alliance-icon.alliance-icon-Search').first.locator('xpath=..')
                        parent.wait_for(state="visible", timeout=3000)
                        parent.click()
                        logger.info("已点击 SVG 的父级元素触发搜索")
                    except Exception as e2:
                        logger.warning(f"点击父级也失败，回退为回车触发搜索: {e2}")
                        try:
                            creator_search.press("Enter")
                            logger.info("已按回车触发搜索（备用）")
                        except Exception:
                            logger.error("搜索触发失败")
                self.delay(2)  # 等待搜索结果

                # 9. 点击达人卡片 - 修改选择器
                try:
                    creator_row = new_page.locator(
                        f'div[data-e2e="6cfbf330-2b43-36cc"]:has(span.text-primary-normal:has-text("{creator_name}"))'
                    ).first
                    creator_row.wait_for(state="visible", timeout=5000)
                    creator_row.click()
                    logger.info(f"已点击达人 {creator_name} 的搜索结果行")
                except Exception as e:
                    logger.error(f"点击达人结果行失败: {e}")
                    return False

                self.delay(1)
                
                # 10. 点击Share按钮发送
                try:
                    final_share_btn = new_page.locator(
                        'button.arco-btn.arco-btn-primary.arco-btn-size-large.arco-btn-shape-square.m4b-button.m4b-button-size-large'
                    ).first
                    final_share_btn.wait_for(state="visible", timeout=5000)
                    final_share_btn.click()
                    logger.info(f"产品 {product_id} 已发送")
                except Exception as e:
                    logger.error(f"点击 Share 按钮失败: {e}")
                    return False

                # 记录发送信息
                self.send_records.append({
                    'creator_name': creator_name,
                    'creator_id': creator_id,
                    'campaign_id': campaign_id,
                    'product_id': product_id,
                    'rate': rate,
                    'send_card_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
                
                self.delay(2)
                
                # 11. 关闭新页面
                new_page.close()
                logger.info("已关闭新页面，返回继续")
                self.delay(1)
                
                # 如果不是最后一个产品，清空搜索框准备下一个
                if idx < len(product_ids):
                    logger.info("准备继续下一个产品...")
                    self.delay(1)
                
            except Exception as e:
                logger.error(f"发送产品 {product_id} 失败: {e}")
                return False
        
        logger.info(f"所有 {len(product_ids)} 个产品卡片已发送完成")
        return True

    def save_records_to_excel(self):
        """保存发送记录到Excel（追加）"""
        if not self.send_records:
            logger.info("无发送记录")
            return
        
        excel_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data', 'card', 'product_send.xlsx'
        )
        
        new_df = pd.DataFrame(self.send_records)
        for col in ['creator_id', 'campaign_id', 'product_id']:
            if col in new_df.columns:
                new_df[col] = new_df[col].astype(str)

        
        # 检查文件是否存在
        if os.path.exists(excel_path):
            existing_df = pd.read_excel(excel_path)
            df = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            df = new_df
        
        df.to_excel(excel_path, index=False)
        logger.info(f"发送记录已保存: {excel_path}")

    def run(self) -> bool:
        """运行主流程"""
        logger.info("=" * 50)
        logger.info("TikTok Chat and Card Sender")
        logger.info("=" * 50)

        with sync_playwright() as p:
            try:
                self.browser = p.chromium.launch(headless=True, timeout=60000)
                self.context = self.browser.new_context(viewport={'width': 1920, 'height': 1080})
                self.context.set_default_timeout(60000)
                self.page = self.context.new_page()

                # 登录（只需一次）
                max_login_attempts = 3
                for attempt in range(1, max_login_attempts + 1):
                    logger.info(f"=== 登录流程 {attempt}/{max_login_attempts} ===")
                    if not self.login(self.page):
                        logger.error("登录失败")
                    else:
                        if self.check_welcome_page(self.page):
                            logger.info("登录成功")
                            break
                    if attempt == max_login_attempts:
                        return False

                # 读取所有达人配置
                all_creators_data = self.load_card_send_data()
                if not all_creators_data:
                    logger.error("未能加载配置数据")
                    return False

                # 循环处理每个达人
                for creator_idx, card_data in enumerate(all_creators_data, 1):
                    logger.info("=" * 50)
                    logger.info(f"处理第 {creator_idx}/{len(all_creators_data)} 个达人")
                    logger.info("=" * 50)
                    
                    creator_id = card_data.get('creator_id')
                    creator_name = card_data.get('creator_name')
                    
                    # 步骤3: 进入聊天页面
                    if not self.open_chat_and_screenshot(self.page, creator_id, max_retries=3):
                        logger.error(f"达人 {creator_name} 聊天页面加载失败，跳过")
                        continue

                    # 步骤4: 发送消息
                    message = card_data.get('message', '')
                    if message:
                        self.check_and_send_message(self.page, message)

                    # 步骤5: 跳转活动页面
                    if not self.navigate_to_campaign_page(self.page, creator_id):
                        logger.error(f"达人 {creator_name} 活动页面加载失败，跳过")
                        continue

                    # 步骤6: 搜索并打开活动
                    campaign_id = card_data.get('campaign_id')
                    if not campaign_id or not self.search_and_open_campaign(self.page, campaign_id):
                        logger.error(f"达人 {creator_name} 活动详情打开失败，跳过")
                        continue

                    # 步骤7: 发送产品卡片
                    product_ids = card_data.get('product_ids', [])
                    rate = card_data.get('rate', 14)
                    if product_ids:
                        self.send_product_cards(self.page, product_ids, rate, creator_name, creator_id, campaign_id)

                    logger.info(f"达人 {creator_name} 处理完成")

                logger.info("=" * 50)
                logger.info("所有达人处理完成")
                logger.info("=" * 50)
                self.save_records_to_excel()
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

if __name__ == '__main__':
    sender = CardSender()
    sender.run()