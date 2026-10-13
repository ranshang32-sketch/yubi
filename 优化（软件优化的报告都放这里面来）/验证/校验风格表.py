"""
校验风格表.py —— 逐键校验 优化/风格表.json 是否只用了真实存在的枚举项

为什么必须校验：
    风格表里的键名（Col.Button / StyleVar.WindowRounding / implot.Col.PlotBg …）
    全部要写进 `getattr(imgui.Col, 键名)`。**写错一个字母，换肤那一行就抛
    AttributeError**。所以这里把 5 套风格 × 所有键逐条与绑定里的真实枚举对一遍，
    并且顺便验证颜色字符串能被解析成合法 RGBA。

跑法：
    .venv/bin/python 优化/验证/校验风格表.py
"""
from __future__ import annotations

import json
import os
import re
import sys

本目录 = os.path.dirname(os.path.abspath(__file__))
包根 = os.path.dirname(os.path.dirname(本目录))
软件目录 = os.path.join(包根, "软件")
if 软件目录 not in sys.path:
    sys.path.insert(0, 软件目录)

from mujoco.experimental.dear_imgui import dear_imgui as imgui            # noqa: E402
from mujoco.experimental.implot import implot                            # noqa: E402

if 软件目录 not in sys.path:
    sys.path.insert(0, 软件目录)
import 界面文字                                                        # noqa: E402


def 枚举名(类) -> set[str]:
    return {v for v in dir(类) if not v.startswith("_") and v not in ("name", "value")}


Imgui颜色 = 枚举名(imgui.Col)
ImGui样式 = 枚举名(imgui.StyleVar)
Implot颜色 = 枚举名(implot.Col)
Implot样式 = 枚举名(implot.StyleVar)

错误: list[str] = []
警告: list[str] = []
统计 = {"颜色": 0, "样式": 0, "曲线颜色": 0}


def 校验颜色(路径: str, 值) -> None:
    if not isinstance(值, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?", 值):
        错误.append(f"{路径}：颜色格式不对（要 #RRGGBB 或 #RRGGBBAA）：{值!r}")
    统计["颜色"] += 1


def 校验数值(路径: str, 值, 变量名: str) -> None:
    if 变量名 in ("WindowPadding", "FramePadding", "ItemSpacing", "ItemInnerSpacing",
                  "CellPadding", "WindowTitleAlign", "ButtonTextAlign",
                  "SeparatorTextPadding", "WindowMinSize",
                  "PlotPadding", "LabelPadding", "LegendPadding", "LegendInnerPadding",
                  "AnnotationPadding", "DigitalPadding", "MousePosPadding",
                  "PlotDefaultSize", "PlotMinSize"):
        if not (isinstance(值, list) and len(值) == 2
                and all(isinstance(v, (int, float)) for v in 值)):
            错误.append(f"{路径}：{变量名} 需要 [x, y] 两个数：{值!r}")
    elif not isinstance(值, (int, float)):
        错误.append(f"{路径}：{变量名} 需要数字：{值!r}")
    统计["样式"] += 1


def main() -> int:
    表路径 = os.path.join(包根, "软件", "风格表.json")      # ★ 实现用的那一份（应用读它）
    镜像路径 = os.path.join(包根, "优化", "风格表.json")     # 审查期快照，两边必须一致
    with open(表路径, encoding="utf-8") as f:
        表 = json.load(f)

    # 两份风格表必须逐字节一致，否则"改了一份、跑的是另一份"这种坑迟早出现
    if os.path.exists(镜像路径):
        甲 = open(表路径, "rb").read()
        乙 = open(镜像路径, "rb").read()
        if 甲 != 乙:
            错误.append(f"软件/风格表.json 与 优化/风格表.json 不一致（{len(甲)} vs {len(乙)} 字节）"
                        f" —— 应用读的是 软件/ 那一份，请同步")
        else:
            print(f"✓ 两份风格表一致（软件/ 与 优化/，{len(甲)} 字节）")
    print()

    风格们 = 表["风格"]
    print(f"读入风格表：{len(风格们)} 套风格 —— {'、'.join(风格们)}")
    print(f"绑定里的可用枚举：imgui.Col {len(Imgui颜色)} 项 / imgui.StyleVar {len(ImGui样式)} 项 / "
          f"implot.Col {len(Implot颜色)} 项 / implot.StyleVar {len(Implot样式)} 项\n")

    for 名, 风格 in 风格们.items():
        print(f"── {名}（{风格.get('显示名','?')}）")
        # 颜色
        for 键, 值 in 风格.get("颜色", {}).items():
            if 键 not in Imgui颜色:
                错误.append(f"{名}.颜色.{键}：imgui.Col 里没有这个枚举项（最接近的："
                            f"{sorted(x for x in Imgui颜色 if 键[:5].lower() in x.lower())[:3]}）")
            校验颜色(f"{名}.颜色.{键}", 值)
        # 样式
        for 键, 值 in 风格.get("样式", {}).items():
            if 键 not in ImGui样式:
                错误.append(f"{名}.样式.{键}：imgui.StyleVar 里没有这个枚举项")
            校验数值(f"{名}.样式", 值, 键)
        # 曲线
        曲线 = 风格.get("曲线", {})
        for 键, 值 in 曲线.get("implot", {}).items():
            if 键 not in Implot颜色:
                错误.append(f"{名}.曲线.implot.{键}：implot.Col 里没有这个枚举项")
            校验颜色(f"{名}.曲线.implot.{键}", 值)
        for 键, 值 in 曲线.get("曲线样式", {}).items():
            if 键 not in Implot样式:
                错误.append(f"{名}.曲线.曲线样式.{键}：implot.StyleVar 里没有这个枚举项")
            校验数值(f"{名}.曲线.曲线样式", 值, 键)
        调色板 = 曲线.get("调色板", [])
        for i, 值 in enumerate(调色板):
            校验颜色(f"{名}.曲线.调色板[{i}]", 值)
        if len(调色板) != 8:
            警告.append(f"{名}.曲线.调色板 有 {len(调色板)} 色（曲线基类默认 8 色，可改但要对齐）")
        print(f"   颜色 {len(风格.get('颜色',{}))} 项 / 样式 {len(风格.get('样式',{}))} 项 / "
              f"曲线颜色 {len(曲线.get('implot',{}))} 项 / 曲线样式 {len(曲线.get('曲线样式',{}))} 项 / "
              f"调色板 {len(调色板)} 色")

    # ★ 面板上会画的字段必须是纯 ASCII（官方 UI 字体没有中文字形，中文会变成 ?）
    #   中文的 显示名/一句话 只给终端与文档用，面板用 英文名/英文说明。
    for 名, 风格 in 风格们.items():
        for 字段 in ("英文名", "英文说明"):
            值 = str(风格.get(字段) or "")
            if not 值:
                错误.append(f"{名}.{字段} 缺失 —— 面板上要显示它（中文会画成 ?）")
            elif not 界面文字.可用(值):
                错误.append(f"{名}.{字段} 含字体画不出来的字符：{值!r}")
        if not 界面文字.可用(str(风格.get("基底主题") or "")):
            错误.append(f"{名}.基底主题 含画不出来的字符")

    # 基底主题必须是官方认得的
    合法基底 = {"dark", "light", "classic"}
    for 名, 风格 in 风格们.items():
        if 风格.get("基底主题") not in 合法基底:
            错误.append(f"{名}.基底主题={风格.get('基底主题')!r}，官方只认 {合法基底}")

    print()
    if 警告:
        print(f"⚠ {len(警告)} 条提醒：")
        for w in 警告:
            print("   · " + w)
    if 错误:
        print(f"\n✗ {len(错误)} 处错误：")
        for e in 错误:
            print("   · " + e)
        return 1
    print(f"✓ 全部通过：{统计['颜色']} 个颜色值 + {统计['样式']} 个样式值，"
          f"没有用到不存在的枚举项，颜色格式全部合法")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
