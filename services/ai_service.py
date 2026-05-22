import logging
import numpy as np
from core.exceptions import APIError
from models.models import SpaceAIConfig, AIConfig, ChatHistory, Dataset
from services.preprocess_service import get_dataframe

# ---------------------------------------------------------------------------
# AI 问答与上下文外观模式 (Facade Pattern)
# ---------------------------------------------------------------------------
class PromptBuilder:
    """Prompt 拼装建造者"""
    @staticmethod
    def build_dataset_context(dataset, df) -> str:
        if df is None or df.empty:
            return ""
            
        col_info = ', '.join([f'{c}({str(df[c].dtype)})' for c in df.columns])
        preview = df.head(10).to_string()
        desc = df.describe().to_string() if len(df.select_dtypes(include=[np.number]).columns) > 0 else '无数值列'
        
        return (
            f'\n\n## 当前数据集: {dataset.name}\n'
            f'- 列信息: {col_info}\n'
            f'- 行数: {len(df)}\n'
            f'- 前 10 行数据:\n{preview}\n'
            f'- 描述性统计:\n{desc}\n'
        )


class OpenAIClientProxy:
    """API 调用网络通信代理"""
    def __init__(self, config):
        self.config = config

    def send_chat(self, messages: list) -> str:
        import requests as http_requests
        try:
            resp = http_requests.post(
                f"{self.config.base_url.rstrip('/')}/chat/completions",
                headers={
                    'Authorization': f'Bearer {self.config.api_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': self.config.model,
                    'messages': messages,
                    'max_tokens': self.config.max_tokens or 2000,
                    'temperature': self.config.temperature or 0.7
                },
                timeout=60
            )
            if resp.status_code != 200:
                raise APIError(f'AI 接口返回错误: {resp.status_code} - {resp.text[:200]}')
                
            data = resp.json()
            if 'choices' not in data or len(data['choices']) == 0:
                raise APIError('AI 接口未返回有效的 choices 节点')
                
            return data['choices'][0]['message']['content']
        except Exception as e:
            if isinstance(e, APIError):
                raise
            raise APIError(f'调用 AI 接口失败: {str(e)}')


class AIChatFacade:
    """AI 对话模块外观类"""
    def __init__(self, db_session):
        self.db = db_session

    def process_chat(self, space_id: int, message: str, dataset_id: int = None) -> tuple[str, int]:
        binding = self.db.query(SpaceAIConfig).filter_by(space_id=space_id).first()
        config = self.db.get(AIConfig, binding.ai_config_id) if binding else None
        
        if not config:
            config = self.db.query(AIConfig).filter_by(is_default=True).first()
            
        if not config:
            raise APIError('未配置 AI，请先在 AI 配置管理中添加配置并与空间绑定')

        user_msg = ChatHistory(space_id=space_id, role='user', content=message, dataset_id=dataset_id)
        self.db.add(user_msg)
        self.db.commit()

        system_prompt = config.system_prompt or '你是一个数据分析助手。'
        if dataset_id:
            try:
                ds = self.db.get(Dataset, dataset_id)
                if ds:
                    df = get_dataframe(dataset_id)
                    system_prompt += PromptBuilder.build_dataset_context(ds, df)
            except Exception as e:
                logger = logging.getLogger("excelany")
                logger.error(f'读取数据集失败: {str(e)}')

        messages = [{'role': 'system', 'content': system_prompt}]
        recent_history = self.db.query(ChatHistory).filter_by(space_id=space_id)\
            .order_by(ChatHistory.created_at.desc()).limit(20).all()
            
        for h in reversed(recent_history):
            messages.append({'role': h.role, 'content': h.content})
            
        if not messages or messages[-1]['role'] != 'user':
            messages.append({'role': 'user', 'content': message})

        proxy = OpenAIClientProxy(config)
        reply = proxy.send_chat(messages)

        ai_msg = ChatHistory(space_id=space_id, role='assistant', content=reply, dataset_id=dataset_id)
        self.db.add(ai_msg)
        self.db.commit()

        return reply, ai_msg.id
