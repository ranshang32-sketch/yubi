"""
字体覆盖.py —— 把"面板上能画哪些字"这件事变成可复现的实测数据

为什么要有它：
    面板上出现一串问号，这是**字体**的问题，不是数据的问题：
    官方 Studio 只装 Atkinson Hyperlegible（纯拉丁）+ FontAwesome，
    ImGui 遇到图集里没有的字符会回退画 `?`。
    以后官方升级 mujoco（换了字体/加了 CJK 范围），这张表就会变 ——
    所以把它做成脚本，随时能重测，而不是靠记忆。

它做什么：
    ① 读官方 assets 里的 3 个 .ttf，用 fontTools 读 cmap，逐字符核对
       "面板常用字（中文/符号/拉丁）到底有没有字形"
    ② 顺手静态扫一遍 软件/面板/*.py：把"会被画出来"的字符串字面量里
       字体画不出来的字符全列出来（0 处才算干净）

跑法：
    .venv/bin/python 优化/验证/字体覆盖.py
    # 输出同时写入 优化/验证/字体覆盖_实测.txt
"""
from __future__ import annotations

import glob
import os
import re
import sys

本目录 = os.path.dirname(os.path.abspath(__file__))
包根 = os.path.dirname(os.path.dirname(本目录))
软件目录 = os.path.join(包根, "软件")
if 软件目录 not in sys.path:
    sys.path.insert(0, 软件目录)

资源目录 = os.path.join(包根, ".venv", "lib",
                    f"python{sys.version_info.major}.{sys.version_info.minor}",
                    "site-packages", "mujoco", "experimental", "studio", "assets")

字体们 = ["AtkinsonHyperlegibleNext[wght].ttf", "AtkinsonHyperlegibleMono-Regular.ttf",
        "fontawesome-webfont.ttf"]

测试字集 = {
    "中文常用字": "当前外观皮肤选配色预览按钮模型库空场景刷新列表数据录制参数辨识关于监控"
                "空闲录制中采样中辨识中就绪等待加载不支持机械臂切换到误差峰值已录行数"
                "从本地导入重新刷新路径不存在文件拖进窗口格式读期望位置软件风格表命令行",
    "制表/标记符": "●○✓✗←→·…｜（）【】「」±°",
    "拉丁/数字": "Appearance Minimal Modern Dark FPS 0123456789 ():;.%_-/[]",
}

# 静态扫描：只认"会被画出来"的字面量
画的调用 = re.compile(r"imgui\.(Text|TextColored|TextDisabled|TextWrapped|Button|SmallButton|"
                  r"Selectable|Checkbox|BulletText|Begin|SetItemTooltip|SetTooltip)\s*\(")


def 主() -> int:
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        print("✗ 需要 fontTools（pip install fonttools）——本地 .venv 里已有")
        return 2

    import 界面文字
    允许 = 界面文字.允许的非ASCII

    行们: list[str] = []
    行们.append("字体覆盖实测（面板上能画哪些字）")
    行们.append(f"字体目录：{资源目录}")
    行们.append(f"环境：mujoco 3.13.0 / Python {sys.version.split()[0]}")
    行们.append("")
    行们.append("判据：Atkinson Hyperlegible 原本是纯拉丁字体（362 个码位）；ImGui 缺字形时回退画 "
              f"`ImFont::FallbackChar`（默认 '?'）→ 面板上就是问号。")
    行们.append("      ★ 若主字体已被 `工具/打补丁_中文字体.py` 补上汉字字形，"
              "本表里「中文常用字」会变成 ✓ 全有 —— 那不是错，是补丁生效了。")
    行们.append("")

    缺集中: set[str] = set()
    for 名 in 字体们:
        路径 = os.path.join(资源目录, 名)
        if not os.path.exists(路径):
            行们.append(f"⚠ 找不到字体：{名}")
            continue
        f = TTFont(路径, fontNumber=0, lazy=True)
        cmap = f.getBestCmap()
        行们.append(f"── {名}（{f['maxp'].numGlyphs} 个字形 / cmap {len(cmap)} 个码位）")
        for 类, 文本 in 测试字集.items():
            缺 = "".join(sorted({c for c in 文本 if ord(c) not in cmap}))
            缺集中.update(缺)
            if 缺:
                行们.append(f"     {类:10s}：✗ 缺 {len(set(缺))} 个 → {''.join(sorted(set(缺)))}")
            else:
                行们.append(f"     {类:10s}：✓ 全有")
        行们.append("")

    主字体汉字 = 0
    try:
        _cm = TTFont(os.path.join(资源目录, 字体们[0]), fontNumber=0, lazy=True).getBestCmap()
        主字体汉字 = sum(1 for cp in _cm if 0x4e00 <= cp <= 0x9fff)
    except Exception:                                                    # noqa: BLE001
        pass
    if 主字体汉字 > 0:
        行们.append(f"结论：★ 主 UI 字体**已打中文字体补丁**（{主字体汉字} 个汉字码位）"
                   f" → 面板可以显示中文。")
        行们.append("     → 打开/还原：`.venv/bin/python 工具/打补丁_中文字体.py`"
                   "（`--还原` 退回官方原样）")
        行们.append(f"     → 未打补丁时面板只允许 ASCII，外加这些符号：{允许}")
    else:
        行们.append(f"结论：官方字体一共缺 {len(缺集中)} 个面板常用字符"
                   f"（含全部中文与 ●○✓✗←→｜（））")
        行们.append(f"     → 面板上只允许 ASCII，外加这些 Atkinson 确实有的符号：{允许}")
        行们.append("     → 想让面板显示中文：`.venv/bin/python 工具/打补丁_中文字体.py`")
    行们.append("")
    行们.append("=" * 78)
    行们.append("静态扫描：软件/面板/*.py 里『会被画出来』的字面量是否都画得出来")
    行们.append("=" * 78)

    总坏 = 0
    for 路径 in sorted(glob.glob(os.path.join(软件目录, "面板", "*.py"))):
        坏 = []
        在文档串 = False          # 文档字符串里的示例不是"画出来的"，要跳过
        for i, 行 in enumerate(open(路径, encoding="utf-8"), 1):
            s = 行.strip()
            if 在文档串:
                if '"""' in s:
                    在文档串 = False
                continue
            if s.count('"""') % 2 == 1:      # 这一行开了文档字符串
                在文档串 = True
                continue
            if s.startswith("#") or not 画的调用.search(s):
                continue
            s2 = re.sub(r"\[[^\]]*\]", "", s)          # 去掉 字典["键"]，那不是在画字
            s2 = re.sub(r'\.get\(\s*"[^"]*"', ".get(", s2)   # 去掉 .get("键") 的键名
            for m in re.finditer(r'f?"([^"\\]*)"', s2):
                文 = re.sub(r"\{[^{}]*\}", "", m.group(1))   # 去掉 f-string 的 {表达式}
                不 = "".join(sorted({c for c in 文 if not 界面文字.可用(c)}))
                if 不:
                    坏.append((i, 不, 文[:56]))
        if 坏:
            总坏 += len(坏)
            行们.append(f"  ✗ {os.path.basename(路径)}：{len(坏)} 处会被画成 ?")
            for i, 不, 文 in 坏:
                行们.append(f"      L{i:<4} 缺[{不}]  {文}")
        else:
            行们.append(f"  ✓ {os.path.basename(路径)}：干净")
    行们.append("")
    行们.append(f"结论：{'✓ 全部干净（面板不会出现问号）' if 总坏 == 0 else f'✗ 共 {总坏} 处要改'}")

    文本 = "\n".join(行们)
    输出 = os.path.join(本目录, "字体覆盖_实测.txt")
    with open(输出, "w", encoding="utf-8") as f:
        f.write(文本 + "\n")
    print(文本)
    print(f"\n（已写入 {输出}）")
    return 0 if 总坏 == 0 else 1


if __name__ == "__main__":
    raise SystemExit(主())
