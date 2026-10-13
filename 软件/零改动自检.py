"""
零改动自检.py —— 验收工具：证明「加控制算法不需要改外壳」

背景：第 2 步的验收标准是"新增算法 = 新建一个 py 文件 + 在列表加一个名字，主程序零改动"。
      这句话必须**能验证**，不能靠嘴说 —— 这个脚本就是干这个的。

原理：
    外壳的 4 个核心文件（插件系统.py / 启动.py / 界面桥.py 的哈希，以及主程序.py 里
    【插件清单】那一段的哈希）被记在 `外壳指纹.json` 里。
    跑 `python 零改动自检.py --建立` 记录指纹；之后任何时候跑 `python 零改动自检.py`
    就能看出核心逻辑有没有被改动过。

用法（在 03_实施 目录下）：
    .venv/bin/python 软件/零改动自检.py --建立     # 第一次记录指纹
    .venv/bin/python 软件/零改动自检.py            # 之后随时校验
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

本目录 = os.path.dirname(os.path.abspath(__file__))
指纹文件 = os.path.join(本目录, "外壳指纹.json")

# 核心逻辑文件：这些应该永远不变
核心文件 = ["插件系统.py", "启动.py", "界面桥.py"]
# 允许你改的地方：主程序.py 里的【插件清单】区段（改它是正常的，加算法就要改它）
清单文件 = "主程序.py"


def 文件哈希(路径: str) -> str:
    with open(路径, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def 清单区段哈希(路径: str) -> str:
    """只取 `主程序.py` 里【算法装配】那一段算哈希。

    ★ 方案 C 之前这里抓的是【插件清单】（一份硬编码的算法列表）。
      现在算法改由 `项目/*.json` 声明，"加算法"要动的是**项目文件**而不是本文件，
      所以这一段理论上可以做到真正的零改动；保留它作为哈希项，是为了看住
      "启动装配这段逻辑"有没有被悄悄改掉（它是启动路径的关键一环）。

    ★ 抓不到区段时**不能**退化成"整个文件" —— 那会让本项检查的含义从
      "装配逻辑没动"变成"主程序一个字符都不能动"，两者完全不是一回事，
      而且后者会在每次改注释时误报（第一版就是这么写的，实测撞上）。
      抓不到就直接报出来，让人去修这个正则。
    """
    源码 = open(路径, encoding="utf-8").read()
    匹配 = re.search(r"# 【算法装配】.*?\n(.*?)\n\n\n", 源码, re.S)
    if 匹配 is None:
        # 用显式哨兵值而不是"整个文件"：哨兵不匹配任何东西 → 自检会报"区段找不到"，
        # 而不是伪装成"文件被改了"或"一切正常"。
        return "区段未找到"
    区段 = 匹配.group(1)
    return hashlib.sha256(区段.encode("utf-8")).hexdigest()[:16]


def 采集指纹() -> dict:
    指纹 = {"核心文件": {}, "算法装配区段": 清单区段哈希(os.path.join(本目录, 清单文件))}
    for 名 in 核心文件:
        指纹["核心文件"][名] = 文件哈希(os.path.join(本目录, 名))
    # 顺便记下算法目录清单（新增算法会让它变化 —— 这是**应该**变化的）
    #
    # ★ 方案 C 之后算法在 `<包根>/算法库/`（原来是 `算法库/通用/`）。
    #   两个目录都扫：老目录还没清空时不至于漏掉。
    包根 = os.path.dirname(本目录)
    算法名: list[str] = []
    for 目录 in (os.path.join(包根, "算法库"), os.path.join(本目录, "plugins")):
        if not os.path.isdir(目录):
            continue
        for 当前, 子目录们, 文件们 in os.walk(目录):
            子目录们[:] = [d for d in 子目录们
                          if not d.startswith(("_", ".")) and d != "__pycache__"]
            算法名.extend(f for f in 文件们
                         if f.endswith(".py") and not f.startswith("_"))
    指纹["插件文件"] = sorted(算法名)
    return 指纹


def main() -> int:
    ap = argparse.ArgumentParser(description="外壳零改动自检")
    ap.add_argument("--建立", action="store_true", help="记录当前指纹为基准")
    args = ap.parse_args()

    当前 = 采集指纹()

    if args.建立 or not os.path.exists(指纹文件):
        with open(指纹文件, "w", encoding="utf-8") as f:
            json.dump(当前, f, ensure_ascii=False, indent=2)
        print(f"✓ 已记录外壳指纹 → {os.path.basename(指纹文件)}")
        print(f"  核心文件：{', '.join(当前['核心文件'])}")
        print(f"  算法装配区段哈希：{当前['算法装配区段']}")
        print(f"  当前插件：{', '.join(当前['插件文件']) or '（无）'}")
        return 0

    基准 = json.load(open(指纹文件, encoding="utf-8"))
    结论 = []

    for 名 in 核心文件:
        旧 = 基准["核心文件"].get(名)
        新 = 当前["核心文件"].get(名)
        if 旧 == 新:
            结论.append(("✓", f"{名} 未改动", 新))
        else:
            结论.append(("✗", f"{名} 被改动了（核心逻辑本该保持不变！）", f"{旧} → {新}"))

    # ★ 区段抓不到时明确报出来（见 清单区段哈希 的说明）—— 不能伪装成"未改动"
    旧, 新 = 基准.get("算法装配区段", "（旧基准没有这一项）"), 当前["算法装配区段"]
    if 新 == "区段未找到":
        结论.append(("✗", f"{清单文件} 里找不到【算法装配】区段（正则要跟着改）", 新))
    else:
        结论.append(("–", f"{清单文件} 的【算法装配】区段" +
                     ("未改动" if 旧 == 新 else "有改动"), f"{旧} → {新}"))

    旧插件 = set(基准.get("插件文件", []))
    新插件 = set(当前["插件文件"])
    新加的 = 新插件 - 旧插件

    print("=" * 72)
    print("外壳零改动自检")
    print("=" * 72)
    for 号, 说明, 值 in 结论:
        print(f"  {号} {说明}")
        if 号 == "✗":
            print(f"      哈希：{值}")
        elif "有改动" in 说明:
            print(f"      哈希：{值}")

    if 新加的:
        print("\n  ★ 新增的插件（这正是「加算法」该有的样子）：")
        for f in sorted(新加的):
            print(f"      算法库/{f}")

    print("\n  结论：" + ("核心逻辑零改动 ✅（验收标准成立）"
                        if all(号 != "✗" for 号, _, _ in 结论) else
                        "核心逻辑被改动了 ❌ —— 请检查改动是否必要"))
    print("\n  提示：方案 C 之后「加算法」= 把 .py 放进 算法库/ 并在项目文件里写上它，")
    print("        **本文件与 主程序.py 都不用改**。所以正常情况下这里应该全绿，")
    print("        只在核心文件被有意改动后才需要跑 `--建立` 重刷基准（并在 CHANGELOG 记一行）。")
    return 0 if all(号 != "✗" for 号, _, _ in 结论) else 1


if __name__ == "__main__":
    raise SystemExit(main())
