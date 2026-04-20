"""数据库初始化脚本"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import db, User, TicketClass

app = create_app()

with app.app_context():
    db.create_all()

    # 创建管理员账号
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin_pw = os.environ.get('ADMIN_PASSWORD', 'admin123')
        admin = User(username='admin', email='admin@wvs.local', is_admin=True)
        admin.set_password(admin_pw)
        db.session.add(admin)
        print(f"✅ 创建管理员账号: admin / {admin_pw}")
    else:
        print("ℹ️ 管理员已存在")

    # 创建默认座位档位
    if TicketClass.query.filter_by(order_id=None).count() == 0:
        defaults = [
            {'name': 'VIP 站席', 'grade_index': 0, 'price': 154000, 'color': '#ef4444', 'icon': '🔥'},
            {'name': 'VIP 坐席', 'grade_index': 1, 'price': 154000, 'color': '#f97316', 'icon': '👑'},
            {'name': 'SR석', 'grade_index': 2, 'price': 132000, 'color': '#eab308', 'icon': '⭐'},
            {'name': 'R석', 'grade_index': 3, 'price': 99000, 'color': '#22c55e', 'icon': '💎'},
            {'name': 'S석', 'grade_index': 4, 'price': 110000, 'color': '#3b82f6', 'icon': '🎵'},
            {'name': 'A석', 'grade_index': 5, 'price': 88000, 'color': '#8b5cf6', 'icon': '🎶'},
        ]
        for d in defaults:
            db.session.add(TicketClass(**d, order_id=None))
        print("✅ 创建默认座位档位")
    else:
        print("ℹ️ 座位档位已存在")

    db.session.commit()
    print("✅ 数据库初始化完成")
