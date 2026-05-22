import os
import sys
import logging
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker, scoped_session

# 获取应用数据目录（exe 所在目录或项目根目录）
def get_app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    # 因为 database.py 在 core/ 下，所以返回上一级目录作为项目根目录
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

APP_DIR = get_app_dir()
DB_PATH = os.path.join(APP_DIR, 'excelany.db')
UPLOAD_FOLDER = os.path.join(APP_DIR, 'uploads')
LOG_FOLDER = os.path.join(APP_DIR, 'logs')
BACKUP_FOLDER = os.path.join(APP_DIR, 'backup')

# 确保核心文件夹存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(LOG_FOLDER, exist_ok=True)
os.makedirs(BACKUP_FOLDER, exist_ok=True)

# 声明 SQLAlchemy 基类
class Base(DeclarativeBase):
    pass

# 初始化 Engine & Session
engine = create_engine(
    f'sqlite:///{DB_PATH}',
    echo=False,
    connect_args={'check_same_thread': False}
)
db_session = scoped_session(sessionmaker(bind=engine))

def init_db(app=None):
    """初始化数据库，创建所有表，并同步缺失的列"""
    logger = app.logger if app else logging.getLogger(__name__)
    
    # 动态导入所有模型，确保 metadata 完整加载，从而正常 create_all
    from models.models import (
        Space, Dataset, Chart, AIConfig, SpaceAIConfig, ChatHistory, AnalysisNote,
        Dashboard, DashboardComponent
    )
    
    Base.metadata.create_all(bind=engine)
    
    # 数据库自省与列增量同步逻辑
    inspector = inspect(engine)
    if 'ai_config' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('ai_config')]
        if 'cached_models' not in columns:
            logger.info("正在同步数据库：为 ai_config 表添加 cached_models 列")
            try:
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE ai_config ADD COLUMN cached_models TEXT DEFAULT '[]'"))
                    conn.commit()
            except Exception as e:
                logger.error(f"同步 ai_config 表失败: {e}")
