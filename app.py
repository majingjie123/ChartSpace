# -*- coding: utf-8 -*-
"""
Excel 多空间智能图表分析工具 - 主入口装配模块
基于 Flask + SQLAlchemy + Vue 3 + Plotly.js
"""

import os
import sys
import argparse
import logging
import threading
from logging.handlers import TimedRotatingFileHandler
from flask import Flask
from flask_cors import CORS

from core.database import (
    DB_PATH,
    UPLOAD_FOLDER,
    LOG_FOLDER,
    db_session,
    init_db
)
from core.exceptions import register_error_handlers
from routes import all_blueprints

# ---------------------------------------------------------------------------
# 路径处理：兼容开发环境和 PyInstaller 打包环境
# ---------------------------------------------------------------------------
def get_resource_path(relative_path):
    """获取资源文件路径（模板等内置资源，支持 PyInstaller 打包路径）"""
    if getattr(sys, '_MEIPASS', False):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


# ---------------------------------------------------------------------------
# Flask 应用初始化与配置
# ---------------------------------------------------------------------------
app = Flask(
    __name__, 
    template_folder=get_resource_path('templates'),
    static_folder=get_resource_path('static')
)

# 修改 Jinja2 定界符，避免与前端 Vue.js 的 {{ }} 冲突
app.jinja_env.variable_start_string = '(('
app.jinja_env.variable_end_string = '))'
app.jinja_env.block_start_string = '(%'
app.jinja_env.block_end_string = '%)'
app.jinja_env.comment_start_string = '(#'
app.jinja_env.comment_end_string = '#)'

# 允许跨域
CORS(app)

# Flask 核心配置
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'excelany-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB 上传限制
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ---------------------------------------------------------------------------
# 日志配置（按天滚动，仅记录 ERROR 级别及以上）
# ---------------------------------------------------------------------------
log_handler = TimedRotatingFileHandler(
    os.path.join(LOG_FOLDER, 'error.log'),
    when='midnight',
    interval=1,
    backupCount=30,
    encoding='utf-8'
)
log_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s'
))
log_handler.setLevel(logging.ERROR)
app.logger.addHandler(log_handler)
app.logger.setLevel(logging.ERROR)

# ---------------------------------------------------------------------------
# 注册全局异常处理器
# ---------------------------------------------------------------------------
register_error_handlers(app)

# ---------------------------------------------------------------------------
# 循环挂载所有模块化的路由蓝图
# ---------------------------------------------------------------------------
for bp in all_blueprints:
    app.register_blueprint(bp)

# ---------------------------------------------------------------------------
# 请求生命周期管理：结束时自动清理并释放数据库会话连接
# ---------------------------------------------------------------------------
@app.teardown_appcontext
def shutdown_session(exception=None):
    """请求结束时自动移除数据库会话，释放连接"""
    db_session.remove()


# ---------------------------------------------------------------------------
# 服务主启动入口
# ---------------------------------------------------------------------------
def main():
    """解析参数并启动 Flask 应用"""
    parser = argparse.ArgumentParser(description='ExcelAny Backend Server')
    parser.add_argument('--port', type=int, default=5000, help='服务运行端口')
    parser.add_argument('--password', type=str, help='访问密码')
    args = parser.parse_args()

    # 将启动密码写入 Flask 配置，供 auth 蓝图使用
    app.config['ACCESS_PASSWORD'] = args.password

    # 初始化数据库 (自动建表与自省迁移)
    init_db(app)

    port = args.port
    debug = not getattr(sys, 'frozen', False)
    
    # 注册系统信号，支持优雅退出
    import signal
    def handle_exit(signum, frame):
        app.logger.info(f'收到信号 {signum}，正在退出...')
        sys.exit(0)
    signal.signal(signal.SIGTERM, handle_exit)
    signal.signal(signal.SIGINT, handle_exit)
    
    # 打包 exe 环境下在子线程中自动打开浏览器
    if not debug:
        import webbrowser
        
        def open_browser():
            import time
            time.sleep(1.5)
            webbrowser.open(f'http://127.0.0.1:{port}')
            
        threading.Thread(target=open_browser, daemon=True).start()
        
    app.logger.info(f'服务启动成功: http://127.0.0.1:{port}')
    if args.password:
        app.logger.info('已开启启动密码验证')
    
    app.run(host='127.0.0.1', port=port, debug=debug, use_reloader=False)


if __name__ == '__main__':
    main()