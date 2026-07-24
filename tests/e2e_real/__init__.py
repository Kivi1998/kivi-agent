"""tests.e2e_real — 真实接入端到端测试（agent: package-e2e-real-v4 + package-e2e-real-w82）。

包含两类 E2E 测试：

- **v4（Wave 4 WT-F4）**：本地 rag-kb mock + SQLite/Postgres Adapter 真实模式
  + 健康检查降级。默认 11 个测试在 ``test_rag_real.py`` / ``test_db_real.py`` /
  ``test_fallback.py`` 中。

- **w82（Wave 8.2 WT-L3）**：5 demo + 5 eval case 真实 LLM 端到端。
  env guard ``KIVI_RUN_E2E=1`` 才跑（默认安全）。报告写到
  ``KIVI_E2E_REPORT_DIR``（默认 ``reports/e2e_real/``）的 JSON + Markdown。

子模块：

- ``_protocols``：LLMSimpleProvider Protocol（解耦 L1/L2）
- ``conftest``：env guard + llm_provider + max_cases + report_dir fixtures
- ``report``：E2ERunResult / E2EReport / make_run_result / compute_cost_usd
- ``prompts/``：6 个 markdown 期望输出说明
- ``fixtures/acceptance_thresholds.yaml``：每个 demo 的最低验收门槛
"""
