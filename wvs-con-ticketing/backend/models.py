"""数据库模型"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model):
    """用户"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Interpark 凭证 (加密存储)
    interpark_id = db.Column(db.String(200), default='')
    interpark_pw_encrypted = db.Column(db.String(500), default='')
    weverse_id = db.Column(db.String(200), default='')
    has_presale = db.Column(db.Boolean, default=False)

    orders = db.relationship('Order', backref='user', lazy=True)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'is_admin': self.is_admin,
            'has_presale': self.has_presale,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Order(db.Model):
    """抢票订单"""
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # 演出信息
    perf_url = db.Column(db.String(500), default='')
    schedule_index = db.Column(db.Integer, default=0)
    schedule_label = db.Column(db.String(100), default='Day 1')

    # 座位偏好 [0=VIP站, 1=VIP坐, 2=SR, 3=R, 4=S, 5=A]
    seat_prefs = db.Column(db.String(100), default='[0,1,2,3,4]')

    # 时间配置
    open_time = db.Column(db.String(50), default='')
    presale_time = db.Column(db.String(50), default='')
    is_presale = db.Column(db.Boolean, default=False)

    # 并发配置
    tab_count = db.Column(db.Integer, default=4)

    # 代理
    proxy = db.Column(db.String(200), default='')

    # 状态
    status = db.Column(db.String(30), default='pending')
    # pending -> waiting -> grabbing -> success / failed / sold_out / error

    # 结果
    order_no = db.Column(db.String(100), default='')
    grabber_tab = db.Column(db.Integer, default=0)
    result_detail = db.Column(db.Text, default='')

    # 截图
    screenshot_path = db.Column(db.String(300), default='')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    logs = db.relationship('OrderLog', backref='order', lazy=True, order_by='OrderLog.created_at')
    ticket_classes = db.relationship('TicketClass', backref='order', lazy=True)

    def to_dict(self):
        import json
        seat = []
        try:
            seat = json.loads(self.seat_prefs)
        except Exception:
            pass
        return {
            'id': self.id,
            'user_id': self.user_id,
            'perf_url': self.perf_url,
            'schedule_index': self.schedule_index,
            'schedule_label': self.schedule_label,
            'seat_prefs': seat,
            'open_time': self.open_time,
            'presale_time': self.presale_time,
            'is_presale': self.is_presale,
            'tab_count': self.tab_count,
            'status': self.status,
            'order_no': self.order_no,
            'result_detail': self.result_detail,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class OrderLog(db.Model):
    """订单日志"""
    __tablename__ = 'order_logs'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    level = db.Column(db.String(10), default='INFO')
    message = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'level': self.level,
            'message': self.message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class TicketClass(db.Model):
    """座位档位配置 — 从平台抓取或手动录入"""
    __tablename__ = 'ticket_classes'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)
    # 关联订单，NULL 表示全局预设

    name = db.Column(db.String(100), default='')          # 如 "VIP 站席", "SR석"
    grade_index = db.Column(db.Integer, default=0)        # 平台编号 (0-based)
    price = db.Column(db.Integer, default=0)              # 韩元票价
    currency = db.Column(db.String(10), default='KRW')
    ticket_per_person = db.Column(db.Integer, default=1)  # 每人限购
    total_seats = db.Column(db.Integer, default=0)        # 总座位数
    available_seats = db.Column(db.Integer, default=0)    # 剩余座位
    is_sold_out = db.Column(db.Boolean, default=False)
    is_visible = db.Column(db.Boolean, default=True)      # 是否在前端展示

    # 外观
    color = db.Column(db.String(20), default='#7c5cfc')   # 档位颜色
    icon = db.Column(db.String(10), default='🎫')         # 图标

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'name': self.name,
            'grade_index': self.grade_index,
            'price': self.price,
            'currency': self.currency,
            'ticket_per_person': self.ticket_per_person,
            'total_seats': self.total_seats,
            'available_seats': self.available_seats,
            'is_sold_out': self.is_sold_out,
            'is_visible': self.is_visible,
            'color': self.color,
            'icon': self.icon,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class SystemStatus(db.Model):
    """系统状态"""
    __tablename__ = 'system_status'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, default='')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
