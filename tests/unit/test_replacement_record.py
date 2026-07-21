from __future__ import annotations

from pathlib import Path

from kama_claude.core.session.replacement import (
    ReplacementRecord,
    list_replacement_records,
    write_replacement_record,
)


# 功能：验证写入一条替换记录后能通过 list_replacement_records 读回，字段一致
# 设计：构造一条记录写入再列出，逐字段断言，覆盖"写入格式和读取解析对得上"这个核心约束
def test_write_and_list_replacement_record(tmp_path: Path) -> None:
    record = ReplacementRecord(
        ts="2026-07-21T00:00:00+00:00",
        original_message_count=42,
        original_tokens=8000,
        summary_text="用户要修复登录 bug，已定位到 auth.py",
        summary_tokens=120,
    )
    write_replacement_record(tmp_path, record)
    records = list_replacement_records(tmp_path)
    assert len(records) == 1
    assert records[0].original_message_count == 42
    assert records[0].summary_text == "用户要修复登录 bug，已定位到 auth.py"


# 功能：验证多次压缩产生的多条记录按时间顺序全部保留、可列出
# 设计：写入两条记录，断言 list 返回长度为 2 且保持写入顺序，确认这是"追加式审计日志"而不是覆盖式存储
def test_multiple_records_are_all_preserved(tmp_path: Path) -> None:
    r1 = ReplacementRecord(ts="t1", original_message_count=10, original_tokens=1000, summary_text="a", summary_tokens=10)
    r2 = ReplacementRecord(ts="t2", original_message_count=20, original_tokens=2000, summary_text="b", summary_tokens=20)
    write_replacement_record(tmp_path, r1)
    write_replacement_record(tmp_path, r2)
    records = list_replacement_records(tmp_path)
    assert len(records) == 2
    assert [r.summary_text for r in records] == ["a", "b"]


# 功能：验证 list_replacement_records 在没有任何记录时返回空列表而不是抛异常
# 设计：空目录调用，断言返回 []，让上游（压缩流程检查）不必做存在性判断
def test_list_empty_returns_empty_list(tmp_path: Path) -> None:
    assert list_replacement_records(tmp_path) == []
