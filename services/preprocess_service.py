import os
from abc import ABC, abstractmethod
import logging
import numpy as np
import pandas as pd
from core.database import db_session
from core.exceptions import APIError
from models.models import Dataset

# ---------------------------------------------------------------------------
# 1. 数据预处理策略模式 (Strategy Pattern)
# ---------------------------------------------------------------------------
class ImputeStrategy(ABC):
    """缺失值填充策略接口"""
    @abstractmethod
    def impute(self, df: pd.DataFrame) -> pd.DataFrame:
        pass

class DropImputeStrategy(ImputeStrategy):
    def impute(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.dropna()

class FFillImputeStrategy(ImputeStrategy):
    def impute(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.ffill()

class LinearImputeStrategy(ImputeStrategy):
    def impute(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.interpolate(method='linear')

class MeanImputeStrategy(ImputeStrategy):
    def impute(self, df: pd.DataFrame) -> pd.DataFrame:
        df_copy = df.copy()
        for col in df_copy.select_dtypes(include=[np.number]).columns:
            df_copy[col] = df_copy[col].fillna(df_copy[col].mean())
        return df_copy

class MedianImputeStrategy(ImputeStrategy):
    def impute(self, df: pd.DataFrame) -> pd.DataFrame:
        df_copy = df.copy()
        for col in df_copy.select_dtypes(include=[np.number]).columns:
            df_copy[col] = df_copy[col].fillna(df_copy[col].median())
        return df_copy

class DefaultImputeStrategy(ImputeStrategy):
    def impute(self, df: pd.DataFrame) -> pd.DataFrame:
        return df

class ImputeStrategyFactory:
    """缺失值处理策略工厂"""
    _strategies = {
        'drop': DropImputeStrategy(),
        'ffill': FFillImputeStrategy(),
        'linear': LinearImputeStrategy(),
        'mean': MeanImputeStrategy(),
        'median': MedianImputeStrategy()
    }

    @classmethod
    def get_strategy(cls, method: str) -> ImputeStrategy:
        if not method or method not in cls._strategies:
            return DefaultImputeStrategy()
        return cls._strategies[method]


# ---------------------------------------------------------------------------
# 2. 数据采样策略模式 (Strategy Pattern)
# ---------------------------------------------------------------------------
class SamplingStrategy(ABC):
    """数据采样策略接口"""
    @abstractmethod
    def sample(self, df: pd.DataFrame, n: int) -> pd.DataFrame:
        pass

class RandomSamplingStrategy(SamplingStrategy):
    def sample(self, df: pd.DataFrame, n: int) -> pd.DataFrame:
        if len(df) <= n:
            return df
        return df.sample(n=n, random_state=42)

class EquidistantSamplingStrategy(SamplingStrategy):
    def sample(self, df: pd.DataFrame, n: int) -> pd.DataFrame:
        if len(df) <= n:
            return df
        step = len(df) // n
        return df.iloc[::step]

class DefaultSamplingStrategy(SamplingStrategy):
    def sample(self, df: pd.DataFrame, n: int) -> pd.DataFrame:
        return df

class SamplingStrategyFactory:
    """采样策略工厂"""
    _strategies = {
        'random': RandomSamplingStrategy(),
        'equidistant': EquidistantSamplingStrategy()
    }

    @classmethod
    def get_strategy(cls, method: str) -> SamplingStrategy:
        if not method or method not in cls._strategies:
            return DefaultSamplingStrategy()
        return cls._strategies[method]


# ---------------------------------------------------------------------------
# 3. 数据集读取与应用预处理辅助函数
# ---------------------------------------------------------------------------
def get_file_size_mb(filepath):
    try:
        return os.path.getsize(filepath) / (1024 * 1024)
    except Exception:
        return 0

def get_dataframe(dataset_id):
    """根据 dataset_id 读取 DataFrame（应用已存储的预处理与采样策略选项）"""
    ds = db_session.get(Dataset, dataset_id)
    if not ds:
        raise APIError('数据集不存在', 404)
        
    file_ext = os.path.splitext(ds.file_path)[1].lower()
    if file_ext not in ('.xlsx', '.xls'):
        raise APIError('不支持的文件格式')
        
    file_size_mb = get_file_size_mb(ds.file_path)
    logger = logging.getLogger("excelany")
    
    # 超大文件分块读取（>100MB 仅读取前 50000 行，以确保低配置服务器稳定运行）
    if file_size_mb > 100:
        logger.info(f'大文件({file_size_mb:.0f}MB)采用分块读取策略')
        df = pd.read_excel(ds.file_path, sheet_name=ds.selected_sheet or 0, engine='openpyxl', nrows=50000)
    else:
        df = pd.read_excel(ds.file_path, sheet_name=ds.selected_sheet or 0, engine='openpyxl')
        
    # 应用已存储的预处理选项
    import json
    opts = json.loads(ds.preprocessing_options) if ds.preprocessing_options else {}
    
    # 缺失值填充 (应用策略模式)
    missing_method = opts.get('missing')
    imputer = ImputeStrategyFactory.get_strategy(missing_method)
    df = imputer.impute(df)
    
    # 数据采样 (应用策略模式)
    sampling = opts.get('sampling')
    if sampling and isinstance(sampling, dict):
        sampling_method = sampling.get('method')
        n = int(sampling.get('n', 50000))
        sampler = SamplingStrategyFactory.get_strategy(sampling_method)
        df = sampler.sample(df, n)
        
    # 日期列转数值特征，辅助拟合运算
    x_type = opts.get('x_type')
    x_col = opts.get('x_col')
    if x_type == 'timestamp' and x_col and x_col in df.columns:
        df[x_col + '_num'] = pd.to_datetime(df[x_col]).astype(np.int64) // 10**9
        
    return df
