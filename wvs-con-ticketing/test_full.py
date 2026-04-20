#!/usr/bin/env python3
"""完整测试：NOL 登录 + 页面访问 + 购买按钮检测"""
import os, sys, time, re

os.environ['FLASK_ENV'] = 'development'
os.environ['SECRET_KEY'] = 'test-secret-key-fixed'
os.environ['JWT_SECRET_KEY'] = 'test-jwt-key-fixed'
os.environ['DATA_ENCRYPT_KEY'] = 'test-encrypt-key-32bytes!!!!!!!'
os.environ['DATABASE_URL'] = 'sqlite:///test_wvs.db'

sys.path.insert(0, 'backend')

from playwright.sync_api import sync_playwright

EMAIL = 'gji24408@gmail.com'
PASSWORD = 'jg1901088217'
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

# 反检测
context.add_init_script("""
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    delete navigator.__proto__.webdriver;
""")

page = context.new_page()
page.set_default_timeout(20000)

# ============ STEP 1: 登录 ============
print('='*50)
print('🔐 STEP 1: 登录 NOL')
print('='*50)

try:
    page.goto('https://world.nol.com/zh-CN/auth-web/login', wait_until='domcontentloaded', timeout=30000)
    time.sleep(4)
    print(f'✅ 登录页面加载: {page.url}')
except Exception as e:
    print(f'⚠️ 登录页加载异常: {e}')

# 截图
os.makedirs('screenshots', exist_ok=True)
try:
    page.screenshot(path='screenshots/nol_login.png', full_page=False, timeout=10000)
    print('📸 登录页截图已保存')
except:
    pass

# 查找并填写邮箱
email_filled = False
for sel in ['input[name="email"]', 'input[type="email"]', 'input[placeholder*="邮箱"]', 'input[placeholder*="email"]', 'input[placeholder*="이메일"]']:
    try:
        page.fill(sel, EMAIL, timeout=3000)
        email_filled = True
        print(f'✅ 邮箱已填入: {sel}')
        break
    except:
        continue

if not email_filled:
    # 列出所有 input
    inputs = page.query_selector_all('input')
    print(f'⚠️ 未找到邮箱框，页面共 {len(inputs)} 个 input:')
    for i, inp in enumerate(inputs):
        try:
            attrs = {
                'type': inp.get_attribute('type'),
                'name': inp.get_attribute('name'),
                'placeholder': inp.get_attribute('placeholder'),
                'id': inp.get_attribute('id'),
            }
            print(f'   input[{i}]: {attrs}')
        except:
            pass

# 查找并填写密码
pw_filled = False
for sel in ['input[name="password"]', 'input[type="password"]', 'input[placeholder*="密码"]', 'input[placeholder*="password"]', 'input[placeholder*="비밀번호"]']:
    try:
        page.fill(sel, PASSWORD, timeout=3000)
        pw_filled = True
        print(f'✅ 密码已填入: {sel}')
        break
    except:
        continue

if not pw_filled:
    print('⚠️ 未找到密码框')

time.sleep(1)

# 点击登录
login_clicked = False
for sel in ['button[type="submit"]', 'button:has-text("登录")', 'button:has-text("Login")', 'button:has-text("로그인")', 'div[role="button"]:has-text("登录")']:
    try:
        page.click(sel, timeout=3000)
        login_clicked = True
        print(f'✅ 登录按钮已点击: {sel}')
        break
    except:
        continue

if not login_clicked:
    print('⚠️ 尝试按 Enter 提交...')
    page.keyboard.press('Enter')

time.sleep(8)

print(f'📍 当前URL: {page.url}')

if 'auth-web' not in page.url and 'login' not in page.url.lower():
    print('✅✅✅ 登录成功！！！')
    # 保存登录态
    state = context.storage_state()
    import json
    with open('state_nol.json', 'w') as f:
        json.dump(state, f)
    print('💾 登录态已保存: state_nol.json')
else:
    print('⚠️ 登录可能未完成，检查页面...')
    try:
        page.screenshot(path='screenshots/nol_login_result.png', full_page=False, timeout=10000)
        print('📸 登录结果截图已保存')
    except:
        pass
    # 检查是否有验证码
    content = page.content()
    if 'turnstile' in content.lower() or 'challenge' in content.lower():
        print('🔐 检测到 Cloudflare 验证码')
    # 检查错误信息
    for sel in ['.error', '.alert', '[class*="error"]', '[class*="Error"]']:
        try:
            el = page.query_selector(sel)
            if el:
                txt = el.inner_text()
                if txt.strip():
                    print(f'❌ 错误信息: {txt.strip()[:100]}')
        except:
            pass

# ============ STEP 2: 访问演出页面 ============
print()
print('='*50)
print('🎫 STEP 2: 访问演出页面')
print('='*50)

try:
    page.goto(URL, wait_until='domcontentloaded', timeout=30000)
    time.sleep(5)
    print(f'✅ 页面加载成功')
    print(f'📄 标题: {page.title()}')
    print(f'🔗 URL: {page.url}')
except Exception as e:
    print(f'⚠️ 页面加载异常: {e}')

content = page.content()

# 检查购买按钮
print()
print('--- 购买按钮检测 ---')
booking_texts = ['立即预订','预约购票','订票','立即购买','购买','Book','Buy','예매하기','立即预约','马上抢','选座购买']
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

    # 尝试点击购买按钮
    print()
    print('--- 尝试点击"立即购买" ---')
    for btn_text in ['立即购买', '购买', '立即预订']:
        try:
            page.locator(f'text={btn_text}').first.click(timeout=5000)
            print(f'✅ 已点击: {btn_text}')
            time.sleep(3)
            print(f'📍 点击后URL: {page.url}')

            # 检查是否进入选座/选票页面
            new_content = page.content()
            if any(k in new_content for k in ['选择座位', '选座', 'select seat', '좌석', '选择区域', '区域']):
                print('🎯 进入选座/选票页面！')

            # 检查是否有档位选择
            seat_kw = ['VIP','SR','R座','S座','A座','R석','S석','等级','席']
            found = [k for k in seat_kw if k in new_content]
            if found:
                print(f'💺 档位: {found}')

            try:
                page.screenshot(path='screenshots/nol_after_buy_click.png', full_page=False, timeout=10000)
                print('📸 点击后截图已保存')
            except:
                pass

            break
        except Exception as e:
            continue
else:
    print('ℹ️  未找到购买按钮')

# 座位/价格信息
print()
print('--- 票务信息 ---')
seat_kw = ['VIP','SR','R座','S座','A座','R석','S석','Restricted View','一般']
found = [k for k in seat_kw if k in content]
if found:
    print(f'💺 档位: {found}')

prices = re.findall(r'[\d,]+\s*(?:원|KRW|won)', content)
if prices:
    print(f'💰 价格: {prices}')

dates = re.findall(r'\d{4}年\d{1,2}月\d{1,2}日', content)
if not dates:
    dates = re.findall(r'\d{4}[-/.]\d{1,2}[-/.]\d{1,2}', content)
if dates:
    print(f'📅 日期: {dates[:5]}')

# 售罄检测
sold_out_kw = ['售罄','sold out','매진','품절','已结束','Sold Out']
if any(k in content.lower() for k in sold_out_kw):
    print('😢 检测到售罄/已结束')

browser.close()
pw.stop()
print('\n✅ 全部测试完成')
