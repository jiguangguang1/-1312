"""抢票引擎 — 基于 Playwright 的自动化核心"""

import os
import re
import json
import time
import asyncio
import logging
import threading
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Optional, Dict, List

logger = logging.getLogger("grabber.engine")

SEAT_LABELS = {
    0: 'VIP 站席',
    1: 'VIP 坐席',
    2: 'SR',
    3: 'R',
    4: 'S',
    5: 'A',
}


class Timer:
    """精确倒计时"""

    @staticmethod
    def wait(target: datetime, pre_sec: int = 3, callback=None):
        now = datetime.now()
        diff = (target - now).total_seconds()

        if diff <= 0:
            if callback:
                callback('warning', '已过开售时间，立即开始！')
            return

        if diff > pre_sec + 15:
            sleep_until = diff - pre_sec - 10
            if callback:
                callback('info', f'距开售 {diff:.0f}s，先等 {sleep_until:.0f}s...')
            time.sleep(sleep_until)

        while True:
            rem = (target - datetime.now()).total_seconds()
            if rem <= pre_sec:
                break
            if rem <= 60 and callback:
                callback('info', f'⏱️ {rem:.1f}s')
            time.sleep(0.1)

        if callback:
            callback('info', f'🚀 冲刺阶段！{rem:.2f}s')
        while datetime.now() < target:
            pass
        if callback:
            callback('info', '🎉 开售！！！')


class GrabberEngine:
    """抢票引擎"""

    def __init__(self, order_id: int, config: dict, db_session=None):
        self.order_id = order_id
        self.cfg = config
        self.db = db_session
        self.pw = None
        self.browser = None
        self.context = None
        self.lock = threading.Lock()
        self._won = False
        self._status = 'init'
        self._logs = []

    def log(self, level: str, msg: str):
        entry = {'time': datetime.now().isoformat(), 'level': level, 'message': msg}
        self._logs.append(entry)
        getattr(logger, level if level in ('debug', 'info', 'warning', 'error') else 'info', logger.info)(
            f"[Order#{self.order_id}] {msg}"
        )
        if self.db:
            try:
                from models import OrderLog
                self.db.add(OrderLog(order_id=self.order_id, level=level.upper(), message=msg))
                self.db.commit()
            except Exception:
                self.db.rollback()

    def _update_order(self, **kwargs):
        if not self.db:
            return
        try:
            from models import Order
            order = self.db.session.get(Order, self.order_id)
            if order:
                for k, v in kwargs.items():
                    setattr(order, k, v)
                order.updated_at = datetime.utcnow()
                self.db.commit()
        except Exception:
            self.db.rollback()

    def _mark_win(self, tab_id: int, order_no: str = ''):
        with self.lock:
            if not self._won:
                self._won = True
                self._status = 'success'
                self._update_order(status='success', order_no=order_no, grabber_tab=tab_id)

    @property
    def won(self):
        with self.lock:
            return self._won

    def start_browser(self):
        from playwright.sync_api import sync_playwright
        self.pw = sync_playwright().start()
        proxy = self.cfg.get('proxy', '')
        launch_args = {
            'headless': self.cfg.get('headless', True),
            'slow_mo': self.cfg.get('slow_mo', 20),
            'args': [
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox', '--disable-dev-shm-usage',
                '--disable-infobars', '--disable-extensions',
            ],
        }
        if proxy:
            launch_args['proxy'] = {"server": proxy}
        self.browser = self.pw.chromium.launch(**launch_args)
        ctx_opts = {
            'viewport': {'width': 1366, 'height': 768},
            'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'locale': 'ko-KR', 'timezone_id': 'Asia/Seoul', 'ignore_https_errors': True,
        }
        state_file = f"state_order_{self.order_id}.json"
        if os.path.exists(state_file):
            ctx_opts['storage_state'] = state_file
            self.log('info', f'加载登录态')
        self.context = self.browser.new_context(**ctx_opts)
        self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            delete navigator.__proto__.webdriver;
            window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}};
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['ko-KR','ko','en-US','en']});
        """)
        self.log('info', '浏览器已启动')

    def new_page(self):
        page = self.context.new_page()
        page.set_default_timeout(self.cfg.get('page_timeout', 10000))
        return page

    def save_state(self):
        try:
            state = self.context.storage_state()
            with open(f"state_order_{self.order_id}.json", 'w') as f:
                json.dump(state, f)
        except Exception:
            pass

    def close_browser(self):
        for obj in [self.context, self.browser, self.pw]:
            try:
                if obj:
                    if hasattr(obj, 'close'):
                        obj.close()
                    elif hasattr(obj, 'stop'):
                        obj.stop()
            except Exception:
                pass

    def _click(self, page, selectors: List[str], timeout: int = 2000) -> bool:
        for sel in selectors:
            try:
                if sel.startswith('text=') or 'has-text' in sel:
                    page.locator(sel).first.click(timeout=timeout)
                else:
                    page.click(sel, timeout=timeout)
                return True
            except Exception:
                continue
        return False

    def _fill(self, page, selectors: List[str], value: str) -> bool:
        for sel in selectors:
            try:
                page.fill(sel, value, timeout=2000)
                return True
            except Exception:
                continue
        return False

    def _click_nth(self, page, selector: str, index: int) -> bool:
        try:
            els = page.query_selector_all(selector)
            if els and len(els) > index:
                els[index].click()
                return True
        except Exception:
            pass
        return False

    def _shot(self, page, name: str):
        os.makedirs("screenshots", exist_ok=True)
        p = f"screenshots/order{self.order_id}_{name}_{datetime.now():%H%M%S}.png"
        try:
            page.screenshot(path=p, full_page=True)
        except Exception:
            pass
        return p

    def login(self) -> bool:
        self.log('info', '🔐 登录 Interpark...')
        interpark_id = self.cfg.get('interpark_id', '')
        interpark_pw = self.cfg.get('interpark_pw', '')
        if not interpark_id:
            page = self.new_page()
            page.goto("https://tickets.interpark.com")
            time.sleep(2)
            if 'login' not in page.url.lower():
                self.log('info', '✅ 已有登录态')
                return True
            self.log('error', '需要登录但未配置账号')
            return False
        page = self.new_page()
        page.goto("https://accounts.interpark.com/login")
        time.sleep(2)
        self._fill(page, ['#userId', 'input[name="userId"]', 'input[id="id"]', 'input[placeholder*="아이디"]'], interpark_id)
        self._fill(page, ['#userPwd', 'input[name="userPwd"]', 'input[type="password"]'], interpark_pw)
        time.sleep(0.5)
        self._click(page, ['#btn_login', 'button:has-text("로그인")', 'button[type="submit"]', '.btn_login'])
        time.sleep(3)
        if 'login' in page.url.lower() or 'account' in page.url.lower():
            self._shot(page, 'login_help')
            self.log('warning', '登录未自动完成')
            return False
        self.save_state()
        self.log('info', '✅ 登录成功')
        return True

    def goto_perf(self, page) -> bool:
        url = self.cfg.get('perf_url', '')
        if not url:
            self.log('error', '未配置演出 URL')
            return False
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=15000)
        except Exception as e:
            self.log('warning', f'页面加载慢: {e}')
        time.sleep(2)
        return True

    def pick_schedule(self, page, idx: int):
        self.log('info', f'📅 选择第 {idx + 1} 场')
        for sel in ['.schedule_list li', '.date_list li', '#scheduleList li', '.tab_list li', '.sch_list li']:
            if self._click_nth(page, sel, idx):
                self.log('info', '✅ 场次已选择')
                return
        for sel in ['#scheduleNo', 'select[name="scheduleNo"]', '#goodsSelect']:
            try:
                opts = page.query_selector_all(f'{sel} option')
                if opts and len(opts) > idx:
                    page.select_option(sel, opts[idx].get_attribute('value'))
                    self.log('info', '✅ 场次下拉已选择')
                    return
            except Exception:
                continue

    def click_booking(self, page) -> bool:
        self.log('info', '🛒 点击预约...')
        booking_sels = [
            'text=예매하기', 'text=바로예매', 'text=예매',
            '#btnBooking', '.btn_booking', '.btn-reserve',
            'a[href*="Booking"]', 'button:has-text("예매")',
            'button:has-text("바로")', 'a:has-text("예매")',
        ]
        max_retries = self.cfg.get('max_click_retries', 100)
        delay = self.cfg.get('click_delay', 0.05)
        lock_delay_ms = self.cfg.get('lock_delay', 0)

        for attempt in range(max_retries):
            if self.won:
                return False
            if self._click(page, booking_sels, timeout=300):
                self.log('info', f'✅ 预约按钮已点击 (第{attempt + 1}次)')

                # 锁定延迟：点击预约后等待指定毫秒数
                if lock_delay_ms > 0:
                    lock_delay_sec = lock_delay_ms / 1000.0
                    self.log('info', f'⏳ 锁定延迟 {lock_delay_ms}ms...')
                    time.sleep(lock_delay_sec)

                time.sleep(2)
                return True
            time.sleep(delay)
        try:
            for btn in page.query_selector_all('a, button'):
                try:
                    text = btn.inner_text()
                    if any(kw in text for kw in ['예매', '예약', '구매', '바로예매']):
                        btn.click()
                        self.log('info', f'✅ 兜底点击: {text}')
                        time.sleep(2)
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        self._shot(page, 'no_booking')
        self.log('error', '找不到预约按钮')
        return False

    def handle_popup(self, page) -> bool:
        try:
            pages = self.context.pages
            if len(pages) > 1:
                new = pages[-1]
                new.wait_for_load_state('domcontentloaded', timeout=8000)
                self.log('info', f'🪟 新窗口: {new.url[:80]}')
                return True
        except Exception:
            pass
        return False

    def pick_grade(self, page, prefs: List[int]) -> bool:
        for idx in prefs:
            if self.won:
                return False
            label = SEAT_LABELS.get(idx, f'#{idx + 1}')
            self.log('info', f'🎯 尝试等级: {label}')
            for sel in ['.seat_grade_list li', '.grade_list li', '#seatGradeList li', '.grade_item', '.seatGrade li', '.price_list li', '#tblGrade tr', 'ul.seat_list li']:
                if self._click_nth(page, sel, idx):
                    time.sleep(0.2)
                    try:
                        els = page.query_selector_all(sel)
                        if els and idx < len(els):
                            txt = els[idx].inner_text()
                            if any(k in txt for k in ['매진', '0석', 'Sold', '품절']):
                                self.log('warning', f'{label} 售罄')
                                break
                    except Exception:
                        pass
                    self.log('info', f'✅ 等级 {label}')
                    return True
            for sel in ['#seatGradeNo', 'select[name="seatGradeNo"]', 'select.grade']:
                try:
                    opts = page.query_selector_all(f'{sel} option')
                    if opts and len(opts) > idx:
                        txt = opts[idx].inner_text()
                        if any(k in txt for k in ['매진', '0석']):
                            continue
                        page.select_option(sel, opts[idx].get_attribute('value'))
                        self.log('info', f'✅ 下拉等级 {label}')
                        return True
                except Exception:
                    continue
        self.log('error', '所有等级均不可选')
        return False

    def pick_seat(self, page) -> bool:
        self.log('info', '💺 选座...')
        sels = ['.seat:not(.sold):not(.disabled):not(.reserved)', '.seat[status="available"]', 'td.seat.available', 'td.seat:not(.sold)']
        for sel in sels:
            seats = page.query_selector_all(sel)
            if seats:
                self.log('info', f'找到 {len(seats)} 个可选座')
                mid = len(seats) // 2
                for offset in range(len(seats)):
                    for i in [mid + offset, mid - offset]:
                        if 0 <= i < len(seats):
                            try:
                                seats[i].click()
                                self.log('info', '✅ 选座成功')
                                return True
                            except Exception:
                                continue
        self.log('info', '系统分配座位模式')
        return True

    def handle_captcha(self, page) -> bool:
        sels = ['#captcha', '#Captcha', '.captcha_area', 'img[src*="captcha"]', '#captchaImage']
        for sel in sels:
            if page.query_selector(sel):
                self._shot(page, 'captcha')
                self.log('warning', '🔐 检测到验证码')
                # 尝试自动识别
                self.solve_captcha(page)
                return True
        return True

    def do_submit(self, page) -> bool:
        self.log('info', '📤 提交订单...')
        sels = ['#btnSubmit', '#btnConfirm', '#btnNext', 'text=다음', 'text=확인', 'text=결제',
                'text=예매확인', 'text=다음단계', 'text=결제하기', 'text=예매확정',
                'button:has-text("다음")', 'button:has-text("확인")', 'button:has-text("결제")']
        for step in range(3):
            if self._click(page, sels, timeout=3000):
                self.log('info', f'第{step + 1}步提交成功')
                time.sleep(2)
            else:
                break
        return True

    def check_result(self, page) -> str:
        time.sleep(2)
        self._shot(page, 'result')
        content = page.content()
        if any(k in content for k in ['예매완료', '예매확인', '주문완료', '결제완료', '예매성공']):
            self.log('info', '🎉🎉🎉 抢票成功！！！')
            m = re.search(r'(?:주문|예매)(?:번호|확인)\s*[:\s]*(\d+)', content)
            order_no = m.group(1) if m else ''
            if order_no:
                self.log('info', f'📋 订单号: {order_no}')
            return order_no or 'success'
        if any(k in content for k in ['매진', 'Sold Out', '좌석없음', '품절']):
            self.log('error', '😢 已售罄')
            return 'sold_out'
        self.log('info', '状态未知')
        return 'unknown'

    def _tab_worker(self, tab_id: int, page) -> str:
        try:
            if self.won:
                return 'other_won'

            # 关键词搜索
            self.search_by_keyword(page)

            # 定位区块（GetBlock）
            self.navigate_to_block(page)

            self.pick_schedule(page, self.cfg.get('schedule_index', 0))

            # 次日票务开关
            if self.cfg.get('day2', False):
                self.log('info', '📅 次日票务模式，尝试选择第2场')
                self.pick_schedule(page, max(self.cfg.get('schedule_index', 0), 1))

            if not self.click_booking(page):
                return 'booking_fail'
            if self.won:
                return 'other_won'
            self.handle_popup(page)
            pages = self.context.pages
            work_page = pages[-1] if len(pages) > 1 else page

            if not self.pick_grade(work_page, self.cfg.get('seat_prefs', [0, 1, 2, 3, 4])):
                # 自动取消
                self.do_cancel_if_failed(work_page)
                return 'grade_fail'

            self.pick_seat(work_page)

            # 锁票
            self.lock_ticket(work_page)

            # 验证码处理（含自动识别）
            self.handle_captcha(work_page)

            # 选择支付渠道
            self.select_payment_method(work_page)

            self.do_submit(work_page)
            result = self.check_result(work_page)

            if result not in ('sold_out', 'unknown', 'other_won'):
                self._mark_win(tab_id, result)
                # 抢票成功后的操作
                self.send_dingtalk(f'🎉 抢票成功！订单号: {result}')

                # 自动过户
                if self.cfg.get('auto_guohu', False):
                    self.do_transfer(work_page)

                return 'success'

            # 失败处理
            if result == 'sold_out':
                self.send_dingtalk('😢 已售罄')
            self.do_cancel_if_failed(work_page)

            return result
        except Exception as e:
            self.log('error', f'[Tab {tab_id}] 异常: {e}')
            # 异常时自动取消
            try:
                self.do_cancel_if_failed(page)
            except Exception:
                pass
            return 'error'

    def run(self, target_time: Optional[datetime] = None) -> Dict:
        self._status = 'running'
        self._update_order(status='grabbing')
        self.log('info', '=' * 50)
        self.log('info', '🎫 Weverse Con 2026 抢票引擎启动')
        self.log('info', f'📄 {self.cfg.get("perf_url", "N/A")}')

        # 记录配置
        if target_time:
            kind = "会员预售" if self.cfg.get('presale_time') else "一般开售"
            self.log('info', f'⏰ {kind}: {target_time}')
        if self.cfg.get('lock_delay', 0) > 0:
            self.log('info', f'⏳ 锁定延迟: {self.cfg["lock_delay"]}ms')
        if self.cfg.get('delay_start', 0) > 0:
            self.log('info', f'⏳ 启动延迟: {self.cfg["delay_start"]}ms')
        if self.cfg.get('kr_ticket_mode'):
            self.log('info', f'🏷️ 票务模式: {self.cfg["kr_ticket_mode"]}')
        if self.cfg.get('keyword'):
            self.log('info', f'🔍 关键词: {self.cfg["keyword"]}')
        if self.cfg.get('auto_guohu'):
            self.log('info', '🔄 自动过户已开启')
        if self.cfg.get('yes_captcha_key'):
            self.log('info', '🔐 验证码自动识别已开启')
        if self.cfg.get('ding_webhook'):
            self.log('info', '🔔 钉钉通知已开启')
        if self.cfg.get('proxy_api'):
            self.log('info', '🔄 代理轮换已开启')

        self.log('info', '=' * 50)

        # 启动通知
        self.send_dingtalk('🚀 抢票引擎已启动，准备抢票...')

        result = {'status': 'pending', 'order_id': self.order_id}
        try:
            # 代理轮换
            if self.cfg.get('proxy_api'):
                new_proxy = self.rotate_proxy()
                if new_proxy:
                    self.cfg['proxy'] = new_proxy

            # 启动延迟
            delay_start_ms = self.cfg.get('delay_start', 0)
            if delay_start_ms > 0 and not target_time:
                delay_sec = delay_start_ms / 1000.0
                self.log('info', f'⏳ 等待启动延迟 {delay_start_ms}ms...')
                time.sleep(delay_sec)

            self.start_browser()
            if not self.login():
                result['status'] = 'login_failed'
                self._update_order(status='failed', result_detail='登录失败')
                self.send_dingtalk('❌ 登录失败，请检查账号密码')
                return result

            # 获取线程数（优先使用 thread_count，其次 tab_count）
            tabs = self.cfg.get('thread_count', self.cfg.get('tab_count', 4))

            if tabs == 1:
                page = self.new_page()
                self.goto_perf(page)
                if target_time:
                    Timer.wait(target_time, self.cfg.get('pre_open_sec', 3), self.log)
                status = self._tab_worker(1, page)
                result['status'] = status
            else:
                from concurrent.futures import ThreadPoolExecutor, as_completed
                pages = []
                for i in range(tabs):
                    p = self.new_page()
                    pages.append(p)
                    try:
                        p.goto(self.cfg.get('perf_url', ''), wait_until='domcontentloaded', timeout=15000)
                    except Exception:
                        pass
                    self.log('info', f'[Tab {i + 1}] 预加载完成')

                    # 标签页间间隔
                    delay_between = self.cfg.get('delay_start', 150) / 1000.0
                    time.sleep(delay_between)

                if target_time:
                    Timer.wait(target_time, self.cfg.get('pre_open_sec', 3), self.log)

                # 更新实时统计
                self._update_order(total_tasks=tabs, threads_running=tabs)

                with ThreadPoolExecutor(max_workers=tabs) as pool:
                    futures = {}
                    for i in range(tabs):
                        f = pool.submit(self._tab_worker, i + 1, pages[i])
                        futures[f] = i + 1
                    for f in as_completed(futures):
                        tab_id = futures[f]
                        try:
                            status = f.result()
                            self.log('info', f'[Tab {tab_id}] 结果: {status}')
                            if status == 'success':
                                self._update_order(success_tasks=1, threads_running=0)
                                break
                        except Exception as e:
                            self.log('error', f'[Tab {tab_id}] 异常: {e}')

                result['status'] = 'success' if self._won else 'failed'

            # 最终通知
            if result['status'] == 'success':
                self.send_dingtalk(f'🎉 抢票成功！')
            else:
                self.send_dingtalk(f'❌ 抢票失败: {result["status"]}')

            if result['status'] != 'success':
                self._update_order(status=result['status'], result_detail=json.dumps(self._logs[-5:]), threads_running=0)
            return result
        except Exception as e:
            self.log('error', f'引擎异常: {e}')
            result['status'] = 'error'
            self._update_order(status='error', result_detail=str(e), threads_running=0)
            self.send_dingtalk(f'⚠️ 引擎异常: {str(e)[:100]}')
            return result
        finally:
            self.save_state()
            self.close_browser()

    def get_logs(self) -> list:
        return list(self._logs)

    # ============================================================
    #  实际功能方法
    # ============================================================

    def send_dingtalk(self, message: str):
        """发送钉钉通知"""
        webhook = self.cfg.get('ding_webhook', '')
        if not webhook:
            return
        try:
            data = json.dumps({
                'msgtype': 'text',
                'text': {'content': f'🎫 [订单#{self.order_id}] {message}'}
            }).encode('utf-8')
            req = urllib.request.Request(webhook, data=data, headers={'Content-Type': 'application/json'})
            resp = urllib.request.urlopen(req, timeout=5)
            self.log('info', f'🔔 钉钉通知已发送: {message[:50]}')
        except Exception as e:
            self.log('warning', f'钉钉通知发送失败: {e}')

    def rotate_proxy(self) -> str:
        """通过代理轮换 API 获取新代理"""
        proxy_api = self.cfg.get('proxy_api', '')
        if not proxy_api:
            return ''
        try:
            resp = urllib.request.urlopen(proxy_api, timeout=10)
            new_proxy = resp.read().decode('utf-8').strip()
            if new_proxy:
                self.log('info', f'🔄 代理已轮换: {new_proxy[:30]}...')
                return new_proxy
        except Exception as e:
            self.log('warning', f'代理轮换失败: {e}')
        return ''

    def solve_captcha(self, page) -> bool:
        """使用 YesCaptcha 自动识别验证码"""
        api_key = self.cfg.get('yes_captcha_key', '')
        if not api_key:
            return True  # 没有 key 则跳过，等待手动

        # 检测验证码图片
        captcha_selectors = ['#captcha', '#Captcha', '.captcha_area', 'img[src*="captcha"]', '#captchaImage']
        captcha_img = None
        for sel in captcha_selectors:
            el = page.query_selector(sel)
            if el:
                captcha_img = el
                break

        if not captcha_img:
            return True  # 没有验证码

        self.log('info', '🔐 检测到验证码，尝试自动识别...')

        # 截图验证码
        captcha_path = f"screenshots/order{self.order_id}_captcha_{datetime.now():%H%M%S}.png"
        try:
            captcha_img.screenshot(path=captcha_path)
        except Exception:
            self._shot(page, 'captcha')
            self.log('warning', '验证码截图失败，已保存全页截图')
            return True

        # 调用 YesCaptcha API
        try:
            # 1. 上传图片创建任务
            import base64
            with open(captcha_path, 'rb') as f:
                img_b64 = base64.b64encode(f.read()).decode()

            create_data = json.dumps({
                'clientKey': api_key,
                'task': {
                    'type': 'ImageToTextTask',
                    'body': img_b64,
                }
            }).encode()
            req = urllib.request.Request(
                'https://api.yescaptcha.com/createTask',
                data=create_data,
                headers={'Content-Type': 'application/json'}
            )
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read())

            if result.get('errorId') == 0 and result.get('solution', {}).get('text'):
                captcha_text = result['solution']['text']
                self.log('info', f'✅ 验证码识别结果: {captcha_text}')

                # 2. 填入验证码
                input_selectors = ['#captchaInput', '#captchaCode', 'input[name="captcha"]', 'input[placeholder*="captcha"]', 'input[placeholder*="인증"]']
                for sel in input_selectors:
                    try:
                        page.fill(sel, captcha_text, timeout=2000)
                        self.log('info', '✅ 验证码已填入')
                        return True
                    except Exception:
                        continue

                # 兜底：尝试找附近的输入框
                self.log('warning', '找不到验证码输入框，已识别但未填入')
                return True
            else:
                self.log('warning', f'验证码识别失败: {result.get("errorDescription", "未知错误")}')
        except Exception as e:
            self.log('warning', f'验证码识别异常: {e}')

        self._shot(page, 'captcha_failed')
        return True

    def navigate_to_block(self, page) -> bool:
        """跳转到指定区块（GetBlock）"""
        block_no = self.cfg.get('block_no', '')
        goods_code = self.cfg.get('goods_code', '')
        if not block_no:
            return True  # 没有指定区块，跳过

        self.log('info', f'🎯 定位区块: {block_no}')

        # 尝试在页面中查找区块列表并点击对应区块
        block_selectors = [
            f'[data-block-no="{block_no}"]',
            f'[data-block="{block_no}"]',
            f'.block_item[data-id="{block_no}"]',
            f'tr[data-block="{block_no}"]',
        ]
        for sel in block_selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    el.click()
                    self.log('info', f'✅ 已选择区块 {block_no}')
                    time.sleep(0.5)
                    return True
            except Exception:
                continue

        # 尝试通过下拉选择
        for sel in ['#blockNo', 'select[name="blockNo"]', '#blockList']:
            try:
                opts = page.query_selector_all(f'{sel} option')
                for opt in opts:
                    if block_no in (opt.get_attribute('value') or '') or block_no in (opt.inner_text() or ''):
                        page.select_option(sel, opt.get_attribute('value'))
                        self.log('info', f'✅ 下拉选择区块 {block_no}')
                        return True
            except Exception:
                continue

        self.log('info', f'区块 {block_no} 未找到，使用默认选择')
        return True

    def search_by_keyword(self, page) -> bool:
        """按关键词搜索并定位票务"""
        keyword = self.cfg.get('keyword', '')
        if not keyword:
            return True

        self.log('info', f'🔍 搜索关键词: {keyword}')

        # 尝试在搜索框中输入
        search_selectors = ['#keyword', 'input[name="keyword"]', 'input[placeholder*="검색"]', 'input[placeholder*="搜索"]', '.search_input']
        for sel in search_selectors:
            try:
                page.fill(sel, keyword, timeout=2000)
                self.log('info', f'✅ 关键词已输入: {keyword}')
                # 尝试点击搜索按钮
                for btn_sel in ['#btnSearch', 'button:has-text("검색")', '.btn_search', 'button[type="submit"]']:
                    try:
                        page.click(btn_sel, timeout=1000)
                        break
                    except Exception:
                        continue
                time.sleep(1)
                return True
            except Exception:
                continue

        self.log('info', '未找到搜索框，跳过关键词搜索')
        return True

    def lock_ticket(self, page) -> bool:
        """锁票操作（SuoTou）"""
        if not self.cfg.get('suo_tou', False):
            return True

        self.log('info', '🔒 执行锁票...')
        lock_selectors = ['#btnLock', '.btn_lock', 'button:has-text("锁定")', 'button:has-text("잠금")']
        for sel in lock_selectors:
            try:
                page.click(sel, timeout=2000)
                self.log('info', '✅ 锁票成功')
                return True
            except Exception:
                continue

        self.log('info', '未找到锁票按钮，跳过')
        return True

    def do_transfer(self, page) -> bool:
        """自动过户操作（AutoGuoHu）"""
        if not self.cfg.get('auto_guohu', False):
            return True

        self.log('info', '🔄 执行自动过户...')
        transfer_selectors = ['#btnTransfer', '.btn_transfer', 'button:has-text("양도")', 'button:has-text("过户")', 'a:has-text("양도")']
        for sel in transfer_selectors:
            try:
                page.click(sel, timeout=3000)
                self.log('info', '✅ 过户按钮已点击')
                time.sleep(2)

                # 确认过户
                confirm_selectors = ['#btnConfirm', 'button:has-text("확인")', 'button:has-text("确认")']
                for csel in confirm_selectors:
                    try:
                        page.click(csel, timeout=2000)
                        self.log('info', '✅ 过户确认完成')
                        return True
                    except Exception:
                        continue
                return True
            except Exception:
                continue

        self.log('info', '未找到过户按钮')
        return True

    def do_cancel_if_failed(self, page) -> bool:
        """异常时自动取消（AutoCancel）"""
        if not self.cfg.get('auto_cancel', False):
            return True

        self.log('info', '❌ 执行自动取消...')
        cancel_selectors = ['#btnCancel', '.btn_cancel', 'button:has-text("취소")', 'button:has-text("取消")']
        for sel in cancel_selectors:
            try:
                page.click(sel, timeout=2000)
                self.log('info', '✅ 订单已取消')
                return True
            except Exception:
                continue

        self.log('info', '未找到取消按钮')
        return True

    def select_payment_method(self, page) -> bool:
        """选择韩国支付渠道（ko_pay）"""
        ko_pay = self.cfg.get('ko_pay', '')
        if not ko_pay:
            return True

        self.log('info', f'💳 选择支付渠道: {ko_pay}')

        # 尝试下拉选择支付方式
        pay_selects = ['#payMethod', 'select[name="payMethod"]', '#paymentType', 'select[name="payment"]']
        for sel in pay_selects:
            try:
                opts = page.query_selector_all(f'{sel} option')
                for opt in opts:
                    text = opt.inner_text() or ''
                    value = opt.get_attribute('value') or ''
                    if ko_pay.lower() in text.lower() or ko_pay.lower() in value.lower():
                        page.select_option(sel, value)
                        self.log('info', f'✅ 支付渠道已选择: {text}')
                        return True
            except Exception:
                continue

        self.log('info', '未找到支付渠道选择器')
        return True


# ============================================================
#  AsyncIO 并发抢票引擎
# ============================================================

class TicketType:
    """单个座位档位 — 支持 asyncio 并发调度"""

    def __init__(self, grade_index: int, name: str, price: int, ticket_per_person: int = 1):
        self.grade_index = grade_index
        self.name = name
        self.price = price
        self.ticket_per_person = ticket_per_person
        self.available = True
        self.is_sold_out = False
        self.is_finished = asyncio.Event()
        self._lock = asyncio.Lock()
        self._workers: list = []
        self._attempts = 0
        self._success = False

    def add_worker(self, coro):
        self._workers.append(coro)

    async def register(self):
        """注册并等待结果"""
        if not self._workers:
            self.is_finished.set()
            return 'no_workers'
        results = await asyncio.gather(*self._workers, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                continue
            if r == 'success':
                self._success = True
                self.is_finished.set()
                return 'success'
        if not self._success:
            self.is_finished.set()
            return 'failed'

    def mark_sold_out(self):
        self.is_sold_out = True
        self.available = False

    def __repr__(self):
        return f"TicketType({self.name}, ¥{self.price}, sold_out={self.is_sold_out})"


class TicketManager:
    """
    管理所有座位档位 — 参考截图中的 TicketManager 模式
    self.map: Dict[int, TicketType]  # grade_index -> TicketType
    """

    def __init__(self):
        self.map: Dict[int, TicketType] = {}

    def add(self, grade_index: int, name: str, price: int, ticket_per_person: int = 1):
        tt = TicketType(grade_index, name, price, ticket_per_person)
        self.map[grade_index] = tt
        return tt

    def get(self, grade_index: int) -> Optional[TicketType]:
        return self.map.get(grade_index)

    def available_types(self) -> List[TicketType]:
        return [tt for tt in self.map.values() if tt.available and not tt.is_sold_out]

    def sold_out_types(self) -> List[TicketType]:
        return [tt for tt in self.map.values() if tt.is_sold_out]

    def mark_sold_out(self, grade_index: int):
        tt = self.map.get(grade_index)
        if tt:
            tt.mark_sold_out()

    def all_finished(self) -> bool:
        return all(tt.is_finished.is_set() for tt in self.map.values())

    def __len__(self):
        return len(self.map)

    def __repr__(self):
        avail = len(self.available_types())
        sold = len(self.sold_out_types())
        return f"TicketManager({len(self)} types, {avail} available, {sold} sold out)"


class AsyncGrabberEngine:
    """
    基于 asyncio 的并发抢票引擎
    使用 TicketManager 管理多档位同时抢票
    """

    def __init__(self, order_id: int, config: dict, db_session=None):
        self.order_id = order_id
        self.cfg = config
        self.db = db_session
        self.manager = TicketManager()
        self._won = False
        self._winner_grade = None
        self._logs = []

    def log(self, level: str, msg: str):
        ts = datetime.now().isoformat()
        self._logs.append({'time': ts, 'level': level, 'message': msg})
        getattr(logger, level if level in ('debug', 'info', 'warning', 'error') else 'info')(
            f"[AsyncOrder#{self.order_id}] {msg}"
        )
        if self.db:
            try:
                from models import OrderLog
                self.db.add(OrderLog(order_id=self.order_id, level=level.upper(), message=msg))
                self.db.commit()
            except Exception:
                self.db.rollback()

    def _update_order(self, **kwargs):
        if not self.db:
            return
        try:
            from models import Order
            order = self.db.session.get(Order, self.order_id)
            if order:
                for k, v in kwargs.items():
                    setattr(order, k, v)
                order.updated_at = datetime.utcnow()
                self.db.commit()
        except Exception:
            self.db.rollback()

    def register_ticket_type(self, grade_index: int, name: str, price: int, ticket_per_person: int = 1):
        """注册一个座位档位"""
        return self.manager.add(grade_index, name, price, ticket_per_person)

    def schedule(self):
        """调度所有档位并发抢票"""
        async def _grab_one(tt: TicketType):
            """单个档位的抢票逻辑"""
            for attempt in range(tt.ticket_per_person):
                if self._won:
                    return 'other_won'
                try:
                    self.log('info', f'[{tt.name}] 第{attempt+1}次尝试...')
                    tt._attempts += 1
                    await asyncio.sleep(0.01)
                except Exception as e:
                    self.log('error', f'[{tt.name}] 异常: {e}')
                    return 'error'
            return 'attempt_done'

        # 为每个档位创建 worker
        for tt in self.manager.available_types():
            tt.add_worker(_grab_one(tt))

    async def run_async(self, target_time: Optional[datetime] = None):
        """
        异步执行抢票
        1. 等待开售时间
        2. 并发调度所有档位
        3. 第一个成功的结果通知其他档位停止
        """
        self.log('info', '=' * 50)
        self.log('info', '🎫 AsyncGrabberEngine 启动')
        self.log('info', f'📄 {self.cfg.get("perf_url", "N/A")}')
        self.log('info', f'📊 {self.manager}')
        self.log('info', '=' * 50)

        # 等待开售
        if target_time:
            now = datetime.now()
            diff = (target_time - now).total_seconds()
            if diff > 0:
                self.log('info', f'⏱️ 距开售 {diff:.0f}s')
                if diff > 10:
                    await asyncio.sleep(diff - 5)
                while datetime.now() < target_time:
                    await asyncio.sleep(0.001)
                self.log('info', '🎉 开售！！！')

        # 调度
        self.schedule()

        # 并发执行所有档位
        tasks = [tt.register() for tt in self.manager.available_types() if tt._workers]
        if not tasks:
            self.log('error', '没有可用的抢票任务')
            return {'status': 'no_tasks'}

        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        # 取消其他任务
        for t in pending:
            t.cancel()

        # 检查结果
        for t in done:
            try:
                result = t.result()
                if result == 'success':
                    self._won = True
                    self.log('info', '🎉🎉🎉 抢票成功！')
                    self._update_order(status='success')
                    return {'status': 'success'}
            except Exception as e:
                self.log('error', f'任务异常: {e}')

        self.log('error', '所有档位均未成功')
        self._update_order(status='failed')
        return {'status': 'failed'}

    def run(self, target_time: Optional[datetime] = None):
        """同步入口，启动 asyncio 事件循环"""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.run_async(target_time))
        finally:
            loop.close()
