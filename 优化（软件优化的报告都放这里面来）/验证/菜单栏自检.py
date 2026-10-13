"""菜单栏挂载点自检（不需要开窗口）：验证"包装幂等 / 无上下文不崩 / 外观开关持久化"。

用法：./.venv/bin/python "优化（软件优化的报告都放这里面来）/验证/菜单栏自检.py"

★ 为什么这些用例必须能不开窗跑：菜单栏的挂载发生在窗口起来之前，而自检脚本自己
  没有 ImGui 上下文 —— 那个绑定在没有上下文时调用任何 imgui 函数会**直接段错误**，
  所以"无上下文时什么都不做"本身就是一条必须守住的契约。
"""
from __future__ import annotations

import os
import sys
import tempfile

包根 = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
面板目录 = os.path.join(包根, "软件", "面板")
for p in (os.path.join(包根, "软件"), 面板目录):
    if p not in sys.path:
        sys.path.insert(0, p)

from mujoco.experimental.dear_imgui import dear_imgui as imgui       # noqa: E402

import 皮肤桥                                                        # noqa: E402
import 菜单栏                                                        # noqa: E402

通过 = 0
失败 = 0
原结束菜单栏 = imgui.EndMainMenuBar
原存档路径 = 皮肤桥.存档路径
临时目录 = tempfile.mkdtemp(prefix="菜单栏自检_")


def 用例(名: str, 条件: bool, 说明: str = "") -> None:
    global 通过, 失败
    if 条件:
        通过 += 1
        print(f"  ✓ {名}")
    else:
        失败 += 1
        print(f"  ✗ {名}{('  —— ' + 说明) if 说明 else ''}")


def 主() -> int:
    print("菜单栏挂载点自检")
    print(f"  临时存档：{临时目录}")

    # ---- ① 安装包装：幂等，且调用时原函数仍被调用 ----
    计数 = {"原": 0}

    def 假原函数():
        计数["原"] += 1

    imgui.EndMainMenuBar = 假原函数
    菜单栏.安装包装()
    菜单栏.安装包装()
    菜单栏.安装包装()
    用例("包装只装一层（连调 3 次）", 计数["原"] == 0, "还没调用就被调用了？")

    # ---- ② 无 ImGui 上下文时调用：不崩，且原函数照常被调用 ----
    崩了 = ""
    try:
        imgui.EndMainMenuBar()               # 此刻没有上下文
    except Exception as 异常:                                                # noqa: BLE001
        崩了 = f"{type(异常).__name__}: {异常}"
    用例("无上下文调用不抛异常", 崩了 == "", 崩了)
    用例("无上下文时原函数仍被调用一次", 计数["原"] == 1, f"实际 {计数['原']}")

    # ---- ③ 外观面板开关：默认关、写入后读回 ----
    皮肤桥.存档路径 = os.path.join(临时目录, "外观.json")
    用例("完整面板默认关", 皮肤桥.完整面板可见() is False)
    菜单栏.设外观面板可见(True)
    用例("设成开后能读回", 皮肤桥.完整面板可见() is True)
    菜单栏.设外观面板可见(False)
    用例("设成关后能读回", 皮肤桥.完整面板可见() is False)

    # ---- ④ 旧格式存档（只有"风格"键）不得报错 ----
    可选 = 皮肤桥.选择项()
    旧风格 = 可选[0] if 可选 else 皮肤桥.关闭
    with open(皮肤桥.存档路径, "w", encoding="utf-8") as f:
        f.write('{"风格": "%s"}' % 旧风格)
    用例("旧格式存档：风格读得回来", 皮肤桥.读取存档() == 旧风格)
    用例("旧格式存档：新开关按默认关处理", 皮肤桥.完整面板可见() is False)

    # ---- ⑤ 菜单数据：5 套风格 + 关，当前项唯一选中 ----
    数据 = 菜单栏.菜单数据()
    皮肤条目 = 数据.get("皮肤") or []
    用例("皮肤条目数 = 选择项数", len(皮肤条目) == len(皮肤桥.选择项()),
         f"{len(皮肤条目)} vs {len(皮肤桥.选择项())}")
    选中数 = sum(1 for 条 in 皮肤条目 if 条[2])
    当前 = 皮肤桥.当前风格
    期望选中 = 1 if 当前 in [条[0] for 条 in 皮肤条目] else 0
    用例("当前风格唯一打勾", 选中数 == 期望选中, f"选中 {选中数}，期望 {期望选中}")
    基底条目 = 数据.get("基底") or []
    用例("基底主题 3 项（Light/Dark/Classic）", len(基底条目) == 3)
    用例("基底当前项唯一打勾", sum(1 for 条 in 基底条目 if 条[2]) == 1)
    用例("菜单数据带外观面板开关", isinstance(数据.get("外观面板"), bool))

    print(f"\n结果：{通过} 通过 / {失败} 失败")
    return 1 if 失败 else 0


if __name__ == "__main__":
    try:
        码 = 主()
    finally:
        imgui.EndMainMenuBar = 原结束菜单栏
        皮肤桥.存档路径 = 原存档路径
    sys.exit(码)
