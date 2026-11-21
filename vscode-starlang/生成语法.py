# -*- coding: utf-8 -*-
r"""生成语法.py —— 从 starlang.py 的键字表生成为 VS Code 语法文件

为什么用生成而不是手写？
    词表在 starlang.py 里，语法文件在 vscode-starlang/ 里 —— 两处手维护迟早对不上。
    让这个脚本去读词表，改完词表重跑一次就同步了。

    python 生成语法.py

★ 中文关键字最难的一点：中文之间没有空格，`打印次数` 里的「打印」不该高亮。
  解决办法是 Unicode 词边界断言：
      (?<![\p{L}\p{N}_]) 关键字 (?![\p{L}\p{N}_])
  前后都不能紧挨着字母/数字/下划线 —— 汉字属于 \p{L}，所以 `打印次数` 不会误伤，
  而 `打印 价格` 里「打印」前后是空格，正常高亮。
"""
import io
import json
import os
import re
import sys

本目录 = os.path.dirname(os.path.abspath(__file__))
上级 = os.path.dirname(本目录)
sys.path.insert(0, 上级)

import starlang          # noqa: E402  （必须先加 sys.path）

# 汉字/字母/数字/下划线 —— 星语名字允许的全集
字 = r"\p{L}\p{N}_"


def 词式(词们):
    """把一堆词做成「前后都不挨着名字字符」的正则"""
    排好 = sorted(set(词们), key=len, reverse=True)      # ★ 长的在前：否则如果 > 否则
    return "(?<![" + 字 + "])(?:" + "|".join(re.escape(w) for w in 排好) + ")(?![" + 字 + "])"


def 规则(name, 词们):
    return {"name": name, "match": 词式(词们)}


def 造语法():
    # ---- 按「这个东西是干嘛的」分 scope，主题靠 scope 上色 ----
    # ★ 每加一批新关键字，这里就得跟着加一行 ——
    #   不然语言能跑了、编辑器里却是灰的（Step 14~17 就漏了好几批）。
    控制流 = (list(starlang.IF_WORDS) + list(starlang.ELSE_WORDS)
            + list(starlang.WHILE_WORDS) + list(starlang.BREAK_WORDS)
            + list(starlang.CONTINUE_WORDS) + list(starlang.THEN_WORDS)
            + list(starlang.FOR_WORDS) + list(starlang.IN_WORDS))
    函数类 = (list(starlang.FUNC_WORDS) + list(starlang.RETURN_WORDS)
            + list(starlang.LAMBDA_WORDS))
    输出类 = list(starlang.PRINT_WORDS)
    异常类 = list(starlang.TRY_WORDS) + list(starlang.CATCH_WORDS)
    逻辑词 = list(starlang.AND_WORDS) + list(starlang.OR_WORDS) + list(starlang.NOT_WORDS)
    造语法类 = (list(starlang.MACRO_WORDS) + list(starlang.INSERT_WORDS)
              + list(starlang.LABEL_WORDS) + list(starlang.HEAD_WORDS)
              + list(starlang.TAIL_WORDS))
    钩子类 = (list(starlang.REGISTER_WORDS) + list(starlang.UNREGISTER_WORDS)
            + list(starlang.BEFORE_WORDS) + list(starlang.AFTER_WORDS))
    布尔词 = list(starlang.BOOL_WORDS.keys()) + list(starlang.NULL_WORDS)
    内建名 = list(starlang.内建函数.keys())

    关键字规则 = [
        规则("keyword.control.exception.starlang", 异常类),
        规则("keyword.control.starlang", 控制流),
        规则("keyword.other.elseif.starlang", list(starlang.ELSEIF_WORDS)),
        规则("storage.type.function.starlang", 函数类),
        规则("support.function.print.starlang", 输出类),
        规则("keyword.operator.word.starlang", 逻辑词),
        规则("keyword.other.macro.starlang", 造语法类),
        规则("keyword.other.hook.starlang", 钩子类),
        规则("constant.language.boolean.starlang", 布尔词),
    ]

    # ═══ 变量名【声明】的地方单独上色 ═══
    # 光高亮关键字不够用：`x = 5` 里的 x、`定义 平方(x)` 里的 平方 和 x
    # 现在都是普通颜色，根本分不清「这里在造一个新名字」。
    定义词 = "|".join(re.escape(w) for w in
                       sorted(set(starlang.FUNC_WORDS), key=len, reverse=True))

    变量规则 = [
        {
            # 定义 平方(x, y) —— 一句话给三样东西上色：
            #   定义 → storage.type.function    平方 → entity.name.function
            #   括号里 → variable.parameter
            # ⚠️ 不用变长 lookbehind（`(?<=定义\s)` 那种）：
            #    VS Code 的 Oniguruma 支持，但 Python 的 re 不支持 ——
            #    用了就没法在本机验证，宁可换种写法。
            "begin": ("(?<![" + 字 + "])(?:" + 定义词 + r")(\s+)([" + 字
                      + r"]+)(\s*)(\()"),
            "beginCaptures": {
                "0": {"patterns": [{"include": "#关键字"}]},
                "2": {"name": "entity.name.function.starlang"},
                "4": {"name": "punctuation.definition.parameters.begin.starlang"},
            },
            "end": r"(\))",
            "endCaptures": {
                "1": {"name": "punctuation.definition.parameters.end.starlang"},
            },
            "patterns": [
                {"name": "variable.parameter.starlang", "match": "[" + 字 + "]+"},
            ],
        },
        {
            "comment": "x = 值 —— 左边是新造的变量",
            # ⚠️ 这里整串是 raw string，所以写 \s 而不是 \\s
            "match": "^(\\s*)([" + 字 + r"]+)(\s*)=(?!=)",
            "captures": {
                "2": {"name": "variable.other.assignment.starlang"},
            },
        },
    ]

    语法 = {
        "$schema": "https://raw.githubusercontent.com/martinring/tmlanguage/master/tmlanguage.json",
        "name": "星语",
        "scopeName": "source.starlang",
        "comment": "★ 这个文件是 生成语法.py 自动生成的，别手改。改词表请改 starlang.py",
        "patterns": [
            {"include": "#注释"},
            {"include": "#字符串"},
            {"include": "#标号"},
            {"include": "#数字"},
            {"include": "#方法"},
            {"include": "#变量"},
            {"include": "#关键字"},
            {"include": "#内置函数"},
            {"include": "#运算符"},
        ],
        "repository": {
            "注释": {
                "patterns": [
                    {
                        # 注释里如果藏着 #@标号，给它单独上一个色
                        "name": "comment.line.number-sign.starlang",
                        "match": "#.*$",
                        "captures": {
                            "0": {
                                "patterns": [
                                    {
                                        "name": "entity.name.tag.starlang",
                                        "match": "#@[" + 字 + "]+",
                                    }
                                ]
                            }
                        },
                    }
                ]
            },

            "字符串": {
                "patterns": [
                    {
                        "name": "string.quoted.double.starlang",
                        "begin": "\"",
                        "end": "\"",
                        "beginCaptures": {"0": {"name": "punctuation.definition.string.begin.starlang"}},
                        "endCaptures": {"0": {"name": "punctuation.definition.string.end.starlang"}},
                        "patterns": [
                            {"name": "constant.character.escape.starlang",
                             "match": "\\\\[ntr\\\\\"'0]|\\\\u[0-9a-fA-F]{4}|\\\\."}
                        ],
                    },
                    {
                        "name": "string.quoted.single.starlang",
                        "begin": "'",
                        "end": "'",
                        "beginCaptures": {"0": {"name": "punctuation.definition.string.begin.starlang"}},
                        "endCaptures": {"0": {"name": "punctuation.definition.string.end.starlang"}},
                        "patterns": [
                            {"name": "constant.character.escape.starlang",
                             "match": "\\\\[ntr\\\\\"'0]|\\\\u[0-9a-fA-F]{4}|\\\\."}
                        ],
                    },
                ]
            },

            "标号": {
                "patterns": [
                    {
                        # 光秃秃的 @名字（跟 #@名字 等价）
                        "name": "entity.name.tag.starlang",
                        "match": "@[" + 字 + "]+",
                    }
                ]
            },

            "数字": {
                "patterns": [
                    {"name": "constant.numeric.starlang",
                     "match": "(?<![" + 字 + "])\\d+(?:\\.\\d+)?"}
                ]
            },

            "关键字": {"patterns": 关键字规则},

            "变量": {"patterns": 变量规则},

            "内置函数": {
                "patterns": [规则("support.function.builtin.starlang", 内建名)]
            },

            "方法": {
                # ★ Step 21：话.长度() —— 点号后面的名字上一个「方法」色，
                #   跟函数调用的颜色拉开一点，一眼看得出「这是在调它自己的方法」。
                #   ⚠️ 后面必须跟 ( 才算，不然 3.14 里那个点也会被上色。
                "patterns": [
                    {
                        "match": r"(\.)\s*([" + 字 + r"]+)\s*(?=\()",
                        "captures": {
                            "1": {"name": "punctuation.accessor.starlang"},
                            "2": {"name": "support.function.method.starlang"},
                        },
                    },
                ]
            },

            "运算符": {
                "patterns": [
                    {"name": "keyword.operator.comparison.starlang",
                     "match": "==|!=|<=|>="},
                    {"name": "keyword.operator.arithmetic.starlang",
                     "match": "\\*\\*|[+\\-*/%]"},
                    {"name": "keyword.operator.assignment.starlang",
                     "match": "(?<!<|>|!)=(?!=)"},
                    {"name": "keyword.operator.comparison.starlang",
                     "match": "<|>"},
                    {"name": "punctuation.separator.starlang",
                     "match": "[,\\[\\]{}():]"},
                ]
            },
        },
    }
    return 语法


def 造语言配置():
    """生成 language-configuration.json

    ★ 缩进块最大的问题：大括号有 `{` 可以当标记，缩进块什么都没有。
      所以按 Enter 时编辑器不知道要不要往里缩 —— 得靠「上一行开头是哪个词」来猜。
      这份配置就是干这个的。
    """
    开头会缩进的 = list(starlang.IF_WORDS) + list(starlang.WHILE_WORDS) \
        + list(starlang.FUNC_WORDS) + list(starlang.TRY_WORDS) \
        + list(starlang.ELSE_WORDS) + list(starlang.CATCH_WORDS) \
        + list(starlang.FOR_WORDS) + list(starlang.ELSEIF_WORDS)
    # 「否则」「出错」这类要退一级（跟 if 对齐），不是往里缩
    要退一级的 = list(starlang.ELSE_WORDS) + list(starlang.CATCH_WORDS)

    def 词组(词们):
        return "|".join(re.escape(w) for w in sorted(set(词们), key=len, reverse=True))

    往里缩 = (
        # 大括号那种老写法
        r"\{\s*(?:#.*)?$"
        # 缩进写法：行首是这些词，且这一行没有 { （有 { 那就走上面那条了）
        + r"|^\s*(?:" + 词组(开头会缩进的) + r")(?![\w])(?![^\n]*\{)"
    )
    退一级 = r"^\s*(?:\}|" + 词组(要退一级的) + r")"

    return {
        "comments": {"lineComment": "#"},
        "brackets": [["{", "}"], ["[", "]"], ["(", ")"]],
        "autoClosingPairs": [
            {"open": "{", "close": "}"},
            {"open": "[", "close": "]"},
            {"open": "(", "close": ")"},
            {"open": "\"", "close": "\"", "notIn": ["string"]},
            {"open": "'", "close": "'", "notIn": ["string"]},
        ],
        "surroundingPairs": [
            ["{", "}"], ["[", "]"], ["(", ")"], ["\"", "\""], ["'", "'"],
        ],
        # 中文词要能被双击选中、也能让「找下一个同名」正常工作
        "wordPattern": "[\\p{L}\\p{N}_]+",
        "indentationRules": {
            "increaseIndentPattern": 往里缩,
            "decreaseIndentPattern": 退一级,
        },
        "onEnterRules": [
            {
                # 打完 `如果 条件` 一按回车，光标自动往里缩 —— 这才是用缩进该有的手感
                "beforeText": "^\\s*(?:" + 词组(开头会缩进的) + r")(?![\w])(?![^\n]*\{).*$",
                "action": {"indent": "increaseIndent"},
            }
        ],
        "folding": {
            "markers": {
                "start": "^\\s*#\\s*region\\b",
                "end": "^\\s*#\\s*endregion\\b",
            }
        },
    }


def main():
    语法 = 造语法()
    输出 = os.path.join(本目录, "syntaxes")
    if not os.path.isdir(输出):
        os.makedirs(输出)
    路径 = os.path.join(输出, "starlang.tmLanguage.json")
    io.open(路径, "w", encoding="utf-8", newline="\n").write(
        json.dumps(语法, ensure_ascii=False, indent=2) + "\n")

    配置路径 = os.path.join(本目录, "language-configuration.json")
    io.open(配置路径, "w", encoding="utf-8", newline="\n").write(
        json.dumps(造语言配置(), ensure_ascii=False, indent=2) + "\n")

    print("已生成 " + 路径)
    print("已生成 " + 配置路径)
    print("  关键字规则 %d 条" % len(语法["repository"]["关键字"]["patterns"]))
    print("  内置函数 %d 个" % len(starlang.内建函数))


if __name__ == "__main__":
    main()
