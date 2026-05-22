import os
import sys
import sqlite3
import pandas as pd
import requests
import json

# 设置控制台输出编码为 utf-8，解决 Windows 乱码问题
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "http://127.0.0.1:5000"
DB_PATH = "excelany.db"
TEST_EXCEL = "test_missing_data.xlsx"

def check_db_state():
    """检测当前数据库中的数据量状态"""
    print("\n=== [1] 数据库当前状态自省 ===")
    if not os.path.exists(DB_PATH):
        print(f"警告: 数据库文件 {DB_PATH} 不存在。")
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"数据库中存在的表: {tables}")
        
        for table in ['space', 'dataset', 'chart', 'ai_config']:
            if table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f" - 表 '{table}' 的记录总数: {count}")
    except Exception as e:
        print(f"读取数据库出错: {e}")
    finally:
        conn.close()

def generate_test_excel(filename):
    """生成包含缺失值和用于线性拟合的测试 Excel 数据集"""
    print(f"\n=== [2] 生成测试 Excel 数据集: {filename} ===")
    # 模拟一个有缺失值的线性关系数据集： y = 2x + 5 + noise
    data = {
        "x": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "y": [7.1, 9.0, None, 13.2, 14.8, 17.1, None, 21.0, 22.9, 25.2], # 包含缺失值 None
        "category": ["A", "A", "B", "B", "A", "B", "A", "B", "A", "B"]
    }
    df = pd.DataFrame(data)
    df.to_excel(filename, index=False)
    print("测试 Excel 文件创建成功。")

def run_api_tests():
    """运行接口链路集成测试"""
    print("\n=== [3] 开始 API 链路测试 ===")
    
    # 1. 检查内存监控接口 (卫语句/扁平化控制路由)
    print("\n--> 1. 检查系统内存监控接口")
    try:
        res = requests.get(f"{BASE_URL}/api/system/memory")
        if res.status_code not in [200, 201]:
            print(f"  [失败] 内存接口响应异常: {res.status_code}")
            return
        print(f"  [成功] 内存状态: {res.json()}")
    except Exception as e:
        print(f"  [连接错误] 无法连接到服务，请确保 Flask 服务运行在 {BASE_URL}。错误: {e}")
        return

    # 2. 创建一个测试空间
    print("\n--> 2. 创建测试空间")
    space_name = f"自动化测试空间"
    res = requests.post(f"{BASE_URL}/api/spaces", json={"name": space_name})
    if res.status_code not in [200, 201]:
        print(f"  [失败] 创建空间返回: {res.text} (状态码: {res.status_code})")
        return
    space_id = res.json().get("id")
    print(f"  [成功] 创建空间成功, ID: {space_id}")

    # 3. 上传数据集
    print("\n--> 3. 上传含有缺失值的数据集")
    if not os.path.exists(TEST_EXCEL):
        generate_test_excel(TEST_EXCEL)
        
    try:
        with open(TEST_EXCEL, "rb") as f:
            files = {"file": (TEST_EXCEL, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            res = requests.post(f"{BASE_URL}/api/spaces/{space_id}/datasets", files=files)
            
        if res.status_code not in [200, 201]:
            print(f"  [失败] 上传数据集失败: {res.text} (状态码: {res.status_code})")
            return
        
        dataset_info = res.json()
        dataset_id = dataset_info.get("dataset_id")
        print(f"  [成功] 数据集上传成功, ID: {dataset_id}, 文件名: {dataset_info.get('name')}")
    except Exception as e:
        print(f"  [错误] 上传数据集发生异常: {e}")
        return

    # 4. 确认工作表 (Confirm Sheet)
    print("\n--> 4. 确认工作表")
    res = requests.post(f"{BASE_URL}/api/datasets/{dataset_id}/confirm-sheet", json={"sheet_name": "Sheet1"})
    if res.status_code not in [200, 201]:
        print(f"  [失败] 确认工作表失败: {res.text} (状态码: {res.status_code})")
        return
    print("  [成功] 确认工作表 Sheet1 成功")

    # 5. 验证策略模式：缺失值填充 (Preprocess API)
    # 分别测试 median 和 ffill 填充方式
    for strategy in ["median", "ffill"]:
        print(f"\n--> 5. 策略模式验证：使用 '{strategy}' 策略填充缺失值")
        payload = {
            "missing_method": strategy,
            "sampling_method": "none",
            "sampling_limit": 1000
        }
        res = requests.post(f"{BASE_URL}/api/datasets/{dataset_id}/preprocess", json=payload)
        if res.status_code not in [200, 201]:
            print(f"  [失败] '{strategy}' 策略预处理失败: {res.text} (状态码: {res.status_code})")
            continue
        
        res_data = res.json()
        print(f"  [成功] '{strategy}' 预处理完成。行数: {res_data.get('row_count')}, 缺失值数: {res_data.get('missing_count')}")

    # 6. 验证建造者/工厂模式：图表生成与渲染
    # 创建带趋势线的折线图，用于验证回归方程的 Annotation 以及 Plotly 新设计的样式
    print("\n--> 6. 工厂与建造者模式验证：创建并渲染图表 (包含线性趋势拟合)")
    chart_payload = {
        "name": "测试拟合趋势图",
        "chart_type": "line",
        "x_col": "x",
        "y_col": "y",
        "trend_enabled": True,
        "config": json.dumps({
            "title": "测试回归方程与新图表样式",
            "color": "#10b981", # 绿色 HSL 配色
            "smooth": True,
            "show_mean": True
        })
    }
    
    res = requests.post(f"{BASE_URL}/api/spaces/{space_id}/charts", json=chart_payload)
    if res.status_code not in [200, 201]:
        print(f"  [失败] 创建图表失败: {res.text} (状态码: {res.status_code})")
        return
    chart_id = res.json().get("id")
    print(f"  [成功] 创建图表成功, ID: {chart_id}")

    # 渲染图表并验证 Plotly 元素
    print("--> 渲染并分析 Plotly 图表布局参数")
    res = requests.get(f"{BASE_URL}/api/charts/{chart_id}/render")
    if res.status_code not in [200, 201]:
        print(f"  [失败] 渲染图表失败: {res.text} (状态码: {res.status_code})")
        return
    
    render_data = res.json()
    plotly_fig = render_data.get("chart_json") # Plotly Figure 字典结构
    
    # 提取渲染参数进行校验
    layout = plotly_fig.get("layout", {})
    annotations = layout.get("annotations", [])
    hoverlabel = layout.get("hoverlabel", {})
    
    # 打印校验信息
    print("  [图表渲染分析]:")
    print(f"    - 图表背景色: {layout.get('plot_bgcolor')}")
    print(f"    - 网格线与网格宽度: xaxis.gridcolor={layout.get('xaxis', {}).get('gridcolor')}")
    print(f"    - 圆角柱状图属性(如果有): barcornerradius={layout.get('barcornerradius')}")
    print(f"    - 悬浮提示框 hoverlabel 样式: {hoverlabel}")
    
    # 检测回归方程 Annotation 是否成功生成
    regression_annotated = False
    for ann in annotations:
        if "回归方程" in ann.get("text", "") or "R²" in ann.get("text", ""):
            regression_annotated = True
            print(f"    - [成功检测到趋势回归框]:\n{ann.get('text')}")
            
    if not regression_annotated:
        print("    - [警告] 未检测到回归拟合信息的 annotation，请检查趋势线运算逻辑。")

    # 7. 外观模式拦截测试：AI 智能对话
    print("\n--> 7. 外观模式验证：测试 AI 智能对话 (期望被卫语句拦截)")
    chat_payload = {
        "message": "帮我分析一下 x 和 y 的关系。",
        "dataset_id": dataset_id
    }
    res = requests.post(f"{BASE_URL}/api/chat", json=chat_payload)
    if res.status_code == 400:
        error_msg = res.json().get("error")
        print(f"  [成功拦截] 捕捉到预期的业务异常 (状态码 400): '{error_msg}'")
    else:
        print(f"  [非预期响应] 对话接口状态码: {res.status_code}, 返回: {res.text}")

    # 8. 看板及组件 CRUD 与数据联动链路测试
    print("\n--> 8. 看板与组件 API 链路测试 (DataInsightHub)")
    
    # 8.1 创建看板
    db_payload = {"name": "自动测试看板", "refresh_interval": 10}
    res = requests.post(f"{BASE_URL}/api/spaces/{space_id}/dashboards", json=db_payload)
    if res.status_code not in [200, 201]:
        print(f"  [失败] 创建看板失败: {res.text}")
        return
    dashboard_id = res.json().get("id")
    print(f"  [成功] 创建看板成功, ID: {dashboard_id}")

    # 8.2 更新看板
    res = requests.put(f"{BASE_URL}/api/dashboards/{dashboard_id}", json={"name": "已更名测试看板", "refresh_interval": 30})
    if res.status_code != 200:
        print(f"  [失败] 更新看板失败: {res.text}")
        return
    print(f"  [成功] 更新看板属性成功, 最新名称: {res.json().get('name')}, 轮询间隔: {res.json().get('refresh_interval')}")

    # 8.3 创建四大类型组件
    print("  --> 创建 KPI 组件...")
    kpi_payload = {
        "title": "测试指标 KPI",
        "component_type": "kpi",
        "dataset_id": dataset_id,
        "config": {"kpi_col": "y", "kpi_agg": "sum", "kpi_decimals": 1, "kpi_unit": "元", "kpi_target": 100}
    }
    res = requests.post(f"{BASE_URL}/api/dashboards/{dashboard_id}/components", json=kpi_payload)
    if res.status_code not in [200, 201]:
        print(f"    [失败] 创建 KPI 组件失败: {res.text}")
        return
    kpi_id = res.json().get("id")
    print(f"    [成功] KPI 组件已创建, ID: {kpi_id}")

    print("  --> 创建折线图表组件...")
    chart_payload = {
        "title": "趋势回归图表组件",
        "component_type": "chart",
        "dataset_id": dataset_id,
        "config": {"chart_type": "line", "x_col": "x", "y_col": "y", "trend_enabled": True}
    }
    res = requests.post(f"{BASE_URL}/api/dashboards/{dashboard_id}/components", json=chart_payload)
    if res.status_code not in [200, 201]:
        print(f"    [失败] 创建图表组件失败: {res.text}")
        return
    chart_comp_id = res.json().get("id")
    print(f"    [成功] 图表组件已创建, ID: {chart_comp_id}")

    print("  --> 创建数据表格组件...")
    table_payload = {
        "title": "原始明细表组件",
        "component_type": "table",
        "dataset_id": dataset_id,
        "config": {"page_size": 5}
    }
    res = requests.post(f"{BASE_URL}/api/dashboards/{dashboard_id}/components", json=table_payload)
    table_comp_id = res.json().get("id")
    print(f"    [成功] 表格组件已创建, ID: {table_comp_id}")

    print("  --> 创建富文本 Markdown 组件...")
    text_payload = {
        "title": "看板说明组件",
        "component_type": "text",
        "config": {"text_content": "### 自动化测试说明\n此文本用于验证 markdown 渲染是否正常。"}
    }
    res = requests.post(f"{BASE_URL}/api/dashboards/{dashboard_id}/components", json=text_payload)
    text_comp_id = res.json().get("id")
    print(f"    [成功] 文本组件已创建, ID: {text_comp_id}")

    # 8.4 获取组件解算数据与联动过滤测试
    print("  --> 验证 KPI 组件数据解算...")
    res = requests.get(f"{BASE_URL}/api/components/{kpi_id}/data")
    if res.status_code != 200:
        print(f"    [失败] 无法加载 KPI 数据: {res.text}")
    else:
        print(f"    [成功] KPI 结果: {res.json().get('formatted_value')} (警示样式: {res.json().get('color_class')})")

    print("  --> 验证图表组件数据解算与趋势预测...")
    res = requests.get(f"{BASE_URL}/api/components/{chart_comp_id}/data")
    if res.status_code != 200:
        print(f"    [失败] 无法加载图表数据: {res.text}")
    else:
        trend = res.json().get("trend_info") or {}
        print(f"    [成功] 图表回归方程斜率: {trend.get('slope')}, R²: {trend.get('r2')}, 预测周期数: {len(trend.get('predictions', []))}")

    print("  --> 验证联动过滤广播 (按 category='A' 过滤折线图数据)...")
    res = requests.get(f"{BASE_URL}/api/components/{chart_comp_id}/data?filter_col=category&filter_val=A")
    if res.status_code != 200:
        print(f"    [失败] 联动过滤图表失败: {res.text}")
    else:
        data_points = res.json().get("trend_info", {}).get("data_points", [])
        print(f"    [成功] 联动过滤后图表原始样本点数: {len(data_points)}")

    # 8.5 组件坐标修改保存
    print("  --> 修改组件网络坐标并保存...")
    pos_payload = {"position": {"x": 2, "y": 0, "w": 6, "h": 5}}
    res = requests.put(f"{BASE_URL}/api/components/{chart_comp_id}", json=pos_payload)
    if res.status_code != 200:
        print(f"    [失败] 保存组件布局失败: {res.text}")
    else:
        print(f"    [成功] 组件坐标已保存: {res.json().get('position')}")

    # 8.5.2 批量保存组件位置接口测试
    print("  --> 批量保存组件布局测试...")
    layout_payload = {
        "layout": [
            {"id": kpi_id, "position": {"x": 0, "y": 0, "w": 4, "h": 2}},
            {"id": chart_comp_id, "position": {"x": 4, "y": 0, "w": 8, "h": 5}},
            {"id": table_comp_id, "position": {"x": 0, "y": 5, "w": 12, "h": 4}}
        ]
    }
    res = requests.put(f"{BASE_URL}/api/dashboards/{dashboard_id}/components/layout", json=layout_payload)
    if res.status_code != 200:
        print(f"    [失败] 批量保存布局接口失败: {res.text}")
    else:
        print(f"    [成功] 批量保存布局接口通过: {res.json().get('message')}")

    # 8.6 删除看板及组件级联删除测试
    print("  --> 删除看板，验证级联删除下属组件机制...")
    res = requests.delete(f"{BASE_URL}/api/dashboards/{dashboard_id}")
    if res.status_code != 200:
        print(f"    [失败] 删除看板失败: {res.text}")
    else:
        print("    [成功] 看板已删除")
        # 尝试读取已被级联删除的组件，期望被卫语句以 404 拦截
        res = requests.get(f"{BASE_URL}/api/components/{chart_comp_id}/data")
        if res.status_code == 404:
            print("    [成功级联拦截] 尝试读取已被删除组件的数据，正确返回 404 错误")
        else:
            print(f"    [警告] 组件可能未被级联删除，状态码: {res.status_code}")

    # 清理测试生成的本地 Excel
    try:
        os.remove(TEST_EXCEL)
        print(f"\n--> 9. 清理临时测试文件: {TEST_EXCEL}")
    except Exception:
        pass

if __name__ == "__main__":
    check_db_state()
    run_api_tests()
