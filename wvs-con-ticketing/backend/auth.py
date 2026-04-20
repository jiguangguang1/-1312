"""JWT 认证装饰器"""

from functools import wraps
from flask import jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from models import User, db


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            verify_jwt_in_request()
        except Exception:
            return jsonify({'error': '请先登录'}), 401
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            verify_jwt_in_request()
            user_id = int(get_jwt_identity())
            user = db.session.get(User, user_id)
            if not user or not user.is_admin:
                return jsonify({'error': '需要管理员权限'}), 403
        except Exception:
            return jsonify({'error': '请先登录'}), 401
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    try:
        verify_jwt_in_request()
        user_id = int(get_jwt_identity())
        return db.session.get(User, user_id)
    except Exception:
        return None
