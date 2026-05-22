# -*- coding: utf-8 -*-
"""
DataInsightHub 看板组件数据计算策略与外观服务
基于策略模式（Strategy Pattern）与工厂模式分发不同组件的数据计算逻辑
"""

import json
import logging
import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from core.exceptions import APIError
from services.preprocess_service import get_dataframe
from services.chart_service import trend_analysis, ChartBuilderFactory

def ensure_dict(config_val):
    """防御型解析，确保组件配置在多重 JSON 序列化下依然解析为 dict"""
    if not config_val:
        return {}
    if isinstance(config_val, dict):
        return config_val
    try:
        parsed = json.loads(config_val)
        while isinstance(parsed, str):
            parsed = json.loads(parsed)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {}


def exclude_summary_rows(df: pd.DataFrame) -> pd.DataFrame:
    """自动检测并排除包含“合计”、“总计”、“Total”字样的统计汇总行，防范财务加倍计算与图表失真"""
    if df is None or df.empty:
        return df
        
    mask = pd.Series(False, index=df.index)
    # 检测前 4 列中是否有包含“合计”、“总计”或“Total”字样的文本（忽略大小写，带去空格防御）
    for col in df.columns[:min(4, len(df.columns))]:
        if df[col].dtype == object or isinstance(df[col].dtype, pd.CategoricalDtype):
            col_str = df[col].astype(str).str.strip()
            mask = mask | col_str.str.contains('合计|总计|^total$', case=False, na=False)
            
    return df[~mask]


class ComponentDataStrategy(ABC):
    """组件数据计算抽象策略"""
    @abstractmethod
    def get_data(self, comp, df: pd.DataFrame, filter_col=None, filter_val=None):
        pass


class ChartDataStrategy(ComponentDataStrategy):
    """图表组件数据策略"""
    def get_data(self, comp, df: pd.DataFrame, filter_col=None, filter_val=None):
        # 卫语句：基本输入校验
        if df is None or df.empty:
            raise APIError("数据集为空，无法生成图表数据")
            
        # 0. 排除合计行和总计行，以防财务数据图表尺度失真
        df = exclude_summary_rows(df)
        if df.empty:
            raise APIError("排除汇总行后数据集为空")
            
        # 统一使用防御型配置转换器 ensure_dict
        config_dict = ensure_dict(comp.config)
        x_col = config_dict.get('x_col')
        y_col = config_dict.get('y_col')
        y2_col = config_dict.get('y2_col')
        
        if not x_col or not y_col:
            raise APIError("组件未配置 X 轴或 Y 轴字段", 400)

        # 卫语句：检验 Y 轴字段是否包含有效数值，防范非数值文本导致绘图渲染失败或无意义
        if y_col in df.columns:
            y_col_numeric = pd.to_numeric(df[y_col], errors='coerce')
            if y_col_numeric.isna().all():
                raise APIError(f"所选的 Y 轴字段 '{y_col}' 不包含有效的数值，无法生成图表，请重新选择数值列", 400)

        if y2_col and y2_col in df.columns:
            y2_col_numeric = pd.to_numeric(df[y2_col], errors='coerce')
            if y2_col_numeric.isna().all():
                raise APIError(f"所选的副轴 Y2 轴字段 '{y2_col}' 不包含有效的数值，无法生成图表，请重新选择数值列", 400)
            
        # 1. 组件联动筛选
        if filter_col and filter_val is not None:
            if filter_col in df.columns:
                df = df[df[filter_col].astype(str) == str(filter_val)]
                
        if df.empty:
            raise APIError("联动筛选后的数据集为空，无法生成图表")

        # 2. 构造虚拟 Chart 对象，以复用原 ChartBuilder 渲染逻辑
        from models.models import Chart
        mock_chart = Chart(
            id=comp.id,
            space_id=None,
            dataset_id=comp.dataset_id,
            name=comp.title or config_dict.get('title', '图表'),
            chart_type=config_dict.get('chart_type', 'scatter'),
            x_col=x_col,
            y_col=y_col,
            y2_col=y2_col,
            trend_enabled=config_dict.get('trend_enabled', False),
            config=json.dumps(config_dict, ensure_ascii=False)
        )

        # 3. WebGL 高性能渲染性能优化 (点数 > 5000)
        row_count = len(df)
        if row_count > 5000:
            if mock_chart.chart_type == 'scatter':
                mock_chart.chart_type = 'scattergl'
            elif mock_chart.chart_type == 'line':
                mock_chart.chart_type = 'scattergl'

        trend_result = None
        trend_info = None

        # 4. 一元线性回归趋势分析（仅限数值类型）
        if mock_chart.trend_enabled and mock_chart.chart_type in ('scatter', 'scattergl', 'line', 'bar'):
            if x_col in df.columns and y_col in df.columns:
                try:
                    # 强转并清洗，容忍少部分非数值脏数据，提供更稳健的回归拟合
                    x_parsed = pd.to_numeric(df[x_col], errors='coerce')
                    y_parsed = pd.to_numeric(df[y_col], errors='coerce')
                    
                    common = x_parsed.dropna().index.intersection(y_parsed.dropna().index)
                    x_vals = [float(v) for v in x_parsed.loc[common].tolist()]
                    y_vals = [float(v) for v in y_parsed.loc[common].tolist()]

                    if len(x_vals) >= 3:
                        trend_result = trend_analysis(x_vals, y_vals)
                except Exception as e:
                    logging.getLogger("excelany").error(f"趋势回归运算失败 (可能包含非数值文本): {e}")
                    trend_result = None

                if trend_result:
                    trend_info = {
                        'slope': round(trend_result.slope, 4),
                        'intercept': round(trend_result.intercept, 4),
                        'r2': round(trend_result.r2, 4),
                        'direction': trend_result.direction,
                        'predictions': [
                            {
                                'period': i + 1,
                                'x': round(trend_result.x_pred[i], 4),
                                'y_pred': round(trend_result.y_pred[i], 4)
                            }
                            for i in range(3)
                        ],
                        'data_points': [
                            {
                                'x': trend_result.x_orig[i],
                                'y': trend_result.y_orig[i],
                                'y_fit': trend_result.y_fit[i]
                            }
                            for i in range(len(trend_result.x_orig))
                        ]
                    }

        # 5. 调用工厂方法渲染 Plotly Figure
        fig = ChartBuilderFactory.build(df, mock_chart, trend_result)

        return {
            'chart_json': json.loads(fig.to_json()),
            'trend_info': trend_info
        }





class KPIDataStrategy(ComponentDataStrategy):
    """指标卡 KPI 数据策略"""
    def get_data(self, comp, df: pd.DataFrame, filter_col=None, filter_val=None):
        if df is None or df.empty:
            return {'value': 0, 'formatted_value': '无数据', 'title': comp.title}

        # 0. 过滤财务数据中合计行对聚合运算的干扰
        df = exclude_summary_rows(df)
        if df.empty:
            return {'value': 0, 'formatted_value': '无有效数据', 'title': comp.title}

        config_dict = ensure_dict(comp.config)
        kpi_col = config_dict.get('kpi_col')
        agg_method = config_dict.get('kpi_agg', 'sum')  # sum, mean, latest, count

        # 1. 组件联动过滤
        if filter_col and filter_val is not None:
            if filter_col in df.columns:
                df = df[df[filter_col].astype(str) == str(filter_val)]

        # 2. 字段校验与边界处理
        if not kpi_col or kpi_col not in df.columns:
            return {'value': None, 'formatted_value': '未选择字段', 'title': comp.title}

        series = df[kpi_col].dropna()
        if series.empty:
            return {'value': 0, 'formatted_value': '0', 'title': comp.title}

        # 3. 聚合逻辑分发（进行数值防错处理）
        decimals = int(config_dict.get('kpi_decimals', 2))
        unit = config_dict.get('kpi_unit', '')

        if agg_method == 'count':
            val = int(series.count())
            formatted = f"{val} 个"
        elif agg_method == 'latest':
            raw_val = series.iloc[-1]
            try:
                val = float(raw_val)
                formatted = f"{val:.{decimals}f} {unit}".strip()
            except (ValueError, TypeError):
                # 卫语句：如果是文本类型，原样返回作为文本指标展示，不强行转换为数值
                val = str(raw_val)
                formatted = val
        else:
            # 对于 sum 和 mean，首先将 series 尝试转换为数值型
            numeric_series = pd.to_numeric(series, errors='coerce').dropna()
            if numeric_series.empty:
                # 卫语句：完全无法数值计算的纯文本列做数值聚合，直接安全降级
                val = 0.0
                formatted = "非数值列无法聚合"
            else:
                if agg_method == 'mean':
                    val = float(numeric_series.mean())
                else:
                    # 默认或 sum 聚合
                    val = float(numeric_series.sum())
                formatted = f"{val:.{decimals}f} {unit}".strip()

        # 4. 指标颜色卡片设定支持
        threshold_val = config_dict.get('kpi_target')
        color_class = 'text-primary'  # 默认正常蓝
        if threshold_val is not None:
            try:
                target = float(threshold_val)
                if isinstance(val, (int, float)):
                    color_class = 'text-success' if val >= target else 'text-danger'
            except ValueError:
                pass

        return {
            'value': val,
            'formatted_value': formatted,
            'title': comp.title,
            'color_class': color_class
        }


class TableDataStrategy(ComponentDataStrategy):
    """数据表格组件策略"""
    def get_data(self, comp, df: pd.DataFrame, filter_col=None, filter_val=None):
        if df is None or df.empty:
            return {'columns': [], 'rows': []}

        # 0. 过滤合计行
        df = exclude_summary_rows(df)

        config_dict = ensure_dict(comp.config)

        # 1. 组件联动筛选
        if filter_col and filter_val is not None:
            if filter_col in df.columns:
                df = df[df[filter_col].astype(str) == str(filter_val)]

        # 2. 排序处理
        sort_col = config_dict.get('sort_col')
        sort_dir = config_dict.get('sort_dir', 'asc')
        if sort_col and sort_col in df.columns:
            df = df.sort_values(by=sort_col, ascending=(sort_dir == 'asc'))

        # 3. 数据清洁，将 NaN 替换为 None 防止 JSON 解析崩塌
        df_clean = df.where(pd.notnull(df), None)
        columns = df_clean.columns.tolist()
        
        # 4. 只返回最新的 2000 行（以确保页面流畅且无需过大开销，前台虚拟滚动渲染）
        rows = df_clean.to_dict(orient='records')

        return {
            'columns': columns,
            'rows': rows[:2000]
        }


class TextDataStrategy(ComponentDataStrategy):
    """富文本组件数据策略"""
    def get_data(self, comp, df: pd.DataFrame, filter_col=None, filter_val=None):
        config_dict = ensure_dict(comp.config)
        text_content = config_dict.get('text_content', '')
        return {
            'text_content': text_content
        }


class ComponentDataStrategyFactory:
    """看板组件数据策略工厂"""
    _strategies = {
        'chart': ChartDataStrategy(),
        'kpi': KPIDataStrategy(),
        'table': TableDataStrategy(),
        'text': TextDataStrategy()
    }

    @classmethod
    def get_strategy(cls, comp_type: str) -> ComponentDataStrategy:
        strategy = cls._strategies.get(comp_type)
        if not strategy:
            raise APIError(f"不支持的组件类型: {comp_type}", 400)
        return strategy
