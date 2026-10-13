"""
面板/参数面板.py —— 控制器参数面板（第 4 步）

它解决什么问题：
    以前改 KP/KD 要"打开文件 → 改数字 → 重启软件"。
    现在界面上拖滑杆，**实时生效**（下一帧控制律就用新值），不用重启、不用改文件。

怎么工作：
    ① 外壳每 ~10 Hz 把"插件声明了哪些可调参数"发给这个面板
    ② 面板画成滑杆；你拖动时，把改动打包成 `参数消息` 发回仿真侧
    ③ 仿真侧的 `参数应用器` 调插件的 `设置参数()` 改类属性
    ④ 插件的 `每步控制()` 下一次执行就直接读到新值

对插件作者的要求（只需要一步）：
    在插件里声明可调参数，界面就自动出现滑杆：

        def 可调参数(self) -> dict:
            return {"KP": {"值": self.KP, "范围": (10.0, 20000.0)},
                    "KD": {"值": self.KD, "范围": (0.0, 500.0)}}

界面上的东西：
    · 每个参数一行滑杆，右边显示当前值（可直接输入）
    · 顶部：Reset（恢复成刚打开时的值）
    · 底部：状态（收到了几帧、发出过几次改动）
"""
from __future__ import annotations

import os as _os
import sys as _sys

_外壳目录 = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _外壳目录 not in _sys.path:
    _sys.path.insert(0, _外壳目录)

from mujoco.experimental.dear_imgui import dear_imgui as imgui       # noqa: E402
from mujoco.experimental.studio import messages, viewer_protocol      # noqa: E402
from 参数桥 import 参数消息, 参数表消息, 采集可调参数                  # noqa: E402

import 文案
import 面板注册表                                                      # noqa: E402
import 界面文字                                                        # noqa: E402


class 参数面板:
    """窗口侧插件：把插件的可调参数画成滑杆，并把改动发回仿真侧。"""

    面板显示名 = "控制器参数"
    页签名 = "Controller params"

    def __init__(self):
        self.viewer = None
        self.可见 = True
        self.参数: dict[str, dict] = {}      # {全名: {插件,参数,值,范围,步长,单位}}
        self.初值: dict[str, float] = {}      # Reset 用
        self.收帧 = 0
        self.发出改动 = 0
        self.绘制次数 = 0
        self.错误次数 = 0
        self.待发送: dict[str, float] = {}
        self._已提醒示例 = False

    # ------------------------------------------------------------------
    @messages.handler(priority=messages.Priority.CRITICAL)
    def 记下窗口(self, event: viewer_protocol.ViewerInitEvent) -> bool:
        self.viewer = event.viewer
        return False

    # ------------------------------------------------------------------
    # 数据：收外壳发来的"可调参数表"
    # ------------------------------------------------------------------
    @messages.handler
    def 收参数表(self, 消息: 参数表消息) -> bool:
        self.收帧 += 1
        表 = getattr(消息, "参数", None)
        if not isinstance(表, dict):
            return False
        # 保留界面上正在编辑的值（避免外壳刷新把用户拖到一半的值弹回去）
        for 全名, 信息 in 表.items():
            旧 = self.参数.get(全名)
            if 旧 is not None and 全名 in self.待发送:
                信息 = dict(信息)
                信息["值"] = self.待发送[全名]
            self.参数[全名] = 信息
            # ★ 初值要在"第一次看到这个参数"时记下来（不能等发送时才记，
            #   否则用户一拖滑杆，初值就被改成拖动后的值，Reset 就没用了）
            self.初值.setdefault(全名, float(信息["值"]))
        for 全名 in list(self.参数):
            if 全名 not in 表:
                self.参数.pop(全名)
                self.待发送.pop(全名, None)
                self.初值.pop(全名, None)
        return False

    # ------------------------------------------------------------------
    # 界面
    # ------------------------------------------------------------------
    @messages.handler
    def 画面板(self, event: messages.BuildGuiEvent) -> bool:
        # ★ 必须在"可见性检查"之前：即使本面板被收进容器/关掉，也要能响应 F9 恢复
        面板注册表.每帧(self)
        if not self.可见:
            return False
        if 面板注册表.画在容器里(self):
            return False
        self.绘制次数 += 1
        # ★ 第二项传 self.可见（= ImGui 的 p_open）：传了它右上角才有 × 关闭按钮。
        #   原来传 None → ImGui 不画关闭按钮 → 窗口关不掉。
        展开, self.可见 = imgui.Begin(文案.取("参数.标题"), self.可见, 0)
        面板注册表.记录(self)
        try:
            if not 展开:
                return False
            self._画内容()
        except Exception as 异常:                                        # noqa: BLE001
            self.错误次数 += 1
            if self.错误次数 <= 2:
                print(f"⚠ 参数面板绘制出错：{type(异常).__name__}: {异常}")
        finally:
            imgui.End()
        return False

    def _画内容(self) -> None:
        # 容器把本面板画在页签里时，容器负责跳过"没打开的页签"；这里再挡一道
        if not self.可见:
            return
        self.绘制次数 += 1
        if not self.参数:
            # ★ 面板上只画 ASCII：官方 UI 字体没有中文字形（画中文会变成 ?）。
            #   而"可调参数 / 值 / 范围"这些**键名本身就是中文**，所以完整的示例
            #   放到终端打印（终端用系统字体，中文正常），面板只给一句英文提示。
            imgui.TextDisabled(文案.取("参数.无可调"))
            imgui.TextDisabled(文案.取("参数.示例代码"))
            imgui.TextDisabled("    " + 文案.取("参数.说明"))
            if not self._已提醒示例:
                self._已提醒示例 = True
                print("【参数】插件要出现滑杆，就在插件里加这个方法（面板上画不了中文，故在此显示）：\n"
                      '        def 可调参数(self) -> dict:\n'
                      '            return {"KP": {"值": self.KP, "范围": (10.0, 20000.0)},\n'
                      '                    "KD": {"值": self.KD, "范围": (0.0, 500.0)}}', flush=True)
            imgui.Separator()
            imgui.TextDisabled(文案.格式化("参数.统计", "frames={帧}  changes sent={改动}", 帧=self.收帧, 改动=self.发出改动))
            return

        改过 = False
        当前插件 = None
        for 全名, 信息 in self.参数.items():
            if 信息["插件"] != 当前插件:
                当前插件 = 信息["插件"]
                imgui.Separator()
                # 插件名优先用插件自己声明的 英文名（参数桥带过来），否则查术语表/剥成 ASCII
                imgui.TextDisabled(str(信息.get("插件英文") or 界面文字.英文(当前插件)))
            lo, hi = 信息["范围"]
            显示名 = 界面文字.安全(str(信息["参数"])) + \
                (f" ({界面文字.安全(str(信息['单位']))})" if 信息["单位"] else "")
            imgui.PushItemWidth(220.0)
            变了, 新值 = imgui.SliderFloat(f"##{全名}", float(信息["值"]), float(lo), float(hi))
            imgui.PopItemWidth()
            if 变了:
                信息["值"] = float(新值)
                self.待发送[全名] = float(新值)
                改过 = True
            imgui.SameLine()
            imgui.Text(显示名)
            imgui.SameLine()
            imgui.TextDisabled(f"= {信息['值']:.4g}")

        # 有改动就发回仿真侧（一条消息带全部改动，不必每帧发）
        if 改过:
            self._发送(self.待发送)

        imgui.Separator()
        if imgui.Button(文案.取("参数.重置")):
            self.待发送 = {全名: v for 全名, v in self.初值.items() if 全名 in self.参数}
            for 全名, v in self.待发送.items():
                self.参数[全名]["值"] = v
            self._发送(self.待发送)
        imgui.SameLine()
        imgui.TextDisabled(文案.格式化("参数.统计行", "frames={帧}  changes sent={改动}",
                                           帧=self.收帧, 改动=self.发出改动))

    def _发送(self, 改动: dict) -> None:
        if self.viewer is None or not 改动:
            return
        try:
            self.viewer.send_to_sim(参数消息(改动=dict(改动)))
            self.发出改动 += 1
            self.待发送 = {}          # 发完清空，避免重复发送
        except Exception as 异常:                                       # noqa: BLE001
            print(f"⚠ 参数改动发送失败：{异常}")


# 启动器约定：模块里叫"面板类"的就是要实例化的面板
面板类 = 参数面板
