"""query_database 业务 Tool（agent: package-c-v1）。

按 docs/contracts/v1.md §1 冻结名 = query_database（旧名 db_query 已弃用）。
按 C 报告 §3.7 + §3.10 决议：
- 两阶段：step1 猜测 SQL（演示版固定模板）→ step2 返回 mock 结果
- 严格只读（演示版 SELECT only）
- 调用次数限制：单次 run 最多 3 次（演示版用类属性 _call_count）

演示版 100% Mock：固定 3 行 mock 数据 + 固定 SQL 模板。
未来切真 ask-db-service：替换 _mock_step1_generate_sql() + _mock_step2_execute() 实现。
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, ValidationError

from kivi_agent.core.business.base import BaseBusinessTool
from kivi_agent.core.tools.base import ToolResult

# 单次 run 内允许的最大调用次数（C 报告 §3.10 + aigroup database_tool.py:15）
_MAX_CALLS_PER_REQUEST = 3


# query_database 输入参数（agent: package-c-v1）
class QueryDatabaseParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    question: str  # 用户自然语言问题
    datasource_id: str  # 必填数据源 ID（演示版不校验存在性）


# 单行 mock 结果（演示版固定）
class MockRow(BaseModel):
    product: str
    sales: int
    region: str
    month: str


# query_database 业务 Tool：演示版 Mock 两阶段数据库问数（agent: package-c-v1）
class QueryDatabaseTool(BaseBusinessTool):
    """query_database Tool：两阶段问数（SQL 生成 → 数据返回）。

    演示版：
    - step1：基于 question + datasource_id 生成固定 SELECT SQL 模板
    - step2：返回 3 行 mock 数据
    - 调用次数限制：单实例（per-run）累计 3 次后返回错误

    严格只读：演示版 SQL 模板中所有语句都是 SELECT。
    """

    # 演示版调用计数器：类属性，所有实例共享（演示版简化）
    # 真实实现应 per-run 计数（按 v1 §2 RunContext 隔离），放 ExecutionContext.runtime
    _call_count: ClassVar[int] = 0
    # 计数重置方法：用于测试 teardown / per-run 重置
    _max_calls: ClassVar[int] = _MAX_CALLS_PER_REQUEST

    params_model = QueryDatabaseParams
    name = "query_database"
    category = "read"  # 严格只读 SELECT，无副作用
    description = (
        "Query a relational database with a natural language question. "
        "Two-stage pipeline: (1) generate a read-only SQL statement, "
        "(2) execute it and return rows. Strictly read-only — only SELECT "
        "statements are allowed. Use this when the user asks for tabular data "
        "or aggregations from a configured data source. "
        "The data source must be specified via datasource_id."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Natural language question, e.g. 'top products by sales last month'.",  # noqa: E501
            },
            "datasource_id": {
                "type": "string",
                "description": (
                    "Identifier of the configured data source. Required. "
                    "Strictly read-only — only SELECT statements are permitted."
                ),
            },
        },
        "required": ["question", "datasource_id"],
    }

    # 演示版入口（agent: package-c-v1）
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        try:
            p = QueryDatabaseParams.model_validate(params)
        except ValidationError as e:
            return ToolResult(
                content=json.dumps({"error": "invalid_params", "detail": e.errors()}, ensure_ascii=False),  # noqa: E501
                is_error=True,
                error_type="schema_error",
            )
        # 调用次数限制（C 报告 §3.10）
        # 关键：用 type(self)._call_count 显式访问类属性
        # 因为 self._call_count += 1 会在实例上创建同名属性遮蔽类属性
        # ClassVar 意图是"全局共享计数器"，必须显式走 type(self) 才能生效
        if type(self)._call_count >= type(self)._max_calls:
            return ToolResult(
                content=json.dumps(
                    {
                        "error": "call_limit_exceeded",
                        "message": (
                            f"数据库查询已连续调用 {type(self)._max_calls} 次，"
                            "为保护系统资源已停止，请简化问题或拆分多次请求。"
                        ),
                        "limit": type(self)._max_calls,
                    },
                    ensure_ascii=False,
                ),
                is_error=True,
                error_type="runtime_error",
            )
        # 自增计数（在 try/except 之外，确保失败也计数）
        type(self)._call_count += 1
        # 阶段 1：生成 SQL
        sql = _mock_step1_generate_sql(p.question, p.datasource_id)
        # 阶段 2：执行 SQL（演示版返回 mock 行）
        rows, columns = _mock_step2_execute(sql, p.datasource_id)
        return ToolResult(
            content=json.dumps(
                {
                    "sql": sql,
                    "rows": rows,
                    "columns": columns,
                    "datasource_id": p.datasource_id,
                    "stage": 2,
                    "call_count": type(self)._call_count,
                },
                ensure_ascii=False,
            )
        )

    # 重置计数器（测试 / per-run 用）
    @classmethod
    def reset_call_count(cls) -> None:
        cls._call_count = 0


# 演示版 step1：基于 question + datasource_id 生成固定 SELECT SQL（agent: package-c-v1）
def _mock_step1_generate_sql(question: str, datasource_id: str) -> str:
    """演示版 SQL 生成：固定模板，question 仅参与注释。

    真实实现：调 LLM with_structured_output(SQLAnalysisResult)
    （aigroup db_query_service.py:36-103 execute_step1）
    演示版简化：根据关键字映射到固定 SQL 模板。
    """
    # 演示版策略：按 datasource_id 区分固定模板
    if "ds-sales" in datasource_id.lower() or "销售" in question:
        return (
            f"-- 演示版 Mock SQL：基于问题「{question}」与数据源 {datasource_id}\n"
            f"SELECT product, sales, region, month\n"
            f"FROM sales_{datasource_id.replace('-', '_')}\n"
            f"ORDER BY sales DESC\n"
            f"LIMIT 10"
        )
    # 默认模板：products 表
    return (
        f"-- 演示版 Mock SQL：基于问题「{question}」与数据源 {datasource_id}\n"
        f"SELECT * FROM products_{datasource_id.replace('-', '_')}\n"
        f"LIMIT 10"
    )


# 演示版 step2：返回固定 3 行 mock 数据（agent: package-c-v1）
def _mock_step2_execute(sql: str, datasource_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    """演示版数据执行：返回 3 行固定数据。

    真实实现：调 ask-db-service step2，返回 data.data_json 行级数据
    （aigroup db_query_service.py）。
    演示版：固定 3 行销售样例。
    """
    rows = [
        MockRow(product="Alpha 旗舰版", sales=1280, region="华东", month="2026-01").model_dump(),
        MockRow(product="Beta 标准版", sales=890, region="华南", month="2026-01").model_dump(),
        MockRow(product="Gamma 入门版", sales=560, region="华北", month="2026-01").model_dump(),
    ]
    columns = list(rows[0].keys())
    return rows, columns
