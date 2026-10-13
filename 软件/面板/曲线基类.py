"""
面板/曲线基类.py —— 实时曲线面板的公共零件（第 4 步 D1/D2 共用）

为什么单独抽出来：
    "监控面板"（D1）和"数据记录面板"（D2）都要画实时曲线、都要勾选/清空/暂停。
    把画图这部分放这里，两个面板各自只关心自己的业务（一个只管显示、一个还管录制）。
    这样加第三个面板（比如参数辨识的结果对比）时也能直接复用。

用法：
    class 我的面板(曲线面板基类):
        def 标题(self): return "My Panel"
        def 顶部控件(self): ...      # 可选：自己加按钮（父类会把曲线部分接上）
"""
from __future__ import annotations

import time
from collections import deque

from mujoco.experimental.dear_imgui import dear_imgui as imgui
from mujoco.experimental.implot import implot
from mujoco.experimental.studio import messages

import 文案
import 面板注册表          # 统一管理"关闭 / 记忆 / F9 恢复"（见 面板注册表.py）
import 界面文字            # 面板上只能画 ASCII（官方 UI 字体没有中文字形）

# 面板最多同时画几条（太多就糊了）
最多曲线数 = 8

# 一组区分度高的颜色（RGBA 元组；画的时候转成 imgui.Vec4）
调色板 = [
    (0.30, 0.85, 0.40, 1.0),   # 绿
    (0.95, 0.45, 0.30, 1.0),   # 橙红
    (0.35, 0.65, 0.98, 1.0),   # 蓝
    (0.95, 0.80, 0.25, 1.0),   # 黄
    (0.80, 0.45, 0.95, 1.0),   # 紫
    (0.40, 0.90, 0.90, 1.0),   # 青
    (0.95, 0.55, 0.75, 1.0),   # 粉
    (0.70, 0.70, 0.70, 1.0),   # 灰
]


def 转颜色(rgba) -> "imgui.Vec4":
    """把 (r,g,b,a) 元组转成 imgui.Vec4。

    ★ 实测踩过：TextColored 只接受 Vec4 对象，直接传元组会报
      "incompatible function calls"。
    """
    return imgui.Vec4(float(rgba[0]), float(rgba[1]), float(rgba[2]), float(rgba[3]))


class 曲线面板基类:
    """带实时曲线的面板。子类实现 标题()，可选实现 顶部控件()。"""

    窗口秒 = 10.0          # 保留多少秒历史
    可见 = True
    页签名 = "Curves"      # 在【工作台】容器里显示成哪个页签（只能 ASCII）

    def __init__(self, 窗口秒: float | None = None):
        if 窗口秒:
            self.窗口秒 = 窗口秒
        self.viewer = None
        self.暂停 = False
        self.窗口时长 = self.窗口秒
        self.曲线: dict[str, dict] = {}
        self.最新值: dict[str, float] = {}
        self.绘制次数 = 0
        self.错误次数 = 0

    # ---------------- 子类可覆盖 ----------------
    def 标题(self) -> str:
        return "Curves"

    def 顶部控件(self) -> None:
        """子类在这里加自己的按钮（父类已经画了 Clear/Pause/窗口时长）。"""
        return None

    # ---------------- 数据 ----------------
    def 记一点(self, 名: str, 值: float, 横轴: float) -> None:
        """往某条曲线上加一个点（子类/子面板也可以直接用）。"""
        线 = self.曲线.get(名)
        if 线 is None:
            序号 = len(self.曲线)
            # ★ 曲线名来自插件的 指标()，可能是中文；面板上画中文会变成 ?。
            #   所以另存一个"界面名"：优先查术语表翻成英文，翻不出来的剥成 ASCII；
            #   剥完为空或与别人重名就用 ch1/ch2… 兜底（保证每条曲线都有可读标签）。
            界面名 = 界面文字.英文(名)
            已用 = {str(线.get("界面名", "")) for 线 in self.曲线.values()}
            if not 界面名 or 界面名 in 已用:
                界面名 = f"ch{序号 + 1}"
            线 = {
                "t": deque(maxlen=int(self.窗口秒 * 60) + 32),
                "v": deque(maxlen=int(self.窗口秒 * 60) + 32),
                "颜色": 调色板[序号 % len(调色板)],
                "界面名": 界面名,
                "显示": True,
                "峰值": 0.0,
            }
            self.曲线[名] = 线
        if not self.暂停:
            线["t"].append(float(横轴))
            线["v"].append(float(值))
        self.最新值[名] = float(值)
        线["峰值"] = max(线["峰值"], abs(float(值)))

    def 清空(self) -> None:
        for 线 in self.曲线.values():
            线["t"].clear()
            线["v"].clear()
            线["峰值"] = 0.0

    # ---------------- 绘制 ----------------
    @messages.handler
    def 画面板(self, event: messages.BuildGuiEvent) -> bool:
        # ★ 必须在"可见性检查"之前：即使本面板归面板窗管/关掉，也要能响应 F9 恢复
        面板注册表.每帧(self)
        if not self.可见:
            return False
        if 面板注册表.画在容器里(self):
            # 面板窗（面板/面板窗.py）会在**展开的那一段**里直接调 _画内容()；
            # 没展开时本面板本来就不可见，这里不用画任何东西（也绝不自己开窗口）。
            return False
        # ★ Begin/End 必须配对：中途抛异常会让 ImGui 状态错乱
        #   （实测报错 "Missing End()"），所以包在 try/finally 里。
        # ★ 第二项传 self.可见（= ImGui 的 p_open）：只有传了它，右上角才会出现
        #   × 关闭按钮。原来传 None —— ImGui 规定 p_open=None 不画关闭按钮，
        #   于是窗口关不掉（用户看到的"点不掉的弹窗"就是这么来的）。
        展开, self.可见 = imgui.Begin(self.标题(), self.可见, 0)
        面板注册表.记录(self)
        try:
            if not 展开:
                return False
            self._画内容()
        except Exception as 异常:                                  # noqa: BLE001
            self.错误次数 += 1
            if self.错误次数 <= 2:
                print(f"⚠ 面板【{self.标题()}】绘制出错：{type(异常).__name__}: {异常}")
        finally:
            imgui.End()
        return False

    def _画内容(self) -> None:
        # 只有"当前被显示的那个页签"才该重画曲线（容器会跳过没打开的页签；
        # 这里再挡一道，防止有人直接从别处调用）
        if not self.可见:
            return
        self.绘制次数 += 1
        # 公共控制条
        if imgui.Button(文案.取("曲线.清空")):
            self.清空()
        imgui.SameLine()
        _, self.暂停 = imgui.Checkbox(文案.取("曲线.暂停"), self.暂停)
        imgui.SameLine()
        imgui.SetNextItemWidth(120.0)
        _, self.窗口时长 = imgui.SliderFloat(文案.取("曲线.时间窗"), float(self.窗口时长), 2.0, 60.0)
        imgui.SameLine()

        # 子类自己的控件
        self.顶部控件()

        if not self.曲线:
            imgui.Separator()
            imgui.TextDisabled(文案.取("曲线.暂无数据"))
            return

        # 曲线开关 + 当前值
        imgui.Separator()
        for 名, 线 in list(self.曲线.items())[:最多曲线数]:
            _, 线["显示"] = imgui.Checkbox(f"##{名}", 线["显示"])
            imgui.SameLine()
            imgui.TextColored(转颜色(线["颜色"]), str(线.get("界面名") or 名))
            imgui.SameLine()
            imgui.TextDisabled(文案.格式化("曲线.峰值",
                                                  "= {值:+.3f}  (peak {峰:.3f})",
                                                  值=self.最新值.get(名, float("nan")),
                                                  峰=线["峰值"]))

        # 曲线图
        imgui.Separator()
        曲线列表 = [(名, 线) for 名, 线 in self.曲线.items() if 线["显示"] and len(线["t"]) >= 2]
        if not 曲线列表:
            imgui.TextDisabled(文案.取("曲线.等待数据"))
            return
        if implot.BeginPlot(f"##{self.标题()}", imgui.Vec2(-1.0, -1.0)):
            implot.SetupAxes("time (s)", "value")
            for 名, 线 in 曲线列表[:最多曲线数]:
                implot.PlotLine(str(线.get("界面名") or 名), list(线["t"]), list(线["v"]))
            implot.EndPlot()
