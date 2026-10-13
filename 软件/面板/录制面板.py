"""
面板/录制面板.py —— 数据录制与回放的界面（第 4 步 D2）

三个按钮：
    Start          —— 开始录制（默认 100 Hz）
    Stop and save  —— 停止并把数据写成 CSV + 元信息
    Replay         —— 把上次录制的控制量重放一遍（复现同一段运动）

它怎么和仿真侧通信：
    这个面板跑在窗口进程，录制逻辑跑在仿真进程 —— 两边只能靠消息。
    面板发 `录制命令` 消息，仿真侧的 `数据录制插件` 收。
    （和"滑杆值送进仿真侧"是同一套路子，见 界面桥.py）

默认输出目录：包根 output/04_记录/
    录制_YYYYmmdd_HHMMSS.csv          ← 数据（t/q/v/tau，带表头）
    录制_YYYYmmdd_HHMMSS.meta.json    ← 元信息（mujoco 版本、模型指纹、插件清单）
"""
from __future__ import annotations

import os as _os
import sys as _sys

_外壳目录 = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _外壳目录 not in _sys.path:
    _sys.path.insert(0, _外壳目录)

from mujoco.experimental.dear_imgui import dear_imgui as imgui       # noqa: E402
from mujoco.experimental.studio import messages, viewer_protocol      # noqa: E402

# 录制命令消息：和仿真侧共用同一个定义（避免两边各自定义导致类型不匹配）
#
# ★★ 这里踩过一个非常隐蔽又非常致命的坑（2026-09-18 实测，用户报"按 Start 完全没反应"）：
#   外壳（主程序.py）用的是 `from plugins.数据录制 import 数据录制插件`
#   → 那个模块在 sys.modules 里的名字是 `plugins.数据录制`；
#   而本文件原来写成 `sys.path.insert(0, 软件/plugins)` + `from 数据录制 import 录制命令`
#   → 模块名是 `数据录制`。**同一个 .py 因此被加载了两遍，成了两个不同的模块对象**：
#       插件注册的处理器类型 = plugins.数据录制.录制命令
#       面板发出的消息类型   = 数据录制.录制命令
#   两者**不是同一个类** → 仿真侧的 `issubclass(type(消息), info.message_type)` 永远不成立
#   → 按 Start / Stop / Replay **毫无反应，而且不报任何错**
#     （实测证据：快照确实到了仿真侧，但终端状态一直"空闲"、连"出错隔离"警告都没有）。
#   修法：统一用 `plugins.数据录制` 这个规范名字 import —— 和外壳完全一致，类才是同一个。
import 文案                                                          # noqa: E402
from 录制桥 import 录制命令                                          # noqa: E402
from 曲线基类 import 曲线面板基类                                       # noqa: E402
from 指标桥 import 指标消息                                             # noqa: E402

import 界面文字                                                        # noqa: E402


class 录制面板(曲线面板基类):
    """录制/回放的界面。同时把录制状态画成曲线（"已录行数"）。"""

    # 启动器按这个名字自动加载本文件
    面板显示名 = "数据录制"
    页签名 = "Recorder"

    def __init__(self, 窗口秒: float = 60.0):
        super().__init__(窗口秒)
        self.频率 = 100.0
        self.备注 = ""
        self.本地状态 = "空闲"
        self.已发命令 = ""
        self.命令次数 = 0

    def 标题(self) -> str:
        return "Recorder"

    # ------------------------------------------------------------------
    @messages.handler(priority=messages.Priority.CRITICAL)
    def 记下窗口(self, event: viewer_protocol.ViewerInitEvent) -> bool:
        self.viewer = event.viewer
        return False

    def _发命令(self, 动作: str) -> None:
        self.已发命令 = 动作
        self.命令次数 += 1
        if self.viewer is None:
            return
        try:
            self.viewer.send_to_sim(录制命令(动作=动作, 频率=self.频率, 备注=self.备注))
        except Exception as 异常:                                       # noqa: BLE001
            print(f"⚠ 录制命令发送失败：{异常}")

    # ------------------------------------------------------------------
    def 顶部控件(self) -> None:
        if imgui.Button(文案.取("录制.开始")):
            self.本地状态 = "录制中"
            self._发命令("开始")
        imgui.SameLine()
        if imgui.Button(文案.取("录制.停止保存")):
            self.本地状态 = "空闲"
            self._发命令("停止")
        imgui.SameLine()
        if imgui.Button(文案.取("录制.回放")):
            self._发命令("回放")
        imgui.SameLine()
        imgui.SetNextItemWidth(90.0)
        _, self.频率 = imgui.SliderFloat(文案.取("录制.频率"), float(self.频率), 10.0, 500.0)
        imgui.SameLine()
        imgui.SetNextItemWidth(160.0)
        _, self.备注 = imgui.InputText(文案.取("录制.备注"), self.备注)

    def _画内容(self) -> None:
        super()._画内容()
        imgui.Separator()
        imgui.TextDisabled(文案.格式化("录制.状态", "state={值}", 值=文案.状态(self.本地状态))
                           + "   "
                           + 文案.格式化("录制.末行",
                                         "last command={命令}   sent={次数}",
                                         命令=文案.状态(self.已发命令) or "-",
                                         次数=self.命令次数))
        imgui.TextDisabled(文案.取("录制.产物说明"))

    # ------------------------------------------------------------------
    # 录制插件把状态当指标上报（"已录行数"），这里接住画成曲线
    # ------------------------------------------------------------------
    @messages.handler
    def 收指标(self, 消息: 指标消息) -> bool:
        数值 = getattr(消息, "数值", None)
        横轴 = getattr(消息, "墙钟", None)
        if not 数值 or 横轴 is None:
            return False
        for 名, 值 in 数值.items():
            if "已录行数" in 名 or "录制" in 名:
                self.记一点(名, float(值), float(横轴))
        return False


# 启动器约定：模块里叫"面板类"的就是要实例化的面板
面板类 = 录制面板
