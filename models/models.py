import json
from datetime import datetime
from sqlalchemy import (Column, Integer, String, Float, Boolean, DateTime,
                        Text, ForeignKey)
from sqlalchemy.orm import relationship
from core.database import Base

class Space(Base):
    """空间/工作区"""
    __tablename__ = 'space'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, default='新空间')
    created_at = Column(DateTime, default=datetime.utcnow)

    datasets = relationship('Dataset', back_populates='space', cascade='all, delete-orphan')
    charts = relationship('Chart', back_populates='space', cascade='all, delete-orphan')
    chat_histories = relationship('ChatHistory', back_populates='space', cascade='all, delete-orphan')
    notes = relationship('AnalysisNote', back_populates='space', cascade='all, delete-orphan')
    space_ai_configs = relationship('SpaceAIConfig', back_populates='space', cascade='all, delete-orphan')
    dashboards = relationship('Dashboard', back_populates='space', cascade='all, delete-orphan')

    def to_dict(self):
        binding = self.space_ai_configs[0] if self.space_ai_configs else None
        return {
            'id': self.id, 
            'name': self.name, 
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'ai_config_id': binding.ai_config_id if binding else None
        }


class Dataset(Base):
    """数据集"""
    __tablename__ = 'dataset'
    id = Column(Integer, primary_key=True, autoincrement=True)
    space_id = Column(Integer, ForeignKey('space.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(100), nullable=False)
    file_path = Column(String(200), nullable=False)
    selected_sheet = Column(String(100), nullable=True)
    preprocessing_options = Column(Text, nullable=True)  # JSON
    row_count = Column(Integer, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    space = relationship('Space', back_populates='datasets')
    charts = relationship('Chart', back_populates='dataset', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id, 'space_id': self.space_id, 'name': self.name,
            'file_path': self.file_path, 'selected_sheet': self.selected_sheet,
            'preprocessing_options': self.preprocessing_options,
            'row_count': self.row_count,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None
        }


class Chart(Base):
    """图表"""
    __tablename__ = 'chart'
    id = Column(Integer, primary_key=True, autoincrement=True)
    space_id = Column(Integer, ForeignKey('space.id', ondelete='CASCADE'), nullable=False)
    dataset_id = Column(Integer, ForeignKey('dataset.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(100), nullable=False)
    chart_type = Column(String(20), default='scatter')
    x_col = Column(String(50), nullable=True)
    y_col = Column(String(50), nullable=True)
    y2_col = Column(String(50), nullable=True)
    trend_enabled = Column(Boolean, default=True)
    config = Column(Text, nullable=True)  # JSON: { title, x_label, y_label, color }
    created_at = Column(DateTime, default=datetime.utcnow)

    space = relationship('Space', back_populates='charts')
    dataset = relationship('Dataset', back_populates='charts')

    def to_dict(self):
        return {
            'id': self.id, 'space_id': self.space_id, 'dataset_id': self.dataset_id,
            'name': self.name, 'chart_type': self.chart_type,
            'x_col': self.x_col, 'y_col': self.y_col, 'y2_col': self.y2_col,
            'trend_enabled': bool(self.trend_enabled), 'config': self.config,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class AIConfig(Base):
    """AI 配置"""
    __tablename__ = 'ai_config'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    base_url = Column(String(200), nullable=False)
    api_key = Column(String(200), nullable=False)
    model = Column(String(100), nullable=False)
    system_prompt = Column(Text, nullable=True)
    max_tokens = Column(Integer, default=2000)
    temperature = Column(Float, default=0.7)
    is_default = Column(Boolean, default=False)
    cached_models = Column(Text, nullable=True, default='[]')

    space_ai_configs = relationship('SpaceAIConfig', back_populates='ai_config', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'base_url': self.base_url,
            'api_key': self.api_key, 'model': self.model,
            'system_prompt': self.system_prompt, 'max_tokens': self.max_tokens,
            'temperature': self.temperature, 'is_default': bool(self.is_default),
            'cached_models': json.loads(self.cached_models) if self.cached_models else []
        }


class SpaceAIConfig(Base):
    """空间 - AI 配置关联"""
    __tablename__ = 'space_ai_config'
    id = Column(Integer, primary_key=True, autoincrement=True)
    space_id = Column(Integer, ForeignKey('space.id', ondelete='CASCADE'), nullable=False)
    ai_config_id = Column(Integer, ForeignKey('ai_config.id', ondelete='CASCADE'), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)

    space = relationship('Space', back_populates='space_ai_configs')
    ai_config = relationship('AIConfig', back_populates='space_ai_configs')

    def to_dict(self):
        return {
            'id': self.id, 'space_id': self.space_id,
            'ai_config_id': self.ai_config_id,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class ChatHistory(Base):
    """聊天记录"""
    __tablename__ = 'chat_history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    space_id = Column(Integer, ForeignKey('space.id', ondelete='CASCADE'), nullable=False)
    role = Column(String(20), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    dataset_id = Column(Integer, ForeignKey('dataset.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    space = relationship('Space', back_populates='chat_histories')

    def to_dict(self):
        return {
            'id': self.id, 'space_id': self.space_id, 'role': self.role,
            'content': self.content, 'dataset_id': self.dataset_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class AnalysisNote(Base):
    """分析笔记"""
    __tablename__ = 'analysis_note'
    id = Column(Integer, primary_key=True, autoincrement=True)
    space_id = Column(Integer, ForeignKey('space.id', ondelete='CASCADE'), nullable=False)
    title = Column(String(200), nullable=True)
    content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    space = relationship('Space', back_populates='notes')

    def to_dict(self):
        return {
            'id': self.id, 'space_id': self.space_id, 'title': self.title,
            'content': self.content,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Dashboard(Base):
    """看板"""
    __tablename__ = 'dashboard'
    id = Column(Integer, primary_key=True, autoincrement=True)
    space_id = Column(Integer, ForeignKey('space.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(100), nullable=False, default='新看板')
    layout = Column(Text, nullable=True, default='[]')  # JSON
    refresh_interval = Column(Integer, default=0)  # 秒，0表示不自动刷新
    created_at = Column(DateTime, default=datetime.utcnow)

    space = relationship('Space', back_populates='dashboards')
    components = relationship('DashboardComponent', back_populates='dashboard', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'space_id': self.space_id,
            'name': self.name,
            'layout': json.loads(self.layout) if self.layout else [],
            'refresh_interval': self.refresh_interval,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class DashboardComponent(Base):
    """看板组件"""
    __tablename__ = 'dashboard_component'
    id = Column(Integer, primary_key=True, autoincrement=True)
    dashboard_id = Column(Integer, ForeignKey('dashboard.id', ondelete='CASCADE'), nullable=False)
    component_type = Column(String(20), nullable=False)  # 'chart', 'kpi', 'table', 'text'
    dataset_id = Column(Integer, ForeignKey('dataset.id', ondelete='SET NULL'), nullable=True)
    title = Column(String(200), nullable=True)
    config = Column(Text, nullable=True, default='{}')   # JSON
    position = Column(Text, nullable=True, default='{}') # JSON: {x, y, w, h}
    created_at = Column(DateTime, default=datetime.utcnow)

    dashboard = relationship('Dashboard', back_populates='components')
    dataset = relationship('Dataset')

    def to_dict(self):
        return {
            'id': self.id,
            'dashboard_id': self.dashboard_id,
            'component_type': self.component_type,
            'dataset_id': self.dataset_id,
            'title': self.title,
            'config': json.loads(self.config) if self.config else {},
            'position': json.loads(self.position) if self.position else {},
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
