"""
TikTok Sample Requests Data Crawler
爬取样品请求页面的所有数据
python manage_sample/sample_all.py --region MX
"""
import logging
import time
import sys
import os
import argparse
from datetime import datetime
from playwright.sync_api import sync_playwright
import pandas as pd
from datetime import datetime
# 确保路径正确
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.email_code import GmailVerificationCode

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SampleAllCrawler:
    """
    TikTok样品请求数据爬虫
    """
    
    def __init__(self, region: str = "MX", tab: str = "all"):
        """初始化爬虫"""
        self.region = region.upper()
        self.tab = tab.lower()
        # 账号配置
        self.accounts_config = {
            "accounts": [
                {
                    "name": "账号1-MX",
                    "login_email": "tiktokshopinfoundtest@gmail.com",
                    "login_password": "fyvbyn-hyctu0-Rafqyp",
                    "gmail_username": "tiktokshopinfoundtest@gmail.com",
                    "gmail_app_password": "cfhlfedjqhfbbbhb",
                    "region": "MX",
                    "enabled": True
                },
                {
                    "name": "账号2-FR",
                    "login_email": "tiktokinfoundfrance@gmail.com",
                    "login_password": "dyvvac-coqnYp-sespo0",
                    "gmail_username": "tiktokinfoundfrance@gmail.com",
                    "gmail_app_password": "gnseoovwafbstjbt",
                    "region": "FR",
                    "enabled": True
                }
            ]
        }
        
        self.region = region.upper()
        self.setup_account_by_region()
        
        # 标签映射
        self.tab_mapping = {
            'all': 'All',
            'review': 'To review',
            'ready': 'Ready to ship',
            'shipped': 'Shipped',
            'pending': 'Content pending',
            'completed': 'Completed',
            'canceled': 'Canceled'
        }
        
        # 数据保存目录和文件 - 根据标签命名
        self.data_dir = "data/manage_sample"
        os.makedirs(self.data_dir, exist_ok=True)
        self.output_file = os.path.join(self.data_dir, f"sample_record_{self.tab}.xlsx")
        
        self.browser = None
        self.context = None
        self.page = None
        
        # 目标URL
        self.target_url = "https://partner.tiktokshop.com/affiliate-campaign/sample-requests?tab=to_review"

        # 添加 View content 点击计数器
        self.view_content_counter = 0
        
        logger.info(f"将爬取 '{self.tab_mapping.get(self.tab, 'All')}' 标签页")
        logger.info(f"数据将保存到: {self.output_file}")

    def setup_account_by_region(self):
        """根据region设置账号信息"""
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
        """延迟"""
        time.sleep(seconds)

    def login(self, page) -> bool:
        """登录TikTok商家平台"""
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
        """检查是否登录成功"""
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
        """跳转到样品请求页面"""
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
        """等待 'Available samples' 文本出现"""
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
        """点击指定标签"""
        tab_text = self.tab_mapping.get(self.tab, 'All')
        logger.info(f"正在点击 '{tab_text}' 标签...")
        
        try:
            # 根据不同标签使用不同的选择器
            if self.tab in ['review', 'ready', 'shipped', 'pending', 'completed', 'canceled']:
                # 这些标签包含数字，需要特殊处理
                # 使用包含文本的方式查找
                tab_elem = page.locator(f'span.arco-tabs-header-title-text').filter(has_text=tab_text.split()[0]).first
            else:
                # All标签
                tab_elem = page.locator(f'span.arco-tabs-header-title-text:has-text("{tab_text}")').first
            
            tab_elem.wait_for(state="visible", timeout=10000)
            tab_elem.click()
            logger.info(f"✓ 已点击 '{tab_text}' 标签")
            return True
        except Exception as e:
            logger.error(f"点击 '{tab_text}' 标签失败: {e}")
            return False

    def get_creator_name(self, page, row_element) -> str:
        """获取creator_name，根据是否有...决定是否需要点击"""
        logger.info("获取creator_name...")
        try:
            # 先找到creator文本元素判断是否有...
            creator_text_elem = row_element.locator('.arco-typography.m4b-typography-text.sc-dcJsrY.gBlgCq').first
            creator_text = creator_text_elem.inner_text().strip()
            
            logger.info(f"发现creator文本: {creator_text}")
            
            # 如果包含...，需要点击获取完整名称
            if '...' in creator_text:
                logger.info("检测到...，需要点击头像获取完整名称")
                
                # 最多重试3次
                for attempt in range(3):
                    detail_page = None
                    is_new_page = False
                    
                    try:
                        logger.info(f"第 {attempt + 1} 次尝试点击头像获取完整名称...")
                        
                        # 监听新页面打开
                        try:
                            with page.context.expect_page(timeout=10000) as new_page_ctx:
                                # 点击头像元素
                                avatar_elem = row_element.locator('.m4b-avatar.m4b-avatar-circle.flex-shrink-0.cursor-pointer').first
                                if avatar_elem.count() == 0:
                                    avatar_elem = row_element.locator('.m4b-avatar.cursor-pointer').first
                                avatar_elem.click()
                                logger.info("✓ 已点击头像")
                            
                            # 获取新页面
                            detail_page = new_page_ctx.value
                            is_new_page = True
                            logger.info("✓ 在新标签页中打开")
                            detail_page.wait_for_load_state("domcontentloaded", timeout=15000)
                            
                        except Exception:
                            # 没有新页面，使用当前页面
                            logger.info("在当前页面打开（同页路由或抽屉）")
                            detail_page = page
                            is_new_page = False
                            
                            # 等待URL变化或特征元素出现
                            try:
                                import re
                                detail_page.wait_for_url(re.compile(r'/creator/detail'), timeout=15000)
                            except:
                                detail_page.wait_for_selector('text=Partnered brands', timeout=8000)
                        
                        # 快速检查是否在详情页
                        is_detail_page = detail_page.evaluate("""
                            () => {
                                const url = window.location.href;
                                return url.includes('/creator/detail') || 
                                    document.querySelector('div.text-head-l') !== null ||
                                    document.querySelector('text=Partnered brands') !== null;
                            }
                        """)
                        
                        if not is_detail_page:
                            logger.warning(f"第 {attempt + 1} 次尝试：未成功进入详情页")
                            if is_new_page and detail_page:
                                detail_page.close()
                            if attempt < 2:
                                self.delay(2)
                                continue
                            else:
                                raise Exception("多次尝试后仍未进入详情页")
                        
                        logger.info("✓ 已进入详情页")
                        
                        # 等待关键元素加载完成（使用与extract_creator_details相同的逻辑）
                        max_wait = 30
                        wait_count = 0
                        
                        # 定义需要等待的关键元素
                        key_elements = [
                            ('标题', 'div.text-head-l:has-text("Creator details"), div.text-head-l:has-text("达人详情")'),
                            ('creator_name', '//*[@id="submodule_layout_container_id"]/div[2]/div/div/div[1]/div[2]/div[1]/div/span[1]/span[1]'),
                            ('分类', '//*[@id="submodule_layout_container_id"]/div[2]/div/div/div[1]/div[2]/div[2]/div[1]/span[1]/span[2]/span/span'),
                            ('粉丝数', '//*[@id="submodule_layout_container_id"]/div[2]/div/div/div[1]/div[2]/div[2]/div[1]/span[2]/span[2]/span/span'),
                        ]
                        
                        loaded_elements = set()
                        creator_name = ""
                        
                        while wait_count < max_wait:
                            try:
                                # 检查每个关键元素是否已加载
                                for elem_name, selector in key_elements:
                                    if elem_name not in loaded_elements:
                                        try:
                                            if selector.startswith('//') or selector.startswith('(//'):
                                                # XPath选择器
                                                element = detail_page.locator(f'xpath={selector}')
                                            else:
                                                # CSS选择器
                                                element = detail_page.locator(selector)
                                            
                                            if element.count() > 0:
                                                loaded_elements.add(elem_name)
                                                logger.debug(f"✓ {elem_name} 已加载")
                                                
                                                # 如果是creator_name元素，立即提取
                                                if elem_name == 'creator_name':
                                                    try:
                                                        creator_name = element.first.inner_text().strip()
                                                        logger.info(f"✓ 成功获取完整creator_name: {creator_name}")
                                                    except:
                                                        pass
                                        except:
                                            pass
                                
                                # 必须所有关键元素都加载完成才继续
                                if len(loaded_elements) == len(key_elements):
                                    logger.info(f"所有关键元素已加载完成 ({len(loaded_elements)}/{len(key_elements)})")
                                    break
                                    
                            except Exception as e:
                                logger.debug(f"检查页面元素时出错: {e}")
                            
                            wait_count += 1
                            self.delay(1)
                            
                            if wait_count % 5 == 0:
                                logger.info(f"已等待 {wait_count} 秒，已加载 {len(loaded_elements)}/{len(key_elements)} 个元素...")
                                missing = set([name for name, _ in key_elements]) - loaded_elements
                                if missing:
                                    logger.info(f"  仍在等待: {', '.join(missing)}")
                        
                        # 超时检查
                        if wait_count >= max_wait:
                            logger.warning(f"等待超时({max_wait}秒)，已加载 {len(loaded_elements)}/{len(key_elements)} 个元素")
                            missing = set([name for name, _ in key_elements]) - loaded_elements
                            if missing:
                                logger.warning(f"  未加载的元素: {', '.join(missing)}")
                            
                            # 如果至少获取到了creator_name，也算成功
                            if creator_name:
                                logger.info(f"虽然部分元素未加载，但已获取到creator_name: {creator_name}")
                            else:
                                # 关闭页面
                                if is_new_page and detail_page:
                                    detail_page.close()
                                    logger.info("✓ 已关闭新标签页")
                                
                                if attempt < 2:
                                    self.delay(2)
                                    continue
                                else:
                                    raise Exception("等待超时且未获取到creator_name")
                        
                        # 检查是否成功获取到名称
                        if creator_name:
                            logger.info(f"✓ 最终获取到creator_name: {creator_name}")
                            
                            # 关闭详情页
                            logger.info("关闭详情页...")
                            if is_new_page and detail_page:
                                detail_page.close()
                                logger.info("✓ 已关闭新标签页")
                            else:
                                # 同页路由，尝试返回
                                try:
                                    detail_page.keyboard.press('Escape')
                                    self.delay(2)
                                    logger.info("✓ 通过ESC键关闭")
                                except:
                                    try:
                                        detail_page.go_back()
                                        self.delay(2)
                                        logger.info("✓ 通过浏览器返回关闭")
                                    except:
                                        logger.warning("关闭详情页失败，但已获取到名称")
                            
                            return creator_name
                        else:
                            logger.warning(f"第 {attempt + 1} 次尝试：未能获取creator_name")
                            
                            # 关闭页面
                            if is_new_page and detail_page:
                                detail_page.close()
                                logger.info("✓ 已关闭新标签页")
                            
                            if attempt < 2:
                                self.delay(2)
                                continue
                        
                    except Exception as e:
                        logger.error(f"第 {attempt + 1} 次尝试失败: {e}")
                        
                        # 尝试关闭可能打开的页面
                        try:
                            if is_new_page and detail_page:
                                detail_page.close()
                                logger.info("✓ 已关闭新标签页")
                        except:
                            pass
                        
                        if attempt < 2:
                            self.delay(2)
                            continue
                
                # 所有尝试都失败，返回去掉...的原始文本
                logger.error("所有尝试都失败，返回原始文本")
                return creator_text.replace('@', '').replace('...', '').strip()
            else:
                # 没有...，直接返回，去掉@
                clean_name = creator_text.replace('@', '').strip()
                logger.info(f"✓ 直接获取creator_name: {clean_name}")
                return clean_name
                
        except Exception as e:
            logger.error(f"获取creator_name失败: {e}")
            import traceback
            traceback.print_exc()
            return ""

    def safe_extract_text(self, page, xpath: str) -> str:
        """安全提取文本内容的辅助方法"""
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
        """提取一行的基础数据 - 改进版（确保ID为字符串）"""
        logger.info("提取行数据...")
        row_data = {}
        
        try:
            # product_name
            try:
                product_name_elem = row_element.locator('span[style*="text-overflow: ellipsis"][style*="-webkit-line-clamp: 2"]').first
                row_data['product_name'] = product_name_elem.inner_text().strip()
            except:
                row_data['product_name'] = ""
            
            # product_id - 提取第一个出现的产品ID（较短的那个），确保是字符串
            try:
                id_text = row_element.locator('span.text-body-s-regular:has-text("ID:")').first.inner_text()
                # 提取数字，保持为字符串
                product_id = id_text.replace("ID:", "").strip()
                row_data['product_id'] = str(product_id)  # 确保是字符串
            except:
                row_data['product_id'] = ""
            
            # sku
            try:
                sku_parent = row_element.locator('span.text-neutral-text3:has-text("SKU:")').locator('..')
                sku_text = sku_parent.inner_text()
                row_data['sku'] = sku_text.replace("SKU:", "").strip()
            except:
                row_data['sku'] = ""
            
            # available_samples
            try:
                # 在第二个td中查找
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
                time_cell = row_element.locator('td').nth(4)  # 通常时间在第5列
                raw_html = time_cell.inner_html().strip()
                if '--' in raw_html or '>' not in raw_html:
                    row_data['request_time_remaining'] = ""
                else:
                    text_elem = time_cell.locator('span, div').first
                    text_val = text_elem.inner_text().strip() if text_elem.count() > 0 else ""
                    if text_val == "--":
                        text_val = ""
                    row_data['request_time_remaining'] = text_val
            except Exception as e:
                logger.debug(f"request_time_remaining 提取失败: {e}")
                row_data['request_time_remaining'] = ""
            
            # campaign_name
            try:
                campaign_elem = row_element.locator('.arco-typography.m4b-typography-paragraph.text-body-m-regular').first
                row_data['campaign_name'] = campaign_elem.inner_text().strip()
            except:
                row_data['campaign_name'] = ""
            
            # campaign_id - 提取第二个ID（较长的那个），确保是字符串
            try:
                all_ids = row_element.locator('span.text-body-s-regular:has-text("ID:")').all()
                if len(all_ids) >= 2:
                    campaign_id_text = all_ids[1].inner_text()
                    # 提取数字，保持为字符串
                    campaign_id = campaign_id_text.replace("ID:", "").strip()
                    row_data['campaign_id'] = str(campaign_id)  # 确保是字符串
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
        """超时重试装饰器"""
        for attempt in range(max_retries):
            try:
                logger.info(f"尝试执行 {func.__name__} (第 {attempt + 1}/{max_retries} 次)")
                result = func(*args, **kwargs)
                logger.info(f"✓ {func.__name__} 执行成功")
                return result
            except Exception as e:
                logger.warning(f"第 {attempt + 1} 次尝试失败: {e}")
                if attempt < max_retries - 1:
                    wait_time = 2 * (attempt + 1)  # 递增等待时间
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    self.delay(wait_time)
                else:
                    logger.error(f"{func.__name__} 达到最大重试次数，放弃")
                    raise

    def extract_promotion_data_by_xpath(self, page, panel_xpath: str, content_type: str) -> list:
        """使用 XPath 提取 video 或 live 的推广数据"""
        logger.info(f"使用 XPath 提取 {content_type} 数据: {panel_xpath}")
        promotion_list = []
        
        try:
            self.delay(1)
            
            # 先检查是否是特殊的单个内容布局
            special_layout_check = page.locator(f'xpath={panel_xpath}/div/div/div/div[2]/div/span/div')
            if special_layout_check.count() > 0:
                logger.info("检测到特殊布局（单个内容）")
                promo_data = {}
                
                base_path = f'{panel_xpath}/div/div/div/div[2]/div'
                
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
                
                # 数据指标
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
                        # 尝试不带span的路径
                        earn_xpath = f'{metrics_base}/div[5]/div[2]/div'
                        earn_text = self.safe_extract_text(page, earn_xpath)
                    
                    if 'p...' in earn_text:
                        promo_data['promotion_earn'] = earn_text.replace('p...', '').strip()
                    else:
                        promo_data['promotion_earn'] = earn_text
                except:
                    promo_data['promotion_earn'] = ""
                
                promotion_list.append(promo_data)
                logger.info("✓ 特殊布局数据提取完成")
                return promotion_list
            
            # 如果不是特殊布局，继续原有的多区块处理逻辑
            if content_type == 'video':
                base_xpath = f'{panel_xpath}/div/div'
            else:  # live
                base_xpath = f'{panel_xpath}/div'
            
            # 获取所有块的数量
            blocks_locator = page.locator(f'xpath={base_xpath}/div')
            blocks_count = blocks_locator.count()
            
            logger.info(f"✓ 找到 {blocks_count} 个 {content_type} 区块")
            
            for idx in range(1, blocks_count + 1):
                logger.info(f"处理第 {idx} 个区块...")
                promo_data = {}
                
                if content_type == 'video':
                    block_base = f'{base_xpath}/div[{idx}]/div[2]/div'
                    
                    # promotion_name
                    try:
                        name_xpath = f'{block_base}/div[1]'
                        promo_data['promotion_name'] = self.safe_extract_text(page, name_xpath)
                    except:
                        promo_data['promotion_name'] = ""

                    # promotion_time
                    try:
                        time_xpath = f'{block_base}/div[2]'
                        promo_data['promotion_time'] = self.safe_extract_text(page, time_xpath)
                    except:
                        promo_data['promotion_time'] = ""
                    
                    # 数据指标区域
                    metrics_base = f'{block_base}/div[3]'
                    
                else:  # live
                    block_base = f'{base_xpath}/div[{idx}]/div/div'
                    
                    # promotion_name
                    try:
                        name_xpath = f'{block_base}/div[1]'
                        promo_data['promotion_name'] = self.safe_extract_text(page, name_xpath)
                    except:
                        promo_data['promotion_name'] = ""
                    
                    # promotion_time
                    try:
                        time_xpath = f'{block_base}/div[2]'
                        promo_data['promotion_time'] = self.safe_extract_text(page, time_xpath)
                    except:
                        promo_data['promotion_time'] = ""
                    
                    # 数据指标区域
                    metrics_base = f'{block_base}/div[3]'
                
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
                
                # promotion_earn - 改进版，特别处理LIVE
                try:
                    if content_type == 'video':
                        earn_xpath = f'{metrics_base}/div[5]/div[2]/span/div'
                    else:  # live
                        # LIVE可能有不同的路径
                        earn_xpath = f'{metrics_base}/div[5]/div[2]/span/div'
                    
                    earn_text = self.safe_extract_text(page, earn_xpath)
                    
                    # 如果上面的路径没获取到，尝试不带span的路径
                    if not earn_text:
                        try:
                            earn_xpath_alt = f'{metrics_base}/div[5]/div[2]/div'
                            earn_text = self.safe_extract_text(page, earn_xpath_alt)
                        except:
                            pass
                    
                    # 处理省略号
                    if earn_text and 'p...' in earn_text:
                        promo_data['promotion_earn'] = earn_text.replace('p...', '').strip()
                    else:
                        promo_data['promotion_earn'] = earn_text
                except:
                    promo_data['promotion_earn'] = ""
                
                promotion_list.append(promo_data)
                logger.info(f"✓ 第 {idx} 个区块处理完成")
            
            logger.info(f"✓ 提取到 {len(promotion_list)} 条 {content_type} 数据")
            return promotion_list
            
        except Exception as e:
            logger.error(f"提取 {content_type} 数据失败: {e}")
            import traceback
            traceback.print_exc()
            return promotion_list

    # 备选方法，我之前用这个爬的，TAP做得太烂了，很容易出问题
    def extract_promotion_data(self, page, content_type: str) -> list:
        """提取video或live的推广数据"""
        logger.info(f"提取{content_type}数据...")
        promotion_list = []
        
        try:
            # 直接尝试获取内容区块，不再等待
            self.delay(1)  # 给一点时间让内容稳定
            content_blocks = page.locator('.rounded-8.bg-white-0.p-16.flex.flex-row').all()
            
            if len(content_blocks) == 0:
                logger.warning("未找到内容区块，可能标签页没有内容")
                return promotion_list
            
            logger.info(f"✓ 找到{len(content_blocks)}个内容区块")
            
            for idx, block in enumerate(content_blocks, 1):
                logger.info(f"处理第{idx}个内容区块...")
                promo_data = {}
                
                # promotion_name (只有video有)
                if content_type == "video":
                    try:
                        name_elem = block.locator('.arco-typography.text-neutral-text1.text-body-m-regular').first
                        promo_data['promotion_name'] = name_elem.inner_text()
                        logger.debug(f"  promotion_name: {promo_data['promotion_name']}")
                    except:
                        promo_data['promotion_name'] = ""
                else:
                    promo_data['promotion_name'] = ""
                
                # promotion_time
                try:
                    if content_type == "video":
                        time_elem = block.locator('.text-neutral-text3.mt-8.text-body-s-regular span').nth(1)
                    else:  # live
                        time_elem = block.locator('.text-neutral-text3.mt-8.text-body-s-regular span').nth(1)
                    promo_data['promotion_time'] = time_elem.inner_text()
                    logger.debug(f"  promotion_time: {promo_data['promotion_time']}")
                except:
                    promo_data['promotion_time'] = ""
                
                # promotion_view
                try:
                    view_elem = block.locator('.arco-icon-eye_fill').locator('..').locator('..').locator('.arco-typography').first
                    promo_data['promotion_view'] = view_elem.inner_text()
                    logger.debug(f"  promotion_view: {promo_data['promotion_view']}")
                except:
                    promo_data['promotion_view'] = ""
                
                # promotion_like
                try:
                    like_elem = block.locator('.arco-icon-like_fill').locator('..').locator('..').locator('.arco-typography').first
                    promo_data['promotion_like'] = like_elem.inner_text()
                    logger.debug(f"  promotion_like: {promo_data['promotion_like']}")
                except:
                    promo_data['promotion_like'] = ""
                
                # promotion_comment
                try:
                    comment_elem = block.locator('.arco-icon-message-fill').locator('..').locator('..').locator('.arco-typography').first
                    promo_data['promotion_comment'] = comment_elem.inner_text()
                    logger.debug(f"  promotion_comment: {promo_data['promotion_comment']}")
                except:
                    promo_data['promotion_comment'] = ""
                
                # promotion_order - 改进的选择器
                promo_data['promotion_order'] = ""
                try:
                    grid_items = block.locator('.grid.grid-cols-3.gap-x-12 .sc-jXbUNg.eDRJuM').all()
                    if len(grid_items) >= 5:
                        order_elem = grid_items[-2].locator('.arco-typography').first
                        order_text = order_elem.inner_text()
                        promo_data['promotion_order'] = order_text
                        logger.debug(f"  promotion_order: {promo_data['promotion_order']}")
                except Exception as e:
                    logger.debug(f"  promotion_order提取失败: {e}")
                
                # promotion_earn - 改进的选择器
                promo_data['promotion_earn'] = ""
                try:
                    grid_items = block.locator('.grid.grid-cols-3.gap-x-12 .sc-jXbUNg.eDRJuM').all()
                    if len(grid_items) >= 5:
                        earn_elem = grid_items[-1].locator('.arco-typography').first
                        earn_text = earn_elem.inner_text()
                        # 处理可能的省略号
                        if 'p...' in earn_text:
                            promo_data['promotion_earn'] = earn_text.replace('p...', '').strip()
                        else:
                            promo_data['promotion_earn'] = earn_text
                        logger.debug(f"  promotion_earn: {promo_data['promotion_earn']}")
                except Exception as e:
                    logger.debug(f"  promotion_earn提取失败: {e}")
                
                promotion_list.append(promo_data)
                logger.info(f"✓ 第{idx}个内容区块处理完成")
            
            logger.info(f"✓ 提取到{len(promotion_list)}条{content_type}数据")
            return promotion_list
            
        except Exception as e:
            logger.error(f"提取{content_type}数据失败: {e}")
            import traceback
            traceback.print_exc()
            return promotion_list

    def process_view_content(self, page, row_data: dict, creator_name: str, tab_id_number: int) -> list:
        """处理View content弹窗，返回完整的数据行列表"""
        logger.info(f"处理View content (tab_id_number={tab_id_number})...")
        all_rows = []

        try:
            logger.info("等待5秒让内容加载...")
            self.delay(5)
            
            # 使用传入的计数器构建 XPath
            tab_0_xpath = f'//*[@id="arco-tabs-{tab_id_number}-tab-0"]'
            tab_1_xpath = f'//*[@id="arco-tabs-{tab_id_number}-tab-1"]'
            panel_0_xpath = f'//*[@id="arco-tabs-{tab_id_number}-panel-0"]'
            panel_1_xpath = f'//*[@id="arco-tabs-{tab_id_number}-panel-1"]'
            
            logger.info(f"使用 tab ID: {tab_id_number}")
            logger.info(f"  tab-0: {tab_0_xpath}")
            logger.info(f"  tab-1: {tab_1_xpath}")
            
            # 检测有哪些 tab
            tabs_info = []
            
            # 检查 tab-0
            try:
                tab_0_elem = page.locator(f'xpath={tab_0_xpath}')
                if tab_0_elem.count() > 0:
                    tab_0_text_elem = tab_0_elem.locator('xpath=./span/span').first
                    tab_0_full_text = tab_0_text_elem.inner_text().strip()
                    logger.info(f"Tab-0 文本: {tab_0_full_text}")
                    
                    # 判断类型
                    if 'video' in tab_0_full_text.lower():
                        tab_type = 'video'
                    elif 'LIVE' in tab_0_full_text or 'live' in tab_0_full_text.lower():
                        tab_type = 'live'
                    else:
                        tab_type = None
                    
                    if tab_type:
                        # 提取数量
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
            
            # 检查 tab-1
            try:
                tab_1_elem = page.locator(f'xpath={tab_1_xpath}')
                if tab_1_elem.count() > 0:
                    tab_1_text_elem = tab_1_elem.locator('xpath=./span/span').first
                    tab_1_full_text = tab_1_text_elem.inner_text().strip()
                    logger.info(f"Tab-1 文本: {tab_1_full_text}")
                    
                    # 判断类型
                    if 'video' in tab_1_full_text.lower():
                        tab_type = 'video'
                    elif 'LIVE' in tab_1_full_text or 'live' in tab_1_full_text.lower():
                        tab_type = 'live'
                    else:
                        tab_type = None
                    
                    if tab_type:
                        # 提取数量
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
            
            # 依次处理每个 tab
            for tab_info in tabs_info:
                tab_type = tab_info['type']
                tab_count = tab_info['count']
                tab_xpath = tab_info['tab_xpath']
                panel_xpath = tab_info['panel_xpath']
                
                logger.info(f"\n{'='*50}")
                logger.info(f"处理标签: {tab_type} (数量: {tab_count})")
                logger.info(f"{'='*50}")
                
                # 点击 tab
                try:
                    logger.info(f"点击 tab: {tab_xpath}")
                    tab_elem = page.locator(f'xpath={tab_xpath}')
                    tab_elem.click(timeout=5000)
                    self.delay(2)
                    logger.info(f"✓ 已点击 {tab_type} 标签")
                except Exception as e:
                    logger.error(f"点击 {tab_type} 标签失败: {e}")
                    continue
                
                # 提取当前 panel 的数据
                try:
                    promotions = self.extract_promotion_data_by_xpath(page, panel_xpath, tab_type)
                    
                    for promo in promotions:
                        row = row_data.copy()
                        row['creator_name'] = creator_name
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
            
            # 统计总数
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

    def save_to_excel(self, rows: list):
        """保存数据到Excel（追加模式）- 防止科学计数法版本"""
        if not rows:
            logger.warning("没有数据需要保存")
            return
        
        try:
            # 读取现有数据（如果文件存在）
            if os.path.exists(self.output_file):
                existing_df = pd.read_excel(self.output_file, engine='openpyxl', dtype=str)  # 全部读取为字符串
                logger.info(f"读取现有文件，已有 {len(existing_df)} 行数据")
            else:
                existing_df = pd.DataFrame()
                logger.info("创建新文件")
            
            # 新数据 - 确保ID列为字符串
            new_df = pd.DataFrame(rows)
            
            # 将ID相关列转换为字符串，防止科学计数法
            id_columns = ['product_id', 'campaign_id', 'creator_id', 'partner_id']
            for col in id_columns:
                if col in new_df.columns:
                    new_df[col] = new_df[col].astype(str)
            
            # 合并数据
            if not existing_df.empty:
                # 确保existing_df的ID列也是字符串
                for col in id_columns:
                    if col in existing_df.columns:
                        existing_df[col] = existing_df[col].astype(str)
                
                df = pd.concat([existing_df, new_df], ignore_index=True)
            else:
                df = new_df
            
            # 再次确保所有ID列都是字符串格式
            for col in id_columns:
                if col in df.columns:
                    df[col] = df[col].astype(str)
            
            # 使用ExcelWriter保存，明确指定列格式
            with pd.ExcelWriter(self.output_file, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
                
                # 获取worksheet
                worksheet = writer.sheets['Sheet1']
                
                # 设置ID列的格式为文本
                from openpyxl.styles import numbers
                
                # 找到ID列的索引
                for col_idx, col_name in enumerate(df.columns, 1):
                    if col_name in id_columns:
                        # 设置整列为文本格式
                        for row_idx in range(2, len(df) + 2):  # 从第2行开始（跳过表头）
                            cell = worksheet.cell(row=row_idx, column=col_idx)
                            cell.number_format = numbers.FORMAT_TEXT
                            # 确保值是字符串
                            if cell.value is not None:
                                cell.value = str(cell.value)
            
            logger.info(f"✓ 已保存 {len(rows)} 行新数据，文件总行数: {len(df)}")
            logger.info(f"  保存位置: {self.output_file}")
            
        except Exception as e:
            logger.error(f"保存Excel失败: {e}")
            import traceback
            traceback.print_exc()

    def crawl_current_page(self, page) -> list:
        """爬取当前页面的所有数据"""
        logger.info("开始爬取当前页面...")
        all_page_rows = []
        
        try:
            # 获取所有表格行 - 注意：tbody下的tr才是数据行
            tbody = page.locator('tbody').first
            rows = tbody.locator('tr.arco-table-tr').all()
            logger.info(f"找到 {len(rows)} 行数据")
            
            for idx, row in enumerate(rows, 1):
                logger.info(f"\n{'='*50}")
                logger.info(f"处理第 {idx} 行...")
                logger.info(f"{'='*50}")
                
                # 用于存储当前行的所有数据
                current_row_data = []
                
                try:
                    # 提取基础数据
                    row_data = self.extract_row_data(page, row)
                    
                    # 获取creator_name
                    creator_name = self.get_creator_name(page, row)
                    
                    # 获取action类型
                    action = ""
                    try:
                        buttons = row.locator('button span').all()
                        if not buttons:
                            action = ""
                        else:
                            for btn in buttons:
                                btn_text = btn.inner_text().strip()
                                if btn_text in ["Approve", "View logistics", "View content", "Contact seller", "Message creator"]:
                                    action = btn_text
                                    break
                            # 若所有按钮都不匹配以上关键词，则视为空
                            if not action:
                                action = ""
                    except Exception as e:
                        logger.debug(f"提取 action 失败: {e}")
                        action = ""
                    
                    row_data['action'] = action
                    logger.info(f"Action类型: {action}")
                    
                    # 如果是View content，需要点击进去获取详细数据
                    if action == "View content":
                        try:
                            logger.info("点击View content按钮...")
                            view_btn = row.locator('button:has-text("View content")').first
                            view_btn.click()
                            self.delay(3)

                            # 暂时不增加计数器，先使用当前值（不变）
                            current_tab_id = self.view_content_counter + 1  # 预备使用的编号

                            logger.info(f"尝试使用 tab_id_number={current_tab_id} 处理View content...")
                            content_rows = self.process_view_content(page, row_data, creator_name, current_tab_id)

                            # 如果确实提取到了数据（至少一条），再正式递增计数器
                            if content_rows and len(content_rows) > 0:
                                self.view_content_counter += 1
                                logger.info(f"✓ 提取成功，View content 计数器更新为: {self.view_content_counter}")
                            else:
                                logger.warning("✗ 本次未提取到任何内容，保持计数器不变")
                            current_row_data.extend(content_rows)
                            
                            logger.info("关闭View content弹窗...")

                            try:
                                # 获取所有弹窗（包括隐藏的旧弹窗）
                                drawers = page.locator('.arco-drawer')
                                drawer_count = drawers.count()
                                logger.info(f"检测到 {drawer_count} 个弹窗实例，准备筛选可见的")

                                visible_close_btn = None
                                for i in range(drawer_count):
                                    drawer = drawers.nth(i)
                                    # 检查该弹窗是否可见
                                    is_visible = drawer.is_visible()
                                    if is_visible:
                                        logger.info(f"第 {i+1} 个抽屉可见，查找关闭按钮...")
                                        # 在这个抽屉范围内查找关闭按钮
                                        btn = drawer.locator('span.arco-icon-hover.arco-drawer-close-icon').first
                                        if btn.count() > 0:
                                            visible_close_btn = btn
                                            logger.info(f"✓ 找到可见抽屉的关闭按钮")
                                            break
                                    else:
                                        logger.debug(f"第 {i+1} 个抽屉不可见，跳过")

                                if visible_close_btn:
                                    # 强制点击可见抽屉的关闭按钮
                                    visible_close_btn.click(timeout=1000, force=True)
                                    logger.info("✓ 成功点击可见弹窗关闭按钮")
                                    self.delay(0.5)
                                else:
                                    logger.warning("✗ 未找到可见抽屉的关闭按钮，改用ESC退出")
                                    page.keyboard.press('Escape')
                                    self.delay(0.5)

                                # 双保险：若弹窗仍存在（未隐藏），再按一次ESC
                                if page.locator('.arco-drawer[style*="display: block"]').count() > 0:
                                    logger.info("检测到抽屉仍显示，执行二次ESC关闭")
                                    page.keyboard.press('Escape')
                                    self.delay(0.5)

                                logger.info("✓ 弹窗关闭完成")

                            except Exception as e:
                                logger.warning(f"关闭弹窗异常: {e}，执行紧急ESC")
                                try:
                                    page.keyboard.press('Escape')
                                    self.delay(0.5)
                                except:
                                    pass
                                
                        except Exception as e:
                            logger.error(f"处理View content失败: {e}")
                            # 尝试关闭可能打开的弹窗
                            try:
                                page.keyboard.press('Escape')
                                self.delay(1)
                            except:
                                pass
                    else:
                        # 非View content的情况，直接保存一行
                        row_data['creator_name'] = creator_name
                        row_data['type'] = ""
                        row_data['type_number'] = ""
                        row_data['promotion_name'] = ""
                        row_data['promotion_time'] = ""
                        row_data['promotion_view'] = ""
                        row_data['promotion_like'] = ""
                        row_data['promotion_comment'] = ""
                        row_data['promotion_order'] = ""
                        row_data['promotion_earn'] = ""
                        row_data['region'] = self.region
                        row_data['extracted_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        current_row_data.append(row_data)
                    
                    # 立即保存当前行的数据
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

    def has_next_page(self, page) -> bool:
        """检查是否有下一页"""
        try:
            next_btn = page.locator('li.arco-pagination-item-next').first
            # 检查是否禁用
            is_disabled = next_btn.get_attribute('aria-disabled')
            return is_disabled != 'true'
        except:
            return False

    def goto_next_page(self, page) -> bool:
        """跳转到下一页"""
        try:
            logger.info("点击下一页...")
            next_btn = page.locator('li.arco-pagination-item-next').first
            next_btn.click()
            self.delay(3)
            
            # 等待新页面加载
            self.wait_for_available_samples_text(page, timeout=30)
            self.delay(2)
            
            logger.info("✓ 已跳转到下一页")
            return True
        except Exception as e:
            logger.error(f"跳转下一页失败: {e}")
            return False

    def run(self) -> bool:
        """运行完整流程"""
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

                # 1. 登录
                if not self.login(self.page):
                    logger.error("登录失败，程序终止")
                    return False

                # 确认登录成功
                if not self.check_login_success(self.page):
                    logger.error("登录状态验证失败，程序终止")
                    return False

                self.delay(2)

                # 2. 跳转到样品请求页面
                if not self.navigate_to_sample_requests(self.page):
                    logger.error("跳转失败，程序终止")
                    return False
                
                self.delay(2)

                # 3. 等待 'Available samples' 文本
                self.wait_for_available_samples_text(self.page, timeout=30)
                
                self.delay(2)

                # 4. 点击All或其他备选标签
                if not self.click_tab(self.page):
                    logger.warning(f"点击 '{self.tab_mapping.get(self.tab, 'All')}' 标签失败，继续")
                else:
                    # 点击标签后，重新等待页面加载
                    self.delay(2)
                    self.wait_for_available_samples_text(self.page, timeout=30)

                self.delay(2)

                # 5. 开始爬取所有页面
                page_num = 1
                total_rows = 0
                
                while True:
                    logger.info(f"\n{'='*60}")
                    logger.info(f"开始爬取第 {page_num} 页")
                    logger.info(f"{'='*60}")
                    
                    # 爬取当前页（会自动保存每一行）
                    page_rows = self.crawl_current_page(self.page)
                    total_rows += len(page_rows)
                    
                    logger.info(f"第 {page_num} 页完成，本页共 {len(page_rows)} 行数据")
                    
                    # 检查是否有下一页
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
    """主函数，支持命令行参数"""
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
    
    args = parser.parse_args()
    
    # 创建爬虫实例并运行
    crawler = SampleAllCrawler(region=args.region.upper(), tab=args.tab.lower())
    success = crawler.run()
    
    # 返回状态码
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()


# 爬取All标签（默认）
# nohup python -u manage_sample/sample_all.py --tab all > logs/sample_all.log 2>&1 &

# 爬取To review标签
# nohup python -u manage_sample/sample_all.py --tab review > logs/sample_review.log 2>&1 &

# 爬取Ready to ship标签
# nohup python -u manage_sample/sample_all.py --tab ready > logs/sample_ready.log 2>&1 &

# 爬取Shipped标签
# nohup python -u manage_sample/sample_all.py --tab shipped > logs/sample_shipped.log 2>&1 &

# 爬取Content pending标签
# nohup python -u manage_sample/sample_all.py --tab pending > logs/sample_pending.log 2>&1 &

# 爬取Completed标签
# nohup python -u manage_sample/sample_all.py --tab completed > logs/sample_completed.log 2>&1 &

# 爬取Canceled标签
# nohup python -u manage_sample/sample_all.py --tab canceled > logs/sample_canceled.log 2>&1 &

# 指定区域和标签
# nohup python -u manage_sample/sample_all.py --region FR --tab review > logs/sample_fr_review.log 2>&1 &