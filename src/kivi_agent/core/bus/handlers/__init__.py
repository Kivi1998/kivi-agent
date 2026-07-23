"""core/bus/handlers 包：业务事件 handler 集合（agent: package-events-bridge-v2）。

按 v1 §5.2.1 冻结的 6 业务事件 + v1 §5.2.2 SessionCancel 命令，本目录负责订阅、
聚合、分发这些事件到上层业务消费者。Wave 2 首个实现是 BusinessEventHandler。
"""
