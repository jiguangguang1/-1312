"""
NOL 抢票核心模块 — v3
支持: 多账号、代理轮换、反检测、智能重试
"""

import json
import time
import random
import logging
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

BASE = Path(__file__).parent
log = logging.getLogger('nol.core')

API_BASE = 'https://world.nol.com/api'

USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
]


class Status(Enum):
    IDLE = 'idle'
    WAITING = 'waiting'
    GRABBING = 'grabbing'
    SUCCESS = 'success'
    FAILED = 'failed'
    ERROR = 'error'


@dataclass
class GrabResult:
    success: bool = False
    date: str = ''
    grade: int = -1
    order_no: str = ''
    endpoint: str = ''
    response: str = ''
    attempts: int = 0
    elapsed: float = 0.0
    timestamp: str = ''


@dataclass
class Stats:
    total_attempts: int = 0
    success_count: int = 0
    fail_count: int = 0
    error_count: int = 0
    avg_latency_ms: float = 0.0
    min_latency_ms: float = 9999.0
    max_latency_ms: float = 0.0
    start_time: str = ''
    last_attempt: str = ''
    last_success: str = ''
    _latencies: list = field(default_factory=list)

    def record(self, latency_ms: float, success: bool = False):
        self.total_attempts += 1
        self.last_attempt = datetime.now().isoformat()
        self._latencies.append(latency_ms)
        if len(self._latencies) > 1000:
            self._latencies = self._latencies[-500:]
        self.avg_latency_ms = sum(self._latencies) / len(self._latencies)
        self.min_latency_ms = min(self.min_latency_ms, latency_ms)
        self.max_latency_ms = max(self.max_latency_ms, latency_ms)
        if success:
            self.success_count += 1
            self.last_success = self.last_attempt
        else:
            self.fail_count += 1

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() not in ['_latencies']}


# ============================================================
#  通知器
# ============================================================

class Notifier:
    def __init__(self, config: dict):
        self.cfg = config.get('notifications', {})

    def send(self, msg: str):
        log.info(f'📢 {msg}')
        self._dingtalk(msg)
        self._wxwork(msg)
        self._telegram(msg)

    def _dingtalk(self, msg):
        wh = self.cfg.get('ding_webhook', '')
        if not wh: return
        try:
            requests.post(wh, json={
                'msgtype': 'text',
                'text': {'content': f'🎫 {msg}'}
            }, timeout=5)
        except: pass

    def _wxwork(self, msg):
        wh = self.cfg.get('wx_webhook', '')
        if not wh: return
        try:
            requests.post(wh, json={
                'msgtype': 'text',
                'text': {'content': f'🎫 {msg}'}
            }, timeout=5)
        except: pass

    def _telegram(self, msg):
        token = self.cfg.get('telegram_bot_token', '')
        chat_id = self.cfg.get('telegram_chat_id', '')
        if not token or not chat_id: return
        try:
            requests.post(
                f'https://api.telegram.org/bot{token}/sendMessage',
                json={'chat_id': chat_id, 'text': f'🎫 {msg}'},
                timeout=5
            )
        except: pass


# ============================================================
#  代理管理
# ============================================================

class ProxyManager:
    def __init__(self, config: dict):
        self.enabled = config.get('proxy_rotation', False)
        self.proxies: List[str] = list(config.get('proxy_list', []))
        self.api_url = config.get('proxy_api', '')
        self._idx = 0
        self._lock = threading.Lock()

    def get(self) -> str:
        if not self.enabled:
            return ''
        with self._lock:
            if self.api_url:
                try:
                    r = requests.get(self.api_url, timeout=5)
                    return r.text.strip()
                except:
                    pass
            if self.proxies:
                p = self.proxies[self._idx % len(self.proxies)]
                self._idx += 1
                return p
        return ''

    def rotate(self) -> str:
        return self.get()


# ============================================================
#  NOL API 客户端
# ============================================================

class NOLAccount:
    """单个 NOL 账号"""

    def __init__(self, token_data: dict, label: str = ''):
        self.label = label or token_data.get('label', 'unknown')
        self.tokens = token_data
        self.s = requests.Session()
        self._update_headers()
        self._enter_cache = None
        self._last_refresh = 0

    def _update_headers(self):
        ua = random.choice(USER_AGENTS) if True else USER_AGENTS[0]
        self.s.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': ua,
            'Origin': 'https://world.nol.com',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Authorization': f'Bearer {self.tokens.get("access_token", "")}',
        })

    def set_referer(self, goods_code: str, place_code: str):
        self.s.headers['Referer'] = (
            f'https://world.nol.com/zh-CN/ticket/places/{place_code}/products/{goods_code}'
        )

    def set_proxy(self, proxy: str):
        if proxy:
            self.s.proxies = {'https': proxy, 'http': proxy}

    @property
    def is_valid(self) -> bool:
        return bool(self.tokens.get('access_token'))

    def refresh_token(self) -> bool:
        rt = self.tokens.get('refresh_token', '')
        if not rt:
            return False
        try:
            r = self.s.post(f'{API_BASE}/auth/refresh', json={'refreshToken': rt}, timeout=10)
            if r.status_code == 200:
                new = r.json().get('accessToken', '')
                if new:
                    self.tokens['access_token'] = new
                    self.s.headers['Authorization'] = f'Bearer {new}'
                    self._last_refresh = time.time()
                    return True
        except:
            pass
        return False

    def user_info(self) -> dict:
        r = self.s.get(f'{API_BASE}/users', timeout=10)
        r.raise_for_status()
        return r.json()

    def enter_info(self, goods_code: str, place_code: str) -> dict:
        r = self.s.get(f'{API_BASE}/users/enter', params={
            'goods_code': goods_code, 'place_code': place_code,
        }, timeout=10)
        r.raise_for_status()
        data = r.json()
        self._enter_cache = data
        return data


class NOLGrabber:
    """抢票引擎 — 多账号并发"""

    def __init__(self, config: dict, accounts: List[NOLAccount]):
        self.cfg = config
        self.accounts = [a for a in accounts if a.is_valid]
        self.notifier = Notifier(config)
        self.proxy_mgr = ProxyManager(config)
        self.stats = Stats()
        self.status = Status.IDLE
        self.result: Optional[GrabResult] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._callbacks = []

    def on_event(self, callback):
        """注册事件回调 (用于 WebSocket 推送)"""
        self._callbacks.append(callback)

    def _emit(self, event: str, data: dict):
        for cb in self._callbacks:
            try:
                cb(event, data)
            except:
                pass

    def stop(self):
        self._stop.set()

    @property
    def stopped(self):
        return self._stop.is_set()

    # ── 售卖信息 ──

    def get_sales_info(self) -> dict:
        account = self.accounts[0] if self.accounts else None
        if not account:
            raise ValueError('没有可用账号')
        account.set_referer(self.cfg['goods_code'], self.cfg['place_code'])
        r = account.s.get(f'{API_BASE}/ent-channel-out/v1/goods/salesinfo', params={
            'goodsCode': self.cfg['goods_code'],
            'placeCode': self.cfg['place_code'],
            'bizCode': self.cfg.get('biz_code', '10965'),
        }, timeout=10)
        r.raise_for_status()
        return r.json()['data']

    # ── 时间 ──

    def parse_time(self, time_str: str) -> datetime:
        from zoneinfo import ZoneInfo
        tz = self.cfg.get('sale_tz', 'Asia/Seoul')
        return datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=ZoneInfo(tz))

    def now(self) -> datetime:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(self.cfg.get('sale_tz', 'Asia/Seoul')))

    # ── 抢单个 ──

    def _try_book(self, account: NOLAccount, play_date: str, grade_idx: int) -> dict:
        """单次下单尝试"""
        enter = account._enter_cache or {}
        ad = self.cfg.get('anti_detect', {})

        # 反检测: 随机延迟
        if ad.get('random_delay', True):
            dr = ad.get('delay_range', [0.01, 0.08])
            time.sleep(random.uniform(dr[0], dr[1]))

        payload = {
            'goodsCode': self.cfg['goods_code'],
            'placeCode': self.cfg['place_code'],
            'bizCode': self.cfg.get('biz_code', '10965'),
            'playDate': play_date,
            'gradeIndex': grade_idx,
            'ticketCount': self.cfg.get('ticket_count', 1),
            'memberId': enter.get('enterMemberId', ''),
            'memberNo': enter.get('enterMemberNo', ''),
            'encryptVal': enter.get('enterEncryptVal', ''),
            'languageType': 'CN',
        }

        endpoints = [
            '/biz/enter/booking',
            '/ent-channel-out/v1/booking/create',
            '/ent-channel-out/v1/booking/reserve',
            '/booking/create',
        ]

        for ep in endpoints:
            t0 = time.monotonic()
            try:
                r = account.s.post(f'{API_BASE}{ep}', json=payload, timeout=10)
                latency = (time.monotonic() - t0) * 1000
                self.stats.record(latency, r.status_code == 200)

                if r.status_code == 200:
                    return {'status': 200, 'endpoint': ep, 'body': r.text[:2000], 'latency_ms': latency}
                elif r.status_code not in (404, 405):
                    return {'status': r.status_code, 'endpoint': ep, 'body': r.text[:500], 'latency_ms': latency}
            except requests.exceptions.Timeout:
                latency = (time.monotonic() - t0) * 1000
                self.stats.record(latency)
                continue
            except Exception as e:
                latency = (time.monotonic() - t0) * 1000
                self.stats.record(latency)
                self.stats.error_count += 1
                log.debug(f'{ep}: {e}')
                continue

        return {'status': 'all_failed'}

    # ── 抢票主循环 ──

    def grab(self) -> GrabResult:
        """执行抢票"""
        self.status = Status.GRABBING
        self.stats.start_time = datetime.now().isoformat()
        self._stop.clear()

        dates = self.cfg.get('play_dates', ['2026-06-12', '2026-06-13'])
        prefer_dates = self.cfg.get('prefer_dates', [0, 1])
        prefer_grades = self.cfg.get('prefer_grades', [0, 1, 2, 3])
        max_retries = self.cfg.get('max_retries', 500)
        base_delay = self.cfg.get('retry_delay', 0.03)
        backoff = self.cfg.get('retry_backoff', True)

        t_start = time.monotonic()

        for attempt in range(1, max_retries + 1):
            if self.stopped:
                break

            # 智能重试: 递增延迟
            if backoff and attempt > 50:
                delay = min(base_delay * (1 + attempt * 0.001), 0.2)
            else:
                delay = base_delay

            # 多账号轮换
            account = self.accounts[attempt % len(self.accounts)]
            account.set_referer(self.cfg['goods_code'], self.cfg['place_code'])

            # 代理轮换 (每10次)
            if attempt % 10 == 0:
                proxy = self.proxy_mgr.rotate()
                if proxy:
                    account.set_proxy(proxy)

            for date_idx in prefer_dates:
                if self.stopped:
                    break
                if date_idx >= len(dates):
                    continue
                date = dates[date_idx]

                for grade_idx in prefer_grades:
                    if self.stopped:
                        break

                    result = self._try_book(account, date, grade_idx)

                    if result.get('status') == 200:
                        elapsed = time.monotonic() - t_start
                        grab_result = GrabResult(
                            success=True,
                            date=date,
                            grade=grade_idx,
                            endpoint=result['endpoint'],
                            response=result['body'],
                            attempts=attempt,
                            elapsed=elapsed,
                            timestamp=datetime.now().isoformat(),
                        )
                        self.result = grab_result
                        self.status = Status.SUCCESS
                        self.notifier.send(
                            f'🎉 抢票成功! {date} 档位#{grade_idx} '
                            f'耗时{elapsed:.1f}s/{attempt}次 '
                            f'延迟{result.get("latency_ms",0):.0f}ms'
                        )
                        self._emit('success', asdict(grab_result))
                        return grab_result

                    # 进度汇报
                    if attempt % 100 == 0:
                        elapsed = time.monotonic() - t_start
                        log.info(
                            f'[{attempt}/{max_retries}] '
                            f'avg={self.stats.avg_latency_ms:.0f}ms '
                            f'elapsed={elapsed:.0f}s'
                        )
                        self._emit('progress', {
                            'attempt': attempt,
                            'max': max_retries,
                            'avg_ms': self.stats.avg_latency_ms,
                            'elapsed': elapsed,
                        })

            time.sleep(delay)

        # 失败
        self.status = Status.FAILED
        elapsed = time.monotonic() - t_start
        self.notifier.send(f'😢 抢票失败 {attempt}次/{elapsed:.0f}s')
        self._emit('failed', {'attempts': attempt, 'elapsed': elapsed})
        return GrabResult(success=False, attempts=attempt, elapsed=elapsed)

    # ── 状态 ──

    def get_status(self) -> dict:
        return {
            'status': self.status.value,
            'stats': {
                'total_attempts': self.stats.total_attempts,
                'success_count': self.stats.success_count,
                'fail_count': self.stats.fail_count,
                'error_count': self.stats.error_count,
                'avg_latency_ms': round(self.stats.avg_latency_ms, 1),
                'min_latency_ms': round(self.stats.min_latency_ms, 1),
                'max_latency_ms': round(self.stats.max_latency_ms, 1),
                'start_time': self.stats.start_time,
                'last_attempt': self.stats.last_attempt,
            },
            'result': asdict(self.result) if self.result else None,
            'accounts': len(self.accounts),
        }


# ============================================================
#  等待器
# ============================================================

class SaleWaiter:
    """精确开售倒计时"""

    def __init__(self, target: datetime, pre_seconds: int = 2, callback=None):
        self.target = target
        self.pre_seconds = pre_seconds
        self.callback = callback

    def wait(self):
        from zoneinfo import ZoneInfo
        kst = ZoneInfo('Asia/Seoul')

        while True:
            now = datetime.now(kst)
            diff = (self.target - now).total_seconds()

            if diff <= 0:
                self._log('🎉 开售!')
                return

            elif diff > 120:
                self._log(f'距开售 {diff/60:.0f}min')
                time.sleep(60)

            elif diff > 10:
                self._log(f'距开售 {diff:.0f}s')
                time.sleep(5)

            elif diff > self.pre_seconds:
                self._log(f'⏱️ {diff:.1f}s')
                time.sleep(0.5)

            else:
                self._log(f'🚀 冲刺! {diff:.2f}s')
                while datetime.now(kst) < self.target:
                    pass
                return

    def _log(self, msg):
        log.info(msg)
        if self.callback:
            self.callback(msg)
