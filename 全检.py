# -*- coding: utf-8 -*-
r"""全检.py —— 一条命令跑完所有验证，只吐一行一个结果

    python 全检.py            全跑
    python 全检.py --快       跳过最慢的两项（缩减器）

★★ 为什么要有它？

    直接在 PowerShell 里连着敲十几个 `python xxx.py`，输出会被吞：
      · PowerShell 5.1 的管道有缓冲，命令跑完了屏幕上还是空的；
      · 中文 + `Out-String -Width` + 管道，换行位置乱飞；
      · 最后一个命令把终端占着，下一条就排队，看起来像卡死。

    真正的解法是【把输出的量降下来】：
    让 Python 去开子进程、自己把输出抓走、这里只打印一行摘要。
    完整输出同时写进 验收报告.txt，要翻细节去那儿翻。
"""
import io
import os
import re
import subprocess
import sys
import time

# ★★ 这一句是整个工具链最重要的一行防御：
#   Windows 上 Python 默认用 GBK 输出，一碰到 ✅ / 🐾 这种字符就
#       UnicodeEncodeError: 'gbk' codec can't encode character '\u2705'
#   于是【后面的输出全部消失】—— 看起来就像「终端把输出吃掉了」。
#   重设成 utf-8 + replace 之后，就算终端再古怪最多显示成问号，不会崩。
for _流 in (sys.stdout, sys.stderr):
    try:
        _流.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

本目录 = os.path.dirname(os.path.abspath(__file__))
报告路径 = os.path.join(本目录, "验收报告.txt")
# ★ 筛要单独再写一份：PowerShell 的 `>` 重定向是 UTF-16，
#   拿 read_file 之类的工具根本读不出来。要留证据就得自己用 utf-8 写。
摘要路径 = os.path.join(本目录, "全检摘要.txt")

环境 = dict(os.environ)
环境["PYTHONIOENCODING"] = "utf-8"
环境["PYTHONUTF8"] = "1"

# (显示名, 命令, 是否慢, 摘要正则)
#   摘要正则里第一个抓到的数就是「通过数」，第二个（可选）是「总数」
项目们 = [
    ("对比    三个实现逐行一致",   ["对比.py"],                    False, r"通过 (\d+) / (\d+)"),
    ("展开    副本跟原文等价",     ["验证展开.py"],                False, r"通过 (\d+) / (\d+)"),
    ("高亮    不启动 VS Code 验",  ["vscode-starlang/验证高亮.py"], False, r"通过 (\d+) / (\d+)"),
    ("库      星语 ⇄ Python",     ["验证库.py"],                  False, r"通过 (\d+) 项"),
    ("手册    每个例子都真跑",     ["验证手册.py"],                False, r"代码通过 (\d+) / (\d+)"),
    ("差分    1000 个随机程序",    ["差分测试.py", "--个数", "1000"], False, r"通过 (\d+) / (\d+)"),
    ("缩减器  自测",              ["缩减.py", "--自测"],           True,  None),
    ("缩减器  注入 bug 能不能缩",  ["验证缩减.py"],                True,  None),
]


def 跑一项(命令):
    """跑一个子进程，把它的输出整段抓走 —— 屏幕上什么都不留。"""
    起 = time.time()
    p = subprocess.run(
        [sys.executable, "-u"] + 命令,
        cwd=本目录, env=环境,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    return (p.stdout or ""), p.returncode, time.time() - 起


def 读摘要(输出, 正则):
    """从输出里抠出「通过 29 / 29」这种数字。"""
    if 正则:
        m = re.search(正则, 输出)
        if m:
            组 = m.groups()
            if len(组) >= 2:
                return "通过 %s / %s" % (组[0], 组[1])
            return "通过 %s 项" % 组[0]
    # 没有固定格式的（缩减器）：看最后一行
    for 行 in reversed(输出.strip().split("\n")):
        if 行.strip():
            return 行.strip()
    return "（没输出）"


class _双写:
    """把屏幕上打印的东西同时存一份。

    ★ 为什么要这么绕：PowerShell 的 `>` / `Tee-Object` 写出来是 UTF-16，
      拿 read_file 这种按 UTF-8 读的工具根本看不了（读出来是乱码）。
      所以摘要要自己用 utf-8 落盘。
    """

    def __init__(self, 真):
        self.真 = 真
        self.存 = io.StringIO()

    def write(self, s):
        self.真.write(s)
        self.存.write(s)
        return len(s)

    def flush(self):
        self.真.flush()


def main():
    快 = "--快" in sys.argv
    行们 = []
    失败们 = []
    总计 = len([1 for p in 项目们 if 快 is False or p[2] is False])

    笔 = _双写(sys.stdout)
    sys.stdout = 笔
    try:
        print("═" * 68)
        print("  星语全检     （完整输出写进 验收报告.txt，屏幕上只看摘要）")
        print("═" * 68)

        for 名, 命令, 慢, 正则 in 项目们:
            if 快 and 慢:
                print("  ⏭  %-26s 跳过（--快）" % 名)
                continue

            输出, 码, 耗时 = 跑一项(命令)

            行们.append("=" * 70)
            行们.append("## " + 名 + "    (" + " ".join(命令) + ")")
            行们.append("=" * 70)
            行们.append(输出)
            行们.append("")

            # 判定：退出码 0 + 输出里没有 ❌ + 没有明说的"没通过"
            坏 = (码 != 0) or ("❌" in 输出) or ("没通过" in 输出)
            if 坏:
                失败们.append(名)
                print("  ❌ %-26s %s   (%.1fs, 退出码 %d)"
                      % (名, 读摘要(输出, 正则), 耗时, 码))
                尾巴 = [l for l in 输出.strip().split("\n") if l.strip()][-6:]
                for l in 尾巴:
                    print("        │ " + l)
            else:
                print("  ✅ %-26s %s   (%.1fs)"
                      % (名, 读摘要(输出, 正则), 耗时))

        print("─" * 68)
        if 失败们:
            print("  %d / %d 项没过：" % (len(失败们), 总计))
            for 名 in 失败们:
                print("     · " + 名)
            print("  细节看 验收报告.txt")
            结果码 = 1
        else:
            print("  全部通过 🐾    细节看 验收报告.txt")
            结果码 = 0
        print("═" * 68)

        io.open(报告路径, "w", encoding="utf-8", newline="\n").write(
            "\n".join(行们) + "\n")
        return 结果码
    finally:
        sys.stdout = 笔.真
        io.open(摘要路径, "w", encoding="utf-8", newline="\n").write(
            笔.存.getvalue())


if __name__ == "__main__":
    sys.exit(main())
