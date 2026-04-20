#!/usr/bin/env python3
"""
NOL 抢票 v3 — 命令行入口
python3 grabber.py [grab|check|monitor|test]
"""

import json
import sys
import logging
from pathlib import Path
from datetime import datetime
from core import NOLGrabber, NOLAccount, SaleWaiter, Status, Notifier

BASE = Path(__file__).parent
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('nol.cli')


def load():
    with open(BASE / 'config.json') as f:
        cfg = json.load(f)
    accounts = []
    tok_path = BASE / 'tokens.json'
    if tok_path.exists():
        with open(tok_path) as f:
            for td in json.load(f):
                if td.get('enabled', True) and td.get('access_token'):
                    accounts.append(NOLAccount(td, td.get('label', '')))
    return cfg, accounts


def cmd_check(cfg, accounts):
    print('\n🔍 账号检查')
    print('=' * 50)
    for a in accounts:
        a.set_referer(cfg['goods_code'], cfg['place_code'])
        try:
            user = a.user_info()
            print(f'  ✅ {a.label}: {user.get("name")} ({user.get("email")})')

            enter = a.enter_info(cfg['goods_code'], cfg['place_code'])
            ekyc = enter.get('enterEkyc', {}).get('status', '?')
            print(f'     eKYC: {ekyc}')
        except Exception as e:
            print(f'  ❌ {a.label}: {e}')

    grabber = NOLGrabber(cfg, accounts)
    try:
        sales = grabber.get_sales_info()
        si = sales['salesInfo']
        print(f'\n📅 演出: {si["playStartDate"]} ~ {si["playEndDate"]}')
        print(f'   开售: {si["bookingOpenTime"]} KST')
        print(f'   状态: {"可售" if si["goodsStatus"]=="Y" else "不可售"}')
        for ps in sales.get('preSalesInfo', []):
            print(f'   🎫 预售: {ps["preBookingKindName"]} {ps["bookingOpenTime"]}')
    except Exception as e:
        print(f'\n❌ 售卖信息失败: {e}')


def cmd_grab(cfg, accounts):
    print('\n🎫 抢票模式')
    print('=' * 50)

    grabber = NOLGrabber(cfg, accounts)

    # 检查
    for a in accounts:
        a.set_referer(cfg['goods_code'], cfg['place_code'])
        try:
            enter = a.enter_info(cfg['goods_code'], cfg['place_code'])
            ekyc = enter.get('enterEkyc', {}).get('status', '?')
            print(f'  {a.label}: eKYC={ekyc}')
        except Exception as e:
            print(f'  {a.label}: ❌ {e}')

    # 等待
    target = grabber.parse_time(cfg['sale_time'])
    if cfg.get('presale_time'):
        target = grabber.parse_time(cfg['presale_time'])

    waiter = SaleWaiter(target, cfg.get('pre_seconds', 2), lambda m: print(f'  {m}'))
    waiter.wait()

    # 刷新 token
    for a in accounts:
        if a.refresh_token():
            print(f'  ✅ {a.label}: Token已刷新')

    # 抢
    result = grabber.grab()
    if result.success:
        print(f'\n🎉 成功! {result.date} 档位#{result.grade} {result.attempts}次')
    else:
        print(f'\n😢 失败 {result.attempts}次')


def cmd_monitor(cfg, accounts):
    print('\n👁️ 监控模式')
    print('=' * 50)

    grabber = NOLGrabber(cfg, accounts)
    notifier = Notifier(cfg)
    interval = cfg.get('monitor_interval', 30)

    import time
    last = None
    while True:
        try:
            sales = grabber.get_sales_info()
            si = sales['salesInfo']
            status = si['goodsStatus']

            if status != last:
                print(f'  [{datetime.now():%H:%M:%S}] 状态: {last} → {status}')
                if status == 'Y':
                    notifier.send('🟢 票务开放!')
                last = status

            # 检查预售/开售时间
            from core import API_BASE
            import requests
            target = grabber.parse_time(cfg['sale_time'])
            diff = (target - grabber.now()).total_seconds()
            if 0 < diff < 120:
                print(f'  ⏰ 开售倒计时: {diff:.0f}s')
            elif -300 < diff < 0:
                notifier.send('🚨 已开售!')

        except Exception as e:
            print(f'  ⚠️ {e}')

        time.sleep(interval)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'check'
    cfg, accounts = load()

    if not accounts:
        print('❌ 没有可用账号，请配置 tokens.json')
        return

    cmds = {'check': cmd_check, 'grab': cmd_grab, 'monitor': cmd_monitor}
    if mode in cmds:
        cmds[mode](cfg, accounts)
    else:
        print(f'用法: python3 grabber.py [{"|".join(cmds.keys())}]')


if __name__ == '__main__':
    main()
