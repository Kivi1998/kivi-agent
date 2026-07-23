"""Test page server — serve fixtures/test_page.html on port 5173（agent: package-web-e2e-v3）。

WT-E5 用：Playwright webServer 启动本脚本。
- 使用 Python 内置 http.server（零额外依赖）
- 暴露 ``/`` (test_page.html) + ``/screenshots/`` (写截图) + 静态资源
- 实际生产是 Vite dev server，本 worktree (WT-E5) 范围是测试脚手架。
"""

from __future__ import annotations

import http.server
import logging
import os
import socketserver
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] test_page_server: %(message)s",
)
logger = logging.getLogger("test_page_server")


class _TestPageHandler(http.server.SimpleHTTPRequestHandler):
    """自定义 handler：把 / 映射到 test_page.html。"""

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/" or self.path == "/index.html":
            self.path = "/test_page.html"
        # 让 screenshots/ 路径可写（GET 不会写，但路径要被识别）
        return super().do_GET()

    def log_message(self, fmt: str, *args: object) -> None:
        # 用 logger 替代 stderr（减少 Playwright 输出噪音）
        logger.debug(fmt, *args)


def main() -> None:
    port = int(os.environ.get("TEST_PAGE_PORT", "5173"))
    # 静态文件根目录 = fixtures/（包含 test_page.html）
    root = Path(__file__).resolve().parent
    os.chdir(str(root))
    logger.info("Serving test page on http://127.0.0.1:%d/ (root=%s)", port, root)

    # SO_REUSEADDR 防止 TIME_WAIT 卡死重启
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), _TestPageHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down test page server")
            httpd.shutdown()


if __name__ == "__main__":
    main()
