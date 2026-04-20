"""管理员 API 路由"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity

from auth import admin_required
from models import db, User, Order, OrderLog, SystemStatus, TicketClass

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

MAX_PER_PAGE = 100


@admin_bp.route('/dashboard', methods=['GET'])
@admin_required
def dashboard():
    total_users = User.query.count()
    total_orders = Order.query.count()
    pending = Order.query.filter_by(status='pending').count()
    grabbing = Order.query.filter_by(status='grabbing').count()
    success = Order.query.filter_by(status='success').count()
    failed = Order.query.filter_by(status='failed').count() + Order.query.filter_by(status='error').count()
    sold_out = Order.query.filter_by(status='sold_out').count()

    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()

    return jsonify({
        'stats': {
            'total_users': total_users,
            'total_orders': total_orders,
            'pending': pending,
            'grabbing': grabbing,
            'success': success,
            'failed': failed,
            'sold_out': sold_out,
        },
        'recent_orders': [o.to_dict() for o in recent_orders],
    })


@admin_bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), MAX_PER_PAGE)

    users = User.query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'users': [u.to_dict() for u in users.items],
        'total': users.total,
        'page': page,
        'pages': users.pages,
    })


@admin_bp.route('/orders', methods=['GET'])
@admin_required
def list_all_orders():
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), MAX_PER_PAGE)
    status = request.args.get('status')

    query = Order.query
    if status:
        query = query.filter_by(status=status)

    orders = query.order_by(Order.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        'orders': [o.to_dict() for o in orders.items],
        'total': orders.total,
        'page': page,
        'pages': orders.pages,
    })


@admin_bp.route('/orders/<int:order_id>/status', methods=['PUT'])
@admin_required
def update_order_status(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({'error': '订单不存在'}), 404

    data = request.get_json()
    new_status = data.get('status')
    if new_status not in ('pending', 'waiting', 'grabbing', 'success', 'failed', 'sold_out', 'error'):
        return jsonify({'error': '无效状态'}), 400

    order.status = new_status
    if data.get('order_no'):
        order.order_no = data['order_no']
    if data.get('result_detail'):
        order.result_detail = data['result_detail']

    db.session.commit()

    log = OrderLog(order_id=order_id, level='ADMIN', message=f'状态手动更新为: {new_status}')
    db.session.add(log)
    db.session.commit()

    return jsonify({'message': '状态已更新', 'order': order.to_dict()})


@admin_bp.route('/system/config', methods=['GET'])
@admin_required
def get_system_config():
    configs = SystemStatus.query.all()
    return jsonify({c.key: c.value for c in configs})


@admin_bp.route('/system/config', methods=['PUT'])
@admin_required
def update_system_config():
    data = request.get_json()
    for key, value in data.items():
        config = SystemStatus.query.filter_by(key=key).first()
        if config:
            config.value = str(value)
        else:
            db.session.add(SystemStatus(key=key, value=str(value)))
    db.session.commit()
    return jsonify({'message': '配置已更新'})


@admin_bp.route('/ticket-classes', methods=['GET'])
@admin_required
def list_all_ticket_classes():
    classes = TicketClass.query.order_by(TicketClass.grade_index).all()
    return jsonify({'ticket_classes': [t.to_dict() for t in classes]})


@admin_bp.route('/ticket-classes/<int:tc_id>/status', methods=['PUT'])
@admin_required
def update_ticket_class_status(tc_id):
    tc = db.session.get(TicketClass, tc_id)
    if not tc:
        return jsonify({'error': '档位不存在'}), 404
    data = request.get_json()
    if 'is_sold_out' in data:
        tc.is_sold_out = bool(data['is_sold_out'])
    if 'available_seats' in data:
        tc.available_seats = int(data['available_seats'])
    if 'is_visible' in data:
        tc.is_visible = bool(data['is_visible'])
    db.session.commit()
    return jsonify({'message': '状态已更新', 'ticket_class': tc.to_dict()})
