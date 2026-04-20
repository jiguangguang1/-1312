#!/usr/bin/env python3
"""拦截 NOL 购票全流程 API 请求"""
import json, time, os, sys
from playwright.sync_api import sync_playwright

TOKEN = sys.argv[1] if len(sys.argv) > 1 else ''
REFRESH = sys.argv[2] if len(sys.argv) > 2 else ''
DEVICE_ID = 'e9a1fa77-ed52-4740-b152-3528364236a0'
URL = 'https://world.nol.com/zh-CN/ticket/places/24000240/products/26001295'

if not TOKEN:
    print('用法: python3 intercept_api.py <access_token> [refresh_token]')
    sys.exit(1)

pw = sync_playwright().start()
browser = pw.chromium.launch(headless=True, args=['--no-sandbox','--disable-dev-shm-usage'], channel='chromium')
context = browser.new_context(
    viewport={'width': 1366, 'height': 768},
    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale='zh-CN', timezone_id='Asia/Shanghai', ignore_https_errors=True,
)

cookies = [
    {'name': 'access_token', 'value': TOKEN, 'domain': 'world.nol.com', 'path': '/', 'httpOnly': True, 'secure': True},
    {'name': 'kint5-web-device-id', 'value': DEVICE_ID, 'domain': 'world.nol.com', 'path': '/'},
    {'name': 'tk-language', 'value': 'zh-CN', 'domain': 'world.nol.com', 'path': '/'},
]
if REFRESH:
    cookies.append({'name': 'refresh_token', 'value': REFRESH, 'domain': 'world.nol.com', 'path': '/', 'httpOnly': True, 'secure': True})
context.add_cookies(cookies)
context.add_init_script(f'Object.defineProperty(navigator,"webdriver",{{get:()=>undefined}});localStorage.setItem("access_token","{TOKEN}");')

page = context.new_page()
page.set_default_timeout(20000)

# 拦截所有 API 请求
api_log = []
def on_request(req):
    u = req.url
    if '/api/' in u:
        entry = {'method': req.method, 'url': u, 'headers': {k:v for k,v in req.headers.items() if k.lower() in ('authorization','content-type','accept')}, 'post_data': None}
        try:
            pd = req.post_data
            if pd:
                entry['post_data'] = pd[:500]
        except:
            pass
        api_log.append(entry)

resp_log = []
def on_response(resp):
    u = resp.url
    if '/api/' in u:
        body = None
        try:
            body = resp.text()[:2000]
        except:
            body = '(无法读取)'
        resp_log.append({'url': u, 'status': resp.status, 'body': body})

page.on('request', on_request)
page.on('response', on_response)

os.makedirs('screenshots', exist_ok=True)

# Step 1: 加载页面
print('🌐 加载演出页面...')
page.goto(URL, wait_until='domcontentloaded', timeout=30000)
time.sleep(5)
print(f'✅ {page.title()}')
print(f'📍 URL: {page.url}')

if 'login' in page.url.lower():
    print('❌ 被重定向到登录页，token 无效')
    browser.close()
    pw.stop()
    sys.exit(1)

print(f'\n📡 初始加载捕获 {len(resp_log)} 个 API 响应:')
for r in resp_log:
    if 'world.nol.com/api' in r['url']:
        print(f'  [{r["status"]}] {r["url"]}')
        try:
            body = json.loads(r['body'])
            print(f'       → {json.dumps(body, ensure_ascii=False)[:300]}')
        except:
            print(f'       → {r["body"][:200]}')

# Step 2: 点击购买按钮
print('\n--- 点击"立即购买" ---')
api_log.clear()
resp_log.clear()

btn = page.locator('text=立即购买').first
btn.click(timeout=5000)
time.sleep(5)

print(f'📍 点击后URL: {page.url}')
print(f'📡 捕获 {len(resp_log)} 个新 API 响应:')
for r in resp_log:
    print(f'  [{r["status"]}] {r["url"]}')
    try:
        body = json.loads(r['body'])
        print(f'       → {json.dumps(body, ensure_ascii=False)[:500]}')
    except:
        print(f'       → {r["body"][:200]}')

# 检查弹窗
for sel in ['[role=dialog]', '.modal', '.popup', '.MuiDialog-root', '[class*=modal]', '[class*=Modal]', '[class*=dialog]']:
    try:
        els = page.query_selector_all(sel)
        for el in els:
            if el.is_visible():
                txt = el.inner_text()[:500]
                print(f'\n🪟 弹窗 [{sel}]:\n{txt}')
    except:
        pass

# 检查 iframe
for f in page.frames:
    if f != page.main_frame:
        print(f'\n🖼️ iframe: {f.url}')
        try:
            txt = f.inner_text('body')[:500]
            print(f'   内容: {txt}')
        except:
            pass

page.screenshot(path='screenshots/nol_intercept.png', full_page=False, timeout=10000)
print('\n📸 截图已保存')

# Step 3: 如果进入了选票页面，继续操作
body_text = page.inner_text('body')
if any(k in body_text for k in ['选择日期', '选择场次', 'select date', '날짜', 'Select']):
    print('\n--- 检测到日期选择器 ---')
    api_log.clear()
    resp_log.clear()

    # 尝试选第一个日期
    for sel in ['.date_item', '.calendar td.available', '.day:not(.disabled)', 'button[class*=date]', '[class*=DateItem]']:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                print(f'✅ 选日期: {sel}')
                time.sleep(3)
                break
        except:
            continue

    print(f'📡 日期选择后捕获 {len(resp_log)} 个 API:')
    for r in resp_log:
        print(f'  [{r["status"]}] {r["url"]}')
        try:
            body = json.loads(r['body'])
            print(f'       → {json.dumps(body, ensure_ascii=False)[:500]}')
        except:
            pass

# Step 4: 尝试选档位
if any(k in body_text for k in ['R座', 'S座', 'VIP', '等级', '选择']):
    print('\n--- 尝试选档位 ---')
    api_log.clear()
    resp_log.clear()

    for sel in ['text=R座', 'text=S座', 'text=70,000', 'text=50,000', '[class*=grade]', '[class*=Grade]']:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=1000):
                el.click(timeout=3000)
                print(f'✅ 点击: {sel}')
                time.sleep(3)
                break
        except:
            continue

    print(f'📡 档位选择后捕获 {len(resp_log)} 个 API:')
    for r in resp_log:
        print(f'  [{r["status"]}] {r["url"]}')
        try:
            body = json.loads(r['body'])
            print(f'       → {json.dumps(body, ensure_ascii=False)[:500]}')
        except:
            pass

# 输出所有请求的 URL 列表
print('\n\n========== 完整 API 请求清单 ==========')
for entry in api_log:
    print(f'{entry["method"]} {entry["url"]}')
    if entry.get('headers'):
        print(f'  Headers: {entry["headers"]}')
    if entry.get('post_data'):
        print(f'  Body: {entry["post_data"][:300]}')

browser.close()
pw.stop()
print('\n✅ 拦截完成')
