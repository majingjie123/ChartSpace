@echo off
echo [ExcelAny] 正在启动打包流程...

:: 清理旧的构建文件
if exist dist\ExcelAny.exe del /f /q dist\ExcelAny.exe
if exist build rmdir /s /q build

:: 执行 PyInstaller 打包
:: --onefile: 打包为单个 exe
:: --windowed: 运行时不显示命令行窗口
:: --add-data: 包含静态资源文件
:: --name: 指定输出文件名
pyinstaller --onefile --windowed ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --collect-all plotly ^
    --hidden-import sklearn.utils._typedefs ^
    --name ExcelAny ^
    app.py

echo.
echo [ExcelAny] 打包完成！
echo 请在 dist 目录下查找 ExcelAny.exe
pause
