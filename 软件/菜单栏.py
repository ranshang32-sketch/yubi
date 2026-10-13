"""
菜单栏.py —— 把 `Appearance` / `Panels` 两个菜单挂进**官方那一行**（File / Simulation / View / Help 右边）

★ 为什么必须这样挂（实测结论，改之前先看）：
    官方菜单栏是 `viewer_app.build_gui()` 里 `BeginMainMenuBar() … EndMainMenuBar()` 画的。
    我们的处理器排在官方之后（`Priority.INTERNAL` 之后），那时菜单栏**已经关掉了** ——
    旧容器那个 `Panels` 菜单就是这么写的：实测它**一个条目都没提交过**，等于从来没画出来。
    包装 `imgui.EndMainMenuBar`（官方每帧必调）就能在"关掉之前"把菜单插进去：
    实测条目落在顶行 `y=1`、尺寸 `79×20`，和 File/Help 同一行。

★ 两条硬要求：
    ① **幂等**：反复调 `安装包装()` 只包一层（包两层会让菜单画两遍）。
    ② **无 ImGui 上下文时什么都不做**：那个绑定在没有上下文时调用任何 imgui 函数会
       **直接段错误**（实测），而本模块会被"不开窗"的自检脚本导入并调用。

★ 安装时机：必须在**第一帧之前**。由 `面板/面板窗.py` 的 `__init__` 调用（它在窗口起来之前执行）。
"""
from __future__ import annotations

import os as _os
import sys as _sys

_外壳目录 = _os.path.dirname(_os.path.abspath(__file__))
if _外壳目录 not in _sys.path:
    _sys.path.insert(0, _外壳目录)
_面板目录 = _os.path.join(_外壳目录, "面板")
if _面板目录 not in _sys.path:
    _sys.path.insert(0, _面板目录)

from mujoco.experimental.dear_imgui import dear_imgui as imgui       # noqa: E402

import 皮肤桥                                                         # noqa: E402
import 面板注册表                                                     # noqa: E402
import 文案                                                           # noqa: E402

# 官方三套基底主题（皮肤关掉时用它兜底）。键名与 皮肤桥._主题表 一致。
基底主题表 = (("LIGHT", "Light"), ("DARK", "Dark"), ("CLASSIC", "Classic"))

# ★ 官方**用 Python 画**的顶栏字符串 → 文案键。只有这 11 条能翻（其余在 C++ 里，翻不了）。
#   做法：包装 imgui.BeginMenu / MenuItem 查这张表，**不复制官方代码** —— 官方升级也不怕。
官方顶栏词表 = {
    "File": "官方.File", "Simulation": "官方.Simulation", "View": "官方.View", "Help": "官方.Help",
    "Quit": "官方.Quit", "Save Config": "官方.Save Config", "Reset Config": "官方.Reset Config",
    "Hide Toolbar": "官方.Hide Toolbar", "Show Toolbar": "官方.Show Toolbar",
    "Info": "官方.Info", "Profiler": "官方.Profiler",
}

已安装 = False
_原结束菜单栏 = None
_出错次数 = 0
_翻译已装 = False


def 安装官方顶栏翻译() -> None:
    """包装 `imgui.BeginMenu` / `imgui.MenuItem`：把官方顶栏那 11 条换成当前语言。

    ★ 为什么用包装而不是改官方文件：官方在 site-packages 里（`.venv` 是"可重建、不进 git"的），
      改它等于每次重建环境都要重来；包装只在我们进程里生效，官方升级也不受影响。
    ★ 只翻译 `官方顶栏词表` 里列出的字符串 —— 我们自己菜单传的是中文/自定义标签，不会误伤。
      字符串里的 `##`（ImGui 的隐藏 ID）要原样保留。
    """
    global _翻译已装
    if _翻译已装:
        return

    def 拆(标签: str) -> tuple[str, str]:
        i = 标签.find("##")
        return (标签, "") if i < 0 else (标签[:i], 标签[i:])

    def 翻译(标签: str) -> str:
        正文, 尾巴 = 拆(str(标签))
        键 = 官方顶栏词表.get(正文)
        if 键 is None:
            return 标签
        return 文案.取(键, 正文) + 尾巴

    try:
        原BeginMenu = imgui.BeginMenu

        def 包BeginMenu(标签, *a, **k):
            return 原BeginMenu(翻译(标签), *a, **k)

        imgui.BeginMenu = 包BeginMenu

        原MenuItem = imgui.MenuItem

        def 包MenuItem(标签, *a, **k):
            return 原MenuItem(翻译(标签), *a, **k)

        imgui.MenuItem = 包MenuItem
        _翻译已装 = True
    except Exception as 异常:                                            # noqa: BLE001
        print(f"⚠ 菜单栏：无法包装 BeginMenu/MenuItem（官方顶栏保持英文）：{异常}")


def _有界面上下文() -> bool:
    """ImGui 上下文在不在（没有时绝不能碰 imgui）。

    ★ 任务 3 会把这一小段统一到 `面板注册表.有界面上下文()`，避免三处各写一份。
    """
    try:
        问 = getattr(imgui, "GetCurrentContext", None)
        return bool(问()) if 问 is not None else False
    except Exception:                                                    # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# 外观开关：那个"完整外观面板"（色卡/实时预览/FPS）的小窗口开不开
# ---------------------------------------------------------------------------
def 外观面板可见() -> bool:
    return 皮肤桥.完整面板可见()


def 设外观面板可见(值: bool) -> None:
    皮肤桥.设完整面板可见(bool(值))
    print(f"【菜单栏】外观面板（完整版）→ {'打开' if 值 else '关闭'}", flush=True)


# ---------------------------------------------------------------------------
# 给绘制用的只读快照（自检脚本直接测它，不用开窗）
# ---------------------------------------------------------------------------
def 菜单数据() -> dict:
    """{"皮肤": [(键, 显示名, 是否当前), …], "基底": [(键, 显示名, 是否当前), …], "外观面板": bool}"""
    皮肤 = [(名, 皮肤桥.界面名(名), 名 == 皮肤桥.当前风格) for 名 in 皮肤桥.选择项()]
    当前基底 = 皮肤桥.用户基底主题()
    基底 = [(键, 显示, 键 == 当前基底) for 键, 显示 in 基底主题表]
    return {"皮肤": 皮肤, "基底": 基底, "外观面板": 皮肤桥.完整面板可见()}


# ---------------------------------------------------------------------------
# 画菜单（只允许在"官方菜单栏关掉之前"这一刻调用）
# ---------------------------------------------------------------------------
def _画外观菜单() -> None:
    if not imgui.BeginMenu(文案.取("顶栏.外观")):
        return
    数据 = 菜单数据()
    开 = bool(数据["外观面板"])
    if imgui.MenuItem(文案.取("顶栏.打开外观面板"), "", 开):
        设外观面板可见(not 开)
    imgui.Separator()
    imgui.TextDisabled(文案.取("顶栏.皮肤行"))
    for 键, 显示, 选中 in 数据["皮肤"]:
        if imgui.MenuItem(f"    {显示}", "", 选中):
            if not 选中:
                皮肤桥.设风格(键)
    imgui.Separator()
    if imgui.BeginMenu(f"  {文案.取('顶栏.语言')}"):
        for 语 in (文案.中文, 文案.英文):
            if imgui.MenuItem(f"    {文案.语言名[语]}", "", 文案.当前语言 == 语):
                文案.设语言(语)
        imgui.EndMenu()
    imgui.Separator()
    imgui.TextDisabled(文案.取("顶栏.基底主题行"))
    for 键, 显示, 选中 in 数据["基底"]:
        if imgui.MenuItem(f"    {显示}", "", 选中):
            if not 选中:
                皮肤桥.设用户基底主题(键)
    imgui.EndMenu()


def _画面板菜单() -> None:
    if not imgui.BeginMenu(文案.取("顶栏.面板")):
        return
    可见 = 面板注册表.面板窗可见()
    if imgui.MenuItem(文案.取("顶栏.显示面板窗"), "", 可见):
        面板注册表.设面板窗可见(not 可见)
    if imgui.MenuItem(文案.取("顶栏.全部恢复")):
        面板注册表.全部显示()
    if imgui.MenuItem(文案.取("顶栏.重置版面")):
        面板注册表.重置版面()
    imgui.Separator()
    imgui.TextDisabled(文案.取("顶栏.面板区提示"))
    名单函 = getattr(面板注册表, "面板顺序", None)
    段展开 = getattr(面板注册表, "段展开", None)
    跳到段 = getattr(面板注册表, "跳到段", None)
    if callable(名单函) and callable(跳到段):
        for i, 名 in enumerate(名单函()):
            快捷键 = f"Ctrl+{i + 1}" if i < 9 else ""
            打开 = bool(段展开(名)) if callable(段展开) else False
            if imgui.MenuItem(f"    {文案.面板名(名)}", 快捷键, 打开):
                跳到段(名)
    imgui.TextDisabled(文案.取("顶栏.面板窗提示"))
    imgui.EndMenu()


_语言按钮报过 = False


def _画语言按钮() -> None:
    """顶栏那一行里的**一键切换**：中文模式显示 `EN`，英文模式显示 `中文`，点一下即切。"""
    global _语言按钮报过
    if imgui.Button(文案.取("顶栏.切到英文" if 文案.当前语言 == 文案.中文 else "顶栏.切到中文")):
        文案.切换()
    if imgui.IsItemHovered():
        imgui.SetTooltip(文案.取("顶栏.语言提示"))
    if not _语言按钮报过:
        # ★ 一次取证：按钮真的被画进那一行了（量它自己的矩形，和验菜单同一招）
        try:
            尺寸 = imgui.GetItemRectSize()
            位置 = imgui.GetItemRectMin()
            if float(尺寸.x) > 0:
                _语言按钮报过 = True
                print(f"【菜单栏】语言按钮已画进顶栏：位置=({位置.x:.0f},{位置.y:.0f}) "
                      f"尺寸={尺寸.x:.0f}×{尺寸.y:.0f}｜当前语言={文案.语言显示名()}", flush=True)
        except Exception:                                                # noqa: BLE001
            pass


def 画菜单() -> None:
    """把菜单追加到官方菜单栏右侧（内部函数；由 安装包装 的包装体调用）。"""
    global _出错次数
    try:
        _画语言按钮()          # ★ 一键切换：就在 File/Help/Appearance 那一行
    except Exception as 异常:                                            # noqa: BLE001
        _出错次数 += 1
        if _出错次数 <= 2:
            print(f"⚠ 菜单栏：语言按钮绘制出错（已隔离）：{type(异常).__name__}: {异常}")
    try:
        _画外观菜单()
    except Exception as 异常:                                            # noqa: BLE001
        _出错次数 += 1
        if _出错次数 <= 2:
            print(f"⚠ 菜单栏：Appearance 菜单绘制出错（已隔离）：{type(异常).__name__}: {异常}")
    try:
        _画面板菜单()
    except Exception as 异常:                                            # noqa: BLE001
        _出错次数 += 1
        if _出错次数 <= 2:
            print(f"⚠ 菜单栏：Panels 菜单绘制出错（已隔离）：{type(异常).__name__}: {异常}")


# ---------------------------------------------------------------------------
# 安装包装（幂等）
# ---------------------------------------------------------------------------
def 安装包装() -> None:
    """把 `imgui.EndMainMenuBar` 包一层（可以反复调）。"""
    global 已安装, _原结束菜单栏
    if 已安装:
        return
    try:
        原版 = imgui.EndMainMenuBar
    except Exception as 异常:                                            # noqa: BLE001
        print(f"⚠ 菜单栏：拿不到 imgui.EndMainMenuBar，Appearance 菜单不会出现（{异常}）")
        return
    _原结束菜单栏 = 原版

    def 包装(*args, **kwargs):
        # ★ 顺序要紧：先把我们的菜单挂进这一行，再让官方真正结束菜单栏
        try:
            if _有界面上下文():
                画菜单()
        except Exception as 异常:                                        # noqa: BLE001
            print(f"⚠ 菜单栏包装体出错（已隔离）：{type(异常).__name__}: {异常}")
        return 原版(*args, **kwargs)

    try:
        imgui.EndMainMenuBar = 包装
        安装官方顶栏翻译()
        已安装 = True
        print("【菜单栏】Appearance / Panels 已挂进官方菜单栏（与 File / Help 同一行）", flush=True)
    except Exception as 异常:                                            # noqa: BLE001
        print(f"⚠ 菜单栏：无法包装 imgui.EndMainMenuBar（Appearance 菜单不会出现）：{异常}")
