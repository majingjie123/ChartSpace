import os
from flask import Blueprint, jsonify, request, send_file
from core.database import db_session
from core.exceptions import APIError
from models.models import Space, Dataset, Chart, ChatHistory, AnalysisNote

spaces_bp = Blueprint('spaces', __name__)

@spaces_bp.route('/api/spaces', methods=['GET'])
def list_spaces():
    """获取所有工作空间"""
    spaces = db_session.query(Space).order_by(Space.created_at.desc()).all()
    return jsonify([s.to_dict() for s in spaces])


@spaces_bp.route('/api/spaces', methods=['POST'])
def create_space():
    """创建工作空间"""
    data = request.get_json(silent=True) or {}
    name = data.get('name')
    
    # 卫语句：校验参数非法
    if not name or not name.strip():
        raise APIError('空间名称不能为空')
        
    space = Space(name=name.strip())
    db_session.add(space)
    db_session.commit()
    return jsonify(space.to_dict()), 201


@spaces_bp.route('/api/spaces/<int:space_id>', methods=['PUT'])
def rename_space(space_id):
    """重命名工作空间"""
    space = db_session.get(Space, space_id)
    if not space:
        raise APIError('空间不存在', 404)
        
    data = request.get_json(silent=True) or {}
    name = data.get('name')
    if not name or not name.strip():
        raise APIError('空间名称不能为空')
        
    space.name = name.strip()
    db_session.commit()
    return jsonify(space.to_dict())


@spaces_bp.route('/api/spaces/<int:space_id>', methods=['DELETE'])
def delete_space(space_id):
    """删除空间（级联删除关联的本地文件及数据库记录）"""
    space = db_session.get(Space, space_id)
    if not space:
        raise APIError('空间不存在', 404)
        
    # 物理删除该空间下的所有数据集文件，防止磁盘泄露
    for ds in space.datasets:
        try:
            if os.path.exists(ds.file_path):
                os.remove(ds.file_path)
        except Exception:
            pass
            
    db_session.delete(space)
    db_session.commit()
    return jsonify({'message': '已删除'})


@spaces_bp.route('/api/spaces/<int:space_id>/datasets', methods=['GET'])
def list_datasets(space_id):
    """获取指定空间下的所有数据集"""
    check_space = db_session.get(Space, space_id)
    if not check_space:
        raise APIError('空间不存在', 404)
        
    datasets = db_session.query(Dataset).filter_by(space_id=space_id).order_by(Dataset.uploaded_at.desc()).all()
    return jsonify([d.to_dict() for d in datasets])


@spaces_bp.route('/api/spaces/<int:space_id>/charts', methods=['GET'])
def list_charts(space_id):
    """获取指定空间下的所有图表"""
    check_space = db_session.get(Space, space_id)
    if not check_space:
        raise APIError('空间不存在', 404)
        
    charts = db_session.query(Chart).filter_by(space_id=space_id).order_by(Chart.created_at.desc()).all()
    return jsonify([c.to_dict() for c in charts])


@spaces_bp.route('/api/spaces/<int:space_id>/chat-history', methods=['GET'])
def get_chat_history(space_id):
    """获取空间内 AI 对话的历史记录"""
    check_space = db_session.get(Space, space_id)
    if not check_space:
        raise APIError('空间不存在', 404)
        
    history = db_session.query(ChatHistory).filter_by(space_id=space_id)\
        .order_by(ChatHistory.created_at.asc()).all()
    return jsonify([h.to_dict() for h in history])


@spaces_bp.route('/api/spaces/<int:space_id>/chat-history', methods=['DELETE'])
def clear_chat_history(space_id):
    """清空空间聊天记录"""
    check_space = db_session.get(Space, space_id)
    if not check_space:
        raise APIError('空间不存在', 404)
        
    db_session.query(ChatHistory).filter_by(space_id=space_id).delete()
    db_session.commit()
    return jsonify({'message': '已清空'})


@spaces_bp.route('/api/spaces/<int:space_id>/notes', methods=['GET'])
def list_notes(space_id):
    """获取空间内所有的分析笔记"""
    check_space = db_session.get(Space, space_id)
    if not check_space:
        raise APIError('空间不存在', 404)
        
    notes = db_session.query(AnalysisNote).filter_by(space_id=space_id)\
        .order_by(AnalysisNote.created_at.desc()).all()
    return jsonify([n.to_dict() for n in notes])


@spaces_bp.route('/api/notes', methods=['POST'])
def create_note():
    """保存或新增一篇分析笔记，采用卫语句"""
    data = request.get_json(silent=True) or {}
    space_id = data.get('space_id')
    if not space_id:
        raise APIError('缺少 space_id')
        
    note = AnalysisNote(
        space_id=space_id,
        title=data.get('title', '分析笔记'),
        content=data.get('content', '')
    )
    db_session.add(note)
    db_session.commit()
    return jsonify(note.to_dict()), 201


@spaces_bp.route('/api/notes/<int:note_id>', methods=['DELETE'])
def delete_note(note_id):
    """根据 id 删除分析笔记"""
    note = db_session.get(AnalysisNote, note_id)
    if not note:
        raise APIError('笔记不存在', 404)
        
    db_session.delete(note)
    db_session.commit()
    return jsonify({'message': '已删除'})


@spaces_bp.route('/api/spaces/<int:space_id>/export', methods=['GET'])
def export_space(space_id):
    """导出整个空间为 ZIP 包"""
    import zipfile
    from io import BytesIO
    import json as json_module
    import requests as http_requests

    space = db_session.get(Space, space_id)
    if not space:
        raise APIError('空间不存在', 404)

    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 1. 归档数据集文件
        for ds in space.datasets:
            if os.path.exists(ds.file_path):
                arc_name = f'datasets/{ds.name}_{ds.id}{os.path.splitext(ds.file_path)[1]}'
                zf.write(ds.file_path, arc_name)
                
        # 2. 导出图表布局 JSON 镜像
        from flask import current_app
        port = current_app.config.get('PORT', 5000)
        for chart in space.charts:
            try:
                url = f"http://127.0.0.1:{port}/api/charts/{chart.id}/render"
                resp = http_requests.get(url, timeout=5)
                if resp.status_code == 200:
                    zf.writestr(f'charts/{chart.name}_{chart.id}.json',
                                json_module.dumps(resp.json(), ensure_ascii=False, indent=2))
            except Exception:
                pass
                
        # 3. 归档对话历史
        history = db_session.query(ChatHistory).filter_by(space_id=space_id)\
            .order_by(ChatHistory.created_at.asc()).all()
        zf.writestr('chat_history.json',
                    json_module.dumps([h.to_dict() for h in history],
                                      ensure_ascii=False, indent=2,
                                      default=str))
                                      
        # 4. 归档分析笔记
        notes = db_session.query(AnalysisNote).filter_by(space_id=space_id).all()
        zf.writestr('analysis_notes.json',
                    json_module.dumps([n.to_dict() for n in notes],
                                      ensure_ascii=False, indent=2,
                                      default=str))
                                      
    buf.seek(0)
    return send_file(buf, mimetype='application/zip',
                     as_attachment=True,
                     download_name=f'{space.name}_导出.zip')
