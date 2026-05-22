from flask import jsonify, request

class APIError(Exception):
    """API 业务自定义异常"""
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code

def register_error_handlers(app):
    """注册全局异常捕获装饰器"""
    
    @app.errorhandler(APIError)
    def handle_api_error(error):
        return jsonify({'error': str(error)}), error.status_code

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': '接口不存在'}), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        valid = getattr(error, 'valid_methods', None)
        msg = f'请求方法不允许。支持的请求方法: {", ".join(valid) if valid else "N/A"}'
        return jsonify({'error': msg}), 405

    @app.errorhandler(413)
    def too_large(error):
        return jsonify({'error': '文件过大，最大支持 50MB'}), 413

    @app.errorhandler(Exception)
    def handle_generic_error(error):
        app.logger.error(f'未捕获异常: {request.path}', exc_info=True)
        return jsonify({'error': '服务器内部错误，请查看日志'}), 500
