from __future__ import annotations

from kama_claude.core.config import KamaConfig
from kama_claude.tui import __main__ as tui_main


# 功能：验证 main() 把 --replay 参数和 get_config() 得到的配置原样转交给 app.run()，不再自己构造 KamaTuiApp
# 设计：monkeypatch get_config 和 run 两个依赖，断言 run 收到的 config 就是 get_config 返回的那个对象、
#      replay_run_id 和命令行参数一致——这样以后 KamaTuiApp 构造逻辑改动只需要改 run() 一处，
#      不会再出现“两个入口各自构造、其中一个忘了传新参数”的情况（这正是 provider/model 状态栏那次的根因）
def test_main_delegates_to_run_with_parsed_config_and_replay_id(monkeypatch) -> None:
    fake_config = KamaConfig()
    calls: list[tuple[KamaConfig, str | None]] = []

    monkeypatch.setattr(tui_main, "get_config", lambda: fake_config)
    monkeypatch.setattr(tui_main, "run", lambda config, replay_run_id=None: calls.append((config, replay_run_id)))
    monkeypatch.setattr(tui_main, "_setup_logging", lambda level: None)
    monkeypatch.setattr("sys.argv", ["kama-tui", "--replay", "run-123"])

    tui_main.main()

    assert calls == [(fake_config, "run-123")]
