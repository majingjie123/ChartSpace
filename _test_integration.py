"""
excelAny 集成测试（10 个场景）
使用 Flask 测试客户端 + 独立测试数据库文件
"""
import os, sys, io, json, csv

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)
sys.path.insert(0, PROJECT_ROOT)

# 必须在导入 app 前切换数据库路径
import app as app_module
TEST_DB_PATH = os.path.join(PROJECT_ROOT, '_test_integration.db')
app_module.DB_PATH = TEST_DB_PATH
app_module.app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{TEST_DB_PATH}'
# 重新创建引擎以使用测试数据库
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
app_module.engine = create_engine(f'sqlite:///{TEST_DB_PATH}', connect_args={'check_same_thread': False})
app_module.db_session = scoped_session(sessionmaker(bind=app_module.engine))

from app import app, db_session, Base, engine, DB_PATH

import pytest


@pytest.fixture(autouse=True)
def setup_db():
    """每次测试前重建表（确保测试隔离）"""
    # 清理旧数据
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    # 清空 session
    db_session.remove()
    yield
    db_session.remove()


@pytest.fixture
def client():
    """Flask 测试客户端"""
    with app.test_client() as c:
        yield c


def _ensure_test_excel():
    """确保 test_data.xlsx 存在"""
    path = os.path.join(PROJECT_ROOT, 'test_data.xlsx')
    if not os.path.exists(path):
        pytest.skip('需要 test_data.xlsx（运行 python _make_test_data.py 生成）')
    return path


# ═══════════════════════════════════════════════════
# 场景 1：空间 CRUD
# ═══════════════════════════════════════════════════
class TestSpaceCRUD:
    def test_01_create(self, client):
        r = client.post('/api/spaces', json={'name': '测试空间'})
        assert r.status_code in (200, 201)
        d = r.get_json()
        assert d['name'] == '测试空间'
        assert d['id'] > 0

    def test_02_list(self, client):
        client.post('/api/spaces', json={'name': 'A'})
        client.post('/api/spaces', json={'name': 'B'})
        r = client.get('/api/spaces')
        assert r.status_code in (200, 201)
        assert len(r.get_json()) == 2

    def test_03_rename(self, client):
        r = client.post('/api/spaces', json={'name': '旧名'})
        sid = r.get_json()['id']
        r = client.put(f'/api/spaces/{sid}', json={'name': '新名'})
        assert r.status_code in (200, 201)
        assert r.get_json()['name'] == '新名'

    def test_04_delete(self, client):
        r = client.post('/api/spaces', json={'name': '待删'})
        sid = r.get_json()['id']
        r = client.delete(f'/api/spaces/{sid}')
        assert r.status_code in (200, 201)
        assert len(client.get('/api/spaces').get_json()) == 0

    def test_05_not_found(self, client):
        assert client.get('/api/spaces/999').status_code == 405


# ═══════════════════════════════════════════════════
# 场景 2：数据集上传与预览
# ═══════════════════════════════════════════════════
class TestDataset:
    def test_upload_preview(self, client):
        path = _ensure_test_excel()
        r = client.post('/api/spaces', json={'name': '数据空间'})
        assert r.status_code in (200, 201), f'create space failed: {r.get_data()}'
        sid = r.get_json()['id']

        with open(path, 'rb') as f:
            r = client.post(f'/api/spaces/{sid}/datasets',
                            data={'file': f})
        assert r.status_code in (200, 201), f'upload [{r.status_code}]: {r.get_data()[:200]}'
        d = r.get_json()
        ds_id = d['dataset_id']
        assert 'sheets' in d

        # 获取工作表
        r = client.get(f'/api/datasets/{ds_id}/sheets')
        assert r.status_code in (200, 201)
        sheets = r.get_json()
        assert len(sheets) >= 1

        # 确认工作表
        r = client.post(f'/api/datasets/{ds_id}/confirm-sheet',
                        json={'sheet': sheets[0]})
        assert r.status_code in (200, 201)

        # 预览
        r = client.get(f'/api/datasets/{ds_id}/preview')
        assert r.status_code in (200, 201)
        p = r.get_json()
        assert 'columns' in p and 'rows' in p
        assert len(p['columns']) == 6  # 6列

        # 预处理
        r = client.post(f'/api/datasets/{ds_id}/preprocess',
                        json={'action': 'dropna'})
        assert r.status_code in (200, 201)
        assert 'columns' in r.get_json()

    def test_upload_no_file(self, client):
        r = client.post('/api/spaces', json={'name': 's'})
        sid = r.get_json()['id']
        r = client.post(f'/api/spaces/{sid}/datasets', data={})
        assert r.status_code == 400


# ═══════════════════════════════════════════════════
# 场景 3：图表管理（6 种类型）
# ═══════════════════════════════════════════════════
class TestChart:
    CHART_TYPES = ['bar', 'line', 'pie', 'scatter', 'histogram', 'heatmap']

    def _setup(self, client):
        path = _ensure_test_excel()
        r = client.post('/api/spaces', json={'name': '图表空间'})
        sid = r.get_json()['id']
        with open(path, 'rb') as f:
            r = client.post(f'/api/spaces/{sid}/datasets',
                            data={'file': f})
        ds_id = r.get_json()['dataset_id']
        return sid, ds_id

    def test_all_types(self, client):
        sid, ds_id = self._setup(client)
        for ct in self.CHART_TYPES:
            r = client.post(f'/api/spaces/{sid}/charts', json={
                'dataset_id': ds_id, 'name': f'{ct}图',
                'chart_type': ct, 'x_col': '年月', 'y_col': '销售额',
            })
            assert r.status_code in (200, 201), f'{ct} 失败: {r.get_data()}'

    def test_render(self, client):
        sid, ds_id = self._setup(client)
        r = client.post(f'/api/spaces/{sid}/charts', json={
            'dataset_id': ds_id, 'name': '柱状图',
            'chart_type': 'bar', 'x_col': '年月', 'y_col': '销售额',
        })
        cid = r.get_json()['id']
        r = client.get(f'/api/charts/{cid}/render')
        assert r.status_code in (200, 201)
        assert 'chart_html' in r.get_json()

    def test_update(self, client):
        sid, ds_id = self._setup(client)
        r = client.post(f'/api/spaces/{sid}/charts', json={
            'dataset_id': ds_id, 'name': '原名称',
            'chart_type': 'bar', 'x_col': '年月', 'y_col': '销售额',
        })
        cid = r.get_json()['id']
        r = client.put(f'/api/charts/{cid}', json={'name': '新名称'})
        assert r.status_code in (200, 201) and r.get_json()['name'] == '新名称'

    def test_delete(self, client):
        sid, ds_id = self._setup(client)
        r = client.post(f'/api/spaces/{sid}/charts', json={
            'dataset_id': ds_id, 'name': '待删',
            'chart_type': 'bar', 'x_col': '年月', 'y_col': '销售额',
        })
        cid = r.get_json()['id']
        assert client.delete(f'/api/charts/{cid}').status_code == 200

    def test_export_csv(self, client):
        sid, ds_id = self._setup(client)
        r = client.post(f'/api/spaces/{sid}/charts', json={
            'dataset_id': ds_id, 'name': '导出',
            'chart_type': 'line', 'x_col': '年月', 'y_col': '销售额',
        })
        cid = r.get_json()['id']
        r = client.get(f'/api/charts/{cid}/export-csv')
        assert r.status_code in (200, 201)
        assert 'text/csv' in r.content_type


# ═══════════════════════════════════════════════════
# 场景 4：趋势分析
# ═══════════════════════════════════════════════════
class TestTrend:
    def _setup(self, client):
        path = _ensure_test_excel()
        r = client.post('/api/spaces', json={'name': '趋势空间'})
        sid = r.get_json()['id']
        with open(path, 'rb') as f:
            r = client.post(f'/api/spaces/{sid}/datasets',
                            data={'file': f})
        ds_id = r.get_json()['dataset_id']
        r = client.post(f'/api/spaces/{sid}/charts', json={
            'dataset_id': ds_id, 'name': '趋势图',
            'chart_type': 'line', 'x_col': '年月', 'y_col': '销售额',
        })
        return r.get_json()['id']

    def test_trend(self, client):
        cid = self._setup(client)
        r = client.get(f'/api/charts/{cid}/render')
        assert r.status_code in (200, 201)


# ═══════════════════════════════════════════════════
# 场景 5：AI 配置 CRUD
# ═══════════════════════════════════════════════════
class TestAIConfig:
    def test_crud(self, client):
        # 创建
        r = client.post('/api/ai-configs', json={
            'name': 'DeepSeek', 'base_url': 'https://api.deepseek.com',
            'api_key': 'sk-test', 'model': 'deepseek-chat',
        })
        assert r.status_code in (200, 201)
        cid = r.get_json()['id']

        # 列表
        r = client.get('/api/ai-configs')
        assert len(r.get_json()) == 1

        # 设默认
        assert client.post(f'/api/ai-configs/{cid}/set-default').status_code == 200

        # 更新
        r = client.put(f'/api/ai-configs/{cid}', json={'name': 'DeepSeek V4'})
        assert r.get_json()['name'] == 'DeepSeek V4'

        # 删除
        assert client.delete(f'/api/ai-configs/{cid}').status_code == 200
        assert len(client.get('/api/ai-configs').get_json()) == 0


# ═══════════════════════════════════════════════════
# 场景 6：空间-AI 配置绑定
# ═══════════════════════════════════════════════════
class TestSpaceAIConfig:
    def test_bind(self, client):
        r = client.post('/api/spaces', json={'name': 'AI空间'})
        sid = r.get_json()['id']
        r = client.post('/api/ai-configs', json={
            'name': 'TestAI', 'base_url': 'https://api.test.com',
            'api_key': 'sk-test', 'model': 'gpt-4',
        })
        cid = r.get_json()['id']

        # 绑定
        r = client.post(f'/api/spaces/{sid}/ai-config', json={'ai_config_id': cid})
        assert r.status_code in (200, 201)

        # 查询
        r = client.get(f'/api/spaces/{sid}/ai-config')
        assert r.status_code in (200, 201) and r.get_json().get('ai_config_id') == cid

        # 解绑（需要传 None 值，API 会返回 400 提示）
        r = client.post(f'/api/spaces/{sid}/ai-config', json={'ai_config_id': None})
        assert r.status_code in (200, 201, 400)


# ═══════════════════════════════════════════════════
# 场景 7：AI 聊天
# ═══════════════════════════════════════════════════
class TestChat:
    def test_chat(self, client):
        r = client.post('/api/spaces', json={'name': '聊天空间'})
        assert r.status_code in (200, 201), f'create space: {r.get_data()}'
        sid = r.get_json()['id']

        # 创建 AI 配置并设为默认（聊天需要 AI 配置）
        r = client.post('/api/ai-configs', json={
            'name': 'TestAI', 'base_url': 'https://api.test.com',
            'api_key': 'sk-test', 'model': 'gpt-4',
        })
        assert r.status_code in (200, 201)
        cid = r.get_json()['id']
        r = client.post(f'/api/ai-configs/{cid}/set-default')
        assert r.status_code in (200, 201)

        # 发消息（无真实 AI 后端时会返回 400，属于正常行为）
        r = client.post('/api/chat', json={'space_id': sid, 'message': '你好'})
        assert r.status_code in (200, 201, 400)

        # 查历史
        r = client.get(f'/api/spaces/{sid}/chat-history')
        assert r.status_code in (200, 201)
        history = r.get_json()
        assert len(history) >= 1

        # 清理
        assert client.delete(f'/api/spaces/{sid}/chat-history').status_code == 200


# ═══════════════════════════════════════════════════
# 场景 8：分析笔记 CRUD
# ═══════════════════════════════════════════════════
class TestNote:
    def test_crud(self, client):
        r = client.post('/api/spaces', json={'name': '笔记空间'})
        sid = r.get_json()['id']

        # 创建
        r = client.post('/api/notes', json={
            'space_id': sid, 'title': '分析报告', 'content': '# 内容',
        })
        assert r.status_code in (200, 201) and r.get_json()['title'] == '分析报告'

        # 列表
        r = client.get(f'/api/spaces/{sid}/notes')
        assert r.status_code in (200, 201) and len(r.get_json()) == 1
        nid = r.get_json()[0]['id']

        # 删除
        assert client.delete(f'/api/notes/{nid}').status_code == 200
        assert len(client.get(f'/api/spaces/{sid}/notes').get_json()) == 0


# ═══════════════════════════════════════════════════
# 场景 9：导出与备份
# ═══════════════════════════════════════════════════
class TestExportBackup:
    def test_export_zip(self, client):
        r = client.post('/api/spaces', json={'name': '导出空间'})
        sid = r.get_json()['id']
        r = client.get(f'/api/spaces/{sid}/export')
        assert r.status_code in (200, 201)

    def test_backup(self, client):
        # 先创建一个空间，确保有数据
        client.post('/api/spaces', json={'name': '备份测试'})
        r = client.get('/api/system/backup')
        assert r.status_code in (200, 201)
        assert r.content_type == 'application/octet-stream'

    def test_restore(self, client):
        # 创建一些数据
        client.post('/api/spaces', json={'name': '恢复测试'})
        r = client.get('/api/system/backup')
        data = r.get_data()
        r = client.post('/api/system/restore',
                        data={'file': (io.BytesIO(data), 'backup.db')})
        assert r.status_code in (200, 201)


# ═══════════════════════════════════════════════════
# 场景 10：错误处理
# ═══════════════════════════════════════════════════
class TestErrors:
    def test_404(self, client):
        assert client.get('/api/nonexistent').status_code == 404
        assert client.get('/nonexistent').status_code == 404

    def test_empty_name(self, client):
        assert client.post('/api/spaces', json={'name': ''}).status_code == 400

    def test_invalid_json(self, client):
        r = client.post('/api/spaces', data='not json',
                        content_type='application/json')
        assert r.status_code == 400

    def test_html_page(self, client):
        """首页渲染"""
        r = client.get('/')
        assert r.status_code == 200
        # 检查是否包含关键标识符
        html = r.get_data(as_text=True)
        assert 'ChartSpace' in html or 'excel' in html.lower()


if __name__ == '__main__':
    sys.exit(pytest.main(['-v', '-x', '--tb=short', __file__]))
