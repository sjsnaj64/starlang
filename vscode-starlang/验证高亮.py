# -*- coding: utf-8 -*-
r"""验证高亮.py —— 不启动 VS Code 也能检查高亮规则对不对

    python 验证高亮.py

为什么需要它：
    中文没空格，`打印次数` 里的「打印」绝不能高亮 —— 这种错误肉眼在一个彩色
    编辑器里很难看出来，但用正则跑一遍就一目了然。

它做的事其实就是一个**极简版 TextMate**：
    从左往右扫，每个位置按规则顺序试，第一个匹配的赢，
    赢家按 captures 给子串上色，然后从匹配末尾继续。
    （begin/end 那种跨行规则这里不支持 —— 但常用的 match 型够查了。）

VS Code 用 Oniguruma，支持 \p{L}（字母）。Python 自带的 re 不支持，
所以这里换成近似写法来模拟。
"""
import io
import json
import os
import re
import sys

本目录 = os.path.dirname(os.path.abspath(__file__))
语法路径 = os.path.join(本目录, "syntaxes", "starlang.tmLanguage.json")

# ★ 关键：先把整个字符类 [\p{L}\p{N}_] 换成 \w，再处理零散的 \p{L}。
#   顺序反了就会变成 [[^\W\d_]\d_] 这种嵌套集合 —— Python 里是另一个意思，
#   lookahead 直接失效，验证结果全假。（踩过一次）
替换 = [
    (r"[\p{L}\p{N}_]", r"\w"),
    (r"\p{L}", r"[^\W\d_]"),
    (r"\p{N}", r"\d"),
]


def 转Python(式):
    for 旧, 新 in 替换:
        式 = 式.replace(旧, 新)
    return 式


class 极简TextMate:
    def __init__(self, 语法):
        self.语法 = 语法
        self.规则们 = []
        self.关键字规则 = []
        # ★ 顺序 = tmLanguage 里 patterns 的顺序，变量在前（它的匹配更长更具体）
        for 类别 in ("变量", "关键字", "内置函数", "数字", "标号"):
            组 = []
            for 条 in 语法["repository"][类别]["patterns"]:
                if "match" in 条:
                    组.append(("match",
                              re.compile(转Python(条["match"])),
                              条.get("name"), self._捕获(条)))
                elif "begin" in 条:
                    内部 = [(re.compile(转Python(p["match"])), p.get("name"))
                            for p in 条.get("patterns", []) if "match" in p]
                    组.append(("begin",
                              re.compile(转Python(条["begin"])),
                              re.compile(转Python(条["end"])),
                              self._捕获(条, "beginCaptures"), 内部))
            self.规则们.extend(组)
            if 类别 == "关键字":
                self.关键字规则 = [g for g in 组 if g[0] == "match"]

    @staticmethod
    def _捕获(条, 键="captures"):
        捕获 = {}
        for 组号, 说明 in (条.get(键) or {}).items():
            if 说明.get("name"):
                捕获[int(组号)] = 说明["name"]
        return 捕获

    def _上色(self, m, scope, 捕获, 结果):
        """把一次匹配的结果记下来（有捕获组就只给捕获组上色）"""
        if not 捕获:
            if scope:
                结果.append((m.group(0), scope))
            return
        for 组号, 组scope in 捕获.items():
            文字 = m.group(组号)
            if 文字:
                结果.append((文字, 组scope))

    def 扫(self, 行):
        """返回 [(文本, scope)]，按出现顺序"""
        结果 = []
        位置 = 0
        while 位置 < len(行):
            命中 = None
            for 条 in self.规则们:
                if 条[0] == "match":
                    _t, 正则, scope, 捕获 = 条
                    m = 正则.search(行, 位置)
                    if m and m.start() == 位置:
                        命中 = ("match", m, scope, 捕获)
                        break
                else:
                    _t, 起, 止, 捕获, 内部 = 条
                    m = 起.search(行, 位置)
                    if m and m.start() == 位置:
                        命中 = ("begin", m, 止, 捕获, 内部)
                        break

            if not 命中:
                位置 += 1
                continue

            if 命中[0] == "match":
                _, m, scope, 捕获 = 命中
                self._上色(m, scope, 捕获, 结果)
                位置 = m.end()
            else:
                _, m, 止, 捕获, 内部 = 命中
                # beginCaptures 里如果是指向 #关键字 的嵌套模式，
                # 就把这一段再拿关键字规则过一遍（模拟 TextMate 的 include）
                for 组号, 组scope in 捕获.items():
                    文字 = m.group(组号)
                    if not 文字:
                        continue
                    if 组scope:
                        结果.append((文字, 组scope))
                    位置们 = m.span(组号)
                    # 组 0 里混着关键字，单独再过一次
                    if 组号 == 0:
                        self._扫关键字(文字, 结果)
                内部起 = m.end()
                剩余 = 行[内部起:]
                e = 止.search(剩余)
                内部文本 = 剩余[:e.start()] if e else 剩余
                for 正则, scope in 内部:
                    for mm in 正则.finditer(内部文本):
                        if scope:
                            结果.append((mm.group(0), scope))
                位置 = (内部起 + e.end()) if e else len(行)
        return 结果

    def _扫关键字(self, 文字, 结果):
        for _t, 正则, scope, _捕获 in self.关键字规则:
            for mm in 正则.finditer(文字):
                if scope:
                    结果.append((mm.group(0), scope))


# (源码, 必须有的 [(文本, scope 关键词)], 不能有的 [(文本, scope 关键词)])
# ★ 用「必须 / 不能」而不是「完全相等」：数字、括号这些也会上色，
#   全都写进期望里太琐碎，而且改一条规则就得改一堆用例。
测 = [
    # ---- 关键字边界 ----
    ("打印 次数",               [("打印", "print")], [("打印次数", "print")]),
    ("打印次数 = 5",            [("打印次数", "assignment")], [("打印", "print")]),
    ("如果 条件 > 0",           [("如果", "control")], []),
    ("如果x = 1",               [("如果x", "assignment")], [("如果", "control")]),
    ("宏 除非(条件, 动作)",     [("宏", "macro")], [("非", "operator.word")]),
    ("否则如果 1 > 0",          [("否则如果", "elseif")], [("否则", "control")]),
    ("结算 单价 * 数量",        [], [("结算", "keyword")]),
    ("非 真",                   [("非", "operator.word"), ("真", "boolean")], []),
    # ---- 内置函数 ----
    ("长度(名单)",              [("长度", "builtin")], []),
    ("平方(3)",                 [], [("平方", "function")]),
    # ---- ★ 变量名定义 ----
    ("价格 = 100",              [("价格", "assignment")], []),
    ("  缩进的 = 1",            [("缩进的", "assignment")], []),
    ("x == 5",                  [], [("x", "assignment")]),          # 比较不是赋值
    ("定义 平方(x)",            [("平方", "function"), ("x", "parameter")], []),
    ("定义 加税(元, 率)",       [("加税", "function"), ("元", "parameter"),
                                  ("率", "parameter")], []),
    ("fn 平方(x)",              [("平方", "function"), ("x", "parameter")], []),
    # ---- ★ Step 14~17 新加的词，一个都不能漏 ----
    #   这批曾经整批都漏上色过：语言跑得好好的，编辑器里全是灰的。
    ("跳出",                    [("跳出", "control")], []),
    ("继续",                    [("继续", "control")], []),
    ("空",                      [("空", "boolean")], []),
    ("x = 空",                  [("空", "boolean")], []),
    ("匿名(甲) { 返回 甲 }",     [("匿名", "function")], []),
    ("c = 如果 a 则 1 否则 2",  [("如果", "control"), ("则", "control"),
                                 ("否则", "control")], []),
    ("点 += 1",                 [], []),                    # 先占位，见下面单独测
]


def 有(实际, 文本, scope片段):
    """实际里有没有「这段文字，且 scope 包含这个片段」"""
    return any(文 == 文本 and scope片段 in sc for 文, sc in 实际)


def main():
    语法 = json.load(io.open(语法路径, encoding="utf-8"))
    器 = 极简TextMate(语法)

    通过 = 0
    失败 = []
    for 源码, 必须有, 不能有 in 测:
        实际 = 器.扫(源码)
        缺 = [期 for 期 in 必须有 if not 有(实际, 期[0], 期[1])]
        多 = [期 for 期 in 不能有 if 有(实际, 期[0], 期[1])]
        if not 缺 and not 多:
            通过 += 1
            print("  ✅ %-24s → %s" % (源码, 实际 if 实际 else "（不高亮）"))
        else:
            print("  ❌ %-24s → %s" % (源码, 实际))
            if 缺:
                print("      少了 %s" % (缺,))
            if 多:
                print("      不该有 %s" % (多,))
            失败.append(源码)

    print()
    print("─" * 62)
    print("通过 %d / %d" % (通过, len(测)))
    if 通过 == len(测):
        print("中文名字里的字不会被当成关键字，变量定义也认得出来 🐾")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
