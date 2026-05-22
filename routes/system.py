import os
import signal
import threading
from datetime import datetime
import psutil
from flask import Blueprint, jsonify, request, send_file
from core.database import db_session, init_db, DB_PATH, BACKUP_FOLDER
from core.exceptions import APIError

system_bp = Blueprint('system', __name__)

def get_memory_info():
    """使用 psutil 获取当前服务器进程及系统内存状态"""
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    sys_mem = psutil.virtual_memory()
    return {
        'process_mb': round(mem_info.rss / (1024 * 1024), 2),
        'sys_percent': sys_mem.percent,
        'sys_available_mb': round(sys_mem.available / (1024 * 1024), 2),
        'warning': sys_mem.percent > 85
    }


@system_bp.route('/api/system/memory', methods=['GET'])
def system_memory():
    """对外暴露内存监控信息接口"""
    return jsonify(get_memory_info())


@system_bp.route('/api/system/backup', methods=['GET'])
def backup_database():
    """打包并下载当前的本地 sqlite db 文件（备份）"""
    if not os.path.exists(DB_PATH):
        raise APIError('数据库文件不存在')
    return send_file(DB_PATH, mimetype='application/octet-stream',
                     as_attachment=True,
                     download_name=f'excelany_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')


@system_bp.route('/api/system/restore', methods=['POST'])
def restore_database():
    """上传备份的 sqlite db 文件进行数据热回滚（恢复）"""
    if 'file' not in request.files:
        raise APIError('请上传备份文件')
    file = request.files['file']
    if file.filename == '':
        raise APIError('请选择文件')
        
    ext = os.path.splitext(file.filename)[1].lower()
    if ext != '.db':
        raise APIError('请上传 .db 文件')

    # 1. 物理备份当前运行中的数据库，防止覆盖失败导致损坏
    backup_path = os.path.join(BACKUP_FOLDER, f'pre_restore_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
    if os.path.exists(DB_PATH):
        import shutil
        shutil.copy2(DB_PATH, backup_path)
        
    # 2. 清理当前所有的 SQLAlchemy 链接池
    db_session.remove()
    
    # 3. 物理覆盖并重新装载 schema 列
    file.save(DB_PATH)
    init_db()
    
    return jsonify({'message': '数据库已恢复，原数据库已备份到 backup 目录'})


@system_bp.route('/api/system/shutdown', methods=['POST'])
def shutdown_server():
    """执行优雅关机指令"""
    import logging
    logger = logging.getLogger("excelany")
    logger.info('收到退出指令，正在关闭服务...')
    
    def delayed_shutdown():
        import time
        time.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)
        
    threading.Thread(target=delayed_shutdown, daemon=True).start()
    return jsonify({'message': '服务正在关闭...'})
