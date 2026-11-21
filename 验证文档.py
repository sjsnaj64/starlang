# -*- coding: utf-8 -*-
r"""验证文档.py —— 手册和 README 里的每个例子都真跑一遍

    python 验证文档.py

★★ 为什么这个必须有？

    文档最常见的烂法不是「写错」，是「写着写着代码改了，文档没跟着改」。
    那时候文档比没有更害人 —— 新手照着抄，报错，然后怀疑是自己蠢。

    所以文档里立了条硬规矩：

        ```星语 / ```starlang   → 完整程序，必须能跑
        ```星语片段             → 只是写法示意，不跑（可能故意报错）
        ```text                → 程序输出，必须一字不差

    这个脚本负责兑现第一条，顺便核对输出。

★ 输出核对只认「紧跟在代码块后面」的 text 块 ——
  中间夹了说明文字就不算，避免误伤。
"""
import io
import os
import re
import sys

for _流 in (sys.stdout, sys.stderr):
    try:
        _流.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

本目录 = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, 本目录)

import starlang                      # noqa: E402

# (文件名, 认哪些语言的代码块) —— README 用英文名，手册用中文名
待验 = [
    ("手册.md", ("星语",)),
    ("README.md", ("starlang",)),
]

# 把 ```语言 ... ``` 整段抓出来，连同它在文件里的起始行号
# ★ 语言名用 \w 不是 [A-Za-z] —— 「星语」是中文，[A-Za-z] 一个都匹配不上，
#   结果就是「共 0 段代码，全部通过」这种自欺欺人的绿。（踩过一次）
块式 = re.compile(r"^```(\w*)[ \t]*\n(.*?)^```[ \t]*$",
                  re.MULTILINE | re.DOTALL)


def 切块(文本):
    """返回 [{语言, 内容, 行, 起, 止}]

    带位置是为了判断「两个块之间有没有夹说明文字」——
    输出核对只认【紧跟在代码块后面】的 text 块。
    """
    结果 = []
    for m in 块式.finditer(文本):
        结果.append({
            "语言": m.group(1),
            "内容": m.group(2),
            "行": 文本.count("\n", 0, m.start()) + 1,
            "起": m.start(),
            "止": m.end(),
        })
    return 结果


def 跑一段(源码):
    """跑一个星语程序，返回 (输出, 错误文本)"""
    缓冲 = io.StringIO()
    旧 = sys.stdout
    sys.stdout = 缓冲
    try:
        starlang.run(源码, echo=False, 基准目录=本目录)
        错 = None
    except Exception as e:                      # noqa: BLE001
        错 = str(e)
    finally:
        sys.stdout = 旧
        # 每个程序跑完都得把全局状态清干净，不然上一个例子的变量/宏会漏过来
        starlang.宏定义表.clear()
        starlang.钩子表.clear()
        starlang.已声明宏.clear()
        starlang.语句行表.clear()
        starlang.当前行[0] = 0
        starlang._gensym[0] = 0
        starlang._宏深度[0] = 0
        starlang._钩子栈.clear()
        starlang.撤掉引入()
    return 缓冲.getvalue(), 错


def 验一个文件(文件名, 认的语言, 汇总):
    """验一份文档。汇总是个字典，用来跨文件累计。"""
    路径 = os.path.join(本目录, 文件名)
    if not os.path.isfile(路径):
        print("  ⏭  %s 不存在，跳过" % 文件名)
        return

    文本 = io.open(路径, encoding="utf-8").read()
    块们 = 切块(文本)
    代码块 = [b for b in 块们 if b["语言"] in 认的语言]

    print()
    print("── %s ── %d 段代码 / %d 段片段（不跑）/ %d 段输出"
          % (文件名, len(代码块),
             len([1 for b in 块们 if b["语言"] == "星语片段"]),
             len([1 for b in 块们 if b["语言"] == "text"])))

    for i, 块 in enumerate(块们):
        if 块["语言"] not in 认的语言:
            continue
        源码 = 块["内容"]
        输出, 错 = 跑一段(源码)
        标题 = 源码.strip().split("\n")[0][:36]
        汇总["代码"] += 1

        if 错 is not None:
            汇总["失败"].append((文件名, 块["行"], 错, 源码))
            print("  ❌ 第 %4d 行 %s" % (块["行"], 标题))
            print("       %s" % 错)
            continue

        汇总["通过"] += 1
        print("  ✅ 第 %4d 行 %s" % (块["行"], 标题))

        # ★ 紧跟在后面的 ```text 就是「这个程序应该输出什么」
        下 = 块们[i + 1] if i + 1 < len(块们) else None
        if 下 is None or 下["语言"] != "text":
            continue
        if 文本[块["止"]:下["起"]].strip():
            continue                    # 中间夹了说明文字，不算「紧跟」
        汇总["核对"] += 1
        # 比较时去掉行首空白：文档里的输出块不写缩进（好读），
        # 而实际打印带着层级。只要「内容和顺序」对就算对。
        实得 = "\n".join(l.strip() for l in 输出.strip().split("\n"))
        期望 = "\n".join(l.strip() for l in 下["内容"].strip().split("\n"))
        if 实得 != 期望:
            汇总["输出错"].append((文件名, 下["行"], 期望, 实得))
            print("       └─ 输出对不上（%s 第 %d 行的 ```text）"
                  % (文件名, 下["行"]))


def main():
    汇总 = {"通过": 0, "代码": 0, "核对": 0, "失败": [], "输出错": []}

    print("═" * 66)
    print("  验证文档：每个代码块都真跑一遍")
    print("═" * 66)

    for 文件名, 认的语言 in 待验:
        验一个文件(文件名, 认的语言, 汇总)

    print()
    print("─" * 66)
    print("代码通过 %d / %d；输出核对 %d 处，对不上 %d 处"
          % (汇总["通过"], 汇总["代码"], 汇总["核对"],
             len(汇总["输出错"])))

    if 汇总["失败"] or 汇总["输出错"]:
        细 = []
        for 文件名, 行, 错, 源码 in 汇总["失败"]:
            细.append("=" * 60)
            细.append("%s 第 %d 行跑挂了：%s" % (文件名, 行, 错))
            for l in 源码.rstrip().split("\n"):
                细.append("    " + l)
        for 文件名, 行, 期望, 实得 in 汇总["输出错"]:
            细.append("=" * 60)
            细.append("%s 第 %d 行的输出块写错了" % (文件名, 行))
            细.append("--- 文档上写的 ---")
            细.extend(期望.split("\n"))
            细.append("--- 实际跑出来的 ---")
            细.extend(实得.split("\n"))
        # ★ 详情另写一份 utf-8 —— PowerShell 屏幕上中文会糊成乱码
        io.open(os.path.join(本目录, "_文档对不上.txt"), "w",
                encoding="utf-8", newline="\n").write("\n".join(细) + "\n")
        print("详情已写进 _文档对不上.txt")
        return 1

    print("文档里每个例子都跑得通，输出也一个字没错 🐾")
    return 0


if __name__ == "__main__":
    sys.exit(main())
