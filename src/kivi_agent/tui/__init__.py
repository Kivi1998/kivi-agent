"""kivi_agent.tui 公共导出（agent: package-tui-events-v2）。

业务事件流 widget 的导出入口；其他 widget（ToolCallBlock / PermissionBlock /
TeamTreeWidget / SessionListScreen 等）仍从 ``tui.app`` / ``tui.permission_widgets``
/ ``tui.team_tree`` / ``tui.session_screen`` 直接导入，避免对 ``tui.app.py`` 1300+ 行
文件做"全量导出"重构。
"""

from kivi_agent.tui.business_event_widget import BusinessEventWidget

__all__ = ["BusinessEventWidget"]
