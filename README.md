# Excel 多空间智能图表分析工具 (ExcelAny)

一个基于 Web 技术的桌面数据分析工具，支持多空间隔离、Excel 数据处理、智能图表渲染及 AI 助手。

## 核心功能

- **多空间管理**：独立的工作区，数据完全隔离。
- **Excel 处理**：支持上传、工作表选择、数据预处理（缺失值填充、采样等）。
- **智能可视化**：支持 6 种基础图表，内置线性回归趋势分析及未来预测。
- **AI 助手**：集成 OpenAI 兼容接口，支持绑定数据集进行智能问答。
- **备份与恢复**：支持整库备份、空间导出。

## 快速开始

### 开发环境运行

1. 安装 Python 3.9+
2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
3. 启动应用：
   ```bash
   python app.py
   ```
4. 浏览器访问：`http://127.0.0.1:5000`

### 生产打包 (Windows)

运行项目根目录下的 `build.bat`，打包完成后在 `dist/` 目录生成 `ExcelAny.exe`。

## 技术栈

- **后端**：Flask, SQLAlchemy, Pandas, Scikit-learn, Plotly
- **前端**：Vue 3 (CDN), Bootstrap 5, Plotly.js
- **存储**：SQLite
- **打包**：PyInstaller

## 注意事项

- 初次运行会自动在同级目录创建 `uploads/`, `logs/`, `backup/` 文件夹及 `excelany.db` 数据库文件。
- AI 功能需要配置有效的 OpenAI 兼容 API Key。
