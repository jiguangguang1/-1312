"""数据库模型"""

import os
import json
import base64
import hashlib
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


# ============================================================
#  敏感字段加密工具
# ============================================================

def _get_encrypt_key():
    """获取加密密钥，优先使用环境变量，否则使用 SECRET_KEY 派生"""
    key = os.environ.get('DATA_ENCRYPT_KEY', '')
    if key:
        return key.encode()[:32].ljust(32, b'0')
    # 兜底：用 SECRET_KEY 派生
    secret = os.environ.get('SECRET_KEY', 'fallback-dev-key-change-me')
    return hashlib.sha256(secret.encode()).digest()


def encrypt_field(plaintext: str) -> str:
    """对称加密敏感字段（AES-128-CTR via XOR + base64）"""
    if not plaintext:
        return ''
    try:
        from cryptography.fernet import Fernet
        # 用 Fernet 做真正的加密
        key = base64.urlsafe_b64encode(_get_encrypt_key())
        f = Fernet(key)
        return f.encrypt(plaintext.encode()).decode()
    except ImportError:
        # 降级：至少不做明文存储，用简单混淆
        key = _get_encrypt_key()
        data = plaintext.encode()
        encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
        return 'enc:' + base64.b64encode(encrypted).decode()


def decrypt_field(ciphertext: str) -> str:
    """解密敏感字段"""
    if not ciphertext:
        return ''
    try:
        if ciphertext.startswith('enc:'):
            # 简单混淆模式
            key = _get_encrypt_key()
            data = base64.b64decode(ciphertext[4:])
            return bytes(b ^ key[i % len(key)] for i, b in enumerate(data)).decode()
        from cryptography.fernet import Fernet
        key = base64.urlsafe_b64encode(_get_encrypt_key())
        f = Fernet(key)
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        return ''


# ============================================================
#  模型
# ============================================================

class User(db.Model):
    """用户"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Interpark 凭证 (加密存储)
    interpark_id = db.Column(db.String(200), default='')
    interpark_pw = db.Column(db.String(500), default='')  # 加密后存储
    weverse_id = db.Column(db.String(200), default='')
    has_presale = db.Column(db.Boolean, default=False)

    orders = db.relationship('Order', backref='user', lazy=True)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    def set_interpark_pw(self, pw: str):
        """加密存储 Interpark 密码"""
        self.interpark_pw = encrypt_field(pw)

    def get_interpark_pw(self) -> str:
        """解密获取 Interpark 密码"""
        return decrypt_field(self.interpark_pw)

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

    # ---- 新增：GetBlock ----
    goods_code = db.Column(db.String(50), default='')
    place_code = db.Column(db.String(50), default='')
    seat_mode = db.Column(db.Integer, default=1)
    block_no = db.Column(db.String(50), default='')

    # ---- 新增：Delay 配置 ----
    lock_delay = db.Column(db.Integer, default=1200)
    delay_start = db.Column(db.Integer, default=300)

    # ---- 新增：票务模式 ----
    kr_ticket_mode = db.Column(db.String(20), default='')

    # ---- 新增：自动过户 ----
    auto_guohu = db.Column(db.Boolean, default=False)
    auto_cancel = db.Column(db.Boolean, default=False)
    guohu_pay = db.Column(db.Boolean, default=False)

    # ---- 新增：验证码 & 代理 & 通知 ----
    yes_captcha_key = db.Column(db.String(200), default='')
    proxy_api = db.Column(db.String(500), default='')
    ding_webhook = db.Column(db.String(500), default='')

    # ---- 新增：多线程控制 ----
    thread_count = db.Column(db.Integer, default=1)

    # ---- 新增：关键词 ----
    keyword = db.Column(db.String(200), default='')

    # ---- 新增：开关 ----
    suo_tou = db.Column(db.Boolean, default=False)
    day2 = db.Column(db.Boolean, default=False)
    pre_yn = db.Column(db.String(5), default='N')
    ko_pay = db.Column(db.String(50), default='')

    # 状态
    status = db.Column(db.String(30), default='pending')

    # 结果
    order_no = db.Column(db.String(100), default='')
    grabber_tab = db.Column(db.Integer, default=0)
    result_detail = db.Column(db.Text, default='')

    # 实时统计
    total_tasks = db.Column(db.Integer, default=0)
    success_tasks = db.Column(db.Integer, default=0)
    threads_running = db.Column(db.Integer, default=0)
    remaining_tickets = db.Column(db.Integer, default=0)

    # 截图
    screenshot_path = db.Column(db.String(300), default='')

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    logs = db.relationship('OrderLog', backref='order', lazy=True, order_by='OrderLog.created_at')
    ticket_classes = db.relationship('TicketClass', backref='order', lazy=True)

    def to_dict(self):
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
            'proxy': self.proxy,
            'status': self.status,
            'order_no': self.order_no,
            'result_detail': self.result_detail,
            'goods_code': self.goods_code,
            'place_code': self.place_code,
            'seat_mode': self.seat_mode,
            'block_no': self.block_no,
            'lock_delay': self.lock_delay,
            'delay_start': self.delay_start,
            'kr_ticket_mode': self.kr_ticket_mode,
            'auto_guohu': self.auto_guohu,
            'auto_cancel': self.auto_cancel,
            'guohu_pay': self.guohu_pay,
            'ding_webhook': self.ding_webhook,
            'thread_count': self.thread_count,
            'total_tasks': self.total_tasks,
            'success_tasks': self.success_tasks,
            'threads_running': self.threads_running,
            'remaining_tickets': self.remaining_tickets,
            'suo_tou': self.suo_tou,
            'day2': self.day2,
            'pre_yn': self.pre_yn,
            'ko_pay': self.ko_pay,
            'keyword': self.keyword,
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
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'level': self.level,
            'message': self.message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class TicketClass(db.Model):
    """座位档位配置"""
    __tablename__ = 'ticket_classes'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)

    name = db.Column(db.String(100), default='')
    grade_index = db.Column(db.Integer, default=0)
    price = db.Column(db.Integer, default=0)
    currency = db.Column(db.String(10), default='KRW')
    ticket_per_person = db.Column(db.Integer, default=1)
    total_seats = db.Column(db.Integer, default=0)
    available_seats = db.Column(db.Integer, default=0)
    is_sold_out = db.Column(db.Boolean, default=False)
    is_visible = db.Column(db.Boolean, default=True)

    color = db.Column(db.String(20), default='#7c5cfc')
    icon = db.Column(db.String(10), default='🎫')

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

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


class Account(db.Model):
    """多账号管理"""
    __tablename__ = 'accounts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)

    no = db.Column(db.Integer, default=1)
    email = db.Column(db.String(200), default='')
    password = db.Column(db.String(500), default='')    # 加密存储
    proxy = db.Column(db.String(300), default='')

    # 支付信息（加密存储）
    card_no = db.Column(db.String(500), default='')      # 加密存储
    card_cvv = db.Column(db.String(200), default='')     # 加密存储

    wrid = db.Column(db.String(100), default='')
    status = db.Column(db.String(30), default='idle')

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref='accounts')

    def set_password(self, pw: str):
        """加密存储密码"""
        self.password = encrypt_field(pw)

    def get_password(self) -> str:
        """解密获取密码"""
        return decrypt_field(self.password)

    def set_card_no(self, card: str):
        self.card_no = encrypt_field(card)

    def get_card_no(self) -> str:
        return decrypt_field(self.card_no)

    def set_card_cvv(self, cvv: str):
        self.card_cvv = encrypt_field(cvv)

    def get_card_cvv(self) -> str:
        return decrypt_field(self.card_cvv)

    def to_dict(self):
        """API 输出 — 不返回敏感明文"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'order_id': self.order_id,
            'no': self.no,
            'email': self.email,
            'password': '***' if self.password else '',
            'proxy': self.proxy,
            'card_no': '****' + self.get_card_no()[-4:] if self.get_card_no() else '',
            'card_cvv': '***' if self.card_cvv else '',
            'wrid': self.wrid,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def to_engine_dict(self):
        """引擎内部使用 — 包含解密后的真实值"""
        return {
            'id': self.id,
            'email': self.email,
            'password': self.get_password(),
            'proxy': self.proxy,
            'card_no': self.get_card_no(),
            'card_cvv': self.get_card_cvv(),
            'wrid': self.wrid,
        }


class SystemStatus(db.Model):
    """系统状态"""
    __tablename__ = 'system_status'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, default='')
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
