"""
指标桥.py —— 把"插件里想看的数"送到界面上去画曲线（第 4 步 D1）

它解决什么问题：
    官方 19 个面板能看内置量（关节角、接触力…），但**看不到你的控制律算出来的中间量**
    —— 比如"末端跟踪误差""力矩峰值""我自己的指标"。
    这个模块把这些量统一采集起来，发给窗口侧的面板去画实时曲线。

怎么用（对写控制算法的人）：
    在你的插件里加一个方法，返回你想看的数（键=曲线名，值=数字）：

        class 我的插件(控制插件):
            def 指标(self) -> dict:
                return {"跟踪误差(mm)": self.误差*1000, "力矩峰值": float(np.abs(数据.ctrl).max())}

    就这样。**不需要改外壳、不需要改面板** —— 面板会自动按"指标名字"建曲线。
    不写 `指标()` 的插件就不出现在面板里，没有任何影响。

数据流（和界面桥同一条已验证的路子）：
    仿真侧：启动.py 每约 1/30 秒 → 指标桥.发布指标(注册表, 发送函数)
                    ↓ 自定义 Snapshot 消息（最新覆盖，不排队）
    窗口侧：面板/监控面板.py 每帧读 → 画实时曲线
"""
from __future__ import annotations

import dataclasses
from typing import Any, Callable

from mujoco.experimental.studio import messages

# 发布频率上限：物理是 500 Hz，但曲线不需要那么密（30 Hz 足够顺滑），
# 而且能避免把通道塞满、避免面板画图成为瓶颈。想改就改这个数。
发布频率 = 30.0


@dataclasses.dataclass(frozen=True)
class 指标消息(messages.Snapshot):
    """一帧指标快照。Snapshot = 只保留最新一条（旧的不排队，天然适合实时曲线）。

    ★ 必须加 @dataclasses.dataclass，否则 pybind 侧取不到字段（实测踩过）。
    """

    时间: float            # 仿真时间（秒）
    墙钟: float            # 真实时间（秒），面板用它做横轴更平稳
    数值: dict             # {指标名: 数字}


def 采集(注册表) -> dict[str, float]:
    """向每个插件要一次指标。插件没写 `指标()`、或写错了，都只跳过它，不影响别人。"""
    结果: dict[str, float] = {}
    for 插件 in getattr(注册表, "_目标", []):
        # 跳过内置的步进插件（它没有指标）
        getter = getattr(插件, "指标", None)
        if getter is None:
            continue
        名字前缀 = str(getattr(插件, "名称", type(插件).__name__))
        try:
            一条 = getter() or {}
        except Exception as 异常:                                  # noqa: BLE001
            # 指标采集失败不该影响控制回路
            print(f"⚠ 插件【{名字前缀}】的 指标() 出错（已跳过）：{type(异常).__name__}: {异常}")
            continue
        for 键, 值 in 一条.items():
            try:
                结果[f"{名字前缀}·{键}"] = float(值)
            except (TypeError, ValueError):
                continue          # 非数字的指标（比如字符串状态）不上曲线
    return 结果


class 发布器:
    """限频发布指标。放在仿真循环里每圈调一次 `也许发布()` 即可。"""

    def __init__(self, 发送函数: Callable[[Any], None], 频率: float = 发布频率):
        self._发送 = 发送函数
        self._间隔 = 1.0 / max(频率, 1e-6)
        self._下次 = 0.0
        self.已发布 = 0
        self.最近: dict[str, float] = {}

    def 也许发布(self, 注册表, 仿真时间: float, 墙钟: float) -> bool:
        """到了时间就采集并发一帧。返回是否真的发了。"""
        if 墙钟 < self._下次:
            return False
        self._下次 = 墙钟 + self._间隔
        数值 = 采集(注册表)
        self.最近 = 数值
        try:
            self._发送(指标消息(时间=仿真时间, 墙钟=墙钟, 数值=数值))
            self.已发布 += 1
            return True
        except Exception as 异常:                                       # noqa: BLE001
            # 通道出问题（比如窗口刚关）不该拖垮仿真
            if self.已发布 == 0:
                print(f"⚠ 指标发布失败（不影响控制）：{type(异常).__name__}: {异常}")
            return False
