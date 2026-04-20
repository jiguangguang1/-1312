"""
NOL 抢票系统 v3 — Web 服务器 + 实时仪表盘

功能:
  - REST API
  - WebSocket 实时推送
  - Web 仪表盘
  - 一键启动抢票/监控
"""

import json
import time
import logging
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit

from core import NOLGrabber, NOLAccount, Notifier, SaleWaiter, Status

BASE = Path(__file__).parent
log = logging.getLogger('nol.server')

# ============================================================
#  Flask + SocketIO
# ============================================================

app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = 'nol-grabber-secret'
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

# ============================================================
#  全局状态
# ============================================================

grabber: NOLGrabber = None
grabber_thread: threading.Thread = None
config: dict = {}
accounts: list = []


def load_config():
    global config
    cfg_path = BASE / 'config.json'
    if cfg_path.exists():
        with open(cfg_path) as f:
            config = json.load(f)
    else:
        config = {}


def load_accounts():
    global accounts
    accounts = []
    tok_path = BASE / 'tokens.json'
    if tok_path.exists():
        with open(tok_path) as f:
            tokens_list = json.load(f)
        for td in tokens_list:
            if td.get('enabled', True) and td.get('access_token'):
                accounts.append(NOLAccount(td, td.get('label', '')))


def save_tokens():
    tok_path = BASE / 'tokens.json'
    data = []
    for a in accounts:
        data.append(a.tokens)
    with open(tok_path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def broadcast(event, data):
    socketio.emit(event, data)


# ============================================================
#  API 路由
# ============================================================

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/api/status')
def api_status():
    if grabber:
        return jsonify(grabber.get_status())
    return jsonify({'status': 'idle', 'accounts': len(accounts)})


@app.route('/api/config', methods=['GET'])
def api_config_get():
    return jsonify(config)


@app.route('/api/config', methods=['POST'])
def api_config_set():
    global config
    config.update(request.json)
    with open(BASE / 'config.json', 'w') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    return jsonify({'ok': True})


@app.route('/api/check')
def api_check():
    """检查账号状态"""
    results = []
    load_accounts()
    for a in accounts:
        try:
            user = a.user_info()
            results.append({
                'label': a.label,
                'name': user.get('name', '?'),
                'email': user.get('email', '?'),
                'status': 'ok',
            })
        except Exception as e:
            results.append({
                'label': a.label,
                'status': 'error',
                'error': str(e)[:100],
            })
    return jsonify({'accounts': results})


@app.route('/api/sales')
def api_sales():
    """获取售卖信息"""
    load_accounts()
    if not accounts:
        return jsonify({'error': '没有可用账号'}), 400
    try:
        grabber = NOLGrabber(config, accounts)
        info = grabber.get_sales_info()
        return jsonify(info)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/grab', methods=['POST'])
def api_grab():
    """启动抢票"""
    global grabber, grabber_thread

    if grabber and grabber.status == Status.GRABBING:
        return jsonify({'error': '抢票进行中'}), 400

    load_accounts()
    if not accounts:
        return jsonify({'error': '没有可用账号，请先配置 tokens.json'}), 400

    # 检查 enter info
    for a in accounts:
        try:
            a.set_referer(config['goods_code'], config['place_code'])
            enter = a.enter_info(config['goods_code'], config['place_code'])
            ekyc = enter.get('enterEkyc', {}).get('status', 'unknown')
            broadcast('log', {'msg': f'{a.label}: eKYC={ekyc}', 'level': 'info'})
        except Exception as e:
            broadcast('log', {'msg': f'{a.label}: enter失败 {e}', 'level': 'error'})

    grabber = NOLGrabber(config, accounts)
    grabber.on_event(lambda ev, data: broadcast(ev, data))

    # 是否需要等待
    wait_first = request.json.get('wait', True) if request.is_json else True

    def run():
        if wait_first:
            target = grabber.parse_time(config['sale_time'])
            presale = config.get('presale_time')
            if presale:
                target = grabber.parse_time(presale)

            waiter = SaleWaiter(
                target,
                config.get('pre_seconds', 2),
                lambda msg: broadcast('log', {'msg': msg, 'level': 'info'}),
            )
            waiter.wait()

            # Token 刷新
            if config.get('auto_refresh_token', True):
                for a in accounts:
                    if a.refresh_token():
                        broadcast('log', {'msg': f'{a.label}: Token已刷新', 'level': 'info'})
                save_tokens()

        result = grabber.grab()
        broadcast('done', {'success': result.success})

    grabber_thread = threading.Thread(target=run, daemon=True)
    grabber_thread.start()

    return jsonify({'ok': True, 'msg': '抢票已启动'})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    """停止抢票"""
    global grabber
    if grabber:
        grabber.stop()
        return jsonify({'ok': True, 'msg': '已发送停止信号'})
    return jsonify({'ok': False, 'msg': '没有进行中的任务'})


@app.route('/api/tokens', methods=['GET'])
def api_tokens_get():
    """获取 token 列表 (脱敏)"""
    load_accounts()
    result = []
    for a in accounts:
        t = a.tokens.copy()
        if t.get('access_token'):
            t['access_token'] = t['access_token'][:20] + '...'
        if t.get('refresh_token'):
            t['refresh_token'] = t['refresh_token'][:10] + '...'
        result.append(t)
    return jsonify(result)


@app.route('/api/tokens', methods=['POST'])
def api_tokens_set():
    """更新 token"""
    global accounts
    data = request.json
    load_accounts()

    label = data.get('label', '')
    for a in accounts:
        if a.label == label:
            a.tokens.update(data)
            a._update_headers()
            save_tokens()
            return jsonify({'ok': True, 'msg': f'{label} 已更新'})

    # 新账号
    accounts.append(NOLAccount(data, label))
    save_tokens()
    return jsonify({'ok': True, 'msg': f'{label} 已添加'})


# ============================================================
#  WebSocket
# ============================================================

@socketio.on('connect')
def on_connect():
    emit('status', grabber.get_status() if grabber else {'status': 'idle', 'accounts': len(accounts)})


@socketio.on('ping')
def on_ping():
    emit('pong', {'time': datetime.now().isoformat()})


# ============================================================
#  启动
# ============================================================

def main():
    load_config()
    load_accounts()

    port = config.get('web_port', 8080)
    host = config.get('web_host', '0.0.0.0')

    log.info(f'🚀 NOL 抢票系统 v3 启动')
    log.info(f'📡 http://{host}:{port}')
    log.info(f'👤 已加载 {len(accounts)} 个账号')

    socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    main()
