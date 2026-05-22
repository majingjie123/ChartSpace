from flask import Blueprint, render_template
from core.database import db_session

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """返回主页 SPA 模板"""
    return render_template('index.html')

