"""抢票引擎 — 基于 Playwright 的自动化核心"""

import os
import re
import json
import time
import asyncio
import logging
import threading
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
        for attempt in range(max_retries):
            if self.won:
                return False
            if self._click(page, booking_sels, timeout=300):
                self.log('info', f'✅ 预约按钮已点击 (第{attempt + 1}次)')
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
                self.log('warning', '🔐 需要验证码，已截图')
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
            self.pick_schedule(page, self.cfg.get('schedule_index', 0))
            if not self.click_booking(page):
                return 'booking_fail'
            if self.won:
                return 'other_won'
            self.handle_popup(page)
            pages = self.context.pages
            work_page = pages[-1] if len(pages) > 1 else page
            if not self.pick_grade(work_page, self.cfg.get('seat_prefs', [0, 1, 2, 3, 4])):
                return 'grade_fail'
            self.pick_seat(work_page)
            self.handle_captcha(work_page)
            self.do_submit(work_page)
            result = self.check_result(work_page)
            if result not in ('sold_out', 'unknown', 'other_won'):
                self._mark_win(tab_id, result)
                return 'success'
            return result
        except Exception as e:
            self.log('error', f'[Tab {tab_id}] 异常: {e}')
            return 'error'

    def run(self, target_time: Optional[datetime] = None) -> Dict:
        self._status = 'running'
        self._update_order(status='grabbing')
        self.log('info', '=' * 50)
        self.log('info', '🎫 Weverse Con 2026 抢票引擎启动')
        self.log('info', f'📄 {self.cfg.get("perf_url", "N/A")}')
        if target_time:
            kind = "会员预售" if self.cfg.get('presale_time') else "一般开售"
            self.log('info', f'⏰ {kind}: {target_time}')
        self.log('info', '=' * 50)
        result = {'status': 'pending', 'order_id': self.order_id}
        try:
            self.start_browser()
            if not self.login():
                result['status'] = 'login_failed'
                self._update_order(status='failed', result_detail='登录失败')
                return result
            tabs = self.cfg.get('tab_count', 4)
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
                    time.sleep(0.15)
                if target_time:
                    Timer.wait(target_time, self.cfg.get('pre_open_sec', 3), self.log)
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
                                break
                        except Exception as e:
                            self.log('error', f'[Tab {tab_id}] 异常: {e}')
                result['status'] = 'success' if self._won else 'failed'
            if result['status'] != 'success':
                self._update_order(status=result['status'], result_detail=json.dumps(self._logs[-5:]))
            return result
        except Exception as e:
            self.log('error', f'引擎异常: {e}')
            result['status'] = 'error'
            self._update_order(status='error', result_detail=str(e))
            return result
        finally:
            self.save_state()
            self.close_browser()

    def get_logs(self) -> list:
        return list(self._logs)


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
