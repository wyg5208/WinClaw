"""沙盒执行器。

安全执行通过 AST 验证的 Python 代码。
"""

import ast
import io
import sys
import threading
import traceback
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass
from typing import Any

from src.tools.sandbox.ast_sandbox import ASTSandbox, SecurityError
from src.tools.sandbox.safe_modules import (
    SAFE_BUILTINS,
    SAFE_DATETIME,
    SAFE_JSON,
    SAFE_MATH,
    SAFE_RANDOM,
    SAFE_RE,
    is_path_allowed,
)

# 执行超时（秒）
EXECUTION_TIMEOUT = 30

# 输出大小限制（字符）
MAX_OUTPUT_SIZE = 10000


@dataclass
class ExecutionResult:
    """执行结果。"""
    success: bool
    output: str = ""
    return_value: Any = None
    error: str = ""
    duration_ms: float = 0.0


class SafeExecutor:
    """安全代码执行器。"""
    
    def __init__(
        self,
        timeout: float = EXECUTION_TIMEOUT,
        max_output: int = MAX_OUTPUT_SIZE,
    ):
        """初始化执行器。
        
        Args:
            timeout: 执行超时时间（秒）
            max_output: 最大输出字符数
        """
        self.timeout = timeout
        self.max_output = max_output
        self._ast_sandbox = ASTSandbox(max_complexity=500, max_depth=20)
    
    def execute(self, code: str) -> ExecutionResult:
        """执行代码。
        
        Args:
            code: Python 代码字符串
            
        Returns:
            ExecutionResult 执行结果
        """
        import time
        start_time = time.perf_counter()
        
        # 第一步：AST 安全验证
        try:
            tree = self._ast_sandbox.validate(code)
        except SecurityError as e:
            return ExecutionResult(
                success=False,
                error=f"安全检查失败: {e}",
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )
        except SyntaxError as e:
            return ExecutionResult(
                success=False,
                error=f"语法错误: {e}",
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )
        
        # 第二步：准备执行环境
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        # 获取安全的命名空间
        namespace = self._get_safe_namespace(stdout_capture)
        
        # 第三步：执行代码
        try:
            # 使用线程执行，以便超时控制
            result_container: list[Any] = [None]
            exception_container: list[Exception] = [None]
            
            def run_code():
                try:
                    # 将 AST 转为代码字符串执行
                    code_str = ast.unparse(tree)
                    
                    # 检查是否是单个表达式
                    is_single_expr = (
                        len(tree.body) == 1 and 
                        isinstance(tree.body[0], ast.Expr)
                    )
                    
                    # 检查是否包含 import 语句
                    has_import = any(
                        isinstance(node, (ast.Import, ast.ImportFrom))
                        for node in ast.walk(tree)
                    )
                    
                    if has_import:
                        # 有 import 语句：用 exec 执行
                        exec(code_str, namespace)
                        # 尝试获取最后一个表达式的值（如果有的话）
                        if tree.body and isinstance(tree.body[-1], ast.Expr):
                            last_expr = ast.unparse(tree.body[-1])
                            result_container[0] = eval(last_expr, namespace)
                    elif is_single_expr:
                        # 单个表达式：用 eval 计算结果
                        result_container[0] = eval(code_str, namespace)
                    else:
                        # 多条语句（无 import）：用 exec 执行
                        exec(code_str, namespace)
                        # 检查是否有 __result__
                        if "__result__" in namespace:
                            result_container[0] = namespace.pop("__result__")
                        
                except Exception as e:
                    exception_container[0] = e
            
            # 创建线程执行
            thread = threading.Thread(target=run_code, daemon=True)
            thread.start()
            thread.join(timeout=self.timeout)
            
            # 检查是否超时
            if thread.is_alive():
                return ExecutionResult(
                    success=False,
                    error=f"执行超时（超过 {self.timeout} 秒）",
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                )
            
            # 检查是否有异常
            if exception_container[0]:
                exc = exception_container[0]
                return ExecutionResult(
                    success=False,
                    error=f"{type(exc).__name__}: {exc}",
                    duration_ms=(time.perf_counter() - start_time) * 1000,
                )
            
            # 第四步：收集输出
            stdout_content = stdout_capture.getvalue()
            stderr_content = stderr_capture.getvalue()
            
            # 合并输出
            output_parts = []
            if stdout_content:
                output_parts.append(stdout_content)
            if stderr_content:
                output_parts.append(f"[stderr] {stderr_content}")
            
            # 截断输出
            full_output = "\n".join(output_parts)
            if len(full_output) > self.max_output:
                full_output = (
                    full_output[:self.max_output] 
                    + f"\n... (输出已截断，最大 {self.max_output} 字符)"
                )
            
            return ExecutionResult(
                success=True,
                output=full_output,
                return_value=result_container[0],
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )
            
        except SecurityError as e:
            return ExecutionResult(
                success=False,
                error=f"执行安全错误: {e}",
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
                duration_ms=(time.perf_counter() - start_time) * 1000,
            )
    
    def _get_safe_namespace(self, stdout_capture) -> dict[str, Any]:
        """获取安全的执行命名空间。
        
        Args:
            stdout_capture: 用于捕获print输出的StringIO对象
        """
        # 创建允许的 print 函数（带输出捕获）
        def safe_print(*args, **kwargs):
            """安全的 print 函数。"""
            sep = kwargs.get("sep", " ")
            end = kwargs.get("end", "\n")
            file = kwargs.get("file", None)
            
            if file is None:
                # 写入到捕获的 stdout
                content = sep.join(str(arg) for arg in args) + end
                stdout_capture.write(content)
            else:
                # 否则使用原始 print
                original_print(*args, **kwargs)
        
        # 安全的 open 函数
        def safe_open(file, mode="r", *args, **kwargs):
            """安全的 open 函数，限制路径访问。"""
            file_str = str(file)
            
            # 检查路径是否允许
            if not is_path_allowed(file_str):
                raise PermissionError(f"不允许访问路径: {file_str}")
            
            return original_open(file, mode, *args, **kwargs)
        
        # 保存原始函数
        global original_print, original_open
        original_print = print
        original_open = open
        
        # 构建命名空间
        ns = {
            **{k: v for k, v in SAFE_BUILTINS.items()},
            # 允许 __import__ 用于 import 语句
            "__builtins__": {
                "__import__": __import__,
            },
            "print": safe_print,
            "open": safe_open,
            # 模块
            "math": SAFE_MATH,
            "random": SAFE_RANDOM,
            "datetime": SAFE_DATETIME,
            "json": SAFE_JSON,
            "re": SAFE_RE,
            # 类型
            **{k: v for k, v in {
                "int": int, "float": float, "str": str, "bool": bool,
                "list": list, "dict": dict, "set": set, "tuple": tuple,
                "bytes": bytes, "bytearray": bytearray,
                "type": type, "object": object, "range": range,
                "slice": slice, "complex": complex, "frozenset": frozenset,
            }.items()},
        }
        
        return ns


# 全局执行器实例
_executor: SafeExecutor | None = None


def get_executor() -> SafeExecutor:
    """获取全局执行器实例。"""
    global _executor
    if _executor is None:
        _executor = SafeExecutor()
    return _executor


def execute_code(code: str) -> ExecutionResult:
    """执行 Python 代码的便捷函数。
    
    Args:
        code: Python 代码字符串
        
    Returns:
        ExecutionResult 执行结果
    """
    executor = get_executor()
    return executor.execute(code)
