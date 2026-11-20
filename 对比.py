# -*- coding: utf-8 -*-
"""对比.py —— 同一份 .star，三个实现分别跑，逐行 diff。

    ① starlang.py    树遍历解释器
    ② starlangc.py   编译成 Python 源码
    ③ starlangvm.py  字节码虚拟机

用法：
    python 对比.py              跑全部 demo*.star
    python 对比.py demo9.star    只比一个

这是「实现写对了没有」的唯一硬标准：
    三边输出必须一模一样，差一个空格都算错。
"""
import os
import re
import subprocess
import sys

本目录 = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

实现们 = [
    ("解释器", "starlang.py", []),
    ("编译器", "starlangc.py", ["--quiet"]),
    ("虚拟机", "starlangvm.py", []),
]

# 这些是驱动自己打印的装饰行，不属于程序输出
装饰 = [
    re.compile(r"^──.*$"),
    re.compile(r"^\s*· "),          # 织入报告 / 已定义语法
    re.compile(r"^\s*插入指令"),      # 织入报告的表头
    re.compile(r"^   \. "),
]


def _跑(脚本, 参数, 额外):
    环境 = dict(os.environ)
    环境["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [PY, "-u", 脚本] + 参数 + 额外,
        cwd=本目录,
        capture_output=True,
        env=环境,
    )
    return (
        r.stdout.decode("utf-8", "replace"),
        r.stderr.decode("utf-8", "replace"),
    )


def 规范化(文本):
    行们 = []
    for 行 in 文本.replace("\r\n", "\n").split("\n"):
        if 行.strip() == "":
            continue
        if any(p.match(行) for p in 装饰):
            continue
        行们.append(行.rstrip())
    return 行们


def 比一个(文件名):
    结果 = []
    for 名字, 脚本, 额外 in 实现们:
        出, 错 = _跑(脚本, [文件名], 额外)
        结果.append((名字, 规范化(出), 错.strip()))

    基准名, 基准, 基准错 = 结果[0]
    报告 = []
    全好 = True

    for 名字, 行们, 错 in 结果[1:]:
        if 错:
            报告.append("  【%s 报错】" % 名字)
            for 行 in 错.split("\n")[-10:]:
                报告.append("    " + 行)
            全好 = False
        if 行们 != 基准:
            全好 = False
            报告.append("  【%s 跟 %s 不一致】  %d 行 / %d 行"
                        % (名字, 基准名, len(行们), len(基准)))
            最多 = max(len(行们), len(基准))
            for i in range(最多):
                x = 基准[i] if i < len(基准) else "<没有这行>"
                y = 行们[i] if i < len(行们) else "<没有这行>"
                if x != y:
                    报告.append("    第 %d 行:" % (i + 1))
                    报告.append("      %s： %s" % (基准名, repr(x)))
                    报告.append("      %s： %s" % (名字, repr(y)))
                    break
    return 全好, len(基准), "\n".join(报告)


def main():
    目标 = sys.argv[1:]
    if not 目标:
        目标 = sorted(
            [f for f in os.listdir(本目录)
             if re.fullmatch(r"demo\d+\.star", f)],
            key=lambda s: int(re.search(r"\d+", s).group()),
        )

    通过 = 0
    失败 = []
    for f in 目标:
        好, 行数, 报告 = 比一个(f)
        if 好:
            print("  %-14s ✅  三方 %d 行一致" % (f, 行数))
            通过 += 1
        else:
            print("  %-14s ❌" % f)
            if 报告:
                print(报告)
            失败.append(f)

    print()
    print("─" * 56)
    print("通过 %d / %d" % (通过, len(目标)))
    if 失败:
        print("没过： " + "、".join(失败))
        return 1
    print("三个实现输出逐行一致 🐾  （解释器 / 编译器 / 虚拟机）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
