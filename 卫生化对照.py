# -*- coding: utf-8 -*-
"""_对照卫生化.py —— 临时脚本，用来证明卫生化真的在干活。

跑两遍 demo15.star：
  ① 正常（开着卫生化）
  ② 把 收集局部绑定 换成「永远返回空集」= 假装没有卫生化
然后看 ② 错成什么样。
"""
import os
import subprocess
import sys

本目录 = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

脏版 = (
    "import sys, starlang\n"
    "starlang.收集局部绑定 = lambda 语句们, 结果=None: set()\n"
    "starlang._gensym[0] = 0\n"
    "sys.argv = ['starlang.py', 'demo15.star']\n"
    "starlang.main()\n"
)


def 跑(命令):
    return subprocess.run(命令, cwd=本目录, capture_output=True,
                          env=dict(os.environ, PYTHONIOENCODING="utf-8"))


def 净(文本):
    行们 = []
    for 行 in 文本.replace("\r\n", "\n").split("\n"):
        if 行.startswith("──") or 行.strip().startswith("· "):
            continue
        if 行.strip():
            行们.append(行.rstrip())
    return 行们


a = 净(跑([PY, "-u", "starlang.py", "demo15.star"]).stdout.decode("utf-8", "replace"))
b = 净(跑([PY, "-u", "-c", 脏版]).stdout.decode("utf-8", "replace"))

print("=" * 78)
print("  左：开着卫生化（正确）        右：关掉卫生化（不卫生的旧行为）")
print("=" * 78)
print()
for i in range(max(len(a), len(b))):
    x = a[i] if i < len(a) else ""
    y = b[i] if i < len(b) else ""
    标 = "  " if x == y else "❗"
    print("%s %-40s | %s" % (标, x, y))

print()
print("❗ = 两边不一样 —— 那些行就是「名字撞车」造成的后果")
