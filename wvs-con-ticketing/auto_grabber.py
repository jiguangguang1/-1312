#!/usr/bin/env python3
"""
NOL 全自动抢票脚本 — BTS WORLD TOUR 'ARIRANG' IN BUSAN

使用方法:
  1. 编辑 token.json，填入你的 access_token / refresh_token / device_id
  2. python3 auto_grabber.py

脚本会自动:
  - 检查账号状态 & eKYC
  - 倒计时到开售
  - 开售瞬间 API 抢票
  - 成功后通知
"""

import json
import time
import sys
import os
import requests
from datetime import datetime, timedelta
from pathlib import Path

# ============================================================
#  配置加载
# ============================================================

SCRIPT_DIR = Path(__file__).parent
TOKEN_FILE = SCRIPT_DIR / 'token.json'
STATE_FILE = SCRIPT_DIR / 'grabber_state.json'

def load_config():
    if not TOKEN_FILE.exists():
        print('❌ token.json 不存在！请创建并填入 token')
        sys.exit(1)
    with open(TOKEN_FILE) as f:
        cfg = json.load(f)
    if not cfg.get('access_token'):
        print('❌ access_token 为空！请编辑 token.json')
        sys.exit(1)
    return cfg

def save_config(cfg):
    with open(TOKEN_FILE, 'w') as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

# ============================================================
#  NOL API
# ============================================================

API = 'https://world.nol.com/api'

class NOL:
    def __init__(self, cfg):
        self.cfg = cfg
        self.s = requests.Session()
        self.s.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
            'Origin': 'https://world.nol.com',
            'Referer': f'https://world.nol.com/zh-CN/ticket/places/{cfg["place_code"]}/products/{cfg["goods_code"]}',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Authorization': f'Bearer {cfg["access_token"]}',
        })
        if cfg.get('proxy'):
            self.s.proxies = {'https': cfg['proxy'], 'http': cfg['proxy']}

    def _get(self, path, **kw):
        r = self.s.get(f'{API}{path}', timeout=15, **kw)
        r.raise_for_status()
        return r.json()

    def _post(self, path, **kw):
        r = self.s.post(f'{API}{path}', timeout=15, **kw)
        return r

    def user(self):
        return self._get('/users')

    def sales_info(self):
        return self._get('/ent-channel-out/v1/goods/salesinfo', params={
            'goodsCode': self.cfg['goods_code'],
            'placeCode': self.cfg['place_code'],
            'bizCode': self.cfg['biz_code'],
        })

    def enter_info(self):
        return self._get('/users/enter', params={
            'goods_code': self.cfg['goods_code'],
            'place_code': self.cfg['place_code'],
        })

    def reservations(self):
        return self._get('/biz/enter/reservations', params={
            'languageType': 'CN', 'memberType': 0,
            'searchStartDate': '20260101', 'searchEndDate': '20261231',
        })

    def try_refresh(self):
        rt = self.cfg.get('refresh_token', '')
        if not rt:
            return False
        try:
            r = self._post('/auth/refresh', json={'refreshToken': rt})
            if r.status_code == 200:
                new = r.json().get('accessToken', '')
                if new:
                    self.cfg['access_token'] = new
                    self.s.headers['Authorization'] = f'Bearer {new}'
                    save_config(self.cfg)
                    return True
        except:
            pass
        return False

    def book(self, play_date, grade_idx, enter):
        """尝试下单"""
        payload = {
            'goodsCode': self.cfg['goods_code'],
            'placeCode': self.cfg['place_code'],
            'bizCode': self.cfg['biz_code'],
            'playDate': play_date,
            'gradeIndex': grade_idx,
            'ticketCount': self.cfg['ticket_count'],
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
                r = self._post(ep, json=payload)
                if r.status_code not in (404, 405):
                    return {'endpoint': ep, 'status': r.status_code, 'body': r.text[:1000]}
            except requests.exceptions.Timeout:
                continue
            except Exception:
                continue
        return {'status': 'all_failed'}

# ============================================================
#  主流程
# ============================================================

def log(msg, level='INFO'):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f'[{ts}] [{level}] {msg}')

def notify(webhook, msg):
    if not webhook:
        return
    try:
        requests.post(webhook, json={'msgtype': 'text', 'text': {'content': f'🎫 {msg}'}}, timeout=5)
    except:
        pass

def parse_time(t_str, tz_name='Asia/Seoul'):
    from zoneinfo import ZoneInfo
    return datetime.strptime(t_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=ZoneInfo(tz_name))

def now_kst():
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo('Asia/Seoul'))

def main():
    cfg = load_config()
    nol = NOL(cfg)
    webhook = cfg.get('ding_webhook', '')

    print()
    print('╔════════════════════════════════════════════════╗')
    print('║  🎫 NOL 全自动抢票 — BTS ARIRANG IN BUSAN    ║')
    print('╚════════════════════════════════════════════════╝')
    print()

    # ── Step 1: 账号检查 ──
    log('检查账号...')
    try:
        user = nol.user()
        log(f'账号: {user.get("name")} ({user.get("email")})', 'OK')
    except Exception as e:
        log(f'账号验证失败: {e}', 'ERROR')
        log('Token 可能过期，请重新获取 token.json', 'ERROR')
        sys.exit(1)

    # ── Step 2: eKYC 检查 ──
    log('检查实名认证 (eKYC)...')
    try:
        enter = nol.enter_info()
        ekyc = enter.get('enterEkyc', {})
        status = ekyc.get('status', 'unknown')
        log(f'eKYC 状态: {status}')

        if status != 'approved':
            log('⚠️  eKYC 未通过！请先在 NOL 网站完成实名认证', 'WARN')
            log('   步骤: 登录 NOL → 个人中心 → 实名认证 → 上传证件', 'WARN')
            log('   认证通过后重新运行此脚本', 'WARN')

            # 不退出，继续 — 到时间了可以重试
            log('继续运行，开售时会自动重试 eKYC...')
    except Exception as e:
        log(f'获取 enter 失败: {e}', 'ERROR')
        sys.exit(1)

    # ── Step 3: 售卖信息 ──
    log('获取售卖信息...')
    try:
        sales = nol.sales_info()
        si = sales['salesInfo']
        log(f'演出: {si["playStartDate"]} ~ {si["playEndDate"]}')
        log(f'一般开售: {si["bookingOpenTime"]} KST')
        log(f'状态: {"可售" if si["goodsStatus"] == "Y" else "不可售"}')

        for ps in sales.get('preSalesInfo', []):
            log(f'预售: {ps["preBookingKindName"]} {ps["bookingOpenTime"]} ~ {ps["bookingEndTime"]}')
    except Exception as e:
        log(f'获取售卖信息失败: {e}', 'ERROR')
        sys.exit(1)

    # ── Step 4: 确定目标时间 ──
    sale_time = parse_time(cfg['sale_time'])
    presale = cfg.get('presale_time')
    target = parse_time(presale) if presale else sale_time
    kind = '粉丝预售' if presale else '一般开售'

    remaining = (target - now_kst()).total_seconds()
    log(f'目标: {kind} {target.strftime("%Y-%m-%d %H:%M:%S")} KST')
    log(f'剩余: {remaining:.0f}s ({remaining/3600:.1f}h)')

    # ── Step 5: 等待开售 ──
    if remaining > 10:
        log(f'等待开售... (Ctrl+C 中断)')
        try:
            while True:
                now = now_kst()
                diff = (target - now).total_seconds()

                if diff <= 0:
                    break
                elif diff > 120:
                    # 每分钟检查一次
                    log(f'距开售 {diff/60:.0f} 分钟')
                    time.sleep(60)
                elif diff > 10:
                    log(f'距开售 {diff:.0f}s')
                    time.sleep(5)
                elif diff > 3:
                    log(f'⏱️  {diff:.1f}s')
                    time.sleep(0.5)
                else:
                    # 冲刺：忙等待
                    log(f'🚀 冲刺！{diff:.2f}s')
                    while now_kst() < target:
                        pass
                    break
        except KeyboardInterrupt:
            log('用户中断')
            return

    # ── Step 6: 刷新 token ──
    log('刷新 token...')
    if nol.try_refresh():
        log('Token 已刷新', 'OK')
    else:
        log('Token 刷新失败，用现有 token 继续', 'WARN')

    # ── Step 7: 重新获取 enter info ──
    log('获取购票凭证...')
    try:
        enter = nol.enter_info()
        ekyc_status = enter.get('enterEkyc', {}).get('status', 'unknown')
        log(f'eKYC: {ekyc_status}')

        if ekyc_status != 'approved':
            log(f'⚠️ eKYC 仍为 {ekyc_status}，尝试继续抢票...', 'WARN')
    except Exception as e:
        log(f'获取 enter 失败: {e}', 'ERROR')
        # 尝试用旧的 enter 数据

    # ── Step 8: 抢票 ──
    log('🎫 开始抢票！')
    notify(webhook, f'🚀 开始抢票! {kind}')

    dates = ['2026-06-12', '2026-06-13']
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
                        log(f'🎉🎉🎉 抢票成功！！！', 'SUCCESS')
                        log(f'日期: {date}  档位: #{grade_idx}')
                        log(f'响应: {result.get("body", "")[:300]}')
                        notify(webhook, f'🎉 抢票成功! {date} 档位#{grade_idx}')

                        # 保存结果
                        with open(STATE_FILE, 'w') as f:
                            json.dump({
                                'success': True,
                                'time': datetime.now().isoformat(),
                                'date': date,
                                'grade': grade_idx,
                                'result': result,
                            }, f, indent=2, ensure_ascii=False)
                        return

                    # 只在重试时打印
                    if attempt % 50 == 0 or attempt <= 5:
                        log(f'[{attempt}/{max_retries}] {date} grade#{grade_idx} → HTTP {result.get("status")}')

                except Exception as e:
                    if attempt % 100 == 0:
                        log(f'[{attempt}] 异常: {e}', 'WARN')

        time.sleep(delay)

    log('😢 抢票失败，已用尽所有重试', 'FAIL')
    notify(webhook, '😢 抢票失败')

    with open(STATE_FILE, 'w') as f:
        json.dump({'success': False, 'time': datetime.now().isoformat()}, f)


if __name__ == '__main__':
    main()
