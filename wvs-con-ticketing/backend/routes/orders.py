"""订单 API 路由"""

import json
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import get_jwt_identity

from auth import login_required
from models import db, Order, OrderLog, User, TicketClass

orders_bp = Blueprint('orders', __name__, url_prefix='/api/orders')


@orders_bp.route('', methods=['GET'])
@login_required
def list_orders():
    """获取用户的订单列表"""
    user_id = int(get_jwt_identity())
    status_filter = request.args.get('status')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    query = Order.query.filter_by(user_id=user_id)
    if status_filter:
        query = query.filter_by(status=status_filter)

    query = query.order_by(Order.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'orders': [o.to_dict() for o in pagination.items],
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages,
    })


@orders_bp.route('', methods=['POST'])
@login_required
def create_order():
    """创建抢票订单"""
    user_id = int(get_jwt_identity())
    data = request.get_json()

    if not data:
        return jsonify({'error': '请求体为空'}), 400

    perf_url = data.get('perf_url', '').strip()
    if not perf_url:
        return jsonify({'error': '请填写演出 URL'}), 400

    open_time = data.get('open_time', '').strip()
    presale_time = data.get('presale_time', '').strip()
    if not open_time and not presale_time:
        return jsonify({'error': '请设置开售时间'}), 400

    seat_prefs = data.get('seat_prefs', [0, 1, 2, 3, 4])
    if isinstance(seat_prefs, str):
        try:
            seat_prefs = json.loads(seat_prefs)
        except Exception:
            seat_prefs = [0, 1, 2, 3, 4]

    order = Order(
        user_id=user_id,
        perf_url=perf_url,
        schedule_index=data.get('schedule_index', 0),
        schedule_label=data.get('schedule_label', 'Day 1'),
        seat_prefs=json.dumps(seat_prefs),
        open_time=open_time,
        presale_time=presale_time,
        is_presale=bool(presale_time),
        tab_count=data.get('tab_count', 4),
        proxy=data.get('proxy', ''),
        status='pending',
    )

    db.session.add(order)
    db.session.commit()

    log = OrderLog(order_id=order.id, level='INFO', message='订单已创建')
    db.session.add(log)
    db.session.commit()

    return jsonify({
        'message': '订单创建成功',
        'order': order.to_dict(),
    }), 201


@orders_bp.route('/<int:order_id>', methods=['GET'])
@login_required
def get_order(order_id):
    """获取订单详情"""
    user_id = int(get_jwt_identity())
    order = Order.query.filter_by(id=order_id, user_id=user_id).first()
    if not order:
        return jsonify({'error': '订单不存在'}), 404

    data = order.to_dict()
    data['logs'] = [l.to_dict() for l in order.logs[-50:]]
    return jsonify(data)


@orders_bp.route('/<int:order_id>', methods=['PUT'])
@login_required
def update_order(order_id):
    """更新订单配置（仅 pending 状态）"""
    user_id = int(get_jwt_identity())
    order = Order.query.filter_by(id=order_id, user_id=user_id).first()
    if not order:
        return jsonify({'error': '订单不存在'}), 404

    if order.status not in ('pending',):
        return jsonify({'error': f'当前状态({order.status})不可修改'}), 400

    data = request.get_json()
    updatable = ['perf_url', 'schedule_index', 'schedule_label', 'seat_prefs',
                 'open_time', 'presale_time', 'tab_count', 'proxy']

    for key in updatable:
        if key in data:
            val = json.dumps(data[key]) if key == 'seat_prefs' else data[key]
            setattr(order, key, val)

    if data.get('presale_time'):
        order.is_presale = True

    db.session.commit()
    return jsonify({'message': '更新成功', 'order': order.to_dict()})


@orders_bp.route('/<int:order_id>', methods=['DELETE'])
@login_required
def delete_order(order_id):
    """删除订单"""
    user_id = int(get_jwt_identity())
    order = Order.query.filter_by(id=order_id, user_id=user_id).first()
    if not order:
        return jsonify({'error': '订单不存在'}), 404

    if order.status in ('grabbing',):
        return jsonify({'error': '抢票中无法删除'}), 400

    OrderLog.query.filter_by(order_id=order_id).delete()
    db.session.delete(order)
    db.session.commit()
    return jsonify({'message': '已删除'})


@orders_bp.route('/<int:order_id>/start', methods=['POST'])
@login_required
def start_grabber(order_id):
    """手动启动抢票"""
    user_id = int(get_jwt_identity())
    order = Order.query.filter_by(id=order_id, user_id=user_id).first()
    if not order:
        return jsonify({'error': '订单不存在'}), 404

    if order.status not in ('pending', 'failed', 'error'):
        return jsonify({'error': f'当前状态({order.status})无法启动'}), 400

    user = db.session.get(User, user_id)

    # 加载座位档位配置
    ticket_classes = TicketClass.query.filter(
        (TicketClass.order_id == order_id) | (TicketClass.order_id == None)
    ).filter_by(is_visible=True).order_by(TicketClass.grade_index).all()

    seat_prefs = json.loads(order.seat_prefs) if order.seat_prefs else [0, 1, 2, 3, 4]
    tc_map = {tc.grade_index: tc.to_dict() for tc in ticket_classes}

    config = {
        'perf_url': order.perf_url,
        'schedule_index': order.schedule_index,
        'seat_prefs': seat_prefs,
        'tab_count': order.tab_count,
        'headless': True,
        'page_timeout': 10000,
        'max_click_retries': 100,
        'click_delay': 0.05,
        'pre_open_sec': 3,
        'proxy': order.proxy,
        'interpark_id': user.interpark_id if user else '',
        'interpark_pw': user.interpark_pw_encrypted if user else '',
        'presale_time': order.presale_time,
        'ticket_classes': tc_map,
    }

    target_time = None
    time_str = order.presale_time or order.open_time
    if time_str:
        try:
            if len(time_str) <= 8:
                target_time = datetime.strptime(f"{datetime.now():%Y-%m-%d} {time_str}", '%Y-%m-%d %H:%M:%S')
            else:
                target_time = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return jsonify({'error': '时间格式错误，需要 YYYY-MM-DD HH:MM:SS'}), 400

    import threading
    order.status = 'grabbing'
    db.session.commit()

    def run_in_thread():
        from grabber.engine import GrabberEngine
        engine = GrabberEngine(order_id, config, db.session)
        engine.run(target_time)

    t = threading.Thread(target=run_in_thread, daemon=True)
    t.start()
    return jsonify({'message': '抢票已启动', 'target_time': str(target_time) if target_time else 'immediate'})


@orders_bp.route('/<int:order_id>/logs', methods=['GET'])
@login_required
def get_order_logs(order_id):
    """获取订单日志"""
    user_id = int(get_jwt_identity())
    order = Order.query.filter_by(id=order_id, user_id=user_id).first()
    if not order:
        return jsonify({'error': '订单不存在'}), 404

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    logs = OrderLog.query.filter_by(order_id=order_id) \
        .order_by(OrderLog.created_at.desc()) \
        .paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'logs': [l.to_dict() for l in logs.items],
        'total': logs.total,
    })
