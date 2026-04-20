#!/usr/bin/env python3
"""测试运行抢票引擎 — 测试登录+页面访问，不会真正下单"""
import os
import sys
import time

os.environ['FLASK_ENV'] = 'development'
os.environ['SECRET_KEY'] = 'test-secret-key-fixed'
os.environ['JWT_SECRET_KEY'] = 'test-jwt-key-fixed'
os.environ['DATA_ENCRYPT_KEY'] = 'test-encrypt-key-32bytes!!!!!!!'
os.environ['DATABASE_URL'] = 'sqlite:///test_wvs.db'

sys.path.insert(0, 'backend')

from app import create_app
from models import db, User, Order

app = create_app()

with app.app_context():
    db.create_all()

    user = User.query.filter_by(username='testrunner').first()
    if not user:
        user = User(username='testrunner', email='test@runner.com', is_admin=False)
        user.set_password('test123456')
        db.session.add(user)
        db.session.commit()
    
    user.interpark_id = 'gji24408@Gmail.com'
    user.set_interpark_pw('jg1901088217')
    db.session.commit()
    print(f'✅ 用户: {user.username}')

    order = Order(
        user_id=user.id,
        perf_url='https://world.nol.com/zh-CN/ticket/places/26000402/products/26006000',
        schedule_index=0,
        schedule_label='Day 1',
        seat_prefs='[0,1,2,3,4]',
        open_time='',
        presale_time='',
        tab_count=1,
        status='pending',
    )
    db.session.add(order)
    db.session.commit()
    print(f'✅ 订单: #{order.id}')

    config = {
        'perf_url': order.perf_url,
        'schedule_index': 0,
        'seat_prefs': [0, 1, 2, 3, 4],
        'tab_count': 1,
        'headless': True,
        'page_timeout': 15000,
        'max_click_retries': 30,
        'click_delay': 0.1,
        'pre_open_sec': 3,
        'proxy': '',
        'interpark_id': user.interpark_id,
        'interpark_pw': user.get_interpark_pw(),
        'presale_time': '',
        'ticket_classes': {},
    }

    print()
    print('=' * 50)
    print('🚀 启动引擎测试...')
    print(f'📄 URL: {config["perf_url"]}')
    print(f'👤 账号: {config["interpark_id"]}')
    print('=' * 50)

    from grabber.engine import GrabberEngine
    engine = GrabberEngine(order.id, config)

    try:
        engine.start_browser()
        print('✅ 浏览器启动成功')

        login_ok = engine.login()
        if login_ok:
            print('✅ 登录成功！')
        else:
            print('⚠️ 登录未自动完成')

        page = engine.new_page()
        print(f'📄 访问: {config["perf_url"]}')
        try:
            page.goto(config['perf_url'], wait_until='domcontentloaded', timeout=20000)
            time.sleep(3)
            print(f'✅ 页面加载: {page.url}')
            title = page.title()
            print(f'📝 标题: {title}')

            engine._shot(page, 'test')
            print('📸 截图已保存')

            content = page.content()
            # 检查关键元素
            for sel in ['text=예매', 'text=구매', 'text=Buy', 'text=立即购买',
                        'text=购票', '.btn_booking', '#btnBooking', 'button']:
                try:
                    els = page.query_selector_all(sel)
                    if els:
                        texts = []
                        for el in els[:5]:
                            try:
                                t = el.inner_text()
                                if t.strip():
                                    texts.append(t.strip()[:40])
                            except:
                                pass
                        if texts:
                            print(f'🔍 [{sel}]: {texts}')
                except:
                    pass

        except Exception as e:
            print(f'❌ 页面错误: {e}')

    except Exception as e:
        print(f'❌ 引擎异常: {e}')
        import traceback
        traceback.print_exc()
    finally:
        engine.close_browser()
        print('\n🏁 测试结束')
