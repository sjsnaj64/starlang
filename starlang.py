#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
 星语 StarLang —— 从零手写一个玩具编程语言
 Step 1：词法分析 → 语法分析 → 求值   （一个完整的"计算器语言"）✔
 Step 2：变量 + 打印 + 多条语句        （语言第一次能"记住东西"）✔
 Step 3：if / else / while + 块        （语言第一次会"判断"和"重复"）✔
 Step 4：函数 + 参数 + 返回 + 闭包    （最后一块拼图：作用域与爸爸环境）✔
 Step 5：插入指令 —— 不改原函数，往里织代码（编译期改 AST）✔
 Step 6：字符串字面量 —— "双引号" / '单引号' / 转义 ✔
 Step 7：运行期钩子 —— 注册 / 拔掉 之前·之后，调用时才决定跑不跑 ✔
 Step 8：宏 —— 用户自定义语法（直接换 AST，不是函数）✔
 Step 9：列表 / 字典 / 下标 / 内置函数 ✔
 Step 10：文件读写 + 文本处理（自举的前置）✔
 Step 11：逻辑运算（且/或/非，短路）+ 真/假 + 否则如果 ✔
 Step 12：错误处理 —— 尝试 { } 出错 [错误] { } ✔
 Step 13：缩进当块 + 关键字同义词 + 报错行号/自定义文案 ✔
 Step 14：跳出 / 继续 / 空 / 读一行 / 载入 ✔
          —— 循环能提前收工、能读输入、能把程序拆成多个文件
 Step 15：纯星语标准库（标准库.star）✔
          —— 40+ 函数，一行 Python 都没有；写库顺便体检出「没有整除」
 Step 16：匿名函数 匿名(x) { … } ✔
          —— 高阶函数终于不用先起个名字了
 Step 17：三元表达式 + 复合赋值 + 自定义比较器排序 ✔
          —— 如果 条件 则 A 否则 B 能当值用；点 += 1；排序按(表, 比较器)
============================================================

任何语言（Python / JS / C++）跑起来，流水线永远长这样：

    源码字符串  "1 + 2 * 3"
        │
        │  ① 词法分析 Lexer   —— 把字符切成一个个 Token
        ▼
    Token 流  [NUM(1), +, NUM(2), *, NUM(3), EOF]
        │
        │  ② 语法分析 Parser  —— 把 Token 组装成一棵树
        ▼
    AST 抽象语法树  ('+', ('num',1), ('*', ('num',2), ('num',3)))
        │
        │  ③ 求值 Evaluate    —— 递归遍历这棵树，算出结果
        ▼
      结果  7

今天这三步全部跑通。虽然只会算数，但**骨架是真的**——
Step 2/3/4 只是往这套骨架上"挂"东西，不用重写。

怎么看懂它：
    python starlang.py                     交互模式（变量能跨行记住）
    python starlang.py "1 + 2 * 3"         默认全透视：Token 流 + 语法树 + 结果
    python starlang.py --tree "1+2*3"      只看语法树
    python starlang.py --tokens "1+2*3"    只看 Token 流
    python starlang.py --all demo2.star    跑整个文件并透视
"""

import os
import sys
from dataclasses import dataclass

# Windows 控制台默认不是 UTF-8，这句保证中文能正常打印
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 递归函数会让 Python 的调用栈用得很深，把上限放宽一点
sys.setrecursionlimit(10000)


# ═══════════════════════════════════════════════════════════
# ⓪ 报错文案 —— 想让星语说什么话，全在 报错文案.py 里改
# ═══════════════════════════════════════════════════════════
# ★ 这里只做一件事：把「已经抛出来的那条报错」翻译成你想要的说法。
#   它【不碰】任何语言行为 —— 词法、语法、求值该怎么错还怎么错，
#   只是错完了以后换个方式告诉你。
#
# 为什么能只改一处就管全部 100 多条报错？
#   因为报错最终只在【两个地方】被人看见：
#     ① main() 里打印      （程序跑完烂在屏幕上）
#     ② 尝试/出错 里存进变量（被程序自己接住）
#   把这两处都过一遍「改写」，就等于全改了。
try:
    import 报错文案 as _报错文案
except Exception:
    _报错文案 = None


def 改写报错(消息):
    """交给 报错文案.py 改写。那个文件不在 / 写坏了 → 原样返回，绝不掩盖真正的错。"""
    if _报错文案 is None:
        return 消息
    try:
        新 = _报错文案.改写(消息)
    except Exception:
        return 消息

    # ★★ 行号不能丢。
    #   文案表里的规则是按「星语：xxx」写的，一旦命中就是【整条替掉】，
    #   前面那个 [第 N 行] 也跟着没了 —— 于是同一个错误，
    #   编译器版报「「长度」只能量…」、解释器版报「[第 8 行] 「长度」只能量…」，
    #   两份说法对不上。差分测试就是这么把它抳出来的。
    if 新 != 消息:
        import re as _re
        m = _re.search(r"\[第 (\d+) 行\]", 消息)
        if m and not _re.search(r"第 \d+ 行", 新):
            新 = "[第 " + m.group(1) + " 行] " + 新
    return 新


# ★ 语法/词法错误自己就带着「第 N 行」（解析时就知道位置）；
#   运行时错误得靠 当前行 补上，统一加一个 [第 N 行] 前缀。
# 前缀只是加在前面，原消息一个字不动 —— 所以文案表里那些
# 「星语：变量「…」」的规则照样能 search 到。
def 最终文案(e, 行号=None):
    """把一条报错变成「最终要说给人听的那句话」：补行号 + 过文案表。

    ★ 行号 可以外部传：VM 用的是它自己的当前行（它是自己算的行号），
      不传就用解释器的 当前行。三个实现必须得出同一句话。

    ★★ 判「已经有行号了吗」不能只看开头 —— 文案表改写之后，
       消息会变成「第 133 行除以 0」，行号跑到句子中间去了。
       只看开头就会再套一层 [第 N 行]，变成「[第 127 行] 第 133 行除以 0」。
       所以整句搜索一下。
    """
    import re as _re
    消息 = str(e) or type(e).__name__
    用行 = 当前行[0] if 行号 is None else 行号
    if 用行 > 0 and not _re.search(r"第 \d+ 行", 消息):
        消息 = "[第 " + str(用行) + " 行] " + 消息
    return 改写报错(消息)


# ═══════════════════════════════════════════════════════════
# ① 词法分析 Lexer —— 字符串 → Token 流
# ═══════════════════════════════════════════════════════════
# 输入: "1 + 2 * 3"
# 输出: [Token('NUM', 1), Token('+', '+'), Token('NUM', 2), ...]

@dataclass
class Token:
    kind: str        # 类型：NUM / + / - / * / ** / ... / EOF
    value: object    # 值：NUM 存数字，其它存符号本身
    pos: int         # 在源码里的【字符偏移】（内部算位置用）
    line: int = 0    # ★ 第几行（从 1 开始）—— 报错给人看的是这个，不是 pos

    def __repr__(self):
        return f"Token({self.kind!r}, {self.value!r})"

    @property
    def name(self):
        """给人类看的名字：NUM/NAME 显示内容，换行显示 ⏎，运算符显示符号"""
        if self.kind == "NEWLINE":
            return "⏎"
        if self.kind == "LABEL":
            return "@" + str(self.value)
        if self.kind == "STR":
            return '"' + str(self.value) + '"'
        return str(self.value) if self.kind in ("NUM", "NAME") else self.kind


def is_name_start(ch):
    """名字的第一个字符：字母、下划线、或汉字"""
    return ch.isalpha() or ch == "_"


def is_name_part(ch):
    """名字的后续字符：字母、数字、下划线、汉字"""
    return ch.isalnum() or ch == "_"


class Lexer:
    """把源码字符串切成一个个 Token"""

    def __init__(self, text):
        self.text = text
        self.pos = 0
        self.depth = 0        # 括号深度：只有第 0 层的换行才算“语句结束”

        # ---- 缩进块（用缩进代替大括号）----
        self.行首 = True        # 是不是站在一行开头
        self.缩进栈 = [0]       # 当前嵌套的缩进宽度
        self.花括号 = 0         # ★ 只在花括号【外面】才认缩进
        #   为什么？因为用 { } 的代码里本来就随便缩进，要是也发 INDENT，
        #   所有旧代码立马全崩。两套写法各自安好，才是真兼容。

    def 行号(self, pos=None):
        """把字符偏移算成行号（从 1 开始）。

        ★ 为什么不一路上维护 self.line？因为读字符串、读数字这些函数
          里到处都在 pos += 1，漏一处行号就漂了。
          直接数 pos 前面有几个换行，永远错不了 —— 反正文本又不长。
        """
        到 = self.pos if pos is None else pos
        return self.text.count("\n", 0, 到) + 1

    def tokenize(self):
        tokens = []
        while self.pos < len(self.text):
            # ---- 行首：先数缩进，再决定发不发 INDENT / DEDENT ----
            if self.行首:
                self.行首 = False
                缩进 = 0
                起点 = self.pos
                while self.pos < len(self.text) and self.text[self.pos] in " \t":
                    缩进 += 4 if self.text[self.pos] == "\t" else 1
                    self.pos += 1
                # 空行 / 纯注释行不参与缩进比较（跟 Python 一样）
                还有东西 = (self.pos < len(self.text)
                          and self.text[self.pos] not in "\n\r")
                # ★ 只在这三样都成立时才算缩进：
                #   花括号外（用 { } 的代码缩进随便写）
                #   圆/方括号外（多行列表 [ \n 1, \n 2 \n ] 里的缩进不算块）
                #   不是纯注释行
                if (还有东西 and self.text[self.pos] != "#"
                        and self.花括号 == 0 and self.depth == 0):
                    if 缩进 > self.缩进栈[-1]:
                        self.缩进栈.append(缩进)
                        tokens.append(Token("INDENT", 缩进, 起点))
                    else:
                        while 缩进 < self.缩进栈[-1]:
                            self.缩进栈.pop()
                            tokens.append(Token("DEDENT", 缩进, 起点))
                        if 缩进 != self.缩进栈[-1]:
                            raise SyntaxError(
                                f"[语法错误] 第 {self.行号(起点)} 行: 缩进对不上 "
                                f"—— 这里缩进了 {缩进} 格，但没有哪一层是这个宽度")

            ch = self.text[self.pos]

            # --- 换行 = 一条语句结束（Step 2 新增）---
            #     括号里的换行不算，所以 (1 +\n  2) 这种折行是允许的
            if ch == "\n":
                # ★ Step 16：花括号块里【要】发 NEWLINE。
                #   块内的语句靠它分隔；不加这条的话，下面这种写法会被
                #   外层圆括号的 depth>0 压成一条语句，报「多了个 NAME」：
                #       映射(表, 匿名(x) {
                #           甲 = 1
                #           返回 甲
                #       })
                if self.depth == 0 or self.花括号 > 0:
                    tokens.append(Token("NEWLINE", "\n", self.pos))
                self.pos += 1
                self.行首 = True      # ← 下一圈开始数缩进
                continue

            # --- 其它空白直接跳过 ---
            #     ★ 顺便吃掉 BOM（U+FEFF）：Windows 上记事本 / PowerShell
            #       写出来的 .star 文件开头常带这个看不见的字符，
            #       不认它的话第一步词法就报「没见过的字符」—— 而且肉眼完全看不出。
            if ch in " \t\r\ufeff":
                self.pos += 1
                continue

            # --- 注释：# 到本行末尾全丢掉 ---
            #     ★ Step 5：`#@名字` 不是注释，是给这条语句起【标号】
            #       写法：  打印 x   #@检查点
            if ch == "#":
                if self.pos + 1 < len(self.text) and self.text[self.pos + 1] == "@":
                    self.pos += 2
                    start = self.pos
                    while (self.pos < len(self.text)
                           and is_name_part(self.text[self.pos])):
                        self.pos += 1
                    if self.pos > start:
                        tokens.append(Token("LABEL", self.text[start:self.pos], start))
                        continue
                    # `#@` 后面没名字 → 当普通注释处理
                while self.pos < len(self.text) and self.text[self.pos] != "\n":
                    self.pos += 1
                continue

            # --- ★ 光秃秃的 @名字 也是标号（跟 #@名字 完全等价）---
            #     写成：  打印 价格   @step1
            #     为什么两种都收：
            #       @step1   —— 好打、一眼看出“这是锚点”，但去掉功能就变语法错
            #       #@step1  —— 多一个字符，但去掉功能最多退化成一条注释，文件照跑
            #     ★ 一个字符的差别，决定的是“以后能不能反悔”。
            if ch == "@":
                self.pos += 1
                start = self.pos
                while (self.pos < len(self.text)
                       and is_name_part(self.text[self.pos])):
                    self.pos += 1
                if self.pos == start:
                    raise SyntaxError(
                        f"[词法错误] 第 {self.行号(start)} 行: @ 后面要跟一个标号名字"
                        f"（比如 @step1）"
                    )
                tokens.append(Token("LABEL", self.text[start:self.pos], start))
                continue

            # --- 名字：字母/下划线/汉字开头（Step 2 新增）---
            if is_name_start(ch):
                tokens.append(self.read_name())
                continue

            # --- 数字：连续的 0-9，最多一个小数点 ---
            if ch.isdigit() or (
                ch == "."
                and self.pos + 1 < len(self.text)
                and self.text[self.pos + 1].isdigit()
            ):
                tokens.append(self.read_number())
                continue

            # --- 字符串："双引号" 或 '单引号'（Step 6 新增）---
            if ch in ("\"", "'"):
                tokens.append(self.read_string())
                continue

            # --- 两字符运算符：先看两格，命中就吃两格 ---
            #     ⚠️ 必须在单字符之前看，否则 == 会被当成两个 =
            two = self.text[self.pos:self.pos + 2]
            if two in ("**", "==", "!=", "<=", ">=",
                       "+=", "-=", "*=", "/=", "%="):
                tokens.append(Token(two, two, self.pos))
                self.pos += 2
                continue

            # --- 单字符运算符（Step 9 又加了 [ ] : ）---
            if ch in "+-*/%()[]{},:<>=":
                # ★ 只让圆括号和方括号抑制换行；花括号是语句块，
                #   它里面的换行必须留着当「一条语句结束」。
                if ch in "([":
                    self.depth += 1
                elif ch in ")]":
                    self.depth = max(0, self.depth - 1)
                elif ch == "{":
                    self.花括号 += 1      # 进了大括号块，里边的缩进不再算数
                elif ch == "}":
                    self.花括号 = max(0, self.花括号 - 1)
                tokens.append(Token(ch, ch, self.pos))
                self.pos += 1
                continue

            raise SyntaxError(f"[词法错误] 第 {self.行号()} 行: 没见过的字符 {ch!r}")

        tokens.append(Token("EOF", None, self.pos))   # 结尾哨兵，方便 Parser 判断"读完了"

        # ★ 文件结束时把没关的缩进全关掉（缩进栈里剩几层就补几个 DEDENT）
        while len(self.缩进栈) > 1:
            self.缩进栈.pop()
            tokens.append(Token("DEDENT", 0, self.pos))

        # ★ 统一给每个 Token 打上行号。放在这里一次性算完，
        #   就不用管上面几十个 pos += 1 会不会漏记 —— 算出来的东西不会漂。
        行 = 1
        上 = 0
        for t in tokens:
            行 += self.text.count("\n", 上, t.pos)
            上 = t.pos
            t.line = 行
        return tokens

    def read_number(self):
        start = self.pos
        has_dot = False
        while self.pos < len(self.text):
            ch = self.text[self.pos]
            if ch.isdigit():
                self.pos += 1
            elif ch == "." and not has_dot:
                has_dot = True
                self.pos += 1
            else:
                break
        raw = self.text[start:self.pos]
        return Token("NUM", float(raw) if has_dot else int(raw), start)

    def read_name(self):
        """读一个名字：x / hp / 星尘 / max_hp 都可以"""
        start = self.pos
        while self.pos < len(self.text) and is_name_part(self.text[self.pos]):
            self.pos += 1
        return Token("NAME", self.text[start:self.pos], start)

    def read_string(self):
        """读一段字符串字面量。

        支持的转义：\\n \\t \\r \\\\ \\" \\' \\0 和 \\uXXXX
        ★ 转义必须显式支持 —— 不然 `"a\\nb"` 里的反斜杠会原样进字符串，
          打印出来是个反斜杠加 n，而不是换行。
        ★ 换行不闭合直接报错：不然少一个引号会把后面整个文件吃进去，
          报错位置离真凶老远，极难查。
        """
        start = self.pos
        引号 = self.text[self.pos]
        self.pos += 1
        缓冲 = []
        转义表 = {"n": "\n", "t": "\t", "r": "\r",
                 "\\": "\\", '"': '"', "'": "'", "0": "\0"}

        while self.pos < len(self.text):
            ch = self.text[self.pos]

            if ch == "\\":
                if self.pos + 1 >= len(self.text):
                    raise SyntaxError(
                        f"[词法错误] 第 {self.行号()} 行: 反斜杠后面什么都没了"
                    )
                nxt = self.text[self.pos + 1]
                if nxt in 转义表:
                    缓冲.append(转义表[nxt])
                    self.pos += 2
                    continue
                if nxt == "u":
                    hexs = self.text[self.pos + 2:self.pos + 6]
                    try:
                        缓冲.append(chr(int(hexs, 16)))
                        self.pos += 6
                        continue
                    except ValueError:
                        raise SyntaxError(
                            f"[词法错误] 第 {self.行号()} 行: \\u 后面要跟 4 位十六进制，"
                            f"实际读到 {hexs!r}"
                        )
                raise SyntaxError(
                    f"[词法错误] 第 {self.行号()} 行: 不认识的转义 \\{nxt}"
                    "（认得的：\\n \\t \\r \\\\ \\\" \\' \\0 \\uXXXX）"
                )

            if ch == 引号:
                self.pos += 1
                return Token("STR", "".join(缓冲), start)

            if ch == "\n":
                raise SyntaxError(
                    f"[词法错误] 第 {self.行号(start)} 行: 字符串没闭合 —— "
                    f"这一行走到头都没碰到收尾的 {引号}"
                )

            缓冲.append(ch)
            self.pos += 1

        raise SyntaxError(f"[词法错误] 第 {self.行号(start)} 行: 字符串一直到文件末尾都没闭合")


# ═══════════════════════════════════════════════════════════
# ② 语法分析 Parser —— Token 流 → AST
# ═══════════════════════════════════════════════════════════
# 用的是最经典的「递归下降」，核心思想只有一句话：
#
#   运算优先级 = 函数的嵌套层数
#   优先级越低，函数越靠外（越先被调用）
#
# 文法（从外到内 = 从低到高优先级，每深入一层就高一档）：
#   expression     := comparison
#   comparison     := additive (('<'|'>'|'=='|'!='|'<='|'>=') additive)*
#   additive       := multiplicative (('+'|'-') multiplicative)*
#   multiplicative := unary (('*'|'/'|'%') unary)*
#   unary          := ('-'|'+') unary | power
#   power          := primary ('**' unary)?        # 右结合
#   primary        := NUM | '(' expression ')'
#
# ⚠️ 这七层必须一层不落。少任何一层，那一档优先级就塔了 ——
#    比如露了 multiplicative，`1 + 2 * 3` 会在读到 * 时报「这位置多了个 *」。
#
# ---- 语句层的文法（Step 2 新增）----
#   program     := statement*
#   statement   := print_stmt | assign_stmt | expr_stmt
#   print_stmt  := ('print'|'打印') expression
#   assign_stmt := NAME '=' expression
#   expr_stmt   := expression
#
# ⚠️ 「打印 x」和「x = 5」开头都是一个 NAME，怎么分？
#    往前偷看一个 Token：下一个是 = 就是赋值，否则就是打印。
#    这就是 Parser.peek() 存在的全部理由。

# ═══════════════════════════════════════════════════════════# 关键字词表
# 星语的原则：**同一个意思，你想得到的说法基本都认**。
# 想不起来「只要」叫什么，敲 循环 / while / 重复 都行 —— 不该因为词穷卡住。
# （都是元组，第一个是「正规名」，报错和速查表里用它。）
PRINT_WORDS = ("print", "打印", "输出", "显示", "说", "echo")
IF_WORDS    = ("if", "如果", "假如", "若", "要是")
ELSE_WORDS  = ("else", "否则", "不然")
# ★ 「否则如果」在词法里是一个整体标识符 —— 汉字连着写中间没分隔符，
#   所以 `否则如果` 会被读成一个 NAME，不能用「否则」去匹配它。
ELSEIF_WORDS = ("否则如果", "否则若", "elif", "elseif", "不然如果")
WHILE_WORDS = ("while", "当", "只要", "循环", "重复", "loop")
MAX_LOOP    = 500000        # 死循环保险丝

# ★ 行号旁表：id(语句) → 第几行。运行时出错时靠它告诉用户「第几行拉的一坨」。
#   为什么不把行号塞进 AST 里？因为 AST 到处都是 stmt[0]/stmt[1] 的解构，
#   多塞一位全都得改。用旁表一个字段都不动。
#   （id 是稳定的：AST 解析完之后整棵树都还活着，不会被回收复用。）
语句行表 = {}
当前行 = [0]           # 正在跑的那条语句是第几行
FUNC_WORDS   = ("fn", "func", "def", "function", "定义", "函数")
RETURN_WORDS = ("return", "返回", "回传", "交回")

# ---- Step 5：插入指令 ----
INSERT_WORDS = ("插入", "insert", "插进去", "塞进去")
LABEL_WORDS  = ("标号", "标签")
HEAD_WORDS   = ("开头", "最前", "开始", "head")
TAIL_WORDS   = ("结尾", "最后", "末尾", "tail")

# ---- Step 7：运行期钩子 ----
REGISTER_WORDS   = ("注册", "挂上", "hook", "register")
UNREGISTER_WORDS = ("拔掉", "摘掉", "卸下", "unhook", "unregister")
BEFORE_WORDS   = ("之前", "前", "before")
AFTER_WORDS    = ("之后", "后", "after")
MAX_HOOK_DEPTH = 50        # 钩子套钩子的保险丝

# ---- Step 12：错误处理 ----
TRY_WORDS   = ("尝试", "试试", "try")
CATCH_WORDS = ("出错", "错了", "出事", "catch")
DEFAULT_ERR_NAME = "错误"
#
# 语法：
#     尝试
#     {
#         可能出错的代码
#     }
#     出错 错误         ← 「错误」这个名字可以自己起，也可以省略
#     {
#         出错了才跑
#     }
#
# ★★★ 最需要小心的一件事：
#   「返回」在星语里是用 ReturnSignal 这个【异常】实现的。
#   如果 catch 写成 except Exception，它会把“返回”也一起吃掉 ——
#   函数就再也回不去了。所以必须先把 ReturnSignal 原样抛出去。

# ---- Step 8：宏（用户自定义语法）----
MACRO_WORDS = ("宏", "macro")
MAX_MACRO_DEPTH = 200      # 宏套宏的保险丝

# ★ 解析阶段用的登记表：名字 -> [参数名...]
#   为什么要模块级：解析器每条语句都会新建一个（REPL 每行建一个），
#   但“这个名字是宏”这个知识必须活到后面几行去。
已声明宏 = {}

# ---- Step 11：逻辑运算 + 真假字面量 ----
# 星语原本只有比较（== != < > <= >=），没「且/或/非」，也没有 真/假。
# 写自举代码时这是硬伤：每个「两个条件之一」都要套一层 如果…否则…
AND_WORDS  = ("且", "并且", "而且", "and")
OR_WORDS   = ("或", "或者", "or")
NOT_WORDS  = ("非", "not")
BOOL_WORDS = {"真": True, "假": False, "true": True, "false": False}

# ---- Step 14：空值 ----
# ★ 为什么必须补这个字面量？
#   因为 读一行() 读到文件尾要说「没东西了」。没有 空 的话只能返回 ""，
#   那就分不清「读到空行」和「读完了」—— 而这两个意思完全不同。
#   注意是单字：「空表」这种变量名不会被误认（猜关键字有 len>=2 的门槛）。
NULL_WORDS = ("空", "空值", "什么都没有", "null", "nil", "nothing")

# ---- Step 14：循环控制 ----
# 没有它们的时候，循环里想提前退出只能挂个标志变量，
# 每一层都要 if 判断一次，代码立刻变成一坨意大利面。
BREAK_WORDS    = ("跳出", "退出循环", "打断", "break")
CONTINUE_WORDS = ("继续", "跳过这圈", "下一圈", "continue")

# ---- Step 16：匿名函数 ----
# ★ 为什么叫「匿名」而不是「函数」？因为「函数」已经被 FUNC_WORDS 占了
#   （定义 / 函数 / fn / func / def 都是它的别名）。
#   写 函数(x) { … } 会被当成函数定义 —— 名字得错开。
#
# 语法：匿名(x) { 返回 x * 2 }      ← 花括号里，一行写完或者换行都行
LAMBDA_WORDS = ("匿名", "匿名函数", "lambda", "lam", "小函数")

# ---- Step 17：三元表达式 ----
# 以前想在表达式里放个条件，只能写成一条语句：
#
#     如果 分数 >= 60 { 标签 = "及格" } 否则 { 标签 = "不及格" }    ← 明明只是选一个值
#
# 现在能直接写：
#
#     标签 = 如果 分数 >= 60 则 "及格" 否则 "不及格"
#
# ★ 「则」是新词。为什么不用「那么」或「就」当主词？
#   「就」太短、太容易和普通句子撞；「则」一个字干净（它不进猜关键字，
#   因为前缀匹配有 len>=2 的门槛，不会误伤「则名」这种变量）。
THEN_WORDS = ("则", "那么", "then")

# ═══════════════════════════════════════════════════════════
# 名字写错了，先猜你想写什么
# ═══════════════════════════════════════════════════════════
# 写星语最容易卡住的地方不是逻辑，是「那个词到底叫什么」。
# 所以两道保险：
#   ① 每个关键字都收一堆同义说法（上面那堆括号里）
#   ② 实在想不起来、敲错了一个，报错里直接告诉你「你是不是想用 X」

全部关键字 = (
    PRINT_WORDS + IF_WORDS + ELSE_WORDS + ELSEIF_WORDS + WHILE_WORDS
    + FUNC_WORDS + RETURN_WORDS + INSERT_WORDS + LABEL_WORDS
    + HEAD_WORDS + TAIL_WORDS + REGISTER_WORDS + UNREGISTER_WORDS
    + BEFORE_WORDS + AFTER_WORDS + TRY_WORDS + CATCH_WORDS
    + MACRO_WORDS + AND_WORDS + OR_WORDS + NOT_WORDS
    + tuple(BOOL_WORDS) + NULL_WORDS + BREAK_WORDS + CONTINUE_WORDS
    + LAMBDA_WORDS + THEN_WORDS
)


def 猜关键字(名字, 宽松=False):
    """这个名字写错了？猜一个最像的关键字。猜不出返回 None。

    宽松=False（默认）：只用 difflib + 前缀匹配，宁可猜不出来也不乱猜。
       —— 运行时「变量未定义」就走这条，因为那儿的名字很可能合法。
    宽松=True：再加一条「只差一个字」。
       —— **只允许在语法已经明显出错时用**（后面跟着数字/字符串）。
       否则 结算→结尾、分数→函数、吃掉→拔掉 这种正常变量名全会被误伤。
    """
    if not isinstance(名字, str) or not 名字:
        return None
    import difflib
    候选 = difflib.get_close_matches(名字, 全部关键字, n=1, cutoff=0.7)
    if 候选:
        return 候选[0]
    if 宽松 and len(名字) >= 2:
        # 中文两字词只错一个字（如过 / 如果）—— difflib 对这种短串只给 0.5
        for 词 in 全部关键字:
            if len(词) == len(名字) and 词 != 名字:
                不同 = sum(1 for a, b in zip(词, 名字) if a != b)
                if 不同 == 1:
                    return 词
    # 「打印x」这种没打空格的：名字以某个关键字开头
    for 词 in sorted(全部关键字, key=len, reverse=True):
        if len(词) >= 2 and 名字.startswith(词) and len(名字) > len(词):
            return 词
    return None


def 速查表():
    """忘词了敲 帮助。★ 每个关键字都把等价说法列出来 —— 认得的都算。"""

    def 行(正规, 别名, 说明):
        串 = " / ".join(别名)
        if len(串) > 24:
            # 太长了就分两行，别把说明挤出去
            return "      " + 串 + "\n" + " " * 8 + "→ " + 说明
        return "  %-24s %s" % (串, 说明)

    print()
    print("═" * 72)
    print("  星语速查   （同一行的说法都等价，想得起哪个用哪个）")
    print("═" * 72)
    组(行, "打印", PRINT_WORDS, "打印一个值")
    组(行, "如果", IF_WORDS, "如果 条件 { … }")
    组(行, "否则", ELSE_WORDS, "跟在 如果 后面")
    组(行, "否则如果", ELSEIF_WORDS, "★ 一个词，中间不能空格")
    组(行, "只要", WHILE_WORDS, "只要 条件 { … }")
    组(行, "定义", FUNC_WORDS, "定义 f(x) { … }")
    组(行, "返回", RETURN_WORDS, "返回 值")
    组(行, "且", AND_WORDS, "两边都真才真（会短路）")
    组(行, "或", OR_WORDS, "有一边真就真（会短路）")
    组(行, "非", NOT_WORDS, "非 条件")
    组(行, "真 / 假", tuple(BOOL_WORDS), "布尔字面量")
    组(行, "空", NULL_WORDS, "空值（读到输入结束时就是它）")
    组(行, "跳出", BREAK_WORDS, "立刻结束这一层循环")
    组(行, "继续", CONTINUE_WORDS, "跳过这一圈剩下的，直接进下一圈")
    组(行, "匿名", LAMBDA_WORDS, "匿名(x) { 返回 x * 2 } —— 当场造个函数")
    组(行, "  —— 三元", ("三元",), "如果 条件 则 A 否则 B（能当值用）")
    组(行, "尝试", TRY_WORDS, "尝试 { … }")
    组(行, "出错", CATCH_WORDS, "出错 错 { … }，后面可以跟个变量名")
    组(行, "插入", INSERT_WORDS, "插入 函数名 开头 { … }")
    组(行, "  位置", HEAD_WORDS + TAIL_WORDS, "或者直接写序号 1 2 3")
    组(行, "  标号", LABEL_WORDS, "插入 标号 名字 { … }")
    组(行, "注册", REGISTER_WORDS, "注册 之前 函数 钩子")
    组(行, "拔掉", UNREGISTER_WORDS, "拔掉 之前 函数 钩子")
    组(行, "  时机", BEFORE_WORDS + AFTER_WORDS, "挂在调用前还是后")
    组(行, "宏", MACRO_WORDS, "宏 名字(参数) { … }")

    print()
    print("  ── 运算符 ──")
    print("    +  -  *  /  %  **        ==  !=  <  >  <=  >=")
    print("    = 赋值                  [ ] 列表    [键: 值] 字典    列表[0] 取下标")
    print("    # 注释                  @标号        \"文本\" / '文本'")

    print()
    print("  ── 内置函数 ──")
    中文内建 = [n for n in sorted(内建函数) if not n.isascii()]
    英文内建 = [n for n in sorted(内建函数) if n.isascii()]
    print("    " + "  ".join(中文内建))
    print("    " + "  ".join(英文内建) + "   ← 英文名也能用")

    print()
    print("  ── 小例子 ──")
    print("    价格 = 100")
    print("    如果 价格 > 50 { 打印 \"太贵了\" } 否则 { 打印 \"还行\" }")
    print("    定义 加税(元) { 返回 元 * 1.06 }")
    print("    打印 加税(100)")
    print("═" * 72)
    print("  敲 q 退出")
    print()


def 组(行函数, 正规, 别名, 说明):
    print(行函数(正规, 别名, 说明))


def 变量未定义消息(名字):
    """★ 解释器 / 编译器产物 / VM 三边都必须调这个，否则报错会对不上。"""
    提示 = 猜关键字(名字)
    if 提示:
        return ("星语：变量「" + 名字 + "」还没定义过 —— 你是不是想用关键字「"
                + 提示 + "」？（关键字后面要打空格或换行）")
    return "星语：变量「" + 名字 + "」还没定义过（先用 " + 名字 + " = 值 定义它）"
#
# 语法：
#     宏 名字(参数1, 参数2)
#     {
#         展开后的语句……
#     }
#
#     调用：  名字( 表达式 或 { 语句块 }, …… )
#
# ★★ 宏和函数长得像，但根本不是一回事：
#
#     函数：先把实参【算成值】，再进一个新环境里跑
#     宏  ：把实参的【代码原样搬进去】，在【调用者的环境】里跑
#
#   所以宏能做三件函数做不到的事：
#     ① 实参不求值 —— 用不到就不算（天然短路）
#     ② 能收到【语句块】当参数 —— 函数只能收值
#     ③ 展开后的代码看得到调用者的变量
#
#   ★ 代价（这叫“卫生宏”问题）：
#     宏体里如果用了和调用者同名的变量，会撞车。
#     真正的语言（Rust / Scheme）要花大力气解决这个，星语这里不解决 ——
#     但会把话说明白：宏体里尽量只用参数，别声明新变量。
#
# 语法：
#     注册 之前 目标函数 钩子函数
#     注册 之后 目标函数 钩子函数
#     拔掉 之前 目标函数 钩子函数
#     拔掉 之后 目标函数 钩子函数
#
# ★ 「拔掉」是「插入」永远做不到的事：
#     织入是编译期的，焊上去就下不来了；
#     钩子是运行期的，随时能挂、随时能拔。
#   ★ 拔不掉的东西不报错、默默失败，是最容易出事的写法 ——
#     所以没挂着的钩子去拔会直接报出来，不静默。
#
# ★ 它和「插入」是两种不同的东西，对比着看：
#
#   |                  | 插入（织入）      | 注册（钩子）          |
#   |------------------|-------------------|----------------------|
#   | 什么时候起作用    | 跑之前改 AST      | 每次调用时查表       |
#   | 看得到函数内部     | ✓ 共享同一环境    | ✗ 各自独立的环境     |
#   | 拿得到实参         | ✓（本就是参数）    | ✓ 钩子直接收实参     |
#   | 拿得到返回值       | ✗                 | ✓ 「之后」收返回值   |
#   | 能不能动态增删     | ✗ 编译期就定死    | ✓ 运行期随时改       |
#   | 运行时开销         | 0                 | 每次调用多几跳       |
#   | 防递归             | 天然不用管        | ★ 得自己防           |
#
# 一句话选型：
#   想“把代码长长地焊进函数里” → 用插入
#   想“在旁边看着它、还能随时拔掉” → 用注册
#
# 语法只有四种写法，全都只干同一件事：往某个语句列表的第 N 个空位塞东西
#
#     插入 函数名 开头 { … }     → 第 0 个空位（= 最前面）
#     插入 函数名 结尾 { … }     → 最后一个空位
#     插入 函数名 2    { … }     → 第 2 个空位（= 第 2 条之后）
#     插入 标号 名字   { … }     → 写 #@名字 的那条之后
#
# ⚠️ 为什么不支持「按语句文本匹配」？
#    因为文本相等不等于语义相等：空格、括号、注释一改就不认识；
#    同一句话出现两次时还不确定插哪一份。
#    真正难的不是“怎么找到”，而是“找到的那条是不是你心里那条”。
#    所以这里用【序号】和【标号】——这两个都不会自己变。

# 函数的文法（Step 4 新增）：
#   statement  := ... | funcdef | return_stmt
#   funcdef    := ('fn'|'定义') NAME '(' 参数表 ')' block
#   参数表     := (NAME (',' NAME)*)?
#   return_stmt := ('return'|'返回') expression?
#   expression := ... | postfix
#   postfix    := primary ('(' 实参表 ')')*      ← 函数调用

# 块与控制流的文法（Step 3 新增）：
#   statement  := ... | if_stmt | while_stmt | block
#   if_stmt    := ('if'|'如果') expression block (('else'|'否则') block)?
#   while_stmt := ('while'|'当') expression block
#   block      := '{' statement* '}'

# AST 用 tuple 表示，最省事又直观：
#   表达式：数字 ("num", 3) / 变量 ("var", "x")
#           二元运算 (运算符, 左, 右) / 一元运算 (运算符, 子树)
#   语句：  打印 ("print", 表达式)
#           赋值 ("assign", 名字, 表达式)
#           表达式语句 ("expr", 表达式)
#   整个程序就是一个 list，里面装着一堆语句

class Parser:

    def __init__(self, tokens):
        self.tokens = tokens
        self.i = 0
        self.宏表 = 已声明宏          # 共享模块级表 —— REPL 跨行也能认得到已定义的宏

    # ---------- 小工具 ----------
    @property
    def cur(self):
        return self.tokens[self.i]

    def peek(self, k=1):
        """往前偷看 k 个 Token，但不消费 —— 靠它区分「打印 x」和「x = 5」"""
        return self.tokens[min(self.i + k, len(self.tokens) - 1)]

    def advance(self):
        t = self.tokens[self.i]
        self.i += 1
        return t

    def expect(self, kind):
        if self.cur.kind != kind:
            raise SyntaxError(
                f"[语法错误] 第 {self.cur.line} 行: 期望 {kind!r}，实际读到 {self.cur.kind!r}"
            )
        return self.advance()

    # ---------- 入口 ----------
    def parse(self):
        """只读一条表达式（Step 1 的入口，保留备用）"""
        node = self.expression()
        if self.cur.kind != "EOF":
            raise SyntaxError(
                f"[语法错误] 第 {self.cur.line} 行: 这里多了个 {self.cur.kind!r}"
            )
        return node

    # ---------- 语句层（Step 2 新增）----------
    def parse_program(self):
        """一整个程序 = 一串语句，一行一条"""
        stmts = []
        while self.cur.kind != "EOF":
            # ★ DEDENT 出现在顶层 = 缩进退回比任何一层都少，直接吃掉别处报错
            if self.cur.kind in ("NEWLINE", "DEDENT"):
                self.advance()
                continue
            stmts.append(self.maybe_label(self.statement()))
            self.end_of_statement()
        return stmts

    def end_of_statement(self):
        """一条语句必须在行尾结束 —— 不然下面两行就会被粘成一行：
               2 ** 3 ** 2
               -3 ** 2        ← 会被读成  2**3**2 - 3**2  = 503！
        """
        if self.cur.kind == "NEWLINE":
            self.advance()
            return
        # ★ } 和 DEDENT 都是「块收尾」，不是「这行多了东西」，交给外层去收
        if self.cur.kind in ("EOF", "}", "DEDENT"):
            return
        # ★★ 缩进块刚收完尾（上一个是 DEDENT），那这条语句本来就已经结束了。
        #    序列是  ⏎ DEDENT 下一句 —— DEDENT 占掉了原本 NEWLINE 的位置。
        if self.i > 0 and self.tokens[self.i - 1].kind == "DEDENT":
            return
        raise SyntaxError(
            f"[语法错误] 第 {self.cur.line} 行: 这里多了个 {self.cur.kind!r}"
            f"（一行只能放一条语句）"
        )

    def statement(self):
        """一条语句。★ 外面这层只干一件事：给这条语句记下它从第几行开始的。"""
        行 = self.cur.line
        句 = self._语句()
        语句行表[id(句)] = 行
        return 句

    def _语句(self):
        """真正的语句解析。目前有这些：
             打印 print 表达式       （print / 打印）
             赋值 名字 = 表达式
             如果 if 条件 { ... } 否则 { ... }
             重复 while 条件 { ... }
             定义 fn 名字(参数) { ... }
             返回 return 表达式
             块 { ... }
             光秃秃一条表达式（会打印出值）
        """
        t = self.cur

        # ★ 卡手急救：行首写了个「像关键字」的名字，先把话说明白。
        #   不这么干的话，`whlie 1 { … }` 会一路解析到尾巴，
        #   最后报一句莫名其妙的「这里多了个 'NUM'」—— 人根本没往拼写上想。
        if (t.kind == "NAME" and t.value not in 全部关键字
                and t.value not in self.宏表):
            下 = self.peek()
            if 下.kind not in ("=", "NEWLINE", "EOF", "}",
                            "+=", "-=", "*=", "/=", "%="):
                # ★ 只有后面直接跟数字/字符串时，才敢用「只差一个字」的宽猜法。
                #   跟的是名字就是 `结算 单价 * 数量` 这种正常语句，不能乱猜。
                建议 = 猜关键字(t.value, 宽松=(下.kind in ("NUM", "STR")))
                if 建议:
                    raise SyntaxError(
                        f"[语法错误] 第 {t.line} 行: 「{t.value}」—— "
                        f"你是不是想写关键字「{建议}」？")

        # --- 宏调用：名字必须是前面被「宏」声明过的（而且后面跟着括号）---
        if t.kind == "NAME" and t.value in self.宏表:
            看看 = self.peek()
            if 看看.kind == "(":
                return self.macro_call_statement()

        # --- 关键字开头的语句（后面不是 = 才当关键字）---
        if t.kind == "NAME" and self.peek().kind != "=":
            if t.value in TRY_WORDS:
                return self.try_statement()
            if t.value in MACRO_WORDS:
                return self.macrodef_statement()
            if t.value in REGISTER_WORDS:
                return self.register_statement()
            if t.value in UNREGISTER_WORDS:
                return self.unregister_statement()
            if t.value in INSERT_WORDS:
                return self.insert_statement()
            if t.value in IF_WORDS:
                return self.if_statement()
            if t.value in WHILE_WORDS:
                return self.while_statement()
            if t.value in FUNC_WORDS:
                return self.funcdef_statement()
            if t.value in RETURN_WORDS:
                return self.return_statement()
            # ★ Step 14：循环控制。合法性（有没有套在循环里）留给 检查跳出()
            #   静态扫一遍再判 —— 执行到才算的话，「如果 假 { 跳出 }」
            #   就永远不会被发现，而编译器一步就查得出来，两边又不一致了。
            if t.value in BREAK_WORDS:
                self.advance()
                return ("break",)
            if t.value in CONTINUE_WORDS:
                self.advance()
                return ("continue",)
            if t.value in PRINT_WORDS:
                self.advance()
                return ("print", self.expression())

            # ★ 载入 是【预处理】指令（见 展开载入），正常情况根本走不到这里。
            #   能走到说明写法不对（比如 载入 写在表达式里、或没带引号），
            #   与其让用户看到「你是不是想写关键字插入」，不如直说。
            if t.value == "载入":
                raise SyntaxError(
                    f"[语法错误] 第 {t.line} 行: 「载入」要单独写一整行，"
                    f"而且路径要带引号 —— 载入 \"工具.star\""
                )

        # --- 复合赋值：名字后面跟 += -= *= /= %= ---
        #     ★ Step 17。
        if t.kind == "NAME" and self.peek().kind in ("+=", "-=", "*=",
                                                      "/=", "%="):
            名 = t.value
            运算 = self.peek().kind[0]     # "+=" -> "+"
            self.advance()                 # 吃掉名字
            self.advance()                 # 吃掉 +=/-=/…
            return ("opassign", 名, 运算, self.expression())

        # --- 赋值语句：名字后面紧跟 = ---
        if t.kind == "NAME" and self.peek().kind == "=":
            self.advance()                 # 吃掉名字
            self.advance()                 # 吃掉 =
            return ("assign", t.value, self.expression())

        # --- 光秃秃一个块 ---
        if t.kind == "{":
            return self.block()

        # --- 表达式语句（顺便接住 a[0] = 值 这种下标赋值）---
        节点 = self.expression()
        if self.cur.kind == "=" and 节点[0] == "index":
            self.advance()
            return ("setindex", 节点[1], 节点[2], self.expression())
        return ("expr", 节点)

    # ---------- 块与控制流（Step 3 新增）----------
    def block(self):
        """一个块。★ 两种写法都认：
               如果 条件 { … }        ← 大括号
               如果 条件               ← 缩进
                   做点什么
        """
        while self.cur.kind == "NEWLINE":     # 允许 { 另起一行
            self.advance()
        if self.cur.kind != "{":
            return self.缩进块()
        self.advance()                        # 吃掉 {
        stmts = []
        while self.cur.kind not in ("}", "EOF"):
            if self.cur.kind == "NEWLINE":    # 空行跳过
                self.advance()
                continue
            stmts.append(self.maybe_label(self.statement()))
            self.end_of_statement()
        self.expect("}")
        return ("block", stmts)

    def 缩进块(self):
        """靠缩进划出来的块。

        ★ 词法器保证了：只有花括号【外面】才会发 INDENT/DEDENT，
          所以用 { } 写的代码永远不会走到这里。
        """
        行 = self.cur.line
        if self.cur.kind != "INDENT":
            raise SyntaxError(
                f"[语法错误] 第 {行} 行: 这里要么写 {{ ，要么把这行往后缩进")
        self.advance()                        # 吃掉 INDENT
        stmts = []
        while True:
            while self.cur.kind == "NEWLINE":
                self.advance()
            if self.cur.kind in ("DEDENT", "EOF"):
                break
            stmts.append(self.maybe_label(self.statement()))
            self.end_of_statement()
        if self.cur.kind == "DEDENT":
            self.advance()
        if not stmts:
            raise SyntaxError(
                f"[语法错误] 第 {行} 行: 这个块里一句话都没有")
        return ("block", stmts)

    def if_statement(self):
        self.advance()                         # 吃掉 if / 如果
        return self.if_rest()

    def if_rest(self):
        """从条件开始读一个 if。拆出来是为了接「否则如果」的链式调用。"""
        cond = self.expression()
        then = self.block()
        els = None

        # 「} else {」允许跳行。但「}」后面也可能压根不是 else，
        # 所以：先记住位置 → 往前偷看 → 不对就把位置退回去。
        save = self.i
        while self.cur.kind == "NEWLINE":
            self.advance()

        是合并词 = (self.cur.kind == "NAME" and self.cur.value in ELSEIF_WORDS)
        是分开词 = (self.cur.kind == "NAME" and self.cur.value in ELSE_WORDS)

        if 是合并词:
            self.advance()                     # 吃掉整个「否则如果」
            els = self.if_rest()               # 它已经自带 if 了，直接从条件开始
        elif 是分开词:
            self.advance()                     # 吃掉「否则」
            if self.cur.kind == "NAME" and self.cur.value in IF_WORDS:
                self.advance()                 # 吃掉「如果」
                els = self.if_rest()
            else:
                els = self.block()
        else:
            self.i = save                      # ← 回退！真 parser 也这么干

        return ("if", cond, then, els)

    def while_statement(self):
        self.advance()                         # 吃掉 while / 当
        cond = self.expression()
        body = self.block()
        return ("while", cond, body)

    # ---------- 函数（Step 4 新增）----------
    def funcdef_statement(self):
        self.advance()                         # 吃掉 定义 / fn
        if self.cur.kind != "NAME":
            raise SyntaxError(f"[语法错误] 第 {self.cur.line} 行: 函数得有个名字")
        name = self.advance().value

        self.expect("(")
        params = []
        if self.cur.kind != ")":
            params.append(self.expect("NAME").value)
            while self.cur.kind == ",":
                self.advance()
                params.append(self.expect("NAME").value)
        self.expect(")")

        body = self.block()
        return ("funcdef", name, params, body)

    def return_statement(self):
        self.advance()                         # 吃掉 返回 / return
        if self.cur.kind in ("NEWLINE", "}", "EOF"):
            return ("return", None)            # 光秃秃一个「返回」
        return ("return", self.expression())

    # ---------- 标号与插入（Step 5 新增）----------
    def maybe_label(self, stmt):
        """一条语句后面可以跟 `#@名字` 给它起个标号。
        标号不改变任何执行行为，只是给「插入」一个稳定的落脚点。"""
        if self.cur.kind == "LABEL":
            新 = ("labeled", self.advance().value, stmt)
            语句行表[id(新)] = 语句行表.get(id(stmt), 0)   # 行号跟着壳一起搬
            return 新
        return stmt

    def insert_statement(self):
        """插入 目标 位置 { 语句... }

            插入 打招呼 开头 { … }     ← 塞到函数最前面
            插入 打招呼 结尾 { … }     ← 塞到最后面
            插入 打招呼 1    { … }     ← 塞在第 1 条之后
            插入 标号 检查点 { … }     ← 塞到写 #@检查点 的那条之后
        """
        self.advance()                         # 吃掉 插入

        # ---- 标号模式：不写函数名，直接认标号 ----
        if self.cur.kind == "NAME" and self.cur.value in LABEL_WORDS:
            self.advance()
            lab = self.expect("NAME").value
            return ("insert", ("label", lab), self.block())

        # ---- 函数模式：先要个函数名 ----
        if self.cur.kind != "NAME":
            raise SyntaxError(
                f"[语法错误] 第 {self.cur.line} 行: 「插入」后面要跟函数名或「标号」"
            )
        fn = self.advance().value

        if self.cur.kind == "NUM":            # 插入 a 2 { … }
            n = int(self.advance().value)
            return ("insert", ("index", fn, n), self.block())

        if self.cur.kind == "NAME":
            w = self.advance().value
            if w in HEAD_WORDS:
                return ("insert", ("head", fn), self.block())
            if w in TAIL_WORDS:
                return ("insert", ("tail", fn), self.block())
            raise SyntaxError(
                f"[语法错误] 第 {self.cur.line} 行: 「{fn}」后面要写 开头 / 结尾 / 一个序号，"
                f"实际读到 {w!r}"
            )

        raise SyntaxError(
            f"[语法错误] 第 {self.cur.line} 行: 「插入 {fn}」后面要写 开头 / 结尾 / 序号"
        )

    # ---------- 运行期钩子（Step 7 新增）----------
    def _读钩子三件套(self, 谁):
        """读「 之前/之后  目标函数  钩子函数 」三样，注册和拔掉共用"""
        if self.cur.kind != "NAME":
            raise SyntaxError(
                f"[语法错误] 第 {self.cur.line} 行: 「{谁}」后面要写 之前 / 之后"
            )
        词 = self.advance().value
        if 词 in BEFORE_WORDS:
            时机 = "之前"
        elif 词 in AFTER_WORDS:
            时机 = "之后"
        else:
            raise SyntaxError(
                f"[语法错误] 第 {self.cur.line} 行: 只能是 之前 或 之后，实际读到 {词!r}"
            )

        if self.cur.kind != "NAME":
            raise SyntaxError(
                f"[语法错误] 第 {self.cur.line} 行: 要写被盯的函数名"
            )
        目标 = self.advance().value

        if self.cur.kind != "NAME":
            raise SyntaxError(
                f"[语法错误] 第 {self.cur.line} 行: 要写当钩子的函数名"
            )
        钩子 = self.advance().value
        return 时机, 目标, 钩子

    def register_statement(self):
        """注册 之前 目标函数 钩子函数"""
        self.advance()                         # 吃掉 注册
        时机, 目标, 钩子 = self._读钩子三件套("注册")
        return ("register", 时机, 目标, 钩子)

    def unregister_statement(self):
        """拔掉 之前 目标函数 钩子函数

        ★ 和「插入」最大的区别就在这里：插进去的代码拔不下来，钩子能。
        """
        self.advance()                         # 吃掉 拔掉
        时机, 目标, 钩子 = self._读钩子三件套("拔掉")
        return ("unregister", 时机, 目标, 钩子)

    # ---------- 宏（Step 8 新增）----------
    def 跳过换行(self):
        """跳过空行。★ DEDENT 不能跳 —— 它是「块到这儿结束」的信号"""
        while self.cur.kind == "NEWLINE":
            self.advance()

    def macrodef_statement(self):
        """宏 名字(参数1, 参数2) { 展开体…… }

        ★ 必须在【最外层】写，而且要在第一次调用之前 ——
          因为解析到调用点的时候，得先知道这个名字是个宏，
          才知道括号里该按“表达式还是语句块”去读。
        """
        self.advance()                         # 吃掉 宏
        if self.cur.kind != "NAME":
            raise SyntaxError(
                f"[语法错误] 第 {self.cur.line} 行: 宏得有个名字"
            )
        名字 = self.advance().value

        self.expect("(")
        参数 = []
        if self.cur.kind != ")":
            参数.append(self.expect("NAME").value)
            while self.cur.kind == ",":
                self.advance()
                参数.append(self.expect("NAME").value)
        self.expect(")")

        体 = self.block()
        # ★ 登记到共享表：从这里开始，后面遇到「名字(」就按宏调用来读
        self.宏表[名字] = list(参数)
        return ("macrodef", 名字, 参数, 体)

    def macro_call_statement(self):
        """宏调用：名字( 实参, …… )。
        实参可以是表达式，也可以是 { 语句块 }。"""
        名字 = self.advance().value
        参数名 = self.宏表[名字]
        self.跳过换行()
        self.expect("(")

        实参 = []
        self.跳过换行()
        if self.cur.kind != ")":
            实参.append(self.宏实参())
            self.跳过换行()
            while self.cur.kind == ",":
                self.advance()
                实参.append(self.宏实参())
                self.跳过换行()
        self.expect(")")

        if len(实参) != len(参数名):
            raise SyntaxError(
                f"[语法错误] 第 {self.cur.line} 行: 宏「{名字}」要 {len(参数名)} 个参数"
                f"（{'、'.join(参数名) if 参数名 else '无'}），你给了 {len(实参)} 个"
            )
        return ("macro", 名字, 实参)

    def 宏实参(self):
        """实参：要么一整个语句块，要么一个表达式"""
        if self.cur.kind == "{":
            return self.block()
        return self.expression()

    # ---------- 错误处理（Step 12 新增）----------
    def try_statement(self):
        """尝试 { … } 出错 [名字] { … }"""
        self.advance()                         # 吃掉 尝试
        体 = self.block()

        self.跳过换行()
        if not (self.cur.kind == "NAME" and self.cur.value in CATCH_WORDS):
            raise SyntaxError(
                f"[语法错误] 第 {self.cur.line} 行: 「尝试」后面必须跟一个「出错」块"
                f"（实际读到 {self.cur.kind!r}）"
            )
        self.advance()                         # 吃掉 出错

        # 出错后面可以跟一个名字，用来自取错误信息；不写就叫「错误」
        名字 = DEFAULT_ERR_NAME
        if self.cur.kind == "NAME":
            名字 = self.advance().value

        处理 = self.block()
        return ("try", 体, 名字, 处理)

    # ---------- 各优先级层 ----------
    def expression(self):
        return self.logic_or()

    # ★ Step 11：或 比 且 松（跟 Python 一样：a or b and c 是 a or (b and c)）
    def logic_or(self):
        node = self.logic_and()
        while self.cur.kind == "NAME" and self.cur.value in OR_WORDS:
            self.advance()
            node = ("或", node, self.logic_and())
        return node

    def logic_and(self):
        node = self.comparison()
        while self.cur.kind == "NAME" and self.cur.value in AND_WORDS:
            self.advance()
            node = ("且", node, self.comparison())
        return node

    def comparison(self):
        node = self.additive()
        while self.cur.kind in ("<", ">", "==", "!=", "<=", ">="):
            op = self.advance().kind
            node = (op, node, self.additive())
        return node

    def additive(self):
        node = self.multiplicative()
        while self.cur.kind in ("+", "-"):
            op = self.advance().kind
            node = (op, node, self.multiplicative())
        return node

    def multiplicative(self):
        node = self.unary()
        while self.cur.kind in ("*", "/", "%"):
            op = self.advance().kind
            node = (op, node, self.unary())
        return node

    def unary(self):
        if self.cur.kind in ("-", "+"):
            op = self.advance().kind
            return (op, self.unary())          # 两元素 tuple = 一元节点
        # ★ Step 11：非 真 / 非 (a == b)
        if self.cur.kind == "NAME" and self.cur.value in NOT_WORDS:
            self.advance()
            return ("非", self.unary())
        return self.power()

    def power(self):
        node = self.postfix()
        if self.cur.kind == "**":
            self.advance()
            return ("**", node, self.unary())  # 右边再调 unary → 实现右结合
        return node

    # ★ Step 4 新插进来的一层：函数调用 f(x)
    #   插在 power 和 primary 中间 = 它的优先级比 ** 紧、比括号松。
    #   所以 f(x) ** 2 是 (f(x))**2，而不是 f(x ** 2)
    def postfix(self):
        node = self.primary()
        while True:
            if self.cur.kind == "(":
                self.advance()                 # 吃掉 (
                args = []
                if self.cur.kind != ")":
                    args.append(self.expression())
                    while self.cur.kind == ",":
                        self.advance()
                        args.append(self.expression())
                self.expect(")")
                node = ("call", node, args)    # 可以连锁：f(1)(2)
                continue
            # ★ Step 9：取下标 a[0]
            if self.cur.kind == "[":
                self.advance()
                下标 = self.expression()
                self.expect("]")
                node = ("index", node, 下标)
                continue
            break
        return node

    def primary(self):
        t = self.cur
        if t.kind == "NUM":
            self.advance()
            return ("num", t.value)
        if t.kind == "STR":                   # Step 6：字符串字面量
            self.advance()
            return ("str", t.value)
        # ★ Step 9：列表 / 字典
        #    []        → 空列表
        #    [1, 2]    → 列表
        #    [: ]      → 空字典
        #    ["a": 1] → 字典（看到冒号就是字典）
        #  为什么字典也用方括号：因为花括号已经被语句块占了，
        #  宏实参那里 { } 到底是块还是字典分不清 —— 干脆不用花括号。
        if t.kind == "[":
            return self.集合字面量()
        # ★ Step 11：真 / 假
        if t.kind == "NAME" and t.value in BOOL_WORDS:
            self.advance()
            return ("bool", BOOL_WORDS[t.value])
        # ★ Step 14：空
        if t.kind == "NAME" and t.value in NULL_WORDS:
            self.advance()
            return ("null",)
        # ★ Step 16：匿名函数
        #   体必须是 { } 块。想用缩进块不行 —— 缩进块会把后面的语句
        #   全吃进去，在表达式中间没法判断到哪结束。
        if t.kind == "NAME" and t.value in LAMBDA_WORDS:
            return self.匿名函数()
        # ★ Step 17：三元表达式。
        #   注意只有【表达式位置】的 如果 才走这里 —— 语句开头的
        #   如果 在 _语句() 里就被 if_statement() 接走了。
        if t.kind == "NAME" and t.value in IF_WORDS:
            return self.三元式()
        if t.kind == "NAME":
            self.advance()
            return ("var", t.value)            # Step 2：读一个变量
        if t.kind == "(":
            self.advance()
            node = self.expression()           # 括号里重新从最低优先级开始
            self.expect(")")
            return node
        raise SyntaxError(
            f"[语法错误] 第 {t.line} 行: 这里应该是数字、变量名或 ( ，实际读到 {t.kind!r}"
        )

    def 匿名函数(self):
        """匿名(x, y) { … } —— 当场造一个函数值出来。

        ★ 为什么体只能用 { } 块，不能用缩进块？
            缩进块靠「下一行缩进变回来」判断结束。在表达式中间（比如
            `映射(表, 匿名(x)` 的下一行）根本没法判断哪一行是它的结尾 ——
            后面的语句全部缩进更深，会被全吃进去。
            花括号有明确的 } 收尾，所以只认这一种写法。
        """
        self.advance()                        # 吃掉 匿名 / lambda
        self.expect("(")
        参数们 = []
        while self.cur.kind != ")":
            if self.cur.kind != "NAME":
                raise SyntaxError(
                    f"[语法错误] 第 {self.cur.line} 行: 匿名函数的参数得是名字，"
                    f"实际读到 {self.cur.kind!r}")
            参数们.append(self.cur.value)
            self.advance()
            if self.cur.kind == ",":
                self.advance()
            elif self.cur.kind != ")":
                raise SyntaxError(
                    f"[语法错误] 第 {self.cur.line} 行: 参数之间要用逗号隔开")
        self.expect(")")
        return ("lambda", 参数们, self.block())

    def 三元式(self):
        """如果 条件 则 甲 否则 乙 —— 能直接当值用，不必拆成语句。

        ★ 不用括号的话，嵌套起来不好读：
            如果 a 则 如果 b 则 1 否则 2 否则 3
          这写法右结合、从右往左吃，没问题。
        """
        行 = self.cur.line
        self.advance()                        # 吃掉 如果 / 假如 / 若 …
        条件 = self.expression()
        if not (self.cur.kind == "NAME" and self.cur.value in THEN_WORDS):
            实际 = self.cur.value if self.cur.kind in ("NAME", "NUM", "STR") \
                else self.cur.kind
            raise SyntaxError(
                f"[语法错误] 第 {行} 行: 三元式写到一半卡住了 —— "
                f"「如果 条件」后面要跟「则」，这里读到的却是 {实际!r}"
            )
        self.advance()                        # 吃掉 则
        真值 = self.expression()
        if not (self.cur.kind == "NAME" and self.cur.value in ELSE_WORDS):
            实际 = self.cur.value if self.cur.kind in ("NAME", "NUM", "STR") \
                else self.cur.kind
            raise SyntaxError(
                f"[语法错误] 第 {行} 行: 三元式还差一半 —— 前面有「则」，"
                f"后面就得有「否则」，这里读到的却是 {实际!r}"
            )
        self.advance()                        # 吃掉 否则
        假值 = self.expression()
        return ("ternary", 条件, 真值, 假值)

    def 集合字面量(self):
        """解析 [ ... ]，到底是列表还是字典看有没有冒号"""
        self.expect("[")
        if self.cur.kind == "]":                 # []
            self.advance()
            return ("list", [])
        if self.cur.kind == ":":                 # [:]
            self.advance()
            self.expect("]")
            return ("dict", [])

        首 = self.expression()

        if self.cur.kind == ":":                 # 字典
            self.advance()
            对 = [[首, self.expression()]]
            while self.cur.kind == ",":
                self.advance()
                if self.cur.kind == "]":
                    break
                键 = self.expression()
                self.expect(":")
                对.append([键, self.expression()])
            self.expect("]")
            return ("dict", 对)

        项 = [首]                                 # 列表
        while self.cur.kind == ",":
            self.advance()
            if self.cur.kind == "]":
                break
            项.append(self.expression())
        self.expect("]")
        return ("list", 项)


# ═══════════════════════════════════════════════════════════
# ③ 求值 Evaluator —— AST → 结果
# ═══════════════════════════════════════════════════════════
# Step 2 引入两个新概念，是整个教程最大的分水岭：
#
#   ◆ 表达式 Expression —— 会“算出一个值”。     1 + 2   →   3
#   ◆ 语句   Statement  —— 只“做一件事”，没值。  x = 5
#
# 所以从今往后是两套函数，别混：
#     evaluate(表达式, 环境)  → 返回一个值
#     execute (语句, 环境)    → 只干活，不返回值
#
#   ◆ 环境 Environment —— 变量到底存在哪儿。就是个字典：
#                            {"星尘": 100, "hp": 250}
#
# ★ Step 4：环境长出「爸爸」了！
#   Step 3 时我说它会改，结果没改 —— 因为块不建新环境。
#   现在真需要了：函数调用会建一个新环境，爸爸指向「定义它时的环境」。
#   找变量的顺序：自己 → 爸爸 → 爷爷 → …… → 都没有才报错。
#   这就是「作用域」的全部秘密。

class Environment:
    """变量存在哪。Step 4 起，它可以有爸爸了"""

    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent              # ← 爸爸环境（没有就是 None）

    def get(self, name):
        env = self
        while env is not None:
            if name in env.vars:
                return env.vars[name]
            env = env.parent              # ← 自己这儿没有，问爸爸
        raise NameError(变量未定义消息(name))

    def define(self, name, value):
        """只定义在自己这一层，不打扰爸爸 —— 参数、函数名用这个"""
        self.vars[name] = value
        return value

    def set(self, name, value):
        """赋值：自己和祖先里哪儿有就改哪儿；四处都没有，才建在自己这儿"""
        env = self
        while env is not None:
            if name in env.vars:
                env.vars[name] = value
                return value
            env = env.parent
        self.vars[name] = value
        return value


class Func:
    """一个星语函数。注意 closure 这个字段 —— 它就是「闭包」"""

    def __init__(self, name, params, body, closure):
        self.name = name
        self.params = params
        self.body = body            # ("block", [语句...])
        self.closure = closure      # ★ 定义它时的那个环境！函数会一直记得


class 内建:
    """星语里能直接用、但不用自己定义的函数（长度/追加/……）。
    ★ 它不是 Func —— 因为 Func 的意思里有“星语写的”、有闭包、有环境，
      而这几个是 Python 侧直接干活的，不应该假装成星语函数。"""

    def __init__(self, 名字):
        self.名字 = 名字

    def __repr__(self):
        return "<内建 " + self.名字 + ">"


def _要参数(名字, 实参, 最少, 最多=None):
    最多 = 最少 if 最多 is None else 最多
    if not (最少 <= len(实参) <= 最多):
        要 = str(最少) if 最少 == 最多 else str(最少) + "~" + str(最多)
        raise RuntimeError(
            "星语：内置函数 " + 名字 + " 要 " + 要 + " 个参数，你给了 "
            + str(len(实参)) + " 个"
        )


def _正规下标(容器, 下标):
    """把下标规整成 Python 能用的正整数，越界就把话说清楚"""
    if isinstance(下标, bool) or not isinstance(下标, int):
        raise RuntimeError("星语：下标得是整数，你给的是 " + fmt(下标))
    位置 = 下标 + len(容器) if 下标 < 0 else 下标      # 负数从后面数
    if 位置 < 0 or 位置 >= len(容器):
        raise IndexError(
            "星语：下标 " + str(下标) + " 越界了（这里只有 " + str(len(容器)) + " 个）"
        )
    return 位置


def 取下标(容器, 下标):
    if isinstance(容器, dict):
        if 下标 not in 容器:
            # ★ 用 RuntimeError 而不是 KeyError ——
            #   KeyError 打印时会把你给的字符串再套一层引号，难看。
            raise RuntimeError(
                "星语：字典里没有键 " + _带引号(下标) + "（用 含有() 先问一下）"
            )
        return 容器[下标]
    if isinstance(容器, (list, str)):
        return 容器[_正规下标(容器, 下标)]
    raise RuntimeError("星语：" + fmt(容器) + " 这东西不能用 [] 取下标")


def _长度(实参):
    _要参数("长度", 实参, 1)
    v = 实参[0]
    if isinstance(v, (list, str, dict)):
        return len(v)
    raise RuntimeError("星语：长度() 只能量文本、列表、字典，这是 " + fmt(v))


def _追加(实参):
    _要参数("追加", 实参, 2)
    列表, 值 = 实参
    if not isinstance(列表, list):
        raise RuntimeError("星语：追加() 的第一个参数得是列表，你给的是 " + fmt(列表))
    列表.append(值)
    return 列表


def _弹出(实参):
    _要参数("弹出", 实参, 1, 2)
    列表 = 实参[0]
    if not isinstance(列表, list):
        raise RuntimeError("星语：弹出() 的第一个参数得是列表")
    if len(实参) == 2:
        return 列表.pop(_正规下标(列表, 实参[1]))
    if not 列表:
        raise RuntimeError("星语：列表是空的，弹不出东西来")
    return 列表.pop()


def _键们(实参):
    _要参数("键们", 实参, 1)
    if not isinstance(实参[0], dict):
        raise RuntimeError("星语：键们() 要的是字典")
    return list(实参[0].keys())


def _值们(实参):
    _要参数("值们", 实参, 1)
    if not isinstance(实参[0], dict):
        raise RuntimeError("星语：值们() 要的是字典")
    return list(实参[0].values())


def _含有(实参):
    _要参数("含有", 实参, 2)
    容器, 项 = 实参
    if isinstance(容器, dict):
        return 项 in 容器
    if isinstance(容器, (list, str)):
        return 项 in 容器
    raise RuntimeError("星语：含有() 不认 " + fmt(容器) + " 这种类型")


def _范围(实参):
    """范围(n) / 范围(a, b) / 范围(a, b, 步长) —— 返回列表"""
    _要参数("范围", 实参, 1, 3)
    for x in 实参:
        if isinstance(x, bool) or not isinstance(x, int):
            raise RuntimeError("星语：范围() 只收整数，你给了 " + fmt(x))
    if len(实参) == 1:
        return list(range(实参[0]))
    if len(实参) == 2:
        return list(range(实参[0], 实参[1]))
    if 实参[2] == 0:
        raise RuntimeError("星语：范围() 的步长不能是 0")
    return list(range(实参[0], 实参[1], 实参[2]))


# ---------------- Step 10：文件读写 + 文本处理 ----------------
# ★ 这一批是「自举」的前置条件：
#   要读进源码 → 得有 读文件
#   要把源码切成行 → 得有 按行分 / 切分
#   要判断「这一行像不像数字」→ 得有 取段 / 是数字
#   路径都是相对当前工作目录（跑 python 的那个目录）。


def _要文本(名字, 值):
    if not isinstance(值, str):
        raise RuntimeError("星语：内置函数 " + 名字 + " 要的是文本，你给的是 " + fmt(值))
    return 值


def _读文件(实参):
    _要参数("读文件", 实参, 1)
    路径 = _要文本("读文件", 实参[0])
    if not os.path.exists(路径):
        raise RuntimeError(
            "星语：找不到文件 " + _带引号(路径)
            + "（当前目录是 " + os.getcwd() + "）"
        )
    try:
        with open(路径, "r", encoding="utf-8") as f:
            return f.read().lstrip("\ufeff")     # 顺手吃掉 BOM
    except UnicodeDecodeError:
        raise RuntimeError(
            "星语：文件 " + _带引号(路径) + " 不是 UTF-8 编码，读不进"
        )


def _写文件(实参):
    _要参数("写文件", 实参, 2)
    路径 = _要文本("写文件", 实参[0])
    内容 = 实参[1] if isinstance(实参[1], str) else fmt(实参[1])
    try:
        with open(路径, "w", encoding="utf-8") as f:
            f.write(内容)
    except OSError as e:
        raise RuntimeError("星语：写不进 " + _带引号(路径) + " —— " + str(e))
    return len(内容)                             # 返回写了几个字符，方便确认


def _追加文件(实参):
    _要参数("追加文件", 实参, 2)
    路径 = _要文本("追加文件", 实参[0])
    内容 = 实参[1] if isinstance(实参[1], str) else fmt(实参[1])
    try:
        with open(路径, "a", encoding="utf-8") as f:
            f.write(内容)
    except OSError as e:
        raise RuntimeError("星语：写不进 " + _带引号(路径) + " —— " + str(e))
    return len(内容)


def _文件在吗(实参):
    _要参数("文件在吗", 实参, 1)
    return os.path.exists(_要文本("文件在吗", 实参[0]))


def _按行分(实参):
    _要参数("按行分", 实参, 1)
    return _要文本("按行分", 实参[0]).splitlines()


def _切分(实参):
    _要参数("切分", 实参, 2)
    文本 = _要文本("切分", 实参[0])
    分隔 = _要文本("切分", 实参[1])
    if 分隔 == "":
        raise RuntimeError(
            "星语：切分() 的分隔符不能是空文本（想按单个字符拆，用 字符们()）"
        )
    return 文本.split(分隔)


def _取段(实参):
    """取段(文本, 起) / 取段(文本, 起, 止) —— 支持负数，跟列表下标一个规矩"""
    _要参数("取段", 实参, 2, 3)
    原 = 实参[0]
    if not isinstance(原, (str, list)):
        raise RuntimeError("星语：取段() 只能用在文本或列表上，这是 " + fmt(原))
    for i in range(1, len(实参)):
        if isinstance(实参[i], bool) or not isinstance(实参[i], int):
            raise RuntimeError("星语：取段() 的位置得是整数，你给了 " + fmt(实参[i]))
    if len(实参) == 2:
        return 原[实参[1]:]
    return 原[实参[1]:实参[2]]


def _排成(实参):
    _要参数("排成", 实参, 2)
    列表 = 实参[0]
    分隔 = _要文本("排成", 实参[1])
    if not isinstance(列表, list):
        raise RuntimeError("星语：排成() 的第一个参数得是列表，这是 " + fmt(列表))
    return 分隔.join(层 if isinstance(层, str) else fmt(层) for 层 in 列表)


def _去空白(实参):
    _要参数("去空白", 实参, 1)
    return _要文本("去空白", 实参[0]).strip()


def _换成(实参):
    _要参数("换成", 实参, 3)
    原 = _要文本("换成", 实参[0])
    找 = _要文本("换成", 实参[1])
    换成啥 = _要文本("换成", 实参[2])
    return 原.replace(找, 换成啥)


def _字符们(实参):
    _要参数("字符们", 实参, 1)
    return list(_要文本("字符们", 实参[0]))


def _是数字(实参):
    """整个文本是不是一串数字（允许开头一个负号、一个小数点）"""
    _要参数("是数字", 实参, 1)
    s = _要文本("是数字", 实参[0])
    if not s:
        return False
    头 = 1 if s[0] in "+-" else 0
    见过点 = False
    有数字 = False
    for ch in s[头:]:
        if ch.isdigit():
            有数字 = True
        elif ch == "." and not 见过点:
            见过点 = True
        else:
            return False
    return 有数字


def _类型(实参):
    """返回一个描述类型的文本。
    ★ 写自举代码时必需 —— 解释器要不断问“这个值是数字、文本还是列表？”
      星语原本没有任何办法回答这个问题。"""
    _要参数("类型", 实参, 1)
    v = 实参[0]
    if v is None:
        return "空"
    if isinstance(v, bool):          # ★ 必须在 int 前面：Python 里 bool 是 int 的子类
        return "布"
    if isinstance(v, (int, float)):
        return "数"
    if isinstance(v, str):
        return "文"
    if isinstance(v, list):
        return "表"
    if isinstance(v, dict):
        return "典"
    if isinstance(v, Func):
        return "函数"
    if isinstance(v, 内建):
        return "内置"
    return "别的"


# ---------------- Step 14：标准输入 ----------------
# ★ 没有这两个，星语只能算「批处理脚本」。
#    读文件 / 写文件 已经很全了，但「程序跑起来跟人说话」是另一回事。

def _读一行(实参):
    """读一行标准输入，返回去掉换行的文本。读到结尾返回 空。

        名字 = 读一行()
        名字 = 读一行("你叫啥？")     ← 先打提示再读（提示不换行、不等刷新）
    """
    _要参数("读一行", 实参, 0, 1)
    if 实参:
        提示 = 实参[0] if isinstance(实参[0], str) else fmt(实参[0])
        sys.stdout.write(提示)
        sys.stdout.flush()                 # ★ 不刷新的话，提示会卡在缓冲区里，
    #                                         程序先卡在等输入 —— 用户以为死机了
    行 = sys.stdin.readline()
    if 行 == "":
        return None                        # EOF：让程序能用「如果 行 == 空」判断输入完了
    return 行.rstrip("\r\n")               # 顺手把 Windows 的 \r\n 也吃了


def _读全部(实参):
    """一口气读完剩下的所有输入。管道/重定向时好用：

        cat 数据.txt | python starlang.py 统计.star
    """
    _要参数("读全部", 实参, 0)
    return sys.stdin.read()


def _整除(实参):
    """整除。★ 为什么非得有这个？

    星语只有 `/`，而 `/` 算出来是小数：7 / 2 = 3.5。
    可下标必须得是整数 —— 写二分查找时算个中点就撞上了：

        中 = (低 + 高) / 2       ← 3.5，拿去当下标直接报错
        中 = 整除(低 + 高, 2)    ← 写标准库时才发现的缺口

    这事挺有意思：语言看着什么都有了，一写库就露馅。
    """
    _要参数("整除", 实参, 2)
    a, b = 实参[0], 实参[1]
    for x in (a, b):
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise RuntimeError("星语：整除() 只收数字，你给了 " + fmt(x))
    if b == 0:
        raise RuntimeError("星语：整除的除数不能是 0")
    return a // b


def _取整(实参):
    """去掉小数部分（向零取整，跟大多数语言的强制转换一样）

        取整(3.9)  -> 3
        取整(-3.9) -> -3        ← 注意不是 -4，不是四舍五入
    """
    _要参数("取整", 实参, 1)
    v = 实参[0]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise RuntimeError("星语：取整() 只收数字，你给了 " + fmt(v))
    return int(v)


内建函数 = {
    "长度": _长度, "len": _长度,
    "追加": _追加, "push": _追加,
    "弹出": _弹出, "pop": _弹出,
    "键们": _键们, "keys": _键们,
    "值们": _值们, "values": _值们,
    "含有": _含有, "has": _含有,
    "范围": _范围, "range": _范围,
    "读文件": _读文件, "读檔": _读文件, "read": _读文件,
    "写文件": _写文件, "write": _写文件,
    "追加文件": _追加文件, "append": _追加文件,
    "文件在吗": _文件在吗, "exists": _文件在吗,
    "按行分": _按行分, "lines": _按行分,
    "切分": _切分, "split": _切分,
    "取段": _取段, "slice": _取段,
    "排成": _排成, "join": _排成,
    "去空白": _去空白, "strip": _去空白,
    "换成": _换成, "replace": _换成,
    "字符们": _字符们, "chars": _字符们,
    "是数字": _是数字, "isnum": _是数字,
    "类型": _类型, "type": _类型,
    "读一行": _读一行, "readline": _读一行,
    "读全部": _读全部, "readall": _读全部,
    "整除": _整除, "div": _整除, "idiv": _整除,
    "取整": _取整, "int": _取整, "trunc": _取整,
}


class ReturnSignal(Exception):
    """「返回」要一口气穿透好几层执行（iframe里层层的块、if、while）。
    用异常做最省事 —— 这不是报错，是一种内部信号，谁调用谁接住。"""

    def __init__(self, value):
        self.value = value


class BreakSignal(Exception):
    """「跳出」的信号。为什么不用返回值？

    因为 跳出 可能埋在好几层里：

        只要 条件
            如果 x > 3
                尝试 { 跳出 } 出错 错 { … }

    层层 return 上去太繁琐，直接抛穿最干净 —— 只被 while 接住。
    跳出去的时候顺手带上栈信息，好让报错指到对的行。
    """


class ContinueSignal(Exception):
    """「继续」的信号 —— 跟 BreakSignal 一个道理，只是接住后不退出循环。"""


# ---- Step 7：运行期钩子 ----
# 函数名 -> {"之前": [Func...], "之后": [Func...]}
钩子表 = {}
_钩子栈 = []          # 正在跑的钩子（防钩子套钩子自己把自己转死）

# ---- Step 8：宏 ----
# 名字 -> ([参数名...], 体语句列表)
宏定义表 = {}
_宏深度 = [0]         # 用 list 装是因为闭包/函数里要能改


def 换(node, 替换表):
    """把 AST 里的参数名换成实参的 AST。

    ★ 只换【名字】，不求值 —— 这就是宏和函数的根本差别。
    """
    if isinstance(node, list):
        return [换(x, 替换表) for x in node]
    if not isinstance(node, tuple):
        return node
    # ★ 遇到块就走「语句表」那条路 —— 否则 `如果 条件 { 动作 }` 里
    #   那个 `动作` 会被当成表达式处理，块参数就摊不平了。
    if node[0] == "block":
        return ("block", 换语句表(node[1], 替换表))
    if node[0] == "var" and node[1] in 替换表:
        实 = 替换表[node[1]]
        if isinstance(实, tuple) and 实[0] == "block":
            raise RuntimeError(
                "星语：宏参数「" + node[1] + "」传的是 { 语句块 }，"
                "但宏体这里拿它当表达式用 —— 块只能放在语句位置"
            )
        return 实
    # ★ 赋值号【左边】也可能是宏参数（"交换"这类宏全靠这个）。
    #   注意 assign 节点的左边存的是裸字符串，不是 ("var", 名字)，
    #   所以上面那条 var 分支抓不到它，得单独认一次。
    if node[0] == "assign" and node[1] in 替换表:
        实 = 替换表[node[1]]
        if not (isinstance(实, tuple) and 实[0] == "var"):
            raise RuntimeError(
                "星语：宏参数「" + node[1] + "」被放在了赋值号左边，"
                "那里只能传一个【变量名】进来"
            )
        return ("assign", 实[1], 换(node[2], 替换表))
    return tuple(换(x, 替换表) for x in node)


def 换语句表(语句表, 替换表):
    """换一个语句列表。★ 块参数在【单独占一条语句】时会被摊平（splice）进去，
    而不是嵌成一个块 —— 这样宏展开的行为才跟“把代码倒进来”一致。"""
    结果 = []
    for s in 语句表:
        if (isinstance(s, tuple) and s[0] == "expr"
                and isinstance(s[1], tuple) and s[1][0] == "var"
                and s[1][1] in 替换表):
            实 = 替换表[s[1][1]]
            if isinstance(实, tuple) and 实[0] == "block":
                结果.extend(换语句表(实[1], 替换表))      # ← 摊平
            else:
                结果.append(("expr", 实))
            continue
        结果.append(换(s, 替换表))
    return 结果


# ═══════════════════════════════════════════════════════════
# 宏卫生化 Hygiene（Step 8.5）
# ═══════════════════════════════════════════════════════════
# 不卫生的宏长这样：
#
#     宏 交换(a, b) {
#         临时 = a
#         a = b
#         b = 临时      ← 如果调用者自己也有个「临时」，就被踩了
#     }
#
#     临时 = 999
#     交换(x, 临时)     ← 展开后 b = 临时 取到的是宏自己的中间值！
#
# 经典解法叫 gensym（generate symbol）：
#   ★ 宏体【自己声明】的局部变量，展开时统统换成一个绝不会撞的名字。
#   撞不上，就卫生了。
#
# 注意这里只做了「一半」卫生 —— 这是【故意的】：
#   · 宏体局部变量  → 改名隔离        （防止宏踩调用者）
#   · 宏体的自由变量 → 仍然看调用者环境（这正是不建新环境的意义）
#
# 后一半不能动，否则 demo9 的「宏能看到调用者的变量」就没了。

_gensym = [0]          # 用 list 装是因为要能就地改


def 收集局部绑定(语句们, 结果=None):
    """找出这段宏体自己【声明】了哪些名字（赋值左边 / 函数名 / 出错变量）。

    ★ 只收集「宏体自己造出来的名字」——参数名要留给 换() 去做替换，
      所以调用处会把参数名减掉。
    """
    if 结果 is None:
        结果 = set()
    for s in 语句们:
        if not isinstance(s, tuple):
            continue
        k = s[0]

        if k == "assign":
            结果.add(s[1])

        elif k == "funcdef":
            结果.add(s[1])
            收集局部绑定(s[3][1], 结果)

        elif k == "try":
            结果.add(s[2])                 # 出错块里那个变量名
            收集局部绑定(s[1][1], 结果)
            收集局部绑定(s[3][1], 结果)

        elif k == "block":
            收集局部绑定(s[1], 结果)

        elif k == "if":
            收集局部绑定(s[2][1], 结果)
            if s[3] is not None:
                if s[3][0] == "if":
                    收集局部绑定([s[3]], 结果)     # 否则如果 → 又是一条 if
                else:
                    收集局部绑定(s[3][1], 结果)

        elif k == "while":
            收集局部绑定(s[2][1], 结果)

        elif k == "labeled":
            收集局部绑定([s[2]], 结果)

        # 宏名住在一张全局表里，不能改名 —— 跳过（macrodef / macro 都不收）
    return 结果


def 重命名(node, 改名表):
    """把 AST 里出现的【名字】按表换掉。

    ★ 跟 换() 的区别：
        换()   —— 拿一整颗子 AST 把参数节点【顶掉】（形状会变）
        重命名 —— 只改名字字符串（形状一点都不动）
    """
    if isinstance(node, list):
        return [重命名(x, 改名表) for x in node]
    if not isinstance(node, tuple):
        return node

    k = node[0]

    if k == "block":
        return ("block", [重命名(s, 改名表) for s in node[1]])

    if k == "var":
        return (k, 改名表.get(node[1], node[1]))

    if k == "assign":
        return (k, 改名表.get(node[1], node[1]), 重命名(node[2], 改名表))

    if k == "funcdef":
        # ★ 函数名和参数名都跟着改 —— 内层用同一个新名字依然自洽，
        #   因为星语/ Python 的作用域规则本来就是「内层遮蔽外层」。
        return (k,
                改名表.get(node[1], node[1]),
                [改名表.get(p, p) for p in node[2]],
                重命名(node[3], 改名表))

    if k == "try":
        return (k,
                重命名(node[1], 改名表),
                改名表.get(node[2], node[2]),
                重命名(node[3], 改名表))

    if k in ("register", "unregister"):
        # 目标是【函数名】，也得跟着改（它指向的是上面那个 funcdef）
        return (k, node[1],
                改名表.get(node[2], node[2]),
                改名表.get(node[3], node[3]))

    if k == "labeled":
        # ★ 标号是「插入锚点」，不是变量 —— 绝对不能改名
        return (k, node[1], 重命名(node[2], 改名表))

    return tuple(重命名(x, 改名表) for x in node)


def 展开宏(名字, 实参, 定义表=None):
    """宏展开的唯一入口。★ 解释器和编译器都走这里，两边行为必然一致。

    定义表 为空时用解释器那张全局表；编译器会传自己的表进来
    （它是编译期展开，表不能跟运行时混）。

    顺序很关键：
        ① 先给宏体的局部变量改名（卫生化）
        ② 再做参数替换（换语句表）
    反过来的话，实参里的同名字符串会被 ① 一起改掉，那就错了。
    """
    if 定义表 is None:
        定义表 = 宏定义表

    if 名字 not in 定义表:
        raise RuntimeError(
            "星语：宏「" + 名字 + "」还没定义 —— 宏定义要写在调用之前"
        )
    if _宏深度[0] > MAX_MACRO_DEPTH:
        raise RuntimeError(
            "星语：宏套得太深了（超过 " + str(MAX_MACRO_DEPTH)
            + " 层）—— 是不是宏体里又调了自己？"
        )

    参数名, 体 = 定义表[名字]
    if len(实参) != len(参数名):
        raise RuntimeError(
            "星语：宏「" + 名字 + "」要 " + str(len(参数名))
            + " 个参数，你给了 " + str(len(实参)) + " 个"
        )

    # ---- ① 卫生化：宏体自己的局部变量换唯一名字 ----
    局部 = 收集局部绑定(体) - set(参数名)
    if 局部:
        _gensym[0] += 1
        后缀 = "#" + str(_gensym[0])
        改名表 = {n: n + 后缀 for n in 局部}
        体 = [重命名(s, 改名表) for s in 体]

    # ---- ② 参数替换 ----
    return 换语句表(体, dict(zip(参数名, 实参)))


def 展开所有宏(语句们):
    """把整棵树里的宏调用全部展开掉（原地替换）。

    ★★ 为什么要做成「解析后统一展开」，而不是「执行时边跑边展开」？

        宏是【编译期】的东西：它决定的是「生成什么代码」，不是「运行时算什么」。
        如果解释器非等到执行那一刻才展开，就会跟编译器/VM 走上两条路 ——

            宏 说两遍(x) { 打印 x }
            如果 假 { 说两遍({ 一堆代码 }) }     ← 参数类型错了

        编译器在这个分支还没跑就直接报错了（它在展开阶段就看完了全树），
        而运行时的解释器根本走不到那条分支，于是「悄悄放过」。

        差分测试就是这么把这个不一致抓出来的。

    ★ 顺带一个好处：展开一次、跑多少次都行 —— 循环里调一万次宏也只展开一次。

    编译器/VM 那边是边编译边展开，但效果等价（它们也会走遍所有分支）。
    """
    def 搬行号(旧, 新):
        """★ 造了新节点，就得把行号搬过去。

        语句行表 是按 id(语句) 查的。这里凡是重建节点的地方（if/while/
        funcdef/try/block/labeled）id 全变了 —— 不搬的话运行时查不到行号，
        报错就变成「光秃秃一句话，不知道哪一行」。差分测试抓到的。
        """
        行 = 语句行表.get(id(旧))
        if 行:
            语句行表[id(新)] = 行
        return 新

    结果 = []
    for s in 语句们:
        if not isinstance(s, tuple):
            结果.append(s)
            continue
        k = s[0]

        if k == "macrodef":
            # 登记定义 + 原样保留（执行到它时只是再登记一次，无害）
            宏定义表[s[1]] = (s[2], s[3][1])
            结果.append(s)

        elif k == "macro":
            展开 = 展开宏(s[1], s[2])
            # 展开出来的语句要【继承调用点的行号】
            行 = 语句行表.get(id(s))
            if 行:
                for 新句 in 展开:
                    语句行表[id(新句)] = 行
            结果.extend(展开所有宏(展开))        # 宏里还有宏 → 继续

        elif k == "funcdef":
            结果.append(搬行号(s, ("funcdef", s[1], s[2],
                                 ("block", 展开所有宏(s[3][1])))))

        elif k == "block":
            结果.append(搬行号(s, ("block", 展开所有宏(s[1]))))

        elif k == "if":
            假 = s[3]
            if 假 is None:
                假 = None
            elif 假[0] == "if":
                假 = 展开所有宏([假])[0]
            else:
                假 = ("block", 展开所有宏(假[1]))
            结果.append(搬行号(s, ("if", s[1], ("block", 展开所有宏(s[2][1])),
                                 假)))

        elif k == "while":
            结果.append(搬行号(s, ("while", s[1],
                                 ("block", 展开所有宏(s[2][1])))))

        elif k == "labeled":
            结果.append(搬行号(s, ("labeled", s[1], 展开所有宏([s[2]])[0])))

        elif k == "try":
            结果.append(搬行号(s, ("try", ("block", 展开所有宏(s[1][1])), s[2],
                                 ("block", 展开所有宏(s[3][1])))))

        else:
            结果.append(s)
    return 结果


def 调函数(f, 实参):
    """真止调一个函数。★ 这个函数【不看钩子表】——
    正因为如此，钩子自己不会再被套一层，不会无端递归。"""
    if len(实参) != len(f.params):
        raise RuntimeError(
            "星语：函数「" + f.name + "」需要 " + str(len(f.params))
            + " 个参数，你给了 " + str(len(实参)) + " 个"
        )
    # ★ 核心：新环境的爸爸，是「函数定义时的环境」—— 不是调用处的环境！
    #   这一个选择，就决定了它是「词法作用域」，也决定了闭包能不能用。
    新环境 = Environment(f.closure)
    for p, v in zip(f.params, 实参):
        新环境.define(p, v)                # 参数直接住进这一层
    try:
        execute(f.body, 新环境)
        return None                        # 没碰到「返回」→ 返回空
    except ReturnSignal as r:
        return r.value                     # 碰到了 → 把值带走


def 带钩子调用(f, 实参):
    """按「之前钩子 → 函数本体 → 之后钩子」的顺序跑一道。

    这就是所谓的【中间件 / 环绕通知】：
        请求  → 中间件一 → 中间件二 → 真函数 → 中间件二 → 中间件一 → 响应
    只不这里只管“进去之前”和“回来之后”，没有能力改掉返回值。
    """
    if len(_钩子栈) > MAX_HOOK_DEPTH:
        raise RuntimeError(
            "星语：钩子套得太深了（超过 " + str(MAX_HOOK_DEPTH)
            + " 层）—— 是不是钩子里又调了它盯的那个函数？"
        )

    钩子们 = 钩子表.get(f.name, {})

    for h in 钩子们.get("之前", []):
        _钩子栈.append(h.name)
        try:
            调函数(h, list(实参))           # 钩子直接拿到这次的实参
        finally:
            _钩子栈.pop()

    结果 = 调函数(f, 实参)

    for h in 钩子们.get("之后", []):
        _钩子栈.append(h.name)
        try:
            调函数(h, [结果])               # 「之后」拿的是返回值
        finally:
            _钩子栈.pop()

    return 结果


def evaluate(node, env):
    kind = node[0]

    # ---- 叶子节点 ----
    if kind == "num":
        return node[1]
    if kind == "str":                        # Step 6：字面量就是个值，没什么好算的
        return node[1]
    if kind == "bool":                       # Step 11
        return node[1]
    if kind == "null":                       # Step 14
        return None
    if kind == "lambda":                     # Step 16：匿名函数
        # ★ 就是造个 Func 而已 —— 匿名函数跟具名函数在运行时没有半点区别，
        #   区别只在「这个名字有没有人叫得出来」。
        #   核心是 closure 传当前环境 —— 所以匿名函数也能当闭包用。
        return Func("<匿名>", node[1], node[2], env)
    if kind == "ternary":                    # Step 17：三元表达式
        if truthy(evaluate(node[1], env)):
            return evaluate(node[2], env)
        return evaluate(node[3], env)
    if kind == "var":
        try:
            return env.get(node[1])          # ← Step 2：去环境里把值捞出来
        except NameError:
            # ★ Step 9：环境里没这个人，再看是不是内置函数（长度/追加/……）
            if node[1] in 内建函数:
                return 内建(node[1])
            raise

    # ---- 列表 / 字典 / 取下标（Step 9 新增）----
    if kind == "list":
        return [evaluate(x, env) for x in node[1]]
    if kind == "dict":
        return {evaluate(k, env): evaluate(v, env) for k, v in node[1]}
    if kind == "index":
        return 取下标(evaluate(node[1], env), evaluate(node[2], env))

    # ---- 函数调用（Step 4 新增）----
    # ⚠️ 必须在下面「二元节点」之前处理！
    #    因为 ("call", 函数, [参数列表]) 也是三元素，会被误当成二元运算
    if kind == "call":
        callee = evaluate(node[1], env)
        args = [evaluate(a, env) for a in node[2]]
        # ★ Step 9：内置函数直接打给 Python，不经过 Func 那套环境/闭包/钩子
        if isinstance(callee, 内建):
            return 内建函数[callee.名字](args)
        if not isinstance(callee, Func):
            raise RuntimeError("星语：这个东西不是函数，不能加 () 调用它")
        # ★ Step 7：从这里开始不再直接调，而是先查钩子表
        return 带钩子调用(callee, args)

    # ---- 一元节点（两元素 tuple）----
    if len(node) == 2:
        operand = evaluate(node[1], env)
        if kind == "-":
            return -operand
        if kind == "+":
            return +operand
        if kind == "非":                     # Step 11
            return not truthy(operand)
        raise RuntimeError(f"未知的一元运算符 {kind!r}")

    # ---- 且 / 或（Step 11）★ 必须短路 ----
    #   「且」左边假 → 右边【不跑】；「或」左边真 → 右边【不跑】。
    #   这不是优化，是语义：右边可能是个会出错的表达式（除零、下标越界），
    #   短路的意义就是“不必要的时候不去碰它”。
    if kind == "或":
        if truthy(evaluate(node[1], env)):
            return True
        return truthy(evaluate(node[2], env))
    if kind == "且":
        if not truthy(evaluate(node[1], env)):
            return False
        return truthy(evaluate(node[2], env))

    # ---- 二元节点（三元素 tuple）----
    left = evaluate(node[1], env)
    right = evaluate(node[2], env)

    if kind == "+":
        # ★★ Step 6 的一个语言设计决定：只要有一边是文本，就按「拼起来」算
        #
        #   为什么这么选：
        #     星语的 打印 只能吐一个东西，没有 f-string、没有格式化。
        #     如果不能拼字符串，就等于连「第 3 轮」这种话都说不出来，
        #     那字符串就是半残废。
        #
        #   代价（写的时候自己记住）：
        #     "1" + 1   →  "11"      ← 不是 2
        #     1 + 1     →  2         ← 两边都是数字才是算数
        #
        #   这是 JS 的规则，不是 Python 的。Python 会直接报错让你先转类型；
        #   这里选了「方便」，因为这是玩具语言，用户要的是能拼出话来看。
        if isinstance(left, str) or isinstance(right, str):
            return fmt(left) + fmt(right)
        return left + right
    if kind == "-":
        return left - right
    if kind == "*":
        return left * right
    if kind == "/":
        if right == 0:
            raise ZeroDivisionError("星语：除数不能为 0")
        return left / right
    if kind == "%":
        if right == 0:
            raise ZeroDivisionError("星语：取余的除数不能为 0")
        return left % right
    if kind == "**":
        return left ** right
    if kind == "<":
        return left < right
    if kind == ">":
        return left > right
    if kind == "<=":
        return left <= right
    if kind == ">=":
        return left >= right
    if kind == "==":
        return left == right
    if kind == "!=":
        return left != right

    raise RuntimeError(f"未知的节点类型 {kind!r}")


def execute(stmt, env):
    """执行一条语句。注意：语句没有「值」，只干活、只产生副作用。"""
    # ★ 走到哪条语句就把「当前行」改到哪行。
    #   这样任何一条语句里炸了（哪怕炸在表达式深处），报出来都是对的那一行。
    行 = 语句行表.get(id(stmt))
    if 行:
        当前行[0] = 行

    kind = stmt[0]

    if kind == "print":
        print("   " + fmt(evaluate(stmt[1], env)))
        return None

    if kind == "assign":
        name = stmt[1]
        value = evaluate(stmt[2], env)    # 先算右边（此刻左边还拿着旧值）
        env.set(name, value)              # 把结果放进环境，覆盖旧的
        return None

    # ---- 改下标：a[0] = 值（Step 9 新增）----
    if kind == "setindex":
        容器 = evaluate(stmt[1], env)
        下标 = evaluate(stmt[2], env)
        值 = evaluate(stmt[3], env)
        if isinstance(容器, dict):
            容器[下标] = 值
            return None
        if isinstance(容器, list):
            容器[_正规下标(容器, 下标)] = 值
            return None
        raise RuntimeError("星语：" + fmt(容器) + " 这东西不能用 [] 改内容")

    if kind == "expr":
        return evaluate(stmt[1], env)     # 表达式有值，顺手返回给 REPL 用

    # ---- 标号与插入（Step 5 新增）----
    if kind == "labeled":
        return execute(stmt[2], env)      # 标号只是个铭牌，不影响执行
    if kind == "insert":
        # 正常情况下织入阶段已经把它抹掉了；到这儿说明织入没跑
        raise RuntimeError("星语：「插入」应该在跑之前就被织入掉，不该留到这里")

    # ---- 运行期钩子（Step 7 新增）----
    if kind == "register":
        时机, 目标名, 钩子名 = stmt[1], stmt[2], stmt[3]
        try:
            目标 = env.get(目标名)
        except NameError:
            raise RuntimeError(
                "星语：「注册" + 时机 + "" + 目标名 + "」找不到这个函数 —— "
                "注册 要写在它定义之后"
            )
        if not isinstance(目标, Func):
            raise RuntimeError("星语：「" + 目标名 + "」不是函数，钩子只能盯函数")
        try:
            钩子 = env.get(钩子名)
        except NameError:
            raise RuntimeError(
                "星语：「注册」用的钩子函数「" + 钩子名 + "」还没定义"
            )
        if not isinstance(钩子, Func):
            raise RuntimeError("星语：钩子「" + 钩子名 + "」不是函数")
        钩子表.setdefault(目标名, {}).setdefault(时机, []).append(钩子)
        print("   · 已在「" + 目标名 + "」的" + 时机 + "挂上钩子「" + 钩子名 + "」")
        return None

    if kind == "unregister":
        时机, 目标名, 钩子名 = stmt[1], stmt[2], stmt[3]
        列 = 钩子表.get(目标名, {}).get(时机, [])
        for i, h in enumerate(列):
            if h.name == 钩子名:
                del 列[i]
                print("   · 已拔掉「" + 目标名 + "」的" + 时机
                      + "钩子「" + 钩子名 + "」")
                return None
        # ★ 拔不掉就报出来，不静默 —— 默默失败比报错难查一百倍
        raise RuntimeError(
            "星语：「" + 目标名 + "」的" + 时机 + "没挂着钩子「" + 钩子名
            + "」，拔不掉（先确认名字对不对、是不是真的很早以前就已经拔过了）"
        )

    # ---- 复合赋值（Step 17 新增）----
    if kind == "opassign":
        # ★ 不另写一套运算逻辑 —— 直接把「x += e」当成「x = x + e」求值。
        #   这样字符串拼接、除零报错、行号定位…… 全部自动跟普通运算一模一样，
        #   三个实现不可能在这里分叉。
        env.set(stmt[1], evaluate((stmt[2], ("var", stmt[1]), stmt[3]), env))
        # ★ 必须返回 None：跟普通赋值一样，赋值【不是】表达式，
        #   顶层不该回显一个「= 15」。编译器/VM 那边天生不回显，
        #   这里要是把 set() 的返回值漏出去，差分测试立刻抓包。
        return None

    # ---- 块与控制流（Step 3 新增）----
    if kind == "block":
        return run_program(stmt[1], env)  # 块里就是一串语句，和“整个程序”一样

    if kind == "if":
        if truthy(evaluate(stmt[1], env)):
            return execute(stmt[2], env)  # 条件真 → 跑真块
        if stmt[3] is not None:           # 有 else 才跑
            return execute(stmt[3], env)
        return None

    if kind == "while":
        guard = 0
        while truthy(evaluate(stmt[1], env)):   # 每转一圈重新算一次条件
            # ★ 圈数先加：下面的「继续」会跳过循环体剩下的部分，
            #   如果计数器放在后面，一个全是「继续」的循环就永远涨不了数 ——
            #   熔断丝成了摆设，工具直接卡死。
            guard += 1
            if guard > MAX_LOOP:
                raise RuntimeError(
                    "星语：循环跑了 " + str(MAX_LOOP) + " 次还没停，先夹了（死循环？）"
                )
            try:
                execute(stmt[2], env)
            except BreakSignal:
                break                       # 「跳出」→ 整个循环结束
            except ContinueSignal:
                continue                    # 「继续」→ 直接看下一圈条件
        return None

    # ---- 循环控制（Step 14）----
    # 这两条本来就不该被跑到：检查跳出() 已经保证它们套在循环里，
    # 而套在循环里的就一定被上面的 while 接住。漏到这里就是实现有 bug，
    # 报出来比默默往下跑强。
    if kind == "break":
        raise BreakSignal()
    if kind == "continue":
        raise ContinueSignal()

    # ---- 函数（Step 4 新增）----
    if kind == "funcdef":
        # ★ 关键：把「当前环境」打包进去一起存起来 —— 这就是闭包
        env.define(stmt[1], Func(stmt[1], stmt[2], stmt[3], env))
        return None

    if kind == "return":
        # 抛个信号出去，让它一路穿到最外层那个 call 去
        raise ReturnSignal(evaluate(stmt[1], env) if stmt[1] is not None else None)

    # ---- 宏（Step 8 新增）----
    if kind == "macrodef":
        宏定义表[stmt[1]] = (stmt[2], stmt[3][1])
        print("   · 已定义语法「" + stmt[1] + "(" + ", ".join(stmt[2]) + ")」")
        return None

    if kind == "macro":
        # ★★ 关键：在【调用者的环境】里跑，不是新环境。
        #    这正是“宏不是函数”的地方 —— 展开的代码能直接看到调用者的变量。
        #    卫生化（宏体局部变量改名）在 展开宏() 里做，解释器/编译器共用。
        _宏深度[0] += 1
        try:
            return run_program(展开宏(stmt[1], stmt[2]), env)
        finally:
            _宏深度[0] -= 1

    # ---- 错误处理（Step 12 新增）----
    if kind == "try":
        体, 错误名, 处理 = stmt[1], stmt[2], stmt[3]
        try:
            return execute(体, env)
        except ReturnSignal:
            # ★★★ 绝对不能吃：这是「返回」，不是出错
            raise
        except (BreakSignal, ContinueSignal):
            # ★ 同理：跳出/继续 也是「控制流信号」，不是错误。
            #   它们必须能穿过 尝试/出错 往外冒，否则：
            #       只要 真
            #           尝试 { 跳出 }
            #           出错 错 { … }
            #   就永远退不出循环（编译器版用的 Python break，穿得过去）。
            raise
        except RecursionError:
            # 递归太深也算错误，但不能把它硬当成普通错误（可能继续爆）
            子 = Environment(env)
            子.define(错误名, "递归太深了（是不是忘了让递归停下来？）")
            return execute(处理, 子)
        except Exception as e:
            # ★ 新环境的爸爸是【当前环境】—— 所以出错块里能读到外面定义了啥
            #   改写报错() 在这儿也过一遂：程序自己 catch 到的也是新说法
            子 = Environment(env)
            子.define(错误名, 最终文案(e))
            return execute(处理, 子)

    raise RuntimeError(f"未知的语句类型 {kind!r}")


def truthy(v):
    """什么叫“真”？0 是假，空字符串 / 空列表 / 空字典也是假，其它都算真。"""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, (str, list, dict)):
        return len(v) > 0
    return True


def run_program(stmts, env, echo=False):
    """按顺序执行每一条语句。语言就是“一条一条来”，没别的玄机。"""
    last = None
    for stmt in stmts:
        result = execute(stmt, env)
        if result is not None:
            last = result
            if echo:
                print("   = " + fmt(result))
    return last


# ═══════════════════════════════════════════════════════════# ④ 织入 Weave —— 把「插入」指令缝进函数体（Step 5 新增）
# ═══════════════════════════════════════════════════════
# 这一步发生在【执行之前】，改的是 AST，不是运行时。
# 所以织入完之后，跟「一开始就写在源码里」**没有任何区别** ——
# 但它不需要你去改原函数那几行，这就是它的全部价值。
#
# 关键设计：所有锚点最后都归成同一个动作 ——
#
#     「往某个语句列表的第 N 个空位里塞一捰语句」
#
#   开头       = 第 0 个空位
#   第 k 条之后 = 第 k 个空位
#   结尾       = 最后一个空位
#   标号之后    = 那条语句的位置 + 1
#
# 一套机制，四种写法。
#
# ⚠️ 一个必须说清楚的边界：插入只认【最外层】写的指令。
#    因为函数体里再藏一个插入，就得在两套嵌套的列表里各自算位置，
#    那是另一个量级的东西了 —— 先把简单的做对，比先做全的靠谱。


def 织入(程序):
    """把最外层的「插入」指令全部应用掉。返回一段给人看的报告。"""
    指令 = [s for s in 程序 if isinstance(s, tuple) and s[0] == "insert"]
    程序[:] = [s for s in 程序 if not (isinstance(s, tuple) and s[0] == "insert")]
    if not 指令:
        return []

    函数体 = {}          # 函数名 -> 它的语句列表（就是这个 list 对象本身）
    标号 = {}            # 标号名 -> (它所在的语句列表, 第几条)

    def 登记列表(语句表):
        for i, s in enumerate(语句表):
            if isinstance(s, tuple) and s[0] == "labeled":
                标号[s[1]] = (语句表, i)
            登记节点(s)

    def 登记节点(s):
        if not isinstance(s, tuple):
            return
        k = s[0]
        if k == "labeled":
            登记节点(s[2])
        elif k == "funcdef":
            函数体[s[1]] = s[3][1]
            登记列表(s[3][1])
        elif k == "block":
            登记列表(s[1])
        elif k == "if":
            登记节点(s[2])
            if s[3] is not None:
                登记节点(s[3])
        elif k == "while":
            登记节点(s[2])

    登记列表(程序)

    # 计划：{(哪个列表, 第几个空位): [要插进去的语句...]}
    计划 = {}
    列表池 = {}

    def 记计划(目标列表, 空位, 语句们):
        列表池[id(目标列表)] = 目标列表
        计划.setdefault((id(目标列表), 空位), []).extend(语句们)

    报告 = []
    for s in 指令:
        锚 = s[1]
        体 = s[2][1]          # ← 取 block 里那串语句，不是 block 这个壳子
        种类 = 锚[0]

        if 种类 == "label":
            名字 = 锚[1]
            if 名字 not in 标号:
                raise NameError(
                    "星语：「插入 标号 " + 名字 + "」找不到这个标号 —— "
                    "要在某条语句后面写  #@" + 名字 + "  才行"
                )
            目标列表, 第几条 = 标号[名字]
            记计划(目标列表, 第几条 + 1, 体)
            报告.append("标号「" + 名字 + "」之后 ← " + str(len(体)) + " 条")
            continue

        fn = 锚[1]
        if fn not in 函数体:
            raise NameError(
                "星语：「插入 " + fn + "」找不到这个函数 —— "
                "插入只能针对文件里定义过的函数"
            )
        目标列表 = 函数体[fn]

        if 种类 == "head":
            记计划(目标列表, 0, 体)
            报告.append("函数「" + fn + "」开头 ← " + str(len(体)) + " 条")
        elif 种类 == "tail":
            记计划(目标列表, len(目标列表), 体)
            报告.append("函数「" + fn + "」结尾 ← " + str(len(体)) + " 条")
        else:
            n = 锚[2]
            if n < 0 or n > len(目标列表):
                raise IndexError(
                    "星语：函数「" + fn + "」只有 " + str(len(目标列表))
                    + " 条语句，插不到第 " + str(n) + " 条之后"
                )
            记计划(目标列表, n, 体)
            报告.append("函数「" + fn + "」第 " + str(n) + " 条之后 ← "
                        + str(len(体)) + " 条")

    # 一次性重建每个被点名的列表。
    # ★ 空位号全是按【织入前】那个列表算的，所以必须“一次重建” ——
    #   一条一条插的话，第二处的位置就被第一处挤歪了。
    for 列表号, 目标列表 in 列表池.items():
        本列表 = {位: 语 for (号, 位), 语 in 计划.items() if 号 == 列表号}
        新 = []
        for i in range(len(目标列表) + 1):
            新.extend(本列表.get(i, []))       # 先把插进来的放进去
            if i < len(目标列表):
                新.append(目标列表[i])          # 再接上原本就在这儿的
        目标列表[:] = 新

    return 报告


# ═══════════════════════════════════════════════════════# 驱动：把三步串起来
# ═══════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════
# Step 14 ①：跳出 / 继续 的合法性静态检查
# ═══════════════════════════════════════════════════════════
def 检查跳出(语句们, 循环深度=0):
    """扫一遍 AST，确认每个「跳出 / 继续」都套在循环里。

    ★★ 为什么非要静态查，明明执行的时候也能发现？

            如果 假
                跳出

        解释器根本跑不到那一行，永远不会报错；
        编译器在编译阶段一步就查得出来，直接报。
        —— 同一个程序，两家说法不一样，差分测试立刻炸。

        而且「跳出写在循环外面」本来就是**写错了**，跟语法错误一个性质：
        越早说越好，别等到某个分支恰好被执行到才骂人。

    ★ 函数定义里的跳出不算外层循环的 —— 换个函数就是新的一层。
      （所以遇到 funcdef 要把深度清零重来）
    """
    for s in 语句们:
        if not isinstance(s, tuple):
            continue
        k = s[0]

        if k in ("break", "continue"):
            if 循环深度 == 0:
                行 = 语句行表.get(id(s))
                词 = "跳出" if k == "break" else "继续"
                开头 = ("[语法错误] 第 " + str(行) + " 行: ") if 行 else "[语法错误] "
                raise SyntaxError(
                    开头 + "「" + 词 + "」得写在循环（只要）里面 —— "
                    "它自己不知道要跳出哪一层"
                )

        elif k == "while":
            检查跳出(s[2][1], 循环深度 + 1)

        elif k == "if":
            检查跳出(s[2][1], 循环深度)
            if s[3] is not None:
                if s[3][0] == "if":
                    检查跳出([s[3]], 循环深度)
                else:
                    检查跳出(s[3][1], 循环深度)

        elif k == "block":
            检查跳出(s[1], 循环深度)

        elif k == "labeled":
            检查跳出([s[2]], 循环深度)

        elif k == "try":
            检查跳出(s[1][1], 循环深度)
            检查跳出(s[3][1], 循环深度)

        elif k == "funcdef":
            检查跳出(s[3][1], 0)          # ★ 函数体重新数

        elif k == "macro":
            # 编译器/VM 是在编译中途才展开宏的，走到这儿说明还没展开过。
            # 那就现场展开一层再查 —— 宏体里的「跳出」也算数。
            # ⚠️ 只有真登记过才展开：解析阶段宏可能还没执行到定义那行，
            #    这时候展开会蹦出「宏还没定义」，把整个编译过程打断
            #    （这坑踩过：4 个 demo 同时红，报的却是「宏还没定义」）。
            if s[1] in 宏定义表:
                try:
                    检查跳出(展开宏(s[1], s[2]), 循环深度)
                except Exception:
                    # 展开本身有错不归这儿管 —— 交给真正的编译器去报，
                    # 它报得比这里准（还能带上宏参数类型那些细节）。
                    pass


# ═══════════════════════════════════════════════════════════
# Step 14 ②：载入 —— 把别的 .star 文件拼进来
# ═══════════════════════════════════════════════════════════
# ★ 设计决定：载入 是【预处理】，不是运行时求值。
#
#   如果做成运行时「跑另一个文件」，三个实现就得各自维护一套
#   「被载入文件的环境该接到哪里」—— 解释器是 Environment、编译器是
#   Python 作用域、VM 是自己的 Environment，接不干净。
#
#   做成「解析前把文本拼进来」以后：
#     · 三个实现天然一致（对 AST 毫无感知）
#     · 被载入文件里定义的函数 / 宏，跟写在同一个文件里完全等价
#     · 想拆分文件就够了，不需要命名空间那套复杂度
#
#   代价：没有命名空间，名字是全局的（跟 Python 的 from x import * 一样）。

import re                                    # noqa: E402

载入行式 = re.compile(r"^([ \t]*)载入[ \t]+[\"']([^\"']+)[\"'][ \t]*$")


def 展开载入(源码, 基准目录=None, 已载=None):
    """把源码里每一行 `载入 "文件.star"` 换成那个文件的全部内容。

    基准目录：相对路径按谁算。跑文件时传文件所在目录，REPL 时传 None（= cwd）。
    已载    ：正在展开的路径栈，用来抓「A 载入 B，B 又载入 A」这种死循环。
    """
    路径栈 = 已载 if 已载 is not None else []
    行们 = 源码.replace("\r\n", "\n").split("\n")
    结果 = []
    for 行 in 行们:
        m = 载入行式.match(行)
        if not m:
            结果.append(行)
            continue

        缩进, 路径 = m.group(1), m.group(2)
        全 = 路径
        if not os.path.isabs(全) and 基准目录:
            全 = os.path.join(基准目录, 路径)
        if not os.path.isfile(全):
            在哪 = ("（找的是 " + 全 + "）") if 基准目录 else ""
            raise SyntaxError(
                "[载入] 找不到文件 " + _带引号(路径) + 在哪
            )

        标记 = os.path.normcase(os.path.abspath(全))
        if 标记 in 路径栈:
            链 = " → ".join([os.path.basename(p) for p in 路径栈] + [路径])
            raise SyntaxError("[载入] 转圈了：" + 链 + "（文件不能自己载入自己）")

        子 = 展开载入(_读文件([全]), 基准目录, 路径栈 + [标记])

        # 注释行也带上缩进：万一 载入 写在块里，注释行不缩进会破坏块的边界
        结果.append(缩进 + "# ──── 载入 " + 路径 + " ────")
        for 子行 in 子.split("\n"):
            结果.append((缩进 + 子行) if 子行.strip() else "")
        结果.append(缩进 + "# ──── " + 路径 + " 结束 ────")
    return "\n".join(结果)


def run(src, flags=(), env=None, echo=False, 基准目录=None):
    """把一段星语源码跑起来，返回最后一个值。

    env       传同一个进来，变量就能跨行记住
    echo      为真时，光秃秃的表达式也会打印出值
    基准目录  载入 "…" 里的相对路径按谁算（跑文件时传文件所在目录）
    """
    if env is None:
        env = Environment()

    # ★ 每次开跑都清空行号表。不清的话上一份程序的旧 AST 被回收后，
    #   新对象可能复用同一个 id，就会查到上辈子那条语句的行号 —— 报错指错行。
    语句行表.clear()
    当前行[0] = 0

    # ①.0 载入：先把「载入 "别的.star"」拼进来。
    #     必须在切词之前 —— 它是纯文本层面的动作，做完之后
    #     整个过程跟「本来就写在一个文件里」没有任何区别。
    if "载入" in src:
        src = 展开载入(src, 基准目录)

    tokens = Lexer(src).tokenize()      # ① 源码 → Token
    if "tokens" in flags:
        print("      Token 流 :", "  ".join(t.name for t in tokens if t.kind != "EOF"))

    stmts = Parser(tokens).parse_program()   # ② Token → 一串语句

    # ②.5 织入：把所有「插入」指令应用到 AST 上（Step 5）
    报告 = 织入(stmts)
    if 报告 and ("tree" in flags or echo):
        print("      插入指令 :")
        for line in 报告:
            print("        · " + line)

    # ②.6 宏展开：★ 在【跑之前】就展开完，跟编译器和 VM 保持一致
    stmts = 展开所有宏(stmts)

    # ②.7 跳出/继续 的合法性：★ 静态查，别等执行到
    #     （详见 检查跳出 的说明：不静态查的话解释器和编译器会不一致）
    检查跳出(stmts)

    if "tree" in flags:
        print("      语法树   :")
        for line in tree_lines(stmts):
            print("        " + line)

    try:
        return run_program(stmts, env, echo)   # ③ 一句一句执行
    except ReturnSignal:
        # 信号一路冒到最外层都没人接住 → 说明「返回」写在了函数外面
        raise SyntaxError("星语：「返回」只能用在一个函数里面")
    except BreakSignal:
        raise SyntaxError("星语：「跳出」只能用在一个循环里面")
    except ContinueSignal:
        raise SyntaxError("星语：「继续」只能用在一个循环里面")
    except SyntaxError:
        # ★ 检查跳出 抛的是 SyntaxError，它自己的消息已经带行号了，别包
        raise
    except Exception as e:
        # ★ 顶层烂掉的也要补行号 + 过文案表 —— VM 那边就是这么干的，
        #   不然同一个错误两边说法不一样（差分测试立刻就能抓到）。
        raise RuntimeError(最终文案(e)) from None


def tree_lines(node):
    """把 AST 画成缩进 ASCII 树，肉眼可读"""
    label, children = node_parts(node)
    lines = [label]
    for i, (edge, child) in enumerate(children):
        is_last = (i == len(children) - 1)
        prefix = "└── " if is_last else "├── "
        pad = "    " if is_last else "│   "
        sub = tree_lines(child)
        lines.append(prefix + (edge + " " if edge else "") + sub[0])
        lines.extend(pad + x for x in sub[1:])
    return lines


def node_parts(node):
    """把节点拆成 (标签, [(边上的说明, 子节点), ...])"""

    # ---- 一整个程序 / 一个块：就是一串语句 ----
    if isinstance(node, list):
        return "程序（" + str(len(node)) + " 条语句）", [("", s) for s in node]

    kind = node[0]

    # ---- 表达式节点 ----
    if kind == "num":
        return "数字 " + fmt(node[1]), []
    if kind == "str":
        return "文本 " + _带引号(node[1]), []
    if kind == "bool":
        return ("真" if node[1] else "假"), []
    if kind == "var":
        return "变量「" + node[1] + "」", []

    # ---- 列表 / 字典 / 下标（Step 9 新增）----
    if kind == "list":
        return ("列表（" + str(len(node[1])) + " 项）",
                [("第" + str(i + 1) + "项", x) for i, x in enumerate(node[1])])
    if kind == "dict":
        kids = []
        for i, (k, v) in enumerate(node[1]):
            kids.append(("键" + str(i + 1), k))
            kids.append(("值" + str(i + 1), v))
        return "字典（" + str(len(node[1])) + " 对）", kids
    if kind == "index":
        return "取下标", [("从", node[1]), ("第几个", node[2])]
    if kind == "setindex":
        return "改下标", [("在", node[1]), ("第几个", node[2]), ("改成", node[3])]

    # ---- 语句节点 ----
    if kind == "print":
        return "打印", [("", node[1])]
    if kind == "assign":
        return "赋值给「" + node[1] + "」", [("", node[2])]
    if kind == "expr":
        return "表达式语句", [("", node[1])]

    # ---- 标号与插入（Step 5 新增）----
    if kind == "labeled":
        return "标号 @" + node[1], [("", node[2])]
    if kind == "insert":
        锚 = node[1]
        if 锚[0] == "label":
            名 = "标号「" + 锚[1] + "」之后"
        elif 锚[0] == "head":
            名 = "函数「" + 锚[1] + "」开头"
        elif 锚[0] == "tail":
            名 = "函数「" + 锚[1] + "」结尾"
        else:
            名 = "函数「" + 锚[1] + "」第 " + str(锚[2]) + " 条之后"
        kids = [("", s) for s in node[2][1]]
        return "插入 → " + 名, kids

    # ---- 运行期钩子（Step 7 新增）----
    if kind == "register":
        return ("注册" + node[1] + "：盯「" + node[2] + "」，用「" + node[3] + "」",
                [])
    if kind == "unregister":
        return ("拔掉" + node[1] + "：盯「" + node[2] + "」，用「" + node[3] + "」",
                [])

    # ---- 宏（Step 8 新增）----
    if kind == "macrodef":
        return ("定义语法「" + node[1] + "(" + ", ".join(node[2]) + ")" + "」",
                [("", node[3])])
    if kind == "macro":
        kids = [("第" + str(i + 1) + "个参数", a) for i, a in enumerate(node[2])]
        return "展开宏「" + node[1] + "」", kids

    # ---- 错误处理（Step 12 新增）----
    if kind == "try":
        return ("尝试（出错叫「" + node[2] + "」）",
                [("试一试", node[1]), ("出错就", node[3])])

    # ---- 块与控制流（Step 3 新增）----
    if kind == "block":
        return "块（" + str(len(node[1])) + " 条语句）", [("", s) for s in node[1]]
    if kind == "if":
        kids = [("条件", node[1]), ("真块", node[2])]
        if node[3] is not None:
            kids.append(("假块", node[3]))
        return "如果", kids
    if kind == "while":
        return "只要条件成立就重复", [("条件", node[1]), ("循环体", node[2])]

    # ---- 函数（Step 4 新增）----
    if kind == "call":
        kids = [("被调用的", node[1])]
        for i, a in enumerate(node[2]):
            kids.append(("第" + str(i + 1) + "个参数", a))
        return "调用", kids
    if kind == "funcdef":
        return ("定义函数「" + node[1] + "(" + ", ".join(node[2]) + ")」",
                [("", node[3])])
    if kind == "return":
        if node[1] is None:
            return "返回（空）", []
        return "返回", [("", node[1])]

    # ---- 运算符节点 ----
    if len(node) == 2:
        return kind + "（一元）", [("", node[1])]
    return kind, [("", node[1]), ("", node[2])]


def _带引号(s):
    """画出语法树时把字符串带上引号，否则分不清 "1" 和数字 1"""
    return '"' + str(s).replace("\\", "\\\\").replace("\n", "\\n") + '"'


def fmt(v):
    """把结果变好看：空显示成「空」，布尔显示成中文，函数显示成 <函数 ...>"""
    if v is None:
        return "空"
    if isinstance(v, bool):
        return "真" if v else "假"
    if isinstance(v, Func):
        return "<函数 " + v.name + "(" + ", ".join(v.params) + ")>"
    if isinstance(v, 内建):
        return "<内置 " + v.名字 + ">"
    if isinstance(v, list):
        return "[" + ", ".join(_显示(x) for x in v) + "]"
    if isinstance(v, dict):
        if not v:
            return "[:]"      # ★ 空字典要跟空列表 [] 分得开，否则看不出来是哪种
        return "[" + ", ".join(_显示(k) + ": " + _显示(x) for k, x in v.items()) + "]"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _显示(v):
    """在列表/字典里面显示一个元素 —— 文本要带引号，
    否则 ["1"] 和 [1] 打印出来长一样，看不出区别。"""
    if isinstance(v, str):
        return _带引号(v)
    return fmt(v)


def main():
    argv = sys.argv[1:]
    flags = set()
    for a in list(argv):
        if a == "--tokens":
            flags.add("tokens")
        elif a in ("--tree", "--ast"):
            flags.add("tree")
        elif a == "--all":
            flags.update(("tokens", "tree"))
    argv = [a for a in argv if not a.startswith("--")]

    # ---------- 单条表达式：python starlang.py [--all] "1 + 2 * 3" ----------
    if argv and not os.path.isfile(argv[0]):
        src = " ".join(argv)
        if not flags:
            flags = {"tokens", "tree"}      # 不加参数默认全透视，方便看明白
        print("源码     :", src)
        try:
            result = run(src, flags)
            if result is not None:
                print("结果     :", fmt(result))
        except Exception as e:
            print("出错了   :", 最终文案(e))
        return

    # ---------- 文件模式：python starlang.py [--all] 程序.star ----------
    if argv:
        # ★ utf-8-sig：容忍 Windows 记事本/PowerShell 存出来的 BOM。
        #   不吞掉的话第一行开头会多一个看不到的 \ufeff，
        #   行首的正则（比如 载入）就匹配不上了 —— 排查半天。
        with open(argv[0], encoding="utf-8-sig") as f:
            src = f.read()
        print("── 执行 " + argv[0] + " " + "─" * 40)
        try:
            # ★ 传基准目录：这样程序里的 载入 "工具.star" 是相对【程序所在目录】，
            #   而不是「你在哪个目录敲的命令」—— 后者会让人调半天。
            run(src, flags, echo=True, 基准目录=os.path.dirname(os.path.abspath(argv[0])))
        except Exception as e:
            print("  ! " + 最终文案(e))
        return

    # ---------- 交互模式 ----------
    print("星语 StarLang v0.7   ← 变量·控制流·函数闭包·插入·字符串·钩子")
    print("试试：  星尘 = \"星尘\"    然后   打印 \"你好\" + 星尘")
    print("       定义 f(x) { 返回 x * 2 }     然后   f(21)")
    print("忘词了就敲 帮助，q 退出。加 --all 可看 Token 流和语法树。")
    env = Environment()                  # ← 整个交互共用一个环境，变量才记得住
    while True:
        try:
            line = input("星语> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if line.strip() in ("q", "quit", "exit"):
            break
        if line.strip() in ("帮助", "help", "?", "？", "h"):
            速查表()
            continue
        if not line.strip():
            continue
        try:
            result = run(line, flags, env)
            if result is not None:
                print("     = " + fmt(result))
        except Exception as e:
            print("     ! " + 最终文案(e))


if __name__ == "__main__":
    main()
