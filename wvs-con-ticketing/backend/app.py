"""Flask 主应用"""

import os
import sys
import json

# 确保能导入同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, get_jwt_identity

from config import config_map
from models import db, User, Order, OrderLog, TicketClass, Account
from auth import login_required, admin_required
from routes.orders import orders_bp
from routes.admin import admin_bp

def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')

    _base = os.path.dirname(os.path.abspath(__file__))
    app = Flask(__name__, static_folder=os.path.join(_base, '..', 'frontend'), static_url_path='')
    app.config.from_object(config_map[config_name])

    # 确保目录存在
    os.makedirs(app.config.get('LOG_DIR', 'logs'), exist_ok=True)
    os.makedirs(app.config.get('SCREENSHOT_DIR', 'screenshots'), exist_ok=True)

    # 初始化扩展
    CORS(app)
    db.init_app(app)
    JWTManager(app)

    # 注册蓝图
    app.register_blueprint(orders_bp)
    app.register_blueprint(admin_bp)

    # ---- 认证 API ----

    @app.route('/api/auth/register', methods=['POST'])
    def register():
        data = request.get_json()
        if not data:
            return jsonify({'error': '请求体为空'}), 400

        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')

        if not username or not email or not password:
            return jsonify({'error': '请填写完整信息'}), 400
        if len(password) < 6:
            return jsonify({'error': '密码至少6位'}), 400

        if User.query.filter_by(username=username).first():
            return jsonify({'error': '用户名已存在'}), 409
        if User.query.filter_by(email=email).first():
            return jsonify({'error': '邮箱已注册'}), 409

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        token = create_access_token(identity=str(user.id))
        return jsonify({
            'message': '注册成功',
            'token': token,
            'user': user.to_dict(),
        }), 201

    @app.route('/api/auth/login', methods=['POST'])
    def login():
        data = request.get_json()
        if not data:
            return jsonify({'error': '请求体为空'}), 400

        username = data.get('username', '').strip()
        password = data.get('password', '')

        user = User.query.filter(
            (User.username == username) | (User.email == username)
        ).first()

        if not user or not user.check_password(password):
            return jsonify({'error': '用户名或密码错误'}), 401

        token = create_access_token(identity=str(user.id))
        return jsonify({
            'message': '登录成功',
            'token': token,
            'user': user.to_dict(),
        })

    @app.route('/api/auth/me', methods=['GET'])
    @login_required
    def get_me():
        user_id = int(get_jwt_identity())
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({'error': '用户不存在'}), 404
        return jsonify(user.to_dict())

    @app.route('/api/auth/profile', methods=['PUT'])
    @login_required
    def update_profile():
        user_id = int(get_jwt_identity())
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({'error': '用户不存在'}), 404

        data = request.get_json()
        if 'interpark_id' in data:
            user.interpark_id = data['interpark_id']
        if 'interpark_pw' in data:
            user.interpark_pw_encrypted = data['interpark_pw']
        if 'weverse_id' in data:
            user.weverse_id = data['weverse_id']
        if 'has_presale' in data:
            user.has_presale = bool(data['has_presale'])

        db.session.commit()
        return jsonify({'message': '更新成功', 'user': user.to_dict()})

    # ---- 座位配置 API ----

    @app.route('/api/ticket-classes', methods=['GET'])
    @login_required
    def list_ticket_classes():
        """获取座位档位列表"""
        order_id = request.args.get('order_id', type=int)
        q = TicketClass.query
        if order_id:
            q = q.filter_by(order_id=order_id)
        else:
            q = q.filter_by(order_id=None)
        classes = q.filter_by(is_visible=True).order_by(TicketClass.grade_index).all()
        return jsonify({'ticket_classes': [t.to_dict() for t in classes]})

    @app.route('/api/ticket-classes', methods=['POST'])
    @login_required
    def create_ticket_class():
        """创建座位档位"""
        data = request.get_json()
        if not data:
            return jsonify({'error': '请求体为空'}), 400

        tc = TicketClass(
            order_id=data.get('order_id'),
            name=data.get('name', ''),
            grade_index=data.get('grade_index', 0),
            price=data.get('price', 0),
            currency=data.get('currency', 'KRW'),
            ticket_per_person=data.get('ticket_per_person', 1),
            total_seats=data.get('total_seats', 0),
            available_seats=data.get('available_seats', data.get('total_seats', 0)),
            is_sold_out=data.get('is_sold_out', False),
            color=data.get('color', '#7c5cfc'),
            icon=data.get('icon', '🎫'),
        )
        db.session.add(tc)
        db.session.commit()
        return jsonify({'message': '创建成功', 'ticket_class': tc.to_dict()}), 201

    @app.route('/api/ticket-classes/<int:tc_id>', methods=['PUT'])
    @login_required
    def update_ticket_class(tc_id):
        """更新座位档位"""
        tc = db.session.get(TicketClass, tc_id)
        if not tc:
            return jsonify({'error': '档位不存在'}), 404

        data = request.get_json()
        updatable = ['name', 'price', 'ticket_per_person', 'total_seats',
                      'available_seats', 'is_sold_out', 'is_visible', 'color', 'icon']
        for key in updatable:
            if key in data:
                setattr(tc, key, data[key])

        db.session.commit()
        return jsonify({'message': '更新成功', 'ticket_class': tc.to_dict()})

    @app.route('/api/ticket-classes/<int:tc_id>', methods=['DELETE'])
    @login_required
    def delete_ticket_class(tc_id):
        """删除座位档位"""
        tc = db.session.get(TicketClass, tc_id)
        if not tc:
            return jsonify({'error': '档位不存在'}), 404
        db.session.delete(tc)
        db.session.commit()
        return jsonify({'message': '已删除'})

    # ---- 多账号管理 API ----

    @app.route('/api/accounts', methods=['GET'])
    @login_required
    def list_accounts():
        """获取用户的账号列表"""
        user_id = int(get_jwt_identity())
        order_id = request.args.get('order_id', type=int)
        q = Account.query.filter_by(user_id=user_id)
        if order_id:
            q = q.filter_by(order_id=order_id)
        accounts = q.order_by(Account.no).all()
        return jsonify({'accounts': [a.to_dict() for a in accounts]})

    @app.route('/api/accounts', methods=['POST'])
    @login_required
    def create_account():
        """添加账号"""
        user_id = int(get_jwt_identity())
        data = request.get_json()
        if not data:
            return jsonify({'error': '请求体为空'}), 400

        email = data.get('email', '').strip()
        password = data.get('password', '')
        if not email or not password:
            return jsonify({'error': '请填写邮箱和密码'}), 400

        # 自动计算序号
        order_id = data.get('order_id')
        max_no = db.session.query(db.func.max(Account.no)).filter_by(user_id=user_id).scalar() or 0

        account = Account(
            user_id=user_id,
            order_id=order_id,
            no=max_no + 1,
            email=email,
            password=password,
            proxy=data.get('proxy', ''),
            card_no=data.get('card_no', ''),
            card_cvv=data.get('card_cvv', ''),
            wrid=data.get('wrid', ''),
        )
        db.session.add(account)
        db.session.commit()
        return jsonify({'message': '账号已添加', 'account': account.to_dict()}), 201

    @app.route('/api/accounts/<int:acc_id>', methods=['PUT'])
    @login_required
    def update_account(acc_id):
        """更新账号"""
        user_id = int(get_jwt_identity())
        acc = Account.query.filter_by(id=acc_id, user_id=user_id).first()
        if not acc:
            return jsonify({'error': '账号不存在'}), 404

        data = request.get_json()
        updatable = ['email', 'password', 'proxy', 'card_no', 'card_cvv', 'wrid', 'status', 'order_id']
        for key in updatable:
            if key in data and data[key] is not None:
                setattr(acc, key, data[key])

        db.session.commit()
        return jsonify({'message': '更新成功', 'account': acc.to_dict()})

    @app.route('/api/accounts/<int:acc_id>', methods=['DELETE'])
    @login_required
    def delete_account(acc_id):
        """删除账号"""
        user_id = int(get_jwt_identity())
        acc = Account.query.filter_by(id=acc_id, user_id=user_id).first()
        if not acc:
            return jsonify({'error': '账号不存在'}), 404
        db.session.delete(acc)
        db.session.commit()
        return jsonify({'message': '已删除'})

    @app.route('/api/accounts/batch', methods=['POST'])
    @login_required
    def batch_create_accounts():
        """批量导入账号 (JSON 数组)"""
        user_id = int(get_jwt_identity())
        data = request.get_json()
        if not isinstance(data, list):
            return jsonify({'error': '需要账号数组'}), 400

        max_no = db.session.query(db.func.max(Account.no)).filter_by(user_id=user_id).scalar() or 0
        created = 0
        for item in data:
            if not item.get('email') or not item.get('password'):
                continue
            max_no += 1
            acc = Account(
                user_id=user_id,
                order_id=item.get('order_id'),
                no=max_no,
                email=item['email'],
                password=item['password'],
                proxy=item.get('proxy', ''),
                card_no=item.get('card_no', ''),
                card_cvv=item.get('card_cvv', ''),
                wrid=item.get('wrid', ''),
            )
            db.session.add(acc)
            created += 1

        db.session.commit()
        return jsonify({'message': f'导入 {created} 个账号'}), 201

    # ---- GetBlock API ----

    @app.route('/api/orders/<int:order_id>/get-block', methods=['POST'])
    @login_required
    def get_block_no(order_id):
        """获取票务区块编号"""
        user_id = int(get_jwt_identity())
        order = Order.query.filter_by(id=order_id, user_id=user_id).first()
        if not order:
            return jsonify({'error': '订单不存在'}), 404

        data = request.get_json() or {}
        goods_code = data.get('goods_code', order.goods_code)
        place_code = data.get('place_code', order.place_code)
        seat_mode = data.get('seat_mode', order.seat_mode)

        if not goods_code:
            return jsonify({'error': '请填写商品编码'}), 400

        # 更新订单
        order.goods_code = goods_code
        order.place_code = place_code
        order.seat_mode = seat_mode
        db.session.commit()

        # 模拟获取 blockNo（实际需对接 Interpark API）
        import hashlib
        block_hash = hashlib.md5(f"{goods_code}:{place_code}:{seat_mode}".encode()).hexdigest()[:8]
        order.block_no = block_hash
        db.session.commit()

        return jsonify({
            'message': '区块编号已获取',
            'block_no': block_hash,
            'goods_code': goods_code,
            'place_code': place_code,
            'seat_mode': seat_mode,
        })

    # ---- 钉钉通知 API ----

    @app.route('/api/orders/<int:order_id>/ding/init', methods=['POST'])
    @login_required
    def ding_init(order_id):
        """初始化钉钉通知"""
        user_id = int(get_jwt_identity())
        order = Order.query.filter_by(id=order_id, user_id=user_id).first()
        if not order:
            return jsonify({'error': '订单不存在'}), 404

        data = request.get_json() or {}
        webhook = data.get('webhook', '').strip()
        if not webhook:
            return jsonify({'error': '请填写钉钉 Webhook 地址'}), 400

        order.ding_webhook = webhook
        db.session.commit()

        # 发送测试消息
        try:
            import urllib.request
            import urllib.parse
            msg_data = json.dumps({
                'msgtype': 'text',
                'text': {'content': f'🎫 YAOLO 抢票系统已连接\n订单 #{order.id} 钉钉通知已启用'}
            }).encode('utf-8')
            req = urllib.request.Request(webhook, data=msg_data, headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=5)
            return jsonify({'message': '钉钉通知已初始化', 'webhook': webhook})
        except Exception as e:
            return jsonify({'message': f'Webhook 已保存，但测试发送失败: {e}', 'webhook': webhook})

    @app.route('/api/orders/<int:order_id>/ding/push', methods=['POST'])
    @login_required
    def ding_push(order_id):
        """推送钉钉通知"""
        user_id = int(get_jwt_identity())
        order = Order.query.filter_by(id=order_id, user_id=user_id).first()
        if not order:
            return jsonify({'error': '订单不存在'}), 404

        if not order.ding_webhook:
            return jsonify({'error': '未配置钉钉 Webhook'}), 400

        data = request.get_json() or {}
        message = data.get('message', f'订单 #{order.id} 状态: {order.status}')

        try:
            import urllib.request
            msg_data = json.dumps({
                'msgtype': 'text',
                'text': {'content': f'🎫 {message}'}
            }).encode('utf-8')
            req = urllib.request.Request(order.ding_webhook, data=msg_data, headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=5)
            return jsonify({'message': '通知已推送'})
        except Exception as e:
            return jsonify({'error': f'推送失败: {e}'}), 500

    # ---- 静态文件 ----

    @app.route('/')
    def index():
        return app.send_static_file('index.html')

    @app.route('/dashboard')
    def dashboard_page():
        return app.send_static_file('dashboard.html')

    @app.route('/admin')
    def admin_page():
        return app.send_static_file('admin.html')

    # ---- 健康检查 ----

    @app.route('/api/health')
    def health():
        return jsonify({'status': 'ok', 'service': 'wvs-con-ticketing'})

    # ---- 创建数据库 ----

    with app.app_context():
        db.create_all()

        # 创建默认管理员
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin_pw = os.environ.get('ADMIN_PASSWORD', 'admin123')
            admin = User(username='admin', email='admin@wvs.local', is_admin=True)
            admin.set_password(admin_pw)
            db.session.add(admin)
            db.session.commit()

        # 创建默认座位档位（如果不存在）
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
            db.session.commit()

    return app


if __name__ == '__main__':
    app = create_app()
    print("🎫 Weverse Con 2026 抢票系统启动")
    print("📡 http://localhost:5000")
    print("👤 管理员: admin / admin123")
    # 用 --no-reload 避免 debug reloader 导致 JWT secret 不一致
    use_reloader = os.environ.get('FLASK_RELOADER', 'true').lower() == 'true'
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=use_reloader)
