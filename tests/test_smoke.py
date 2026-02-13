"""MVP 冒烟测试 — 验证工具层和核心组件不依赖 API Key 的部分。"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

# 将项目根目录加入路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.registry import ModelRegistry, ModelConfig
from src.tools.base import ToolResult, ToolResultStatus
from src.tools.registry import ToolRegistry, create_default_registry
from src.tools.shell import ShellTool
from src.tools.file import FileTool
from src.tools.screen import ScreenTool


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


async def test_model_registry():
    """测试模型注册中心。"""
    print("\n🧪 测试模型注册中心")
    reg = ModelRegistry()
    models = reg.list_models()
    check("加载模型配置", len(models) >= 8, f"只加载了 {len(models)} 个")

    gpt = reg.get("gpt-4o-mini")
    check("获取 gpt-4o-mini", gpt is not None)
    check("模型支持 function calling", gpt.supports_function_calling if gpt else False)

    fc_models = reg.find_by_capability(needs_function_calling=True)
    check("筛选支持 FC 的模型", len(fc_models) >= 6, f"仅 {len(fc_models)} 个")

    img_models = reg.find_by_capability(needs_image=True)
    check("筛选支持图片的模型", len(img_models) >= 4, f"仅 {len(img_models)} 个")

    # DeepSeek 模型配置校验
    ds = reg.get("deepseek-chat")
    check("获取 deepseek-chat", ds is not None)
    if ds:
        check("DeepSeek model id 正确", ds.id == "deepseek-chat")
        check("DeepSeek base_url 正确", ds.base_url == "https://api.deepseek.com")
        check("DeepSeek api_key_env 正确", ds.api_key_env == "DEEPSEEK_API_KEY")
        check("DeepSeek 支持 FC", ds.supports_function_calling is True)


async def test_tool_registry():
    """测试工具注册器。"""
    print("\n🧪 测试工具注册器")
    reg = create_default_registry()

    tools = reg.list_tools()
    check("注册 ≥ 3 个工具", len(tools) >= 3, f"实际 {len(tools)} 个")

    schemas = reg.get_all_schemas()
    check("生成 schema", len(schemas) >= 4, f"只有 {len(schemas)} 个 schema")

    # 验证 schema 格式
    for s in schemas:
        check(
            f"schema {s['function']['name']} 格式正确",
            "type" in s and "function" in s and "name" in s["function"],
        )

    # 验证函数名解析
    resolved = reg.resolve_function_name("shell_run")
    check("解析 shell_run", resolved == ("shell", "run"), str(resolved))

    resolved = reg.resolve_function_name("file_read")
    check("解析 file_read", resolved == ("file", "read"), str(resolved))

    resolved = reg.resolve_function_name("unknown_func")
    check("未知函数返回 None", resolved is None)


async def test_shell_tool():
    """测试 Shell 工具。"""
    print("\n🧪 测试 Shell 工具")
    shell = ShellTool(timeout=10)

    # 执行简单命令
    result = await shell.safe_execute("run", {"command": "echo hello"})
    check("echo 命令", result.is_success, result.error)
    check("echo 输出包含 hello", "hello" in result.output.lower(), result.output[:100])

    # 执行 PowerShell 命令
    result = await shell.safe_execute("run", {"command": "Get-Date -Format 'yyyy-MM-dd'"})
    check("Get-Date 命令", result.is_success, result.error)
    check("日期格式正确", "202" in result.output, result.output[:50])

    # 危险命令拦截
    result = await shell.safe_execute("run", {"command": "shutdown /s"})
    check("拦截 shutdown", result.status == ToolResultStatus.DENIED, result.error)

    result = await shell.safe_execute("run", {"command": "Remove-Item -Recurse C:\\"})
    check("拦截 Remove-Item -Recurse", result.status == ToolResultStatus.DENIED, result.error)

    # 空命令
    result = await shell.safe_execute("run", {"command": ""})
    check("拒绝空命令", not result.is_success)

    # 不支持的动作
    result = await shell.safe_execute("invalid", {})
    check("拒绝未知动作", not result.is_success)


async def test_file_tool():
    """测试 File 工具。"""
    print("\n🧪 测试 File 工具")
    file_tool = FileTool()

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = str(Path(tmpdir) / "test.txt")

        # 写入文件
        result = await file_tool.safe_execute("write", {
            "path": test_file,
            "content": "Hello WinClaw!\n这是测试文件。",
        })
        check("写入文件", result.is_success, result.error)
        check("文件实际存在", Path(test_file).exists())

        # 读取文件
        result = await file_tool.safe_execute("read", {"path": test_file})
        check("读取文件", result.is_success, result.error)
        check("内容正确", "Hello WinClaw" in result.output, result.output[:100])
        check("中文内容正确", "这是测试文件" in result.output)

        # 追加写入
        result = await file_tool.safe_execute("write", {
            "path": test_file,
            "content": "\n追加内容",
            "append": True,
        })
        check("追加写入", result.is_success, result.error)

        result = await file_tool.safe_execute("read", {"path": test_file})
        check("追加后内容完整", "追加内容" in result.output and "Hello" in result.output)

        # 列出目录
        result = await file_tool.safe_execute("list", {"path": tmpdir})
        check("列出目录", result.is_success, result.error)
        check("目录包含测试文件", "test.txt" in result.output, result.output[:200])

        # 读取不存在的文件
        result = await file_tool.safe_execute("read", {"path": str(Path(tmpdir) / "nonexistent.txt")})
        check("不存在文件报错", not result.is_success)


async def test_screen_tool():
    """测试 Screen 工具。"""
    print("\n🧪 测试 Screen 工具")
    screen = ScreenTool(max_width=800, model_max_width=800)

    result = await screen.safe_execute("capture", {})
    check("全屏截图", result.is_success, result.error)
    if result.is_success:
        check("截图有 base64 数据", bool(result.data.get("base64")))
        check("截图有尺寸信息", result.data.get("width", 0) > 0)
        check(
            f"截图尺寸合理 ({result.data.get('width')}x{result.data.get('height')})",
            result.data.get("width", 0) <= 800,
        )


async def test_agent_init():
    """测试 Agent 初始化（不调用 API）。"""
    print("\n🧪 测试 Agent 初始化")
    from src.core.agent import Agent

    model_reg = ModelRegistry()
    tool_reg = create_default_registry()

    agent = Agent(
        model_registry=model_reg,
        tool_registry=tool_reg,
    )
    check("Agent 创建成功", agent is not None)
    check("Agent 默认模型为 deepseek-chat", agent.model_key == "deepseek-chat")
    check("Agent 有 system prompt", len(agent.messages) >= 1 and agent.messages[0]["role"] == "system")

    agent.reset()
    check("Agent reset 保留 system prompt", len(agent.messages) == 1 and agent.messages[0]["role"] == "system")


async def main():
    print("=" * 60)
    print("  WinClaw MVP 冒烟测试")
    print("=" * 60)

    await test_model_registry()
    await test_tool_registry()
    await test_shell_tool()
    await test_file_tool()
    await test_screen_tool()
    await test_agent_init()

    print("\n" + "=" * 60)
    print(f"  结果: ✅ {passed} 通过  ❌ {failed} 失败")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
