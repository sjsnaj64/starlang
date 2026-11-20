# -*- coding: utf-8 -*-
"""
星语字节码 VM —— 解释器的第三种做法

三种做法，同一门语言：

    starlang.py    ① 树遍历解释器   AST 留在内存，走一步问一次「你是什么节点」
    starlangc.py   ② 编译器          把 AST 写成 Python 源码，之后跟星语无关
    starlangvm.py  ③ 字节码虚拟机    把 AST 压成【一串平铺的指令】，一个 while 跑到底

为什么字节码比树遍历快？
    树遍历：每条语句都要判断 kind == "print" / "assign" / ... 一路 if 下去
    字节码：指令已经是一条条扁平的 (操作, 参数)，while 里查一次表就分派完
    少掉的是「走树」这件事本身。Python / Java / Lua / Ruby 全是这么干的。

为什么 VM 要有一个「栈」？
    表达式天然是嵌套的：  (1 + 2) * 3
    压平之后就是：        CONST 1 / CONST 2 / ADD / CONST 3 / MUL
    中间结果没地方放，就放在栈上。ADD 弹两个压一个，天生配嵌套。

用法：
    python starlangvm.py demo1.star          跑
    python starlangvm.py demo1.star --code   看反汇编（字节码长什么样）
    python starlangvm.py demo1.star --both   反汇编 + 跑

支持的语法跟 starlang.py 一致：变量 / 控制流 / 函数闭包 / 插入 / 字符串 /
钩子 / 宏 / 列表字典 / 逻辑短路 / 尝试出错。
"""
import io
import os
import sys

import starlang
from starlang import (
    Lexer, Parser, Environment, ReturnSignal, 内建, 内建函数,
    钩子表, 织入, 展开宏, 宏定义表, fmt, truthy, MAX_LOOP, MAX_MACRO_DEPTH,
)

sys.setrecursionlimit(10000)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ═══════════════════════════════════════════════════════════
#  一、指令集
# ═══════════════════════════════════════════════════════════
# 一条指令 = (操作, 参数...)。跳转目标是【指令数组的下标】。
#
#   常量 / 变量
#     CONST  值            压一个常量
#     LOAD   名字          读变量，压栈
#     STORE  名字          弹一个，写变量
#     POP                  弹掉栈顶（表达式语句不要值）
#     DUP                  复制栈顶
#     TRUTH                把栈顶转成真/假
#
#   算术 / 比较（都是弹两个压一个）
#     ADD SUB MUL DIV MOD POW NEG NOT
#     EQ NE LT GT LE GE
#
#   控制流
#     JUMP       目标
#     JUMP_IF_FALSE 目标   弹栈，为假就跳
#     JUMP_BACK  目标      往回跳（专门用来数循环圈数，防死循环）
#
#   容器
#     LIST   n             弹 n 个，建列表
#     DICT   n             弹 2n 个，建字典
#     INDEX                弹下标和容器，压元素
#     SETINDEX             弹值、下标、容器，写进去
#
#   函数
#     MAKE_FUNC 名字, 参数元组, 入口地址
#     CALL    n            弹 n 个实参 + 1 个函数值，压返回值
#     RETURN               弹栈顶当返回值，结束这一帧
#
#   杂项
#     PRINT                弹栈顶，打印
#     PRINT_EXPR           弹栈顶，按「= 值」格式回显（顶层裸表达式）
#     SETUP_TRY 目标, 变量名
#     POP_TRY
#     PUSH_SCOPE / POP_SCOPE    出错块要一个子环境
#     REGISTER 时机, 目标, 钩子
#     UNREGISTER 时机, 目标, 钩子

二元算术 = {
    "+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV", "%": "MOD",
    "**": "POW", "==": "EQ", "!=": "NE",
    "<": "LT", ">": "GT", "<=": "LE", ">=": "GE",
}


class VM函数:
    """VM 里的函数值。★ 跟 starlang.Func 长得像，但 body 不是 AST，是入口地址。"""

    def __init__(self, 名字, 参数, 入口, 闭包):
        self.名字 = 名字
        self.参数 = list(参数)
        self.入口 = 入口
        self.闭包 = 闭包

    def __repr__(self):
        return "<函数 " + self.名字 + "(" + ", ".join(self.参数) + ")>"


# ═══════════════════════════════════════════════════════════
#  二、编译器：AST → 字节码
# ═══════════════════════════════════════════════════════════
class 字节码编译器:
    def __init__(self):
        self.代码 = []        # [(操作, 参数...), ...]
        self.行号 = []        # 跟 代码 一一对应，报错时告诉用户第几行
        self.当前行 = 0
        self.宏表 = {}
        self.宏层 = 0
        # ★ 循环栈：每层存 {"顶": 回跳地址, "出口们": [待回填的跳出指令]}。
        #   为什么要栈：嵌套循环里「跳出」只结束最内那一层，
        #   得知道当前最近的一个循环出口在哪。
        self.循环栈 = []
        # ★ 当前正套在几层 尝试/出错 里面。
        #   「跳出」得把穿过的那几层 try 亲手收拾干净（发 POP_TRY），
        #   不然 handler 会一直赖在运行时的「处理栈」上。
        #   真踩过的坑：泄漏的 handler 会把后面完全无关的异常吃掉，
        #   程序看着像在死循环里反复执行出错块。
        self.处理深度 = 0

    # ---------- 发指令 ----------
    def 发(self, *指令):
        self.代码.append(指令)
        self.行号.append(self.当前行)
        return len(self.代码) - 1          # 返回这条指令的下标

    def 这里(self):
        return len(self.代码)

    def 回填(self, 位置, 目标):
        """先占位、后回填 —— 前向跳转只能这么干。"""
        指令 = list(self.代码[位置])
        指令[1] = 目标
        self.代码[位置] = tuple(指令)

    # ---------- 表达式 ----------
    def 编式(self, n):
        k = n[0]

        if k in ("num", "str", "bool"):
            self.发("CONST", n[1])
            return

        if k == "null":
            self.发("CONST", None)
            return

        if k == "ternary":
            # 两个分支只能跳过一个，所以用标准的「跳假 → 真段 → 跳过假段 → 假段」
            self.编式(n[1])
            self.发("TRUTH")
            跳假 = self.发("JUMP_IF_FALSE", None)
            self.编式(n[2])
            跳过 = self.发("JUMP", None)
            self.回填(跳假, self.这里())
            self.编式(n[3])
            self.回填(跳过, self.这里())
            return

        if k == "lambda":
            # ★ VM 比编译器简单得多：指令流是线性的，函数体直接【就地】铺开，
            #   前面加一条 JUMP 跳过去就行 —— 不用担心栈，因为
            #   JUMP 跳过整段，MAKE_FUNC 又只往栈上压一个函数值。
            跳过 = self.发("JUMP", None)
            入口 = self.这里()
            旧栈 = self.循环栈
            旧处理 = self.处理深度
            self.循环栈 = []
            self.处理深度 = 0
            try:
                self.编块(n[2], False)
            finally:
                self.循环栈 = 旧栈
                self.处理深度 = 旧处理
            self.发("CONST", None)
            self.发("RETURN")
            self.回填(跳过, self.这里())
            self.发("MAKE_FUNC", "<匿名>", tuple(n[1]), 入口)
            return

        if k == "var":
            self.发("LOAD", n[1])
            return

        if k == "list":
            for x in n[1]:
                self.编式(x)
            self.发("LIST", len(n[1]))
            return

        if k == "dict":
            for 键, 值 in n[1]:
                self.编式(键)
                self.编式(值)
            self.发("DICT", len(n[1]))
            return

        if k == "index":
            self.编式(n[1])
            self.编式(n[2])
            self.发("INDEX")
            return

        if k == "call":
            self.编式(n[1])                    # 先压函数值，再压实参
            for a in n[2]:
                self.编式(a)
            self.发("CALL", len(n[2]))
            return

        # ---- 逻辑短路：★ 这是真语义，不是优化 ----
        #   且：左边假了，右边【一次都不能跑】（右边可能是个会报错的表达式）
        if k == "且":
            self.编式(n[1])
            self.发("TRUTH")
            self.发("DUP")
            跳 = self.发("JUMP_IF_FALSE", None)     # 弹掉副本，假就跳走
            self.发("POP")
            self.编式(n[2])
            self.发("TRUTH")
            self.回填(跳, self.这里())
            return

        if k == "或":
            self.编式(n[1])
            self.发("TRUTH")
            self.发("DUP")
            跳 = self.发("JUMP_IF_TRUE", None)
            self.发("POP")
            self.编式(n[2])
            self.发("TRUTH")
            self.回填(跳, self.这里())
            return

        if k == "非":
            self.编式(n[1])
            self.发("NOT")
            return

        # ---- 一元 ----
        if len(n) == 2:
            self.编式(n[1])
            self.发("NEG")
            return

        # ---- 二元 ----
        self.编式(n[1])
        self.编式(n[2])
        操作 = 二元算术.get(k)
        if 操作 is None:
            raise RuntimeError("星语VM：不认识的运算符 " + repr(k))
        self.发(操作)

    # ---------- 语句 ----------
    def 编块(self, 块, 回显=False):
        for s in 块[1]:
            self.编句(s, 回显)

    def 跳出错误(self, s, 词):
        """跟 starlang.检查跳出() 一个字都不差 —— 三个实现的报错必须一致"""
        行 = starlang.语句行表.get(id(s))
        开头 = ("[语法错误] 第 " + str(行) + " 行: ") if 行 else "[语法错误] "
        return (开头 + "「" + 词 + "」得写在循环（只要）里面 —— "
                "它自己不知道要跳出哪一层")

    def 编句(self, s, 回显=False):
        行 = starlang.语句行表.get(id(s))
        if 行:
            self.当前行 = 行
        k = s[0]

        if k == "print":
            self.编式(s[1])
            self.发("PRINT")

        elif k == "assign":
            self.编式(s[2])
            self.发("STORE", s[1])

        elif k == "opassign":
            # ★ 先算出 x + e 压栈，再存回 x —— 跟普通赋值共用 STORE
            self.编式((s[2], ("var", s[1]), s[3]))
            self.发("STORE", s[1])

        elif k == "setindex":
            self.编式(s[1])
            self.编式(s[2])
            self.编式(s[3])
            self.发("SETINDEX")

        elif k == "expr":
            self.编式(s[1])
            self.发("PRINT_EXPR" if 回显 else "POP")

        elif k == "block":
            self.编块(s, False)

        elif k == "labeled":
            self.编句(s[2], 回显)

        elif k == "if":
            self.编式(s[1])
            跳假 = self.发("JUMP_IF_FALSE", None)
            self.编块(s[2], False)
            有假 = s[3] is not None
            跳完 = self.发("JUMP", None) if 有假 else None
            self.回填(跳假, self.这里())
            if 有假:
                if s[3][0] == "if":
                    self.编句(s[3], False)          # 否则如果 → 又是一条 if
                else:
                    self.编块(s[3], False)
                self.回填(跳完, self.这里())

        elif k == "while":
            顶 = self.这里()
            self.编式(s[1])
            跳出口 = self.发("JUMP_IF_FALSE", None)
            self.循环栈.append({"顶": 顶, "出口们": [], "深度": self.处理深度})
            try:
                self.编块(s[2], False)
            finally:
                层 = self.循环栈.pop()
            self.发("JUMP_BACK", 顶)
            出口 = self.这里()
            self.回填(跳出口, 出口)
            # ★ 所有「跳出」都补到这里 —— 它们当初发的时候还不知道出口在哪
            for 位置 in 层["出口们"]:
                self.回填(位置, 出口)

        elif k in ("break", "continue"):
            if not self.循环栈:
                raise SyntaxError(self.跳出错误(s, "跳出" if k == "break" else "继续"))
            层 = self.循环栈[-1]
            # ★★ 先把穿过的那几层 try 收拾干净。
            #   只算「循环体内部」的层数 —— 循环自己如果本来就套在某个
            #   尝试里，那个 handler 应该留着（我们只是离开循环，没离开它）。
            for _ in range(self.处理深度 - 层["深度"]):
                self.发("POP_TRY")
            if k == "break":
                位置 = self.发("JUMP", None)
                层["出口们"].append(位置)
            else:
                # ★ 「继续」= 直接回跳。用 JUMP_BACK 而不是 JUMP，
                #   是为了把这一圈也算进死循环熔断的计数里。
                self.发("JUMP_BACK", 层["顶"])

        elif k == "break":
            if not self.循环栈:
                raise SyntaxError(self.跳出错误(s, "跳出"))
            位置 = self.发("JUMP", None)
            self.循环栈[-1]["出口们"].append(位置)

        elif k == "continue":
            if not self.循环栈:
                raise SyntaxError(self.跳出错误(s, "继续"))
            # ★ 「继续」= 直接回跳。用 JUMP_BACK 而不是 JUMP，
            #   是为了把这一圈也算进死循环熔断的计数里。
            self.发("JUMP_BACK", self.循环栈[-1]["顶"])

        elif k == "funcdef":
            # ★ 先跳过函数体，再回头把入口地址打进 MAKE_FUNC
            跳过 = self.发("JUMP", None)
            入口 = self.这里()
            旧栈 = self.循环栈
            旧处理 = self.处理深度
            self.循环栈 = []          # ★ 函数体里不能「跳出」到外面那层循环
            self.处理深度 = 0        # ★ 外面的 尝试 也管不到函数体里面
            try:
                self.编块(s[3], False)
            finally:
                self.循环栈 = 旧栈
                self.处理深度 = 旧处理
            self.发("CONST", None)
            self.发("RETURN")
            self.回填(跳过, self.这里())
            self.发("MAKE_FUNC", s[1], tuple(s[2]), 入口)
            self.发("STORE", s[1])

        elif k == "return":
            if s[1] is None:
                self.发("CONST", None)
            else:
                self.编式(s[1])
            self.发("RETURN")

        elif k == "try":
            self.发("SETUP_TRY", None, s[2])
            跳错 = len(self.代码) - 1
            self.处理深度 += 1
            try:
                self.编块(s[1], False)
            finally:
                self.处理深度 -= 1
            self.发("POP_TRY")
            跳过 = self.发("JUMP", None)
            self.回填(跳错, self.这里())
            # 到这里栈顶就是错误消息（VM 塞进来的）
            self.发("PUSH_SCOPE")
            self.发("STORE", s[2])
            self.编块(s[3], False)
            self.发("POP_SCOPE")
            self.回填(跳过, self.这里())

        elif k in ("register", "unregister"):
            self.发("REGISTER" if k == "register" else "UNREGISTER",
                   s[1], s[2], s[3])

        elif k == "macrodef":
            self.宏表[s[1]] = (list(s[2]), s[3][1])
            self.发("CONST", None)
            self.发("POP")

        elif k == "macro":
            名字 = s[1]
            if 名字 not in self.宏表:
                raise RuntimeError("星语VM：宏「" + 名字 + "」还没定义")
            self.宏层 += 1
            if self.宏层 > MAX_MACRO_DEPTH:
                raise RuntimeError("星语VM：宏套得太深了")
            try:
                展开 = 展开宏(名字, s[2], self.宏表)
            finally:
                self.宏层 -= 1
            for 句 in 展开:
                self.编句(句, 回显)

        elif k == "insert":
            raise RuntimeError("星语VM：「插入」应该在编译前就被织入掉")

        else:
            raise RuntimeError("星语VM：不认识的语句 " + repr(k))

    # ---------- 整程序 ----------
    def 编译(self, 语句们):
        for s in 语句们:
            self.编句(s, 回显=True)      # ★ 顶层裸表达式会回显
        self.发("HALT")
        return self.代码, self.行号


# ═══════════════════════════════════════════════════════════
#  三、VM：一个 while 跑到底
# ═══════════════════════════════════════════════════════════
def _加(a, b):
    if isinstance(a, str) or isinstance(b, str):
        return fmt(a) + fmt(b)
    return a + b


def _除(a, b):
    if b == 0:
        raise ZeroDivisionError("星语：除数不能为 0")
    return a / b


def _余(a, b):
    if b == 0:
        raise ZeroDivisionError("星语：取余的除数不能为 0")
    return a % b


def _正规下标(容器, 下标):
    if isinstance(下标, bool) or not isinstance(下标, int):
        raise RuntimeError("星语：下标得是整数，你给的是 " + fmt(下标))
    位置 = 下标 + len(容器) if 下标 < 0 else 下标
    if 位置 < 0 or 位置 >= len(容器):
        raise IndexError("星语：下标 " + str(下标) + " 越界了（这里只有 "
                         + str(len(容器)) + " 个）")
    return 位置


class VM:
    def __init__(self, 代码, 行号):
        self.代码 = 代码
        self.行号 = 行号
        self.当前行 = 0
        self.圈数 = {}          # 每个 JUMP_BACK 转了多少圈 —— 防死循环

    # ---------- 出错时补上行号 ----------
    def _带着行(self, e):
        消息 = str(e) or type(e).__name__
        if "第 " not in 消息[:12]:
            消息 = "[第 " + str(self.当前行) + " 行] " + 消息
        return 消息

    # ---------- 调用 ----------
    def 带钩子调用(self, f, 实参):
        if isinstance(f, 内建):
            return 内建函数[f.名字](实参)
        if not isinstance(f, VM函数):
            raise RuntimeError("星语：这个东西不是函数，不能加 () 调用它")
        前 = 钩子表.get(f.名字, {}).get("之前", ())
        for h in 前:
            self.直接调(h, 实参)
        值 = self.直接调(f, 实参)
        后 = 钩子表.get(f.名字, {}).get("之后", ())
        for h in 后:
            self.直接调(h, (值,))
        return 值

    def 直接调(self, f, 实参):
        """★ 不看钩子表 —— 钩子自己再被套钩子就会没完没了。"""
        if not isinstance(f, VM函数):
            raise RuntimeError("星语：这个东西不是函数，不能加 () 调用它")
        if len(实参) != len(f.参数):
            raise RuntimeError(
                "星语：函数「" + f.名字 + "」需要 " + str(len(f.参数))
                + " 个参数，你给了 " + str(len(实参)) + " 个")
        环境 = Environment(f.闭包)
        for p, v in zip(f.参数, 实参):
            环境.define(p, v)
        return self.执行(f.入口, 环境)

    # ---------- 主循环 ----------
    def 执行(self, 入口, 环境):
        # ★ 全部提到局部变量：VM 的瓶颈就在「每条指令耍摸几次 self」上，
        #   少一次属性访问就是几十纳秒，一千万条指令就是半秒。
        代码 = self.代码
        行号 = self.行号
        圈数 = {}
        pc = 入口
        栈 = []
        处理栈 = []          # [(错误变量名, 进块时的栈高, handler 地址)]

        while True:
            try:
                while True:
                    指令 = 代码[pc]
                    操作 = 指令[0]
                    pc += 1

                    # ---- 常量 / 变量 ----
                    # ★ LOAD/STORE 是出现频率最高的指令（一个表达式动辄好几条），
                    #   所以把 Environment.get/set 的查找手写进来 ——
                    #   省下一次 Python 方法调用（~100ns）。看起来丑，但值。
                    if 操作 == "CONST":
                        栈.append(指令[1])
                    elif 操作 == "LOAD":
                        名 = 指令[1]
                        e = 环境
                        while e is not None:
                            d = e.vars
                            if 名 in d:
                                栈.append(d[名])
                                break
                            e = e.parent
                        else:
                            raise NameError(starlang.变量未定义消息(名))
                    elif 操作 == "STORE":
                        名 = 指令[1]
                        值 = 栈.pop()
                        e = 环境
                        while e is not None:
                            d = e.vars
                            if 名 in d:
                                d[名] = 值
                                break
                            e = e.parent
                        else:
                            环境.vars[名] = 值
                    elif 操作 == "POP":
                        栈.pop()
                    elif 操作 == "DUP":
                        栈.append(栈[-1])
                    elif 操作 == "TRUTH":
                        栈[-1] = truthy(栈[-1])

                    # ---- 算术 ----
                    elif 操作 == "ADD":
                        b = 栈.pop(); a = 栈.pop()
                        栈.append(_加(a, b))
                    elif 操作 == "SUB":
                        b = 栈.pop(); a = 栈.pop()
                        栈.append(a - b)
                    elif 操作 == "MUL":
                        b = 栈.pop(); a = 栈.pop()
                        栈.append(a * b)
                    elif 操作 == "DIV":
                        b = 栈.pop(); a = 栈.pop()
                        栈.append(_除(a, b))
                    elif 操作 == "MOD":
                        b = 栈.pop(); a = 栈.pop()
                        栈.append(_余(a, b))
                    elif 操作 == "POW":
                        b = 栈.pop(); a = 栈.pop()
                        栈.append(a ** b)
                    elif 操作 == "NEG":
                        栈[-1] = -栈[-1]
                    elif 操作 == "NOT":
                        栈[-1] = not truthy(栈[-1])
                    elif 操作 == "EQ":
                        b = 栈.pop(); a = 栈.pop()
                        栈.append(a == b)
                    elif 操作 == "NE":
                        b = 栈.pop(); a = 栈.pop()
                        栈.append(a != b)
                    elif 操作 == "LT":
                        b = 栈.pop(); a = 栈.pop()
                        栈.append(a < b)
                    elif 操作 == "GT":
                        b = 栈.pop(); a = 栈.pop()
                        栈.append(a > b)
                    elif 操作 == "LE":
                        b = 栈.pop(); a = 栈.pop()
                        栈.append(a <= b)
                    elif 操作 == "GE":
                        b = 栈.pop(); a = 栈.pop()
                        栈.append(a >= b)

                    # ---- 跳转 ----
                    elif 操作 == "JUMP":
                        pc = 指令[1]
                    elif 操作 == "JUMP_IF_FALSE":
                        if not truthy(栈.pop()):
                            pc = 指令[1]
                    elif 操作 == "JUMP_IF_TRUE":
                        if truthy(栈.pop()):
                            pc = 指令[1]
                    elif 操作 == "JUMP_BACK":
                        目标 = 指令[1]
                        圈 = 圈数.get(目标, 0) + 1
                        圈数[目标] = 圈
                        if 圈 > MAX_LOOP:
                            raise RuntimeError(
                                "星语：循环跑了 " + str(MAX_LOOP)
                                + " 次还没停，先夹了（死循环？）")
                        pc = 目标

                    # ---- 容器 ----
                    elif 操作 == "LIST":
                        n = 指令[1]
                        项 = 栈[-n:] if n else []
                        if n:
                            del 栈[-n:]
                        栈.append(list(项))
                    elif 操作 == "DICT":
                        n = 指令[1]
                        对 = []
                        for _ in range(n):
                            v = 栈.pop()
                            k = 栈.pop()
                            对.append((k, v))
                        对.reverse()
                        栈.append(dict(对))
                    elif 操作 == "INDEX":
                        下标 = 栈.pop()
                        容器 = 栈.pop()
                        if isinstance(容器, dict):
                            if 下标 not in 容器:
                                raise RuntimeError(
                                    "星语：字典里没有键 " + starlang._带引号(下标)
                                    + "（用 含有() 先问一下）")
                            栈.append(容器[下标])
                        elif isinstance(容器, (list, str)):
                            栈.append(容器[_正规下标(容器, 下标)])
                        else:
                            raise RuntimeError(
                                "星语：" + fmt(容器) + " 这东西不能用 [] 取下标")
                    elif 操作 == "SETINDEX":
                        值 = 栈.pop()
                        下标 = 栈.pop()
                        容器 = 栈.pop()
                        if isinstance(容器, dict):
                            容器[下标] = 值
                        elif isinstance(容器, list):
                            容器[_正规下标(容器, 下标)] = 值
                        else:
                            raise RuntimeError(
                                "星语：" + fmt(容器) + " 这东西不能用 [] 改内容")
                        栈.append(值)

                    # ---- 函数 ----
                    elif 操作 == "MAKE_FUNC":
                        栈.append(VM函数(指令[1], 指令[2], 指令[3], 环境))
                    elif 操作 == "CALL":
                        n = 指令[1]
                        实参 = 栈[-n:] if n else []
                        if n:
                            del 栈[-n:]
                        函数值 = 栈.pop()
                        栈.append(self.带钩子调用(函数值, list(实参)))
                    elif 操作 == "RETURN":
                        return 栈.pop() if 栈 else None

                    # ---- 杂项 ----
                    elif 操作 == "PRINT":
                        print("   " + fmt(栈.pop()))
                    elif 操作 == "PRINT_EXPR":
                        值 = 栈.pop()
                        if 值 is not None:
                            print("   = " + fmt(值))
                    elif 操作 == "SETUP_TRY":
                        处理栈.append((指令[2], len(栈), 指令[1]))
                    elif 操作 == "POP_TRY":
                        处理栈.pop()
                    elif 操作 == "PUSH_SCOPE":
                        环境 = Environment(环境)
                    elif 操作 == "POP_SCOPE":
                        环境 = 环境.parent
                    elif 操作 == "REGISTER":
                        时机, 目标名, 钩子名 = 指令[1], 指令[2], 指令[3]
                        目标 = 环境.get(目标名)
                        钩子 = 环境.get(钩子名)
                        if not isinstance(目标, VM函数):
                            raise RuntimeError(
                                "星语：「" + 目标名 + "」不是函数，钩子只能盯函数")
                        if not isinstance(钩子, VM函数):
                            raise RuntimeError("星语：钩子「" + 钩子名 + "」不是函数")
                        钩子表.setdefault(目标名, {}).setdefault(时机, []).append(钩子)
                    elif 操作 == "UNREGISTER":
                        时机, 目标名, 钩子名 = 指令[1], 指令[2], 指令[3]
                        列 = 钩子表.get(目标名, {}).get(时机, [])
                        找到了 = False
                        for i, h in enumerate(列):
                            if h.名字 == 钩子名:
                                del 列[i]
                                找到了 = True
                                break
                        if not 找到了:
                            raise RuntimeError(
                                "星语：「" + 目标名 + "」的" + 时机
                                + "没挂着钩子「" + 钩子名 + "」，拔不掉")

                    elif 操作 == "HALT":
                        return None

                    else:
                        raise RuntimeError("星语VM：不认识的指令 " + repr(操作))

            except ReturnSignal:
                raise
            except Exception as e:
                # ★ 行号不再每条指令都存一次，而是出错时才拿 pc 反查 ——
                #   省下每指令一次列表索引 + 一次属性赋值。
                self.当前行 = 行号[pc - 1] if 0 <= pc - 1 < len(行号) else 0
                if not 处理栈:
                    # 跟解释器用同一个「最终说法」，否则三边对不上
                    raise RuntimeError(
                        starlang.最终文案(e, self.当前行)) from None
                变量名, 栈高, 目标 = 处理栈.pop()
                del 栈[栈高:]
                栈.append(starlang.改写报错(self._带着行(e)))
                pc = 目标


# ═══════════════════════════════════════════════════════════
#  四、驱动
# ═══════════════════════════════════════════════════════════
def 反汇编(代码, 行号):
    """把字节码印成人能看的样子"""
    行们 = []
    for i, 指令 in enumerate(代码):
        行们.append("%4d [行 %-3s] %s" % (
            i,
            行号[i] if 行号[i] else "?",
            " ".join(repr(x) if isinstance(x, str) else str(x) for x in 指令),
        ))
    return "\n".join(行们)


def 编译源码(源码, 基准目录=None):
    starlang.语句行表.clear()
    starlang.当前行[0] = 0

    # ★ 切词前先把「载入 "…"」拼进来（跟解释器/编译器同一份实现）
    if "载入" in 源码:
        源码 = starlang.展开载入(源码, 基准目录)

    tokens = Lexer(源码).tokenize()
    语句们 = Parser(tokens).parse_program()

    报告 = 织入(语句们)          # ★ 插入：编译期织进 AST，跟别的实现一样

    # ★ 「跳出/继续」合法性：解释器、编译器、VM 用同一个检查、同一句话
    starlang.检查跳出(语句们)

    器 = 字节码编译器()
    代码, 行号 = 器.编译(语句们)
    return 代码, 行号, 报告


def 跑(源码, 环境=None):
    代码, 行号, 报告 = 编译源码(源码)
    for line in 报告:
        print("   · " + line)
    if 环境 is None:
        环境 = Environment()
        for 名字 in 内建函数:
            if 名字 not in 环境.vars:
                环境.define(名字, 内建(名字))
    钩子表.clear()
    return VM(代码, 行号).执行(0, 环境)


def 跑文件(路径, 只看代码=False, 也跑=False):
    源码 = io.open(路径, encoding="utf-8-sig").read()
    # ★ 跟解释器/编译器一样传基准目录（载入 的相对路径靠它）
    代码, 行号, 报告 = 编译源码(源码, os.path.dirname(os.path.abspath(路径)))

    if 只看代码 or 也跑:
        print("── 字节码 " + "─" * 48)
        print(反汇编(代码, 行号))
        print()

    if 只看代码:
        return None

    for line in 报告:
        print("   · " + line)

    环境 = Environment()
    for 名字 in 内建函数:
        环境.define(名字, 内建(名字))
    钩子表.clear()
    return VM(代码, 行号).执行(0, 环境)


def main():
    参数 = sys.argv[1:]
    if not 参数:
        print(__doc__)
        return

    paths = [a for a in 参数 if not a.startswith("--")]
    if not paths:
        print(__doc__)
        return

    看代码 = "--code" in 参数
    也跑 = "--both" in 参数

    print("── 执行 " + paths[0] + " " + "─" * 40)
    try:
        跑文件(paths[0], 只看代码=看代码, 也跑=也跑)
    except Exception as e:
        print("  ! " + starlang.最终文案(e))


if __name__ == "__main__":
    main()
