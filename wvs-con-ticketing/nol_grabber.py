#!/usr/bin/env python3
"""
NOL 抢票脚本 — BTS WORLD TOUR 'ARIRANG' IN BUSAN
基于 API 直接调用 + Playwright 浏览器备用方案

使用方法:
  1. 填入 access_token 和 refresh_token
  2. python3 nol_grabber.py

⚠️ 使用前确认:
  - NOL 账号已完成 eKYC 实名认证
  - 如参加粉丝预售，需完成会员验证
"""

import json
import time
import sys
import os
import re
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List

import requests

# ============================================================
#  配置 — 在这里修改
# ============================================================

CONFIG = {
    # 演出信息
    'goods_code': '26005547',
    'place_code': '26000398',
    'biz_code': '10965',

    # 开售时间 (KST = UTC+9)
    # 一般开售: 2026-04-30 20:00 KST
    'sale_time': '2026-04-30 20:00:00',
    'sale_tz': 'Asia/Seoul',  # KST

    # 粉丝预售 (如不参加，留空)
    # 'presale_time': '2026-04-29 20:00:00',

    # 期望场次: 0=Day1 (6/12), 1=Day2 (6/13)
    'prefer_dates': [0, 1],

    # 期望档位 (index 优先级，从 0 开始)
    # 需要根据实际页面的档位顺序填写
    'prefer_grades': [0, 1, 2, 3],

    # 购买数量
    'ticket_count': 1,

    # 登录 Token (从浏览器 Cookie 获取)
    # ⚠️ Token 只有5分钟有效期，需要在开售前刷新
    'access_token': '',
    'refresh_token': '',

    # 设备 ID (从浏览器 Cookie 获取)
    'device_id': '',

    # 代理 (可选，海外 VPS 可留空)
    'proxy': '',

    # 抢票策略
    'max_retries': 200,           # 最大重试次数
    'retry_delay': 0.05,          # 重试间隔(秒)
    'pre_seconds': 3,             # 提前几秒开始冲刺
    'refresh_token_before': 60,   # 开售前多少秒刷新 token

    # 通知
    'ding_webhook': '',           # 钉钉 webhook (可选)
}

# ============================================================
#  NOL API 客户端
# ============================================================

API_BASE = 'https://world.nol.com/api'

class NOLClient:
    """NOL API 客户端"""

    def __init__(self, config: dict):
        self.cfg = config
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Origin': 'https://world.nol.com',
            'Referer': f'https://world.nol.com/zh-CN/ticket/places/{config["place_code"]}/products/{config["goods_code"]}',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        if config.get('proxy'):
            self.session.proxies = {'https': config['proxy'], 'http': config['proxy']}
        self._update_token(config['access_token'])
        self._member_info = None
        self._goods_detail = None
        self._sales_info = None

    def _update_token(self, token: str):
        self.session.headers['Authorization'] = f'Bearer {token}'

    def log(self, msg: str, level: str = 'info'):
        ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        print(f'[{ts}] [{level.upper()}] {msg}')

    # ── 公开 API (不需要 auth) ──

    def get_sales_info(self) -> dict:
        """获取售卖信息"""
        r = self.session.get(f'{API_BASE}/ent-channel-out/v1/goods/salesinfo', params={
            'goodsCode': self.cfg['goods_code'],
            'placeCode': self.cfg['place_code'],
            'bizCode': self.cfg['biz_code'],
        }, timeout=10)
        r.raise_for_status()
        data = r.json()['data']
        self._sales_info = data
        return data

    def get_goods_detail(self) -> dict:
        """获取商品详情"""
        r = self.session.get(f'{API_BASE}/ent-channel-out/v1/goods/detail', params={
            'goodsCode': self.cfg['goods_code'],
            'placeCode': self.cfg['place_code'],
            'language': 'ZH_CN',
        }, timeout=10)
        r.raise_for_status()
        data = r.json()['data']
        self._goods_detail = data
        return data

    # ── 需要 Auth 的 API ──

    def get_user_info(self) -> dict:
        """获取用户信息"""
        r = self.session.get(f'{API_BASE}/users', timeout=10)
        r.raise_for_status()
        return r.json()

    def get_enter_info(self) -> dict:
        """获取购票凭证 — 这是下单的核心参数！"""
        r = self.session.get(f'{API_BASE}/users/enter', params={
            'goods_code': self.cfg['goods_code'],
            'place_code': self.cfg['place_code'],
        }, timeout=10)
        r.raise_for_status()
        data = r.json()
        self._member_info = data
        return data

    def check_reservations(self) -> list:
        """查询已有订单"""
        r = self.session.get(f'{API_BASE}/biz/enter/reservations', params={
            'languageType': 'CN',
            'memberType': 0,
            'searchStartDate': '20260101',
            'searchEndDate': '20261231',
        }, timeout=10)
        r.raise_for_status()
        return r.json().get('data', [])

    # ── 核心: booking API ──

    def attempt_booking(self, schedule_date: str, grade_index: int, enter_info: dict) -> dict:
        """
        尝试下单购票

        ⚠️ 这里是猜测的 API 结构，需要根据实际拦截到的请求确认。
        NOL 可能通过以下两种方式之一:
        1. 直接 API 下单 (最理想)
        2. 跳转到 Interpark 的 iframe 选座系统 (需要 Playwright)

        以下是基于 Interpark API 模式的尝试
        """
        payload = {
            'goodsCode': self.cfg['goods_code'],
            'placeCode': self.cfg['place_code'],
            'bizCode': self.cfg['biz_code'],
            'playDate': schedule_date,      # e.g. '2026-06-12'
            'gradeIndex': grade_index,
            'ticketCount': self.cfg['ticket_count'],
            'memberId': enter_info.get('enterMemberId', ''),
            'memberNo': enter_info.get('enterMemberNo', ''),
            'encryptVal': enter_info.get('enterEncryptVal', ''),
            'languageType': 'CN',
        }

        # 尝试多个可能的 booking 端点
        endpoints = [
            f'{API_BASE}/biz/enter/booking',
            f'{API_BASE}/ent-channel-out/v1/booking/create',
            f'{API_BASE}/ent-channel-out/v1/booking/reserve',
            f'{API_BASE}/booking/create',
        ]

        for endpoint in endpoints:
            try:
                r = self.session.post(endpoint, json=payload, timeout=10)
                if r.status_code != 404:
                    self.log(f'Booking API 响应 [{r.status_code}]: {endpoint}')
                    return {'status': r.status_code, 'body': r.text[:500], 'endpoint': endpoint}
            except requests.exceptions.Timeout:
                self.log(f'超时: {endpoint}', 'warning')
            except Exception as e:
                self.log(f'异常: {endpoint} → {e}', 'warning')

        return {'status': 'no_endpoint_found'}

    # ── Token 刷新 ──

    def try_refresh_token(self) -> bool:
        """尝试用 refresh_token 刷新 access_token"""
        refresh = self.cfg.get('refresh_token', '')
        if not refresh:
            return False
        try:
            r = self.session.post(f'{API_BASE}/auth/refresh', json={
                'refreshToken': refresh,
            }, timeout=10)
            if r.status_code == 200:
                data = r.json()
                new_token = data.get('accessToken', '')
                if new_token:
                    self._update_token(new_token)
                    self.cfg['access_token'] = new_token
                    self.log('✅ Token 已刷新')
                    return True
        except Exception as e:
            self.log(f'Token 刷新失败: {e}', 'warning')
        return False


# ============================================================
#  抢票主逻辑
# ============================================================

def parse_sale_time(config: dict) -> datetime:
    """解析开售时间"""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(config['sale_tz'])
    naive = datetime.strptime(config['sale_time'], '%Y-%m-%d %H:%M:%S')
    return naive.replace(tzinfo=tz)


def wait_for_sale(target: datetime, pre_seconds: int = 3, logger=None):
    """精确倒计时"""
    from zoneinfo import ZoneInfo
    kst = ZoneInfo('Asia/Seoul')

    while True:
        now = datetime.now(kst)
        diff = (target - now).total_seconds()

        if diff <= 0:
            if logger:
                logger('🎉 开售时间到！开始抢票！')
            return

        if diff > 15:
            sleep_time = diff - 10
            if logger:
                logger(f'⏱️ 距开售 {diff:.0f}s，等待 {sleep_time:.0f}s...')
            time.sleep(sleep_time)
        elif diff > pre_seconds:
            if logger:
                logger(f'⏱️ {diff:.1f}s...')
            time.sleep(0.5)
        else:
            # 冲刺阶段：忙等待
            if logger:
                logger(f'🚀 冲刺！{diff:.2f}s')
            while datetime.now(kst) < target:
                pass
            return


def send_dingtalk(webhook: str, message: str):
    """钉钉通知"""
    if not webhook:
        return
    try:
        requests.post(webhook, json={
            'msgtype': 'text',
            'text': {'content': f'🎫 [NOL抢票] {message}'}
        }, timeout=5)
    except:
        pass


def main():
    config = CONFIG

    if not config['access_token']:
        print('❌ 请先填入 access_token！')
        print('   从浏览器 Cookie-Editor 复制 access_token 的值')
        sys.exit(1)

    client = NOLClient(config)

    print('=' * 60)
    print('🎫 NOL 抢票脚本 — BTS WORLD TOUR \'ARIRANG\' IN BUSAN')
    print('=' * 60)

    # Step 1: 验证账号
    print('\n📋 Step 1: 验证账号...')
    try:
        user = client.get_user_info()
        print(f'   ✅ 用户: {user.get("name", "?")} ({user.get("email", "?")})')
    except Exception as e:
        print(f'   ❌ 获取用户信息失败: {e}')
        print('   Token 可能已过期，请重新获取')
        sys.exit(1)

    # Step 2: 获取售卖信息
    print('\n📋 Step 2: 获取售卖信息...')
    try:
        sales = client.get_sales_info()
        si = sales['salesInfo']
        print(f'   演出期: {si["playStartDate"]} ~ {si["playEndDate"]}')
        print(f'   一般开售: {si["bookingOpenTime"]}')
        print(f'   截止时间: {si["bookingEndTime"]}')
        print(f'   状态: {"可售" if si["goodsStatus"] == "Y" else "不可售"}')

        # 预售信息
        for ps in sales.get('preSalesInfo', []):
            print(f'   🎫 预售: {ps["preBookingKindName"]}')
            print(f'      时间: {ps["bookingOpenTime"]} ~ {ps["bookingEndTime"]}')
            print(f'      验证字段: {ps.get("checkFieldName1", "")} / {ps.get("checkFieldName2", "")}')
    except Exception as e:
        print(f'   ❌ 获取售卖信息失败: {e}')
        sys.exit(1)

    # Step 3: 获取购票凭证
    print('\n📋 Step 3: 获取购票凭证...')
    try:
        enter = client.get_enter_info()
        print(f'   ✅ Member ID: {enter.get("enterMemberId", "?")}')
        print(f'   ✅ Member No: {enter.get("enterMemberNo", "?")}')
        print(f'   Has Email: {enter.get("enterHasEmail", False)}')
        print(f'   Has eKYC: {enter.get("enterHasEkyc", False)}')

        ekyc = enter.get('enterEkyc', {})
        ekyc_status = ekyc.get('status', 'unknown')
        print(f'   eKYC 状态: {ekyc_status}')

        if ekyc_status != 'approved':
            print(f'   ⚠️ eKYC 未通过! 需要先完成实名认证才能购票')
            print(f'   请在 NOL 网站完成认证后重试')
    except Exception as e:
        print(f'   ❌ 获取购票凭证失败: {e}')
        sys.exit(1)

    # Step 4: 检查已有订单
    print('\n📋 Step 4: 检查已有订单...')
    try:
        reservations = client.check_reservations()
        print(f'   已有订单数: {len(reservations)}')
    except Exception as e:
        print(f'   ⚠️ 查询订单失败: {e}')

    # Step 5: 确定开售时间
    print('\n📋 Step 5: 开售时间...')
    sale_time = parse_sale_time(config)

    # 检查是否使用预售时间
    presale_time = None
    if config.get('presale_time'):
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(config['sale_tz'])
        presale_time = datetime.strptime(config['presale_time'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=tz)

    target_time = presale_time or sale_time
    kind = "粉丝预售" if presale_time else "一般开售"

    from zoneinfo import ZoneInfo
    kst = ZoneInfo('Asia/Seoul')
    now = datetime.now(kst)
    diff = (target_time - now).total_seconds()

    print(f'   类型: {kind}')
    print(f'   开售: {target_time.strftime("%Y-%m-%d %H:%M:%S")} KST')
    print(f'   现在: {now.strftime("%Y-%m-%d %H:%M:%S")} KST')
    print(f'   倒计时: {diff:.0f}s ({diff/3600:.1f}h)')

    if diff < -3600:
        print(f'   ⚠️ 已过开售时间超过1小时，可能已售罄')
    elif diff < 0:
        print(f'   ⚠️ 已过开售时间，立即尝试购买！')

    # Step 6: 等待 & 抢票
    print('\n📋 Step 6: 准备抢票...')
    print(f'   档位优先级: {config["prefer_grades"]}')
    print(f'   日期优先级: {config["prefer_dates"]}')
    print(f'   最大重试: {config["max_retries"]}次')
    print()

    # 如果还没到时间，等待
    if diff > config['refresh_token_before']:
        print(f'⏳ 等待开售... (Ctrl+C 可随时中断)')
        try:
            wait_for_sale(
                target_time - timedelta(seconds=config['pre_seconds']),
                config['pre_seconds'],
                lambda msg: print(f'   {msg}')
            )
        except KeyboardInterrupt:
            print('\n⏹️ 用户中断')
            return

    # 刷新 token
    if diff > 60:
        print('🔄 刷新 token...')
        client.try_refresh_token()

    # 冲刺抢票
    print('\n🚀 开始抢票！')
    send_dingtalk(config.get('ding_webhook', ''), f'🚀 开始抢票! {kind}')

    dates = ['2026-06-12', '2026-06-13']

    for attempt in range(1, config['max_retries'] + 1):
        for date_idx in config['prefer_dates']:
            if date_idx >= len(dates):
                continue
            date = dates[date_idx]

            for grade_idx in config['prefer_grades']:
                try:
                    result = client.attempt_booking(date, grade_idx, enter)

                    if result.get('status') == 200:
                        print(f'\n🎉🎉🎉 抢票成功！！！')
                        print(f'   日期: {date}')
                        print(f'   档位: #{grade_idx}')
                        print(f'   响应: {result.get("body", "")[:200]}')
                        send_dingtalk(config.get('ding_webhook', ''), f'🎉 抢票成功! {date} 档位#{grade_idx}')
                        return

                    if attempt % 20 == 0:
                        print(f'   [{attempt}/{config["max_retries"]}] {date} grade#{grade_idx} → {result.get("status")}')

                except Exception as e:
                    if attempt % 50 == 0:
                        print(f'   [{attempt}] 异常: {e}')

        time.sleep(config['retry_delay'])

    print('\n😢 抢票失败，已用尽所有重试')
    send_dingtalk(config.get('ding_webhook', ''), '😢 抢票失败')


# ============================================================
#  Playwright 备用方案 (API 不可用时)
# ============================================================

async def browser_grab(config: dict):
    """
    当 API 直接下单不可用时，用 Playwright 模拟浏览器操作
    这是 Interpark/NOL 的传统选座购票流程
    """
    from playwright.async_api import async_playwright

    TOKEN = config['access_token']
    DEVICE_ID = config['device_id']
    GOODS = config['goods_code']
    PLACE = config['place_code']
    URL = f'https://world.nol.com/zh-CN/ticket/places/{PLACE}/products/{GOODS}'

    print('🌐 启动浏览器模式...')

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage'],
            channel='chromium',
            proxy={'server': config['proxy']} if config.get('proxy') else None,
        )
        context = await browser.new_context(
            viewport={'width': 1366, 'height': 768},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            locale='zh-CN',
            timezone_id='Asia/Seoul',
            ignore_https_errors=True,
        )

        # 注入登录态
        await context.add_cookies([
            {'name': 'access_token', 'value': TOKEN, 'domain': 'world.nol.com', 'path': '/', 'httpOnly': True, 'secure': True},
            {'name': 'refresh_token', 'value': config['refresh_token'], 'domain': 'world.nol.com', 'path': '/', 'httpOnly': True, 'secure': True},
            {'name': 'kint5-web-device-id', 'value': DEVICE_ID, 'domain': 'world.nol.com', 'path': '/'},
            {'name': 'tk-language', 'value': 'zh-CN', 'domain': 'world.nol.com', 'path': '/'},
        ])

        await context.add_init_script(f'''
            Object.defineProperty(navigator, "webdriver", {{get: () => undefined}});
            localStorage.setItem("access_token", "{TOKEN}");
        ''')

        page = await context.new_page()
        page.set_default_timeout(30000)

        # 加载页面
        await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
        await asyncio.sleep(5)

        print(f'📄 {await page.title()}')

        # 等待开售
        target = parse_sale_time(config)
        from zoneinfo import ZoneInfo
        kst = ZoneInfo('Asia/Seoul')

        while datetime.now(kst) < target:
            remaining = (target - datetime.now(kst)).total_seconds()
            if remaining > 30:
                await asyncio.sleep(remaining - 25)
                await page.reload()
            elif remaining > 3:
                print(f'⏱️ {remaining:.1f}s')
                await asyncio.sleep(1)
            else:
                # 冲刺：疯狂刷新
                while datetime.now(kst) < target:
                    pass
                break

        print('🎉 开售！')

        # 疯狂点击购买按钮
        buy_texts = ['立即购买', '立即预订', '购买', 'Book', 'Buy', '예매하기']
        for attempt in range(config['max_retries']):
            for text in buy_texts:
                try:
                    btn = page.locator(f'text={text}').first
                    if await btn.is_visible(timeout=200):
                        await btn.click(timeout=1000)
                        print(f'✅ 点击成功: {text} (第{attempt+1}次)')
                        await asyncio.sleep(3)

                        # 检查是否进入选座
                        content = await page.content()
                        if any(k in content for k in ['选座', 'select seat', '좌석', '区域', '等级']):
                            print('🎯 进入选座页面！')
                            # TODO: 自动选座逻辑
                            await page.screenshot(path='screenshots/nol_seat_selection.png')
                            return True
                except:
                    continue

            await asyncio.sleep(config['retry_delay'])

        print('😢 浏览器抢票也失败了')
        return False


if __name__ == '__main__':
    print("""
╔══════════════════════════════════════════════════════════╗
║  NOL 抢票脚本 v1.0                                      ║
║  目标: BTS WORLD TOUR 'ARIRANG' IN BUSAN               ║
║  日期: 2026-06-12 ~ 2026-06-13                          ║
║  开售: 2026-04-30 20:00 KST (一般)                      ║
║  预售: 2026-04-29 20:00 KST (粉丝)                      ║
╚══════════════════════════════════════════════════════════╝
    """)
    main()
