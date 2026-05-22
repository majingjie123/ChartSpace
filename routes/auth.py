from flask import Blueprint, jsonify, request, session, current_app

auth_bp = Blueprint('auth', __name__)

@auth_bp.before_app_request
def check_auth():
    """全局安全密码校验拦截器（应用卫语句）"""
    access_password = current_app.config.get('ACCESS_PASSWORD')
    # 未开启密码直接放行
    if access_password is None:
        return
        
    # 白名单放行
    if request.path in ['/api/auth/login', '/api/auth/status'] or \
       request.path.startswith('/static/') or \
       request.path == '/':
        return
        
    # 未授权拦截
    if not session.get('is_authenticated'):
        return jsonify({'error': '未授权访问', 'code': 401}), 401


@auth_bp.route('/api/auth/status', methods=['GET'])
def auth_status():
    """获取登录验证状态"""
    access_password = current_app.config.get('ACCESS_PASSWORD')
    return jsonify({
        'required': access_password is not None,
        'authenticated': session.get('is_authenticated', False)
    })


@auth_bp.route('/api/auth/login', methods=['POST'])
def auth_login():
    """登录接口（使用卫语句扁平化）"""
    access_password = current_app.config.get('ACCESS_PASSWORD')
    
    # 1. 拦截未开启密码验证的情形
    if not access_password:
        session['is_authenticated'] = True
        return jsonify({'message': '登录成功'})
        
    data = request.get_json(silent=True) or {}
    pwd = data.get('password')
    
    # 2. 拦截错误密码
    if pwd != access_password:
        return jsonify({'error': '密码错误'}), 401
        
    # 3. 正常通过，写入会话
    session['is_authenticated'] = True
    return jsonify({'message': '登录成功'})
