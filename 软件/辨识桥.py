"""
辨识桥.py —— 参数辨识面板与后端之间的消息（第 4 步 D3 界面化）

两条消息，方向相反：
    辨识命令（界面 → 仿真侧）："去采样" / "去辨识"
    辨识状态（仿真侧 → 界面）：当前状态、结果表、拟合残差、日志

★ 为什么状态要带"拟合残差"而不只是参数值：
    辨识出的参数"像不像真的"没法直接验证（我们没有真机当参考）。
    但可以看"用这组参数去预测这段数据，残差是不是更小" ——
    残差显著下降，说明这组参数确实更贴合数据。
    **注意**：这只说明"比原始标称值更贴合这段数据"，不等于"找到了真值"。
    证明算法能找到真值的证据是离线那个闭环实验（造已知真值 → 误差 1.47%）。
"""
from __future__ import annotations

import dataclasses

from mujoco.experimental.studio import messages


@dataclasses.dataclass(frozen=True)
class 辨识命令(messages.Snapshot):
    """界面 → 仿真侧。"""

    动作: str = "空闲"        # "采样" / "辨识"
    时长: float = 1.0         # 采样时长（秒）


@dataclasses.dataclass(frozen=True)
class 辨识状态(messages.Snapshot):
    """仿真侧 → 界面。"""

    状态: str = "空闲"        # 空闲 / 采样中 / 辨识中
    进度: str = ""
    采样步数: int = 0
    结果: list = dataclasses.field(default_factory=list)   # [(名称, 标称, 估计值, 误差%)]
    拟合: dict = dataclasses.field(default_factory=dict)   # {"标称": r0, "辨识后": r1}
    耗时: float = 0.0
    日志: list = dataclasses.field(default_factory=list)


class 发布器:
    """周期性把辨识状态发给界面（默认 5 Hz —— 采样/辨识都是秒级过程，不需要更密）。"""

    def __init__(self, 发送函数, 频率: float = 5.0):
        self._发送 = 发送函数
        self._间隔 = 1.0 / max(频率, 1e-6)
        self._下次 = 0.0
        self.已发布 = 0

    def 也许发布(self, 注册表, 墙钟: float) -> bool:
        if 墙钟 < self._下次:
            return False
        self._下次 = 墙钟 + self._间隔
        状态 = None
        for 插件 in getattr(注册表, "_目标", []):
            取 = getattr(插件, "状态消息", None)
            if 取 is None:
                continue
            try:
                状态 = 取()
                break
            except Exception:                                        # noqa: BLE001
                continue
        if 状态 is None:
            return False
        try:
            self._发送(状态)
            self.已发布 += 1
            return True
        except Exception as 异常:                                     # noqa: BLE001
            if self.已发布 == 0:
                print(f"⚠ 辨识状态发布失败（不影响控制）：{type(异常).__name__}: {异常}")
            return False
