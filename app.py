#!/usr/bin/env python3
import json
import os
import random
import string
import sys
from flask import Flask, render_template, jsonify, request, redirect, url_for, session
from functools import wraps

# 添加项目目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 尝试导入配置，如果不存在则使用默认值
try:
    from config import ADMIN_USER, ADMIN_PASS, SECRET_KEY, MUDB_FILE
except ImportError:
    ADMIN_USER = 'admin'
    ADMIN_PASS = 'admin123'
    SECRET_KEY = 'default-secret-key-change-me'
    MUDB_FILE = '/usr/local/shadowsocksr/mudb.json'

app = Flask(__name__)
app.secret_key = SECRET_KEY

def check_auth(username, password):
    return username == ADMIN_USER and password == ADMIN_PASS

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def load_users():
    with open(MUDB_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_users(users):
    with open(MUDB_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=4, ensure_ascii=False)

def generate_password(length=12):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def format_bytes(bytes_val):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.2f} PB"

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if check_auth(username, password):
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('index'))
        else:
            error = '用户名或密码错误'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/')
@requires_auth
def index():
    users = load_users()
    total_users = len(users)
    total_upload = sum(u.get('u', 0) for u in users)
    total_download = sum(u.get('d', 0) for u in users)
    total_transfer = total_upload + total_download
    inactive_users = sum(1 for u in users if (u.get('u', 0) + u.get('d', 0)) == 0)
    return render_template('index.html', 
                         users=users,
                         total_users=total_users,
                         total_upload=total_upload,
                         total_download=total_download,
                         total_transfer=total_transfer,
                         inactive_users=inactive_users,
                         format_bytes=format_bytes)

@app.route('/api/users')
@requires_auth
def api_users():
    users = load_users()
    for u in users:
        u['upload_human'] = format_bytes(u.get('u', 0))
        u['download_human'] = format_bytes(u.get('d', 0))
        u['total_human'] = format_bytes(u.get('u', 0) + u.get('d', 0))
        u['transfer_limit_human'] = format_bytes(u.get('transfer_enable', 0))
        u['usage_percent'] = min(100, (u.get('u', 0) + u.get('d', 0)) / u.get('transfer_enable', 1) * 100)
    return jsonify({'success': True, 'data': users})

@app.route('/api/add', methods=['POST'])
@requires_auth
def add_user():
    data = request.json
    users = load_users()
    
    new_user = {
        'user': data.get('user', str(data.get('port', 10000))),
        'passwd': data.get('password', generate_password()),
        'port': int(data.get('port', 10000)),
        'method': data.get('method', 'aes-256-cfb'),
        'protocol': data.get('protocol', 'auth_aes128_md5'),
        'obfs': data.get('obfs', 'tls1.2_ticket_auth'),
        'obfs_param': data.get('obfs_param', 'www.baidu.com'),
        'protocol_param': data.get('protocol_param', '3#'),
        'transfer_enable': int(data.get('transfer', 268435456000)),
        'enable': 1,
        'd': 0,
        'u': 0
    }
    
    if any(u.get('port') == new_user['port'] for u in users):
        return jsonify({'success': False, 'error': f"端口 {new_user['port']} 已存在"})
    
    users.append(new_user)
    save_users(users)
    return jsonify({'success': True, 'message': '用户添加成功', 'user': new_user})

@app.route('/api/delete/<user>')
@requires_auth
def delete_user(user):
    users = load_users()
    users = [u for u in users if u.get('user') != user]
    save_users(users)
    return jsonify({'success': True, 'message': '用户删除成功'})

@app.route('/api/reset/<user>')
@requires_auth
def reset_user(user):
    users = load_users()
    for u in users:
        if u.get('user') == user:
            u['u'] = 0
            u['d'] = 0
    save_users(users)
    return jsonify({'success': True, 'message': f'用户 {user} 流量已重置'})

@app.route('/api/toggle/<user>')
@requires_auth
def toggle_user(user):
    users = load_users()
    for u in users:
        if u.get('user') == user:
            u['enable'] = 0 if u.get('enable', 0) == 1 else 1
    save_users(users)
    return jsonify({'success': True, 'message': f'用户 {user} 状态已切换'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
