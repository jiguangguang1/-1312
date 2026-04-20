#!/usr/bin/env python3
"""
NOL 抢票系统 — 完整版

功能:
  1. 全自动抢票 (API 直调)
  2. Playwright 浏览器抢票 (备用)
  3. 监控模式 (票务状态监控 + 通知)
  4. 钉钉通知
  5. 自动日志记录
  6. 多场次/多档位并发

使用方法:
  编辑 config.json → python3 run.py [模式]

模式:
  grab     — 抢票模式 (默认)
  monitor  — 监控模式 (持续监控票务状态)
  check    — 检查模式 (一次性检查账号+票务)
  test     — 测试模式 (测试浏览器连接)
"""

import json
import time
import sys
import os
import re
import requests
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List

# ============================================================
#  路径 & 配置
# ============================================================

BASE = Path(__file__).parent
CONFIG_FILE = BASE / 'config.json'
TOKEN_FILE = BASE / 'token.json'
LOG_DIR = BASE / 'logs'
STATE_FILE = BASE / 'state.json'
SCREENSHOT_DIR = BASE / 'screenshots'

LOG_DIR.mkdir(exist_ok=True)
SCREENSHOT_DIR.mkdir(exist_ok=True)

# 日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / f'grabber_{datetime.now():%Y%m%d_%H%M%S}.log', encoding='utf-8'),
    ]
)
log = logging.getLogger('nol')


def load_json(path: Path, default=None):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default or {}


def save_json(path: Path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ============================================================
#  通知模块
# ============================================================

class Notifier:
    """多渠道通知"""

    def __init__(self, config: dict):
        self.ding_webhook = config.get('ding_webhook', '')
        self.wx_webhook = config.get('wx_webhook', '')

    def send(self, msg: str, level: str = 'info'):
        """发送通知"""
        log.info(f'📢 {msg}')
        self._dingtalk(msg)
        self._wxwork(msg)

    def _dingtalk(self, msg):
        if not self.ding_webhook:
            return
        try:
            requests.post(self.ding_webhook, json={
                'msgtype': 'text',
                'text': {'content': f'🎫 [NOL抢票] {msg}'}
            }, timeout=5)
        except Exception as e:
            log.warning(f'钉钉发送失败: {e}')

    def _wxwork(self, msg):
        if not self.wx_webhook:
            return
        try:
            requests.post(self.wx_webhook, json={
                'msgtype': 'text',
                'text': {'content': f'🎫 [NOL抢票] {msg}'}
            }, timeout=5)
        except Exception as e:
            log.warning(f'企微发送失败: {e}')


# ============================================================
#  NOL API 客户端
# ============================================================

API_BASE = 'https://world.nol.com/api'

class NOLClient:

    def __init__(self, config: dict, token_data: dict):
        self.cfg = config
        self.tokens = token_data
        self.s = requests.Session()
        self.s.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
            'Origin': 'https://world.nol.com',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })
        self._update_auth()
        if config.get('proxy'):
            self.s.proxies = {'https': config['proxy'], 'http': config['proxy']}

    def _update_auth(self):
        token = self.tokens.get('access_token', '')
        self.s.headers['Authorization'] = f'Bearer {token}'
        self.s.headers['Referer'] = (
            f'https://world.nol.com/zh-CN/ticket/places/'
            f'{self.cfg["place_code"]}/products/{self.cfg["goods_code"]}'
        )

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
                    self._update_auth()
                    save_json(TOKEN_FILE, self.tokens)
                    log.info('✅ Token 已刷新')
                    return True
        except Exception as e:
            log.warning(f'Token 刷新失败: {e}')
        return False

    # ── 公开 API ──

    def sales_info(self) -> dict:
        r = self.s.get(f'{API_BASE}/ent-channel-out/v1/goods/salesinfo', params={
            'goodsCode': self.cfg['goods_code'],
            'placeCode': self.cfg['place_code'],
            'bizCode': self.cfg.get('biz_code', '10965'),
        }, timeout=10)
        r.raise_for_status()
        return r.json()['data']

    def goods_detail(self) -> dict:
        r = self.s.get(f'{API_BASE}/ent-channel-out/v1/goods/detail', params={
            'goodsCode': self.cfg['goods_code'],
            'placeCode': self.cfg['place_code'],
            'language': 'ZH_CN',
        }, timeout=10)
        r.raise_for_status()
        return r.json()['data']

    # ── 需要 Auth ──

    def user_info(self) -> dict:
        r = self.s.get(f'{API_BASE}/users', timeout=10)
        r.raise_for_status()
        return r.json()

    def enter_info(self) -> dict:
        r = self.s.get(f'{API_BASE}/users/enter', params={
            'goods_code': self.cfg['goods_code'],
            'place_code': self.cfg['place_code'],
        }, timeout=10)
        r.raise_for_status()
        return r.json()

    def reservations(self) -> list:
        r = self.s.get(f'{API_BASE}/biz/enter/reservations', params={
            'languageType': 'CN', 'memberType': 0,
            'searchStartDate': '20260101', 'searchEndDate': '20261231',
        }, timeout=10)
        r.raise_for_status()
        return r.json().get('data', [])

    # ── 抢票 ──

    def book(self, play_date: str, grade_idx: int, enter: dict) -> dict:
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
            try:
                r = self.s.post(f'{API_BASE}{ep}', json=payload, timeout=10)
                if r.status_code not in (404, 405):
                    return {'endpoint': ep, 'status': r.status_code, 'body': r.text[:2000]}
            except requests.exceptions.Timeout:
                continue
            except Exception as e:
                log.debug(f'{ep}: {e}')
                continue
        return {'status': 'all_failed'}


# ============================================================
#  时间工具
# ============================================================

def parse_sale_time(time_str: str, tz='Asia/Seoul') -> datetime:
    from zoneinfo import ZoneInfo
    return datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=ZoneInfo(tz))

def now_tz(tz='Asia/Seoul'):
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo(tz))


# ============================================================
#  模式: check (检查账号+票务)
# ============================================================

def mode_check(cfg, token_data, notifier):
    """一次性检查"""
    log.info('=' * 50)
    log.info('🔍 检查模式')
    log.info('=' * 50)

    nol = NOLClient(cfg, token_data)

    # 账号
    try:
        user = nol.user_info()
        log.info(f'✅ 账号: {user.get("name")} ({user.get("email")})')
        log.info(f'   Provider: {user.get("provider")}')
    except Exception as e:
        log.error(f'❌ 账号验证失败: {e}')
        return False

    # eKYC
    try:
        enter = nol.enter_info()
        ekyc = enter.get('enterEkyc', {})
        status = ekyc.get('status', 'unknown')
        log.info(f'📋 eKYC: {status}')
        if status != 'approved':
            log.warning('⚠️ eKYC 未通过，需要实名认证')
    except Exception as e:
        log.error(f'❌ enter 失败: {e}')
        return False

    # 售卖信息
    try:
        sales = nol.sales_info()
        si = sales['salesInfo']
        log.info(f'📅 演出: {si["playStartDate"]} ~ {si["playEndDate"]}')
        log.info(f'   一般开售: {si["bookingOpenTime"]} KST')
        log.info(f'   截止: {si["bookingEndTime"]}')
        log.info(f'   状态: {"✅ 可售" if si["goodsStatus"] == "Y" else "❌ 不可售"}')

        for ps in sales.get('preSalesInfo', []):
            log.info(f'   🎫 预售: {ps["preBookingKindName"]}')
            log.info(f'      {ps["bookingOpenTime"]} ~ {ps["bookingEndTime"]}')
    except Exception as e:
        log.error(f'❌ 售卖信息失败: {e}')
        return False

    # 已有订单
    try:
        res = nol.reservations()
        log.info(f'📋 已有订单: {len(res)} 个')
    except:
        pass

    return True


# ============================================================
#  模式: monitor (持续监控)
# ============================================================

def mode_monitor(cfg, token_data, notifier):
    """监控模式 — 持续监控票务状态变化"""
    interval = cfg.get('monitor_interval', 30)  # 秒
    log.info('=' * 50)
    log.info(f'👁️ 监控模式 (每{interval}s检查)')
    log.info('=' * 50)

    nol = NOLClient(cfg, token_data)
    last_status = None

    while True:
        try:
            sales = nol.sales_info()
            si = sales['salesInfo']
            status = si['goodsStatus']

            # 检查状态变化
            if status != last_status:
                log.info(f'📊 状态变化: {last_status} → {status}')
                if status == 'Y':
                    notifier.send(f'🟢 票务已开放！{si["playStartDate"]}~{si["playEndDate"]}')
                last_status = status

            # 检查预售信息
            for ps in sales.get('preSalesInfo', []):
                open_time = parse_sale_time(ps['bookingOpenTime'])
                remaining = (open_time - now_tz()).total_seconds()
                if 0 < remaining < 300:  # 5分钟内开售
                    notifier.send(f'⏰ 预售即将开始: {ps["preBookingKindName"]} 还有{remaining:.0f}s')
                elif -60 < remaining < 0:  # 刚开售1分钟内
                    notifier.send(f'🚨 预售已开始！{ps["preBookingKindName"]}')

            # 检查一般开售
            open_time = parse_sale_time(si['bookingOpenTime'])
            remaining = (open_time - now_tz()).total_seconds()
            if 0 < remaining < 300:
                notifier.send(f'⏰ 一般开售还有{remaining:.0f}s')
            elif -60 < remaining < 0:
                notifier.send(f'🚨 一般开售已开始！')

            log.debug(f'监控中... status={status} 剩余={remaining:.0f}s')

        except Exception as e:
            log.warning(f'监控异常: {e}')

        time.sleep(interval)


# ============================================================
#  模式: grab (抢票)
# ============================================================

def mode_grab(cfg, token_data, notifier):
    """抢票模式"""
    log.info('=' * 50)
    log.info('🎫 抢票模式')
    log.info('=' * 50)

    nol = NOLClient(cfg, token_data)

    # 检查账号
    try:
        user = nol.user_info()
        log.info(f'✅ {user.get("name")} ({user.get("email")})')
    except Exception as e:
        log.error(f'❌ 账号失败: {e}')
        return

    # 检查 eKYC
    enter = nol.enter_info()
    ekyc_status = enter.get('enterEkyc', {}).get('status', 'unknown')
    log.info(f'eKYC: {ekyc_status}')

    # 售卖信息
    sales = nol.sales_info()
    si = sales['salesInfo']
    log.info(f'演出: {si["playStartDate"]}~{si["playEndDate"]}')

    # 确定时间
    sale_time = parse_sale_time(cfg['sale_time'])
    presale = cfg.get('presale_time')
    target = parse_sale_time(presale) if presale else sale_time
    kind = '粉丝预售' if presale else '一般开售'

    remaining = (target - now_tz()).total_seconds()
    log.info(f'目标: {kind} {target} KST')
    log.info(f'剩余: {remaining:.0f}s ({remaining/3600:.1f}h)')

    # 等待
    if remaining > 5:
        log.info('⏳ 等待开售...')
        try:
            while True:
                diff = (target - now_tz()).total_seconds()
                if diff <= 0:
                    break
                elif diff > 120:
                    log.info(f'距开售 {diff/60:.0f}min')
                    time.sleep(60)
                elif diff > 10:
                    log.info(f'距开售 {diff:.0f}s')
                    time.sleep(5)
                elif diff > 3:
                    log.info(f'⏱️ {diff:.1f}s')
                    time.sleep(0.5)
                else:
                    log.info(f'🚀 冲刺！')
                    while now_tz() < target:
                        pass
                    break
        except KeyboardInterrupt:
            log.info('中断')
            return

    # 刷新 token
    nol.refresh_token()

    # 重新获取 enter
    enter = nol.enter_info()

    # 抢票
    log.info('🎫 开抢！')
    notifier.send(f'🚀 开始抢票! {kind}')

    dates = cfg.get('play_dates', ['2026-06-12', '2026-06-13'])
    max_retries = cfg.get('max_retries', 200)
    delay = cfg.get('retry_delay', 0.05)

    for attempt in range(1, max_retries + 1):
        for date_idx in cfg.get('prefer_dates', [0, 1]):
            if date_idx >= len(dates):
                continue
            date = dates[date_idx]

            for grade_idx in cfg.get('prefer_grades', [0, 1, 2, 3]):
                try:
                    result = nol.book(date, grade_idx, enter)

                    if result.get('status') == 200:
                        log.info(f'🎉🎉🎉 成功！{date} grade#{grade_idx}')
                        log.info(f'响应: {result.get("body", "")[:500]}')
                        notifier.send(f'🎉 抢票成功! {date} 档位#{grade_idx}')

                        save_json(STATE_FILE, {
                            'success': True,
                            'time': datetime.now().isoformat(),
                            'date': date, 'grade': grade_idx,
                            'result': result,
                        })
                        return

                    if attempt % 50 == 0 or attempt <= 3:
                        log.info(f'[{attempt}/{max_retries}] {date} g{grade_idx} → {result.get("status")}')

                except Exception as e:
                    if attempt % 100 == 0:
                        log.warning(f'[{attempt}] {e}')

        time.sleep(delay)

    log.error('😢 失败')
    notifier.send('😢 抢票失败')
    save_json(STATE_FILE, {'success': False, 'time': datetime.now().isoformat()})


# ============================================================
#  模式: test (浏览器测试)
# ============================================================

def mode_test(cfg, token_data, notifier):
    """浏览器测试"""
    log.info('=' * 50)
    log.info('🧪 浏览器测试模式')
    log.info('=' * 50)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.error('需要安装 playwright: pip install playwright && playwright install chromium')
        return

    token = token_data.get('access_token', '')
    if not token:
        log.error('token.json 缺少 access_token')
        return

    goods = cfg['goods_code']
    place = cfg['place_code']
    url = f'https://world.nol.com/zh-CN/ticket/places/{place}/products/{goods}'

    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        args=['--no-sandbox', '--disable-dev-shm-usage'],
        channel='chromium',
    )
    ctx = browser.new_context(
        viewport={'width': 1366, 'height': 768},
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
        locale='zh-CN', timezone_id='Asia/Seoul', ignore_https_errors=True,
    )
    ctx.add_cookies([
        {'name': 'access_token', 'value': token, 'domain': 'world.nol.com', 'path': '/', 'httpOnly': True, 'secure': True},
        {'name': 'refresh_token', 'value': token_data.get('refresh_token', ''), 'domain': 'world.nol.com', 'path': '/', 'httpOnly': True, 'secure': True},
        {'name': 'kint5-web-device-id', 'value': token_data.get('device_id', ''), 'domain': 'world.nol.com', 'path': '/'},
        {'name': 'tk-language', 'value': 'zh-CN', 'domain': 'world.nol.com', 'path': '/'},
    ])
    ctx.add_init_script('Object.defineProperty(navigator,"webdriver",{get:()=>undefined})')

    page = ctx.new_page()
    page.set_default_timeout(30000)

    log.info(f'加载: {url}')
    page.goto(url, wait_until='domcontentloaded', timeout=60000)
    time.sleep(5)

    title = page.title()
    log.info(f'标题: {title}')

    if 'login' in page.url.lower():
        log.error('❌ 未登录')
    else:
        log.info('✅ 已登录')

        # 检查购买按钮
        for text in ['立即购买', '立即预订', '购买', 'Book']:
            try:
                btn = page.locator(f'text={text}').first
                if btn.is_visible(timeout=1000):
                    log.info(f'🛒 找到按钮: {text}')
            except:
                pass

    page.screenshot(path=str(SCREENSHOT_DIR / 'test.png'), full_page=False, timeout=10000)
    log.info(f'截图: {SCREENSHOT_DIR / "test.png"}')

    browser.close()
    pw.stop()
    log.info('✅ 测试完成')


# ============================================================
#  入口
# ============================================================

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'grab'

    # 加载配置
    if not CONFIG_FILE.exists():
        # 创建默认配置
        default_cfg = {
            "goods_code": "26005547",
            "place_code": "26000398",
            "biz_code": "10965",
            "sale_time": "2026-04-30 20:00:00",
            "sale_tz": "Asia/Seoul",
            "play_dates": ["2026-06-12", "2026-06-13"],
            "prefer_dates": [0, 1],
            "prefer_grades": [0, 1, 2, 3],
            "ticket_count": 1,
            "max_retries": 200,
            "retry_delay": 0.05,
            "monitor_interval": 30,
            "proxy": "",
            "ding_webhook": "",
            "wx_webhook": ""
        }
        save_json(CONFIG_FILE, default_cfg)
        log.info(f'已创建默认配置: {CONFIG_FILE}')
        log.info('请编辑 config.json 和 token.json 后重新运行')
        return

    cfg = load_json(CONFIG_FILE)
    token_data = load_json(TOKEN_FILE)

    if not token_data.get('access_token'):
        log.error('token.json 缺少 access_token，请填入后重试')
        return

    notifier = Notifier(cfg)

    modes = {
        'grab': mode_grab,
        'monitor': mode_monitor,
        'check': mode_check,
        'test': mode_test,
    }

    if mode not in modes:
        log.error(f'未知模式: {mode}  可选: {", ".join(modes.keys())}')
        return

    try:
        modes[mode](cfg, token_data, notifier)
    except KeyboardInterrupt:
        log.info('用户中断')
    except Exception as e:
        log.error(f'异常: {e}', exc_info=True)
        notifier.send(f'⚠️ 异常: {str(e)[:100]}')


if __name__ == '__main__':
    main()
