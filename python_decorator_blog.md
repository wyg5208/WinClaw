# Python装饰器详解：从入门到精通

## 引言

装饰器（Decorator）是 Python 中一个非常强大且优雅的特性，它允许我们在不修改原函数代码的情况下，为函数添加新的功能。装饰器在 Python 中应用广泛，从简单的日志记录到复杂的权限验证，都能看到它的身影。本文将深入探讨 Python 装饰器的原理、用法和实践技巧。

## 一、装饰器的基本概念

### 1.1 什么是装饰器？

装饰器本质上是一个 Python 函数或类，它可以让其他函数或类在不修改源代码的情况下增加额外的功能。装饰器的返回值也是一个函数/类对象。

### 1.2 装饰器的核心思想

装饰器的核心思想是"装饰"——就像给一个礼物包装上漂亮的包装纸一样，我们给函数"包装"上额外的功能，而不改变函数本身。

## 二、装饰器的语法和使用

### 2.1 基本语法

```python
@decorator
def function():
    pass
```

### 2.2 简单示例

```python
def my_decorator(func):
    def wrapper():
        print("函数执行前")
        func()
        print("函数执行后")
    return wrapper

@my_decorator
def say_hello():
    print("Hello, World!")

say_hello()
# 输出：
# 函数执行前
# Hello, World!
# 函数执行后
```

## 三、带参数的装饰器

### 3.1 装饰带参数的函数

```python
def timer_decorator(func):
    import time
    
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        print(f"函数 {func.__name__} 执行时间: {end_time - start_time:.4f}秒")
        return result
    return wrapper

@timer_decorator
def calculate_sum(n):
    return sum(range(n))

print(calculate_sum(1000000))
```

### 3.2 带参数的装饰器

```python
def repeat(times):
    """重复执行指定次数的装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            results = []
            for i in range(times):
                print(f"第 {i+1} 次执行")
                result = func(*args, **kwargs)
                results.append(result)
            return results
        return wrapper
    return decorator

@repeat(times=3)
def greet(name):
    return f"Hello, {name}!"

print(greet("Python"))
```

## 四、类装饰器

### 4.1 使用类作为装饰器

```python
class LoggerDecorator:
    def __init__(self, func):
        self.func = func
    
    def __call__(self, *args, **kwargs):
        print(f"开始执行函数: {self.func.__name__}")
        print(f"参数: args={args}, kwargs={kwargs}")
        result = self.func(*args, **kwargs)
        print(f"函数执行完成，返回值: {result}")
        return result

@LoggerDecorator
def multiply(a, b):
    return a * b

print(multiply(5, 6))
```

### 4.2 带参数的类装饰器

```python
class RetryDecorator:
    def __init__(self, max_retries=3):
        self.max_retries = max_retries
    
    def __call__(self, func):
        def wrapper(*args, **kwargs):
            for attempt in range(self.max_retries):
                try:
                    print(f"第 {attempt + 1} 次尝试")
                    return func(*args, **kwargs)
                except Exception as e:
                    print(f"尝试失败: {e}")
                    if attempt == self.max_retries - 1:
                        raise
            return None
        return wrapper

@RetryDecorator(max_retries=3)
def risky_operation():
    import random
    if random.random() < 0.7:
        raise ValueError("随机失败")
    return "操作成功"

print(risky_operation())
```

## 五、装饰器的常见应用场景

### 5.1 日志记录

```python
def log_decorator(func):
    import logging
    logging.basicConfig(level=logging.INFO)
    
    def wrapper(*args, **kwargs):
        logging.info(f"调用函数 {func.__name__}，参数: {args}, {kwargs}")
        result = func(*args, **kwargs)
        logging.info(f"函数 {func.__name__} 执行完成，返回值: {result}")
        return result
    return wrapper
```

### 5.2 性能监控

```python
def profile_decorator(func):
    import cProfile
    import pstats
    import io
    
    def wrapper(*args, **kwargs):
        pr = cProfile.Profile()
        pr.enable()
        result = func(*args, **kwargs)
        pr.disable()
        
        s = io.StringIO()
        ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
        ps.print_stats()
        print(s.getvalue())
        
        return result
    return wrapper
```

### 5.3 权限验证

```python
def require_login(role="user"):
    def decorator(func):
        def wrapper(user, *args, **kwargs):
            if not user.get("is_authenticated", False):
                raise PermissionError("用户未登录")
            
            if role == "admin" and not user.get("is_admin", False):
                raise PermissionError("需要管理员权限")
            
            return func(user, *args, **kwargs)
        return wrapper
    return decorator

@require_login(role="admin")
def delete_user(user, user_id):
    return f"用户 {user_id} 已被删除"

user = {"is_authenticated": True, "is_admin": True}
print(delete_user(user, 123))
```

### 5.4 缓存装饰器

```python
def cache_decorator(func):
    cache = {}
    
    def wrapper(*args, **kwargs):
        # 创建缓存键
        key = (args, tuple(sorted(kwargs.items())))
        
        if key in cache:
            print(f"从缓存中获取结果")
            return cache[key]
        
        result = func(*args, **kwargs)
        cache[key] = result
        print(f"计算结果并缓存")
        return result
    return wrapper

@cache_decorator
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

print(fibonacci(10))
```

## 六、装饰器的高级技巧

### 6.1 多个装饰器的使用

```python
def decorator1(func):
    def wrapper():
        print("装饰器1 - 前")
        func()
        print("装饰器1 - 后")
    return wrapper

def decorator2(func):
    def wrapper():
        print("装饰器2 - 前")
        func()
        print("装饰器2 - 后")
    return wrapper

@decorator1
@decorator2
def my_function():
    print("原始函数")

my_function()
# 输出：
# 装饰器1 - 前
# 装饰器2 - 前
# 原始函数
# 装饰器2 - 后
# 装饰器1 - 后
```

### 6.2 保留函数元信息

```python
from functools import wraps

def preserve_metadata_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        """包装函数的文档字符串"""
        return func(*args, **kwargs)
    return wrapper

@preserve_metadata_decorator
def example_function():
    """原始函数的文档字符串"""
    pass

print(example_function.__name__)  # 输出: example_function
print(example_function.__doc__)   # 输出: 原始函数的文档字符串
```

## 七、内置装饰器

### 7.1 @staticmethod 和 @classmethod

```python
class MyClass:
    @staticmethod
    def static_method():
        print("这是一个静态方法")
    
    @classmethod
    def class_method(cls):
        print(f"这是一个类方法，类名: {cls.__name__}")
    
    def instance_method(self):
        print("这是一个实例方法")

MyClass.static_method()
MyClass.class_method()
```

### 7.2 @property

```python
class Person:
    def __init__(self, first_name, last_name):
        self._first_name = first_name
        self._last_name = last_name
    
    @property
    def full_name(self):
        return f"{self._first_name} {self._last_name}"
    
    @full_name.setter
    def full_name(self, name):
        first, last = name.split(" ")
        self._first_name = first
        self._last_name = last

person = Person("张", "三")
print(person.full_name)  # 输出: 张 三
person.full_name = "李 四"
print(person._first_name)  # 输出: 李
```

## 八、装饰器的最佳实践

### 8.1 保持装饰器简单

装饰器应该专注于单一职责，避免在一个装饰器中实现太多功能。

### 8.2 使用 functools.wraps

始终使用 `@functools.wraps` 来保留原始函数的元信息。

### 8.3 考虑性能影响

装饰器会增加函数调用的开销，在性能敏感的场景中需要谨慎使用。

### 8.4 文档化装饰器

为装饰器编写清晰的文档，说明其功能、参数和使用方法。

## 九、实战案例：Web API 装饰器

```python
from functools import wraps
import json
from flask import Flask, request, jsonify

app = Flask(__name__)

def validate_json(*expected_args):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            json_data = request.get_json()
            
            for expected_arg in expected_args:
                if expected_arg not in json_data:
                    return jsonify({
                        "error": f"缺少必要参数: {expected_arg}"
                    }), 400
            
            return func(*args, **kwargs)
        return wrapper
    return decorator

@app.route('/api/user', methods=['POST'])
@validate_json('username', 'email', 'password')
def create_user():
    data = request.get_json()
    # 处理用户创建逻辑
    return jsonify({"message": "用户创建成功", "data": data}), 201

if __name__ == '__main__':
    app.run(debug=True)
```

## 十、总结

Python 装饰器是一个强大而灵活的工具，它体现了 Python 的"优雅"和"简洁"的设计哲学。通过装饰器，我们可以：

1. **增强函数功能**：在不修改原函数代码的情况下添加新功能
2. **代码复用**：将通用功能封装成装饰器，多处使用
3. **提高可读性**：通过装饰器语法清晰地表达函数的行为
4. **实现AOP**：面向切面编程，分离关注点

掌握装饰器不仅能让你的代码更加优雅，还能让你更好地理解 Python 的函数式编程特性。希望本文能帮助你深入理解并熟练使用 Python 装饰器！

---

**作者**：[您的名字]
**发布时间**：2026年2月15日
**标签**：Python, 装饰器, 编程技巧, 函数式编程, 高级特性