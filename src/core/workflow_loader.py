"""工作流模板加载器 — 管理预置工作流模板的发现、加载和触发。

功能：
1. 扫描 config/workflows/ 目录下的所有工作流模板
2. 按名称/标签/类别查询工作流模板
3. 支持自然语言触发（关键词匹配）
4. 支持变量注入和参数覆盖
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.core.workflow import WorkflowDefinition, WorkflowEngine

logger = logging.getLogger(__name__)

# 默认模板目录
_DEFAULT_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "workflows"


class WorkflowTemplate:
    """工作流模板元数据。"""
    
    def __init__(
        self,
        name: str,
        file_path: Path,
        definition: WorkflowDefinition,
        tags: list[str] = None,
        category: str = "",
    ):
        self.name = name
        self.file_path = file_path
        self.definition = definition
        self.tags = tags or []
        self.category = category
    
    def __repr__(self) -> str:
        return f"WorkflowTemplate(name={self.name}, category={self.category}, tags={self.tags})"


class WorkflowLoader:
    """工作流模板加载器。
    
    职责：
    - 扫描并加载所有预置工作流模板
    - 提供模板查询接口（按名称/标签/类别）
    - 支持自然语言触发（关键词匹配）
    """
    
    def __init__(
        self,
        workflow_engine: WorkflowEngine,
        templates_dir: Path | None = None,
    ):
        self.workflow_engine = workflow_engine
        self.templates_dir = templates_dir or _DEFAULT_TEMPLATES_DIR
        
        # 模板缓存（name -> WorkflowTemplate）
        self._templates: dict[str, WorkflowTemplate] = {}
        
        # 触发关键词映射（keyword -> workflow_name）
        self._trigger_keywords: dict[str, str] = {
            "整理桌面": "desktop_organizer",
            "桌面整理": "desktop_organizer",
            "清理桌面": "desktop_organizer",
            "网页采集": "web_scraper",
            "爬取网页": "web_scraper",
            "抓取网页": "web_scraper",
            "系统清理": "system_cleanup",
            "清理系统": "system_cleanup",
            "检查系统": "system_cleanup",
            "截屏分析": "smart_screenshot_analysis",
            "智能截屏": "smart_screenshot_analysis",
        }
    
    # ----------------------------------------------------------------
    # 模板加载
    # ----------------------------------------------------------------
    
    def load_all_templates(self) -> int:
        """扫描并加载所有模板文件。
        
        Returns:
            加载的模板数量
        """
        if not self.templates_dir.exists():
            logger.warning(f"模板目录不存在: {self.templates_dir}")
            return 0
        
        count = 0
        for file_path in self.templates_dir.glob("*.yaml"):
            try:
                # 加载工作流定义
                definition = self.workflow_engine.load_from_file(file_path)
                
                # 提取元数据
                # 注意：我们需要从原始 YAML 读取额外的 tags/category 字段
                import yaml
                with open(file_path, "r", encoding="utf-8") as f:
                    raw_data = yaml.safe_load(f)
                
                template = WorkflowTemplate(
                    name=definition.name,
                    file_path=file_path,
                    definition=definition,
                    tags=raw_data.get("tags", []),
                    category=raw_data.get("category", ""),
                )
                
                self._templates[template.name] = template
                count += 1
                logger.info(f"已加载工作流模板: {template.name} (类别: {template.category})")
            
            except Exception as e:
                logger.error(f"加载模板失败 {file_path}: {e}")
        
        logger.info(f"共加载 {count} 个工作流模板")
        return count
    
    def reload(self) -> int:
        """重新加载所有模板。"""
        self._templates.clear()
        return self.load_all_templates()
    
    # ----------------------------------------------------------------
    # 模板查询
    # ----------------------------------------------------------------
    
    def get_template(self, name: str) -> WorkflowTemplate | None:
        """按名称获取模板。"""
        return self._templates.get(name)
    
    def list_templates(self) -> list[WorkflowTemplate]:
        """列出所有模板。"""
        return list(self._templates.values())
    
    def find_by_tag(self, tag: str) -> list[WorkflowTemplate]:
        """按标签查询模板。"""
        return [t for t in self._templates.values() if tag in t.tags]
    
    def find_by_category(self, category: str) -> list[WorkflowTemplate]:
        """按类别查询模板。"""
        return [t for t in self._templates.values() if t.category == category]
    
    def search(self, keyword: str) -> list[WorkflowTemplate]:
        """模糊搜索（名称/描述/标签/类别）。"""
        keyword_lower = keyword.lower()
        results = []
        
        for template in self._templates.values():
            # 搜索名称
            if keyword_lower in template.name.lower():
                results.append(template)
                continue
            
            # 搜索描述
            if keyword_lower in template.definition.description.lower():
                results.append(template)
                continue
            
            # 搜索标签
            if any(keyword_lower in tag.lower() for tag in template.tags):
                results.append(template)
                continue
            
            # 搜索类别
            if keyword_lower in template.category.lower():
                results.append(template)
                continue
        
        return results
    
    # ----------------------------------------------------------------
    # 自然语言触发
    # ----------------------------------------------------------------
    
    def match_trigger(self, user_input: str) -> str | None:
        """根据用户输入匹配触发关键词。
        
        Args:
            user_input: 用户输入的自然语言
            
        Returns:
            匹配到的工作流名称，如果没有匹配返回 None
        """
        user_input_lower = user_input.lower()
        
        for keyword, workflow_name in self._trigger_keywords.items():
            if keyword in user_input_lower:
                logger.info(f"触发关键词 '{keyword}' 匹配到工作流: {workflow_name}")
                return workflow_name
        
        return None
    
    def add_trigger(self, keyword: str, workflow_name: str) -> None:
        """添加触发关键词。"""
        self._trigger_keywords[keyword] = workflow_name
        logger.info(f"添加触发关键词: '{keyword}' -> {workflow_name}")
    
    # ----------------------------------------------------------------
    # 执行工作流
    # ----------------------------------------------------------------
    
    async def execute_template(
        self,
        template_name: str,
        variables: dict[str, Any] | None = None,
    ) -> Any:
        """执行工作流模板。
        
        Args:
            template_name: 模板名称
            variables: 变量注入（会覆盖模板中的默认变量）
            
        Returns:
            WorkflowContext
        """
        template = self.get_template(template_name)
        if not template:
            raise ValueError(f"工作流模板不存在: {template_name}")
        
        # 合并变量
        merged_vars = {**template.definition.variables, **(variables or {})}
        
        # 执行工作流
        return await self.workflow_engine.execute(
            template.definition,
            initial_vars=merged_vars,
        )
    
    # ----------------------------------------------------------------
    # 工具方法
    # ----------------------------------------------------------------
    
    def get_summary(self) -> str:
        """获取所有模板的摘要信息。"""
        lines = [f"已加载 {len(self._templates)} 个工作流模板:\n"]
        
        # 按类别分组
        by_category: dict[str, list[WorkflowTemplate]] = {}
        for template in self._templates.values():
            category = template.category or "其他"
            by_category.setdefault(category, []).append(template)
        
        for category, templates in sorted(by_category.items()):
            lines.append(f"\n📁 {category}:")
            for t in templates:
                tags_str = ", ".join(t.tags) if t.tags else "无标签"
                lines.append(f"  • {t.name}: {t.definition.description}")
                lines.append(f"    标签: {tags_str}")
        
        return "\n".join(lines)
