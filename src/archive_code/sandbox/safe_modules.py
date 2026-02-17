"""安全模块白名单定义。

定义沙盒中允许导入和使用的模块、函数、常量。
"""

import base64
import collections
import datetime
import functools
import hashlib
import heapq
import itertools
import json
import math
import operator
import random
import re
import string
from typing import Any

# ============== 内置函数白名单 ==============
SAFE_BUILTINS: dict[str, Any] = {
    # 类型转换
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    "bytes": bytes,
    "bytearray": bytearray,
    # 序列操作
    "len": len,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "sorted": sorted,
    "reversed": reversed,
    "sum": sum,
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "pow": pow,
    "divmod": divmod,
    # 字符串操作
    "format": format,
    "chr": chr,
    "ord": ord,
    "ascii": ascii,
    # 类型检查
    "isinstance": isinstance,
    "type": type,
    "issubclass": issubclass,
    "hasattr": hasattr,
    "getattr": getattr,
    "setattr": setattr,
    "delattr": delattr,
    # 其他
    "print": print,
    "help": help,
    "dir": dir,
    "id": id,
    "hash": hash,
    "iter": iter,
    "next": next,
    "callable": callable,
    "repr": repr,
    "complex": complex,
    "slice": slice,
}

# ============== math 模块白名单 ==============
SAFE_MATH: dict[str, Any] = {
    # 常量
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": math.inf,
    "nan": math.nan,
    # 函数
    "sqrt": math.sqrt,
    "pow": math.pow,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
    "asinh": math.asinh,
    "acosh": math.acosh,
    "atanh": math.atanh,
    "log": math.log,
    "log10": math.log10,
    "log1p": math.log1p,
    "log2": math.log2,
    "exp": math.exp,
    "expm1": math.expm1,
    "floor": math.floor,
    "ceil": math.ceil,
    "trunc": math.trunc,
    "fabs": math.fabs,
    "factorial": math.factorial,
    "gcd": math.gcd,
    "lcm": math.lcm,
    "perm": math.perm,
    "comb": math.comb,
    "isclose": math.isclose,
    "isfinite": math.isfinite,
    "isinf": math.isinf,
    "isnan": math.isnan,
    "copysign": math.copysign,
    "fmod": math.fmod,
    "frexp": math.frexp,
    "ldexp": math.ldexp,
    "modf": math.modf,
    "nextafter": math.nextafter,
    "degrees": math.degrees,
    "radians": math.radians,
    "hypot": math.hypot,
}

# ============== random 模块白名单 ==============
SAFE_RANDOM: dict[str, Any] = {
    "random": random.random,
    "randint": random.randint,
    "randrange": random.randrange,
    "choice": random.choice,
    "choices": random.choices,
    "shuffle": random.shuffle,
    "sample": random.sample,
    "uniform": random.uniform,
    "triangular": random.triangular,
    "betavariate": random.betavariate,
    "expovariate": random.expovariate,
    "gammavariate": random.gammavariate,
    "gauss": random.gauss,
    "lognormvariate": random.lognormvariate,
    "normalvariate": random.normalvariate,
    "vonmisesvariate": random.vonmisesvariate,
    "weibullvariate": random.weibullvariate,
    "seed": random.seed,
    "getstate": random.getstate,
    "setstate": random.setstate,
}

# ============== datetime 模块白名单 ==============
SAFE_DATETIME: dict[str, Any] = {
    "datetime": datetime.datetime,
    "date": datetime.date,
    "time": datetime.time,
    "timedelta": datetime.timedelta,
    "tzinfo": datetime.tzinfo,
}

# ============== JSON 模块白名单 ==============
SAFE_JSON: dict[str, Any] = {
    "dumps": json.dumps,
    "loads": json.loads,
    "dump": json.dump,
    "load": json.load,
}

# ============== re 模块白名单（只读） ==============
def _safe_compile(pattern: str, flags: int = 0) -> re.Pattern:
    """安全编译正则表达式。"""
    return re.compile(pattern, flags)

def _safe_match(pattern: str, string: str, flags: int = 0):
    return re.match(pattern, string, flags)

def _safe_search(pattern: str, string: str, flags: int = 0):
    return re.search(pattern, string, flags)

def _safe_findall(pattern: str, string: str, flags: int = 0):
    return re.findall(pattern, string, flags)

def _safe_sub(pattern: str, repl: str, string: str, count: int = 0, flags: int = 0):
    return re.sub(pattern, repl, string, count, flags)

def _safe_split(pattern: str, string: str, maxsplit: int = 0, flags: int = 0):
    return re.split(pattern, string, maxsplit, flags)

SAFE_RE: dict[str, Any] = {
    "compile": _safe_compile,
    "match": _safe_match,
    "search": _safe_search,
    "findall": _safe_findall,
    "finditer": re.finditer,
    "sub": _safe_sub,
    "subn": re.subn,
    "split": _safe_split,
    "escape": re.escape,
    "IGNORECASE": re.IGNORECASE,
    "MULTILINE": re.MULTILINE,
    "DOTALL": re.DOTALL,
    "DEBUG": re.DEBUG,
}

# ============== collections 模块白名单 ==============
SAFE_COLLECTIONS: dict[str, Any] = {
    "Counter": collections.Counter,
    "OrderedDict": collections.OrderedDict,
    "defaultdict": collections.defaultdict,
    "deque": collections.deque,
    "namedtuple": collections.namedtuple,
    "ChainMap": collections.ChainMap,
}

# ============== itertools 模块白名单 ==============
SAFE_ITERTOOLS: dict[str, Any] = {
    "count": itertools.count,
    "cycle": itertools.cycle,
    "repeat": itertools.repeat,
    "islice": itertools.islice,
    "chain": itertools.chain,
    "zip_longest": itertools.zip_longest,
    "product": itertools.product,
    "permutations": itertools.permutations,
    "combinations": itertools.combinations,
    "groupby": itertools.groupby,
    "accumulate": itertools.accumulate,
}

# ============== functools 模块白名单 ==============
SAFE_FUNCTOOLS: dict[str, Any] = {
    "lru_cache": functools.lru_cache,
    "cache": functools.cache,
    "partial": functools.partial,
    "reduce": functools.reduce,
    "wraps": functools.wraps,
}

# ============== operator 模块白名单 ==============
SAFE_OPERATOR: dict[str, Any] = {
    "add": operator.add,
    "sub": operator.sub,
    "mul": operator.mul,
    "truediv": operator.truediv,
    "floordiv": operator.floordiv,
    "mod": operator.mod,
    "pow": operator.pow,
    "neg": operator.neg,
    "pos": operator.pos,
    "abs": operator.abs,
    "eq": operator.eq,
    "ne": operator.ne,
    "lt": operator.lt,
    "le": operator.le,
    "gt": operator.gt,
    "ge": operator.ge,
    "and_": operator.and_,
    "or_": operator.or_,
    "xor": operator.xor,
    "not_": operator.not_,
    "contains": lambda container, item: item in container,
    "getitem": operator.getitem,
    "setitem": operator.setitem,
    "delitem": operator.delitem,
    "itemgetter": operator.itemgetter,
    "attrgetter": operator.attrgetter,
    "truth": operator.truth,
    "is_": operator.is_,
    "is_not": operator.is_not,
    "indexOf": lambda obj, index: obj.index(index) if hasattr(obj, 'index') else None,
    "countOf": lambda obj, item: obj.count(item) if hasattr(obj, 'count') else 0,
}

# ============== string 模块白名单 ==============
SAFE_STRING: dict[str, Any] = {
    "ascii_letters": string.ascii_letters,
    "ascii_lowercase": string.ascii_lowercase,
    "ascii_uppercase": string.ascii_uppercase,
    "digits": string.digits,
    "hexdigits": string.hexdigits,
    "octdigits": string.octdigits,
    "punctuation": string.punctuation,
    "whitespace": string.whitespace,
    " Template": string.Template,
    "Formatter": string.Formatter,
}

# ============== heapq 模块白名单 ==============
SAFE_HEAPQ: dict[str, Any] = {
    "heappush": heapq.heappush,
    "heappop": heapq.heappop,
    "heapify": heapq.heapify,
    "heappushpop": heapq.heappushpop,
    "heapreplace": heapq.heapreplace,
    "nlargest": heapq.nlargest,
    "nsmallest": heapq.nsmallest,
    "merge": heapq.merge,
}

# ============== hashlib 模块白名单 ==============
SAFE_HASHLIB: dict[str, Any] = {
    "md5": hashlib.md5,
    "sha1": hashlib.sha1,
    "sha224": hashlib.sha224,
    "sha256": hashlib.sha256,
    "sha384": hashlib.sha384,
    "sha512": hashlib.sha512,
    "sha3_224": hashlib.sha3_224,
    "sha3_256": hashlib.sha3_256,
    "sha3_384": hashlib.sha3_384,
    "sha3_512": hashlib.sha3_512,
    "blake2b": hashlib.blake2b,
    "blake2s": hashlib.blake2s,
}

# ============== base64 模块白名单 ==============
SAFE_BASE64: dict[str, Any] = {
    "b64encode": base64.b64encode,
    "b64decode": base64.b64decode,
    "urlsafe_b64encode": base64.urlsafe_b64encode,
    "urlsafe_b64decode": base64.urlsafe_b64decode,
    "standard_b64encode": base64.standard_b64encode,
    "standard_b64decode": base64.standard_b64decode,
    "encode": base64.encode,
    "decode": base64.decode,
}

# ============== 集合类型白名单 ==============
SAFE_TYPES: dict[str, Any] = {
    # 基本类型
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "bytes": bytes,
    # 集合类型
    "list": list,
    "dict": dict,
    "set": set,
    "frozenset": frozenset,
    "tuple": tuple,
    # 特殊类型
    "type": type,
    "object": object,
    "range": range,
    "slice": slice,
    "complex": complex,
}

# ============== 异常白名单 ==============
SAFE_EXCEPTIONS: tuple[type, ...] = (
    BaseException,
    Exception,
    StopIteration,
    StopAsyncIteration,
    ArithmeticError,
    FloatingPointError,
    OverflowError,
    ZeroDivisionError,
    AssertionError,
    AttributeError,
    BufferError,
    EOFError,
    ImportError,
    ModuleNotFoundError,
    LookupError,
    IndexError,
    KeyError,
    MemoryError,
    NameError,
    UnboundLocalError,
    OSError,
    PermissionError,
    FileNotFoundError,
    ProcessLookupError,
    RecursionError,
    ReferenceError,
    RuntimeError,
    NotImplementedError,
    SystemError,
    TypeError,
    ValueError,
    UnicodeError,
    UnicodeDecodeError,
    UnicodeEncodeError,
    UnicodeTranslateError,
    Warning,
    DeprecationWarning,
    FutureWarning,
    ImportWarning,
    PendingDeprecationWarning,
    RuntimeWarning,
    SyntaxWarning,
    UserWarning,
    BytesWarning,
)

# ============== 完整命名空间 ==============
def get_safe_namespace() -> dict[str, Any]:
    """获取安全的执行命名空间。"""
    ns = {
        # 副本，避免修改原字典
        **{k: v for k, v in SAFE_BUILTINS.items()},
        # 允许 __import__ 用于 import 语句
        "__builtins__": {
            "__import__": __import__,
        },
        # 允许的模块（作为命名空间）
        "math": SAFE_MATH,
        "random": SAFE_RANDOM,
        "datetime": SAFE_DATETIME,
        "json": SAFE_JSON,
        "re": SAFE_RE,
        "collections": SAFE_COLLECTIONS,
        "itertools": SAFE_ITERTOOLS,
        "functools": SAFE_FUNCTOOLS,
        "operator": SAFE_OPERATOR,
        "string": SAFE_STRING,
        "heapq": SAFE_HEAPQ,
        "hashlib": SAFE_HASHLIB,
        "base64": SAFE_BASE64,
        # 常用类型
        **{k: v for k, v in SAFE_TYPES.items()},
        # 异常
        **{cls.__name__: cls for cls in SAFE_EXCEPTIONS},
    }
    return ns


# ============== 路径限制 ==============
ALLOWED_PATH_PREFIXES: tuple[str, ...] = (
    # 生成目录
    "D:/python_projects/openclaw_demo/winclaw/generated",
    "D:/winclaw/generated",
    "D:/winclaw/temp",
    # 用户文档目录
    "C:/Users/ThinkPad/Documents",
    "C:/Users/ThinkPad/Desktop",
    "C:/Users/ThinkPad/Downloads",
    # 当前工作目录
    "./",
    ".\\",
    "",
    # 允许任意非系统路径（用户目录下的文件）
)

# 禁止访问的系统路径
FORBIDDEN_PATHS: tuple[str, ...] = (
    # Windows 系统关键目录
    "C:/Windows/System32",
    "C:/Windows/SysWOW64",
    "C:/Windows/winSxS",
    "C:/Windows/Security",
    "C:/Program Files",
    "C:/Program Files (x86)",
    "C:/ProgramData/Microsoft",
    # Linux/Mac 系统目录
    "/etc/",
    "/usr/bin/",
    "/usr/sbin/",
    "/bin/",
    "/sbin/",
    "/var/",
    "/sys/",
    "/proc/",
)


def is_path_allowed(path: str) -> bool:
    """检查路径是否允许访问。"""
    import os
    # 规范化路径
    path = os.path.normpath(path).replace("\\", "/")
    path_lower = path.lower()
    
    # 检查是否包含禁止的路径
    for forbidden in FORBIDDEN_PATHS:
        if forbidden.replace("\\", "/").lower() in path_lower:
            return False
    
    # 检查是否以允许的前缀开头
    for prefix in ALLOWED_PATH_PREFIXES:
        prefix = prefix.replace("\\", "/")
        if path.startswith(prefix):
            return True
    
    # 如果不是系统路径，且不在禁止列表中，则允许
    # 主要是用户目录下的文件
    if "c:/users" in path_lower or "d:/" in path_lower:
        return True
    
    return False
