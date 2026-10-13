"""
面板/监控面板.py —— 实时曲线面板（第 4 步 D1）

它干什么：
    把插件通过 `指标()` 报上来的数画成实时曲线（跟踪误差、力矩峰值、你自定义的任何量）。
    官方 19 个面板看不到这些"你自己算出来的中间量"，这个面板补上。

怎么用（对写控制算法的人）：
    在你的插件里加一个方法，返回你想看的数：

        def 指标(self) -> dict:
            return {"最大误差(deg)": float(np.degrees(self.当前误差)),
                    "力矩峰值(Nm)": float(np.abs(数据.ctrl).max())}

    就这样。**不用改外壳、不用改面板** —— 面板会按"指标名字"自动建曲线。

数据从哪来（见 指标桥.py）：
    仿真侧每 ~30 Hz 采集一次 → 自定义消息 → 这个面板每帧读一次。
"""
from __future__ import annotations

import os as _os
import sys as _sys

# 让面板能 import 到外壳里的模块（指标桥）
_外壳目录 = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _外壳目录 not in _sys.path:
    _sys.path.insert(0, _外壳目录)

from mujoco.experimental.studio import messages          # noqa: E402
from 指标桥 import 指标消息                                # noqa: E402
import 文案                                                          # noqa: E402
from 曲线基类 import 曲线面板基类                          # noqa: E402


class 监控面板(曲线面板基类):
    """订阅指标消息并画曲线的窗口侧插件。"""

    # 启动器按这个名字自动加载本文件（见 启动.py 的"面板目录自动加载"）
    面板显示名 = "实时监控"
    页签名 = "Monitor (metrics)"

    def __init__(self, 窗口秒: float = 10.0):
        super().__init__(窗口秒)
        self.收到帧数 = 0
        self.最后收到 = 0.0

    def 标题(self) -> str:
        return "Monitor (metrics)"

    def 顶部控件(self) -> None:
        # 用坐标轴标签表达"数据来源"，避免刷屏
        pass

    # ------------------------------------------------------------------
    # 数据：收指标
    # ------------------------------------------------------------------
    @messages.handler
    def 收指标(self, 消息: 指标消息) -> bool:
        self.收到帧数 += 1
        import time as _time
        self.最后收到 = _time.perf_counter()
        数值 = getattr(消息, "数值", None)
        横轴 = getattr(消息, "墙钟", None)
        if not 数值 or 横轴 is None:
            return False
        for 名, 值 in 数值.items():
            self.记一点(名, float(值), float(横轴))
        return False

    def _画内容(self) -> None:
        super()._画内容()
        # 在窗口底部补一行状态（父类画完曲线后）
        from mujoco.experimental.dear_imgui import dear_imgui as imgui
        imgui.Separator()
        imgui.TextDisabled(文案.格式化("监控.收帧", "metric frames received = {n}", n=self.收到帧数))


# 启动器约定：模块里叫"面板类"的就是要实例化的面板
面板类 = 监控面板
