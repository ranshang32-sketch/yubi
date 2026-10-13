"""
正弦摆动.py —— 一个会"动"的最小例子（算法只有几行）

前面的插件都是"走到某个姿势就停住"。这个插件让关节一直按正弦摆动，
用来演示：**控制律可以依赖时间**（data.time），也就是轨迹跟踪的雏形。

和其他插件的关系：
    两个插件都会写 ctrl[:]，**按注册顺序，后面的覆盖前面的**。
    本插件在主程序里排在「关节 PD 位置控制」前面，所以会被它盖掉；
    想看本插件单独工作，就把主程序插件清单里的关节 PD 注释掉。
"""
from __future__ import annotations

import numpy as np

import 插件系统 as 插件
from 插件系统 import 控制插件, 每步


class 正弦摆动插件(控制插件):
    名称 = "正弦摆动（轨迹跟踪雏形）"
    版本 = "1.0"
    英文名 = "Sinusoid swing"   # 面板上显示用（官方 UI 字体没有中文字形，面板只能画 ASCII）
    说明 = "让 shoulder_lift 绕初始姿势做正弦摆动 —— 演示控制律如何随时间变化。"
    作者 = "数字样机"

    # ---- 调参入口 ----
    振幅 = 0.35        # 摆动幅度（rad），0.35 rad ≈ 20°
    频率 = 0.3         # 摆动频率（Hz）
    KP = 200.0
    KD = 30.0

    def __init__(self):
        self.基准 = None
        self.步数 = 0
        self.当前目标 = None

    def 模型兼容性(self, 模型) -> str:
        """要求 nu == nq（同样要写 `ctrl[:]`）且至少有 3 个关节。

        ★ 关于"摆哪个关节"的诚实说明：下面的代码固定摆 `qpos[1]`（第 2 个关节），
          这在 UR5e 上是 shoulder_lift，在 7 轴手臂上则是另一个关节 ——
          **不会报错，但摆的不是你以为的那个关节**。这一点没法从 model 上自动判断，
          所以这里只挡"必然出错"的情况（关节太少 / 执行器对不上），
          关节语义的差别留在注释里提示。
        """
        nq = int(getattr(模型, "nq", 0))
        nu = int(getattr(模型, "nu", 0))
        if nq < 3 or nu == 0:
            return f"需要至少 3 个关节且带执行器（本模型 nq={nq}、nu={nu}）"
        if nu != nq:
            return f"需要 nu==nq 的扭矩模型（本模型 nq={nq}、nu={nu}）"
        return ""

    @每步
    def 每步控制(self, event: 插件.messages.StepEvent) -> bool:
        数据 = event.data
        # ★ 空场景没有关节：直接返回，别让 目标[1] 越界（越界会被"出错隔离"停用插件）
        if 数据.qpos.size < 3 or 数据.ctrl.size == 0:
            self.基准 = None
            return False
        if self.基准 is None:                       # 第一次：记住初始姿势当摆动中心
            self.基准 = 数据.qpos.copy()

        目标 = self.基准.copy()
        目标[1] += self.振幅 * np.sin(2 * np.pi * self.频率 * 数据.time)
        self.当前目标 = 目标

        数据.ctrl[:] = self.KP * (目标 - 数据.qpos) - self.KD * 数据.qvel + 数据.qfrc_bias
        self.步数 += 1
        return False

    def 插件状态(self) -> dict:
        if self.当前目标 is None:
            return {"状态": "等待第一步"}
        return {"步数": self.步数,
                "摆动到": f"{np.degrees(self.当前目标[1] - self.基准[1]):+.1f}°"}
