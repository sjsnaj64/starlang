# -*- coding: utf-8 -*-
"""测速.py —— 解释器 vs 编译器，同一份 .star 跑同样的事。

比的是「纯执行」，所以把启动开销扣掉：
  解释器：python starlang.py xxx.star
  编译器：python starlangc.py xxx.star --quiet
两边都包含 Python 解释器启动，公平。
另外额外给出「编译一次、之后直接跑生成的 .py」的数字 —— 那才是编译器真正的上限。
"""
import os
import subprocess
import sys
import time

本目录 = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

基准 = {
    "递归.star": (
        "定义 斐波(n)\n{\n如果 n < 2\n{\n返回 n\n}\n"
        "返回 斐波(n - 1) + 斐波(n - 2)\n}\n打印 斐波(26)\n"
    ),
    "循环.star": (
        "合 = 0\n序 = 0\n只要 序 < 500000\n{\n合 = 合 + 序\n序 = 序 + 1\n}\n打印 合\n"
    ),
    "字符串.star": (
        "文 = \"\"\n序 = 0\n只要 序 < 20000\n{\n文 = 文 + \"星\"\n序 = 序 + 1\n}\n打印 长度(文)\n"
    ),
}


def 计时(命令, 次数=1):
    最好 = 1e9
    for _ in range(次数):
        t = time.perf_counter()
        r = subprocess.run(命令, cwd=本目录, capture_output=True,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        dt = time.perf_counter() - t
        if r.returncode != 0:
            return None, r.stderr.decode("utf-8", "replace")[:300]
        if dt < 最好:
            最好 = dt
    return 最好, None


def main():
    print("=" * 62)
    print("  解释器 vs 编译器（取 3 次里最快的一次，已含 Python 启动开销）")
    print("=" * 62)
    print()

    for 文件名, 源码 in 基准.items():
        with open(os.path.join(本目录, 文件名), "w", encoding="utf-8") as f:
            f.write(源码)

    print("  %-12s %10s %10s %10s %10s" % ("测试", "解释器", "编译器", "虚拟机", "直接跑.py"))
    print("  " + "-" * 62)

    for 文件名 in 基准:
        解, 解错 = 计时([PY, "-u", "starlang.py", 文件名])
        编, 编错 = 计时([PY, "-u", "starlangc.py", 文件名, "--quiet"])
        VM, VM错 = 计时([PY, "-u", "starlangvm.py", 文件名])

        if 解 is None or 编 is None or VM is None:
            print("  %-12s  出错：%s" % (文件名, (解错 or 编错 or VM错 or "").split("\n")[0]))
            continue

        # 生成 .py，之后直接跑它
        产物 = "_基准_" + 文件名.replace(".star", "") + ".py"
        subprocess.run([PY, "starlangc.py", 文件名, "--quiet", "--out", 产物],
                       cwd=本目录, capture_output=True)
        直, 直错 = 计时([PY, "-u", 产物])

        if 直 is None:
            print("  %-12s  生成文件跑不动" % 文件名)
            continue

        print("  %-12s %9.3fs %9.3fs %9.3fs %9.3fs"
              % (文件名, 解, 编, VM, 直))
        os.remove(os.path.join(本目录, 产物))
        os.remove(os.path.join(本目录, 文件名))

    print()
    print("  直接跑.py = 编译一次、之后当普通 Python 跑 —— 那才是编译器的上限")


if __name__ == "__main__":
    main()
