"""
面板/外观面板.py —— 换肤的"挂载点"与切换界面

★ 为什么换肤引擎挂在这个面板文件里（而不是新加一个"窗口侧插件"）：
    外壳 `启动.py` 的约定是 —— **`面板/` 目录里的每个 .py 都会被自动加载**，
    只要模块里有 `面板类` 这个名字。而它的 4 个核心文件（插件系统/启动/界面桥）
    被 `零改动自检.py` 用哈希钉住了（"加功能不该改外壳"）。
    所以换肤这样做：
        · 引擎在 `软件/皮肤桥.py`（纯工具模块，没有 `面板类` → 不会被当成面板）
        · 挂载点就是本文件（被自动加载的窗口侧插件）
        · 本面板即使被用户关掉，下面那几个消息处理器**照常运行** → 皮肤不会跟着消失

它干四件事（前两件与"面板是否可见"无关）：
    ① `UpdateEvent`（priority=CRITICAL，在**所有窗口 Begin 之前**）
       → `皮肤桥.帧开始()`：推入本帧皮肤 + 轮询 F10
    ② `BuildGuiEvent`（priority=0，比官方 INTERNAL 还低 → **永远最后一个**）
       → `皮肤桥.帧结束()`：弹出皮肤
    ③ `BuildGuiEvent`（priority=INTERNAL）→ 取一次证（官方面板画完之后皮肤还在不在）
    ④ `BuildGuiEvent`（默认优先级）→ 画这个切换界面

界面上的东西：
    当前风格 + 一句话说明 ｜ 全部风格 + 「关」逐条可选（点一下即切换，当前项打 *）
    配色色卡（用 ColorButton 画，不需要画布接口）｜ 标题栏与按钮样式实时预览
    底部：FPS（验收要求 ≥55）、见证指示灯、统计行

快捷键：**F10** 在"5 套风格 + 关"之间轮换（F9 已被面板恢复占用，官方占了 F2/F3/F6/F7）
命令行：`--风格 <名字>` 或 `--style <名字>`（可用名字以 软件/风格表.json 里的 风格列表 为准）
环境变量：`驭臂_风格`｜存档：`输出/外观.json`
"""
from __future__ import annotations

import os as _os
import sys as _sys

_外壳目录 = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _外壳目录 not in _sys.path:
    _sys.path.insert(0, _外壳目录)

from mujoco.experimental.dear_imgui import dear_imgui as imgui       # noqa: E402
from mujoco.experimental.studio import messages, viewer_protocol      # noqa: E402

import 文案
import 面板注册表                                                      # noqa: E402
import 皮肤桥                                                          # noqa: E402
import 菜单栏                                                          # noqa: E402

轮换快捷键 = imgui.Key.F10
_上一帧 = -1


class 外观面板:
    """窗口侧插件：换肤引擎的挂载点 + 风格切换界面。"""

    面板显示名 = "外观"
    页签名 = "Appearance"

    # ★ 独立窗口：**不占面板窗的段位**。换风格日常走菜单栏 `Appearance`（点开就能切，不用开窗），
    #   这个完整面板（色卡 / 实时预览 / FPS / 见证指示灯）只在需要时由菜单里的
    #   `Open Appearance panel` 打开 —— 开关存在 输出/外观.json，默认关。
    独立窗口 = True

    def __init__(self):
        self.viewer = None
        self.可见 = True
        self.绘制次数 = 0
        self.错误次数 = 0
        self.切换次数 = 0
        self.摆放过 = False
        self._帧 = 0
        # ★ 包装官方 ux.setup_theme（幂等）—— 这是"官方 19 个面板也能换肤"的唯一路径。
        #   放在这里而不是模块顶部，是为了让"什么时候装的"看得见、可排查。
        皮肤桥.安装包装()
        # ★ 把 Appearance / Panels 挂进官方菜单栏那一行（幂等；必须在第一帧之前装好）。
        #   挂载原理见 菜单栏.py 文件头：官方菜单栏结束前的那一刻才插得进去。
        菜单栏.安装包装()

    # ------------------------------------------------------------------
    # ① 拿到 viewer（换基底主题要用它把 theme 同步给官方 App）
    # ------------------------------------------------------------------
    @messages.handler(priority=messages.Priority.CRITICAL)
    def 记下窗口(self, event: viewer_protocol.ViewerInitEvent) -> bool:
        self.viewer = event.viewer
        return False

    # ------------------------------------------------------------------
    # ② 每帧最开头：推入皮肤 + 轮询 F10
    #    ★ 不看 self.可见 —— 面板被关掉也必须继续换肤
    # ------------------------------------------------------------------
    @messages.handler(priority=messages.Priority.CRITICAL)
    def 每帧推入(self, event: messages.UpdateEvent) -> bool:
        self._帧 += 1
        皮肤桥.帧开始(self._窗口侧对象())
        皮肤桥.写见证("① 自研面板开始画之前")
        self._轮询快捷键()
        return False

    # ------------------------------------------------------------------
    # ③ 见证：官方 GUI 画完之后（本处理器排在官方 _on_build_gui 之后）
    # ------------------------------------------------------------------
    @messages.handler(priority=messages.Priority.INTERNAL)
    def 见证官方(self, event: messages.BuildGuiEvent) -> bool:
        皮肤桥.写见证("② 官方 GUI 画完之后")
        return False

    # ------------------------------------------------------------------
    # ④ 每帧最后：弹出皮肤
    #    ★ priority=-1（比 0 更低 → 永远最后一个跑）。为什么必须是 -1 而不是 0：
    #      `面板窗.画面板` 也排在 0 —— 同优先级的先后顺序**官方文档明说是未定义的**，
    #      实测就出现过"皮肤先弹出、面板窗后绘制"，于是面板窗读到的页签颜色是
    #      **官方主题的灰**、换皮肤也不跟着变（用户报的"Inspector/Panels 都变灰、
    #      切风格它们不跟着切"）。挪到 -1 之后，面板窗的绘制稳定落在皮肤生效期间。
    # ------------------------------------------------------------------
    @messages.handler(priority=-1)
    def 每帧弹出(self, event: messages.BuildGuiEvent) -> bool:
        皮肤桥.帧结束()
        return False

    def _窗口侧对象(self):
        """官方 ViewerApp（换基底主题时要把 theme 同步给它，否则菜单显示与实际不一致）。"""
        窗口 = getattr(self.viewer, "app", None) if self.viewer is not None else None
        return [窗口] if 窗口 is not None else []

    def _轮询快捷键(self) -> None:
        """F10 = 轮换风格。每帧只真正轮询一次（避免重复触发）。"""
        global _上一帧
        try:
            帧 = int(imgui.GetFrameCount())
        except Exception:                                                # noqa: BLE001
            return
        if 帧 == _上一帧:
            return
        _上一帧 = 帧
        try:
            if imgui.IsKeyPressed(int(轮换快捷键)):
                self.切换次数 += 1
                皮肤桥.轮换(1)
        except Exception:                                                # noqa: BLE001
            pass                     # 快捷键失败绝不能影响换肤

    # ------------------------------------------------------------------
    # 界面
    # ------------------------------------------------------------------
    @messages.handler
    def 画面板(self, event: messages.BuildGuiEvent) -> bool:
        # ★ 必须在"可见性检查"之前：即使本面板被收进容器/关掉，也要能响应 F9 恢复
        #   （注意：换肤本身不依赖这里 —— 它在 每帧推入()/每帧弹出() 里，
        #     那两个处理器跟面板可见性无关，面板收起来了皮肤照样生效）
        面板注册表.每帧(self)
        if not self.可见:
            return False
        # ★ 它不占面板窗的段位：这个完整面板只在菜单栏 Appearance 里点开时才画。
        #   点右上角 × 也走同一个开关（否则"可见性每帧广播"会把窗口立刻顶回来）。
        if not 皮肤桥.完整面板可见():
            return False
        self.绘制次数 += 1
        if not self.摆放过:
            self.摆放过 = True
            # 只用 FirstUseEver：ImGui 自己记住用户拖到的位置，我们只决定"第一次"放哪
            imgui.SetNextWindowPos(imgui.Vec2(384.0, 56.0), imgui.Cond.FirstUseEver.value)
            imgui.SetNextWindowSize(imgui.Vec2(352.0, 430.0), imgui.Cond.FirstUseEver.value)
        展开, 新可见 = imgui.Begin("Appearance", self.可见, 0)
        面板注册表.记录(self)
        try:
            if not 新可见:
                皮肤桥.设完整面板可见(False)
                print("【菜单栏】外观面板（完整版）→ 关闭（菜单 Appearance 里可再打开）", flush=True)
                return False
            if not 展开:
                return False
            self._画内容()
        except Exception as 异常:                                        # noqa: BLE001
            self.错误次数 += 1
            if self.错误次数 <= 2:
                print(f"⚠ 外观面板绘制出错：{type(异常).__name__}: {异常}")
        finally:
            imgui.End()
        return False

    def _画内容(self) -> None:
        # 容器把本面板画在页签里时，容器负责跳过"没打开的页签"；这里再挡一道
        if not self.可见:
            return
        self.绘制次数 += 1
        # ★ 这个面板里**只写 ASCII**：官方 UI 字体（Atkinson Hyperlegible）没有中文字形，
        #   面板上画中文会被 ImGui 回退成 `?`（"弹窗里很多问号"就是这个）。
        #   中文留给终端与文档。校验：./.venv/bin/python 优化（软件优化的报告都放这里面来）/验证/字体覆盖.py
        风格表 = 皮肤桥.读取风格表()
        if not 风格表.get("风格"):
            imgui.TextColored(imgui.Vec4(0.95, 0.45, 0.30, 1.0), 文案.取("外观.无风格表"))
            imgui.TextDisabled(文案.取("外观.风格表位置"))
            imgui.Separator()
            imgui.TextDisabled(皮肤桥.界面状态行())
            return

        # ---- 当前风格 ----
        imgui.Text(文案.取("外观.当前"))
        imgui.SameLine()
        imgui.TextColored(imgui.Vec4(0.30, 0.85, 0.40, 1.0), 皮肤桥.界面名(皮肤桥.当前风格))
        imgui.TextDisabled("  " + 皮肤桥.界面说明(皮肤桥.当前风格))
        imgui.Separator()

        # ---- 选择列表 ----
        imgui.TextDisabled(文案.取("外观.选一个"))
        for 名 in 皮肤桥.选择项():
            选中 = (名 == 皮肤桥.当前风格)
            标记 = "*" if 选中 else " "
            if imgui.Selectable(f"{标记} {皮肤桥.界面名(名)}##{名}", 选中):
                if not 选中:
                    self.切换次数 += 1
                    皮肤桥.设风格(名)
        imgui.Separator()

        # ---- 这套风格的色卡（ColorButton 是现成的色块控件，不需要画布接口）----
        条目 = (风格表.get("风格") or {}).get(皮肤桥.当前风格) or {}
        颜色 = 条目.get("颜色") or {}
        imgui.TextDisabled(文案.取("外观.色卡"))
        预览键 = ("WindowBg", "TitleBgActive", "Button", "ButtonHovered", "FrameBg",
                  "Border", "Text", "TextDisabled", "Separator", "CheckMark")
        for i, 键 in enumerate(预览键):
            文本 = 颜色.get(键)
            if not 文本:
                continue
            try:
                色 = 皮肤桥.十六进制转Vec4(文本)
            except Exception:                                            # noqa: BLE001
                continue
            imgui.ColorButton(f"##swatch{i}", 色, 0, imgui.Vec2(22.0, 18.0))
            imgui.SameLine()
        imgui.NewLine()
        imgui.Separator()

        # ---- 实时预览：按钮 + 这套风格的真实形状参数 ----
        imgui.TextDisabled("Preview")
        if 皮肤桥.当前风格 != 皮肤桥.关闭:
            样式 = 条目.get("样式") or {}
            基底 = str(条目.get("基底主题", "?")).upper()
            圆角 = 样式.get("WindowRounding", 0)
            边框 = 样式.get("WindowBorderSize", 0)
            imgui.TextDisabled(文案.格式化("外观.预览详情",
                                           "  base theme {基底} | rounding {圆角} | "
                                           "window border {边框} | colors {颜色} | style vars {样式}",
                                           基底=基底, 圆角=圆角, 边框=边框,
                                           颜色=len(颜色), 样式=len(样式)))
        imgui.Button(文案.取("外观.预览按钮"))
        imgui.SameLine()
        imgui.TextDisabled(文案.取("外观.预览说明"))
        imgui.Separator()

        # ---- 验收指标 ----
        fps = 0.0
        try:
            fps = float(imgui.GetIO().Framerate)
        except Exception:                                                # noqa: BLE001
            pass
        见证 = 皮肤桥.见证
        官方 = 见证.get("② 官方 GUI 画完之后") or {}
        自研 = 见证.get("① 自研面板开始画之前") or {}
        官方生效 = 官方.get("生效")
        自研生效 = 自研.get("生效")
        if 皮肤桥.当前风格 == 皮肤桥.关闭:
            imgui.TextDisabled(文案.取("外观.皮肤关"))
        else:
            好 = (官方生效 is True and 自研生效 is True)
            色 = imgui.Vec4(0.30, 0.85, 0.40, 1.0) if 好 else imgui.Vec4(0.95, 0.80, 0.25, 1.0)
            字 = 文案.取("外观.皮肤好") if 好 else 文案.取("外观.皮肤查")
            imgui.TextColored(色, 字)
            imgui.TextDisabled(文案.格式化("外观.见证",
                                           "  custom-before={自研}  official-after={官方}  "
                                           "witness button={实测} (expect {期望})",
                                           自研=自研生效, 官方=官方生效,
                                           实测=官方.get("实测"), 期望=官方.get("期望")))
        imgui.TextDisabled(文案.格式化("外观.指标",
                                           "  FPS {帧率:.1f} (acceptance line 55) | switches {切换} | "
                                           "draws {重绘}",
                                           帧率=fps, 切换=self.切换次数, 重绘=self.绘制次数))
        imgui.Separator()
        imgui.TextDisabled(皮肤桥.界面状态行())
        if 皮肤桥.界面警告数():
            imgui.TextColored(imgui.Vec4(0.95, 0.45, 0.30, 1.0),
                              文案.格式化("外观.坏键",
                                              "[warn] style table skipped {n} bad key(s) - see terminal",
                                              n=皮肤桥.界面警告数()))
        imgui.TextDisabled(文案.取("外观.命令行"))


# 启动器约定：模块里叫"面板类"的就是要实例化的面板
面板类 = 外观面板
