"""
皮肤桥.py —— 面板外观换肤的引擎（纯工具模块，**没有** `面板类`）

它解决什么问题：
    需求是"改面板样式（按钮、边框…），并且能在几种风格之间切换"。
    官方 Studio 的界面全部由 ImGui 画，而**这个绑定没有"设置一次就全局生效"的入口**：
        · `GetStyle()` 只暴露 3 个可写字段（实测 AttributeError 一片）
        · 没有 `SetStyleColor` / `SetStyleVar`
    所以唯一的机制是 **每帧推入样式、画完再弹出**（ImGui 的样式栈是全局的，
    在"所有窗口 Begin 之前"推入，"所有窗口 End 之后"弹出，就能覆盖整窗口）。

★ 三个关键坑（都是实测出来的，别照直觉改）：

    ① **官方每帧都在重设主题**
       官方 `viewer_app.build_gui()` 第一行就是 `ux.setup_theme(self.theme)`，
       而它是**直接改写全局样式**（不走 push 栈）—— 我们在窗口事件里推入的皮肤
       会被它整片抹掉，于是"我们自己的面板变色了、官方 19 个面板没变"。
       → 解法：把 `ux.setup_theme` **包一层**，官方设完主题我们立刻补推一次。
         代价是"劫持了一个官方函数"，所以：自检里盯住它（骨架/官方接口清单.py），
         并且包装函数一有异常就自动退回"只换自研面板"模式。

    ② **弹出必须排在所有绘制之后**
       官方文档写明"同优先级的处理顺序是 undefined"，而官方 GUI 用的正是
       `INTERNAL(=1)`。所以弹出处理器用 **priority=0**（比 INTERNAL 更低）→ 永远最后一个跑。

    ③ **推入/弹出必须逐帧配对**
       跨帧不弹，ImGui 会报 `Missing PopStyleColor()`（实测：不崩，但刷错误日志，
       而且它在帧末会把多余的那层丢掉）。所以：
         · 每帧开头**无条件把本帧计数清零**（万一上一帧中途抛异常，残留不要在下一帧补弹）
         · 所有推入都在 try 里，成功一次才计一次数 —— 保证弹出的数量和栈里的一致
         · 出错就整帧放弃皮肤（界面回到基底主题），绝不让窗口挂掉

风格从哪来：`软件/风格表.json`（5 套风格，每套 55 个颜色项 + 28 个样式项 + 曲线配色）。
记住你的选择：`输出/外观.json`（和 输出/面板状态.json 同目录同约定）。

谁在用：`面板/外观面板.py`（每帧调用 帧开始()/帧结束()，并画切换界面）。
"""
from __future__ import annotations

import json
import os
import re

from mujoco.experimental.dear_imgui import dear_imgui as imgui
from mujoco.experimental.implot import implot
from mujoco.experimental.studio import ux

import 界面文字

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
_软件目录 = os.path.dirname(os.path.abspath(__file__))
包根 = os.path.dirname(_软件目录)
风格表路径 = os.path.join(_软件目录, "风格表.json")
存档路径 = os.path.join(包根, "输出", "外观.json")

关闭 = "关"                     # "不推任何皮肤" = 完全回到官方外观
默认风格 = "现代深色"            # 首次启动用哪套（日常干活最舒服的一套）

# 官方主题名（ux.GuiTheme）与字符串的对应
_主题表 = {"LIGHT": ux.GuiTheme.LIGHT, "DARK": ux.GuiTheme.DARK,
           "CLASSIC": ux.GuiTheme.CLASSIC}


# ---------------------------------------------------------------------------
# 颜色：风格表里写 "#RRGGBB" / "#RRGGBBAA"，这里转成 imgui 吃的 Vec4
# ---------------------------------------------------------------------------
def 十六进制转Vec4(文本: str):
    h = str(文本).lstrip("#")
    r, g, b = int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0
    a = int(h[6:8], 16) / 255.0 if len(h) == 8 else 1.0
    return imgui.Vec4(r, g, b, a)


# ---------------------------------------------------------------------------
# 风格表：读一次 → 编译成"可以直接推"的清单（每帧就不用再做 getattr 了）
# ---------------------------------------------------------------------------
_风格表缓存: dict | None = None
_编译缓存: dict[str, dict] = {}
_加载警告: list[str] = []


def 读取风格表() -> dict:
    """读 `软件/风格表.json`（只读一次，之后走缓存）。读不到返回空表。"""
    global _风格表缓存
    if _风格表缓存 is not None:
        return _风格表缓存
    try:
        with open(风格表路径, encoding="utf-8") as f:
            表 = json.load(f)
        _风格表缓存 = 表 if isinstance(表, dict) else {}
    except FileNotFoundError:
        print(f"⚠ 皮肤：找不到风格表 {风格表路径}（换肤功能关闭）")
        _风格表缓存 = {}
    except Exception as 异常:                                          # noqa: BLE001
        print(f"⚠ 皮肤：风格表读取失败（换肤功能关闭）：{type(异常).__name__}: {异常}")
        _风格表缓存 = {}
    return _风格表缓存


def 全部风格() -> list[str]:
    """风格表里定义的全部风格名（顺序 = 表里的顺序）。"""
    return list((读取风格表().get("风格") or {}).keys())


def 选择项() -> list[str]:
    """界面上要列的全部选项：5 套风格 + 「关」。"""
    return 全部风格() + [关闭]


def 显示名(风格: str) -> str:
    if 风格 == 关闭:
        return "官方默认（不换肤）"
    条目 = (读取风格表().get("风格") or {}).get(风格) or {}
    return str(条目.get("显示名") or 风格)


def 一句话(风格: str) -> str:
    if 风格 == 关闭:
        return "完全交给官方主题，回到没有皮肤的样子（退路）"
    return str(((读取风格表().get("风格") or {}).get(风格) or {}).get("一句话") or "")


def 界面名(风格: str) -> str:
    """**面板上**显示的风格名（纯 ASCII）。

    ★ 为什么单开一个函数：官方 UI 字体（Atkinson Hyperlegible）没有中文字形，
      面板上画中文会变成一串 `?`（ImGui 的缺字形回退）。所以面板用英文名，
      中文的 显示名/一句话 只给终端和文档用（终端用系统字体，中文正常）。
      详见 软件/界面文字.py 与 优化（软件优化的报告都放这里面来）/验证/字体覆盖_实测.txt。
    """
    if 风格 == 关闭:
        return "Official (no skin)"
    条目 = (读取风格表().get("风格") or {}).get(风格) or {}
    return str(条目.get("英文名") or "") or 界面文字.英文(显示名(风格))


def 界面说明(风格: str) -> str:
    """**面板上**显示的一句话说明（纯 ASCII）。"""
    if 风格 == 关闭:
        return "Stock theme, no skin applied."
    条目 = (读取风格表().get("风格") or {}).get(风格) or {}
    return str(条目.get("英文说明") or "") or 界面文字.英文(一句话(风格))


def 界面状态行() -> str:
    """面板底部的状态行（纯 ASCII）。"""
    if 当前风格 == 关闭:
        return "skin: off (official appearance)"
    范围 = "official + custom panels" if not 包装是否失效 else "custom panels only (repush disabled)"
    返回 = (f"skin: {界面名(当前风格)} | {范围} | "
          f"frames {统计['帧']} push {统计['推入轮']} repush {统计['补推轮']} "
          f"errors {统计['出错']} degraded {统计['降级帧']}")
    if _加载警告:
        返回 += f" | table warnings {len(_加载警告)} (see terminal)"
    return 返回


def 界面警告数() -> int:
    """风格表里被跳过的坏键条数（面板只显示条数，具体内容打到终端）。"""
    return len(_加载警告)


def 用户基底主题() -> str:
    """用户原本要的官方主题（命令行 --主题 设的，或默认 dark）。"""
    名字 = (os.environ.get("MUJOCO_STUDIO_THEME") or "DARK").strip().upper()
    return 名字 if 名字 in _主题表 else "DARK"


def 基底主题(风格: str) -> str:
    """这套风格该配哪个官方主题当基底（皮肤只覆盖列出的项，其余沿用基底）。"""
    if 风格 == 关闭:
        return 用户基底主题()
    条目 = (读取风格表().get("风格") or {}).get(风格) or {}
    基底 = str(条目.get("基底主题") or "dark").strip().upper()
    return 基底 if 基底 in _主题表 else "DARK"


def _编译一套(风格: str) -> dict:
    """把一套风格编译成 [(枚举值, 值), …]，坏键在这里就被剔掉（只警告一次）。

    ★ 为什么先编译：每帧都要推 55+28+16 项，逐帧做 getattr+字符串解析是白费力气；
      而且**编译期剔除坏键**能保证"推入成功几项 = 计数几项"，弹出数量永远对得上。
    """
    if 风格 in _编译缓存:
        return _编译缓存[风格]
    条目 = (读取风格表().get("风格") or {}).get(风格) or {}
    颜色, 变量, 曲线颜色 = [], [], []
    坏键: list[str] = []

    for 键, 值 in (条目.get("颜色") or {}).items():
        枚举 = getattr(imgui.Col, 键, None)
        if 枚举 is None:
            坏键.append(f"Col.{键}")
            continue
        颜色.append((int(枚举), 十六进制转Vec4(值)))

    for 键, 值 in (条目.get("样式") or {}).items():
        枚举 = getattr(imgui.StyleVar, 键, None)
        if 枚举 is None:
            坏键.append(f"StyleVar.{键}")
            continue
        变量.append((int(枚举), imgui.Vec2(float(值[0]), float(值[1]))
                    if isinstance(值, list) and len(值) == 2 else float(值)))

    曲线 = 条目.get("曲线") or {}
    for 键, 值 in (曲线.get("implot") or {}).items():
        枚举 = getattr(implot.Col, 键, None)
        if 枚举 is None:
            坏键.append(f"implot.Col.{键}")
            continue
        曲线颜色.append((int(枚举), 十六进制转Vec4(值)))

    # ★ 刻意**不**解析 implot 的 StyleVar（曲线图框形状）：本机绑定里
    #   20 项有 9 项会段错误（见 _推入一套 的说明与 优化（软件优化的报告都放这里面来）/验证/implot样式项安全矩阵.txt）。
    #   曲线只换颜色。将来官方修好了再按那张矩阵逐个放开。

    if 坏键:
        行 = f"⚠ 皮肤：风格「{风格}」里有 {len(坏键)} 个枚举项不存在，已跳过：{坏键[:6]}"
        if 行 not in _加载警告:
            _加载警告.append(行)
            print(行)

    编译 = {"颜色": 颜色, "变量": 变量, "曲线颜色": 曲线颜色,
            "调色板": 曲线.get("调色板") or [],
            "按钮色": str((条目.get("颜色") or {}).get("Button") or "#FFFFFF")}
    _编译缓存[风格] = 编译
    return 编译


def 曲线调色板(风格: str) -> list[tuple[float, float, float, float]]:
    """这套风格的 8 色曲线调色板（给 曲线基类 用；风格=关 时返回空表示用默认）。"""
    if 风格 == 关闭:
        return []
    出 = []
    for 文本 in _编译一套(风格)["调色板"]:
        v = 十六进制转Vec4(文本)
        出.append((v.x, v.y, v.z, v.w))
    return 出


# ---------------------------------------------------------------------------
# 存档：输出/外观.json
# ---------------------------------------------------------------------------
def _读取存档字典() -> dict:
    """存档的原始字典（读不出来就给空 dict，永不抛）。"""
    try:
        with open(存档路径, encoding="utf-8") as f:
            数据 = json.load(f)
        return 数据 if isinstance(数据, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as 异常:                                             # noqa: BLE001
        print(f"⚠ 外观存档读取失败（按默认处理）：{type(异常).__name__}: {异常}")
        return {}


def _写入存档字典(数据: dict) -> None:
    try:
        os.makedirs(os.path.dirname(存档路径), exist_ok=True)
        with open(存档路径, "w", encoding="utf-8") as f:
            json.dump(数据, f, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception as 异常:                                             # noqa: BLE001
        print(f"⚠ 外观存档保存失败（不影响使用）：{type(异常).__name__}: {异常}")


def 读取存档() -> str:
    风格 = str(_读取存档字典().get("风格") or "")
    return 风格 if 风格 in 选择项() else ""


def 写入存档(风格: str, *, 完整面板: bool | None = None) -> None:
    """写存档。`完整面板=None` 表示"保持原值"（旧调用点不用改）。"""
    数据 = _读取存档字典()
    数据["风格"] = 风格
    if 完整面板 is not None:
        数据["完整面板"] = bool(完整面板)
    _写入存档字典(数据)


def 完整面板可见() -> bool:
    """【外观】面板那个独立小窗口开不开（默认关：看风格直接走菜单栏 Appearance）。

    ★ 为什么这个开关放在皮肤桥而不是面板注册表：它是**外观自己的事**，
      面板注册表管的是"面板在哪儿画"，不该知道某一块面板的业务含义。
    """
    return bool(_读取存档字典().get("完整面板", False))


def 设完整面板可见(值: bool) -> None:
    数据 = _读取存档字典()
    数据["完整面板"] = bool(值)
    _写入存档字典(数据)


def _有界面上下文() -> bool:
    """ImGui 上下文在不在。

    ★ 没有上下文时调用任何 imgui/ux 函数都可能**直接段错误**（实测），
      而本模块会被"不开窗"的自检脚本导入，所以凡是要碰界面 API 的地方都先过这一关。
    """
    try:
        return bool(imgui.GetCurrentContext())
    except Exception:                                                    # noqa: BLE001
        return False


def 设用户基底主题(键名: str, *, 存盘: bool = True) -> bool:
    """切换官方基底主题（皮肤关掉时用它兜底）。返回是否认得这个名字。

    ★ 环境变量 `MUJOCO_STUDIO_THEME` 是基底主题的**单一真源**：
      界面桥启动时读它、`用户基底主题()` 读它、`主程序.py` 也从它推风格。
      所以这里先改环境变量，再立刻应用一次；没有界面上下文时只改环境变量。
    """
    global 基底已应用
    键 = str(键名).strip().upper()
    if 键 not in _主题表:
        return False
    os.environ["MUJOCO_STUDIO_THEME"] = 键
    基底已应用 = ""                       # 逼下一帧重新应用（带窗口侧对象再确认一次）
    if not _有界面上下文():
        return True
    try:
        应用基底主题(键)
        if 存盘:
            ux.save_settings(_主题表[键])   # 写进 ~/.mujoco.ini，下次启动仍是它
    except Exception as 异常:                                             # noqa: BLE001
        print(f"⚠ 皮肤：基底主题切换失败（不影响使用）：{type(异常).__name__}: {异常}")
    return True



def 决定启动风格(命令行风格: str | None = None) -> tuple[str, str]:
    """启动时用哪套风格。优先级：命令行 > 环境变量 驭臂_风格 > 存档 > 默认。

    返回 (风格, 来源说明) —— 来源说明只用于启动时打印一行，方便排查"为什么是这样"。
    """
    可选 = 选择项()
    if 命令行风格:
        值 = 命令行风格.strip()
        if 值 in 可选:
            return 值, "命令行 --风格"
        print(f"⚠ 认不出风格「{值}」，可选：{'、'.join(可选)}（已按默认处理）")
    环境 = (os.environ.get("驭臂_风格") or "").strip()
    if 环境 and 环境 in 可选:
        return 环境, "环境变量 驭臂_风格"
    存档 = 读取存档()
    if 存档:
        return 存档, "上次选的（输出/外观.json）"
    return (默认风格, "默认") if 默认风格 in 可选 else (关闭, "默认（风格表不可用）")


# ---------------------------------------------------------------------------
# 当前状态
# ---------------------------------------------------------------------------
当前风格 = 关闭              # 真正的默认由 主程序.py 通过 决定启动风格() 设进来
基底已应用 = ""              # 已经应用到官方主题的基底（避免每帧重复调用 setup_theme）
见证: dict = {}              # 验收用：记录"皮肤到底有没有生效"的实测值
统计 = {"帧": 0, "推入轮": 0, "补推轮": 0, "出错": 0, "降级帧": 0}


def 设风格(风格: str, *, 记住: bool = True) -> tuple[bool, str]:
    """切换风格。返回 (是否成功, 给人看的一句话)。下一帧生效。"""
    global 当前风格, 基底已应用
    if 风格 not in 选择项():
        return False, f"认不出风格「{风格}」"
    if 风格 == 当前风格:
        return True, f"已经是「{显示名(风格)}」"
    当前风格 = 风格
    基底已应用 = ""               # 逼下一帧重新应用基底主题
    if 记住:
        写入存档(风格)
    是皮肤 = 风格 != 关闭
    print(f"【外观】已切换到「{显示名(风格)}」"
          f"（{'皮肤生效中' if 是皮肤 else '已关闭皮肤，回到官方外观'}；下一帧生效）", flush=True)
    return True, f"已切换到「{显示名(风格)}」"


def 轮换(方向: int = 1) -> str:
    """F10 用：在"5 套风格 + 关"之间转一格。"""
    可选 = 选择项()
    if not 可选:
        return 关闭
    当前 = 当前风格 if 当前风格 in 可选 else 可选[0]
    下一个 = 可选[(可选.index(当前) + 方向) % len(可选)]
    设风格(下一个)
    return 下一个


# ---------------------------------------------------------------------------
# 官方主题：设基底（皮肤没覆盖到的项就靠它兜底）
# ---------------------------------------------------------------------------
def 应用基底主题(主题名: str, 窗口侧对象=None) -> None:
    """把官方主题设成这套风格的基底。

    ★ 必须做三件事（和 界面桥.py 同一个道理，少一件就会被"改回去"）：
        ① 写进官方 App 的 theme → Options → Theme 菜单显示的值正确
        ② 真正应用 → ImGui 样式变了
        ③ 下次启动仍是这个值 → 官方 App 关窗时会用 self.theme 存进 ini
    调用方负责判断"要不要重设"（见 帧开始）。
    """
    global 基底已应用
    主题 = _主题表.get(str(主题名).upper())
    if 主题 is None:
        return
    try:
        for 对象 in (窗口侧对象 or []):
            try:
                对象.theme = 主题
            except Exception:                                          # noqa: BLE001
                pass
        ux.setup_theme(主题)
        基底已应用 = str(主题名).upper()
    except Exception as 异常:                                             # noqa: BLE001
        print(f"⚠ 皮肤：基底主题设置失败（不影响使用）：{type(异常).__name__}: {异常}")


# ---------------------------------------------------------------------------
# ★ 包装 ux.setup_theme —— 让官方那 19 个面板也被换肤
# ---------------------------------------------------------------------------
_原版setup_theme = None
_包装已安装 = False
包装是否失效 = False            # 连续补推失败太多次就置位 → 自动退回"只换自研面板"
_补推失败次数 = 0
补推失败上限 = 60               # 连续失败约 1 秒才放弃：偶发一次不该永久降级


def 安装包装() -> None:
    """把 ux.setup_theme 包一层（幂等，可以反复调）。"""
    global _原版setup_theme, _包装已安装, _补推失败次数
    if _包装已安装:
        return
    try:
        原版 = ux.setup_theme
    except Exception as 异常:                                          # noqa: BLE001
        print(f"⚠ 皮肤：拿不到 ux.setup_theme，官方面板将不会被换肤（{异常}）")
        return
    _原版setup_theme = 原版

    def 包装(主题, *args, **kwargs):
        global _补推失败次数
        结果 = 原版(主题, *args, **kwargs)
        # ★ 只有"本帧皮肤已经推入"时才补推：
        #   官方在窗口初始化时也会调 setup_theme，那时不在帧内，推了就没机会弹（会报 Missing Pop）。
        if _本帧已推 and 当前风格 != 关闭 and not 包装是否失效:
            try:
                _推入一套()
                统计["补推轮"] += 1
                _补推失败次数 = 0
            except Exception as 异常:                                  # noqa: BLE001
                _补推失败次数 += 1
                if _补推失败次数 <= 2:
                    print(f"⚠ 皮肤：官方主题之后补推失败（第 {_补推失败次数} 次，"
                          f"本帧官方面板退回基底主题）：{type(异常).__name__}: {异常}")
                if _补推失败次数 >= 补推失败上限:
                    print(f"⚠ 皮肤：补推连续失败 {_补推失败次数} 次 → 已退回"
                          f"「只换自研面板」模式（官方 19 个面板保持官方配色）")
                    _包装失效()
        return 结果

    try:
        ux.setup_theme = 包装
        _包装已安装 = True
    except Exception as 异常:                                          # noqa: BLE001
        print(f"⚠ 皮肤：无法包装 ux.setup_theme（官方面板将不会被换肤）：{异常}")


def _包装失效() -> None:
    global 包装是否失效
    包装是否失效 = True
    统计["出错"] += 1
    try:                                # 尽力恢复官方原函数，避免留下半包装状态
        if _原版setup_theme is not None:
            ux.setup_theme = _原版setup_theme
    except Exception:                                                  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# 每帧：推入 / 弹出
# ---------------------------------------------------------------------------
已推颜色数 = 0
已推变量数 = 0
已推曲线颜色数 = 0
本帧期望按钮色 = 0             # 推入那一刻算好的"这套皮肤应有的按钮色"（见 写见证 的说明）
_本帧已推 = False
本帧是否降级 = False


def _推入一套() -> None:
    """把当前风格推入样式栈（ImGui 颜色/形状 + implot 颜色）。

    ★★ 实测踩过的坑（验收脚本 + 逐项探针抓出来的，别踩第二次）：

      ① **implot 有自己独立的一套栈**：用 `implot.PushStyleColor` 推的必须用
         `implot.PopStyleColor` 弹。一开始图省事算进同一个计数、结尾统一用
         `imgui.PopStyleColor` 弹 → 每帧多弹 16 项、ImGui 刷
         `Calling PopStyleColor() too many times!`，而且 implot 的栈每帧净涨 16 项（内存泄漏）。

      ② **implot 的 StyleVar 在本机绑定里是"地雷"，一个都不能推**：
         20 个样式项逐项实测，9 个会直接**段错误**（MajorGridSize / LegendSpacing /
         MajorTickLen / MajorTickSize / MinorTickLen / MinorTickSize / MinorGridSize /
         DigitalPadding / DigitalSpacing），崩溃与传 float 还是 Vec2 无关 ——
         说明绑定里的枚举值和实际 .so 的 ImPlotStyleVar 枚举对不上，越界索引算出野指针。
         证据：`优化（软件优化的报告都放这里面来）/验证/implot样式项安全矩阵.txt`。
         → 所以曲线**只换颜色**，图框形状保持 implot 默认。
           （想重新启用：先用那个探针把 20 项全测一遍，只推退出码为 0 的那些。）
    """
    global 已推颜色数, 已推变量数, 已推曲线颜色数
    编译 = _编译一套(当前风格)
    for 枚举, 颜色 in 编译["颜色"]:
        imgui.PushStyleColor(枚举, 颜色)
        已推颜色数 += 1
    for 枚举, 值 in 编译["变量"]:
        imgui.PushStyleVar(枚举, 值)
        已推变量数 += 1
    for 枚举, 颜色 in 编译["曲线颜色"]:
        implot.PushStyleColor(枚举, 颜色)
        已推曲线颜色数 += 1
    _记期望按钮色(编译)
    统计["推入轮"] += 1


def _记期望按钮色(编译: dict) -> None:
    """把"这套皮肤应有的按钮色"算好存起来。

    ★ 为什么在推入那一刻算、而不是取见证时再算：用户点"换风格"是发生在某一帧的
      UpdateEvent 里（在我们已经推入之后），如果取见证时再用"当前风格"去算期望值，
      那一帧就会拿**新**风格的期望色去比**旧**皮肤的实际色 → 假报警一次。
      所以期望值必须与"这一帧真正推的是什么"绑定。
    """
    global 本帧期望按钮色
    try:
        本帧期望按钮色 = int(imgui.GetColorU32(十六进制转Vec4(编译["按钮色"])))
    except Exception:                                                  # noqa: BLE001
        本帧期望按钮色 = 0


def 帧开始(窗口侧对象=None) -> None:
    """每帧**最开头**调用（必须在所有窗口 Begin 之前）。"""
    global 已推颜色数, 已推变量数, 已推曲线颜色数
    global _本帧已推, 本帧是否降级
    # ★ 关键坑 ③：无条件清零。上一帧若中途抛异常，ImGui 已在帧末丢掉那层，
    #    这里绝不能再补弹（补弹会报 "Calling PopStyleColor() too many times!"）。
    已推颜色数 = 已推变量数 = 已推曲线颜色数 = 0
    _本帧已推 = False
    本帧是否降级 = False
    统计["帧"] += 1
    if 当前风格 == 关闭:
        return
    try:
        目标基底 = 基底主题(当前风格)
        if 基底已应用 != 目标基底:
            应用基底主题(目标基底, 窗口侧对象)
        _推入一套()
        _本帧已推 = True
    except Exception as 异常:                                             # noqa: BLE001
        本帧是否降级 = True
        统计["降级帧"] += 1
        # ★ 已经推成功的那部分**保留计数**，让 帧结束 精确弹回那几项
        #   （宁可这一帧只换一半皮肤，也不要弹出数量对不上而被 ImGui 报错）
        if 统计["降级帧"] <= 2:
            print(f"⚠ 皮肤：本帧换肤失败（本帧退回基底主题，不影响使用）："
                  f"{type(异常).__name__}: {异常}")


def 帧结束() -> None:
    """每帧**最后**调用（必须在所有窗口 End 之后 = priority=0）。"""
    global 已推颜色数, 已推变量数, 已推曲线颜色数, 本帧期望按钮色, _本帧已推
    写见证("③ 弹出之前（官方 GUI 已画完）")
    try:
        if 已推颜色数:
            imgui.PopStyleColor(已推颜色数)
        if 已推变量数:
            imgui.PopStyleVar(已推变量数)
        if 已推曲线颜色数:
            implot.PopStyleColor(已推曲线颜色数)
    except Exception as 异常:                                             # noqa: BLE001
        统计["出错"] += 1
        if 统计["出错"] <= 2:
            print(f"⚠ 皮肤：弹出失败（ImGui 会在帧末自行丢弃，不影响使用）：{异常}")
    finally:
        已推颜色数 = 已推变量数 = 已推曲线颜色数 = 0
        本帧期望按钮色 = 0
        _本帧已推 = False


# ---------------------------------------------------------------------------
# 见证：证明"皮肤真的生效了"（不靠肉眼 —— 这是本项目的验收习惯）
# ---------------------------------------------------------------------------
def 当前按钮色() -> int:
    try:
        return int(imgui.GetColorU32(imgui.Col.Button))
    except Exception:                                                  # noqa: BLE001
        return 0


def 期望按钮色() -> int:
    """本帧皮肤应有的按钮色（推入时记下的）；没有皮肤时为 0。"""
    return 本帧期望按钮色


def 写见证(阶段: str) -> None:
    """记录"此刻算出来的按钮色是不是皮肤色"，供验收脚本与面板上的指示灯用。"""
    if not _本帧已推:
        return
    实测, 期望 = 当前按钮色(), 期望按钮色()
    见证[阶段] = {"实测": f"{实测:#010x}", "期望": f"{期望:#010x}", "生效": 实测 == 期望}
    见证["风格"] = 当前风格


def 状态行() -> str:
    """一行中文状态（面板底部显示 / 排查用）。"""
    if 当前风格 == 关闭:
        return "皮肤：已关闭（官方外观）"
    一句 = "官方+自研面板都换肤" if not 包装是否失效 else "★ 仅自研面板（官方补推已失效）"
    return (f"皮肤：{显示名(当前风格)} ｜ {一句} ｜ "
            f"帧 {统计['帧']} 推入 {统计['推入轮']} 轮 补推 {统计['补推轮']} 轮 "
            f"出错 {统计['出错']} 降级 {统计['降级帧']} 帧")
