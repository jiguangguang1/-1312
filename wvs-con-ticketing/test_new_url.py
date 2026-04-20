#!/usr/bin/env python3
"""测试 NOL 页面 — 新链接（快速版）"""
import os, sys, time, re

os.environ['FLASK_ENV'] = 'development'
os.environ['SECRET_KEY'] = 'test-secret-key-fixed'
os.environ['JWT_SECRET_KEY'] = 'test-jwt-key-fixed'
os.environ['DATA_ENCRYPT_KEY'] = 'test-encrypt-key-32bytes!!!!!!!'
os.environ['DATABASE_URL'] = 'sqlite:///test_wvs.db'

sys.path.insert(0, 'backend')

from playwright.sync_api import sync_playwright

URL = 'https://world.nol.com/zh-CN/ticket/places/24000240/products/26001295'

pw = sync_playwright().start()
browser = pw.chromium.launch(headless=True, args=['--no-sandbox','--disable-dev-shm-usage'], channel='chromium')
context = browser.new_context(
    viewport={'width': 1366, 'height': 768},
    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale='zh-CN',
    timezone_id='Asia/Shanghai',
    ignore_https_errors=True,
)
page = context.new_page()

print(f'🌐 正在打开: {URL}')
try:
    page.goto(URL, wait_until='domcontentloaded', timeout=30000)
    print('✅ 页面加载成功')
except Exception as e:
    print(f'⚠️ 页面加载异常: {e}')

time.sleep(5)

title = page.title()
print(f'📄 标题: {title}')
print(f'🔗 URL: {page.url}')

# 截图（非全页，避免字体加载超时）
os.makedirs('screenshots', exist_ok=True)
try:
    page.screenshot(path='screenshots/nol_new_url.png', full_page=False, timeout=10000)
    print('📸 截图已保存')
except Exception as e:
    print(f'⚠️ 截图跳过: {e}')

content = page.content()

# 检查购买按钮
booking_texts = ['立即预订','预约购票','订票','立即购买','购买','Book','Buy','예매하기','立即预约','马上抢']
found_buttons = []
for t in booking_texts:
    try:
        el = page.locator(f'text={t}').first
        if el.is_visible(timeout=500):
            found_buttons.append(t)
    except:
        pass
if found_buttons:
    print(f'🛒 找到购买按钮: {found_buttons}')
else:
    print('ℹ️  未找到购买按钮（可能未开售）')

# 检查座位关键词
seat_kw = ['VIP','SR','R석','S석','A석','站席','坐席','SEAT','Seat','等级','席']
found = [k for k in seat_kw if k in content]
if found:
    print(f'💺 座位关键词: {found}')

# 价格
prices = re.findall(r'[\d,]+\s*(?:원|KRW|¥|CNY|USD)', content)
if prices:
    print(f'💰 价格: {prices[:5]}')

# 日期
dates = re.findall(r'\d{4}[-/.]\d{1,2}[-/.]\d{1,2}', content)
if dates:
    print(f'📅 日期: {dates[:5]}')

# 售罄检测
sold_out_kw = ['售罄','sold out','매진','품절','已结束','Sold Out']
if any(k in content.lower() for k in sold_out_kw):
    print('😢 检测到售罄/已结束')

# 检查演出日期时间信息
time_patterns = re.findall(r'\d{1,2}:\d{2}', content)
if time_patterns:
    print(f'⏰ 时间: {time_patterns[:5]}')

# 检查场馆信息
venue_kw = ['场馆','地点','venue','홀','극장','THEATER','Theater','Arena']
found_venue = [k for k in venue_kw if k.lower() in content.lower()]
if found_venue:
    print(f'🏟️ 场馆关键词: {found_venue}')

# 页面文本摘要
try:
    text = page.inner_text('body')
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    print(f'\n📝 页面内容摘要（前50行）:')
    for line in lines[:50]:
        print(f'   {line[:120]}')
except Exception as e:
    print(f'文本提取失败: {e}')

browser.close()
pw.stop()
print('\n✅ 测试完成')
