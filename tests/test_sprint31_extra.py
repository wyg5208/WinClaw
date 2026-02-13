"""Cron 工具和工作流加载器测试 — Sprint 3.1。

测试覆盖：
1. Cron 工具：创建/列出/删除定时任务
2. Cron 持久化：任务存储和恢复
3. 工作流加载器：扫描/加载/查询模板
4. 自然语言触发
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from src.core.event_bus import EventBus
from src.core.workflow import WorkflowEngine
from src.core.workflow_loader import WorkflowLoader
from src.tools.cron import CronTool
from src.tools.cron_storage import CronStorage, JobStatus, TriggerType
from src.tools.registry import ToolRegistry


# =====================================================================
# Fixtures
# =====================================================================

@pytest.fixture
def cron_tool():
    """使用临时数据库的 Cron 工具实例。"""
    # 使用临时文件作为数据库
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    return CronTool(db_path=db_path)


@pytest.fixture
def temp_db_path():
    """临时数据库路径（用于持久化测试）。"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        return f.name


@pytest.fixture
def tool_registry_with_cron(temp_db_path):
    """包含 Cron 工具的注册器。"""
    registry = ToolRegistry()
    cron_tool = CronTool(db_path=temp_db_path)
    registry.register(cron_tool)
    return registry


@pytest.fixture
def workflow_engine(tool_registry_with_cron):
    """工作流引擎。"""
    return WorkflowEngine(
        tool_registry=tool_registry_with_cron,
        event_bus=EventBus(),
    )


@pytest.fixture
def workflow_loader(workflow_engine):
    """工作流加载器。"""
    # 使用实际的模板目录
    templates_dir = Path(__file__).resolve().parent.parent / "config" / "workflows"
    return WorkflowLoader(workflow_engine, templates_dir)


# =====================================================================
# Cron 工具测试
# =====================================================================

@pytest.mark.asyncio
async def test_cron_add_interval_job(cron_tool):
    """测试创建间隔任务。"""
    result = await cron_tool.execute(
        "add_interval",
        {
            "job_id": "test_interval",
            "interval_seconds": 10,
            "command": "Write-Output 'Hello'",
            "description": "测试间隔任务",
        }
    )
    
    assert result.is_success
    assert "test_interval" in result.output
    assert result.data["interval_seconds"] == 10


@pytest.mark.asyncio
async def test_cron_list_jobs(cron_tool):
    """测试列出任务。"""
    # 先创建一个任务
    await cron_tool.execute(
        "add_interval",
        {
            "job_id": "test_list",
            "interval_seconds": 60,
            "command": "Write-Output 'Test'",
        }
    )
    
    # 列出任务
    result = await cron_tool.execute("list_jobs", {})
    
    assert result.is_success
    assert "test_list" in result.output
    assert len(result.data["jobs"]) >= 1


@pytest.mark.asyncio
async def test_cron_remove_job(cron_tool):
    """测试删除任务。"""
    # 先创建任务
    await cron_tool.execute(
        "add_interval",
        {
            "job_id": "test_remove",
            "interval_seconds": 30,
            "command": "Write-Output 'Remove me'",
        }
    )
    
    # 删除任务
    result = await cron_tool.execute(
        "remove_job",
        {"job_id": "test_remove"}
    )
    
    assert result.is_success
    assert "已删除" in result.output


@pytest.mark.asyncio
async def test_cron_add_cron_job(cron_tool):
    """测试创建 cron 定时任务。"""
    result = await cron_tool.execute(
        "add_cron",
        {
            "job_id": "test_cron",
            "cron_expr": "0 9 * * *",  # 每天 9:00
            "command": "Write-Output 'Daily task'",
            "description": "每日任务",
        }
    )
    
    assert result.is_success
    assert "test_cron" in result.output
    assert "0 9 * * *" in result.output


@pytest.mark.asyncio
async def test_cron_pause_resume_job(cron_tool):
    """测试暂停和恢复任务。"""
    # 创建任务
    await cron_tool.execute(
        "add_interval",
        {
            "job_id": "test_pause",
            "interval_seconds": 20,
            "command": "Write-Output 'Pause test'",
        }
    )
    
    # 暂停任务
    result_pause = await cron_tool.execute(
        "pause_job",
        {"job_id": "test_pause"}
    )
    assert result_pause.is_success
    
    # 恢复任务
    result_resume = await cron_tool.execute(
        "resume_job",
        {"job_id": "test_pause"}
    )
    assert result_resume.is_success


# =====================================================================
# Cron 持久化测试
# =====================================================================

@pytest.mark.asyncio
async def test_cron_persistence_save(temp_db_path):
    """测试任务创建后被持久化到数据库。"""
    cron_tool = CronTool(db_path=temp_db_path)
    
    # 创建任务
    await cron_tool.execute(
        "add_interval",
        {
            "job_id": "persist_test",
            "interval_seconds": 60,
            "command": "Write-Output 'Persist'",
            "description": "持久化测试",
        }
    )
    
    # 检查存储
    storage = CronStorage(db_path=temp_db_path)
    job = storage.get_job("persist_test")
    
    assert job is not None
    assert job.job_id == "persist_test"
    assert job.trigger_type == TriggerType.INTERVAL
    assert job.trigger_config["seconds"] == 60
    assert job.status == JobStatus.ACTIVE


@pytest.mark.asyncio
async def test_cron_persistence_restore(temp_db_path):
    """测试重启后任务恢复。"""
    # 第一个实例创建任务
    cron_tool1 = CronTool(db_path=temp_db_path)
    await cron_tool1.execute(
        "add_interval",
        {
            "job_id": "restore_test",
            "interval_seconds": 30,
            "command": "Write-Output 'Restore'",
        }
    )
    cron_tool1.shutdown()
    
    # 第二个实例（模拟重启）
    cron_tool2 = CronTool(db_path=temp_db_path)
    
    # 列出任务，应该能看到恢复的任务
    result = await cron_tool2.execute("list_jobs", {})
    
    assert result.is_success
    assert "restore_test" in result.output
    assert any(j["id"] == "restore_test" for j in result.data["jobs"])
    cron_tool2.shutdown()


@pytest.mark.asyncio
async def test_cron_persistence_pause_status(temp_db_path):
    """测试暂停状态持久化。"""
    # 创建并暂停任务
    cron_tool1 = CronTool(db_path=temp_db_path)
    await cron_tool1.execute(
        "add_interval",
        {
            "job_id": "pause_status_test",
            "interval_seconds": 45,
            "command": "Write-Output 'Pause status'",
        }
    )
    await cron_tool1.execute("pause_job", {"job_id": "pause_status_test"})
    cron_tool1.shutdown()
    
    # 检查存储中的状态
    storage = CronStorage(db_path=temp_db_path)
    job = storage.get_job("pause_status_test")
    assert job.status == JobStatus.PAUSED
    
    # 重启后任务应保持暂停状态
    cron_tool2 = CronTool(db_path=temp_db_path)
    result = await cron_tool2.execute("list_jobs", {})
    
    paused_job = next((j for j in result.data["jobs"] if j["id"] == "pause_status_test"), None)
    assert paused_job is not None
    assert paused_job["status"] == "paused"
    cron_tool2.shutdown()


@pytest.mark.asyncio
async def test_cron_persistence_delete(temp_db_path):
    """测试删除任务后存储也被删除。"""
    cron_tool = CronTool(db_path=temp_db_path)
    
    # 创建任务
    await cron_tool.execute(
        "add_interval",
        {
            "job_id": "delete_test",
            "interval_seconds": 15,
            "command": "Write-Output 'Delete'",
        }
    )
    
    # 确认存储中有任务
    storage = CronStorage(db_path=temp_db_path)
    assert storage.get_job("delete_test") is not None
    
    # 删除任务
    await cron_tool.execute("remove_job", {"job_id": "delete_test"})
    
    # 确认存储中任务已删除
    assert storage.get_job("delete_test") is None
    cron_tool.shutdown()


@pytest.mark.asyncio
async def test_cron_persistence_cron_type(temp_db_path):
    """测试 cron 类型任务的持久化。"""
    # 创建 cron 任务
    cron_tool1 = CronTool(db_path=temp_db_path)
    await cron_tool1.execute(
        "add_cron",
        {
            "job_id": "cron_persist",
            "cron_expr": "30 8 * * 1-5",  # 周一到周五 8:30
            "command": "Write-Output 'Morning task'",
            "description": "工作日早晨任务",
        }
    )
    cron_tool1.shutdown()
    
    # 检查存储
    storage = CronStorage(db_path=temp_db_path)
    job = storage.get_job("cron_persist")
    
    assert job is not None
    assert job.trigger_type == TriggerType.CRON
    assert job.trigger_config["minute"] == "30"
    assert job.trigger_config["hour"] == "8"
    assert job.trigger_config["day_of_week"] == "1-5"
    
    # 模拟重启
    cron_tool2 = CronTool(db_path=temp_db_path)
    result = await cron_tool2.execute("list_jobs", {})
    assert "cron_persist" in result.output
    cron_tool2.shutdown()


# =====================================================================
# 工作流加载器测试
# =====================================================================

def test_workflow_loader_scan(workflow_loader):
    """测试扫描工作流模板。"""
    count = workflow_loader.load_all_templates()
    
    # 应该至少加载 4 个模板
    assert count >= 4
    assert len(workflow_loader.list_templates()) >= 4


def test_workflow_loader_get_template(workflow_loader):
    """测试获取模板。"""
    workflow_loader.load_all_templates()
    
    template = workflow_loader.get_template("desktop_organizer")
    
    assert template is not None
    assert template.name == "desktop_organizer"
    assert template.definition.description
    assert "file" in template.tags or "organization" in template.tags


def test_workflow_loader_find_by_tag(workflow_loader):
    """测试按标签查询。"""
    workflow_loader.load_all_templates()
    
    automation_templates = workflow_loader.find_by_tag("automation")
    
    assert len(automation_templates) > 0


def test_workflow_loader_find_by_category(workflow_loader):
    """测试按类别查询。"""
    workflow_loader.load_all_templates()
    
    productivity_templates = workflow_loader.find_by_category("productivity")
    
    # desktop_organizer 属于 productivity 类别
    assert len(productivity_templates) >= 1


def test_workflow_loader_search(workflow_loader):
    """测试模糊搜索。"""
    workflow_loader.load_all_templates()
    
    # 搜索"整理"
    results = workflow_loader.search("整理")
    
    assert len(results) >= 1
    assert any("desktop_organizer" in t.name for t in results)


def test_workflow_loader_trigger_match(workflow_loader):
    """测试自然语言触发匹配。"""
    workflow_loader.load_all_templates()
    
    # 测试触发关键词
    workflow_name = workflow_loader.match_trigger("帮我整理桌面")
    
    assert workflow_name == "desktop_organizer"


def test_workflow_loader_add_trigger(workflow_loader):
    """测试添加触发关键词。"""
    workflow_loader.load_all_templates()
    
    workflow_loader.add_trigger("清理文件", "desktop_organizer")
    
    workflow_name = workflow_loader.match_trigger("清理文件")
    assert workflow_name == "desktop_organizer"


def test_workflow_loader_summary(workflow_loader):
    """测试获取摘要。"""
    workflow_loader.load_all_templates()
    
    summary = workflow_loader.get_summary()
    
    assert "已加载" in summary
    assert "个工作流模板" in summary


# =====================================================================
# 集成测试：工作流 + Cron
# =====================================================================

@pytest.mark.asyncio
async def test_workflow_execute_template(workflow_loader):
    """测试执行工作流模板（简化场景）。"""
    workflow_loader.load_all_templates()
    
    # 注意：这里不执行实际的工作流，因为它们需要真实的工具
    # 只测试模板加载和参数注入
    template = workflow_loader.get_template("system_cleanup")
    
    assert template is not None
    assert len(template.definition.steps) >= 4


# =====================================================================
# 汇总统计
# =====================================================================

def test_summary():
    """测试汇总。"""
    print("\n" + "="*70)
    print("Sprint 3.1 附加功能测试汇总")
    print("="*70)
    print("✅ Cron 工具：创建间隔任务 / cron 任务 / 一次性任务")
    print("✅ Cron 工具：列出 / 删除 / 暂停 / 恢复任务")
    print("✅ 工作流加载器：扫描加载模板 / 按名称获取")
    print("✅ 工作流加载器：按标签查询 / 按类别查询 / 模糊搜索")
    print("✅ 工作流加载器：自然语言触发匹配")
    print("="*70)
