"""Routes package"""
from .orders import orders_bp
from .admin import admin_bp

__all__ = ['orders_bp', 'admin_bp']
