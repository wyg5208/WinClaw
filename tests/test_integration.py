"""Sprint 1.2 集成测试 — 事件总线 / 会话管理 / Agent 重构验证。"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.event_bus import EventBus
from src.core.events import EventType, AgentThinkingEvent, ToolCallEvent
from src.core.session import SessionManager, Session
from src.core.agent import Agent, AgentResponse, DEFAULT_SYSTEM_PROMPT
from src.models.registry import ModelRegistry
from src.models.selector import ModelSelector
from src.models.cost import CostTracker
from src.tools.registry import create_default_registry

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} — {detail}")


# =====================================================================
# 事件总线测试
# =====================================================================

async def test_event_bus_basic():
    """测试事件总线基础功能。"""
    print("\n🧪 测试事件总线 - 基础")

    bus = EventBus()
    received = []

    async def handler(event_type, data):
        received.append((event_type, data))

    # 订阅
    sub_id = bus.on("test_event", handler)
    check("订阅返回 ID", sub_id > 0)
    check("订阅者数量 = 1", bus.subscriber_count("test_event") == 1)

    # 发布
    count = await bus.emit("test_event", {"key": "value"})
    check("发布通知 1 个订阅者", count == 1)
    check("回调收到事件", len(received) == 1)
    check("事件类型正确", received[0][0] == "test_event")
    check("事件数据正确", received[0][1]["key"] == "value")


async def test_event_bus_priority():
    """测试事件总线优先级。"""
    print("\n🧪 测试事件总线 - 优先级")

    bus = EventBus()
    order = []

    bus.on("evt", lambda et, d: order.append("C"), priority=300)
    bus.on("evt", lambda et, d: order.append("A"), priority=100)
    bus.on("evt", lambda et, d: order.append("B"), priority=200)

    await bus.emit("evt")
    check("按优先级顺序调用", order == ["A", "B", "C"], str(order))


async def test_event_bus_once():
    """测试一次性订阅。"""
    print("\n🧪 测试事件总线 - 一次性订阅")

    bus = EventBus()
    count = [0]

    bus.once("evt", lambda et, d: count.__setitem__(0, count[0] + 1))

    await bus.emit("evt")
    check("第一次触发", count[0] == 1)

    await bus.emit("evt")
    check("第二次不触发", count[0] == 1)


async def test_event_bus_wildcard():
    """测试通配符订阅。"""
    print("\n🧪 测试事件总线 - 通配符")

    bus = EventBus()
    all_events = []

    bus.on("*", lambda et, d: all_events.append(et))

    await bus.emit("event_a")
    await bus.emit("event_b")
    check("通配符收到所有事件", len(all_events) == 2)
    check("事件类型正确", all_events == ["event_a", "event_b"])


async def test_event_bus_off():
    """测试取消订阅。"""
    print("\n🧪 测试事件总线 - 取消订阅")

    bus = EventBus()
    count = [0]

    sub_id = bus.on("evt", lambda et, d: count.__setitem__(0, count[0] + 1))
    await bus.emit("evt")
    check("取消前收到事件", count[0] == 1)

    result = bus.off("evt", sub_id)
    check("取消订阅成功", result is True)

    await bus.emit("evt")
    check("取消后不再收到", count[0] == 1)

    # off_all
    bus.on("a", lambda et, d: None)
    bus.on("b", lambda et, d: None)
    cleared = bus.off_all()
    check("off_all 清除所有", cleared >= 2)


async def test_event_bus_async_handler():
    """测试异步回调处理。"""
    print("\n🧪 测试事件总线 - 异步回调")

    bus = EventBus()
    results = []

    async def async_handler(event_type, data):
        await asyncio.sleep(0.01)
        results.append("async_done")

    bus.on("evt", async_handler)
    await bus.emit("evt")
    check("异步回调执行完成", "async_done" in results)


# =====================================================================
# 会话管理器测试
# =====================================================================

def test_session_manager_basic():
    """测试会话管理器基础功能。"""
    print("\n🧪 测试会话管理器 - 基础")

    mgr = SessionManager(system_prompt="test prompt")

    check("自动创建默认会话", mgr.current_session is not None)
    check("默认会话有 system prompt", mgr.current_session.has_system_prompt)
    check("system prompt 内容正确", "test prompt" in mgr.current_session.messages[0]["content"])


def test_session_manager_messages():
    """测试消息管理。"""
    print("\n🧪 测试会话管理器 - 消息管理")

    mgr = SessionManager(system_prompt="你是助手")

    mgr.add_message(role="user", content="你好")
    check("添加用户消息", mgr.current_session.message_count == 2)  # system + user

    mgr.add_assistant_message(content="你好！有什么可以帮你的？")
    check("添加助手消息", mgr.current_session.message_count == 3)

    messages = mgr.get_messages()
    check("获取消息列表", len(messages) == 3)
    check("第一条是 system", messages[0]["role"] == "system")
    check("第二条是 user", messages[1]["role"] == "user")
    check("第三条是 assistant", messages[2]["role"] == "assistant")


def test_session_manager_tool_messages():
    """测试工具消息。"""
    print("\n🧪 测试会话管理器 - 工具消息")

    mgr = SessionManager()

    mgr.add_assistant_message(
        content="",
        tool_calls=[{"id": "tc1", "type": "function", "function": {"name": "shell_run", "arguments": "{}"}}],
    )
    mgr.add_tool_message(tool_call_id="tc1", content="命令执行成功")

    msgs = mgr.get_messages()
    tool_msg = [m for m in msgs if m["role"] == "tool"]
    check("工具消息存在", len(tool_msg) == 1)
    check("工具消息有 tool_call_id", tool_msg[0].get("tool_call_id") == "tc1")


def test_session_manager_multi_session():
    """测试多会话管理。"""
    print("\n🧪 测试会话管理器 - 多会话")

    mgr = SessionManager()
    first_id = mgr.current_session_id

    mgr.add_message(role="user", content="第一个会话的消息")

    # 创建第二个会话
    s2 = mgr.create_session(title="第二个对话")
    check("创建新会话", s2.id != first_id)
    check("自动切换到新会话", mgr.current_session_id == s2.id)

    mgr.add_message(role="user", content="第二个会话的消息")

    # 切换回第一个
    mgr.switch_session(first_id)
    check("切换回第一个会话", mgr.current_session_id == first_id)

    msgs1 = mgr.get_messages()
    user_msgs = [m for m in msgs1 if m["role"] == "user"]
    check("第一个会话消息隔离", len(user_msgs) == 1)
    check("消息内容正确", "第一个" in user_msgs[0]["content"])

    # 列出会话
    sessions = mgr.list_sessions()
    check("会话列表 = 2", len(sessions) == 2)


def test_session_manager_clear():
    """测试清空消息。"""
    print("\n🧪 测试会话管理器 - 清空消息")

    mgr = SessionManager(system_prompt="系统提示")
    mgr.add_message(role="user", content="消息1")
    mgr.add_message(role="user", content="消息2")
    check("清空前消息数 = 3", mgr.current_session.message_count == 3)

    mgr.clear_messages()
    check("清空后消息数 = 1", mgr.current_session.message_count == 1)  # 保留 system
    check("保留 system prompt", mgr.current_session.messages[0]["role"] == "system")


def test_session_manager_truncation():
    """测试上下文窗口截断。"""
    print("\n🧪 测试会话管理器 - 截断")

    # 设置很小的上下文窗口
    mgr = SessionManager(context_window=50, system_prompt="sys")

    # 添加很多消息
    for i in range(20):
        mgr.add_message(role="user", content=f"这是第 {i} 条很长的消息，包含很多内容。" * 3)
        mgr.add_message(role="assistant", content=f"这是第 {i} 条回复消息。" * 3)

    messages = mgr.get_messages()
    check("消息被截断", len(messages) < 42)  # 1 system + 40 messages
    check("第一条仍是 system", messages[0]["role"] == "system")
    # 最后一条应该是最近添加的
    check("保留最近消息", "19" in messages[-1]["content"])


def test_session_manager_delete():
    """测试删除会话。"""
    print("\n🧪 测试会话管理器 - 删除")

    mgr = SessionManager()
    s1_id = mgr.current_session_id
    s2 = mgr.create_session(title="会话2")

    # 删除当前会话
    result = mgr.delete_session(s2.id)
    check("删除成功", result is True)
    check("自动切换到其他会话", mgr.current_session_id == s1_id)

    # 删除不存在的会话
    result = mgr.delete_session("nonexistent")
    check("删除不存在的返回 False", result is False)


# =====================================================================
# Agent 重构验证测试
# =====================================================================

async def test_agent_new_init():
    """测试重构后的 Agent 初始化。"""
    print("\n🧪 测试 Agent 重构 - 初始化")

    model_reg = ModelRegistry()
    tool_reg = create_default_registry()

    agent = Agent(
        model_registry=model_reg,
        tool_registry=tool_reg,
    )

    check("Agent 创建成功", agent is not None)
    check("Agent 有事件总线", agent.event_bus is not None)
    check("Agent 有会话管理器", agent.session_manager is not None)
    check("Agent 有模型选择器", agent.model_selector is not None)
    check("Agent 有成本追踪器", agent.cost_tracker is not None)
    check("默认模型 deepseek-chat", agent.model_key == "deepseek-chat")


async def test_agent_backward_compat():
    """测试 Agent 向后兼容性。"""
    print("\n🧪 测试 Agent 重构 - 向后兼容")

    model_reg = ModelRegistry()
    tool_reg = create_default_registry()

    agent = Agent(
        model_registry=model_reg,
        tool_registry=tool_reg,
    )

    # messages 属性兼容
    check("messages 属性可用", isinstance(agent.messages, list))

    # reset 方法兼容
    agent.session_manager.add_message(role="user", content="test")
    msg_count_before = len(agent.messages)
    agent.reset()
    check("reset 清空消息", len(agent.messages) < msg_count_before)
    check("reset 保留 system", agent.messages[0]["role"] == "system" if agent.messages else False)


async def test_agent_event_integration():
    """测试 Agent 与事件总线的集成。"""
    print("\n🧪 测试 Agent 重构 - 事件集成")

    bus = EventBus()
    events_received = []

    bus.on("*", lambda et, d: events_received.append(et))

    model_reg = ModelRegistry()
    tool_reg = create_default_registry()

    agent = Agent(
        model_registry=model_reg,
        tool_registry=tool_reg,
        event_bus=bus,
    )

    # 不实际调用 API，只验证初始化
    check("事件总线已连接", agent.event_bus is bus)
    check("初始无事件", len(events_received) == 0)


async def test_agent_session_integration():
    """测试 Agent 与会话管理器的集成。"""
    print("\n🧪 测试 Agent 重构 - 会话集成")

    model_reg = ModelRegistry()
    tool_reg = create_default_registry()

    session_mgr = SessionManager(system_prompt="自定义提示")
    agent = Agent(
        model_registry=model_reg,
        tool_registry=tool_reg,
        session_manager=session_mgr,
    )

    check("使用自定义会话管理器", agent.session_manager is session_mgr)
    check("会话有 system prompt", agent.messages[0]["content"] == "自定义提示")

    # 创建新会话
    session_mgr.create_session(title="测试会话")
    check("新会话也有 system prompt", agent.messages[0]["role"] == "system")


async def test_agent_cost_integration():
    """测试 Agent 与成本追踪器的集成。"""
    print("\n🧪 测试 Agent 重构 - 成本集成")

    model_reg = ModelRegistry()
    tool_reg = create_default_registry()
    cost_tracker = CostTracker(budget_limit=1.0)

    agent = Agent(
        model_registry=model_reg,
        tool_registry=tool_reg,
        cost_tracker=cost_tracker,
    )

    check("使用自定义成本追踪器", agent.cost_tracker is cost_tracker)
    check("初始无费用", cost_tracker.total_calls == 0)
    check("预算上限正确", cost_tracker.budget_limit == 1.0)


# =====================================================================
# 主入口
# =====================================================================

async def main():
    print("=" * 60)
    print("  WinClaw Sprint 1.2 集成测试")
    print("=" * 60)

    # 事件总线
    await test_event_bus_basic()
    await test_event_bus_priority()
    await test_event_bus_once()
    await test_event_bus_wildcard()
    await test_event_bus_off()
    await test_event_bus_async_handler()

    # 会话管理器
    test_session_manager_basic()
    test_session_manager_messages()
    test_session_manager_tool_messages()
    test_session_manager_multi_session()
    test_session_manager_clear()
    test_session_manager_truncation()
    test_session_manager_delete()

    # Agent 重构验证
    await test_agent_new_init()
    await test_agent_backward_compat()
    await test_agent_event_integration()
    await test_agent_session_integration()
    await test_agent_cost_integration()

    print("\n" + "=" * 60)
    print(f"  结果: ✅ {passed} 通过  ❌ {failed} 失败")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
