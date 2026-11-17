"""Запуск тестов: python3 -m unittest discover -s tests -v"""
import io
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import speed_test

# создаём 70 000 байт, чтобы проверить, что скрипт читает весь ответ, а не только первые 65 536 байт
BODY = b'x' * 70000

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        with self.server.lock:
            self.server.requests += 1
            self.server.active += 1
            self.server.peak = max(self.server.peak, self.server.active)
        finish_body = False
        try:
            if self.path == '/error':
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Length', str(len(BODY)))
            self.end_headers()
            if self.path == '/broken':
                self.wfile.write(BODY[:10])
            else:
                self.wfile.write(BODY[:-1])
                self.wfile.flush()
                time.sleep(0.01)
                finish_body = True
        finally:
            with self.server.lock:
                try:
                    if finish_body:
                        self.wfile.write(BODY[-1:])
                        self.wfile.flush()
                finally:
                    self.server.active -= 1



class SpeedTestTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.lock = threading.RLock()
        self.server.requests = self.server.active = self.server.peak = 0
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def run_cli(self, path):
        url = f'http://127.0.0.1:{self.server.server_port}{path}'
        output, errors = io.StringIO(), io.StringIO()
        with patch('sys.argv', ['speed_test.py', url]), redirect_stdout(output), redirect_stderr(errors):
            code = speed_test.main()
        return code, output.getvalue(), errors.getvalue()

    def test_downloads_are_complete_and_sequential(self):
        code, output, errors = self.run_cli('/ok')
        self.assertEqual(code, 0, errors)
        self.assertEqual(self.server.requests, 10)
        self.assertEqual(self.server.peak, 1)
        self.assertIn('Скачано: 700000 байт', output)

    def test_calculations(self):
        # Длительности запросов — 1, 2, ..., 10 секунд: всего 55 секунд.
        ticks = [tick for i in range(10) for tick in (i * 20, i * 20 + i + 1)]
        with patch.object(speed_test, 'perf_counter', side_effect=ticks):
            code, output, errors = self.run_cli('/ok')
        self.assertEqual(code, 0, errors)
        self.assertIn('Среднее время запроса: 5.500 с', output)
        # 700000 байт × 8 / 55 секунд / 1000000 = 0,101818... Мбит/с.
        self.assertIn('Скорость скачивания: 0.102 Мбит/с', output)

    def test_incomplete_response(self):
        code, output, errors = self.run_cli('/broken')
        self.assertEqual(code, 1)
        self.assertEqual(self.server.requests, 1)
        self.assertEqual(output, '')
        self.assertIn('Неполный ответ', errors)

    def test_http_error(self):
        code, output, errors = self.run_cli('/error')
        self.assertEqual(code, 1)
        self.assertEqual(self.server.requests, 1)
        self.assertEqual(output, '')
        self.assertIn('404', errors)


if __name__ == '__main__':
    unittest.main()
