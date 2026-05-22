import json
from abc import ABC, abstractmethod
from collections import namedtuple
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

# 命名元组：存储趋势分析结果
TrendResult = namedtuple('TrendResult', ['slope', 'intercept', 'r2', 'direction',
                                         'x_pred', 'y_pred', 'x_fit', 'y_fit',
                                         'x_orig', 'y_orig'])

def trend_analysis(x, y):
    """对 x, y 进行一元线性回归分析，返回 TrendResult"""
    x = np.array(x, dtype=float)
    y = np.array(y, dtype=float)

    # 清理 NaN / Inf
    mask = ~(np.isnan(x) | np.isnan(y) | np.isinf(x) | np.isinf(y))
    x = x[mask]
    y = y[mask]
    if len(x) < 3:
        return TrendResult(0, 0, 0, '平稳', [], [], [], [], x.tolist(), y.tolist())

    model = LinearRegression()
    model.fit(x.reshape(-1, 1), y)
    slope = float(model.coef_[0])
    intercept = float(model.intercept_)
    y_pred = model.predict(x.reshape(-1, 1))
    r2 = float(r2_score(y, y_pred))

    # 趋势方向判定
    if slope > 0.01:
        direction = '上升'
    elif slope < -0.01:
        direction = '下降'
    else:
        direction = '平稳'

    # 基于最后一步长外推未来 3 期预测
    if len(x) >= 2:
        step = (x[-1] - x[0]) / max(len(x) - 1, 1)
    else:
        step = 1
    x_pred = [x[-1] + step * (i + 1) for i in range(3)]
    y_pred_future = [float(model.predict([[xv]])[0]) for xv in x_pred]
    x_fit = x.tolist()
    y_fit = y_pred.tolist()

    return TrendResult(slope, intercept, r2, direction,
                       x_pred, y_pred_future, x_fit, y_fit,
                       x.tolist(), y.tolist())


# ---------------------------------------------------------------------------
# Plotly 图表构建工厂模式 & 建造者模式 (Factory & Builder Pattern)
# ---------------------------------------------------------------------------
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


class ChartBuilder(ABC):
    """图表构建建造者基类"""
    def __init__(self, df: pd.DataFrame, chart, trend_result=None):
        self.df = df
        self.chart = chart
        self.trend_result = trend_result
        self.fig = go.Figure()
        self.config = ensure_dict(chart.config)
        
        # 基础数据准备
        self.x_col = chart.x_col
        self.y_col = chart.y_col
        self.y2_col = chart.y2_col
        self.x_vals = []
        self.y_vals = []
        self.y2_vals = []
        self._prepare_data()

    def hex_to_rgba(self, hex_str, alpha=0.15):
        """将十六进制颜色转换为 RGBA，供渐变/半透明填充使用"""
        if not hex_str:
            return f"rgba(59, 130, 246, {alpha})"
        hex_str = hex_str.lstrip('#')
        if len(hex_str) == 3:
            hex_str = ''.join([c*2 for c in hex_str])
        try:
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            return f"rgba({r}, {g}, {b}, {alpha})"
        except Exception:
            return f"rgba(59, 130, 246, {alpha})"

    def _prepare_data(self):
        """清洗和匹配数据"""
        if not self.x_col or self.x_col not in self.df.columns:
            return
        if not self.y_col or self.y_col not in self.df.columns:
            return
            
        x_data = self.df[self.x_col].dropna()
        y_data = self.df[self.y_col].dropna()
        common = x_data.index.intersection(y_data.index)
        self.x_vals = x_data.loc[common].tolist()
        self.y_vals = y_data.loc[common].tolist()

        if self.y2_col and self.y2_col in self.df.columns:
            y2_data = self.df[self.y2_col].dropna()
            common2 = x_data.index.intersection(y2_data.index)
            self.y2_vals = y2_data.loc[common2].tolist()

    @abstractmethod
    def build_primary_trace(self):
        """构建主轴图表元素"""
        pass

    def build_secondary_trace(self):
        """构建副轴图表元素（如有必要）"""
        if not self.y2_vals:
            return
        chart_type = self.chart.chart_type or 'scatter'
        if chart_type not in ('scatter', 'line', 'bar', 'area'):
            return
            
        is_smooth = self.config.get('smooth', False)
        secondary_color = self.config.get('color2', '#f97316')
        self.fig.add_trace(go.Scatter(
            x=self.x_vals, y=self.y2_vals, mode='lines+markers',
            name=self.y2_col, yaxis='y2',
            line=dict(color=secondary_color, width=2.5, shape='spline' if is_smooth else 'linear'),
            marker=dict(color=secondary_color, size=6, line=dict(width=1, color='white'))
        ))

    def apply_decorations(self):
        """添加图表修饰（趋势线、均值线、回归方程信息框）"""
        # 1. 均值辅助线 (淡雅极简风)
        show_mean = self.config.get('show_mean', False)
        if show_mean and self.y_vals:
            valid_y = [v for v in self.y_vals if v is not None and isinstance(v, (int, float))]
            if valid_y:
                mean_val = float(np.mean(valid_y))
                self.fig.add_shape(
                    type="line", line=dict(color="#64748b", width=1.5, dash="dash"),
                    x0=0, x1=1, xref="paper", y0=mean_val, y1=mean_val, yref="y"
                )
                self.fig.add_annotation(
                    x=0.02, y=mean_val, xref="paper", yref="y",
                    text=f"均值: {mean_val:.2f}", showarrow=False,
                    font=dict(color="#475569", size=10, family='sans-serif'), 
                    bgcolor="rgba(255,255,255,0.9)", bordercolor="#cbd5e1", borderwidth=1,
                    yshift=10, xanchor="left"
                )
        
        # 2. 趋势线
        chart_type = self.chart.chart_type or 'scatter'
        if self.trend_result and self.chart.trend_enabled and chart_type in ('scatter', 'line', 'bar'):
            self.fig.add_trace(go.Scatter(
                x=self.trend_result.x_fit, y=self.trend_result.y_fit,
                mode='lines', name='趋势线',
                line=dict(color='#ef4444', dash='dashdot', width=2)
            ))
            
            # 3. 回归方程与 R² 的右上角信息框注解
            eq_text = f"回归方程: y = {self.trend_result.slope:.4f}x + {self.trend_result.intercept:.4f}<br>拟合优度 R² = {self.trend_result.r2:.4f}"
            self.fig.add_annotation(
                xref="paper", yref="paper",
                x=0.98, y=0.98,
                text=eq_text,
                showarrow=False,
                align="right",
                bgcolor="rgba(255, 255, 255, 0.9)",
                bordercolor="#e2e8f0",
                borderwidth=1,
                borderpad=6,
                font=dict(size=11, color="#334155", family='Consolas, "Microsoft YaHei", monospace')
            )

    def apply_layout(self):
        """布局参数配置（极致精细的坐标轴与悬停卡片）"""
        title = self.config.get('title', self.chart.name)
        x_label = self.config.get('x_label', self.x_col or '')
        y_label = self.config.get('y_label', self.y_col or '')
        
        layout_args = {
            'title': dict(text=title, x=0.5, font=dict(size=18, color='#0f172a', weight='bold')),
            'xaxis': dict(
                title=x_label, 
                gridcolor='#f1f5f9', 
                gridwidth=1,
                zerolinecolor='#e2e8f0',
                linecolor='#cbd5e1'
            ),
            'yaxis': dict(
                title=y_label, 
                gridcolor='#f1f5f9', 
                gridwidth=1,
                zerolinecolor='#e2e8f0',
                linecolor='#cbd5e1'
            ),
            'template': 'plotly_white',
            'hovermode': 'x unified',
            'hoverlabel': dict(
                bgcolor='rgba(255, 255, 255, 0.96)',
                bordercolor='#e2e8f0',
                font=dict(size=13, color='#1e293b', family='Inter, "Microsoft YaHei", sans-serif'),
                namelength=-1
            ),
            'margin': dict(l=60, r=60, t=80, b=60),
            'height': 450,
            'legend': dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            'plot_bgcolor': 'white',
            'paper_bgcolor': 'white',
            'barcornerradius': 5
        }

        if self.y2_vals:
            layout_args['yaxis2'] = dict(
                title=self.y2_col,
                overlaying='y',
                side='right',
                showgrid=False,
                zerolinecolor='#e2e8f0',
                linecolor='#cbd5e1'
            )

        self.fig.update_layout(**layout_args)

    def get_result(self) -> go.Figure:
        """运行完整构建流程"""
        self.build_primary_trace()
        self.build_secondary_trace()
        self.apply_decorations()
        self.apply_layout()
        return self.fig


class ScatterChartBuilder(ChartBuilder):
    def build_primary_trace(self):
        show_labels = self.config.get('show_labels', False)
        primary_color = self.config.get('color', '#3b82f6')
        self.fig.add_trace(go.Scatter(
            x=self.x_vals, y=self.y_vals, name=self.y_col,
            text=[f"{v}" for v in self.y_vals] if show_labels else None,
            textposition='top center' if show_labels else None,
            mode='markers+text' if show_labels else 'markers',
            marker=dict(color=primary_color, size=8, line=dict(width=1.5, color='white'))
        ))


class LineChartBuilder(ChartBuilder):
    def build_primary_trace(self):
        show_labels = self.config.get('show_labels', False)
        is_smooth = self.config.get('smooth', False)
        primary_color = self.config.get('color', '#3b82f6')
        self.fig.add_trace(go.Scatter(
            x=self.x_vals, y=self.y_vals, name=self.y_col,
            text=[f"{v}" for v in self.y_vals] if show_labels else None,
            textposition='top center' if show_labels else None,
            mode='lines+markers+text' if show_labels else 'lines+markers',
            line=dict(color=primary_color, width=3, shape='spline' if is_smooth else 'linear'),
            marker=dict(color=primary_color, size=6, line=dict(width=1.2, color='white'))
        ))


class BarChartBuilder(ChartBuilder):
    def build_primary_trace(self):
        show_labels = self.config.get('show_labels', False)
        primary_color = self.config.get('color', '#3b82f6')
        self.fig.add_trace(go.Bar(
            x=self.x_vals, y=self.y_vals, name=self.y_col,
            text=[f"{v}" for v in self.y_vals] if show_labels else None,
            textposition='auto' if show_labels else None,
            marker=dict(
                color=primary_color,
                line=dict(width=1, color=primary_color)
            )
        ))


class AreaChartBuilder(ChartBuilder):
    def build_primary_trace(self):
        show_labels = self.config.get('show_labels', False)
        is_smooth = self.config.get('smooth', False)
        primary_color = self.config.get('color', '#3b82f6')
        fill_color = self.hex_to_rgba(primary_color, 0.15)
        self.fig.add_trace(go.Scatter(
            x=self.x_vals, y=self.y_vals, name=self.y_col,
            text=[f"{v}" for v in self.y_vals] if show_labels else None,
            textposition='top center' if show_labels else None,
            mode='lines+text' if show_labels else 'lines',
            fill='tozeroy', 
            fillcolor=fill_color,
            line=dict(color=primary_color, width=2.5, shape='spline' if is_smooth else 'linear')
        ))


class BoxChartBuilder(ChartBuilder):
    def build_primary_trace(self):
        primary_color = self.config.get('color', '#3b82f6')
        y_data = self.df[self.y_col].dropna() if self.y_col in self.df.columns else []
        self.fig.add_trace(go.Box(
            y=y_data, name=self.y_col, marker_color=primary_color,
            boxpoints='outliers', line=dict(width=1.5)
        ))
        
    def build_secondary_trace(self):
        if self.y2_col and self.y2_col in self.df.columns:
            secondary_color = self.config.get('color2', '#f97316')
            self.fig.add_trace(go.Box(
                y=self.df[self.y2_col].dropna(), name=self.y2_col,
                marker_color=secondary_color, boxpoints='outliers', line=dict(width=1.5)
            ))


class PieChartBuilder(ChartBuilder):
    def build_primary_trace(self):
        if self.y2_col and self.y2_col in self.df.columns:
            labels = self.df[self.y2_col].dropna().unique()[:20]
            values = self.df.groupby(self.y2_col)[self.y_col].sum().values[:20]
        else:
            labels = self.x_vals[:20] if self.x_vals else []
            values = self.y_vals[:20] if self.y_vals else []
        self.fig.add_trace(go.Pie(
            labels=labels, values=values, name=self.chart.name,
            hole=0.1, marker=dict(line=dict(color='white', width=1.5))
        ))


class ChartBuilderFactory:
    """图表构建器工厂"""
    _builders = {
        'scatter': ScatterChartBuilder,
        'line': LineChartBuilder,
        'bar': BarChartBuilder,
        'area': AreaChartBuilder,
        'box': BoxChartBuilder,
        'pie': PieChartBuilder
    }

    @classmethod
    def build(cls, df: pd.DataFrame, chart, trend_result=None) -> go.Figure:
        chart_type = chart.chart_type or 'scatter'
        builder_cls = cls._builders.get(chart_type, ScatterChartBuilder)
        builder = builder_cls(df, chart, trend_result)
        return builder.get_result()
