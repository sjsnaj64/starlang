# -*- coding: utf-8 -*-
"""验证缩减.py —— 检验「缩减器」本身靠不靠谱

    python 验证缩减.py

★★ 为什么缩减器也需要验证？

    缩减器是个「会自己删代码」的工具。它要是坏了，有两种坏法：
        · 删太狠  → 把 bug 也删掉了，缩出来的程序跑着没问题（假阴性）
        · 删太少  → 留一堆无关代码，等于没用

    这两种坏法都不会报错，只会安安静静给你一个不太对的结果 ——
    比直接崩掉危险得多。所以要有个「已知答案」的考题。

★★ 考题怎么造：往真虚拟机里注入一个真 bug

    复制一份 starlangvm.py，把比较里的「<=」错写成「<」。
    这是真正的语义错误（不是字符串匹配那种假 bug），
    所以三家真的会算出不同结果，缩减器面对的是真实的失败场景。

    然后挑一个能触发它的随机程序，丢给缩减器，看能不能砍到 10 行以内。

    验收标准：
        · 缩减后 ≤ 10 行          （证明真的在删）
        · 分歧对跟缩减前相同       （证明删的是同一个 bug，不是又冒出个新的）
"""
import io
import os
import sys

本目录 = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, 本目录)

坏文件 = os.path.join(本目录, "_坏虚拟机.py")


def 造坏虚拟机():
    """复制一份虚拟机，让数字加法永远多算 1

    ★ 原来注入的是「把 <= 写成 <」，但那只在两数相等时才露馅 ——
      差分测试的生成器一改（比如加了匿名函数），随机序列就变了，
      400 个种子里可能一个都碰不上，考卷直接失效。
      改成动加法：任何算数的地方都会出错，稳定得多。
    """
    源 = io.open(os.path.join(本目录, "starlangvm.py"), encoding="utf-8").read()
    坏源 = 源.replace("    return a + b\n", "    return a + b + 1\n")
    assert 坏源 != 源, "注入点没找到 —— starlangvm.py 的 _加 改过了？"
    io.open(坏文件, "w", encoding="utf-8", newline="\n").write(坏源)


def main():
    print("=" * 62)
    print("  验证缩减器：往真虚拟机里注入一个真 bug，看它能不能缩到最小")
    print("=" * 62)

    # ── ① 注入 ──
    造坏虚拟机()
    print("\n① 已注入：虚拟机算数字加法时永远多算 1（真的语义错误）")

    # ── ② 让跑三方改用坏虚拟机 ──
    import 差分测试 as D              # noqa: E402
    import _坏虚拟机                    # noqa: E402
    D.starlangvm = _坏虚拟机
    print("② 跑三方已切换到坏虚拟机")

    import 缩减                        # noqa: E402

    # ── ③ 找一个能触发的随机程序 ──
    选 = None
    for 种子 in range(400):
        源码 = 缩减.从种子生成(种子)
        if 缩减.分歧对(源码) is not None:
            选 = (种子, 源码)
            break
    if 选 is None:
        print("③ 400 个种子里都没触发 —— 注入的 bug 太隐蔽，换个注入点")
        return 1

    种子, 源码 = 选
    原行数 = len(源码.split("\n"))
    原分歧 = 缩减.分歧对(源码)
    print("③ 触发程序：种子 %d，%d 行" % (种子, 原行数))
    print("   分歧：%s" % "、".join("≠".join(p) for p in sorted(原分歧)))

    # ── ④ 缩减 ──
    最小, 报告 = 缩减.缩减(源码, 原分歧)
    新行数 = len(最小.split("\n"))
    print("\n④ 缩减结果：%d 行 → %d 行" % (原行数, 新行数))
    print("   " + "─" * 46)
    for 行 in 最小.split("\n"):
        print("   " + 行)
    print("   " + "─" * 46)
    print("   尝试次数：%d" % 缩减._尝试[0])

    确认 = 缩减.分歧对(最小)
    print("   缩减后分歧：%s"
          % ("、".join("≠".join(p) for p in sorted(确认)) if 确认 else "无"))

    # ── ⑤ 判卷 ──
    通过 = []
    if 确认 is None:
        通过.append("❌ 缩减后三方一致了 —— 把 bug 也删掉了（删太狠）")
    elif 确认 != 原分歧:
        通过.append("❌ 分歧对变了 —— 缩出来的是另一个 bug（漂移了）")
    else:
        通过.append("✅ 还是原来那个 bug")

    if 新行数 <= 10:
        通过.append("✅ 砍到 %d 行，够小了" % 新行数)
    else:
        通过.append("❌ 还剩 %d 行 —— 删得太保守" % 新行数)

    print()
    for 行 in 通过:
        print("  " + 行)
    好 = all(x.startswith("✅") for x in 通过)
    print()
    print("验证通过 🐾" if 好 else "验证没通过，缩减器要修")
    return 0 if 好 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        if os.path.isfile(坏文件):
            os.remove(坏文件)       # 注入的产物，用完就扔
