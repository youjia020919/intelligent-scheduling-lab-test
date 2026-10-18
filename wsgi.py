"""WSGI entrypoint for PythonAnywhere and similar hosts."""
from pathlib import Path
import json

from paper_extra_solver import solve as solve_extra
from staff_flex_solver import solve as solve_staff

ROOT = Path(__file__).resolve().parent
PAGE = ROOT / 'index.html'


def application(environ, start_response):
    path = environ.get('PATH_INFO', '/')
    method = environ.get('REQUEST_METHOD', 'GET').upper()

    def reply(status, payload, content_type='application/json; charset=utf-8'):
        body = (payload if isinstance(payload, bytes)
                else json.dumps(payload, ensure_ascii=False, default=str).encode('utf-8'))
        start_response(status, [('Content-Type', content_type),
                                ('Content-Length', str(len(body))),
                                ('Cache-Control', 'no-store')])
        return [body]

    if method == 'GET' and path in ('/', '/index.html'):
        return reply('200 OK', PAGE.read_bytes(), 'text/html; charset=utf-8')
    if method == 'GET' and path == '/api/coopa/status':
        return reply('200 OK', {'ready': False, 'missing_packages': [],
                                'model_key_configured': False,
                                'glpk_available': False, 'highs_available': False})
    if method == 'POST' and path == '/api/coopa/solve':
        return reply('503 Service Unavailable', {'error': '测试网站暂未启用 COOPA 模型 API。其他排程功能可正常使用。'})
    if method == 'POST' and path in ('/api/paper-extra', '/api/staff-flex'):
        try:
            size = int(environ.get('CONTENT_LENGTH', '0'))
            if not 1 <= size <= 30000:
                raise ValueError('参数大小不符合要求')
            data = json.loads(environ['wsgi.input'].read(size))
            result = (solve_staff(data) if path == '/api/staff-flex'
                      else solve_extra(str(data.get('case', '')), data.get('config')))
            return reply('200 OK', result)
        except (ValueError, KeyError, TypeError) as exc:
            return reply('400 Bad Request', {'error': str(exc)})
        except Exception:
            return reply('500 Internal Server Error', {'error': '求解服务内部错误，请检查输入或稍后重试。'})
    return reply('404 Not Found', {'error': '页面或接口不存在'})
