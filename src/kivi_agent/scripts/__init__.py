"""kivi-agent 启动 / 停止 / 健康检查的 Python 入口（Wave 7 WT-K1）。

设计：
- 这里只是 `scripts/*.sh` 的薄封装：subprocess 调 shell 脚本
- 真正的逻辑在 shell（docker compose profiles），便于运维直接复制
- Python 入口解决两个问题：
  1. `uv run kivi-start` 一行启动（pyproject [project.scripts]）
  2. 子 agent / 测试可在 Python 里 `from kivi_agent.scripts.start import main; main()`

注意：
- 所有入口在缺省时走 minimal profile（最安全启动）
- 不吞 stderr：subprocess 输出直接透传，便于排查
- raise on non-zero exit code，调用方 try/except 决定重试
"""
from kivi_agent.scripts.health import main as health_main
from kivi_agent.scripts.start import main as start_main
from kivi_agent.scripts.stop import main as stop_main

__all__ = ["start_main", "stop_main", "health_main"]
