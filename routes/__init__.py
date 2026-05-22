# -*- coding: utf-8 -*-
from routes.auth import auth_bp
from routes.spaces import spaces_bp
from routes.datasets import datasets_bp
from routes.charts import charts_bp
from routes.chat import chat_bp
from routes.system import system_bp
from routes.main import main_bp
from routes.dashboards import dashboards_bp

# 统一导出所有蓝图，方便主入口循环注册
all_blueprints = [
    auth_bp,
    spaces_bp,
    datasets_bp,
    charts_bp,
    chat_bp,
    system_bp,
    main_bp,
    dashboards_bp
]

