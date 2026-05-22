# -*- coding: utf-8 -*-
"""
DataInsightHub 看板与组件管理 API 控制器
基于卫语句优先拦截与扁平化设计原则
"""

import json
from flask import Blueprint, jsonify, request
from core.database import db_session
from core.exceptions import APIError
from models.models import Space, Dashboard, DashboardComponent, Dataset
from services.preprocess_service import get_dataframe
from services.dashboard_service import ComponentDataStrategyFactory

dashboards_bp = Blueprint('dashboards', __name__)

@dashboards_bp.route('/api/spaces/<int:space_id>/dashboards', methods=['GET'])
def list_dashboards(space_id):
    """获取指定空间下的所有看板"""
    space = db_session.get(Space, space_id)
    if not space:
        raise APIError('工作空间不存在', 404)
        
    dashboards = db_session.query(Dashboard).filter_by(space_id=space_id).order_by(Dashboard.created_at.asc()).all()
    return jsonify([d.to_dict() for d in dashboards])


@dashboards_bp.route('/api/spaces/<int:space_id>/dashboards', methods=['POST'])
def create_dashboard(space_id):
    """在指定空间下新建看板"""
    space = db_session.get(Space, space_id)
    if not space:
        raise APIError('工作空间不存在', 404)
        
    data = request.get_json(silent=True) or {}
    name = data.get('name')
    if not name or not name.strip():
        raise APIError('看板名称不能为空', 400)
        
    dashboard = Dashboard(
        space_id=space_id,
        name=name.strip(),
        layout='[]',
        refresh_interval=data.get('refresh_interval', 0)
    )
    db_session.add(dashboard)
    db_session.commit()
    return jsonify(dashboard.to_dict()), 201


@dashboards_bp.route('/api/dashboards/<int:dashboard_id>', methods=['PUT'])
def update_dashboard(dashboard_id):
    """更新指定看板信息（如名称、布局、轮询频率）"""
    dashboard = db_session.get(Dashboard, dashboard_id)
    if not dashboard:
        raise APIError('看板不存在', 404)
        
    data = request.get_json(silent=True) or {}
    
    if 'name' in data:
        name = data['name']
        if not name or not name.strip():
            raise APIError('看板名称不能为空', 400)
        dashboard.name = name.strip()
        
    if 'layout' in data:
        layout_data = data['layout']
        if isinstance(layout_data, list):
            dashboard.layout = json.dumps(layout_data, ensure_ascii=False)
        else:
            dashboard.layout = str(layout_data)
            
    if 'refresh_interval' in data:
        try:
            dashboard.refresh_interval = int(data['refresh_interval'])
        except (ValueError, TypeError):
            raise APIError('轮询间隔必须为非负整数', 400)
            
    db_session.commit()
    return jsonify(dashboard.to_dict())


@dashboards_bp.route('/api/dashboards/<int:dashboard_id>/components/layout', methods=['PUT'])
def update_dashboard_layout(dashboard_id):
    """批量更新看板下的组件布局位置"""
    dashboard = db_session.get(Dashboard, dashboard_id)
    if not dashboard:
        raise APIError('看板不存在', 404)
        
    data = request.get_json(silent=True) or {}
    layout = data.get('layout')
    if not isinstance(layout, list):
        raise APIError('布局数据格式不正确，应为列表', 400)
        
    for item in layout:
        comp_id = item.get('id')
        position = item.get('position')
        # 卫语句：如果没有组件 id 或位置信息则忽略该项
        if not comp_id or not position:
            continue
            
        comp = db_session.get(DashboardComponent, comp_id)
        # 卫语句：如果组件不存在或者不属于该看板，则忽略
        if not comp or comp.dashboard_id != dashboard_id:
            continue
            
        if isinstance(position, dict):
            comp.position = json.dumps(position, ensure_ascii=False)
        else:
            comp.position = str(position)
            
    db_session.commit()
    return jsonify({'message': '布局已成功保存'})


@dashboards_bp.route('/api/dashboards/<int:dashboard_id>', methods=['DELETE'])
def delete_dashboard(dashboard_id):
    """级联删除指定看板及其下辖的所有组件"""
    dashboard = db_session.get(Dashboard, dashboard_id)
    if not dashboard:
        raise APIError('看板不存在', 404)
        
    db_session.delete(dashboard)
    db_session.commit()
    return jsonify({'message': '看板已成功删除'})


@dashboards_bp.route('/api/dashboards/<int:dashboard_id>/components', methods=['GET'])
def list_components(dashboard_id):
    """获取指定看板下的所有组件配置"""
    dashboard = db_session.get(Dashboard, dashboard_id)
    if not dashboard:
        raise APIError('看板不存在', 404)
        
    components = db_session.query(DashboardComponent).filter_by(dashboard_id=dashboard_id).order_by(DashboardComponent.id.asc()).all()
    return jsonify([c.to_dict() for c in components])


@dashboards_bp.route('/api/dashboards/<int:dashboard_id>/components', methods=['POST'])
def create_component(dashboard_id):
    """为指定看板添加新组件"""
    dashboard = db_session.get(Dashboard, dashboard_id)
    if not dashboard:
        raise APIError('看板不存在', 404)
        
    data = request.get_json(silent=True) or {}
    comp_type = data.get('component_type')
    
    if comp_type not in ('chart', 'kpi', 'table', 'text'):
        raise APIError('不支持的组件类型', 400)
        
    dataset_id = data.get('dataset_id')
    # 卫语句：文本类型的组件可以不选择数据集
    if comp_type != 'text' and not dataset_id:
        raise APIError('该类型组件必须关联一个数据集', 400)
        
    if dataset_id:
        dataset = db_session.get(Dataset, dataset_id)
        if not dataset:
            raise APIError('所选数据集不存在', 404)
            
    config_dict = data.get('config', {})
    position_dict = data.get('position', {'x': 0, 'y': 0, 'w': 4, 'h': 4})
    
    comp = DashboardComponent(
        dashboard_id=dashboard_id,
        component_type=comp_type,
        dataset_id=dataset_id if comp_type != 'text' else None,
        title=data.get('title', '未命名组件'),
        config=json.dumps(config_dict, ensure_ascii=False),
        position=json.dumps(position_dict, ensure_ascii=False)
    )
    db_session.add(comp)
    db_session.commit()
    return jsonify(comp.to_dict()), 201


@dashboards_bp.route('/api/components/<int:comp_id>', methods=['PUT'])
def update_component(comp_id):
    """更新组件元信息、配置或网格坐标"""
    comp = db_session.get(DashboardComponent, comp_id)
    if not comp:
        raise APIError('组件不存在', 404)
        
    data = request.get_json(silent=True) or {}
    
    if 'title' in data:
        comp.title = data['title']
        
    if 'dataset_id' in data:
        ds_id = data['dataset_id']
        if ds_id is not None:
            dataset = db_session.get(Dataset, ds_id)
            if not dataset:
                raise APIError('指定的数据集不存在', 404)
        comp.dataset_id = ds_id
        
    if 'config' in data:
        config_data = data['config']
        if isinstance(config_data, dict):
            comp.config = json.dumps(config_data, ensure_ascii=False)
        else:
            comp.config = str(config_data)
            
    if 'position' in data:
        pos_data = data['position']
        if isinstance(pos_data, dict):
            comp.position = json.dumps(pos_data, ensure_ascii=False)
        else:
            comp.position = str(pos_data)
            
    db_session.commit()
    return jsonify(comp.to_dict())


@dashboards_bp.route('/api/components/<int:comp_id>', methods=['DELETE'])
def delete_component(comp_id):
    """删除看板组件"""
    comp = db_session.get(DashboardComponent, comp_id)
    if not comp:
        raise APIError('组件不存在', 404)
        
    db_session.delete(comp)
    db_session.commit()
    return jsonify({'message': '组件已成功删除'})


@dashboards_bp.route('/api/components/<int:comp_id>/data', methods=['GET'])
def get_component_data(comp_id):
    """获取组件解算后的最新数据，支持同看板内的联动过滤筛选"""
    comp = db_session.get(DashboardComponent, comp_id)
    if not comp:
        raise APIError('组件不存在', 404)
        
    df = None
    if comp.dataset_id:
        try:
            df = get_dataframe(comp.dataset_id)
        except Exception as e:
            raise APIError(f'读取数据集失败: {str(e)}', 500)
            
    filter_col = request.args.get('filter_col')
    filter_val = request.args.get('filter_val')
    
    strategy = ComponentDataStrategyFactory.get_strategy(comp.component_type)
    data = strategy.get_data(comp, df, filter_col=filter_col, filter_val=filter_val)
    return jsonify(data)
