# -*- coding: utf-8 -*-
"""
星语编译器： 星语源码  →  Python 源码  →  跑

和 starlang.py 的根本区别
────────────────────────────────────────────────────────
  解释器：AST 留在那儿，走一步问一次「你是什么节点」—— 一万次就是一万次分派
  编译器：把树「写」成另一棵树（Python 的树），之后跟星语再无关系

  解释器：变量存在一层层字典里        _取(env, 'x')  ← 每次都要顺着链找
  编译器：变量直接变成 Python 变量       x             ← 就是 Python 自己的局部变量

  解释器：宏在【运行时】才展开
  编译器：宏在【编译时】就展开完，生成出来的代码里根本没有宏

用法
────────────────────────────────────────────────────────
  python starlangc.py demo1.star            编译并运行
  python starlangc.py demo1.star --show     只看生成的 Python 代码
  python starlangc.py demo1.star --out x.py 保存成文件
"""

import sys
import io
import keyword
import os
import starlang
from starlang import Lexer, Parser, 织入


# ═══════════════════════════════════════════════════════════
# ① 作用域分析
# ═══════════════════════════════════════════════════════════
# 这是编译器必须干、解释器完全不用干的事。
#
# 星语的变量规则（Environment.set）：
#     自己和祖先里哪儿有就改哪儿；四处都没有，才建在自己这儿
#
# Python 的规则：
#     函数里被赋值的名字 = 局部变量；想改外层的要显式写 nonlocal
#
# 要让两者对上，就得在【编译时】把每个名字算清楚：
#
#     「这个名字在本层被赋值，而所有祖先都没有」→ 本层局部 ✅ Python 默认就这样
#     「这个名字在本层被赋值，某个祖先有」      → 必须写 nonlocal
#
# 算不出来就只能靠字典环境了 —— 那样虽然对，但一点没快起来。


class 作用域:
    def __init__(self, 名, 父=None):
        self.名 = 名
        self.父 = 父
        self.参数 = []          # 函数参数
        self.定义 = set()        # funcdef / try 的错误名 —— 这些是「写本层」
        self.赋值 = set()        # x = 值
        self.子 = []
        self.本层 = set()        # 算出来的：真正属于本层的名字
        self.外层 = {}           # 名字 -> "nonlocal"

    def 祖上有(self, 名字):
        p = self.父
        while p is not None:
            if 名字 in p.本层:
                return True
            p = p.父
        return False

    def __repr__(self):
        return "<作用域 " + self.名 + ">"


def 扫描(域, 语句表):
    for s in 语句表:
        扫描语句(域, s)


def 扫描语句(域, s):
    if not isinstance(s, tuple):
        return
    k = s[0]

    if k == "funcdef":
        名, 参数, 体 = s[1], s[2], s[3]
        子 = 作用域(名, 域)
        子.参数 = list(参数)
        域.定义.add(名)          # ★ 定义函数也是「写本层」，跟 define() 一致
        域.子.append(子)
        扫描(子, 体[1])

    elif k == "assign":
        域.赋值.add(s[1])

    elif k == "opassign":
        # ★ x += 1 也是「写」，必须跟 assign 一样记账。
        #   漏了这条，函数里的 `计数 += 1` 会被 Python 当成局部变量
        #   （因为生成了「计数 = 计数 + 1」），然后报 UnboundLocalError ——
        #   而解释器那边是正常的，差分测试立刻抓包。
        域.赋值.add(s[1])

    elif k == "block":
        扫描(域, s[1])

    elif k == "if":
        扫描(域, s[2][1])
        if s[3] is not None:
            扫描语句(域, s[3])       # 可能是 block，也可能是另一个 if

    elif k == "while":
        扫描(域, s[2][1])

    elif k == "for":
        扫描(域, s[3][1])

    elif k == "try":
        域.定义.add(s[2])        # 出错块里的那个变量名
        扫描(域, s[1][1])
        扫描(域, s[3][1])

    elif k == "labeled":
        扫描语句(域, s[2])

    elif k == "macro":
        pass                     # 宏在编译期展开，展开后的语句会再被扫一遍

    elif k == "macrodef":
        扫描(域, s[3][1])        # 宏体里的赋值不算到调用者头上，但先扫着占位


def 定名(域):
    """自顶向下算：本层有哪些名字、哪些名字改的是外层的。"""
    for n in 域.赋值:
        # ★★ 本层已经有这个名字（参数 / 函数定义 / 出错变量）→ 改的就是本层！
        #    漏了这一句就会生成 `def f(x): nonlocal x` —— 那是 Python 语法错误。
        #    星语的 set() 是从里往外找「第一层有的」，所以本层有就轮不到外层。
        if n in 域.参数 or n in 域.定义:
            continue
        if 域.祖上有(n):
            域.外层[n] = "nonlocal"
    域.本层 = set(域.参数) | set(域.定义) | (set(域.赋值) - set(域.外层))
    for 子 in 域.子:
        定名(子)


# ═══════════════════════════════════════════════════════════
# ② 名字映射
# ═══════════════════════════════════════════════════════════
# 中文名 Python 3 直接用，生成出来的代码好看。
# ASCII 名一律加 _v_ 前缀 —— 因为 len / range / type / str 这些
# 星语内建恰好跟 Python 内建同名，直接用会互相踩。

def py名(名字):
    # ★ 宏卫生化生成的 gensym 名长这样： 序#1
    #   '#' 在星语里是注释符（用户写不进名字），拿来当标记最安全；
    #   但 Python 里 '#' 也是注释符，必须转成合法标识符才能生成代码。
    if "#" in 名字:
        名字 = 名字.replace("#", "_g_")
    if 名字.isascii():
        return "_v_" + 名字
    if 名字.startswith("_"):
        return "_v0" + 名字          # 别撞上运行时的那堆 _xxx
    return 名字


# ═══════════════════════════════════════════════════════════
# ③ 代码生成
# ═══════════════════════════════════════════════════════════

MAX_LOOP = 500000
MAX_MACRO_DEPTH = 200


class 编译器:
    def __init__(self):
        self.行 = []
        self.深 = 0
        self.当前 = None          # 当前作用域
        self.计数 = 0             # 生成函数实现名的计数器
        self.宏表 = {}            # 名字 -> (参数名们, 体语句列表)
        self.宏层 = 0
        self.循环深度 = 0         # ★ 当前套了几层循环（「跳出/继续」合法性靠它）
        self.待补 = []           # ★ 匿名函数提升出来的定义，等这条语句编完插到它前面
        # ★ 产物行号 → 星语行号。运行时看 traceback 就能反推回源文件的第几行，
        #   不用在每条语句前插一句 _当前行 = N（那样代码变肿、还多一次赋值）。
        self.行映射 = {}

    # ---------- 小工具 ----------
    def 写(self, 文字=""):
        self.行.append(("    " * self.深 + 文字) if 文字 else "")

    def 新名(self, 前缀):
        self.计数 += 1
        return "_" + 前缀 + str(self.计数)

    # ═════════════ 表达式 ═════════════
    def 式(self, n):
        k = n[0]

        # ---- 叶子 ----
        if k == "num":
            return repr(n[1])
        if k == "str":
            return repr(n[1])
        if k == "bool":
            return "True" if n[1] else "False"
        if k == "null":
            return "None"
        if k == "已值":
            # ★ 内部专用：n[1] 存的是【已经算好的 Python 变量名】
            return n[1]
        if k == "ternary":
            # Python 的三元就是 a if cond else b —— 直接对上了，不用搞跳转
            return ("(" + self.式(n[2]) + " if _真(" + self.式(n[1])
                    + ") else " + self.式(n[3]) + ")")
        if k == "lambda":
            # ★ Python 的表达式位置不能写 def，所以匿名函数得「提升」：
            #   当场生成一个具名实现 + 一个 _函数 包装，然后把包装名当值用。
            #
            #   为什么不直接用 Python 的 lambda？因为星语的函数体是【语句块】，
            #   Python 的 lambda 只能装一个表达式 —— 装不下 返回/如果/只要。
            实现 = self.新名("匿实现")
            包名 = self.新名("匿")
            默认们 = n[3] if len(n) > 3 else [None] * len(n[1])
            形参件 = []
            for i, p in enumerate(n[1]):
                形参件.append(py名(p) if 默认们[i] is None
                              else py名(p) + "=_缺省")
            开头 = len(self.行)
            self.写("def " + 实现 + "(" + ", ".join(形参件) + "):")
            旧循环 = self.循环深度
            self.循环深度 = 0          # 匿名函数体里不能 跳出 到外面
            self.深 += 1
            for i, p in enumerate(n[1]):
                if 默认们[i] is None:
                    continue
                self.写("if " + py名(p) + " is _缺省:")
                self.深 += 1
                self.写(py名(p) + " = " + self.式(默认们[i]))
                self.深 -= 1
            self.语句表(n[2][1])
            self.深 -= 1
            self.循环深度 = 旧循环
            # ★ 包装成 _函数，这样 _调() 认得它是个星语函数（带名字显示）
            最少 = sum(1 for d in 默认们 if d is None)
            self.写(包名 + " = _函数(\"<匿名>\", " + repr(list(n[1]))
                    + ", " + 实现 + ", " + str(最少) + ")")
            段 = self.行[开头:]
            del self.行[开头:]
            # 先攒着 —— 后面可能还有内层匿名函数，让它们先排前面
            self.待补.append(段)
            # 名字已经是合法的 ASCII 标识符（_匿1 这种），不能再过 py名()
            return 包名
        if k == "var":
            return py名(n[1])

        # ---- 集合 ----
        if k == "list":
            return "[" + ", ".join(self.式(x) for x in n[1]) + "]"
        if k == "dict":
            return ("{" + ", ".join(self.式(a) + ": " + self.式(b) for a, b in n[1]) + "}")
        if k == "index":
            return "_下标(" + self.式(n[1]) + ", " + self.式(n[2]) + ")"

        # ---- 调用 ----
        if k == "call":
            实 = [self.式(a) for a in n[2]]
            尾巴 = "," if len(实) == 1 else ""      # 一个参数时要有逗号才是元组
            return "_调(" + self.式(n[1]) + ", (" + ", ".join(实) + 尾巴 + "))"

        # ---- 逻辑：★ 星语返回的是【布尔】，所以直接 or/and 就行 ----
        #     解释器那边要手写 "左边假就不跑右边"，Python 的 or/and 天生就短路
        if k == "或":
            return "(_真(" + self.式(n[1]) + ") or _真(" + self.式(n[2]) + "))"
        if k == "且":
            return "(_真(" + self.式(n[1]) + ") and _真(" + self.式(n[2]) + "))"
        if k == "非":
            return "(not _真(" + self.式(n[1]) + "))"

        # ---- 一元 ----
        if len(n) == 2:
            return "(" + k + self.式(n[1]) + ")"

        # ---- 二元 ----
        左 = self.式(n[1])
        右 = self.式(n[2])
        if k == "+":
            return "_加(" + 左 + ", " + 右 + ")"      # 一边是字符串就拼接，得走函数
        if k == "/":
            return "_除(" + 左 + ", " + 右 + ")"
        if k == "%":
            return "_余(" + 左 + ", " + 右 + ")"
        if k == "**":
            return "(" + 左 + " ** " + 右 + ")"
        if k in ("-", "*", "<", ">", "<=", ">=", "==", "!="):
            return "(" + 左 + " " + k + " " + 右 + ")"

        raise RuntimeError("星语编译器：不认识的表达式节点 " + repr(k))

    # ═════════════ 语句 ═════════════
    # ★ 回显（echo）是个真语义：解释器只在【顶层】打印光秃秃表达式的值
    #   （run_program(..., echo=True)），块里不打印。编译器得一模一样。
    def 语句表(self, 语句们, 回显=False):
        开头 = len(self.行)
        for s in 语句们:
            self.语句(s, 回显)
        if len(self.行) == 开头:
            self.写("pass")           # 空块必须有 pass

    def 语句(self, s, 回显=False):
        """★ 外面这层只干一件事：把这条语句生成的每一行都记到星语行号上。

        用 setdefault 是有意的：子语句先登记了自己的行号，外层再包一层时
        就不会把它盖掉 —— 越深越准。
        """
        星语行 = starlang.语句行表.get(id(s), 0)
        开头 = len(self.行)
        旧待补 = self.待补
        self.待补 = []
        self._语句(s, 回显)
        # ★ 匿名函数提升出来的 def 必须排在本条语句【之前】——
        #   不然表达式里用到它的时候，这个名字还没定义。
        提升 = self.待补
        self.待补 = 旧待补
        if 提升:
            self.行[开头:开头] = [行 for 段 in 提升 for 行 in 段]
        if 星语行:
            for i in range(开头, len(self.行)):
                self.行映射.setdefault(i + 1, 星语行)

    def 跳出错误(self, s, 词):
        """跟 starlang.检查跳出() 一个字都不差 —— 三个实现的报错必须一致"""
        行 = starlang.语句行表.get(id(s))
        开头 = ("[语法错误] 第 " + str(行) + " 行: ") if 行 else "[语法错误] "
        return (开头 + "「" + 词 + "」得写在循环（只要）里面 —— "
                "它自己不知道要跳出哪一层")

    def _语句(self, s, 回显=False):
        k = s[0]

        if k == "print":
            self.写("print('   ' + _fmt(" + self.式(s[1]) + "))")

        elif k == "assign":
            self.写(py名(s[1]) + " = " + self.式(s[2]))

        elif k == "opassign":
            # ★ 老规矩：展开成普通赋值，复用 式() 里那套二元逻辑（含 _加/_除）
            self.写(py名(s[1]) + " = " + self.式((s[2], ("var", s[1]), s[3])))

        elif k == "setindex":
            self.写("_设下标(" + self.式(s[1]) + ", " + self.式(s[2])
                    + ", " + self.式(s[3]) + ")")

        elif k == "setindexop":
            # ★ 容器和下标各求值【一次】，存到临时变量里再用。
            #   不存的话表达式会被写两遍，有副作用时行为全乱。
            容 = self.新名("容")
            位 = self.新名("位")
            旧 = self.新名("旧")
            self.写(容 + " = " + self.式(s[1]))
            self.写(位 + " = " + self.式(s[2]))
            self.写(旧 + " = _下标(" + 容 + ", " + 位 + ")")
            self.写("_设下标(" + 容 + ", " + 位 + ", "
                    + self.式((s[3], ("已值", 旧), s[4])) + ")")

        elif k == "expr":
            # ★ 解释器是 if result is not None 才打印 —— 所以函数没返回值（None）
            #   时不该冒出一个「= 空」。这一行是很容易漏的语义细节。
            if 回显:
                值 = self.新名("值")
                self.写(值 + " = " + self.式(s[1]))
                self.写("if " + 值 + " is not None:")
                self.写("    print('   = ' + _fmt(" + 值 + "))")
            else:
                self.写(self.式(s[1]))

        elif k == "block":
            # ★ 块里跑 run_program(..., echo=False)，所以永不回显
            self.语句表(s[1], False)

        elif k == "labeled":
            内 = s[2]
            if 内[0] in ("while", "for"):
                # ★ 带标号的循环：「跳出 这个标号」会抛 _跳出标号，在这里接住
                错 = self.新名("标号错")
                self.写("try:")
                self.深 += 1
                self.语句(s[2])
                self.深 -= 1
                self.写("except _跳出标号 as " + 错 + ":")
                self.深 += 1
                self.写("if " + 错 + ".标签 != " + repr(s[1]) + ":")
                self.深 += 1
                self.写("raise")          # 不是找我的，继续往外冒
                self.深 -= 1
                self.深 -= 1
            else:
                self.语句(s[2], 回显)

        elif k == "insert":
            raise RuntimeError("星语编译器：「插入」应该在编译前就被织入掉")

        elif k == "if":
            self.写("if _真(" + self.式(s[1]) + "):")
            self.深 += 1
            self.语句表(s[2][1])
            self.深 -= 1
            if s[3] is not None:
                self.写("else:")
                self.深 += 1
                if s[3][0] == "if":
                    self.语句(s[3])       # 否则如果 → else: 里再套 if
                else:
                    self.语句表(s[3][1])
                self.深 -= 1

        elif k == "while":
            圈 = self.新名("圈")
            self.写(圈 + " = 0")
            self.写("while _真(" + self.式(s[1]) + "):")
            self.深 += 1
            # ★ 圈数累加必须放在循环体【最前面】，不能放后面。
            #   因为「继续」会跳过后面的语句 —— 计数器在后面的话，
            #   一个满是 continue 的循环永远涨不了数，死循环熔断丝就成了摆设。
            self.写(圈 + " = " + 圈 + " + 1")
            self.写("if " + 圈 + " > " + str(MAX_LOOP) + ":")
            self.深 += 1
            self.写("raise RuntimeError('星语：循环跑了 " + str(MAX_LOOP)
                    + " 次还没停，先夹了（死循环？）')")
            self.深 -= 1
            self.循环深度 += 1
            try:
                self.语句表(s[2][1])
            finally:
                self.循环深度 -= 1
            self.深 -= 1

        elif k == "for":
            # ★ 遍历 跟 Python 的 for 语义直接对上，几乎不用费心：
            #   快照、字典给键、文本给字 —— 靠前言里的 _循环速() 一次搞定。
            self.写("for " + py名(s[1]) + " in _循环速(" + self.式(s[2]) + "):")
            self.深 += 1
            self.循环深度 += 1
            try:
                self.语句表(s[3][1])
            finally:
                self.循环深度 -= 1
            self.深 -= 1

        elif k in ("break", "continue"):
            if self.循环深度 == 0:
                raise SyntaxError(self.跳出错误(s, "跳出" if k == "break" else "继续"))
            # ★ Step 22：带标号的跳出
            标签 = s[1] if len(s) > 1 else None
            if k == "break" and 标签 is not None:
                self.写("raise _跳出标号(" + repr(标签) + ")")
            else:
                self.写("break" if k == "break" else "continue")

        elif k == "funcdef":
            self.编译函数定义(s)

        elif k == "return":
            if s[1] is None:
                self.写("return None")
            else:
                self.写("return " + self.式(s[1]))

        elif k == "try":
            self.写("try:")
            self.深 += 1
            self.语句表(s[1][1])
            self.深 -= 1
            # ★ Step 22：带标号的跳出不能当成「出错」吃掉 —— 必须原样往外冒。
            #   跟解释器里 BreakSignal 单独重抛是一个道理。
            self.写("except _跳出标号:")
            self.深 += 1
            self.写("raise")
            self.深 -= 1
            错 = self.新名("错")
            self.写("except Exception as " + 错 + ":")
            self.深 += 1
            self.写(py名(s[2]) + " = _星语错误文本(" + 错 + ")")
            self.语句表(s[3][1])
            self.深 -= 1

        elif k == "register":
            时机, 目标, 钩子 = s[1], s[2], s[3]
            self.写("_注册(" + repr(时机) + ", " + repr(目标) + ", "
                    + py名(目标) + ", " + py名(钩子) + ")")

        elif k == "unregister":
            时机, 目标, 钩子 = s[1], s[2], s[3]
            self.写("_拔掉(" + repr(时机) + ", " + repr(目标) + ", "
                    + py名(目标) + ", " + py名(钩子) + ")")

        # ---- 宏：★ 编译期就展开掉，生成出来的代码里根本见不到宏 ----
        elif k == "macrodef":
            self.宏表[s[1]] = (list(s[2]), s[3][1])
            self.写("# 宏「" + s[1] + "(" + ", ".join(s[2]) + ")」已在编译期登记，不生成代码")

        elif k == "macro":
            名字 = s[1]
            if 名字 not in self.宏表:
                raise RuntimeError("星语编译器：宏「" + 名字 + "」还没定义")
            self.宏层 += 1
            if self.宏层 > MAX_MACRO_DEPTH:
                raise RuntimeError("星语编译器：宏套得太深了（超过 "
                                   + str(MAX_MACRO_DEPTH) + " 层）")
            try:
                # ★ 卫生化（宏体局部变量改名）也在里面 —— 跟解释器同一份代码，
                #   这样「编译器版」和「解释器版」的宏行为不可能分叉。
                #   定义表传自己的：编译期展开，不能跟运行时那张表混。
                展开 = starlang.展开宏(名字, s[2], self.宏表)
            finally:
                self.宏层 -= 1
            self.写("# ↓ 下面是宏「" + 名字 + "」展开出来的（局部名已卫生化）")
            self.语句表(展开, 回显)

        else:
            raise RuntimeError("星语编译器：不认识的语句节点 " + repr(k))

    # ---------- 函数定义 ----------
    def 编译函数定义(self, s, 匿名名=None):
        名, 参数, 体 = s[1], s[2], s[3]
        默认们 = s[4] if len(s) > 4 else [None] * len(参数)
        实现 = self.新名("实现")
        外层深 = self.深          # ← 这条语句本身所在的层

        # ★ 星语的函数是「值」，要能被传来传去、被打印成 <函数 f(x)>，
        #   所以生成两层：一层是真 Python 函数（闭包照旧），一层是包壳。
        #
        # ★★ 默认值为什么不用 Python 自己的 `def f(a=表达式)`？
        #   Python 在【定义时】算一次就冻住了 —— 著名的 `def f(x=[])` 坑。
        #   星语的语义是【每次调用重算】。所以形参默认值先给哨兵，
        #   进函数体再判哨兵、现算 —— 这样两边语义才能对齐。
        形参件 = []
        for i, p in enumerate(参数):
            形参件.append(py名(p) if 默认们[i] is None
                          else py名(p) + "=_缺省")
        self.写("def " + 实现 + "(" + ", ".join(形参件) + "):")

        旧域 = self.当前
        旧循环 = self.循环深度
        self.循环深度 = 0        # ★ 函数体里不算外层循环（break 不能穿函数）
        self.当前 = self.找子域(名, len(参数)) if 匿名名 is None else None
        self.深 += 1
        if self.当前 is not None:
            for 外名 in sorted(self.当前.外层):
                self.写("nonlocal " + py名(外名))
        # ★ 哨兵检查必须在函数体【最前面】—— 函数体里马上就会用到这些参数
        for i, p in enumerate(参数):
            if 默认们[i] is None:
                continue
            self.写("if " + py名(p) + " is _缺省:")
            self.深 += 1
            # ★★ 生成默认值表达式时，把 self.深 临时退回「语句所在层」。
            #   为什么？因为表达式里可能藏着匿名函数，而它的 def 会被
            #   提到【本语句开头】去（见 待补 机制）——那里是外层缩进。
            #   不退回的话，def 会按「函数体内」的缩进写出来，
            #   插到外层就变成 unexpected indent。（demo23 就是这么炸的）
            内层深 = self.深
            self.深 = 外层深
            值代码 = self.式(默认们[i])
            self.深 = 内层深
            self.写(py名(p) + " = " + 值代码)
            self.深 -= 1
        self.语句表(体[1])
        self.深 -= 1
        self.当前 = 旧域
        self.循环深度 = 旧循环

        最少 = sum(1 for d in 默认们 if d is None)
        self.写(py名(名) + " = _函数(" + repr(名) + ", " + repr(list(参数))
                + ", " + 实现 + ", " + str(最少) + ")")

    def 找子域(self, 名, 参数个数):
        """按 (名字, 参数个数) 从当前域的子里挑 —— 同名重定义时会挑到第一个，无所谓。"""
        if self.当前 is None:
            return None
        for 子 in self.当前.子:
            if 子.名 == 名 and len(子.参数) == 参数个数 and not getattr(子, "_用过", False):
                子._用过 = True
                return 子
        for 子 in self.当前.子:
            if 子.名 == 名:
                return 子
        return None

    # ---------- 整程序 ----------
    def 编译(self, 语句们, 根域):
        """整个程序包进一个函数里 —— 这样「先调用、后定义」仍然是错的，
        跟解释器顺序执行的行为一模一样。"""
        self.当前 = 根域
        self.写("def _主():")
        self.深 += 1
        # ★★ 内建函数必须绑在 _主() 【里面】，不能绑在模块级。
        #   这是一个老 bug（Step 23 写 demo28 时才撞上）：
        #   用户一旦 `定义 长度(...)`，Python 就会把 _主() 里的 长度 当成局部变量，
        #   于是「定义之前那次 长度(x) 调用」直接 UnboundLocalError。
        #   挪进来之后：先绑内置 → 用户定义再覆盖，
        #   跟解释器「环境优先、查不到才用内置」的顺序完全一致。
        for 行 in 内建注册行().split("\n"):
            self.写(行)
        self.语句表(语句们, 回显=True)      # ← 顶层：光秃秃表达式会打印
        self.深 -= 1
        self.写("")
        self.写("")
        self.写("_主()")
        return "\n".join(self.行)


# ═══════════════════════════════════════════════════════════
# ④ 运行时前言 —— 编译产物要用的那一小段 Python
# ═══════════════════════════════════════════════════════════
# 为什么不直接内联成 Python 原生操作？
#   因为星语有几个「故意跟 Python 不一样」的地方：
#     · 一边是文本的 + 要拼接，不是报错
#     · 除以 0 要吐中文
#     · 打印前要先 fmt()（空→「空」、布尔→「真/假」、空字典→「[:]」）

前言 = '''# -*- coding: utf-8 -*-
# ===== 由星语编译器自动生成，别手改 =====
import sys
import re


class _函数:
    __slots__ = ("名字", "参数", "实现", "最少")

    def __init__(self, 名字, 参数, 实现, 最少=None):
        self.名字 = 名字
        self.参数 = list(参数)
        self.实现 = 实现
        # 有默认值的参数可以不传，但前面的必须全传
        self.最少 = len(self.参数) if 最少 is None else 最少

    def __repr__(self):
        return "<函数 " + self.名字 + "(" + ", ".join(self.参数) + ")>"


class _内建:
    __slots__ = ("名字",)

    def __init__(self, 名字):
        self.名字 = 名字

    def __repr__(self):
        return "<内置 " + self.名字 + ">"


_钩子表 = {}


def _注册(时机, 目标名, 目标, 钩子):
    if not isinstance(目标, _函数):
        raise RuntimeError("星语：「" + 目标名 + "」不是函数，钩子只能盯函数 —— "
                           "注册 要写在它定义之后")
    if not isinstance(钩子, _函数):
        raise RuntimeError("星语：钩子函数不是函数")
    _钩子表.setdefault(目标名, {}).setdefault(时机, []).append(钩子)


def _拔掉(时机, 目标名, 目标, 钩子):
    列 = _钩子表.get(目标名, {}).get(时机, [])
    for i, h in enumerate(列):
        if h.名字 == 钩子.名字:
            del 列[i]
            return None
    raise RuntimeError("星语：「" + 目标名 + "」的" + 时机 + "没挂着钩子「"
                       + 钩子.名字 + "」，拔不掉")


def _直调(f, 实参):
    if not isinstance(f, _函数):
        raise RuntimeError("星语：这个东西不是函数，不能加 () 调用它")
    if not (f.最少 <= len(实参) <= len(f.参数)):
        # ★ 跟解释器/VM 共用同一句，否则同一个错误三家说法又不一样了
        raise RuntimeError(_sl.参数个数消息(
            f.名字, f.最少, len(f.参数), len(实参)))
    # ★ 不足的用哨兵补上，实现体开头会把哨兵换成默认值
    补 = list(实参) + [_缺省] * (len(f.参数) - len(实参))
    return f.实现(*补)


def _调(f, 实参):
    if isinstance(f, _函数):
        名 = f.名字
        for h in _钩子表.get(名, {}).get("之前", ()):
            _直调(h, 实参)
        值 = _直调(f, 实参)
        for h in _钩子表.get(名, {}).get("之后", ()):
            _直调(h, (值,))
        return 值
    if isinstance(f, _内建):
        return _内建实现[f.名字](实参)
    raise RuntimeError("星语：这个东西不是函数，不能加 () 调用它")


def _真(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, (str, list, dict)):
        return len(v) > 0
    return True


def _循环速(v):
    """把要遍历的东西转成一个「快照序列」。

    ★ 为什么先复制一份？
      边遍历边改容器（追加 / 弹出）是无数 bug 的源头 —— Python 里会跳过元素
      甚至死循环。星语直接切断这种可能：遍历到的是开始那一刻的样子。
    ★ 字典返回【键】，跟 键们() 一致。要值就用 值们() 或 遍历 k 于 字典{ 字典[k] }。
    """
    if isinstance(v, dict):
        return list(v.keys())
    if isinstance(v, (list, str)):
        return list(v)
    raise RuntimeError("星语：遍历 只认列表、文本、字典，这是 " + _fmt(v))


class _跳出标号(Exception):
    """「跳出 某标号」的专用信号。

    ★ Step 22。为什么用异常而不是「标志变量 + 每层检查」？
      标志变量的问题：跳出后 break 只退一层，外层循环体剩下的语句
      还会继续跑完 —— 跟解释器对不上。异常一抛就直接到了标号那里，
      中间一句话都不多跑。
    """

    def __init__(self, 标签):
        super().__init__()
        self.标签 = 标签


def _还名(p):
    """把 Python 名字还原成星语名字（py名 的反函数）。"""
    if p.startswith("_v_"):
        p = p[3:]
    elif p.startswith("_v0"):
        p = p[3:]
    return p.replace("_g_", "#")


# ---- 报错文案改写（规则在编译时被内联成下面的 _改写规则）----
_改写规则 = []
_改写外套 = ""


def _改写(消息):
    for 式, 说 in _改写规则:
        m = 式.search(消息)
        if m:
            try:
                新 = _改写外套 + 说.format(*m.groups())
            except (IndexError, KeyError, ValueError):
                新 = _改写外套 + 说
            # ★ 保住 [第 N 行] —— 文案是整条替掉的，不特意留就会丢
            # ⚠️ 这段代码写在【普通三引号字符串】里，写正则要过两层转义，
            #    漏一层就 SyntaxWarning（打到 stderr 上，对比脚本立刻判失败）。
            #    所以索性别用正则了，纯字符串找一找，一目了然。
            起 = 消息.find("[第 ")
            if 起 >= 0:
                止 = 消息.find(" 行]", 起)
                if 止 > 起:
                    号 = 消息[起 + 3:止]
                    if 号.isdigit() and ("第 " + 号 + " 行") not in 新:
                        新 = "[第 " + 号 + " 行] " + 新
            return 新
    return _改写外套 + 消息


def _星语错误文本(e):
    """★ 变量没定义时 Python 吐的是英文，这里翻成星语自己那套中文提示，
    不然 尝试/出错 接到的消息会跟解释器版完全不同。

    _取星语行(e) 负责把「产物里的第几行」反推回「源文件里的第几行」，
    所以报出来的行号跟解释器版一模一样。
    """
    if isinstance(e, NameError):
        s = str(e)
        if s.startswith("name '") and s.endswith("' is not defined"):
            n = _还名(s[6:-16])
            # ★ 跟解释器/VM 用同一份消息（包括「你是不是想用关键字 X」那句）
            消息 = _sl.变量未定义消息(n)
        else:
            消息 = str(e)
    else:
        消息 = str(e)

    行 = _取星语行(e)
    if 行:
        消息 = "[第 " + str(行) + " 行] " + 消息
    return _改写(消息)


# 产物行号 → 星语行号（编译时生成，下面会被真表覆盖）
_行映射 = {}


def _取星语行(e):
    """沿着 traceback 往下走，取最后一个能查到映射的行 —— 那就是真正出错处。"""
    tb = getattr(e, "__traceback__", None)
    找到 = 0
    while tb is not None:
        行号 = tb.tb_lineno
        if 行号 in _行映射:
            找到 = _行映射[行号]
        tb = tb.tb_next
    return 找到


def _加(a, b):
    if isinstance(a, str) or isinstance(b, str):
        return _fmt(a) + _fmt(b)
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
        raise RuntimeError("星语：下标得是整数，你给的是 " + _fmt(下标))
    位置 = 下标 + len(容器) if 下标 < 0 else 下标
    if 位置 < 0 or 位置 >= len(容器):
        raise IndexError("星语：下标 " + str(下标) + " 越界了（这里只有 "
                         + str(len(容器)) + " 个）")
    return 位置


def _下标(容器, 下标):
    if isinstance(容器, dict):
        if 下标 not in 容器:
            raise RuntimeError("星语：字典里没有键 " + _带引号(下标)
                               + "（用 含有() 先问一下）")
        return 容器[下标]
    if isinstance(容器, (list, str)):
        return 容器[_正规下标(容器, 下标)]
    raise RuntimeError("星语：" + _fmt(容器) + " 这东西不能用 [] 取下标")


def _设下标(容器, 下标, 值):
    if isinstance(容器, dict):
        容器[下标] = 值
        return 值
    if isinstance(容器, list):
        容器[_正规下标(容器, 下标)] = 值
        return 值
    raise RuntimeError("星语：" + _fmt(容器) + " 这东西不能用 [] 改内容")


def _带引号(s):
    return '"' + str(s).replace("\\\\", "\\\\\\\\").replace("\\n", "\\\\n") + '"'


def _显示(v):
    if isinstance(v, str):
        return _带引号(v)
    return _fmt(v)


def _fmt(v):
    if v is None:
        return "空"
    if isinstance(v, bool):
        return "真" if v else "假"
    if isinstance(v, _函数):
        return "<函数 " + v.名字 + "(" + ", ".join(v.参数) + ")>"
    if isinstance(v, _内建):
        return "<内置 " + v.名字 + ">"
    if isinstance(v, list):
        return "[" + ", ".join(_显示(x) for x in v) + "]"
    if isinstance(v, dict):
        if not v:
            return "[:]"
        return "[" + ", ".join(_显示(k) + ": " + _显示(x) for k, x in v.items()) + "]"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


# ---- 内建函数：直接把 starlang.py 里那套搬过来，行为完全一致 ----
import starlang as _sl
_内建实现 = _sl.内建函数
# ★ Step 23：引入进来的模块常量也走同一张表（math_pi / np_e 这些）
_内建常量 = _sl.内建常量
# ★ 默认参数的哨兵直接借解释器那个单例 —— 两边共用同一个对象，
#   所以 is 判等不会出错。
_缺省 = _sl.缺省
'''


def 内建注册行():
    """把内建函数名一个不落地绑成整个程序的「变量」，
    这样用户自己 定义 长度(...) 也能正常覆盖 —— 跟解释器的查找顺序一致。"""
    行 = ["# ---- 星语内建函数（用户自己定义同名函数会覆盖它）----"]
    见过 = set()
    for 名字 in starlang.内建函数:
        if 名字 in 见过:
            continue
        见过.add(名字)
        行.append(py名(名字) + " = _内建(" + repr(名字) + ")")
    # ★ Step 23：引入进来的模块常量（比如 math_pi）也绑成变量
    for 名字 in starlang.内建常量:
        if 名字 in 见过:
            continue
        见过.add(名字)
        行.append(py名(名字) + " = _内建常量[" + repr(名字) + "]")
    return "\n".join(行)


def 改写规则行():
    """★ 把 报错文案.py 里的规则【内联】进产物。

    为什么不在运行时 import？因为生成的 .py 可能要拷到别的目录、甚至给
    别人跑。内联之后它自己就带着文案表，不依赖星语那堆文件。
    """
    try:
        import 报错文案
        规则 = 报错文案._编译好的
        外套 = 报错文案.外套
    except Exception:
        return "# （没找到 报错文案.py，报错保持原样）"

    if not 规则 and not 外套:
        return "# （报错文案用的是「正经」风格，不改写）"

    行 = ["# ---- 自定义报错文案（从 报错文案.py 抄过来的）----"]
    行.append("_改写规则 = [")
    for 式, 说 in 规则:
        行.append("    (re.compile(" + repr(式.pattern) + "), " + repr(说) + "),")
    行.append("]")
    行.append("_改写外套 = " + repr(外套))
    return "\n".join(行)


# ═══════════════════════════════════════════════════════════
# ⑤ 驱动
# ═══════════════════════════════════════════════════════════

def 编译源码(源码, 基准目录=None):
    """返回 (可执行的 Python 源码, 插入报告)"""
    # ★ 跟解释器一样，切词前先把「载入 "…"」拼进来
    if "载入" in 源码:
        源码 = starlang.展开载入(源码, 基准目录)

    # ★ Step 23：引入 "math" 这类行也在切词前吃掉（只登记名字，不改程序结构）
    if "引入" in 源码:
        源码 = starlang.展开引入(源码)

    tokens = Lexer(源码).tokenize()
    语句们 = Parser(tokens).parse_program()

    报告 = 织入(语句们)          # ★ 复用解释器那套织入 —— 它本来就工作在 AST 上

    # ★ 「跳出/继续」写在循环外面属于写错了，跟解释器用同一个检查、同一句话。
    #   （宏体里的那部分靠 编译器.循环深度 在 _语句 里把关）
    starlang.检查跳出(语句们)

    根 = 作用域("<程序>")
    扫描(根, 语句们)
    定名(根)

    器 = 编译器()
    主体 = 器.编译(语句们, 根)

    头 = 前言 + "\n" + 改写规则行() + "\n\n\n"

    # ★ 偏移得迭代算：映射表自己也要占行，但它要占几行又只取决于条数，
    #   所以先拿 0 生成一遍数出行数，再带真偏移重新生成一次就行。
    表 = 行映射行(器.行映射, 0)
    偏移 = (头 + 表).count("\n")
    表 = 行映射行(器.行映射, 偏移)

    return (头 + 表 + 主体 + "\n", 报告)


def 行映射行(映射, 偏移):
    """★ 把「产物第几行 → 源文件第几行」的表内联进产物。

    这样产物出错时，_取星语行() 顺着 traceback 的 tb_lineno 一查，
    就能报出源文件的真实行号 —— 而且【不用在每条语句前面插代码】，
    运行时一分钱开销都不多花。
    """
    if not 映射:
        return ""

    件 = []
    for 产物内行 in sorted(映射):
        件.append(str(产物内行 + 偏移) + ": " + str(映射[产物内行]))

    return ("# ---- 产物行号 → 源文件行号（报错时反查用）----\n"
            "_行映射 = {\n    " + ",\n    ".join(件) + ",\n}\n\n")


def 跑文件(路径, 只看=False, 存到=None):
    源码 = io.open(路径, encoding="utf-8-sig").read()
    # ★ 传基准目录：程序里的 载入 "工具.star" 按「程序所在目录」算，
    #   不然在别的目录敲命令就找不到文件了。
    产物, 报告 = 编译源码(源码, os.path.dirname(os.path.abspath(路径)))

    if 存到:
        io.open(存到, "w", encoding="utf-8", newline="\n").write(产物)
        print("已写入 " + 存到)

    if 只看:
        print(产物)
        return None

    if 报告 and "quiet" not in sys.argv:
        for line in 报告:
            print("   · " + line)

    # ★ 编译产物和「直接跑生成的 .py 文件」是同一件事 —— 这里只是省了个写盘
    全局 = {"__name__": "__星语__", "__file__": 路径}
    try:
        exec(compile(产物, "<星语编译产物>", "exec"), 全局)
    except SystemExit:
        raise
    except Exception as e:
        # ★★ 顶层烂掉也要走【产物自己的】转换器 —— 只有它手里有
        #    「产物行号 → 源文件行号」那张表，也才拼得出 [第 N 行] 前缀。
        #    少了这一步，程序内部 catch 的是带行号的新说法、外面烂掉的是旧说法。
        转 = 全局.get("_星语错误文本")
        if 转 is not None:
            try:
                raise SystemExit("  ! " + 转(e)) from None
            except SystemExit:
                raise
        raise
    return 全局


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("--") or a == "--show"]
    参数 = sys.argv[1:]

    if not 参数:
        print(__doc__)
        return

    路径 = 参数[0]
    只看 = "--show" in 参数
    存到 = None
    if "--out" in 参数:
        i = 参数.index("--out")
        if i + 1 < len(参数):
            存到 = 参数[i + 1]

    try:
        跑文件(路径, 只看=只看, 存到=存到)
    except SystemExit:
        raise
    except Exception as e:
        # ★ 顶层烂掉的异常是 Python 原生的（NameError 说的是英文），
        #   得先翻成星语那句，再过文案表 —— 否则外面的说法跟不上里面。
        print("  ! " + 顶层错误文本(e), file=sys.stderr)
        raise SystemExit(1)


def _还原名(p):
    """py名 的反函数：把生成代码里的名字还原成星语里的名字。

    ★ 这只是编译器【自己】要用的版本（用来拼错误提示）。
      产物里另有一个同功能的 _还名，那是写给生成代码用的，两者互不相干。
    """
    if p.startswith("_v_") or p.startswith("_v0"):
        p = p[3:]
    return p.replace("_g_", "#")


def 顶层错误文本(e):
    if isinstance(e, NameError):
        s = str(e)
        if s.startswith("name '") and s.endswith("' is not defined"):
            n = _还原名(s[6:-16])
            return starlang.改写报错(starlang.变量未定义消息(n))
    return starlang.改写报错(str(e))


if __name__ == "__main__":
    main()
