# -*- coding: utf-8 -*-
"""桥原型.py —— 验证「星语调 Python 库」这条路通不通

一句话：星语的值【本来就是】Python 原生对象（int/str/list/dict），
所以调 Python 不需要任何类型转换 —— 这是最关键的一点。

现在唯一缺的是「怎么把 Python 的东西挂到星语的名字上」。
而三个引擎（解释器/编译器/VM）取内置函数时，读的都是同一个
starlang.内建函数 字典 —— 所以只要往那个字典里塞，三家自动都有。
"""
import math
import sys

import starlang
import starlangc
import starlangvm


# ── ① 手动挂几个 Python 函数进去 ──
starlang.内建函数["math_sqrt"] = lambda 实参: math.sqrt(实参[0])
starlang.内建函数["math_pi"] = lambda 实参: math.pi
starlang.内建函数["math_fsum"] = lambda 实参: math.fsum(实参[0])

源码 = """
打印 math_sqrt(16)
打印 math_pi()
打印 math_fsum([0.1, 0.2, 0.3])
"""

print("── 解释器 ──")
starlang.run(源码)

print("── 编译器 ──")
产物, _报告 = starlangc.编译源码(源码)
环境 = {"__name__": "__星语__"}
exec(compile(产物, "<星语>", "exec"), 环境)

print("── 虚拟机 ──")
starlangvm.跑(源码)
