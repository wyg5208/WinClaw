# Python装饰器入门：从基础到实战

## 什么是装饰器？

装饰器是Python中一种强大的语法特性，它允许在不修改原函数代码的情况下，为函数添加额外的功能。装饰器本质上是一个函数，它接受一个函数作为参数，并返回一个新的函数。

## 基本语法

使用@符号来应用装饰器：

```python
@decorator
def my_function():
    pass
```

## 简单示例

```python
def simple_decorator(func):
    def wrapper():
        print("函数执行前")
        func()
        print("函数执行后")
    return wrapper

@simple_decorator
def say_hello():
    print("Hello!")

say_hello()
```

输出：
```
函数执行前
Hello!
函数执行后
```

## 带参数的装饰器

```python
def repeat(n):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for i in range(n):
                result = func(*args, **kwargs)
            return result
        return wrapper
    return decorator

@repeat(3)
def greet(name):
    print(f"Hello, {name}!")

greet("Python")
```

输出：
```
Hello, Python!
Hello, Python!
Hello, Python!
```

## 实际应用场景

1. **日志记录**：记录函数调用时间和参数
2. **性能测试**：测量函数执行时间
3. **权限验证**：检查用户权限
4. **缓存功能**：缓存函数结果
5. **输入验证**：验证函数参数

## 日志记录装饰器示例

```python
import time
import functools

def log_decorator(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        print(f"开始执行 {func.__name__}，参数: args={args}, kwargs={kwargs}")
        result = func(*args, **kwargs)
        end_time = time.time()
        print(f"结束执行 {func.__name__}，耗时: {end_time - start_time:.4f}秒")
        return result
    return wrapper

@log_decorator
def calculate_sum(n):
    return sum(range(n+1))

result = calculate_sum(1000)
print(f"结果: {result}")
```

## 性能测试装饰器示例

```python
import time

def timer_decorator(func):
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        end = time.perf_counter()
        print(f"{func.__name__} 执行时间: {end - start:.6f}秒")
        return result
    return wrapper

@timer_decorator
def slow_function():
    time.sleep(1)
    return "完成"

slow_function()
```

## 总结

装饰器是Python编程中的重要概念，掌握装饰器可以让你的代码更加优雅和可维护。建议多练习实际应用场景，理解装饰器的原理和使用方法。

### 装饰器的优点：
1. **代码复用**：相同的功能可以应用于多个函数
2. **代码简洁**：避免在每个函数中重复相同的代码
3. **关注点分离**：将核心逻辑和附加功能分离
4. **易于维护**：修改装饰器即可影响所有使用它的函数

### 注意事项：
1. 使用`functools.wraps`保持原函数的元信息
2. 注意装饰器的执行顺序（从内到外）
3. 考虑装饰器对性能的影响
4. 合理使用带参数的装饰器

希望这篇入门教程能帮助你理解Python装饰器的基本概念和用法！