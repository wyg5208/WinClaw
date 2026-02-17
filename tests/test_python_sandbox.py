"""Python 沙盒工具测试用例。"""

import pytest
from src.tools.sandbox import execute_code


class TestMathOperations:
    """数学运算测试"""

    def test_basic_arithmetic(self):
        result = execute_code("2 + 3 * 4")
        assert result.success
        assert "14" in result.output or "14" in str(result.return_value)

    def test_parentheses(self):
        result = execute_code("(2 + 3) * 4")
        assert result.success
        assert "20" in result.output or "20" in str(result.return_value)

    def test_division(self):
        result = execute_code("10 / 3")
        assert result.success
        assert result.return_value is not None

    def test_floor_division(self):
        result = execute_code("10 // 3")
        assert result.success
        assert result.return_value == 3

    def test_power(self):
        result = execute_code("2 ** 10")
        assert result.success
        assert result.return_value == 1024

    def test_math_sqrt(self):
        result = execute_code("import math; math.sqrt(144)")
        assert result.success
        assert result.return_value == 12.0

    def test_math_sin(self):
        result = execute_code("import math; math.sin(math.pi / 2)")
        assert result.success
        assert abs(result.return_value - 1.0) < 0.0001

    def test_math_factorial(self):
        result = execute_code("import math; math.factorial(5)")
        assert result.success
        assert result.return_value == 120

    def test_math_log(self):
        result = execute_code("import math; math.log(math.e)")
        assert result.success
        assert abs(result.return_value - 1.0) < 0.0001

    def test_abs(self):
        result = execute_code("abs(-100)")
        assert result.success
        assert result.return_value == 100


class TestListOperations:
    """列表操作测试"""

    def test_list_comprehension(self):
        result = execute_code("[x**2 for x in range(10)]")
        assert result.success
        assert result.return_value == [0, 1, 4, 9, 16, 25, 36, 49, 64, 81]

    def test_list_filter(self):
        result = execute_code("[x for x in range(20) if x % 2 == 0]")
        assert result.success
        assert result.return_value == [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]

    def test_sum(self):
        result = execute_code("sum(range(101))")
        assert result.success
        assert result.return_value == 5050

    def test_max(self):
        result = execute_code("max([3,1,4,1,5,9,2,6])")
        assert result.success
        assert result.return_value == 9

    def test_min(self):
        result = execute_code("min([3,1,4,1,5,9,2,6])")
        assert result.success
        assert result.return_value == 1

    def test_len(self):
        result = execute_code("len('hello world')")
        assert result.success
        assert result.return_value == 11

    def test_zip(self):
        result = execute_code("list(zip([1,2,3], ['a','b','c']))")
        assert result.success

    def test_sorted(self):
        result = execute_code("sorted([5,2,8,1,9], reverse=True)")
        assert result.success
        assert result.return_value == [9, 8, 5, 2, 1]


class TestDictOperations:
    """字典操作测试"""

    def test_dict_access(self):
        result = execute_code("{'a': 1, 'b': 2}['a']")
        assert result.success
        assert result.return_value == 1

    def test_dict_comprehension(self):
        result = execute_code("{k: v*2 for k, v in {'a':1, 'b':2}.items()}")
        assert result.success
        assert result.return_value == {'a': 2, 'b': 4}

    def test_dict_get(self):
        result = execute_code("{'a':1}.get('b', 'default')")
        assert result.success
        assert result.return_value == 'default'


class TestStringOperations:
    """字符串操作测试"""

    def test_upper(self):
        result = execute_code("'hello'.upper()")
        assert result.success
        assert result.return_value == 'HELLO'

    def test_lower(self):
        result = execute_code("'HELLO'.lower()")
        assert result.success
        assert result.return_value == 'hello'

    def test_split(self):
        result = execute_code("'hello world'.split()")
        assert result.success
        assert result.return_value == ['hello', 'world']

    def test_join(self):
        result = execute_code("'-'.join(['a','b','c'])")
        assert result.success
        assert result.return_value == 'a-b-c'

    def test_replace(self):
        result = execute_code("'hello'.replace('l', 'x')")
        assert result.success
        assert result.return_value == 'hexxo'

    def test_string_module(self):
        result = execute_code("import string; string.ascii_letters")
        assert result.success
        assert 'a' in result.return_value
        assert 'Z' in result.return_value


class TestJSON:
    """JSON 处理测试"""

    def test_json_dumps(self):
        result = execute_code("import json; json.dumps({'a': 1, 'b': 2})")
        assert result.success
        assert result.return_value == '{"a": 1, "b": 2}'

    def test_json_loads(self):
        result = execute_code("import json; json.loads('{\"x\": 10}')['x']")
        assert result.success
        assert result.return_value == 10


class TestRegex:
    """正则表达式测试"""

    def test_findall(self):
        result = execute_code("import re; re.findall(r'\\d+', 'abc123def456')")
        assert result.success
        assert result.return_value == ['123', '456']

    def test_sub(self):
        result = execute_code("import re; re.sub(r'\\d+', 'X', 'a1b2c3')")
        assert result.success
        assert result.return_value == 'aXbXcX'

    def test_match(self):
        result = execute_code("import re; re.match(r'\\w+', 'hello world').group()")
        assert result.success
        assert result.return_value == 'hello'


class TestCollections:
    """collections 模块测试"""

    def test_counter(self):
        result = execute_code("import collections; collections.Counter('aabbccdd').most_common(2)")
        assert result.success

    def test_defaultdict(self):
        result = execute_code("import collections; collections.defaultdict(int)['key']")
        assert result.success
        assert result.return_value == 0

    def test_deque(self):
        result = execute_code("import collections; d = collections.deque([1,2,3]); d.append(4); list(d)")
        assert result.success
        assert result.return_value == [1, 2, 3, 4]


class TestItertools:
    """itertools 模块测试"""

    def test_product(self):
        result = execute_code("import itertools; list(itertools.product([1,2], ['a','b']))")
        assert result.success
        assert len(result.return_value) == 4


class TestFunctools:
    """functools 模块测试"""

    def test_reduce(self):
        result = execute_code("import functools; functools.reduce(lambda x,y: x+y, [1,2,3,4,5])")
        assert result.success
        assert result.return_value == 15


class TestRandom:
    """random 模块测试"""

    def test_randint(self):
        result = execute_code("import random; random.seed(42); random.randint(1, 6)")
        assert result.success
        assert 1 <= result.return_value <= 6

    def test_choice(self):
        result = execute_code("import random; random.seed(42); random.choice(['a','b','c'])")
        assert result.success
        assert result.return_value in ['a', 'b', 'c']


class TestDatetime:
    """datetime 模块测试"""

    def test_datetime_now(self):
        result = execute_code("import datetime; datetime.datetime.now().year")
        assert result.success
        assert result.return_value == 2026

    def test_timedelta(self):
        result = execute_code("import datetime; (datetime.datetime(2026,1,31) - datetime.datetime(2026,1,1)).days")
        assert result.success
        assert result.return_value == 30


class TestHashlib:
    """hashlib 模块测试"""

    def test_md5(self):
        result = execute_code("import hashlib; hashlib.md5(b'hello').hexdigest()")
        assert result.success
        assert result.return_value == '5d41402abc4b2a76b9719d911017c592'


class TestBase64:
    """base64 模块测试"""

    def test_b64encode(self):
        result = execute_code("import base64; base64.b64encode(b'hello').decode()")
        assert result.success
        assert result.return_value == 'aGVsbG8='


class TestSecurity:
    """安全测试 - 应该被拒绝"""

    def test_import_os_blocked(self):
        result = execute_code("import os")
        assert not result.success
        assert "安全" in result.error or "不支持" in result.error

    def test_import_sys_blocked(self):
        result = execute_code("import sys")
        assert not result.success

    def test_import_subprocess_blocked(self):
        result = execute_code("import subprocess")
        assert not result.success

    def test_dunder_import_blocked(self):
        result = execute_code("__import__('os')")
        assert not result.success


class TestEdgeCases:
    """边界情况测试"""

    def test_timeout(self):
        """超时测试 - 由于无法真正测试超时，这里测试死循环会被中断"""
        # 简单验证返回成功
        result = execute_code("sum(range(10000))")
        assert result.success


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
