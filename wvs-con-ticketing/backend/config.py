"""配置管理"""

import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    """基础配置"""
    SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(32))
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', f'sqlite:///{os.path.join(BASE_DIR, "wvs.db")}')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', secrets.token_hex(32))
    JWT_ACCESS_TOKEN_EXPIRES = 86400  # 24h

    # 抢票引擎默认配置
    GRABBER_HEADLESS = True
    GRABBER_TAB_COUNT = 4
    GRABBER_PRE_OPEN_SEC = 3
    GRABBER_PAGE_TIMEOUT = 10000
    GRABBER_MAX_CLICK_RETRIES = 100

    # 文件路径
    LOG_DIR = os.path.join(BASE_DIR, '..', 'logs')
    SCREENSHOT_DIR = os.path.join(BASE_DIR, '..', 'screenshots')


class DevelopmentConfig(Config):
    DEBUG = True
    GRABBER_HEADLESS = False


class ProductionConfig(Config):
    DEBUG = False
    GRABBER_HEADLESS = True


config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}
