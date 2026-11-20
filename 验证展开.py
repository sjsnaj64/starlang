# -*- coding: utf-8 -*-
"""验证展开.py —— 确认「展开」是【语义保持】的

    python 验证展开.py

怎么验：
    对每个 demo：
        ① 原文件跑一遍 → 输出 A
        ② 展开.py 生成副本
        ③ 副本跑一遍   → 输出 B
        ④ A 和 B 必须一模一样

这才是「合并插入」这件事真的做对了的证据 ——
要是搬到函数体里的时候位置错了，副本跑出来的结果就一定不一样。
"""
import os
import re
import subprocess
import sys

本目录 = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

装饰 = [
    re.compile(r"^──.*$"),
    re.compile(r"^\s*· "),
    re.compile(r"^\s*插入指令"),
    re.compile(r"^   \. "),
]


def 跑(脚本, 参数):
    环境 = dict(os.environ)
    环境["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run([PY, "-u", 脚本] + 参数, cwd=本目录,
                       capture_output=True, env=环境)
    return (r.stdout.decode("utf-8", "replace"),
            r.stderr.decode("utf-8", "replace"))


def 净(文本):
    """★ 顺便把「第 N 行」抹平。

    副本是重新排版过的，行号和原文件必然不一样 —— 那不是语义差异。
    真出错的地方（谁除以零、谁没定义）会一模一样，只有行号这项会变。
    """
    行们 = []
    for 行 in 文本.replace("\r\n", "\n").split("\n"):
        if not 行.strip() or any(p.match(行) for p in 装饰):
            continue
        行们.append(re.sub(r"第 \d+ 行", "第 ? 行", 行.rstrip()))
    return 行们


def main():
    目标 = sorted(
        [f for f in os.listdir(本目录) if re.fullmatch(r"demo\d+\.star", f)],
        key=lambda s: int(re.search(r"\d+", s).group()),
    )

    通过 = 0
    失败 = []
    for f in 目标:
        副本 = "_展开_" + f
        出, 错 = 跑("展开.py", [f, "--out", 副本])
        if not os.path.exists(os.path.join(本目录, 副本)):
            失败.append(f)
            print("  ❌ %-14s  展开不出来" % f)
            print("      " + (错.strip().split("\n")[-1] if 错.strip() else ""))
            continue

        A, _ = 跑("starlang.py", [f])
        B, B错 = 跑("starlang.py", [副本])
        os.remove(os.path.join(本目录, 副本))

        a, b = 净(A), 净(B)
        if b == a and not B错.strip():
            通过 += 1
            print("  ✅ %-14s  原 %d 行 / 副本 %d 行，一致" % (f, len(a), len(b)))
        else:
            失败.append(f)
            print("  ❌ %-14s  原 %d 行 / 副本 %d 行" % (f, len(a), len(b)))
            if B错.strip():
                print("      副本报错： " + B错.strip().split("\n")[-1])
            for i in range(max(len(a), len(b))):
                x = a[i] if i < len(a) else "<没有>"
                y = b[i] if i < len(b) else "<没有>"
                if x != y:
                    print("      第 %d 行  原： %s" % (i + 1, repr(x)))
                    print("                副本： %s" % (repr(y),))
                    break

    print()
    print("─" * 60)
    print("通过 %d / %d" % (通过, len(目标)))
    if 失败:
        print("没过： " + "、".join(失败))
        return 1
    print("展开之后的副本跟原文件跑出来一模一样 🐾  插入真的搬对位置了")
    return 0


if __name__ == "__main__":
    sys.exit(main())
