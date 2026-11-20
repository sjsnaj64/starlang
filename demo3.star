# 星语 Step 3 演示：if / else / while
# 运行:  python starlang.py demo3.star
# 透视:  python starlang.py --all demo3.star

# ---- 1. 判断 ----
分 = 85
if 分 >= 60 {
    print 1
} else {
    print 0
}

# ---- 2. 累加 1..5 ----
i = 1
总和 = 0
while i <= 5 {
    总和 = 总和 + i
    i = i + 1
}
print 总和

# ---- 3. 嵌套循环：3x3 乘法表 ----
行 = 1
while 行 <= 3 {
    列 = 1
    当 列 <= 3 {
        print 行 * 列
        列 = 列 + 1
    }
    行 = 行 + 1
}

# ---- 4. 斐波那契第 10 项 ----
a = 0
b = 1
n = 0
while n < 10 {
    t = a + b
    a = b
    b = t
    n = n + 1
}
print a

# ---- 5. else 另起一行也认（靠"偷看+回退"实现）----
x = 5
if x > 10 {
    print 100
}
else {
    print 200
}

# ---- 6. 死循环保险丝（去掉下一段的注释试试）----
# while 1 {
#     x = x + 1
# }
