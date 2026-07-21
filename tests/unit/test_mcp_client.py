from __future__ import annotations

from unittest.mock import AsyncMock, patch

from kama_claude.core.mcp.client import McpClient


# 功能：验证 connect_http 用 httpx 向指定 URL 发 initialize 请求完成握手，不走 stdio/tcp 那套行读取
# 设计：mock httpx.AsyncClient.post 返回一个符合 JSON-RPC 格式的 initialize 响应，
#      断言 connect_http 正常完成不抛异常，且后续 list_tools 也走同一个 HTTP POST 路径
async def test_connect_http_completes_handshake() -> None:
    client = McpClient()

    async def _fake_post(*args, **kwargs):
        # httpx.AsyncClient.post 是 bound method，patch 后 self 自动注入为 args[0]
        json = kwargs.get("json") or (args[2] if len(args) > 2 else {})
        method = json.get("method")
        response = AsyncMock()
        if method == "initialize":
            response.json = lambda: {"jsonrpc": "2.0", "id": json["id"], "result": {}}
        elif method == "tools/list":
            response.json = lambda: {
                "jsonrpc": "2.0", "id": json["id"],
                "result": {"tools": [{"name": "echo", "description": "回显", "inputSchema": {}}]},
            }
        else:
            response.json = lambda: {"jsonrpc": "2.0", "id": json["id"], "result": {}}
        response.raise_for_status = lambda: None
        return response

    with patch("httpx.AsyncClient.post", new=_fake_post):
        await client.connect_http("http://fake-mcp-server/rpc")
        tools = await client.list_tools()

    assert len(tools) == 1
    assert tools[0].name == "echo"
