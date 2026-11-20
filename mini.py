def frequencySort(s:str) -> str:
    ferq = {}
    for i in s:
        if i in ferq:
            ferq[i] += 1
        else:
            ferq[i] = 1
    bucket = [[] for _ in range(len(s)+1)]
    for char, count in ferq.items():
        bucket[count].append(char)
    res = []
    for i in range(len(bucket)-1, -1, -1):
        for char in bucket[i]:
            res.append(char*i)
    return "".join(res)
test = "tree"
print(frequencySort(test))

# bucket = []
# for item in range(len(s)+1):
#     bucket.append([])
# a = [1,2,3,4,5]
# a[1]
# a[0].append(1)
# a:1