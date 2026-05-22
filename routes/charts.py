import os
import json
import pandas as pd
import threading
from flask import Blueprint, jsonify, request, send_file
from core.database import db_session, UPLOAD_FOLDER
from core.exceptions import APIError
from models.models import Chart, Space, Dataset
from services.preprocess_service import get_dataframe
from services.chart_service import trend_analysis, ChartBuilderFactory
import plotly.io as pio

# ---------------------------------------------------------------------------
# 性能优化：禁用 GPU 硬件加速并预热 Kaleido 常驻渲染进程
# ---------------------------------------------------------------------------
os.environ["KALEIDO_DISABLE_GPU"] = "1"
os.environ["plotly_kaleido_disable_gpu"] = "True"

def _preheat_kaleido_scope():
    """在后台线程中预热并初始化全局 Kaleido 常驻进程"""
    try:
        # 仅仅触碰属性即会激发单例 Scope 进程冷启动
        _ = pio.kaleido.scope
    except Exception:
        pass

threading.Thread(target=_preheat_kaleido_scope, daemon=True).start()


charts_bp = Blueprint('charts', __name__)


@charts_bp.route('/api/spaces/<int:space_id>/charts', methods=['POST'])
def create_chart(space_id):
    """保存或新增图表，使用卫语句对必填项进行边界防御"""
    check_space = db_session.get(Space, space_id)
    if not check_space:
        raise APIError('空间不存在', 404)

    data = request.get_json(silent=True) or {}
    name = data.get('name')
    if not name:
        raise APIError('缺少 name 参数', 400)

    chart_type = data.get('chart_type', 'scatter')
    x_col = data.get('x_col')
    y_col = data.get('y_col')
    y2_col = data.get('y2_col')
    trend_enabled = data.get('trend_enabled', True)
    config_val = data.get('config')

    # 转换 config 为字符串存储
    if isinstance(config_val, dict):
        config_str = json.dumps(config_val, ensure_ascii=False)
    else:
        config_str = config_val

    dataset_id = data.get('dataset_id')
    if not dataset_id:
        # 默认使用该空间下最新上传的数据集
        latest_dataset = db_session.query(Dataset).filter_by(space_id=space_id).order_by(Dataset.uploaded_at.desc()).first()
        if not latest_dataset:
            raise APIError('空间内没有可用的数据集，请先上传数据', 400)
        dataset_id = latest_dataset.id
    else:
        dataset = db_session.get(Dataset, dataset_id)
        if not dataset or dataset.space_id != space_id:
            raise APIError('指定的数据集不存在或不属于该空间', 400)

    chart = Chart(
        space_id=space_id,
        dataset_id=dataset_id,
        name=name,
        chart_type=chart_type,
        x_col=x_col,
        y_col=y_col,
        y2_col=y2_col,
        trend_enabled=trend_enabled,
        config=config_str
    )
    db_session.add(chart)
    db_session.commit()

    return jsonify(chart.to_dict()), 201


@charts_bp.route('/api/charts/<int:chart_id>', methods=['PUT'])
def update_chart(chart_id):
    """更新图表配置信息"""
    chart = db_session.get(Chart, chart_id)
    if not chart:
        raise APIError('图表不存在', 404)
        
    data = request.get_json(silent=True) or {}
    if 'name' in data:
        chart.name = data['name']
    if 'chart_type' in data:
        chart.chart_type = data['chart_type']
    if 'x_col' in data:
        chart.x_col = data['x_col']
    if 'y_col' in data:
        chart.y_col = data['y_col']
    if 'y2_col' in data:
        chart.y2_col = data['y2_col']
    if 'trend_enabled' in data:
        chart.trend_enabled = data['trend_enabled']
    if 'config' in data:
        chart.config = json.dumps(data['config'], ensure_ascii=False)
        
    db_session.commit()
    return jsonify(chart.to_dict())


@charts_bp.route('/api/charts/<int:chart_id>', methods=['DELETE'])
def delete_chart(chart_id):
    """删除指定的分析图表配置"""
    chart = db_session.get(Chart, chart_id)
    if not chart:
        raise APIError('图表不存在', 404)
        
    db_session.delete(chart)
    db_session.commit()
    return jsonify({'message': '已删除'})


@charts_bp.route('/api/charts/<int:chart_id>/render', methods=['GET'])
def render_chart(chart_id):
    """图表渲染逻辑（返回自适应 Plotly 布局 JSON，带有拟合方程）"""
    chart = db_session.get(Chart, chart_id)
    if not chart:
        raise APIError('图表不存在', 404)
        
    try:
        df = get_dataframe(chart.dataset_id)
    except Exception as e:
        raise APIError(f'读取数据失败: {str(e)}')

    trend_result = None
    trend_info = None
    
    # 检测是否能开展线性拟合分析
    if chart.trend_enabled and chart.chart_type in ('scatter', 'line', 'bar'):
        x_col = chart.x_col
        y_col = chart.y_col
        if x_col and y_col and x_col in df.columns and y_col in df.columns:
            x_data = df[x_col].dropna()
            y_data = df[y_col].dropna()
            common = x_data.index.intersection(y_data.index)
            x_vals = x_data.loc[common].tolist()
            y_vals = y_data.loc[common].tolist()
            
            if len(x_vals) >= 3:
                try:
                    trend_result = trend_analysis(x_vals, y_vals)
                except Exception:
                    trend_result = None
                    
                if trend_result:
                    trend_info = {
                        'slope': round(trend_result.slope, 4),
                        'intercept': round(trend_result.intercept, 4),
                        'r2': round(trend_result.r2, 4),
                        'direction': trend_result.direction,
                        'predictions': [
                            {'period': i+1, 'x': round(trend_result.x_pred[i], 4),
                             'y_pred': round(trend_result.y_pred[i], 4)}
                            for i in range(3)
                        ],
                        'data_points': [
                            {'x': trend_result.x_orig[i], 'y': trend_result.y_orig[i],
                             'y_fit': trend_result.y_fit[i]}
                            for i in range(len(trend_result.x_orig))
                        ]
                    }

    fig = ChartBuilderFactory.build(df, chart, trend_result)
    
    return jsonify({
        'chart_json': json.loads(fig.to_json()),
        'chart_data': chart.to_dict(),
        'trend_info': trend_info
    })


@charts_bp.route('/api/charts/<int:chart_id>/export-csv', methods=['GET'])
def export_chart_csv(chart_id):
    """导出图表线性拟合的详细预测与偏差 CSV"""
    chart = db_session.get(Chart, chart_id)
    if not chart:
        raise APIError('图表不存在', 404)
        
    try:
        df = get_dataframe(chart.dataset_id)
    except Exception as e:
        raise APIError(f'读取数据失败: {str(e)}')
        
    x_col, y_col = chart.x_col, chart.y_col
    if not x_col or not y_col or x_col not in df.columns or y_col not in df.columns:
        raise APIError('选定坐标列在数据中不存在')
        
    x_data = df[x_col].dropna()
    y_data = df[y_col].dropna()
    common = x_data.index.intersection(y_data.index)
    x_vals = x_data.loc[common].tolist()
    y_vals = y_data.loc[common].tolist()

    if len(x_vals) >= 3:
        try:
            tr = trend_analysis(x_vals, y_vals)
        except Exception:
            tr = None
            
        if tr:
            out_df = pd.DataFrame({
                '数据点类型': ['原始数据'] * len(tr.x_orig),
                'X (自变量)': tr.x_orig,
                'Y (观测值)': tr.y_orig,
                'Y_fit (拟合值)': tr.y_fit,
                '偏差 (残差)': [round(y_o - y_f, 4) for y_o, y_f in zip(tr.y_orig, tr.y_fit)]
            })
            pred_df = pd.DataFrame({
                '数据点类型': ['未来预测'] * len(tr.x_pred),
                'X (自变量)': tr.x_pred,
                'Y (观测值)': [''] * len(tr.x_pred),
                'Y_fit (拟合值)': tr.y_pred,
                '偏差 (残差)': [''] * len(tr.x_pred)
            })
            out_df = pd.concat([out_df, pred_df], ignore_index=True)
        else:
            out_df = pd.DataFrame({
                '数据点类型': ['原始数据'] * len(x_vals),
                'X (自变量)': x_vals,
                'Y (观测值)': y_vals
            })
    else:
        out_df = pd.DataFrame({'X': x_vals, 'Y': y_vals, 'Y_fit': ['']*len(x_vals)})

    csv_path = os.path.join(UPLOAD_FOLDER, f'chart_{chart_id}_trend.csv')
    out_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    return send_file(csv_path, mimetype='text/csv',
                     as_attachment=True,
                     download_name=f'{chart.name}_趋势分析.csv')


@charts_bp.route('/api/charts/<int:chart_id>/export-image', methods=['GET', 'POST'])
def export_chart_image(chart_id):
    """使用 Plotly 的 kaleido 引擎渲染并导出静态 PNG 图片"""
    chart = db_session.get(Chart, chart_id)
    if not chart:
        raise APIError('图表不存在', 404)
        
    try:
        df = get_dataframe(chart.dataset_id)
    except Exception as e:
        raise APIError(f'读取数据失败: {str(e)}')

    trend_result = None
    if chart.trend_enabled and chart.chart_type in ('scatter', 'line', 'bar'):
        x_col, y_col = chart.x_col, chart.y_col
        if x_col and y_col and x_col in df.columns and y_col in df.columns:
            x_data = df[x_col].dropna()
            y_data = df[y_col].dropna()
            common = x_data.index.intersection(y_data.index)
            x_vals = x_data.loc[common].tolist()
            y_vals = y_data.loc[common].tolist()
            
            if len(x_vals) >= 3:
                try:
                    trend_result = trend_analysis(x_vals, y_vals)
                except Exception:
                    trend_result = None

    fig = ChartBuilderFactory.build(df, chart, trend_result)
    fig.update_layout(
        font=dict(family='SimHei, "Microsoft YaHei", sans-serif', size=14),
        title_font=dict(size=20)
    )
    img_path = os.path.join(UPLOAD_FOLDER, f'chart_{chart_id}.png')
    fig.write_image(img_path, format='png', width=1000, height=600, scale=2)
    return send_file(img_path, mimetype='image/png',
                     as_attachment=True,
                     download_name=f'{chart.name}_数据分析图.png')
