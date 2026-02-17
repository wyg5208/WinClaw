"""Python Runner 工具 — 智能Python脚本执行器。

核心功能：
1. 智能虚拟环境检测与选择
2. 依赖自动安装
3. 脚本安全执行
4. 执行结果汇总

设计理念：
- 优先使用项目已有的虚拟环境（如winclaw自身的.venv）
- 支持UV工具加速虚拟环境创建和依赖安装
- 自动检测并安装缺失的依赖
- 提供详细的执行日志和结果汇总

v1.0.13 优化：
- GUI程序检测与非交互模式支持
- 中文输出编码优化
- 脚本内容分析与智能执行策略
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.tools.base import ActionDef, BaseTool, ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)


# GUI库检测模式
GUI_PATTERNS = {
    "matplotlib": [r"import\s+matplotlib", r"from\s+matplotlib", r"plt\.", r"pyplot"],
    "tkinter": [r"import\s+tkinter", r"from\s+tkinter", r"import\s+Tk"],
    "PyQt": [r"import\s+PyQt", r"from\s+PyQt", r"from\s+PySide"],
    "PyGame": [r"import\s+pygame", r"from\s+pygame"],
    "PIL.ImageTk": [r"ImageTk", r"ImageShow"],
}


@dataclass
class VenvInfo:
    """虚拟环境信息。"""
    path: Path
    python_path: Path
    pip_path: Path
    is_uv: bool = False
    is_project_venv: bool = False
    name: str = ""


@dataclass
class ScriptAnalysis:
    """脚本分析结果。"""
    is_gui_program: bool = False
    gui_libraries: list[str] = field(default_factory=list)
    has_main_block: bool = False
    imports: list[str] = field(default_factory=list)
    suggested_mode: str = "auto"  # auto, headless, gui


@dataclass
class ExecutionSummary:
    """执行汇总信息。"""
    script_path: str = ""
    venv_used: str = ""
    dependencies_installed: list[str] = field(default_factory=list)
    output: str = ""
    error: str = ""
    return_code: int = 0
    duration_seconds: float = 0.0
    success: bool = True
    steps: list[str] = field(default_factory=list)
    script_analysis: ScriptAnalysis | None = None
    execution_mode: str = "normal"  # normal, headless, gui

    def to_markdown(self) -> str:
        """生成Markdown格式的汇总报告。"""
        lines = [
            "## 🐍 Python脚本执行报告",
            "",
            f"**脚本路径**: `{self.script_path}`",
            f"**虚拟环境**: `{self.venv_used}`",
            f"**执行模式**: {self._get_mode_display()}",
            f"**执行状态**: {'✅ 成功' if self.success else '❌ 失败'}",
            f"**执行时长**: {self.duration_seconds:.2f}秒",
            f"**返回码**: {self.return_code}",
            "",
        ]
        
        # 脚本分析信息
        if self.script_analysis and self.script_analysis.is_gui_program:
            lines.append("### 🔍 脚本分析")
            lines.append(f"- **检测到GUI库**: {', '.join(self.script_analysis.gui_libraries)}")
            lines.append(f"- **执行模式**: {self.execution_mode}")
            lines.append("")
        
        if self.steps:
            lines.append("### 📋 执行步骤")
            for i, step in enumerate(self.steps, 1):
                lines.append(f"{i}. {step}")
            lines.append("")
        
        if self.dependencies_installed:
            lines.append("### 📦 已安装依赖")
            for dep in self.dependencies_installed:
                lines.append(f"- {dep}")
            lines.append("")
        
        if self.output:
            lines.append("### 📤 输出结果")
            lines.append("```")
            lines.append(self.output[:5000])  # 限制输出长度
            if len(self.output) > 5000:
                lines.append("...(输出已截断)")
            lines.append("```")
            lines.append("")
        
        if self.error:
            lines.append("### ⚠️ 错误信息")
            lines.append("```")
            lines.append(self.error[:2000])
            lines.append("```")
            lines.append("")
        
        return "\n".join(lines)
    
    def _get_mode_display(self) -> str:
        """获取执行模式显示文本。"""
        mode_map = {
            "normal": "标准模式",
            "headless": "无头模式（非GUI）",
            "gui": "GUI模式",
        }
        return mode_map.get(self.execution_mode, self.execution_mode)


class PythonRunnerTool(BaseTool):
    """智能Python脚本执行工具。

    功能：
    1. 自动检测可用的虚拟环境
    2. 支持使用UV工具加速
    3. 自动安装缺失依赖
    4. 安全执行Python脚本
    5. 生成执行汇总报告
    6. 智能检测GUI程序并支持非交互模式
    """

    name = "python_runner"
    emoji = "🐍"
    title = "Python脚本执行器"
    description = "智能执行Python脚本，自动处理虚拟环境和依赖"
    timeout = 300.0  # 5分钟超时

    # 项目默认虚拟环境路径
    PROJECT_VENV_PATHS = [
        Path(r"D:\python_projects\openclaw_demo\winclaw\.venv"),
        Path(__file__).resolve().parent.parent.parent / ".venv",
    ]

    def __init__(
        self,
        timeout: int = 300,
        max_output_length: int = 10000,
        prefer_uv: bool = True,
        auto_install_deps: bool = True,
        default_headless: bool = True,  # 默认使用无头模式执行GUI程序
    ):
        self.timeout = timeout
        self.max_output_length = max_output_length
        self.prefer_uv = prefer_uv
        self.auto_install_deps = auto_install_deps
        self.default_headless = default_headless
        self._detected_venv: VenvInfo | None = None

    def get_actions(self) -> list[ActionDef]:
        return [
            ActionDef(
                name="execute",
                description=(
                    "智能执行Python脚本。自动检测和使用虚拟环境，安装缺失依赖，"
                    "返回详细的执行报告。支持GUI程序的非交互模式执行。"
                ),
                parameters={
                    "script_path": {
                        "type": "string",
                        "description": "Python脚本的绝对路径",
                    },
                    "requirements": {
                        "type": "string",
                        "description": "需要的依赖包列表，逗号分隔（可选，如：numpy,pandas,requests）",
                    },
                    "venv_path": {
                        "type": "string",
                        "description": "指定使用的虚拟环境路径（可选，不指定则自动检测）",
                    },
                    "args": {
                        "type": "string",
                        "description": "传递给脚本的命令行参数（可选）",
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "脚本执行的工作目录（可选）",
                    },
                    "headless": {
                        "type": "boolean",
                        "description": "是否使用无头模式执行GUI程序（默认true，自动禁用显示）",
                    },
                    "save_figure": {
                        "type": "string",
                        "description": "保存matplotlib图表的路径（可选，如 output.png）",
                    },
                },
                required_params=["script_path"],
            ),
            ActionDef(
                name="detect_venv",
                description="检测系统中可用的Python虚拟环境和Python解释器",
                parameters={},
                required_params=[],
            ),
            ActionDef(
                name="analyze_script",
                description="分析Python脚本内容，检测GUI库和执行模式建议",
                parameters={
                    "script_path": {
                        "type": "string",
                        "description": "要分析的脚本路径",
                    },
                },
                required_params=["script_path"],
            ),
            ActionDef(
                name="create_venv",
                description="创建新的虚拟环境",
                parameters={
                    "venv_path": {
                        "type": "string",
                        "description": "虚拟环境创建路径（可选，默认创建临时环境）",
                    },
                    "use_uv": {
                        "type": "boolean",
                        "description": "是否优先使用UV工具（默认true）",
                    },
                },
                required_params=[],
            ),
            ActionDef(
                name="install_deps",
                description="在虚拟环境中安装Python依赖",
                parameters={
                    "packages": {
                        "type": "string",
                        "description": "要安装的包名列表，逗号分隔",
                    },
                    "venv_path": {
                        "type": "string",
                        "description": "虚拟环境路径（可选，使用检测到的环境）",
                    },
                    "use_uv": {
                        "type": "boolean",
                        "description": "是否使用UV安装（更快）",
                    },
                },
                required_params=["packages"],
            ),
            ActionDef(
                name="run_code",
                description="直接执行Python代码片段（不创建文件）",
                parameters={
                    "code": {
                        "type": "string",
                        "description": "要执行的Python代码",
                    },
                    "requirements": {
                        "type": "string",
                        "description": "需要的依赖包列表，逗号分隔（可选）",
                    },
                    "headless": {
                        "type": "boolean",
                        "description": "是否使用无头模式（默认true）",
                    },
                },
                required_params=["code"],
            ),
        ]

    async def execute(self, action: str, params: dict[str, Any]) -> ToolResult:
        handlers = {
            "execute": self._execute_script,
            "detect_venv": self._detect_venv_action,
            "analyze_script": self._analyze_script_action,
            "create_venv": self._create_venv_action,
            "install_deps": self._install_deps_action,
            "run_code": self._run_code_action,
        }
        handler = handlers.get(action)
        if handler is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"不支持的动作: {action}",
            )
        return await handler(params)

    # ------------------------------------------------------------------
    # 脚本分析
    # ------------------------------------------------------------------

    def _analyze_script_content(self, script_content: str) -> ScriptAnalysis:
        """分析脚本内容，检测GUI库和执行模式。"""
        analysis = ScriptAnalysis()
        
        # 检测GUI库
        for lib_name, patterns in GUI_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, script_content, re.IGNORECASE):
                    analysis.is_gui_program = True
                    if lib_name not in analysis.gui_libraries:
                        analysis.gui_libraries.append(lib_name)
                    break
        
        # 检测main块
        if re.search(r"if\s+__name__\s*==\s*['\"]__main__['\"]", script_content):
            analysis.has_main_block = True
        
        # 提取imports
        import_pattern = r"^(?:import|from)\s+(\w+)"
        for match in re.finditer(import_pattern, script_content, re.MULTILINE):
            module = match.group(1)
            if module not in analysis.imports:
                analysis.imports.append(module)
        
        # 建议执行模式
        if analysis.is_gui_program:
            analysis.suggested_mode = "headless"
        else:
            analysis.suggested_mode = "auto"
        
        return analysis

    async def _analyze_script_action(self, params: dict[str, Any]) -> ToolResult:
        """分析脚本内容的动作。"""
        script_path = Path(params["script_path"]).expanduser().resolve()
        if not script_path.exists():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"脚本文件不存在: {script_path}",
            )
        
        try:
            content = script_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"读取脚本失败: {e}",
            )
        
        analysis = self._analyze_script_content(content)
        
        lines = ["## 🔍 Python脚本分析结果", ""]
        lines.append(f"**脚本路径**: `{script_path}`")
        lines.append(f"**是否GUI程序**: {'是' if analysis.is_gui_program else '否'}")
        
        if analysis.gui_libraries:
            lines.append(f"**检测到的GUI库**: {', '.join(analysis.gui_libraries)}")
        
        lines.append(f"**包含main块**: {'是' if analysis.has_main_block else '否'}")
        lines.append(f"**建议执行模式**: {analysis.suggested_mode}")
        
        if analysis.imports:
            lines.append(f"\n**导入的模块**: {', '.join(analysis.imports[:20])}")
            if len(analysis.imports) > 20:
                lines.append(f"  ...(共{len(analysis.imports)}个)")
        
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(lines),
            data={
                "is_gui_program": analysis.is_gui_program,
                "gui_libraries": analysis.gui_libraries,
                "has_main_block": analysis.has_main_block,
                "suggested_mode": analysis.suggested_mode,
                "imports": analysis.imports,
            },
        )

    # ------------------------------------------------------------------
    # 核心功能：执行Python脚本
    # ------------------------------------------------------------------

    async def _execute_script(self, params: dict[str, Any]) -> ToolResult:
        """执行Python脚本的核心逻辑。"""
        start_time = time.time()
        summary = ExecutionSummary(script_path=params.get("script_path", ""))
        
        # 1. 验证脚本路径
        script_path = Path(params["script_path"]).expanduser().resolve()
        if not script_path.exists():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"脚本文件不存在: {script_path}",
            )
        if not script_path.is_file():
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"路径不是文件: {script_path}",
            )
        summary.script_path = str(script_path)
        summary.steps.append(f"验证脚本文件: {script_path}")

        # 2. 分析脚本内容
        try:
            script_content = script_path.read_text(encoding="utf-8", errors="replace")
            script_analysis = self._analyze_script_content(script_content)
            summary.script_analysis = script_analysis
            if script_analysis.is_gui_program:
                summary.steps.append(f"检测到GUI库: {', '.join(script_analysis.gui_libraries)}")
        except Exception as e:
            script_analysis = ScriptAnalysis()
            summary.steps.append(f"⚠ 脚本分析失败: {e}")

        # 3. 检测或获取虚拟环境
        venv_path = params.get("venv_path")
        if venv_path:
            venv_info = await self._get_venv_info(Path(venv_path))
        else:
            venv_info = await self._detect_best_venv()
        
        if venv_info is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="未找到可用的Python环境，请确保系统已安装Python",
            )
        
        summary.venv_used = str(venv_info.path)
        summary.steps.append(f"使用虚拟环境: {venv_info.path}")
        if venv_info.is_project_venv:
            summary.steps.append("(使用项目内置虚拟环境)")
        if venv_info.is_uv:
            summary.steps.append("(UV环境)")

        # 4. 安装依赖
        requirements = params.get("requirements", "")
        if requirements:
            packages = [p.strip() for p in requirements.split(",") if p.strip()]
            if packages:
                summary.steps.append(f"检测到需要安装的依赖: {', '.join(packages)}")
                if self.auto_install_deps:
                    install_result = await self._install_packages(venv_info, packages)
                    if install_result:
                        summary.dependencies_installed.extend(packages)
                        summary.steps.append(f"✓ 已安装依赖: {', '.join(packages)}")
                    else:
                        summary.steps.append(f"⚠ 部分依赖安装可能失败")

        # 5. 确定执行模式
        headless = params.get("headless", self.default_headless)
        save_figure = params.get("save_figure", "")
        
        if script_analysis.is_gui_program and headless:
            summary.execution_mode = "headless"
            summary.steps.append("使用无头模式执行（禁用GUI显示）")
        elif script_analysis.is_gui_program:
            summary.execution_mode = "gui"
            summary.steps.append("使用GUI模式执行")
        else:
            summary.execution_mode = "normal"

        # 6. 准备执行环境
        working_dir = params.get("working_dir")
        if working_dir:
            working_dir = Path(working_dir).expanduser().resolve()
        else:
            working_dir = script_path.parent

        # 构建环境变量（确保中文编码）
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        
        # 无头模式设置
        if summary.execution_mode == "headless":
            env["MPLBACKEND"] = "Agg"  # matplotlib非交互后端
            if save_figure:
                env["SAVE_FIGURE_PATH"] = str(Path(save_figure).resolve())

        # 7. 执行脚本
        summary.steps.append("开始执行脚本...")
        
        args = params.get("args", "")
        cmd = [str(venv_info.python_path), str(script_path)]
        if args:
            cmd.extend(args.split())

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(working_dir) if working_dir else None,
                env=env,
            )
            
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout,
            )
            
            summary.return_code = proc.returncode or 0
            # 使用utf-8解码，处理中文
            summary.output = stdout.decode("utf-8", errors="replace")
            summary.error = stderr.decode("utf-8", errors="replace")
            
            # 过滤掉字体警告和非交互警告（常见的matplotlib警告）
            if summary.error:
                filtered_errors = []
                for line in summary.error.split("\n"):
                    # 过滤掉字体缺失警告、非交互警告、重复的警告
                    skip_patterns = [
                        "missing from font",
                        "Glyph",
                        "FigureCanvasAgg is non-interactive",
                        "plt.tight_layout()",
                        "UserWarning:",
                    ]
                    should_skip = any(pattern in line for pattern in skip_patterns)
                    if not should_skip:
                        filtered_errors.append(line)
                summary.error = "\n".join(filtered_errors).strip()
            
            if proc.returncode == 0:
                summary.success = True
                summary.steps.append("✓ 脚本执行成功")
                
                # 检查是否生成了图片
                if save_figure:
                    figure_path = Path(save_figure).resolve()
                    if figure_path.exists():
                        summary.steps.append(f"✓ 图表已保存: {figure_path}")
            else:
                summary.success = False
                summary.steps.append(f"✗ 脚本执行失败，返回码: {proc.returncode}")
                
        except asyncio.TimeoutError:
            proc.kill()
            summary.success = False
            summary.error = f"脚本执行超时（{self.timeout}秒）"
            summary.steps.append(f"✗ 执行超时")
        except Exception as e:
            summary.success = False
            summary.error = f"执行异常: {e}"
            summary.steps.append(f"✗ 执行异常: {e}")

        summary.duration_seconds = time.time() - start_time

        # 8. 生成报告
        report = summary.to_markdown()
        
        return ToolResult(
            status=ToolResultStatus.SUCCESS if summary.success else ToolResultStatus.ERROR,
            output=report,
            error=summary.error if not summary.success else "",
            data={
                "return_code": summary.return_code,
                "duration_seconds": summary.duration_seconds,
                "venv_path": str(venv_info.path),
                "dependencies_installed": summary.dependencies_installed,
                "execution_mode": summary.execution_mode,
                "is_gui_program": script_analysis.is_gui_program if script_analysis else False,
            },
        )

    # ------------------------------------------------------------------
    # 虚拟环境检测
    # ------------------------------------------------------------------

    async def _detect_venv_action(self, params: dict[str, Any]) -> ToolResult:
        """检测可用虚拟环境的动作。"""
        venvs = await self._detect_all_venvs()
        system_pythons = await self._detect_system_pythons()
        
        lines = ["## 🔍 Python环境检测结果", ""]
        
        if venvs:
            lines.append("### 虚拟环境")
            for v in venvs:
                flags = []
                if v.is_project_venv:
                    flags.append("项目环境")
                if v.is_uv:
                    flags.append("UV")
                flag_str = f" ({', '.join(flags)})" if flags else ""
                lines.append(f"- `{v.path}`{flag_str}")
                lines.append(f"  - Python: `{v.python_path}`")
            lines.append("")
        
        if system_pythons:
            lines.append("### 系统Python")
            for p in system_pythons:
                lines.append(f"- `{p}`")
            lines.append("")
        
        # 检测UV工具
        uv_available = shutil.which("uv") is not None
        lines.append("### 工具状态")
        lines.append(f"- UV: {'✅ 可用' if uv_available else '❌ 不可用'}")
        
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output="\n".join(lines),
            data={
                "venvs": [{"path": str(v.path), "python": str(v.python_path)} for v in venvs],
                "system_pythons": [str(p) for p in system_pythons],
                "uv_available": uv_available,
            },
        )

    async def _detect_all_venvs(self) -> list[VenvInfo]:
        """检测所有可用的虚拟环境。"""
        venvs = []
        
        # 检测项目虚拟环境
        for venv_path in self.PROJECT_VENV_PATHS:
            if venv_path.exists():
                venv_info = await self._get_venv_info(venv_path)
                if venv_info:
                    venv_info.is_project_venv = True
                    venvs.append(venv_info)
        
        # 检测当前目录及父目录的.venv
        current = Path.cwd()
        for _ in range(5):  # 向上查找5层
            venv_candidate = current / ".venv"
            if venv_candidate.exists():
                venv_info = await self._get_venv_info(venv_candidate)
                if venv_info and venv_info not in venvs:
                    venvs.append(venv_info)
            parent = current.parent
            if parent == current:
                break
            current = parent
        
        # 检测VIRTUAL_ENV环境变量
        venv_env = os.environ.get("VIRTUAL_ENV")
        if venv_env:
            venv_info = await self._get_venv_info(Path(venv_env))
            if venv_info and venv_info not in venvs:
                venvs.append(venv_info)
        
        return venvs

    async def _detect_system_pythons(self) -> list[Path]:
        """检测系统中的Python解释器。"""
        pythons = []
        
        # Windows: 使用where命令
        try:
            proc = await asyncio.create_subprocess_exec(
                "where", "python",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            for line in stdout.decode("utf-8", errors="replace").strip().split("\n"):
                p = Path(line.strip())
                if p.exists() and p not in pythons:
                    pythons.append(p)
        except Exception:
            pass
        
        # 也检测python3
        try:
            proc = await asyncio.create_subprocess_exec(
                "where", "python3",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            for line in stdout.decode("utf-8", errors="replace").strip().split("\n"):
                p = Path(line.strip())
                if p.exists() and p not in pythons:
                    pythons.append(p)
        except Exception:
            pass
        
        return pythons

    async def _detect_best_venv(self) -> VenvInfo | None:
        """检测最佳可用的虚拟环境。"""
        venvs = await self._detect_all_venvs()
        
        # 优先返回项目虚拟环境
        for v in venvs:
            if v.is_project_venv:
                return v
        
        # 其次返回其他虚拟环境
        if venvs:
            return venvs[0]
        
        # 最后使用系统Python
        system_pythons = await self._detect_system_pythons()
        if system_pythons:
            return VenvInfo(
                path=system_pythons[0].parent,
                python_path=system_pythons[0],
                pip_path=system_pythons[0].parent / "pip.exe",
            )
        
        return None

    async def _get_venv_info(self, venv_path: Path) -> VenvInfo | None:
        """获取虚拟环境详细信息。"""
        if not venv_path.exists():
            return None
        
        # Windows: Scripts/python.exe
        python_path = venv_path / "Scripts" / "python.exe"
        pip_path = venv_path / "Scripts" / "pip.exe"
        
        # Linux/Mac: bin/python
        if not python_path.exists():
            python_path = venv_path / "bin" / "python"
            pip_path = venv_path / "bin" / "pip"
        
        if not python_path.exists():
            return None
        
        # 检测是否为UV创建的环境
        is_uv = (venv_path / ".uv").exists() or "uv" in venv_path.name.lower()
        
        return VenvInfo(
            path=venv_path,
            python_path=python_path,
            pip_path=pip_path if pip_path.exists() else python_path.parent / "pip",
            is_uv=is_uv,
        )

    # ------------------------------------------------------------------
    # 虚拟环境创建
    # ------------------------------------------------------------------

    async def _create_venv_action(self, params: dict[str, Any]) -> ToolResult:
        """创建虚拟环境的动作。"""
        use_uv = params.get("use_uv", True) and shutil.which("uv") is not None
        venv_path = params.get("venv_path")
        
        if venv_path:
            venv_path = Path(venv_path).expanduser().resolve()
        else:
            venv_path = Path(tempfile.mkdtemp(prefix="pyrunner_venv_"))
        
        venv_info = await self._create_venv(venv_path, use_uv)
        
        if venv_info is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"创建虚拟环境失败",
            )
        
        output = f"""## ✅ 虚拟环境创建成功

- **路径**: `{venv_info.path}`
- **Python**: `{venv_info.python_path}`
- **使用UV**: {'是' if venv_info.is_uv else '否'}
"""
        return ToolResult(
            status=ToolResultStatus.SUCCESS,
            output=output,
            data={
                "venv_path": str(venv_info.path),
                "python_path": str(venv_info.python_path),
            },
        )

    async def _create_venv(self, venv_path: Path, use_uv: bool = True) -> VenvInfo | None:
        """创建新的虚拟环境。"""
        try:
            if use_uv and shutil.which("uv"):
                # 使用UV创建
                proc = await asyncio.create_subprocess_exec(
                    "uv", "venv", str(venv_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
            else:
                # 使用标准venv
                system_python = await self._detect_system_pythons()
                if not system_python:
                    return None
                proc = await asyncio.create_subprocess_exec(
                    str(system_python[0]), "-m", "venv", str(venv_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
            
            return await self._get_venv_info(venv_path)
        except Exception as e:
            logger.error("创建虚拟环境失败: %s", e)
            return None

    # ------------------------------------------------------------------
    # 依赖安装
    # ------------------------------------------------------------------

    async def _install_deps_action(self, params: dict[str, Any]) -> ToolResult:
        """安装依赖的动作。"""
        packages_str = params.get("packages", "")
        if not packages_str:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="未指定要安装的包",
            )
        
        packages = [p.strip() for p in packages_str.split(",") if p.strip()]
        use_uv = params.get("use_uv", True) and shutil.which("uv") is not None
        venv_path = params.get("venv_path")
        
        if venv_path:
            venv_info = await self._get_venv_info(Path(venv_path))
        else:
            venv_info = await self._detect_best_venv()
        
        if venv_info is None:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="未找到可用的虚拟环境",
            )
        
        result = await self._install_packages(venv_info, packages, use_uv)
        
        if result:
            output = f"## ✅ 依赖安装成功\n\n已安装: {', '.join(packages)}"
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=output,
                data={"packages": packages},
            )
        else:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"部分依赖安装失败",
            )

    async def _install_packages(
        self, 
        venv_info: VenvInfo, 
        packages: list[str],
        use_uv: bool = True,
    ) -> bool:
        """在虚拟环境中安装包。"""
        if not packages:
            return True
        
        try:
            if use_uv and shutil.which("uv"):
                # 使用UV安装（更快）
                cmd = ["uv", "pip", "install", "--python", str(venv_info.python_path)]
                cmd.extend(packages)
            else:
                # 使用pip安装
                cmd = [str(venv_info.python_path), "-m", "pip", "install"]
                cmd.extend(packages)
            
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=120,  # 2分钟超时
            )
            
            if proc.returncode == 0:
                logger.info("成功安装依赖: %s", ", ".join(packages))
                return True
            else:
                logger.warning("安装依赖可能失败: %s", stderr.decode())
                return False
                
        except asyncio.TimeoutError:
            logger.error("安装依赖超时")
            return False
        except Exception as e:
            logger.error("安装依赖异常: %s", e)
            return False

    # ------------------------------------------------------------------
    # 代码执行
    # ------------------------------------------------------------------

    async def _run_code_action(self, params: dict[str, Any]) -> ToolResult:
        """执行Python代码片段。"""
        code = params.get("code", "")
        if not code:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error="代码不能为空",
            )
        
        # 如果代码包含matplotlib等GUI库，自动添加headless设置
        headless = params.get("headless", True)
        if headless and ("matplotlib" in code or "plt." in code):
            # 在代码开头添加matplotlib后端设置
            headless_preamble = "import matplotlib\nmatplotlib.use('Agg')\n"
            if not code.startswith("import matplotlib"):
                code = headless_preamble + code
        
        # 创建临时脚本文件
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(code)
            temp_script = Path(f.name)
        
        try:
            # 复用execute逻辑
            result = await self._execute_script({
                "script_path": str(temp_script),
                "requirements": params.get("requirements", ""),
                "headless": headless,
            })
            return result
        finally:
            # 清理临时文件
            try:
                temp_script.unlink()
            except Exception:
                pass
