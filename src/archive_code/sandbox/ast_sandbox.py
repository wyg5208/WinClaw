"""AST 安全解析器。

使用 AST 解析 Python 代码，只允许安全的语法结构。
"""

import ast
import sys
from typing import Any

from src.tools.sandbox.safe_modules import (
    SAFE_BUILTINS,
    SAFE_DATETIME,
    SAFE_JSON,
    SAFE_MATH,
    SAFE_RANDOM,
    SAFE_RE,
    SAFE_TYPES,
    is_path_allowed,
)

# 允许的模块名
ALLOWED_MODULES = {
    "math", "random", "datetime", "json", "re",
    "collections", "itertools", "functools", "operator",
    "string", "heapq", "hashlib", "base64",
}

# 允许的内置函数
ALLOWED_BUILTINS = set(SAFE_BUILTINS.keys())

    # 允许的 AST 节点类型
ALLOWED_NODES = {
    # 模块和程序（顶层）
    ast.Module,
    ast.Interactive,
    ast.Expression,
    ast.Module,
    # 表达式
    ast.Expr,
    ast.BinOp,
    ast.UnaryOp,
    ast.Call,
    ast.Compare,
    ast.BoolOp,
    # 常量
    ast.Constant,
    ast.Num,
    ast.Str,
    ast.Bytes,
    ast.NameConstant,
    # f-string 支持
    ast.JoinedStr,
    ast.FormattedValue,
    # 名称
    ast.Name,
    ast.Store,
    ast.Load,
    ast.Del,
    ast.Attribute,
    # 导入语句
    ast.Import,
    ast.ImportFrom,
    ast.alias,
    # 列表/字典/集合
    ast.List,
    ast.Dict,
    ast.Set,
    ast.Tuple,
    # 切片
    ast.Index,
    ast.Slice,
    ast.ExtSlice,
    # 关键字参数和参数
    ast.keyword,
    ast.arguments,
    ast.arg,
    # 下标访问
    ast.Subscript,
    # 比较运算符
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Is,
    ast.IsNot,
    ast.In,
    ast.NotIn,
    # 布尔运算符
    ast.And,
    ast.Or,
    ast.Not,
    # 二元运算符
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.LShift,
    ast.RShift,
    ast.BitAnd,
    ast.BitOr,
    ast.BitXor,
    # 一元运算符
    ast.UAdd,
    ast.USub,
    ast.Invert,
    # 赋值
    ast.Assign,
    ast.AnnAssign,
    ast.AugAssign,
    # 列表/字典/集合推导式
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.comprehension,
    # 生成器表达式
    ast.GeneratorExp,
    # 条件表达式
    ast.IfExp,
    # if语句
    ast.If,
    # Lambda
    ast.Lambda,
    # 函数定义（允许简单函数）
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    # Pass/Break/Continue
    ast.Pass,
    ast.Break,
    ast.Continue,
    ast.Return,
    # For/While 循环
    ast.For,
    ast.While,
    # Try/Except/Finally
    ast.Try,
    ast.ExceptHandler,
    ast.Raise,
    # With 语句
    ast.With,
    ast.withitem,
    # 全局/非局部
    ast.Global,
    ast.Nonlocal,
    # 类定义（可选，允许简单类）
    ast.ClassDef,
    # AugAssign 扩展
    ast.AugAssign,
}

# 禁止的模块属性（危险操作）
FORBIDDEN_ATTRS = {
    # os 模块
    "os": {
        "system", "popen", "spawn", "exec", "fork", "kill",
        "remove", "rmdir", "unlink", "rename", "mkdir",
        "chmod", "chown", "access", "pathsep",
        "environ", "getenv", "putenv",
    },
    # sys 模块
    "sys": {
        "exit", "quit", "breakpointhook",
        "exc_info", "excepthook", "frame",
        "stdin", "stdout", "stderr",
    },
    # subprocess 模块
    "subprocess": {
        "call", "run", "Popen", "spawn",
    },
    # requests/urllib
    "requests": {"get", "post", "put", "delete", "session"},
    "urllib": {"urlopen", "request"},
    # socket/network
    "socket": {"socket", "create_connection"},
    # 文件系统
    "shutil": {"rmtree", "move", "copy", "copyfile", "copytree"},
    # 其他危险模块
    "importlib": {"__import__"},
    "builtins": {"__import__"},
}


class SecurityError(Exception):
    """安全检查失败异常。"""
    pass


class ASTSandbox:
    """AST 安全解析器。"""
    
    def __init__(self, max_complexity: int = 500, max_depth: int = 20):
        """初始化沙盒。
        
        Args:
            max_complexity: 最大复杂度（节点数）
            max_depth: 最大嵌套深度
        """
        self.max_complexity = max_complexity
        self.max_depth = max_depth
        self._node_count = 0
        self._depth = 0
    
    def validate(self, code: str) -> ast.AST:
        """验证代码安全性并返回 AST。
        
        Args:
            code: Python 代码字符串
            
        Returns:
            解析后的 AST 树
            
        Raises:
            SecurityError: 代码包含不安全模式
            SyntaxError: 代码语法错误
        """
        self._node_count = 0
        self._depth = 0
        
        try:
            tree = ast.parse(code, mode="exec")
        except SyntaxError as e:
            raise SyntaxError(f"语法错误: {e.msg} (行 {e.lineno})")
        
        # 检查节点数量（防止资源耗尽）
        if self._node_count > self.max_complexity:
            raise SecurityError(
                f"代码过于复杂（{self._node_count} 节点），"
                f"最大允许 {self.max_complexity} 节点"
            )
        
        # 遍历 AST 检查安全性
        self._check_node(tree)
        
        return tree
    
    def _check_node(self, node: ast.AST, depth: int = 0) -> None:
        """递归检查 AST 节点安全性。"""
        if depth > self.max_depth:
            raise SecurityError(f"嵌套深度超过限制 ({self.max_depth})")
        
        node_type = type(node)
        
        # 检查是否允许的节点类型
        if node_type not in ALLOWED_NODES:
            raise SecurityError(
                f"不支持的语法: {node_type.__name__} "
                f"(行 {getattr(node, 'lineno', '?')})"
            )
        
        self._node_count += 1
        if self._node_count > self.max_complexity:
            raise SecurityError(f"代码过于复杂，超过 {self.max_complexity} 节点限制")
        
        # 递归检查子节点
        for child in ast.iter_child_nodes(node):
            self._check_node(child, depth + 1)
        
        # 特殊检查
        self._check_special_nodes(node)
    
    def _check_special_nodes(self, node: ast.AST) -> None:
        """检查特殊节点。"""
        # 检查 Import/ImportFrom
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            self._check_import(node)
        
        # 检查函数调用
        elif isinstance(node, ast.Call):
            self._check_call(node)
        
        # 检查属性访问
        elif isinstance(node, ast.Attribute):
            self._check_attribute(node)
        
        # 检查名称（变量引用）
        elif isinstance(node, ast.Name):
            self._check_name(node)
        
        # 检查赋值
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            self._check_assignment(node)
        
        # 检查函数/类定义（允许简单函数和类）
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            self._check_function_or_class(node)
        
        # 检查 with 语句
        elif isinstance(node, ast.With):
            self._check_with(node)
        
        # 检查 Try 语句
        elif isinstance(node, ast.Try):
            self._check_try(node)
        
        # 检查 For/While 循环
        elif isinstance(node, (ast.For, ast.While)):
            self._check_loop(node)
    
    def _check_import(self, node: ast.Import | ast.ImportFrom) -> None:
        """检查导入语句。"""
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name.split(".")[0]
                if module_name not in ALLOWED_MODULES:
                    raise SecurityError(
                        f"不允许导入模块: {alias.name} "
                        f"(行 {getattr(node, 'lineno', '?')})"
                    )
        
        elif isinstance(node, ast.ImportFrom):
            module_name = node.module.split(".")[0] if node.module else ""
            if module_name and module_name not in ALLOWED_MODULES:
                raise SecurityError(
                    f"不允许从模块导入: {node.module} "
                    f"(行 {getattr(node, 'lineno', '?')})"
                )
    
    def _check_call(self, node: ast.Call) -> None:
        """检查函数调用。"""
        # 检查 __import__ 调用
        if isinstance(node.func, ast.Name) and node.func.id == "__import__":
            raise SecurityError(
                f"不允许使用 __import__ "
                f"(行 {getattr(node, 'lineno', '?')})"
            )
        
        # 检查危险属性调用
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                mod_name = node.func.value.id
                if mod_name in FORBIDDEN_ATTRS:
                    if node.func.attr in FORBIDDEN_ATTRS[mod_name]:
                        raise SecurityError(
                            f"不允许调用 {mod_name}.{node.func.attr} "
                            f"(行 {getattr(node, 'lineno', '?')})"
                        )
    
    def _check_attribute(self, node: ast.Attribute) -> None:
        """检查属性访问。"""
        # 检查危险属性
        if isinstance(node.value, ast.Name):
            mod_name = node.value.id
            if mod_name in FORBIDDEN_ATTRS:
                if node.attr in FORBIDDEN_ATTRS[mod_name]:
                    raise SecurityError(
                        f"不允许访问 {mod_name}.{node.attr} "
                        f"(行 {getattr(node, 'lineno', '?')})"
                    )
    
    def _check_name(self, node: ast.Name) -> None:
        """检查名称引用。"""
        # 不检查 ctx，因为我们在验证阶段
    
    def _check_assignment(self, node: ast.Assign | ast.AnnAssign | ast.AugAssign) -> None:
        """检查赋值语句。"""
        # 允许基本赋值
    
    def _check_with(self, node: ast.With) -> None:
        """检查 with 语句。"""
        for item in node.items:
            if item.context_expr:
                # 检查是否使用 open
                if isinstance(item.context_expr, ast.Call):
                    func = item.context_expr.func
                    if isinstance(func, ast.Name) and func.id == "open":
                        # 检查路径是否允许
                        if item.context_expr.args:
                            arg = item.context_expr.args[0]
                            if isinstance(arg, ast.Constant):
                                if not is_path_allowed(str(arg.value)):
                                    raise SecurityError(
                                        f"不允许访问路径: {arg.value} "
                                        f"(行 {getattr(node, 'lineno', '?')})"
                                    )
    
    def _check_try(self, node: ast.Try) -> None:
        """检查 try 语句。"""
        # 只允许安全的异常类型
        for handler in node.handlers:
            if handler.type:
                if isinstance(handler.type, ast.Name):
                    exc_name = handler.type.id
                    # 检查是否是允许的异常
                    allowed = (
                        exc_name in SAFE_BUILTINS or
                        exc_name in SAFE_TYPES or
                        exc_name == "Exception" or
                        exc_name == "BaseException"
                    )
                    if not allowed:
                        raise SecurityError(
                            f"不允许捕获异常: {exc_name} "
                            f"(行 {getattr(node, 'lineno', '?')})"
                        )
    
    def _check_loop(self, node: ast.For | ast.While) -> None:
        """检查循环语句。"""
        # 检查是否有安全措施
        # 注意：这里不做强制限制，但运行时会有超时保护

    def _check_function_or_class(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        """检查函数或类定义。"""
        # 检查函数名是否安全（不以 _ 开头）
        if node.name.startswith('_') and node.name != '__init__':
            raise SecurityError(
                f"不允许定义以 _ 开头的函数或类: {node.name} "
                f"(行 {getattr(node, 'lineno', '?')})"
            )
        
        # 检查函数体是否为空（除 Pass 之外）
        if hasattr(node, 'body') and node.body:
            for item in node.body:
                # 允许 Pass, Return, 表达式等
                if isinstance(item, ast.Pass):
                    continue
                # 不允许嵌套函数定义（防御递归）
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    raise SecurityError(
                        f"不允许嵌套定义函数或类: {item.name} "
                        f"(行 {getattr(item, 'lineno', '?')})"
                    )
