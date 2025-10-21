# -*- coding: utf-8 -*-
# 多链接抓取 TikTok 评论（主评优先 + 可选只抓主评 + 硬上限150 + 验证检测 + 楼中楼展开、全局收集）
from playwright.sync_api import sync_playwright
import time, re, json, os, subprocess, requests, random
from typing import List, Dict, Tuple, Optional
import pandas as pd
from urllib.parse import urlparse

# --- 可选：Windows 应用音量控制（用于取消静音并拉满 Edge 音量） ---
try:
    from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume  # pip install pycaw comtypes
    HAVE_PYCAW = True
except Exception:
    HAVE_PYCAW = False

def set_app_volume(process_names=("msedge.exe", "chrome.exe"), volume=1.0, mute=False, tries=15, sleep_s=0.2) -> int:
    """
    将指定进程名的音量设置为指定值（0.0~1.0），并取消静音；返回命中的会话数量。
    由于音频会话在进程启动后才出现，这里会短轮询等待会话出现。
    """
    if not HAVE_PYCAW:
        return 0
    hit_total = 0
    for _ in range(max(1, tries)):
        hit = 0
        try:
            for s in AudioUtilities.GetAllSessions():
                p = getattr(s, "Process", None)
                if not p:
                    continue
                name = (p.name() or "").lower()
                if name in process_names:
                    try:
                        sv = s._ctl.QueryInterface(ISimpleAudioVolume)
                        sv.SetMute(bool(mute), None)
                        sv.SetMasterVolume(float(volume), None)  # 0.0~1.0
                        hit += 1
                    except Exception:
                        pass
        except Exception:
            pass
        hit_total = max(hit_total, hit)
        if hit > 0:
            break
        time.sleep(sleep_s)
    return hit_total

# ====== 源链接（不传命令行参数时使用）======
VIDEO_SOURCES = [
    "https://www.tiktok.com/@stephale16/video/7511077669191093522",
]

# ====== 滚动/策略参数 ======
MAX_ROUNDS = 240
MAIN_STABLE_TRIGGER = 5
TOTAL_STABLE_ROUNDS = 5
ROUND_SLEEP_S = 1.2
REPLY_CLICK_SLEEP = 1.2
WHEEL_STEPS_PER_ROUND = (5, 8)
DELTA_Y_RANGE = (180, 250)

# ====== 新增：抓取总数硬上限（主评+楼中楼合计）======
MAX_COMMENTS = 150

# ====== 展开楼中楼策略 ======
EXPAND_PASS_MAX_CLICKS = 60
EXPAND_MAX_ROUNDS = 6
EXPAND_STILL_TOLERANCE = 2

# ====== 快速策略 ======
FAST_STOP_NO_CHANGE = 2  # 当需要很多条且连续 X 轮无新增则可早停


class TikTokCommentScraper:
    def __init__(self, edge_user_data_dir=None, max_comments: int = MAX_COMMENTS, main_only: bool = False):
        self.edge_user_data_dir = edge_user_data_dir or self.get_default_edge_user_data()
        self.last_verification_check = 0.0
        self.playwright = None
        self.browser = None
        self.verification_count = 0
        self.should_extract_replies = True     # Hybrid 时用于控制是否展开楼中楼
        self.max_comments = max_comments       # 硬上限
        self.main_only = main_only             # 只抓主评模式

    def get_default_edge_user_data(self) -> str:
        username = os.getenv('USER')
        paths = [
            f"/Users/{username}/Library/Application Support/Google/Chrome/Default",  # Chrome
            f"/Users/{username}/Library/Application Support/Microsoft Edge/Default",  # Edge
        ]
        for p in paths:
            if os.path.exists(p):
                return p
        return paths[0]

    # ---------- 启动与连接 ----------
    def start_edge_with_debug_port(self, port=9222):
        try:
            r = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=1.5)
            if r.status_code == 200:
                print(f"✅ Chrome调试端口已在运行: {port}")
                # 端口已在运行，尝试拉满音量
                try:
                    set_app_volume(("msedge.exe",), volume=1.0, mute=False)
                except Exception:
                    pass
                return True
        except:
            pass
        try:
            subprocess.run("taskkill /F /IM msedge.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2)
        except:
            pass
        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if not os.path.exists(chrome_path):
            print("未找到Chrome")
            return False
        cmd = [
            chrome_path,
            f'--user-data-dir={self.edge_user_data_dir}',
            '--profile-directory=Default',
            f'--remote-debugging-port={port}',
            '--start-maximized',
            '--disable-web-security',
            '--disable-features=VizDisplayCompositor',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
            '--disable-field-trial-config',
            '--disable-ipc-flooding-protection',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-default-apps',
            '--disable-extensions-except=',
            '--disable-plugins-discovery',
            '--disable-background-networking',
            '--disable-sync',
            '--disable-translate',
            '--hide-scrollbars',
            # '--mute-audio',  # 移除静音参数
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-zygote',
            '--disable-gpu'
        ]
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("✅ 已启动Edge（带调试端口，保留扩展/登录）")
            # 启动后尝试取消静音并拉满音量
            try:
                hit = set_app_volume(("msedge.exe",), volume=1.0, mute=False, tries=20, sleep_s=0.2)
                if hit > 0:
                    print("🔊 已尝试取消静音并拉满 Edge 音量")
            except Exception:
                pass
            return True
        except Exception as e:
            print(f"❌ 启动Edge失败: {e}")
            return False

    def _stabilize_video_page(self, page, url: str):
        # 调整：不再强制把 video 静音或暂停，允许播放且非静音
        page.add_init_script("""
        (() => {
          const stop = (e) => { try { e.stopImmediatePropagation(); } catch(_){} };
          window.addEventListener('beforeunload', stop, true);
          window.addEventListener('pagehide', stop, true);
          document.addEventListener('visibilitychange', stop, true);
          setInterval(()=>{ try{
            const v=document.querySelector('video');
            if(v){
              v.loop=true;
              v.muted=false;
              if(v.paused) v.play().catch(()=>{});
            }
          }catch(e){} }, 2000);
        })();
        """)
        try:
            page.wait_for_selector("video", state="attached", timeout=4000)
            page.evaluate("""
            (() => {
              const v = document.querySelector('video');
              if(!v) return;
              v.muted = false; v.loop = true; v.playbackRate = 1.0;
              try { if(v.paused) v.play().catch(()=>{}); } catch(_){}
            })();
            """)
        except Exception:
            pass

    def _open_comments_drawer(self, page):
        sels = [
            '[data-e2e="browse-comment-icon"]',
            '[data-e2e="video-detail-comment"]',
            'button[aria-label*="Comments"]',
            'button:has(svg[aria-label*="comment"])',
        ]
        for sel in sels:
            try:
                el = page.locator(sel).first
                if el.count():
                    el.click(timeout=1500)
                    page.wait_for_timeout(600)
                    return
            except Exception:
                pass
        try:
            page.keyboard.press("c")
            page.wait_for_timeout(500)
        except Exception:
            pass

    def _guard_stay_on_video(self, page, url: str):
        try:
            if "/video/" not in page.url:
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(600)
                self._stabilize_video_page(page, url)
                self._open_comments_drawer(page)
        except Exception:
            pass

    def wait_for_debug_ready(self, port=9222, max_wait=15):
        for i in range(max_wait):
            try:
                r = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=2)
                if r.status_code == 200:
                    print(f"✅ 调试端口就绪，用时 {i + 1}s")
                    return True
            except:
                pass
            time.sleep(1)
        return False

    def connect_to_running_edge(self, port=9222):
        try:
            self.playwright = sync_playwright().start()
            try:
                self.browser = self.playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=30000)
                print("✅ 已连接到正在运行的Edge")
                # 连接成功后再次确保音量拉满
                try:
                    set_app_volume(("msedge.exe",), volume=1.0, mute=False)
                except Exception:
                    pass
                return True
            except Exception as e:
                print(f"⚠️ 连接失败: {e}")
                self.start_edge_with_debug_port(port)
                time.sleep(5)
                try:
                    self.browser = self.playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=30000)
                    print("✅ 重新连接成功")
                    try:
                        set_app_volume(("msedge.exe",), volume=1.0, mute=False)
                    except Exception:
                        pass
                    return True
                except Exception as e2:
                    print(f"❌ 重新连接也失败: {e2}")
                    return False
        except Exception as e:
            print(f"❌ Playwright启动失败: {e}")
            return False

    def force_navigate(self, page, url):
        tries = [
            lambda: page.goto(url, wait_until="domcontentloaded", timeout=60000),
            lambda: page.evaluate(f'location.href="{url}"'),
            lambda: page.evaluate(f'window.open("{url}","_self")'),
        ]
        for fn in tries:
            try:
                fn()
                try:
                    page.wait_for_url("**/video/**", timeout=30000)
                except:
                    pass
                if "/video/" in (page.url or ""):
                    return True
            except:
                pass
        try:
            newp = page.context.new_page()
            newp.bring_to_front()
            newp.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                newp.wait_for_url("**/video/**", timeout=30000)
            except:
                pass
            if "/video/" in (newp.url or ""):
                return newp
        except:
            pass
        return False

    # ---------- 解析/检测 ----------
    def _parse_compact_count(self, text: str) -> int:
        if not text:
            return 0
        t = text.strip().replace(',', '').replace(' ', '')
        m = re.match(r'^(\d+(?:\.\d+)?)([KkMmBb]?)$', t)
        if m:
            num = float(m.group(1)); suf = m.group(2).lower()
            return int(num * (1000 if suf=='k' else 1_000_000 if suf=='m' else 1_000_000_000 if suf=='b' else 1))
        m2 = re.search(r'(\d[\d, ]*)', text)
        return int(re.sub(r'[^\d]', '', m2.group(1))) if m2 else 0

    def get_video_stats(self, page) -> Dict:
        stats = {'likes': None, 'comments': None, 'shares': None}
        candidates = {
            'likes':    ['[data-e2e="like-count"]','strong[data-e2e="like-count"]','button[aria-label*="Like"] span','button:has(svg[aria-label*="Like"]) span','button:has-text("Like") span'],
            'comments': ['[data-e2e="comment-count"]','strong[data-e2e="comment-count"]','button[aria-label*="Comment"] span','button:has(svg[aria-label*="Comment"]) span','button:has-text("Comment") span'],
            'shares':   ['[data-e2e="share-count"]','strong[data-e2e="share-count"]','button[aria-label*="Share"] span','button:has(svg[aria-label*="Share"]) span','button:has-text("Share") span'],
        }
        for key, sels in candidates.items():
            for sel in sels:
                try:
                    loc = page.locator(sel)
                    if loc.count() > 0:
                        stats[key] = self._parse_compact_count(loc.first.inner_text().strip()); break
                except:
                    continue
        return stats

    def get_target_total(self, page) -> int:
        try:
            for sel in (
                '[data-e2e="comment-count"]',
                'strong[data-e2e="comment-count"]',
                'button[aria-label*="Comment"] span',
                'button:has(svg[aria-label*="Comment"]) span',
                'button:has-text("Comment") span',
            ):
                loc = page.locator(sel)
                if loc.count() > 0:
                    txt = loc.first.inner_text().strip()
                    val = self._parse_compact_count(txt)
                    if val > 0:
                        return val
        except:
            pass
        try:
            loc = page.locator('text=/评论\\s*\\(\\s*\\d[\\d,\\.]*\\s*\\)/i')
            if loc.count() > 0:
                txt = loc.first.inner_text().strip()
                m = re.search(r'(\d[\d,\.]*)', txt)
                if m:
                    return int(re.sub(r'[^\d]', '', m.group(1)))
        except:
            pass
        try:
            loc = page.locator('text=/Comments?\\s*\\(\\s*\\d[\\d,\\.]*\\s*\\)/i')
            if loc.count() > 0:
                txt = loc.first.inner_text().strip()
                m = re.search(r'(\d[\d,\.]*)', txt)
                if m:
                    return int(re.sub(r'[^\d]', '', m.group(1)))
        except:
            pass
        return -1

    def _is_verify_present(self, page) -> dict:
        reasons, score = [], 0
        try:
            puzzle_selectors = [
                'text=/Drag the puzzle piece into place/i','text=/拖拽拼图/i',
                'div[class*="puzzle"]','div[class*="captcha"]:has-text("puzzle")',
                'div[class*="drag"]:has-text("puzzle")','div[role="dialog"]:has-text("puzzle")',
                'div[aria-modal="true"]:has-text("puzzle")'
            ]
            if any(page.locator(sel).count() > 0 for sel in puzzle_selectors):
                reasons.append("拼图验证码"); score += 3

            dialog_selectors = [
                'div[role="dialog"]:has-text("验证")','div[role="dialog"]:has-text("verify")',
                'div[role="dialog"]:has-text("captcha")','div[aria-modal="true"]:has-text("验证")',
                'div[class*="captcha"]:visible','div[id*="captcha"]:visible','div[class*="verify"]:visible',
                'div[id*="verify"]:visible','div[class*="challenge"]:visible'
            ]
            if any(page.locator(sel).count() > 0 for sel in dialog_selectors):
                reasons.append("验证对话框"); score += 3

            for frame in page.frames:
                url = (frame.url or "").lower()
                if any(k in url for k in ["verify","captcha","challenge","recaptcha","hcaptcha"]):
                    reasons.append(f"验证iframe:{url}"); score += 2; break

            current_url = (page.url or "").lower()
            if any(k in current_url for k in ["verify","captcha","challenge","robot"]):
                reasons.append("URL疑似验证"); score += 2

            try:
                loading_selectors = ['div[class*="loading"]:has-text("验证")','div[class*="spinner"]:has-text("验证")','div[class*="mask"]:has-text("验证")']
                for sel in loading_selectors:
                    if page.locator(sel).count() > 0 and page.locator(sel).first.is_visible():
                        time.sleep(2)
                        if page.locator(sel).first.is_visible():
                            reasons.append("验证遮罩持续可见"); score += 2; break
            except:
                pass

            try:
                comment_selectors = ['[data-e2e="comment-level-1"]','[data-e2e="comment-list"]','div[class*="CommentList"]']
                has_comment = any(page.locator(sel).count() > 0 for sel in comment_selectors)
                if not has_comment:
                    if any(page.locator(v).count() > 0 for v in ['div[class*="captcha"]','div[class*="verify"]','text=/人机验证|安全验证/i']):
                        reasons.append("评论区缺失且存在验证元素"); score += 2
            except:
                pass

            weak_texts = ['text=/请完成验证|安全验证|人机验证|滑动验证|点击验证/i','text=/verify|verification|captcha|challenge|security|robot/i',
                          'button:has-text("验证")','button:has-text("Verify")','button:has-text("继续")','button:has-text("Continue")']
            if any(page.locator(sel).count() > 0 for sel in weak_texts):
                reasons.append("弱信号文本存在"); score += 1
        except Exception as e:
            reasons.append(f"检测异常: {str(e)}")

        return {'has_verification': score >= 3, 'score': score, 'reasons': reasons}

    def smart_verification_check(self, page, context=""):
        current_time = time.time()
        min_interval = 8 if self.verification_count >= 3 else 5 if self.verification_count >= 1 else 3
        if current_time - self.last_verification_check < min_interval:
            return
        result = self._is_verify_present(page)
        if result['has_verification']:
            self.verification_count += 1
            print(f"🛑 检测到验证（{context}），评分 {result['score']}")
            for reason in result['reasons'][:6]:
                print(f"   • {reason}")
            print("👉 请在浏览器完成验证后按回车继续...")
            input()
            print("⏳ 等待验证完成...")
            start_time = time.time()
            while time.time() - start_time < 60:
                after = self._is_verify_present(page)
                if not after['has_verification']:
                    print("✅ 验证完成，继续抓取")
                    self.last_verification_check = time.time()
                    return
                time.sleep(1)
            print("⚠️ 验证可能仍在进行，尝试继续抓取...")
        self.last_verification_check = current_time

    # ---------- 计数 ----------
    def _count_by_priority(self, page, selectors) -> int:
        for sel in selectors:
            try:
                cnt = page.locator(sel).count()
                if cnt > 0: return cnt
            except:
                pass
        return 0

    def count_main(self, page) -> int:
        return self._count_by_priority(page, [
            '[data-e2e="comment-level-1"]',
            'div[data-e2e="comment-item"][data-level="1"]',
            'div[class*="CommentItem"][class*="level-1"]',
        ])

    def count_replies(self, page) -> int:
        direct = self._count_by_priority(page, [
            '[data-e2e="comment-level-2"]',
            'div[data-e2e="comment-item"][data-level="2"]',
            'div[class*="CommentItem"][class*="level-2"]',
        ])
        if direct > 0: return direct
        all_cnt = self._count_by_priority(page, ['div[data-e2e="comment-item"]'])
        if all_cnt == 0:
            all_cnt = page.locator('[data-e2e="comment-level-1"], [data-e2e="comment-level-2"]').count()
            if all_cnt == 0:
                all_cnt = page.locator('div[class*="CommentItem"]').count()
        main_cnt = self.count_main(page)
        return max(0, all_cnt - main_cnt)

    def _comment_container(self, page):
        for sel in ('[data-e2e="comment-list"]','div[class*="CommentList"]','div[data-e2e*="comment"] div[style*="overflow"]'):
            loc = page.locator(sel)
            if loc.count() > 0: return loc.first
        return None

    def get_adaptive_params(self, remaining: Optional[int] = None):
        """
        根据 verification_count 和 remaining（还需要抓取的条数）动态调整滚动策略。
        remaining=None 表示未知
        """
        # base
        if self.verification_count >= 3:
            base_round_sleep = 2.0; base_wheel = (3,5); base_delta = (120,180)
        elif self.verification_count >= 1:
            base_round_sleep = 1.5; base_wheel = (4,6); base_delta = (150,220)
        else:
            base_round_sleep = ROUND_SLEEP_S; base_wheel = WHEEL_STEPS_PER_ROUND; base_delta = DELTA_Y_RANGE

        # 如果还需很多条，倾向更快但更激进的滚动
        if remaining is not None:
            if remaining >= 80:
                return {'round_sleep': max(0.5, base_round_sleep * 0.6), 'wheel_steps': (8, 12), 'delta_y': (220, 380)}
            if remaining >= 40:
                return {'round_sleep': max(0.7, base_round_sleep * 0.75), 'wheel_steps': (6, 10), 'delta_y': (200, 320)}
            if remaining >= 20:
                return {'round_sleep': max(0.9, base_round_sleep * 0.85), 'wheel_steps': (5, 9), 'delta_y': (180, 300)}
        return {'round_sleep': base_round_sleep, 'wheel_steps': base_wheel, 'delta_y': base_delta}

    def micro_scroll_with_verification_check(self, page, round_idx, remaining: Optional[int] = None):
        params = self.get_adaptive_params(remaining)
        if round_idx % 5 == 0:
            self.smart_verification_check(page, f"轮 {round_idx} 滚动前")
        cont = self._comment_container(page)
        steps = random.randint(*params['wheel_steps'])
        for _ in range(steps):
            dy = random.randint(*params['delta_y'])
            try:
                if cont: cont.evaluate(f"(el)=>el.scrollBy(0,{dy})")
                page.mouse.wheel(0, dy + random.randint(-15, 15))
            except:
                pass
            time.sleep(params['round_sleep'] * random.uniform(0.7, 1.05))
        for key in ("PageDown", "End"):
            try: page.keyboard.press(key)
            except: pass
        # 少量延时等待内容加载
        time.sleep(0.9)
        if round_idx % 3 == 0:
            self.smart_verification_check(page, f"轮 {round_idx} 滚动后")

    def wait_skeleton_quiet(self, page, timeout=2.0):
        try:
            for sel in ['div[class*="skeleton"]','div[class*="loading"]','div[class*="placeholder"]']:
                try: page.wait_for_selector(sel, state="hidden", timeout=int(timeout*1000))
                except: pass
        except: pass
        time.sleep(timeout * 0.6)

    # ---------- 楼中楼展开 ----------
    def _is_reply_button_text(self, txt: str) -> bool:
        if not txt: return False
        t = txt.strip()
        if any(k.lower() in t.lower() for k in ("翻译","translation","更多","more","详情","detail","展开","expand")):
            return False
        return bool(re.search(r'(查看|view).*(\d+).*(回复|repl|评论|comment)', t, flags=re.I))

    def _gather_reply_buttons(self, page) -> List:
        locators = []
        selectors = [
            'button:has-text("查看")','button:has-text("回复")',
            'button:has-text("repl")','button:has-text("comment")',
            'text=/查看.*(条)?(回复|评论)/i','text=/View.*repl/i',
        ]
        for sel in selectors:
            try:
                loc = page.locator(sel); cnt = loc.count()
                for i in range(cnt):
                    el = loc.nth(i)
                    try: t = el.inner_text().strip()
                    except: t = ""
                    if self._is_reply_button_text(t): locators.append(el)
            except: continue
        uniq, seen = [], set()
        for el in locators:
            try:
                handle = el.evaluate_handle("el=>el"); hid = str(handle)
                if hid not in seen:
                    seen.add(hid); uniq.append(el)
            except:
                uniq.append(el)
        return uniq

    def _scroll_into_view_and_click(self, el) -> bool:
        try: el.scroll_into_view_if_needed(timeout=3000)
        except: pass
        try:
            el.click(timeout=3000); return True
        except:
            try:
                el.evaluate("(b)=>b.click()"); return True
            except:
                return False

    def expand_replies_pass(self, page, max_clicks=EXPAND_PASS_MAX_CLICKS) -> int:
        """
        先尝试 JS 批量点击（速度快），失败则回退为 locator 方式逐个点击（稳定）。
        """
        clicked = 0
        try:
            clicked = self.expand_replies_pass_js(page, max_clicks)
            if clicked > 0:
                return clicked
        except Exception:
            pass
        # 回退到原先方式
        btns = self._gather_reply_buttons(page)
        if not btns: return 0
        for el in btns:
            if clicked >= max_clicks: break
            try:
                txt = ""
                try: txt = el.inner_text().strip()
                except: pass
                if not self._is_reply_button_text(txt): continue
                ok = self._scroll_into_view_and_click(el)
                if ok:
                    clicked += 1
                    time.sleep(REPLY_CLICK_SLEEP)
            except:
                continue
        return clicked

    def expand_replies_pass_js(self, page, max_clicks=EXPAND_PASS_MAX_CLICKS) -> int:
        """
        使用 page.evaluate 在 DOM 中寻找符合回复按钮文本的元素并批量 click。
        返回实际点击数。
        """
        script = r'''
        (maxClicks) => {
          try {
            const out = [];
            const candidates = Array.from(document.querySelectorAll('button, a, span, div'));
            const isBad = (t) => /翻译|translation|更多|more|详情|detail|展开|expand/i.test(t);
            const ok = (t) => /(查看|view).*(\d+).*(回复|repl|评论|comment)/i.test(t) && !isBad(t);
            let clicked = 0;
            for (const el of candidates) {
              try {
                const t = (el.innerText || '').trim();
                if (!t) continue;
                if (!ok(t)) continue;
                el.scrollIntoView({block:'center'});
                try { el.click(); } catch(e){ 
                    // fallback dispatch event
                    const ev = document.createEvent('MouseEvents');
                    ev.initMouseEvent('click', true, true, window);
                    el.dispatchEvent(ev);
                }
                clicked++;
                if (clicked >= maxClicks) break;
              } catch(e) {}
            }
            return clicked;
          } catch(e) { return 0; }
        }
        '''
        try:
            n = page.evaluate(script, max_clicks)
            # 稍作等待让内容加载
            if n:
                page.wait_for_timeout(600)
            return int(n)
        except Exception:
            return 0

    def expand_all_replies(self, page) -> int:
        total_clicked, no_change = 0, 0
        for r in range(1, EXPAND_MAX_ROUNDS + 1):
            c = self.expand_replies_pass(page)
            total_clicked += c
            print(f"   ↳ 展开轮 {r}: 点击 {c} 个")
            if c == 0: no_change += 1
            else: no_change = 0
            try: page.mouse.wheel(0, random.randint(600, 900))
            except: pass
            time.sleep(0.6)
            if no_change >= EXPAND_STILL_TOLERANCE: break
        return total_clicked

    # ---------- 提取 ----------
    def extract_comment_data_from_locator(self, locator, index, level) -> Dict:
        try:
            content_locator = locator.locator('span[class*="TUXText"]')
            content = content_locator.first.inner_text().strip() if content_locator.count() > 0 else "无内容"
            username_locator = locator.locator('a[class*="username"]')
            username = username_locator.first.inner_text().strip() if username_locator.count() > 0 else f"用户{index}"
            time_locator = locator.locator('span[class*="time"]')
            time_text = time_locator.first.inner_text().strip() if time_locator.count() > 0 else "未知时间"

            likes = 0
            like_selectors = [
                'button[aria-label*="Like"] span','button:has(svg[aria-label*="Like"]) span',
                'button:has-text("Like") span','span[class*="like"]','span[class*="count"]',
                'button[class*="like"] span','div[class*="like"] span',
            ]
            extracted = False
            for like_sel in like_selectors:
                like_locator = locator.locator(like_sel)
                if like_locator.count() > 0:
                    txt = like_locator.first.inner_text().strip()
                    if txt:
                        likes = self._parse_compact_count(txt); extracted = True; break
            if not extracted:
                attr_candidates = [
                    ('button[aria-label*="Like"]', ['aria-label', 'title']),
                    ('button[class*="like"]', ['aria-label', 'title']),
                    ('div[class*="like"]', ['aria-label', 'title']),
                ]
                for sel, attrs in attr_candidates:
                    try:
                        btn = locator.locator(sel)
                        if btn.count() > 0:
                            for a in attrs:
                                val = btn.first.get_attribute(a)
                                if val:
                                    likes = self._parse_compact_count(val)
                                    if likes > 0: extracted = True; break
                        if extracted: break
                    except:
                        pass

            reply_count = 0
            for reply_sel in ['text=/查看.*条回复/i','text=/View.*replies/i','text=/回复/i','text=/replies/i','button:has-text("查看")','button:has-text("View")']:
                reply_locator = locator.locator(reply_sel)
                if reply_locator.count() > 0:
                    reply_text = reply_locator.first.inner_text().strip()
                    reply_count = self._parse_compact_count(reply_text); break

            user_id = ""
            try:
                user_link = username_locator.first.get_attribute('href') if username_locator.count() > 0 else ""
                if user_link: user_id = user_link.split('/')[-1] if '/' in user_link else ""
            except:
                pass

            return {
                'index': str(index), 'username': username, 'user_id': user_id,
                'content': content, 'time': time_text, 'likes': likes,
                'reply_count': reply_count, 'level': level,
                'parent_comment': None, 'parent_username': None,
                'is_high_value': likes >= 10 or reply_count >= 5
            }
        except:
            return {'index': str(index), 'username': f"用户{index}", 'user_id': "", 'content': "提取失败",
                    'time': "未知时间", 'likes': 0, 'reply_count': 0, 'level': level,
                    'parent_comment': None, 'parent_username': None, 'is_high_value': False}

    # ===== 新增：JS 批量提取（当评论很多时更快）=====
    def extract_all_comments_via_js(self, page) -> List[Dict]:
        """
        使用 document.querySelectorAll 批量读取评论节点并在前端组装结果，返回 Python 可序列化的结构。
        如果 JS 提取失败则抛异常，调用方应 fallback 到 Python 版本。
        """
        js = r'''
        (maxCount) => {
          try {
            const sel = '[data-e2e="comment-item"], [data-e2e="comment-level-1"], [data-e2e="comment-level-2"], div[class*="CommentItem"]';
            const items = Array.from(document.querySelectorAll(sel));
            const out = [];
            let main_num = 0, reply_num_under_main = 0, last_main_idx = null, last_main_username = null;
            for (let i = 0; i < items.length && out.length < maxCount; i++) {
              const el = items[i];
              const obj = {index: "", username: "", user_id: "", content: "", time: "", likes: 0, reply_count: 0, level: 1, parent_comment: null, parent_username: null, is_high_value: false};
              // detect level
              let lvl = 1;
              try {
                const a = el.getAttribute("data-level") || el.dataset.level || "";
                if (a && a.indexOf("2") !== -1) lvl = 2;
              } catch(e){}
              try {
                const cls = (el.getAttribute("class") || "").toLowerCase();
                if (cls.indexOf("level-2") !== -1) lvl = 2;
                if (cls.indexOf("level-1") !== -1) lvl = 1;
              } catch(e){}
              obj.level = lvl;
              if (lvl === 1) {
                main_num += 1;
                reply_num_under_main = 0;
                const idx_label = String(main_num);
                obj.index = idx_label;
                // username
                let uname = "";
                const ua = el.querySelector('a[href*="/@"], a[class*="username"], a[class*="UserName"]');
                if (ua) uname = (ua.innerText || "").trim();
                if (!uname) {
                  const n = el.querySelector('[data-e2e="user-name"], [data-e2e*="username"]');
                  if(n) uname = (n.innerText||"").trim();
                }
                obj.username = uname || ("用户"+idx_label);
                // user_id
                try {
                  const href = ua ? ua.getAttribute('href') : null;
                  if (href) obj.user_id = href.split('/').filter(Boolean).pop();
                } catch(e){}
                // content
                let content = "";
                const contentEl = el.querySelector('span[class*="TUXText"], [data-e2e="comment-content"], p, div[class*="comment-text"], div[class*="content"]');
                if (contentEl) content = (contentEl.innerText || "").trim();
                obj.content = content || "无内容";
                // time
                let t = "";
                const tEl = el.querySelector('span[class*="time"], time, [data-e2e="comment-time"]');
                if (tEl) t = (tEl.innerText || "").trim();
                obj.time = t || "未知时间";
                // likes
                try {
                  const likeEl = el.querySelector('button[aria-label*="Like"] span, span[class*="like"], span[class*="count"], [data-e2e="comment-like"]');
                  if (likeEl) obj.likes = parseInt((likeEl.innerText||"").replace(/[^\d]/g,"")||0) || 0;
                } catch(e){}
                // reply count
                try {
                  const replyBtn = Array.from(el.querySelectorAll('button, a, span')).find(x => /(查看|view).*(\d+).*(回复|repl|评论|comment)/i.test((x.innerText||"")));
                  if (replyBtn) {
                    const m = (replyBtn.innerText||"").match(/(\d[\d,\,\.]*)/);
                    if (m) obj.reply_count = parseInt((m[1]||"").replace(/[^\d]/g,""))||0;
                  }
                } catch(e){}
                obj.is_high_value = (obj.likes >= 10 || obj.reply_count >= 5);
                last_main_idx = obj.index;
                last_main_username = obj.username;
                out.push(obj);
              } else {
                // reply: attach to last main, if none, promote to main
                if (!last_main_idx) {
                  main_num += 1;
                  reply_num_under_main = 0;
                  const idx_label = String(main_num);
                  // treat as main to avoid orphan
                  const uname = (el.querySelector('a[href*="/@"], a[class*="username"], a[class*="UserName"]')||{innerText:""}).innerText.trim() || ("用户"+idx_label);
                  const contentEl = el.querySelector('span[class*="TUXText"], [data-e2e="comment-content"], p, div[class*="comment-text"], div[class*="content"]');
                  const content = contentEl ? (contentEl.innerText||"").trim() : "无内容";
                  const tEl = el.querySelector('span[class*="time"], time, [data-e2e="comment-time"]');
                  const t = tEl ? (tEl.innerText||"").trim() : "未知时间";
                  out.push({index: idx_label, username: uname, user_id:"", content: content, time: t, likes:0, reply_count:0, level:1, parent_comment:null, parent_username:null, is_high_value:false});
                  last_main_idx = idx_label;
                  last_main_username = uname;
                } else {
                  reply_num_under_main += 1;
                  const idx_label = last_main_idx + "-" + reply_num_under_main;
                  const uname = (el.querySelector('a[href*="/@"], a[class*="username"], a[class*="UserName"]')||{innerText:""}).innerText.trim() || ("用户"+idx_label);
                  const contentEl = el.querySelector('span[class*="TUXText"], [data-e2e="comment-content"], p, div[class*="comment-text"], div[class*="content"]');
                  const content = contentEl ? (contentEl.innerText||"").trim() : "无内容";
                  const tEl = el.querySelector('span[class*="time"], time, [data-e2e="comment-time"]');
                  const t = tEl ? (tEl.innerText||"").trim() : "未知时间";
                  let likes = 0;
                  try {
                    const likeEl = el.querySelector('button[aria-label*="Like"] span, span[class*="like"], span[class*="count"], [data-e2e="comment-like"]');
                    if (likeEl) likes = parseInt((likeEl.innerText||"").replace(/[^\d]/g,"")||0) || 0;
                  } catch(e){}
                  const obj2 = {index: idx_label, username: uname, user_id:"", content: content, time: t, likes: likes, reply_count:0, level:2, parent_comment: last_main_idx, parent_username: last_main_username, is_high_value: (likes>=10)};
                  out.push(obj2);
                }
              }
            }
            return out;
          } catch(e) { return []; }
        }
        '''
        maxc = int(self.max_comments or 1000)
        try:
            res = page.evaluate(js, maxc)
            if not isinstance(res, list):
                return []
            # sanitize keys and types
            out = []
            for r in res:
                if not isinstance(r, dict):
                    continue
                out.append({
                    'index': str(r.get('index','')),
                    'username': r.get('username',''),
                    'user_id': r.get('user_id',''),
                    'content': r.get('content',''),
                    'time': r.get('time',''),
                    'likes': int(r.get('likes') or 0),
                    'reply_count': int(r.get('reply_count') or 0),
                    'level': int(r.get('level') or 1),
                    'parent_comment': r.get('parent_comment'),
                    'parent_username': r.get('parent_username'),
                    'is_high_value': bool(r.get('is_high_value', False))
                })
            return out[:maxc]
        except Exception as e:
            # 上层决定是否 fallback
            raise

    # ===== 新增：全局收集（原 locator 版）=====
    def _detect_level(self, el) -> int:
        try:
            lvl_attr = el.get_attribute("data-level") or ""
            if "2" in lvl_attr: return 2
            if "1" in lvl_attr: return 1
        except: pass
        try:
            cls = (el.get_attribute("class") or "").lower()
            if "level-2" in cls: return 2
            if "level-1" in cls: return 1
        except: pass
        return 1

    def extract_all_comments_globally(self, page) -> List[Dict]:
        all_comments: List[Dict] = []
        last_main_idx = None
        last_main_username = None

        items = page.locator('[data-e2e="comment-item"], [data-e2e="comment-level-1"], [data-e2e="comment-level-2"]')
        cnt = items.count()
        main_num = 0
        reply_num_under_main = 0

        for i in range(cnt):
            if len(all_comments) >= self.max_comments: break
            el = items.nth(i)
            lvl = 1
            try:
                lvl = self._detect_level(el)
            except: pass

            if lvl == 1:
                main_num += 1
                reply_num_under_main = 0
                idx_label = str(main_num)
                d = self.extract_comment_data_from_locator(el, idx_label, 1)
                last_main_idx = idx_label
                last_main_username = d.get("username")
                all_comments.append(d)
            else:
                if last_main_idx is None:
                    main_num += 1
                    idx_label = str(main_num)
                    d = self.extract_comment_data_from_locator(el, idx_label, 1)
                    last_main_idx = idx_label
                    last_main_username = d.get("username")
                    all_comments.append(d)
                else:
                    reply_num_under_main += 1
                    idx_label = f"{last_main_idx}-{reply_num_under_main}"
                    d = self.extract_comment_data_from_locator(el, idx_label, 2)
                    d["parent_comment"] = last_main_idx
                    d["parent_username"] = last_main_username
                    all_comments.append(d)

        return all_comments[: self.max_comments]
    # ===== 新增：全局收集 END =====

    def extract_all_comments(self, page) -> List[Dict]:
        """
        智能选择 JS 批量提取（当页面元素数量较大或需要很多条时）或回退到 locator 方式。
        """
        try:
            # 快速获取 items 长度（在页面端）
            cnt = 0
            try:
                cnt = page.evaluate('()=> document.querySelectorAll(\'[data-e2e="comment-item"], [data-e2e="comment-level-1"], [data-e2e="comment-level-2"], div[class*="CommentItem"]\').length')
            except:
                cnt = 0
            # 如果页面 comment 元素很多或目标上限较高，优先用 JS 批量提取
            if (cnt and cnt >= 60) or (self.max_comments and self.max_comments >= 80):
                try:
                    res = self.extract_all_comments_via_js(page)
                    if res and isinstance(res, list):
                        return res[: self.max_comments]
                except Exception:
                    # JS 提取失败则落回 locator 版
                    pass
            # 否则使用稳健的 locator 版
            return self.extract_all_comments_globally(page)
        except Exception:
            # 最后兜底返回空
            return []

    # ---------- 保存 ----------
    def save_comments(self, comments: List[Dict], video_id: str, outdir=".", video_stats: Optional[Dict] = None):
        if comments is None:
            comments = []
        os.makedirs(os.path.join(outdir, "tiktok_comments"), exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        mode_tag = "_mainonly" if self.main_only else "_hybrid"
        base_filename = f"tiktok_comments_{video_id}{mode_tag}_{timestamp}"

        if len(comments) > self.max_comments:
            comments = comments[: self.max_comments]
            print(f"ℹ️ 结果已按上限 {self.max_comments} 条截断")

        # 保存 CSV / JSON / TXT（即使为空也生成文件以便 pipeline 后续处理）
        df = pd.DataFrame(comments)
        csv_path = os.path.join(outdir, "tiktok_comments", f"{base_filename}.csv")
        df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        print(f"💾 CSV文件已保存: {csv_path}")

        json_path = os.path.join(outdir, "tiktok_comments", f"{base_filename}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(comments, f, ensure_ascii=False, indent=2)
        print(f"💾 JSON文件已保存: {json_path}")

        high_value_comments = [c for c in comments if c.get('is_high_value', False)]
        if high_value_comments:
            high_value_csv_path = os.path.join(outdir, "tiktok_comments", f"{base_filename}_high_value.csv")
            pd.DataFrame(high_value_comments).to_csv(high_value_csv_path, index=False, encoding='utf-8-sig')
            print(f"💾 高价值评论CSV已保存: {high_value_csv_path}")

        txt_path = os.path.join(outdir, "tiktok_comments", f"{base_filename}.txt")
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(f"TikTok视频评论数据 - {video_id}\n")
            f.write("=" * 50 + "\n\n")
            if video_stats:
                likes = video_stats.get('likes'); cmts = video_stats.get('comments'); shares = video_stats.get('shares')
                f.write(f"视频点赞: {likes if likes is not None else '未知'}\n")
                f.write(f"视频评论: {cmts if cmts is not None else '未知'} | 视频分享: {shares if shares is not None else '未知'}\n\n")
            main_comments = [c for c in comments if c.get('level') == 1]

            for main_comment in main_comments:
                f.write(f"【{main_comment['index']}】{main_comment['username']} ({main_comment['time']})\n")
                f.write(f"点赞: {main_comment['likes']} | 回复数: {main_comment['reply_count']}\n")
                f.write(f"内容: {main_comment['content']}\n")
                if main_comment.get('is_high_value'):
                    f.write("⭐ 高价值评论\n")
                f.write("-" * 30 + "\n")

        print(f"💾 TXT文件已保存: {txt_path}")
        print(f"\n📊 评论统计: 总 {len(comments)}，主评 {len([c for c in comments if c['level']==1])}，回复 {len([c for c in comments if c['level']==2])}，高价值 {len(high_value_comments)}")

    # ---------- 收敛判断 ----------
    def enhanced_stagnation_detection(self, cur_main, cur_total, last_main, last_total, main_stable, total_stable, round_idx, page):
        if cur_main == last_main: main_stable += 1
        else: main_stable = 0
        if cur_total == last_total: total_stable += 1
        else: total_stable = 0
        return main_stable, total_stable

    # ---------- 主流程：单视频 ----------
    def scrape_comments(self, url: str) -> Tuple[List[Dict], Dict]:
        port = 9222
        if not self.start_edge_with_debug_port(port):
            return [], {}
        if not self.wait_for_debug_ready(port):
            print("❌ 调试端口等待超时")
            return [], {}

        try:
            if not self.connect_to_running_edge(port):
                print("❌ 无法连接到浏览器")
                return [], {}

            ctx = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.set_default_timeout(60000)
            page.set_default_navigation_timeout(60000)

            try:
                ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
            except:
                pass

            nav_ok = self.force_navigate(page, url)
            if isinstance(nav_ok, object) and hasattr(nav_ok, "url"):
                page = nav_ok
            elif not nav_ok:
                print(f"❌ 无法跳转到视频页，当前URL: {page.url}")
                return [], {}

            # 可选：设置 UA/Referer（更稳）
            try:
                # Page 没有 set_user_agent；如需设置，应在 context 创建时设置，这里略过
                pass
            except Exception:
                pass
            try:
                page.set_extra_http_headers({"Referer": "https://www.tiktok.com/"})
            except Exception:
                pass

            # 进入后立刻稳住并打开评论抽屉（关键）
            self._stabilize_video_page(page, url)
            self._open_comments_drawer(page)

            print(f"✅ 当前页面: {page.url}")

            mode_msg = f"🧩 模式：{'MainOnly（只抓主评）' if self.main_only else 'Hybrid（先主评，不足再抓楼中楼）'}；上限 {self.max_comments} 条"
            print(mode_msg)

            video_stats = self.get_video_stats(page)
            print(
                f"🎯 视频数据：点赞 {video_stats.get('likes') if video_stats.get('likes') is not None else '未知'} | 评论 {video_stats.get('comments') if video_stats.get('comments') is not None else '未知'} | 分享 {video_stats.get('shares') if video_stats.get('shares') is not None else '未知'}")

            self.smart_verification_check(page, "初始进入")
            try:
                page.wait_for_selector('[data-e2e="comment-level-1"]', timeout=25000)
            except:
                pass

            target = self.get_target_total(page)
            print(f"🎯 页面显示评论总数: {target if target > 0 else '未知'}")

            if self.main_only:
                self.should_extract_replies = False
                print("ℹ️ 当前为 MainOnly：不会展开楼中楼，只抓主评")
            else:
                self.should_extract_replies = True
                print("ℹ️ 当前为 Hybrid：优先主评，未达上限再展开楼中楼补齐")

            last_main, main_stable = -1, 0
            last_total, total_stable = -1, 0
            tried_final_expand = False
            reached_cap = False

            # 在循环外保留当前已知 total（便于动态调整滚动速度）
            cur_total = 0

            # 若目标很大，可稍微缩短总轮数（避免无意义长时间循环）
            local_max_rounds = MAX_ROUNDS
            if self.max_comments and self.max_comments >= 200:
                local_max_rounds = min(MAX_ROUNDS, 120)

            for round_idx in range(1, local_max_rounds + 1):
                # 先看门狗，防主页跳转
                self._guard_stay_on_video(page, url)

                remaining = max(0, (self.max_comments or 0) - cur_total) if self.max_comments else None
                self.micro_scroll_with_verification_check(page, round_idx, remaining=remaining)
                self.wait_skeleton_quiet(page, 1.4)

                cur_main = self.count_main(page)
                cur_reply = self.count_replies(page) if (not self.main_only) else 0
                cur_total = cur_main + cur_reply
                print(f" 轮 {round_idx} | 主评 {cur_main} | 楼中楼 {cur_reply} | 总 {cur_total}")

                verify_check = self._is_verify_present(page)
                if verify_check.get('has_verification'):
                    print(f"🛑 发现验证拦截（评分 {verify_check.get('score')}）")
                    for r in verify_check.get('reasons', [])[:6]:
                        print(f"   • {r}")
                    print("👉 请在浏览器完成验证后按回车继续...")
                    input()
                    self.last_verification_check = time.time()
                    main_stable = 0
                    total_stable = 0
                    continue

                if cur_total >= self.max_comments:
                    print(f"✅ 已达到抓取上限 {self.max_comments} 条，停止滚动")
                    reached_cap = True
                    break

                main_stable, total_stable = self.enhanced_stagnation_detection(
                    cur_main, cur_total, last_main, last_total, main_stable, total_stable, round_idx, page
                )
                last_main, last_total = cur_main, cur_total

                # 快速模式：如果需要很多条且短时间内无新增则提前结束，以节省时间（随后会做 final expand）
                if (self.max_comments and self.max_comments >= 80) and (total_stable >= FAST_STOP_NO_CHANGE):
                    print(f"⚡ 快速退出：已连续 {total_stable} 轮无新增（目标较大），进入最终展开/收尾")
                    break

                if (not self.main_only) and self.should_extract_replies and (cur_total < self.max_comments) and (
                        main_stable >= MAIN_STABLE_TRIGGER):
                    print("🔍 开始展开楼中楼...")
                    clicked = self.expand_all_replies(page)
                    print(f"🔎 展开完成，本轮累计点击 {clicked} 个")
                    main_stable = 0
                    total_stable = 0
                    try:
                        page.mouse.wheel(0, 800)
                    except:
                        pass
                    self.wait_skeleton_quiet(page, 1.2)
                    cur_main = self.count_main(page)
                    cur_reply = self.count_replies(page)
                    cur_total = cur_main + cur_reply
                    print(f"   ↳ 展开后刷新 | 主评 {cur_main} | 楼中楼 {cur_reply} | 总 {cur_total}")

                if ((target > 0 and cur_total >= int(target * 0.95)) or total_stable >= TOTAL_STABLE_ROUNDS):
                    if (not self.main_only) and self.should_extract_replies and (cur_total < self.max_comments) and (
                    not tried_final_expand):
                        print("🧩 进入最终展开尝试...")
                        clicked = self.expand_all_replies(page)
                        print(f"   ↳ 最终展开点击 {clicked} 个")
                        tried_final_expand = True
                        self.wait_skeleton_quiet(page, 1.2)
                        cur_main = self.count_main(page)
                        cur_reply = self.count_replies(page)
                        cur_total = cur_main + cur_reply
                        print(f"   ↳ 最终展开后 | 主评 {cur_main} | 楼中楼 {cur_reply} | 总 {cur_total}")
                        main_stable = 0
                        total_stable = 0
                        continue
                    print("✅ 达到收敛条件或无需继续，结束滚动")
                    break

            # 循环结束后，仅在“不是因为上限退出”时做一次收尾展开，以尽量补齐回复
            try:
                if (not self.main_only) and self.should_extract_replies and (not reached_cap):
                    print("🔁 循环结束后补齐展开一次楼中楼（收尾）...")
                    self.expand_all_replies(page)
                    self.wait_reply_count_stable(page)
            except:
                pass

            # 最终全局收集（尝试 JS 高速提取，否则回退）
            comments = self.extract_all_comments(page)

            print(
                f"✅ 共获取 {len(comments)} 条（模式：{'MainOnly' if self.main_only else 'Hybrid'}，上限 {self.max_comments}）")
            return comments, video_stats

        except Exception as e:
            print(f"❌ 抓取失败: {e}")
            return [], {}
        finally:
            try:
                if self.playwright:
                    self.playwright.stop()
            except:
                pass

    def wait_reply_count_stable(self, page, checks=3, interval=1.5):
        last = -1
        stable = 0
        for _ in range(20):
            cnt = page.locator('[data-e2e="comment-level-2"]').count()
            if cnt == last:
                stable += 1
                if stable >= checks:
                    break
            else:
                stable = 0
                last = cnt
            time.sleep(interval)

    # 保留一个可调用的“最终收集”接口（使用全局收集+去重）
    def final_collect_with_hierarchy(self, page, upper_limit=None):
        self.wait_reply_count_stable(page)
        comments = self.extract_all_comments_globally(page)
        seen = set()
        deduped = []
        for c in comments:
            key = (c.get('username',''), c.get('content',''), c.get('level',0), c.get('parent_comment'))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(c)
        if upper_limit and len(deduped) > upper_limit:
            mains = [c for c in deduped if c.get('level') == 1]
            replies = [c for c in deduped if c.get('level') == 2]
            keep_main = min(len(mains), upper_limit)
            keep_reply = max(0, upper_limit - keep_main)
            deduped = mains[:keep_main] + replies[:keep_reply]
        return deduped

    def cleanup(self):
        try:
            if self.playwright:
                self.playwright.stop()
        except:
            pass


def main(args=None):
    import argparse, re
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", action="append", help="可多次传入 URL；不传则使用 VIDEO_SOURCES")
    parser.add_argument("--videos-file", help="文本文件（每行一个 URL）")
    parser.add_argument("--outdir", default=".", help="输出根目录（写入 outdir/tiktok_comments/）")
    parser.add_argument("--edge-user-data-dir", help="Edge 用户数据目录；默认自动探测")
    parser.add_argument("--max-comments", type=int, default=MAX_COMMENTS, help=f"最多抓取的评论条数（主评+回复合计，默认：{MAX_COMMENTS}）")
    parser.add_argument("--main-only", action="store_true", help="只抓主评（不抓楼中楼），仍受 --max-comments 限制")
    if args is None:
        args = parser.parse_args()

    sources = []
    if args.video:
        sources.extend(args.video)
    videos_file = getattr(args, "videos_file", None)
    if videos_file:
        with open(videos_file, "r", encoding="utf-8") as f:
            sources.extend([ln.strip() for ln in f if ln.strip()])
    if not sources:
        sources = VIDEO_SOURCES

    uniq, seen = [], set()
    for u in sources:
        if u and u not in seen:
            seen.add(u); uniq.append(u)
    sources = uniq

    print(f"🎯 准备处理 {len(sources)} 个视频链接")
    for i, url in enumerate(sources, 1):
        path = urlparse(url).path
        m = re.search(r"/video/(\d+)", path)
        print(f"  {i}. 视频ID: {m.group(1) if m else '无法解析'}")

    scraper = TikTokCommentScraper(edge_user_data_dir=args.edge_user_data_dir,
                                   max_comments=args.max_comments,
                                   main_only=args.main_only)

    print(f"\n==== 运行配置 ====")
    print(f"🧩 抓取模式：{'MainOnly（只抓主评）' if scraper.main_only else 'Hybrid（先主评，不足再抓楼中楼）'}")
    print(f"📈 条数上限：{scraper.max_comments}")
    print(f"==================\n")

    try:
        for i, url in enumerate(sources, 1):
            path = urlparse(url).path
            m = re.search(r"/video/(\d+)", path)
            if not m:
                print(f"❌ URL无法解析视频ID：{url}")
                continue
            vid = m.group(1)

            print(f"\n{'=' * 60}")
            print(f"🎬 开始处理第 {i}/{len(sources)} 个视频")
            print(f"📹 视频ID: {vid}")
            print(f"🔗 URL: {url}")
            print(f"{'=' * 60}")

            comments, video_stats = scraper.scrape_comments(url)
            if comments:
                print(f"✅ 第 {i} 个视频抓取完成！{vid} 共 {len(comments)} 条评论（不超过上限 {scraper.max_comments}）")
                scraper.save_comments(comments, vid, outdir=args.outdir, video_stats=video_stats)
            else:
                print(f"❌ 第 {i} 个视频抓取失败或无评论：{vid}")
                # 仍然保存空结果文件，方便后续 pipeline
                scraper.save_comments([], vid, outdir=args.outdir, video_stats=video_stats)

            if i < len(sources):
                print(f"\n⏳ 等待 3 秒后处理下一个视频...")
                time.sleep(3)

        print(f"\n✅ 所有 {len(sources)} 个视频处理完成！")

    except KeyboardInterrupt:
        print(f"\n⚠️ 用户中断，已处理 {i - 1}/{len(sources)} 个视频")
    except Exception as e:
        print(f"\n❌ 处理过程中出现错误: {e}")
    finally:
        scraper.cleanup()


if __name__ == "__main__":
    main()
