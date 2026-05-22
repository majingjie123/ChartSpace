import json
from flask import Blueprint, jsonify, request
from core.database import db_session
from core.exceptions import APIError
from models.models import Space, Dataset, AIConfig, SpaceAIConfig, ChatHistory
from services.ai_service import AIChatFacade

chat_bp = Blueprint('chat', __name__)

def _fetch_models_from_url(base_url, api_key):
    """从 API 地址拉取模型列表，返回 (models_list, last_error_str)"""
    import requests as http_requests
    base = base_url.rstrip('/')
    candidates = []
    if '/v1' not in base:
        candidates.append(f"{base}/v1/models")
    candidates.append(f"{base}/models")
    last_error = ''
    
    for url in candidates:
        try:
            resp = http_requests.get(
                url,
                headers={'Authorization': f'Bearer {api_key}'},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                models = []
                if 'data' in data:
                    for m in data['data']:
                        if isinstance(m, dict) and 'id' in m:
                            models.append(m['id'])
                        elif isinstance(m, str):
                            models.append(m)
                if models:
                    return models, ''
                last_error = '返回数据中没有模型'
            else:
                last_error = f'HTTP {resp.status_code}'
        except http_requests.exceptions.RequestException as ex:
            last_error = str(ex)
            continue
            
    return [], last_error


@chat_bp.route('/api/chat', methods=['POST'])
def chat():
    """发送消息给 AI（利用外观类 AIChatFacade 做封装与拦截）"""
    data = request.get_json(silent=True) or {}
    space_id = data.get('space_id')
    if not space_id:
        raise APIError('缺少 space_id')
        
    message = data.get('message', '').strip()
    if not message:
        raise APIError('消息不能为空')
        
    dataset_id = data.get('dataset_id')

    facade = AIChatFacade(db_session)
    reply, message_id = facade.process_chat(space_id, message, dataset_id)
    return jsonify({'reply': reply, 'message_id': message_id})


@chat_bp.route('/api/ai-configs', methods=['GET'])
def list_ai_configs():
    """获取所有已录入的 AI 供应商配置"""
    configs = db_session.query(AIConfig).all()
    return jsonify([c.to_dict() for c in configs])


@chat_bp.route('/api/ai-configs', methods=['POST'])
def create_ai_config():
    """新建 AI 供应商配置，应用卫语句"""
    data = request.get_json(silent=True) or {}
    required = ['name', 'base_url', 'api_key', 'model']
    for field in required:
        if not data.get(field):
            raise APIError(f'缺少必填字段: {field}')
            
    config = AIConfig(
        name=data['name'],
        base_url=data['base_url'].rstrip('/'),
        api_key=data['api_key'],
        model=data['model'],
        system_prompt=data.get('system_prompt', '你是一个数据分析助手，基于用户上传的 Excel 数据回答问题。'),
        max_tokens=data.get('max_tokens', 2000),
        temperature=data.get('temperature', 0.7),
        is_default=data.get('is_default', False)
    )
    
    if config.is_default:
        db_session.query(AIConfig).filter(AIConfig.is_default == True).update({'is_default': False})
        
    db_session.add(config)
    db_session.commit()
    return jsonify(config.to_dict()), 201


@chat_bp.route('/api/ai-configs/<int:config_id>', methods=['PUT'])
def update_ai_config(config_id):
    """更新已有的 AI 供应商配置信息"""
    config = db_session.get(AIConfig, config_id)
    if not config:
        raise APIError('AI 配置不存在', 404)
        
    data = request.get_json(silent=True) or {}
    for field in ['name', 'base_url', 'api_key', 'model', 'system_prompt',
                  'max_tokens', 'temperature', 'is_default']:
        if field in data:
            setattr(config, field, data[field])
            
    if data.get('is_default'):
        db_session.query(AIConfig).filter(AIConfig.is_default == True, AIConfig.id != config_id).update({'is_default': False})
        
    db_session.commit()
    return jsonify(config.to_dict())


@chat_bp.route('/api/ai-configs/<int:config_id>', methods=['DELETE'])
def delete_ai_config(config_id):
    """物理删除 AI 供应商配置记录"""
    config = db_session.get(AIConfig, config_id)
    if not config:
        raise APIError('AI 配置不存在', 404)
        
    db_session.delete(config)
    db_session.commit()
    return jsonify({'message': '已删除'})


@chat_bp.route('/api/ai-configs/<int:config_id>/set-default', methods=['POST'])
def set_default_ai_config(config_id):
    """设置某 AI 供应商配置为全局系统默认选项"""
    config = db_session.get(AIConfig, config_id)
    if not config:
        raise APIError('AI 配置不存在', 404)
        
    db_session.query(AIConfig).filter(AIConfig.is_default == True).update({'is_default': False})
    config.is_default = True
    db_session.commit()
    return jsonify(config.to_dict())


@chat_bp.route('/api/ai-configs/<int:config_id>/refresh-models', methods=['POST'])
def refresh_ai_models(config_id):
    """根据 api_key 刷新所查询供应商的模型支持清单"""
    config = db_session.get(AIConfig, config_id)
    if not config:
        raise APIError('AI 配置不存在', 404)
        
    models, _ = _fetch_models_from_url(config.base_url, config.api_key)
    if not models:
        raise APIError(f'获取模型列表失败，请检查 base_url 和 api_key 是否正确')
        
    config.cached_models = json.dumps(models, ensure_ascii=False)
    db_session.commit()
    return jsonify({'models': models, 'message': f'已刷新，获取到 {len(models)} 个模型'})


@chat_bp.route('/api/ai-configs/refresh-models-preview', methods=['POST'])
def refresh_ai_models_preview():
    """测试并预览 AI 模型拉取，而不用执行保存"""
    data = request.get_json(silent=True) or {}
    base_url = (data.get('base_url') or '').strip()
    api_key = (data.get('api_key') or '').strip()
    if not base_url or not api_key:
        raise APIError('base_url 和 api_key 不能为空')
        
    models, last_error = _fetch_models_from_url(base_url, api_key)
    if not models:
        raise APIError(f'获取模型列表失败: {last_error or "未知错误"}')
    return jsonify({'models': models, 'message': f'获取到 {len(models)} 个模型'})


@chat_bp.route('/api/spaces/<int:space_id>/ai-config', methods=['GET'])
def get_space_ai_config(space_id):
    """获取空间绑定的 AI 配置 ID，若未绑定返回系统默认配置 ID"""
    check_space = db_session.get(Space, space_id)
    if not check_space:
        raise APIError('空间不存在', 404)
        
    binding = db_session.query(SpaceAIConfig).filter_by(space_id=space_id).first()
    if binding:
        return jsonify({'ai_config_id': binding.ai_config_id})
        
    default = db_session.query(AIConfig).filter_by(is_default=True).first()
    return jsonify({'ai_config_id': default.id if default else None})


@chat_bp.route('/api/spaces/<int:space_id>/ai-config', methods=['POST'])
def set_space_ai_config(space_id):
    """为指定空间强制绑定或切换专属 AI 供应商"""
    check_space = db_session.get(Space, space_id)
    if not check_space:
        raise APIError('空间不存在', 404)
        
    data = request.get_json(silent=True) or {}
    ai_config_id = data.get('ai_config_id')
    
    # 清理旧的空间绑定关系
    db_session.query(SpaceAIConfig).filter_by(space_id=space_id).delete()
    
    if ai_config_id:
        ai_config = db_session.get(AIConfig, ai_config_id)
        if not ai_config:
            raise APIError('AI 配置不存在')
        binding = SpaceAIConfig(space_id=space_id, ai_config_id=ai_config_id)
        db_session.add(binding)
        db_session.commit()
        return jsonify(binding.to_dict())
        
    db_session.commit()
    return jsonify({'message': '已解除绑定，将使用默认配置', 'ai_config_id': None})
