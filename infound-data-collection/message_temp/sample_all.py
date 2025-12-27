"""Legacy docstring removed for English-only repo."""
import logging
import time
import sys
import os
import argparse
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import re
from playwright.sync_api import sync_playwright
import pandas as pd
from datetime import datetime
# NOTE: legacy comment removed for English-only repo.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.email_code import GmailVerificationCode

# NOTE: legacy comment removed for English-only repo.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SampleAllCrawler:
    """Legacy docstring removed for English-only repo."""
    
    def __init__(self, region: str = "MX", tab: str = "all", expand_view_content: bool = True):
        """Legacy docstring removed for English-only repo."""
        self.region = region.upper()
        self.tab = tab.lower()
        self.expand_view_content = expand_view_content
        # Account configuration
        self.accounts_config = {
            "accounts": [
                {
                    "name": "Account MX1",
                    "login_email": "mx1@example.com",
                    "login_password": "<ACCOUNT_PASSWORD>",
                    "gmail_username": "mx1@example.com",
                    "gmail_app_password": "<GMAIL_APP_PASSWORD>",
                    "region": "MX",
                    "enabled": True
                },
                {
                    "name": "Account FR1",
                    "login_email": "fr1@example.com",
                    "login_password": "<ACCOUNT_PASSWORD>",
                    "gmail_username": "fr1@example.com",
                    "gmail_app_password": "<GMAIL_APP_PASSWORD>",
                    "region": "FR",
                    "enabled": True
                }
            ]
        }
        
        self.region = region.upper()
        self.setup_account_by_region()
        
        # NOTE: legacy comment removed for English-only repo.
        self.tab_mapping = {
            'all': 'All',
            'review': 'To review',
            'ready': 'Ready to ship',
            'shipped': 'Shipped',
            'pending': 'Content pending',
            'completed': 'Completed',
            'canceled': 'Canceled'
        }
        
        # NOTE: legacy comment removed for English-only repo.
        self.data_dir = "data/manage_sample"
        os.makedirs(self.data_dir, exist_ok=True)
        self.output_file = os.path.join(self.data_dir, f"sample_record_{self.tab}.xlsx")
        
        self.browser = None
        self.context = None
        self.page = None
        
        # NOTE: legacy comment removed for English-only repo.
        self.target_url = "https://partner.tiktokshop.com/affiliate-campaign/sample-requests?tab=to_review"

        # NOTE: legacy comment removed for English-only repo.
        self.view_content_counter = 0

        # NOTE: legacy comment removed for English-only repo.
        self.total_pages = None  # NOTE: legacy comment removed for English-only repo.
        self.max_crawl_pages = None  # NOTE: legacy comment removed for English-only repo.
        
        logger.info(f"将爬取 '{self.tab_mapping.get(self.tab, 'All')}' 标签页")
        logger.info(f"数据将保存到: {self.output_file}")
        logger.info("View content展开模式: %s", "开启" if self.expand_view_content else "关闭")

    def setup_account_by_region(self):
        """Legacy docstring removed for English-only repo."""
        logger.info(f"选择区域: {self.region}")
        
        selected_account = None
        for account in self.accounts_config['accounts']:
            if account['region'] == self.region and account['enabled']:
                selected_account = account
                break
        
        if not selected_account:
            for account in self.accounts_config['accounts']:
                if account['enabled']:
                    logger.warning(f"未找到region={self.region}的账号,使用默认账号: {account['name']}")
                    selected_account = account
                    break
        
        if not selected_account:
            raise Exception("没有可用的账号配置")
        
        self.login_email = selected_account['login_email']
        self.login_password = selected_account['login_password']
        self.gmail_username = selected_account['gmail_username']
        self.gmail_app_password = selected_account['gmail_app_password']
        self.account_name = selected_account['name']
        self.account_region = selected_account['region']
        
        self.gmail_verifier = GmailVerificationCode(
            username=self.gmail_username,
            app_password=self.gmail_app_password
        )
        
        logger.info("=" * 60)
        logger.info(f"账号配置:")
        logger.info(f"  账号名称: {self.account_name}")
        logger.info(f"  登录邮箱: {self.login_email}")
        logger.info(f"  区域: {self.account_region}")
        logger.info("=" * 60)

    def delay(self, seconds: float):
        """Legacy docstring removed for English-only repo."""
        time.sleep(seconds)

    def login(self, page) -> bool:
        """Legacy docstring removed for English-only repo."""
        max_retries = 5
        for i in range(max_retries):
            logger.info(f"开始登录流程（第 {i + 1} 次尝试）...")
            try:
                page.goto("https://partner-sso.tiktok.com/account/login?from=ttspc_logout&redirectURL=%2F%2Fpartner.tiktokshop.com%2Fhome&lang=en", 
                         wait_until="networkidle", timeout=60000)
                
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

                self.delay(3)

                if "partner.tiktokshop.com" in page.url:
                    logger.info("✓ 登录成功")
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
        
        logger.error(f"登录失败，已达到最大重试次数 {max_retries}")
        return False

    def check_login_success(self, page, timeout: int = 20) -> bool:
        """Legacy docstring removed for English-only repo."""
        logger.info("检查登录状态...")
        
        try:
            if "partner.tiktokshop.com" in page.url:
                logger.info("✓ URL验证通过")
                
                try:
                    page.wait_for_selector('text=Welcome to TikTok Shop Partner Center', timeout=timeout * 1000)
                    logger.info("✓ 找到欢迎文字，登录确认成功")
                    return True
                except:
                    try:
                        page.wait_for_selector('nav, header, [class*="header"]', timeout=5000)
                        logger.info("✓ 找到页面特征元素，登录确认成功")
                        return True
                    except:
                        logger.warning("URL正确但未找到特征元素，可能仍在加载")
                        return True
            else:
                logger.error("URL验证失败，未跳转到正确页面")
                return False
                
        except Exception as e:
            logger.error(f"检查登录状态时出错: {e}")
            return False

    def navigate_to_sample_requests(self, page) -> bool:
        """Legacy docstring removed for English-only repo."""
        max_retries = 3
        
        for i in range(max_retries):
            logger.info(f"跳转到样品请求页面（第 {i + 1} 次尝试）: {self.target_url}")
            
            try:
                page.goto(self.target_url, wait_until="networkidle", timeout=20000)
                logger.info("✓ 页面加载完成")
                return True
            except Exception as e:
                logger.error(f"第 {i + 1} 次跳转失败: {e}")
                if i < max_retries - 1:
                    logger.warning(f"等待 3 秒后重试...")
                    time.sleep(3)
        
        logger.error(f"跳转失败，已达到最大重试次数 {max_retries}")
        return False

    def wait_for_available_samples_text(self, page, timeout: int = 30) -> bool:
        """Legacy docstring removed for English-only repo."""
        logger.info(f"等待 'Available samples' 文本出现（最多 {timeout} 秒）...")
        
        try:
            selectors = [
                'text=Available samples',
                'h1:has-text("Available samples")',
                'h2:has-text("Available samples")',
                'div:has-text("Available samples")',
                'span:has-text("Available samples")'
            ]
            
            for selector in selectors:
                try:
                    page.wait_for_selector(selector, timeout=timeout * 1000, state="visible")
                    logger.info(f"✓ 找到 'Available samples' 文本")
                    return True
                except:
                    continue
            
            logger.warning("未找到 'Available samples' 文本，但继续")
            return False
            
        except Exception as e:
            logger.error(f"等待文本时出错: {e}")
            return False

    def click_tab(self, page) -> bool:
        """Legacy docstring removed for English-only repo."""
        tab_text = self.tab_mapping.get(self.tab, 'All')
        logger.info(f"正在点击 '{tab_text}' 标签...")
        
        try:
            # NOTE: legacy comment removed for English-only repo.
            if self.tab in ['review', 'ready', 'shipped', 'pending', 'completed', 'canceled']:
                # NOTE: legacy comment removed for English-only repo.
                # NOTE: legacy comment removed for English-only repo.
                tab_elem = page.locator(f'span.arco-tabs-header-title-text').filter(has_text=tab_text.split()[0]).first
            else:
                # NOTE: legacy comment removed for English-only repo.
                tab_elem = page.locator(f'span.arco-tabs-header-title-text:has-text("{tab_text}")').first
            
            tab_elem.wait_for(state="visible", timeout=10000)
            tab_elem.click()
            logger.info(f"✓ 已点击 '{tab_text}' 标签")
            return True
        except Exception as e:
            logger.error(f"点击 '{tab_text}' 标签失败: {e}")
            return False

    def get_avatar_element(self, row_element):
        """Legacy docstring removed for English-only repo."""
        selectors = [
            '.m4b-avatar.m4b-avatar-circle.flex-shrink-0.cursor-pointer',
            '.m4b-avatar.cursor-pointer'
        ]
        for selector in selectors:
            avatar = row_element.locator(selector)
            if avatar.count() > 0:
                return avatar.first
        return None

    def parse_creator_id_from_url(self, url: str) -> str:
        """Legacy docstring removed for English-only repo."""
        try:
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            cid_values = query.get('cid', [])
            if cid_values:
                return cid_values[0]
        except Exception as e:
            logger.debug(f"解析creator_id失败: {e}")
        return ""

    def close_creator_detail_page(self, detail_page, is_new_page: bool):
        """Legacy docstring removed for English-only repo."""
        try:
            if is_new_page and detail_page:
                detail_page.close()
                logger.info("✓ 已关闭新标签页")
            else:
                try:
                    detail_page.keyboard.press('Escape')
                    self.delay(2)
                    logger.info("✓ 通过ESC键关闭")
                except Exception:
                    try:
                        detail_page.go_back()
                        self.delay(2)
                        logger.info("✓ 通过浏览器返回关闭")
                    except Exception:
                        logger.warning("关闭详情页失败")
        except Exception as e:
            logger.warning(f"关闭详情页时出错: {e}")

    def fetch_creator_detail_info(self, page, row_element, fallback_name: str):
        """Legacy docstring removed for English-only repo."""
        for attempt in range(3):
            detail_page = None
            is_new_page = False
            avatar_elem = self.get_avatar_element(row_element)

            if not avatar_elem:
                logger.warning("未找到头像元素，无法获取达人详情")
                return None

            try:
                logger.info(f"第 {attempt + 1} 次尝试打开达人详情...")
                try:
                    with page.context.expect_page(timeout=10000) as new_page_ctx:
                        avatar_elem.click()
                        logger.info("✓ 已点击头像")
                    detail_page = new_page_ctx.value
                    is_new_page = True
                    logger.info("✓ 在新标签页中打开")
                    detail_page.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    logger.info("在当前页面打开达人详情")
                    detail_page = page
                    is_new_page = False
                    try:
                        detail_page.wait_for_url(re.compile(r'/creator/detail'), timeout=15000)
                    except Exception:
                        detail_page.wait_for_selector('text=Partnered brands', timeout=8000)

                is_detail_page = detail_page.evaluate("""
                    () => {
                        const url = window.location.href;
                        return url.includes('/creator/detail') || 
                            document.querySelector('div.text-head-l') !== null ||
                            document.querySelector('text=Partnered brands') !== null;
                    }
                """)

                if not is_detail_page:
                    logger.warning(f"第 {attempt + 1} 次尝试：未进入达人详情页")
                    if is_new_page and detail_page:
                        detail_page.close()
                    if attempt < 2:
                        self.delay(2)
                        continue
                    else:
                        return None

                logger.info("✓ 已进入详情页，等待关键信息加载")

                creator_name = ""
                max_wait = 15
                wait_count = 0
                key_elements = [
                    ('creator_name', '//*[@id="submodule_layout_container_id"]/div[2]/div/div/div[1]/div[2]/div[1]/div/span[1]/span[1]'),
                ]
                loaded_elements = set()

                while wait_count < max_wait:
                    try:
                        for elem_name, selector in key_elements:
                            if elem_name in loaded_elements:
                                continue
                            element = detail_page.locator(f'xpath={selector}')
                            if element.count() > 0:
                                loaded_elements.add(elem_name)
                                if elem_name == 'creator_name':
                                    try:
                                        creator_name = element.first.inner_text().strip()
                                        logger.info(f"✓ 成功获取完整creator_name: {creator_name}")
                                    except Exception:
                                        pass
                    except Exception as e:
                        logger.debug(f"检查达人详情元素出错: {e}")

                    if len(loaded_elements) == len(key_elements):
                        logger.info("所有关键元素已加载完成")
                        break

                    wait_count += 1
                    self.delay(1)
                    if wait_count % 5 == 0:
                        logger.info(f"已等待 {wait_count} 秒，已加载 {len(loaded_elements)}/{len(key_elements)} 个元素")

                detail_url = detail_page.url if detail_page else ""
                creator_id = self.parse_creator_id_from_url(detail_url) if detail_url else ""

                if not creator_name:
                    creator_name = fallback_name
                    logger.info(f"未从详情页获取到昵称，使用回退名称: {creator_name}")

                logger.info(f"✓ 达人信息: name={creator_name}, url={detail_url}, creator_id={creator_id}")
                self.close_creator_detail_page(detail_page, is_new_page)
                return creator_name, detail_url, creator_id

            except Exception as e:
                logger.error(f"获取达人详情失败 (尝试 {attempt + 1}/3): {e}")
                try:
                    if is_new_page and detail_page:
                        detail_page.close()
                except Exception:
                    pass
                if attempt < 2:
                    self.delay(2)
                    continue
        return None

    def get_creator_name(self, page, row_element):
        """Legacy docstring removed for English-only repo."""
        logger.info("获取creator信息...")
        fallback_name = ""
        try:
            creator_text_elem = row_element.locator('.arco-typography.m4b-typography-text.sc-dcJsrY.gBlgCq').first
            creator_text = creator_text_elem.inner_text().strip()
            logger.info(f"发现creator文本: {creator_text}")
            fallback_name = creator_text.replace('@', '').replace('...', '').strip()
        except Exception as e:
            logger.error(f"读取creator文本失败: {e}")

        detail_info = self.fetch_creator_detail_info(page, row_element, fallback_name)
        if detail_info:
            return detail_info

        logger.warning("未能通过详情页获取达人信息，使用回退数据")
        return fallback_name, "", ""

    def safe_extract_text(self, page, xpath: str) -> str:
        """Legacy docstring removed for English-only repo."""
        try:
            element = page.locator(f'xpath={xpath}')
            if element.count() > 0:
                text = element.first.inner_text().strip()
                return text if text else ""
            return ""
        except Exception as e:
            logger.debug(f"提取文本失败 {xpath}: {e}")
            return ""

    def extract_row_data(self, page, row_element) -> dict:
        """Legacy docstring removed for English-only repo."""
        logger.info("提取行数据...")
        row_data = {}
        
        try:
            # product_name
            try:
                product_name_elem = row_element.locator('span[style*="text-overflow: ellipsis"][style*="-webkit-line-clamp: 2"]').first
                row_data['product_name'] = product_name_elem.inner_text().strip()
            except:
                row_data['product_name'] = ""
            
            # NOTE: legacy comment removed for English-only repo.
            try:
                id_text = row_element.locator('span.text-body-s-regular:has-text("ID:")').first.inner_text()
                # NOTE: legacy comment removed for English-only repo.
                product_id = id_text.replace("ID:", "").strip()
                row_data['product_id'] = str(product_id)  # NOTE: legacy comment removed for English-only repo.
            except:
                row_data['product_id'] = ""
            
            # sku
            try:
                sku_parent = row_element.locator('span.text-neutral-text3:has-text("SKU:")').locator('..')
                sku_text = sku_parent.inner_text()
                row_data['sku'] = sku_text.replace("SKU:", "").strip()
            except:
                row_data['sku'] = ""

            # stock
            try:
                stock_parent = row_element.locator('span.text-neutral-text3:has-text("Stock:")').locator('..')
                stock_text = stock_parent.inner_text()
                row_data['stock'] = stock_text.replace("Stock:", "").strip()
            except:
                row_data['stock'] = ""

            # available_samples
            try:
                # NOTE: legacy comment removed for English-only repo.
                second_td = row_element.locator('td').nth(1)
                available_elem = second_td.locator('div[style*="width: fit-content"]').first
                row_data['available_samples'] = available_elem.inner_text().strip()
            except:
                row_data['available_samples'] = ""
            
            # status
            try:
                status_elem = row_element.locator('.arco-tag .text').first
                row_data['status'] = status_elem.inner_text().strip()
            except:
                row_data['status'] = ""

            # request_time_remaining
            try:
                time_remaining_cell = row_element.locator('td').nth(3)  # NOTE: legacy comment removed for English-only repo.
                row_data['request_time_remaining'] = time_remaining_cell.inner_text().strip()
            except:
                row_data['request_time_remaining'] = ""

            # post_rate
            try:
                post_rate_cell = row_element.locator('td').nth(6)  # NOTE: legacy comment removed for English-only repo.
                row_data['post_rate'] = post_rate_cell.inner_text().strip()
            except:
                row_data['post_rate'] = ""
            
            # is_showcase
            try:
                showcase_cell = row_element.locator('td').nth(10)  # NOTE: legacy comment removed for English-only repo.
                row_data['is_showcase'] = showcase_cell.inner_text().strip()
            except:
                row_data['is_showcase'] = ""
        
            # campaign_name
            try:
                campaign_elem = row_element.locator('.arco-typography.m4b-typography-paragraph.text-body-m-regular').first
                row_data['campaign_name'] = campaign_elem.inner_text().strip()
            except:
                row_data['campaign_name'] = ""
            
            # NOTE: legacy comment removed for English-only repo.
            try:
                all_ids = row_element.locator('span.text-body-s-regular:has-text("ID:")').all()
                if len(all_ids) >= 2:
                    campaign_id_text = all_ids[1].inner_text()
                    # NOTE: legacy comment removed for English-only repo.
                    campaign_id = campaign_id_text.replace("ID:", "").strip()
                    row_data['campaign_id'] = str(campaign_id)  # NOTE: legacy comment removed for English-only repo.
                else:
                    row_data['campaign_id'] = ""
            except:
                row_data['campaign_id'] = ""
            
            logger.info(f"✓ 提取基础数据完成: product_name={row_data.get('product_name', '')[:30]}...")
            logger.debug(f"  product_id={row_data.get('product_id', '')}, campaign_id={row_data.get('campaign_id', '')}")
            
            return row_data
            
        except Exception as e:
            logger.error(f"提取行数据失败: {e}")
            import traceback
            traceback.print_exc()
            return row_data

    def retry_on_timeout(self, func, max_retries=3, *args, **kwargs):
        """Legacy docstring removed for English-only repo."""
        for attempt in range(max_retries):
            try:
                logger.info(f"尝试执行 {func.__name__} (第 {attempt + 1}/{max_retries} 次)")
                result = func(*args, **kwargs)
                logger.info(f"✓ {func.__name__} 执行成功")
                return result
            except Exception as e:
                logger.warning(f"第 {attempt + 1} 次尝试失败: {e}")
                if attempt < max_retries - 1:
                    wait_time = 2 * (attempt + 1)  # NOTE: legacy comment removed for English-only repo.
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    self.delay(wait_time)
                else:
                    logger.error(f"{func.__name__} 达到最大重试次数，放弃")
                    raise

    def extract_single_block_with_retry(self, page, block_xpath: str, content_type: str, block_index: int, max_retries: int = 3) -> dict:
        """Legacy docstring removed for English-only repo."""
        for attempt in range(max_retries):
            try:
                logger.info(f"尝试提取第 {block_index} 个区块 (尝试 {attempt + 1}/{max_retries})...")
                promo_data = {}
                
                # NOTE: legacy comment removed for English-only repo.
                self.delay(2 + attempt)  # NOTE: legacy comment removed for English-only repo.
                
                # NOTE: legacy comment removed for English-only repo.
                try:
                    page.wait_for_selector(f'xpath={block_xpath}', timeout=5000)
                except:
                    logger.warning(f"区块 {block_index} 未在5秒内加载")
                
                if content_type == 'video':
                    block_base = f'{block_xpath}/div[2]/div'
                    
                    # promotion_name
                    try:
                        name_xpath = f'{block_base}/div[1]'
                        # NOTE: legacy comment removed for English-only repo.
                        page.wait_for_selector(f'xpath={name_xpath}', state='visible', timeout=2000)
                        promo_data['promotion_name'] = self.safe_extract_text(page, name_xpath)
                    except:
                        promo_data['promotion_name'] = ""
                        logger.debug(f"区块 {block_index}: 无法获取 promotion_name")

                    # promotion_time
                    try:
                        time_xpath = f'{block_base}/div[2]'
                        promo_data['promotion_time'] = self.safe_extract_text(page, time_xpath)
                    except:
                        promo_data['promotion_time'] = ""
                        logger.debug(f"区块 {block_index}: 无法获取 promotion_time")
                    
                    metrics_base = f'{block_base}/div[3]'
                    
                else:  # live
                    block_base = f'{block_xpath}/div/div'
                    
                    # promotion_name
                    try:
                        name_xpath = f'{block_base}/div[1]'
                        page.wait_for_selector(f'xpath={name_xpath}', state='visible', timeout=2000)
                        promo_data['promotion_name'] = self.safe_extract_text(page, name_xpath)
                    except:
                        promo_data['promotion_name'] = ""
                        logger.debug(f"区块 {block_index}: 无法获取 promotion_name")
                    
                    # promotion_time
                    try:
                        time_xpath = f'{block_base}/div[2]'
                        promo_data['promotion_time'] = self.safe_extract_text(page, time_xpath)
                    except:
                        promo_data['promotion_time'] = ""
                        logger.debug(f"区块 {block_index}: 无法获取 promotion_time")
                    
                    metrics_base = f'{block_base}/div[3]'
                
                # NOTE: legacy comment removed for English-only repo.
                self.delay(0.5)
                
                # promotion_view
                try:
                    view_xpath = f'{metrics_base}/div[1]/div[2]/div'
                    promo_data['promotion_view'] = self.safe_extract_text(page, view_xpath)
                except:
                    promo_data['promotion_view'] = ""
                    logger.debug(f"区块 {block_index}: 无法获取 promotion_view")
                
                # promotion_like
                try:
                    like_xpath = f'{metrics_base}/div[2]/div[2]/div'
                    promo_data['promotion_like'] = self.safe_extract_text(page, like_xpath)
                except:
                    promo_data['promotion_like'] = ""
                    logger.debug(f"区块 {block_index}: 无法获取 promotion_like")
                
                # promotion_comment
                try:
                    comment_xpath = f'{metrics_base}/div[3]/div[2]/div'
                    promo_data['promotion_comment'] = self.safe_extract_text(page, comment_xpath)
                except:
                    promo_data['promotion_comment'] = ""
                    logger.debug(f"区块 {block_index}: 无法获取 promotion_comment")
                
                # promotion_order
                try:
                    order_xpath = f'{metrics_base}/div[4]/div[2]/div'
                    promo_data['promotion_order'] = self.safe_extract_text(page, order_xpath)
                except:
                    promo_data['promotion_order'] = ""
                    logger.debug(f"区块 {block_index}: 无法获取 promotion_order")
                
                # promotion_earn
                try:
                    earn_xpath = f'{metrics_base}/div[5]/div[2]/span/div'
                    earn_text = self.safe_extract_text(page, earn_xpath)
                    
                    if not earn_text:
                        earn_xpath_alt = f'{metrics_base}/div[5]/div[2]/div'
                        earn_text = self.safe_extract_text(page, earn_xpath_alt)
                    
                    if earn_text and 'p...' in earn_text:
                        promo_data['promotion_earn'] = earn_text.replace('p...', '').strip()
                    else:
                        promo_data['promotion_earn'] = earn_text
                except:
                    promo_data['promotion_earn'] = ""
                    logger.debug(f"区块 {block_index}: 无法获取 promotion_earn")
                
                # NOTE: legacy comment removed for English-only repo.
                if promo_data.get('promotion_name') or promo_data.get('promotion_view') or promo_data.get('promotion_earn'):
                    logger.info(f"✓ 第 {block_index} 个区块提取成功")
                    return promo_data
                else:
                    logger.warning(f"区块 {block_index} 数据为空，准备重试...")
                    if attempt < max_retries - 1:
                        self.delay(2)  # NOTE: legacy comment removed for English-only repo.
                        
            except Exception as e:
                logger.error(f"提取区块 {block_index} 失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    self.delay(3)  # NOTE: legacy comment removed for English-only repo.
                    
        # NOTE: legacy comment removed for English-only repo.
        logger.error(f"区块 {block_index} 在 {max_retries} 次尝试后仍然失败")
        return {
            'promotion_name': "",
            'promotion_time': "",
            'promotion_view': "",
            'promotion_like': "",
            'promotion_comment': "",
            'promotion_order': "",
            'promotion_earn': ""
        }

    def extract_promotion_data_by_xpath(self, page, panel_xpath: str, content_type: str) -> list:
        """Legacy docstring removed for English-only repo."""
        logger.info(f"使用 XPath 提取 {content_type} 数据: {panel_xpath}")
        promotion_list = []
        
        try:
            # NOTE: legacy comment removed for English-only repo.
            self.delay(2)
            
            # NOTE: legacy comment removed for English-only repo.
            try:
                page.wait_for_selector(f'xpath={panel_xpath}', timeout=10000)
                logger.info("✓ 面板已加载")
            except:
                logger.warning("面板加载超时，继续尝试提取")
            
            # NOTE: legacy comment removed for English-only repo.
            special_layout_check = page.locator(f'xpath={panel_xpath}/div/div/div/div[2]/div/span/div')
            if special_layout_check.count() > 0:
                logger.info("检测到特殊布局（单个内容）")
                
                # NOTE: legacy comment removed for English-only repo.
                for attempt in range(3):
                    try:
                        promo_data = {}
                        base_path = f'{panel_xpath}/div/div/div/div[2]/div'
                        
                        # NOTE: legacy comment removed for English-only repo.
                        self.delay(1 + attempt)
                        
                        # promotion_name
                        try:
                            name_xpath = f'{base_path}/span/div'
                            promo_data['promotion_name'] = self.safe_extract_text(page, name_xpath)
                        except:
                            promo_data['promotion_name'] = ""
                        
                        # promotion_time
                        try:
                            time_xpath = f'{base_path}/div[1]'
                            promo_data['promotion_time'] = self.safe_extract_text(page, time_xpath)
                        except:
                            promo_data['promotion_time'] = ""
                        
                        # NOTE: legacy comment removed for English-only repo.
                        metrics_base = f'{base_path}/div[2]'
                        
                        # promotion_view
                        try:
                            view_xpath = f'{metrics_base}/div[1]/div[2]/div'
                            promo_data['promotion_view'] = self.safe_extract_text(page, view_xpath)
                        except:
                            promo_data['promotion_view'] = ""
                        
                        # promotion_like
                        try:
                            like_xpath = f'{metrics_base}/div[2]/div[2]/div'
                            promo_data['promotion_like'] = self.safe_extract_text(page, like_xpath)
                        except:
                            promo_data['promotion_like'] = ""
                        
                        # promotion_comment
                        try:
                            comment_xpath = f'{metrics_base}/div[3]/div[2]/div'
                            promo_data['promotion_comment'] = self.safe_extract_text(page, comment_xpath)
                        except:
                            promo_data['promotion_comment'] = ""
                        
                        # promotion_order
                        try:
                            order_xpath = f'{metrics_base}/div[4]/div[2]/div'
                            promo_data['promotion_order'] = self.safe_extract_text(page, order_xpath)
                        except:
                            promo_data['promotion_order'] = ""
                        
                        # promotion_earn
                        try:
                            earn_xpath = f'{metrics_base}/div[5]/div[2]/span/div'
                            earn_text = self.safe_extract_text(page, earn_xpath)
                            if not earn_text:
                                earn_xpath = f'{metrics_base}/div[5]/div[2]/div'
                                earn_text = self.safe_extract_text(page, earn_xpath)
                            
                            if 'p...' in earn_text:
                                promo_data['promotion_earn'] = earn_text.replace('p...', '').strip()
                            else:
                                promo_data['promotion_earn'] = earn_text
                        except:
                            promo_data['promotion_earn'] = ""
                        
                        # NOTE: legacy comment removed for English-only repo.
                        if any(promo_data.values()):
                            promotion_list.append(promo_data)
                            logger.info("✓ 特殊布局数据提取成功")
                            return promotion_list
                        elif attempt < 2:
                            logger.warning(f"特殊布局数据为空，重试 {attempt + 2}/3")
                            self.delay(2)
                            
                    except Exception as e:
                        logger.error(f"特殊布局提取失败 (尝试 {attempt + 1}/3): {e}")
                        if attempt < 2:
                            self.delay(3)
                
                # NOTE: legacy comment removed for English-only repo.
                if not promotion_list:
                    promotion_list.append({
                        'promotion_name': "",
                        'promotion_time': "",
                        'promotion_view': "",
                        'promotion_like': "",
                        'promotion_comment': "",
                        'promotion_order': "",
                        'promotion_earn': ""
                    })
                return promotion_list
            
            # NOTE: legacy comment removed for English-only repo.
            if content_type == 'video':
                base_xpath = f'{panel_xpath}/div/div'
            else:  # live
                base_xpath = f'{panel_xpath}/div'
            
            # NOTE: legacy comment removed for English-only repo.
            blocks_locator = page.locator(f'xpath={base_xpath}/div')
            blocks_count = blocks_locator.count()
            
            logger.info(f"✓ 找到 {blocks_count} 个 {content_type} 区块")
            
            # NOTE: legacy comment removed for English-only repo.
            if blocks_count == 0:
                logger.warning("未找到区块，等待3秒后重新检查...")
                self.delay(3)
                blocks_count = blocks_locator.count()
                if blocks_count == 0:
                    logger.error("仍未找到任何区块")
                    return promotion_list
            
            # NOTE: legacy comment removed for English-only repo.
            for idx in range(1, blocks_count + 1):
                if content_type == 'video':
                    block_xpath = f'{base_xpath}/div[{idx}]'
                else:  # live
                    block_xpath = f'{base_xpath}/div[{idx}]'
                
                # NOTE: legacy comment removed for English-only repo.
                promo_data = self.extract_single_block_with_retry(page, block_xpath, content_type, idx)
                promotion_list.append(promo_data)
                
                # NOTE: legacy comment removed for English-only repo.
                if idx % 3 == 0:
                    self.delay(1)
            
            logger.info(f"✓ 成功提取 {len(promotion_list)} 条 {content_type} 数据")
            return promotion_list
            
        except Exception as e:
            logger.error(f"提取 {content_type} 数据失败: {e}")
            import traceback
            traceback.print_exc()
            return promotion_list

    def process_view_content(self, page, row_data: dict, tab_id_number: int) -> list:
        """Legacy docstring removed for English-only repo."""
        logger.info(f"处理View content (tab_id_number={tab_id_number})...")
        all_rows = []

        try:
            logger.info("等待5秒让内容加载...")
            self.delay(5)
            
            # NOTE: legacy comment removed for English-only repo.
            tab_0_xpath = f'//*[@id="arco-tabs-{tab_id_number}-tab-0"]'
            tab_1_xpath = f'//*[@id="arco-tabs-{tab_id_number}-tab-1"]'
            panel_0_xpath = f'//*[@id="arco-tabs-{tab_id_number}-panel-0"]'
            panel_1_xpath = f'//*[@id="arco-tabs-{tab_id_number}-panel-1"]'
            
            logger.info(f"使用 tab ID: {tab_id_number}")
            logger.info(f"  tab-0: {tab_0_xpath}")
            logger.info(f"  tab-1: {tab_1_xpath}")
            
            # NOTE: legacy comment removed for English-only repo.
            tabs_info = []
            
            # NOTE: legacy comment removed for English-only repo.
            try:
                tab_0_elem = page.locator(f'xpath={tab_0_xpath}')
                if tab_0_elem.count() > 0:
                    tab_0_text_elem = tab_0_elem.locator('xpath=./span/span').first
                    tab_0_full_text = tab_0_text_elem.inner_text().strip()
                    logger.info(f"Tab-0 文本: {tab_0_full_text}")
                    
                    # NOTE: legacy comment removed for English-only repo.
                    if 'video' in tab_0_full_text.lower():
                        tab_type = 'video'
                    elif 'LIVE' in tab_0_full_text or 'live' in tab_0_full_text.lower():
                        tab_type = 'live'
                    else:
                        tab_type = None
                    
                    if tab_type:
                        # NOTE: legacy comment removed for English-only repo.
                        import re
                        try:
                            count_match = re.search(r'(\d+)', tab_0_full_text)
                            tab_count = int(count_match.group(1)) if count_match else 0
                        except:
                            tab_count = 0
                        
                        tabs_info.append({
                            'type': tab_type,
                            'count': tab_count,
                            'tab_xpath': tab_0_xpath,
                            'panel_xpath': panel_0_xpath,
                            'tab_index': 0
                        })
                        logger.info(f"✓ Tab-0: {tab_type}, 数量: {tab_count}")
            except Exception as e:
                logger.debug(f"检查 tab-0 失败: {e}")
            
            # NOTE: legacy comment removed for English-only repo.
            try:
                tab_1_elem = page.locator(f'xpath={tab_1_xpath}')
                if tab_1_elem.count() > 0:
                    tab_1_text_elem = tab_1_elem.locator('xpath=./span/span').first
                    tab_1_full_text = tab_1_text_elem.inner_text().strip()
                    logger.info(f"Tab-1 文本: {tab_1_full_text}")
                    
                    # NOTE: legacy comment removed for English-only repo.
                    if 'video' in tab_1_full_text.lower():
                        tab_type = 'video'
                    elif 'LIVE' in tab_1_full_text or 'live' in tab_1_full_text.lower():
                        tab_type = 'live'
                    else:
                        tab_type = None
                    
                    if tab_type:
                        # NOTE: legacy comment removed for English-only repo.
                        import re
                        try:
                            count_match = re.search(r'(\d+)', tab_1_full_text)
                            tab_count = int(count_match.group(1)) if count_match else 0
                        except:
                            tab_count = 0
                        
                        tabs_info.append({
                            'type': tab_type,
                            'count': tab_count,
                            'tab_xpath': tab_1_xpath,
                            'panel_xpath': panel_1_xpath,
                            'tab_index': 1
                        })
                        logger.info(f"✓ Tab-1: {tab_type}, 数量: {tab_count}")
            except Exception as e:
                logger.debug(f"检查 tab-1 失败: {e}")
            
            if not tabs_info:
                logger.warning("未找到任何 video 或 LIVE 标签")
                return all_rows
            
            tabs_summary = [f"{t['type']}({t['count']})" for t in tabs_info]
            logger.info(f"共识别到 {len(tabs_info)} 个标签: {tabs_summary}")
            
            # NOTE: legacy comment removed for English-only repo.
            for tab_info in tabs_info:
                tab_type = tab_info['type']
                tab_count = tab_info['count']
                tab_xpath = tab_info['tab_xpath']
                panel_xpath = tab_info['panel_xpath']
                
                logger.info(f"\n{'='*50}")
                logger.info(f"处理标签: {tab_type} (数量: {tab_count})")
                logger.info(f"{'='*50}")
                
                # NOTE: legacy comment removed for English-only repo.
                try:
                    logger.info(f"点击 tab: {tab_xpath}")
                    tab_elem = page.locator(f'xpath={tab_xpath}')
                    tab_elem.click(timeout=5000)
                    self.delay(2)
                    logger.info(f"✓ 已点击 {tab_type} 标签")
                except Exception as e:
                    logger.error(f"点击 {tab_type} 标签失败: {e}")
                    continue
                
                # NOTE: legacy comment removed for English-only repo.
                try:
                    promotions = self.extract_promotion_data_by_xpath(page, panel_xpath, tab_type)
                    base_creator_name = row_data.get('creator_name', '')
                    base_creator_url = row_data.get('creator_url', '')
                    base_creator_id = row_data.get('creator_id', '')
                    base_creator_tiktok = row_data.get('creator_tiktok', f"https://www.tiktok.com/@{base_creator_name}" if base_creator_name else "")
                    
                    for promo in promotions:
                        row = row_data.copy()
                        row['creator_name'] = base_creator_name
                        row['creator_url'] = base_creator_url
                        row['creator_id'] = base_creator_id
                        row['creator_tiktok'] = base_creator_tiktok
                        row['type'] = tab_type
                        row['type_number'] = str(tab_count)
                        row.update(promo)
                        row['region'] = self.region
                        row['extracted_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        all_rows.append(row)
                        
                except Exception as e:
                    logger.error(f"提取 {tab_type} 数据失败: {e}")
                    import traceback
                    traceback.print_exc()
            
            # NOTE: legacy comment removed for English-only repo.
            video_count = sum(t['count'] for t in tabs_info if t['type'] == 'video')
            live_count = sum(t['count'] for t in tabs_info if t['type'] == 'live')
            
            logger.info(f"✓ 处理完成，共生成 {len(all_rows)} 行数据 "
                        f"(video={video_count}, live={live_count})")
            return all_rows

        except Exception as e:
            logger.error(f"处理View content失败: {e}")
            import traceback
            traceback.print_exc()
            return all_rows

    def close_view_content_drawer(self, page) -> bool:
        """Legacy docstring removed for English-only repo."""
        logger.info("关闭View content弹窗...")
        try:
            drawers = page.locator('.arco-drawer')
            drawer_count = drawers.count()
            logger.info(f"检测到 {drawer_count} 个弹窗实例，准备筛选可见的")

            visible_close_btn = None
            for i in range(drawer_count):
                drawer = drawers.nth(i)
                if drawer.is_visible():
                    logger.info(f"第 {i + 1} 个抽屉可见，查找关闭按钮...")
                    btn = drawer.locator('span.arco-icon-hover.arco-drawer-close-icon').first
                    if btn.count() > 0:
                        visible_close_btn = btn
                        logger.info("✓ 找到可见抽屉的关闭按钮")
                        break
                else:
                    logger.debug(f"第 {i + 1} 个抽屉不可见，跳过")

            if visible_close_btn:
                visible_close_btn.click(timeout=1000, force=True)
                logger.info("✓ 成功点击可见弹窗关闭按钮")
                self.delay(0.5)
            else:
                logger.warning("✗ 未找到可见抽屉的关闭按钮，尝试ESC退出")
                page.keyboard.press('Escape')
                self.delay(0.5)

            if page.locator('.arco-drawer[style*="display: block"]').count() > 0:
                logger.info("检测到抽屉仍显示，执行二次ESC关闭")
                page.keyboard.press('Escape')
                self.delay(0.5)

            logger.info("✓ 弹窗关闭完成")
            return True

        except Exception as e:
            logger.warning(f"关闭View content弹窗异常: {e}，执行紧急ESC")
            try:
                page.keyboard.press('Escape')
                self.delay(0.5)
            except Exception:
                pass
            return False

    def ensure_view_content_closed(self, page, max_attempts: int = 3) -> bool:
        """Legacy docstring removed for English-only repo."""
        try:
            for attempt in range(1, max_attempts + 1):
                open_drawers = page.locator('.arco-drawer[style*="display: block"]')
                if open_drawers.count() == 0:
                    logger.info("未检测到打开的View content抽屉")
                    return True

                logger.warning(f"检测到打开的View content抽屉，尝试关闭 ({attempt}/{max_attempts})")
                self.close_view_content_drawer(page)
                self.delay(0.5)

            if page.locator('.arco-drawer[style*="display: block"]').count() > 0:
                logger.warning("多次尝试后仍有View content抽屉未关闭")
                return False
            return True
        except Exception as e:
            logger.warning(f"检查View content抽屉状态失败: {e}")
            return False

    def save_to_excel(self, rows: list):
        """Legacy docstring removed for English-only repo."""
        if not rows:
            logger.warning("没有数据需要保存")
            return
        
        # NOTE: legacy comment removed for English-only repo.
        fieldnames = [
            'region', 'product_name', 'product_id',
            'stock', 'sku',	'available_samples',
            'status', 'request_time_remaining',
            'campaign_name', 'campaign_id', 'action',
            'creator_name', 'creator_url', 'creator_id', 'creator_tiktok', 'post_rate', 'is_showcase',
            'type', 'type_number', 'promotion_name',
            'promotion_time', 'promotion_view', 'promotion_like', 'promotion_comment',
            'promotion_order', 'promotion_earn', 'extracted_time'
        ]
        
        try:
            # NOTE: legacy comment removed for English-only repo.
            if os.path.exists(self.output_file):
                existing_df = pd.read_excel(self.output_file, engine='openpyxl', dtype=str)
                logger.info(f"读取现有文件，已有 {len(existing_df)} 行数据")
            else:
                existing_df = pd.DataFrame()
                logger.info("创建新文件")
            
            # NOTE: legacy comment removed for English-only repo.
            new_df = pd.DataFrame(rows)
            
            # NOTE: legacy comment removed for English-only repo.
            new_df = new_df.reindex(columns=fieldnames)
            
            # NOTE: legacy comment removed for English-only repo.
            id_columns = ['product_id', 'campaign_id', 'creator_id', 'partner_id']
            for col in id_columns:
                if col in new_df.columns:
                    new_df[col] = new_df[col].astype(str)
            
            # NOTE: legacy comment removed for English-only repo.
            if not existing_df.empty:
                # NOTE: legacy comment removed for English-only repo.
                for col in id_columns:
                    if col in existing_df.columns:
                        existing_df[col] = existing_df[col].astype(str)
                
                df = pd.concat([existing_df, new_df], ignore_index=True)
            else:
                df = new_df
            
            # NOTE: legacy comment removed for English-only repo.
            for col in id_columns:
                if col in df.columns:
                    df[col] = df[col].astype(str)
            
            # NOTE: legacy comment removed for English-only repo.
            with pd.ExcelWriter(self.output_file, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
                
                # NOTE: legacy comment removed for English-only repo.
                worksheet = writer.sheets['Sheet1']
                
                # NOTE: legacy comment removed for English-only repo.
                from openpyxl.styles import numbers
                
                # NOTE: legacy comment removed for English-only repo.
                for col_idx, col_name in enumerate(df.columns, 1):
                    if col_name in id_columns:
                        # NOTE: legacy comment removed for English-only repo.
                        for row_idx in range(2, len(df) + 2):  # NOTE: legacy comment removed for English-only repo.
                            cell = worksheet.cell(row=row_idx, column=col_idx)
                            cell.number_format = numbers.FORMAT_TEXT
                            # NOTE: legacy comment removed for English-only repo.
                            if cell.value is not None:
                                cell.value = str(cell.value)
            
            logger.info(f"✓ 已保存 {len(rows)} 行新数据，文件总行数: {len(df)}")
            logger.info(f"  保存位置: {self.output_file}")
            
        except Exception as e:
            logger.error(f"保存Excel失败: {e}")
            import traceback
            traceback.print_exc()

    def crawl_current_page(self, page) -> list:
        """Legacy docstring removed for English-only repo."""
        logger.info("开始爬取当前页面...")
        all_page_rows = []
        
        try:
            # NOTE: legacy comment removed for English-only repo.
            tbody = page.locator('tbody').first
            rows = tbody.locator('tr.arco-table-tr').all()
            logger.info(f"找到 {len(rows)} 行数据")
            
            for idx, row in enumerate(rows, 1):
                logger.info(f"\n{'='*50}")
                logger.info(f"处理第 {idx} 行...")
                logger.info(f"{'='*50}")
                
                # NOTE: legacy comment removed for English-only repo.
                current_row_data = []
                
                try:
                    # NOTE: legacy comment removed for English-only repo.
                    row_data = self.extract_row_data(page, row)
                    
                    # NOTE: legacy comment removed for English-only repo.
                    creator_name, creator_url, creator_id = self.get_creator_name(page, row)
                    row_data['creator_name'] = creator_name
                    row_data['creator_url'] = creator_url
                    row_data['creator_id'] = creator_id
                    row_data['creator_tiktok'] = f"https://www.tiktok.com/@{creator_name}" if creator_name else ""
                    
                    # NOTE: legacy comment removed for English-only repo.
                    action = ""
                    try:
                        buttons = row.locator('button span').all()
                        if buttons:
                            for btn in buttons:
                                btn_text = btn.inner_text().strip()
                                # NOTE: legacy comment removed for English-only repo.
                                # if btn_text in ["Approve", "View logistics", "View content", "Contact seller", "Message creator"]:
                                if btn_text in ["View content", "View logistics"]:
                                    action = btn_text
                                    break
                    except Exception as e:
                        logger.debug(f"提取 action 失败: {e}")
                        action = ""

                    row_data['action'] = action
                    logger.info(f"Action类型: {action}")
                    
                    # NOTE: legacy comment removed for English-only repo.
                    if action == "View content" and not self.expand_view_content:
                        logger.info("View content 展开被禁用，记录基础信息后跳过点击")
                        base_row = row_data.copy()
                        base_row['creator_name'] = creator_name
                        base_row['creator_tiktok'] = f"https://www.tiktok.com/@{creator_name}" if creator_name else ""
                        base_row['type'] = ""
                        base_row['type_number'] = ""
                        base_row['promotion_name'] = ""
                        base_row['promotion_time'] = ""
                        base_row['promotion_view'] = ""
                        base_row['promotion_like'] = ""
                        base_row['promotion_comment'] = ""
                        base_row['promotion_order'] = ""
                        base_row['promotion_earn'] = ""
                        base_row['region'] = self.region
                        base_row['extracted_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        current_row_data.append(base_row)
                    elif action == "View content":
                        content_rows = []
                        max_view_content_retries = 3

                        for attempt in range(1, max_view_content_retries + 1):
                            logger.info(f"View content 第 {attempt}/{max_view_content_retries} 次尝试")
                            view_btn = row.locator('button:has-text("View content")').first

                            if view_btn.count() == 0:
                                logger.error("未找到 View content 按钮，无法继续")
                                break

                            try:
                                view_btn.click()
                                logger.info("✓ 已点击View content按钮")
                            except Exception as e:
                                logger.error(f"点击 View content 按钮失败: {e}")
                                break

                            self.delay(3)
                            self.view_content_counter += 1
                            current_tab_id = self.view_content_counter
                            logger.info(f"View content 计数器更新为: {self.view_content_counter}")
                            logger.info(f"尝试使用 tab_id_number={current_tab_id} 处理View content...")

                            try:
                                rows_from_view = self.process_view_content(page, row_data, current_tab_id)
                                content_rows = rows_from_view or []
                            except Exception as e:
                                logger.error(f"处理 View content 异常: {e}")
                                import traceback
                                traceback.print_exc()
                                content_rows = []
                            finally:
                                self.close_view_content_drawer(page)

                            if content_rows:
                                logger.info("✓ 成功从View content提取数据")
                                break
                            elif attempt < max_view_content_retries:
                                logger.warning("✗ 本次未提取到任何内容，关闭后重新尝试")
                                self.delay(2)
                            else:
                                logger.warning("多次尝试后仍未能从View content获取数据")

                        current_row_data.extend(content_rows)
                    else:
                        # NOTE: legacy comment removed for English-only repo.
                        base_row = row_data.copy()
                        base_row['creator_name'] = creator_name
                        base_row['creator_tiktok'] = f"https://www.tiktok.com/@{creator_name}" if creator_name else ""
                        base_row['type'] = ""
                        base_row['type_number'] = ""
                        base_row['promotion_name'] = ""
                        base_row['promotion_time'] = ""
                        base_row['promotion_view'] = ""
                        base_row['promotion_like'] = ""
                        base_row['promotion_comment'] = ""
                        base_row['promotion_order'] = ""
                        base_row['promotion_earn'] = ""
                        base_row['region'] = self.region
                        base_row['extracted_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        current_row_data.append(base_row)
                    
                    # NOTE: legacy comment removed for English-only repo.
                    if current_row_data:
                        logger.info(f"准备保存第 {idx} 行的 {len(current_row_data)} 条数据...")
                        self.save_to_excel(current_row_data)
                        all_page_rows.extend(current_row_data)
                        logger.info(f"✓ 第 {idx} 行的数据已保存")
                    else:
                        logger.warning(f"第 {idx} 行没有数据可保存")
                    
                    logger.info(f"✓ 第 {idx} 行处理完成")
                    
                except Exception as e:
                    logger.error(f"处理第 {idx} 行失败: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            logger.info(f"\n{'='*60}")
            logger.info(f"✓ 当前页面爬取完成，共 {len(all_page_rows)} 行数据")
            logger.info(f"{'='*60}")
            return all_page_rows
            
        except Exception as e:
            logger.error(f"爬取当前页面失败: {e}")
            import traceback
            traceback.print_exc()
            return all_page_rows

    def get_total_pages(self, page) -> int:
        """Legacy docstring removed for English-only repo."""
        try:
            # NOTE: legacy comment removed for English-only repo.
            # NOTE: legacy comment removed for English-only repo.
            page_items = page.locator('li.arco-pagination-item:not(.arco-pagination-item-jumper):not(.arco-pagination-item-next):not(.arco-pagination-item-previous)').all()
            
            max_page = 0
            for item in page_items:
                try:
                    page_text = item.inner_text().strip()
                    if page_text.isdigit():
                        page_num = int(page_text)
                        if page_num > max_page:
                            max_page = page_num
                except:
                    continue
            
            if max_page > 0:
                logger.info(f"✓ 检测到总页数: {max_page}")
                return max_page
            else:
                logger.warning("未能检测到总页数，将逐页爬取直到无下一页")
                return None
                
        except Exception as e:
            logger.error(f"获取总页数失败: {e}")
            return None

    def has_next_page(self, page) -> bool:
        """Legacy docstring removed for English-only repo."""
        try:
            next_btn = page.locator('li.arco-pagination-item-next').first
            # NOTE: legacy comment removed for English-only repo.
            is_disabled = next_btn.get_attribute('aria-disabled')
            return is_disabled != 'true'
        except:
            return False

    def goto_next_page(self, page) -> bool:
        """Legacy docstring removed for English-only repo."""
        try:
            logger.info("点击下一页...")
            if not self.ensure_view_content_closed(page):
                logger.warning("翻页前未能关闭View content抽屉，停止翻页")
                return False
            next_btn = page.locator('li.arco-pagination-item-next').first
            next_btn.click()
            self.delay(3)
            
            # NOTE: legacy comment removed for English-only repo.
            self.wait_for_available_samples_text(page, timeout=30)
            self.delay(2)
            
            logger.info("✓ 已跳转到下一页")
            return True
        except Exception as e:
            logger.error(f"跳转下一页失败: {e}")
            return False

    def run(self) -> bool:
        """Legacy docstring removed for English-only repo."""
        logger.info("=" * 60)
        logger.info(f"TikTok Sample All Data Crawler - Region: {self.region}")
        logger.info("=" * 60)
        
        with sync_playwright() as p:
            try:
                logger.info("启动浏览器...")
                self.browser = p.chromium.launch(headless=True, timeout=60000)
                self.context = self.browser.new_context(viewport={'width': 1920, 'height': 1080})
                self.context.set_default_timeout(60000)
                self.page = self.context.new_page()

                # NOTE: legacy comment removed for English-only repo.
                if not self.login(self.page):
                    logger.error("登录失败，程序终止")
                    return False

                # NOTE: legacy comment removed for English-only repo.
                if not self.check_login_success(self.page):
                    logger.error("登录状态验证失败，程序终止")
                    return False

                self.delay(2)

                # NOTE: legacy comment removed for English-only repo.
                if not self.navigate_to_sample_requests(self.page):
                    logger.error("跳转失败，程序终止")
                    return False
                
                self.delay(2)

                # NOTE: legacy comment removed for English-only repo.
                self.wait_for_available_samples_text(self.page, timeout=30)
                
                self.delay(2)

                # NOTE: legacy comment removed for English-only repo.
                if not self.click_tab(self.page):
                    logger.warning(f"点击 '{self.tab_mapping.get(self.tab, 'All')}' 标签失败，继续")
                else:
                    # NOTE: legacy comment removed for English-only repo.
                    self.delay(2)
                    self.wait_for_available_samples_text(self.page, timeout=30)

                self.delay(2)

                # NOTE: legacy comment removed for English-only repo.
                self.total_pages = self.get_total_pages(self.page)
                if self.total_pages:
                    self.max_crawl_pages = self.total_pages + 2
                    logger.info(f"计划爬取页数: {self.max_crawl_pages} 页（总页数 {self.total_pages} + 2）")
                else:
                    logger.info("未获取到总页数，将爬取到没有下一页为止")

                # NOTE: legacy comment removed for English-only repo.
                page_num = 1
                total_rows = 0

                while True:
                    logger.info(f"\n{'='*60}")
                    logger.info(f"开始爬取第 {page_num} 页")
                    logger.info(f"{'='*60}")
                    
                    # NOTE: legacy comment removed for English-only repo.
                    page_rows = self.crawl_current_page(self.page)
                    total_rows += len(page_rows)
                    
                    logger.info(f"第 {page_num} 页完成，本页共 {len(page_rows)} 行数据")
                    
                    # NOTE: legacy comment removed for English-only repo.
                    if self.max_crawl_pages and page_num >= self.max_crawl_pages:
                        logger.info(f"✓ 已达到设定的最大页数 {self.max_crawl_pages}，停止爬取")
                        break
                    
                    # NOTE: legacy comment removed for English-only repo.
                    if self.has_next_page(self.page):
                        if self.goto_next_page(self.page):
                            page_num += 1
                            continue
                        else:
                            logger.warning("跳转下一页失败，停止爬取")
                            break
                    else:
                        logger.info("已到达最后一页")
                        break
                
                logger.info("=" * 60)
                logger.info("✓ 所有数据爬取完成")
                logger.info(f"  共爬取 {page_num} 页")
                logger.info(f"  总共爬取 {total_rows} 行数据")
                logger.info(f"  数据保存位置: {self.output_file}")
                logger.info("=" * 60)
                return True

            except Exception as e:
                logger.error(f"程序运行出错: {e}")
                import traceback
                traceback.print_exc()
                return False
            finally:
                if self.page:
                    self.page.close()
                if self.context:
                    self.context.close()
                if self.browser:
                    self.browser.close()
                logger.info("浏览器已关闭")

def main():
    """Legacy docstring removed for English-only repo."""
    parser = argparse.ArgumentParser(description='TikTok Sample All Data Crawler')
    parser.add_argument(
        '--region',
        type=str,
        choices=['MX', 'FR', 'mx', 'fr'],
        default='MX',
        help='选择区域: MX 或 FR (默认: MX)'
    )
    parser.add_argument(
        '--tab',
        type=str,
        choices=['all', 'review', 'ready', 'shipped', 'pending', 'completed', 'canceled'],
        default='all',
        help='选择要爬取的标签页 (默认: all)'
    )
    parser.add_argument(
        '--skip-view-content',
        action='store_true',
        help='不展开 View content 抽屉，直接记录基础信息'
    )
    
    args = parser.parse_args()
    
    # NOTE: legacy comment removed for English-only repo.
    crawler = SampleAllCrawler(
        region=args.region.upper(),
        tab=args.tab.lower(),
        expand_view_content=not args.skip_view_content,
    )
    success = crawler.run()
    
    # NOTE: legacy comment removed for English-only repo.
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()


# NOTE: legacy comment removed for English-only repo.
# nohup python -u manage_sample/sample_all.py --tab all > logs/sample_all1126.log 2>&1 &

# NOTE: legacy comment removed for English-only repo.
# nohup python -u manage_sample/sample_all.py --tab review > logs/sample_review1127.log 2>&1 &

# NOTE: legacy comment removed for English-only repo.
# nohup python -u manage_sample/sample_all.py --tab ready > logs/sample_ready.log 2>&1 &

# NOTE: legacy comment removed for English-only repo.
# nohup python -u manage_sample/sample_all.py --tab shipped > logs/sample_shipped.log 2>&1 &

# NOTE: legacy comment removed for English-only repo.
# nohup python -u manage_sample/sample_all.py --tab pending > logs/sample_pending.log 2>&1 &

# NOTE: legacy comment removed for English-only repo.
# nohup python -u manage_sample/sample_all.py --tab completed > logs/sample_completed.log 2>&1 &

# NOTE: legacy comment removed for English-only repo.
# nohup python -u manage_sample/sample_all.py --tab canceled > logs/sample_canceled.log 2>&1 &

# NOTE: legacy comment removed for English-only repo.
# nohup python -u manage_sample/sample_all.py --region FR --tab review > logs/sample_fr_review.log 2>&1 &
