#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
 星语 StarLang —— 从零手写一个玩具编程语言
 Step 1：词法分析 → 语法分析 → 求值   （一个完整的"计算器语言"）
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
    python starlang.py "1 + 2 * 3"      半默全透视：Token 流 + 语法树 + 结果
    python starlang.py --tree "1+2*3"   只看语法树
    python starlang.py --tokens "1+2*3" 只看 Token 流
    python starlang.py --all demo1.star 跑整个文件并逐行透视
"""

import os
import sys
from dataclasses import dataclass

# Windows 控制台默认不是 UTF-8，这句保证中文能正常打印
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ═══════════════════════════════════════════════════════════
# ① 词法分析 Lexer —— 字符串 → Token 流
# ═══════════════════════════════════════════════════════════
# 输入: "1 + 2 * 3"
# 输出: [Token('NUM', 1), Token('+', '+'), Token('NUM', 2), ...]

@dataclass
class Token:
    kind: str        # 类型：NUM / + / - / * / ** / ... / EOF
    value: object    # 值：NUM 存数字，其它存符号本身
    pos: int         # 在源码里的位置（报错时告诉用户错在哪）

    def __repr__(self):
        return f"Token({self.kind!r}, {self.value!r})"

    @property
    def name(self):
        """给人类看的名字：NUM 显示数字，运算符显示符号"""
        return str(self.value) if self.kind == "NUM" else self.kind


class Lexer:
    """把源码字符串切成一个个 Token"""

    def __init__(self, text):
        self.text = text
        self.pos = 0

    def tokenize(self):
        tokens = []
        while self.pos < len(self.text):
            ch = self.text[self.pos]

            # --- 空白直接跳过 ---
            if ch in " \t\r\n":
                self.pos += 1
                continue

            # --- 数字：连续的 0-9，最多一个小数点 ---
            if ch.isdigit() or (
                ch == "."
                and self.pos + 1 < len(self.text)
                and self.text[self.pos + 1].isdigit()
            ):
                tokens.append(self.read_number())
                continue

            # --- 两字符运算符：先看两格，命中就吃两格 ---
            two = self.text[self.pos:self.pos + 2]
            if two in ("**", "==", "!=", "<=", ">="):
                tokens.append(Token(two, two, self.pos))
                self.pos += 2
                continue

            # --- 单字符运算符 ---
            if ch in "+-*/%()<>":
                tokens.append(Token(ch, ch, self.pos))
                self.pos += 1
                continue

            raise SyntaxError(f"[词法错误] 位置 {self.pos}: 没见过的字符 {ch!r}")

        tokens.append(Token("EOF", None, self.pos))   # 结尾哨兵，方便 Parser 判断"读完了"
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
# AST 用 tuple 表示，最省事又直观：
#   数字节点 ("num", 3)          二元运算 (运算符, 左子树, 右子树)
#   一元运算 (运算符, 子树)

class Parser:

    def __init__(self, tokens):
        self.tokens = tokens
        self.i = 0

    # ---------- 小工具 ----------
    @property
    def cur(self):
        return self.tokens[self.i]

    def advance(self):
        t = self.tokens[self.i]
        self.i += 1
        return t

    def expect(self, kind):
        if self.cur.kind != kind:
            raise SyntaxError(
                f"[语法错误] 位置 {self.cur.pos}: 期望 {kind!r}，实际读到 {self.cur.kind!r}"
            )
        return self.advance()

    # ---------- 入口 ----------
    def parse(self):
        node = self.expression()
        if self.cur.kind != "EOF":
            raise SyntaxError(
                f"[语法错误] 位置 {self.cur.pos}: 这里多了个 {self.cur.kind!r}"
            )
        return node

    # ---------- 各优先级层 ----------
    def expression(self):
        return self.comparison()

    def comparison(self):
        node = self.multiplicative_outer()
        while self.cur.kind in ("<", ">", "==", "!=", "<=", ">="):
            op = self.advance().kind
            node = (op, node, self.multiplicative_outer())
        return node

    # ★ 实验：把「乘除层」搬到外面（= 让它优先级变低）
    #    正常版是 additive 在外 / multiplicative 在内
    def multiplicative_outer(self):
        node = self.additive_inner()
        while self.cur.kind in ("*", "/", "%"):
            op = self.advance().kind
            node = (op, node, self.additive_inner())
        return node

    # ★ 实验：把「加减层」塞到里面（= 让它优先级变高）
    def additive_inner(self):
        node = self.unary()
        while self.cur.kind in ("+", "-"):
            op = self.advance().kind
            node = (op, node, self.unary())
        return node

    def unary(self):
        if self.cur.kind in ("-", "+"):
            op = self.advance().kind
            return (op, self.unary())          # 两元素 tuple = 一元节点
        return self.power()

    def power(self):
        node = self.primary()
        if self.cur.kind == "**":
            self.advance()
            return ("**", node, self.unary())  # 右边再调 unary → 实现右结合
        return node

    def primary(self):
        t = self.cur
        if t.kind == "NUM":
            self.advance()
            return ("num", t.value)
        if t.kind == "(":
            self.advance()
            node = self.expression()           # 括号里重新从最低优先级开始
            self.expect(")")
            return node
        raise SyntaxError(
            f"[语法错误] 位置 {t.pos}: 这里应该是数字或 ( ，实际读到 {t.kind!r}"
        )


# ═══════════════════════════════════════════════════════════
# ③ 求值 Evaluator —— AST → 结果
# ═══════════════════════════════════════════════════════════
# 递归遍历这棵树。每种节点一个分支 ——
# 以后要加变量、函数、if、while，就是在这里多加几个 if 而已。

def evaluate(node):
    kind = node[0]

    # 叶子节点：数字
    if kind == "num":
        return node[1]

    # 一元节点（两元素 tuple）
    if len(node) == 2:
        operand = evaluate(node[1])
        if kind == "-":
            return -operand
        if kind == "+":
            return +operand
        raise RuntimeError(f"未知的一元运算符 {kind!r}")

    # 二元节点（三元素 tuple）
    left = evaluate(node[1])
    right = evaluate(node[2])

    if kind == "+":
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


# ═══════════════════════════════════════════════════════════
# 驱动：把三步串起来
# ═══════════════════════════════════════════════════════════

def run(src, flags=()):
    """跑一段星语源码，返回结果。flags 里可以放 'tokens' / 'tree' 来打印中间结果"""
    tokens = Lexer(src).tokenize()      # ① 源码 → Token
    if "tokens" in flags:
        print("      Token 流 :", "  ".join(t.name for t in tokens if t.kind != "EOF"))

    ast = Parser(tokens).parse()        # ② Token → AST
    if "tree" in flags:
        print("      语法树   :")
        for line in tree_lines(ast):
            print("        " + line)

    return evaluate(ast)                # ③ AST → 结果


def tree_lines(node):
    """把 AST 画成缩进 ASCII 树，肉眼可读"""
    kind = node[0]

    if kind == "num":
        return ["数字 " + fmt(node[1])]

    if len(node) == 2:                  # 两元素 tuple = 一元节点
        label = kind + " (一元)"
        children = [node[1]]
    else:                               # 三元素 tuple = 二元节点
        label = kind
        children = [node[1], node[2]]

    lines = [label]
    for i, child in enumerate(children):
        is_last = (i == len(children) - 1)
        sub = tree_lines(child)
        lines.append(("└── " if is_last else "├── ") + sub[0])
        pad = "    " if is_last else "│   "
        lines.extend(pad + x for x in sub[1:])
    return lines


def fmt(v):
    """把结果变好看：布尔显示成中文，3.0 显示成 3"""
    if isinstance(v, bool):
        return "真" if v else "假"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


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
            print("结果     :", fmt(run(src, flags)))
        except Exception as e:
            print("出错了   :", e)
        return

    # ---------- 文件模式：python starlang.py [--all] 程序.star ----------
    if argv:
        with open(argv[0], encoding="utf-8") as f:
            src = f.read()
        print("── 执行 " + argv[0] + " " + "─" * 40)
        for line in src.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):     # 星语的注释以 # 开头
                continue
            try:
                result = run(line, flags)
                print(f"  {line:<28} = {fmt(result)}")
            except Exception as e:
                print(f"  {line:<28} ! {e}")
        return

    # ---------- 交互模式 ----------
    print("星语 StarLang v0.1   ← 目前只会算数 (Step 1)")
    print("输入算式回车，q 退出。加 --all 可看到 Token 流和语法树。")
    while True:
        try:
            line = input("星语> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if line.strip() in ("q", "quit", "exit"):
            break
        if not line.strip():
            continue
        try:
            print("     =", fmt(run(line, flags)))
        except Exception as e:
            print("     !", e)


if __name__ == "__main__":
    main()
