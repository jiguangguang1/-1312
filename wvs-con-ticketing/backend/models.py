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

    # ---- 新增：GetBlock ----
    goods_code = db.Column(db.String(50), default='')     # 商品编码
    place_code = db.Column(db.String(50), default='')     # 场地编码
    seat_mode = db.Column(db.Integer, default=1)          # 座位模式
    block_no = db.Column(db.String(50), default='')       # 获取到的区块编号

    # ---- 新增：Delay 配置 ----
    lock_delay = db.Column(db.Integer, default=1200)      # 锁定延迟 ms
    delay_start = db.Column(db.Integer, default=300)      # 延迟启动 ms

    # ---- 新增：票务模式 ----
    kr_ticket_mode = db.Column(db.String(20), default='') # 韩国票务模式编码

    # ---- 新增：自动过户 ----
    auto_guohu = db.Column(db.Boolean, default=False)     # 自动过户
    auto_cancel = db.Column(db.Boolean, default=False)    # 异常自动取消
    guohu_pay = db.Column(db.Boolean, default=False)      # 过户支付

    # ---- 新增：验证码 & 代理 & 通知 ----
    yes_captcha_key = db.Column(db.String(200), default='')  # YesCaptcha Key
    proxy_api = db.Column(db.String(500), default='')        # 代理轮换 API
    ding_webhook = db.Column(db.String(500), default='')     # 钉钉 webhook

    # ---- 新增：多线程控制 ----
    thread_count = db.Column(db.Integer, default=1)       # 线程数

    # ---- 新增：关键词 ----
    keyword = db.Column(db.String(200), default='')       # 搜索关键词

    # ---- 新增：开关 ----
    suo_tou = db.Column(db.Boolean, default=False)        # 锁票开关
    day2 = db.Column(db.Boolean, default=False)           # 次日票务
    pre_yn = db.Column(db.String(5), default='N')         # 预抢票 Y/N
    ko_pay = db.Column(db.String(50), default='')         # 韩国支付渠道

    # 状态
    status = db.Column(db.String(30), default='pending')
    # pending -> waiting -> grabbing -> success / failed / sold_out / error

    # 结果
    order_no = db.Column(db.String(100), default='')
    grabber_tab = db.Column(db.Integer, default=0)
    result_detail = db.Column(db.Text, default='')

    # 实时统计
    total_tasks = db.Column(db.Integer, default=0)
    success_tasks = db.Column(db.Integer, default=0)
    threads_running = db.Column(db.Integer, default=0)
    remaining_tickets = db.Column(db.Integer, default=0)  # SYL

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
            'proxy': self.proxy,
            'status': self.status,
            'order_no': self.order_no,
            'result_detail': self.result_detail,
            # GetBlock
            'goods_code': self.goods_code,
            'place_code': self.place_code,
            'seat_mode': self.seat_mode,
            'block_no': self.block_no,
            # Delay
            'lock_delay': self.lock_delay,
            'delay_start': self.delay_start,
            # 票务模式
            'kr_ticket_mode': self.kr_ticket_mode,
            # 自动过户
            'auto_guohu': self.auto_guohu,
            'auto_cancel': self.auto_cancel,
            'guohu_pay': self.guohu_pay,
            # 验证码 & 代理 & 通知
            'ding_webhook': self.ding_webhook,
            # 多线程
            'thread_count': self.thread_count,
            # 实时统计
            'total_tasks': self.total_tasks,
            'success_tasks': self.success_tasks,
            'threads_running': self.threads_running,
            'remaining_tickets': self.remaining_tickets,
            # 开关
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


class Account(db.Model):
    """多账号管理 — 每个账号对应一个抢票任务行"""
    __tablename__ = 'accounts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)
    # 关联订单，NULL 表示全局账号池

    # 账号信息
    no = db.Column(db.Integer, default=1)              # 任务序号
    email = db.Column(db.String(200), default='')       # 登录邮箱
    password = db.Column(db.String(200), default='')     # 登录密码
    proxy = db.Column(db.String(300), default='')        # 该账号的代理

    # 支付信息
    card_no = db.Column(db.String(50), default='')       # 银行卡号
    card_cvv = db.Column(db.String(10), default='')      # CVV

    # 标识
    wrid = db.Column(db.String(100), default='')         # 账号标识
    status = db.Column(db.String(30), default='idle')    # idle / running / success / failed

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='accounts')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'order_id': self.order_id,
            'no': self.no,
            'email': self.email,
            'password': '***' if self.password else '',
            'proxy': self.proxy,
            'card_no': self.card_no,
            'card_cvv': self.card_cvv,
            'wrid': self.wrid,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def to_dict_full(self):
        """包含明文密码（仅后端内部使用）"""
        d = self.to_dict()
        d['password'] = self.password
        return d


class SystemStatus(db.Model):
    """系统状态"""
    __tablename__ = 'system_status'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, default='')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
