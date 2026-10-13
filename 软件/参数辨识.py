"""
参数辨识.py —— D3 的核心算法（已用"已知真值"闭环验证）

它做什么：
    给定"真机"上采到的一段数据（状态 + 控制量），反推机器人的惯性参数
    （各连杆质量、质心位置…）。这就是"让仿真像真机"的关键一步。

怎么用（三步）：
    from 参数辨识 import 采数据, 辨识, 参数定义

    数据 = 采数据(模型路径, 时长=2.0)                    # 在你的真机/高保真模型上激励
    结果 = 辨识(模型路径, 数据, 待辨识的参数, 初值)        # 反推参数
    print(结果.对比表())                                  # 看估计值 vs 初值 vs 真值

★ 最关键的一条经验（踩了一整轮才明白，务必别重犯）：
    **残差必须用"一步预测误差"，不能用"自由滚动轨迹误差"。**
        · 自由滚动：让候选参数自己跑 1 秒再比轨迹 → 参数稍偏，轨迹就跑到别处（混沌），
          残差变成噪声、对参数不敏感 → 优化撞边界、4 个参数全不收敛（实测残差只降 2 倍）。
        · 一步预测：每个采样点把仿真**重置到记录的真状态**，只推进一步再比 →
          误差不累积，残差对参数敏感且光滑 → 同样数据下 4 个参数全部收敛到 0.1%（实测）。
    这也是 mujoco.sysid 这类工具的核心思想。

为什么不用官方 sysid 的 optimize()：
    它的残差函数接口有"隐式批量/广播"语义（有限差分会把参数广播成矩阵），
    实测试了 6 种返回形状组合都对不上。改用它只做参数管理（ParameterDict 带边界/存档/对比表），
    优化用下面自实现的 Gauss-Newton（算法透明、好调试）。
"""
from __future__ import annotations

import dataclasses
import time

import numpy as np

import mujoco

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class 参数定义:
    """一个待辨识参数的元信息。

    ★ 必须显式给出"要写进模型的哪个对象"，不要靠名字猜：
      参数名是给你看的（比如 upperarm_mass），模型里的名字往往不同
      （upper_arm_link）。早期版本按 `名称[:-5]` 去查 body，结果
      spec.body("upperarm") 返回 None，报 "'NoneType' object has no attribute 'mass'"
      （实测踩过）。所以这里明确写下 (body名, 字段)。

    目标字段：
        ("forearm_link", "mass")        → 连杆质量
        ("forearm_link", "com_x")       → 质心 x 分量
    """

    名称: str
    目标: tuple[str, str]
    初值: float
    下界: float
    上界: float
    真值: float | None = None      # 做闭环验证时填；真实辨识时留 None
    单位: str = ""


@dataclasses.dataclass
class 采集数据:
    """一段激励实验的记录。"""

    时间: np.ndarray
    qpos: np.ndarray
    qvel: np.ndarray
    ctrl: np.ndarray
    模型路径: str = ""
    备注: str = ""

    @property
    def 步数(self) -> int:
        return len(self.时间)


@dataclasses.dataclass
class 辨识结果:
    参数: list[参数定义]
    估计值: np.ndarray
    残差历史: list[float]
    往返次数: int
    耗时: float

    def 表格(self) -> list[tuple[str, float, float, float | None, float | None]]:
        """返回 [(名称, 初值, 估计值, 真值, 相对误差%), …]。"""
        out = []
        for i, p in enumerate(self.参数):
            误 = None
            if p.真值 is not None and abs(p.真值) > 1e-9:
                误 = abs(self.估计值[i] - p.真值) / abs(p.真值) * 100
            out.append((p.名称, p.初值, float(self.估计值[i]), p.真值, 误))
        return out

    def 对比表(self) -> str:
        行 = [f"{'参数':<18}{'初值':>10}{'估计值':>12}{'真值':>10}{'误差':>10}"]
        for 名, 初, 估, 真, 误 in self.表格():
            真s = f"{真:>10.3f}" if 真 is not None else f"{'—':>10}"
            误s = f"{误:>9.1f}%" if 误 is not None else f"{'—':>10}"
            行.append(f"{名:<18}{初:>10.3f}{估:>12.4f}{真s}{误s}")
        return "\n".join(行)


# ---------------------------------------------------------------------------
# ① 采数据（闭环激励 —— 别用开环大力矩，会把机械臂甩飞）
# ---------------------------------------------------------------------------
def 默认激励(t: float, home: np.ndarray, 幅度: float = 0.25) -> np.ndarray:
    """一段平滑的多关节正弦目标（闭环跟踪用）。

    ★ 形状自动跟随 home 的长度 —— 以前这里写死了 6 个分量（UR5e 是 6 轴），
      换成 Franka Panda / iiwa14 / xArm7（都是 7 轴）会直接广播错误
      （实测：`operands could not be broadcast together with shapes (7,) (6,)`）。
      现在：能激励几个关节就激励几个，6 轴时的取值与前完全一致。
    """
    激励 = np.zeros_like(np.asarray(home, dtype=float))
    n = 激励.size
    if n >= 2:
        激励[1] = np.sin(2*np.pi*0.5*t)
    if n >= 3:
        激励[2] = np.sin(2*np.pi*0.5*t + 1.0)
    if n >= 4:
        激励[3] = 0.6*np.sin(2*np.pi*0.8*t + 0.5)
    return np.asarray(home, dtype=float) + 幅度 * 激励


def 采数据(模型路径: str, 时长: float = 2.0, 质量覆盖: dict | None = None,
           KP: float = 400.0, KD: float = 40.0, 备注: str = "") -> 采集数据:
    """在模型上做闭环激励并记录 q/v/τ。

    参数
      质量覆盖: {连杆名: 质量} —— 用来造"真机"（做闭环验证时给真值）；
                真实辨识时传 None（直接在真机数据上跑）。
    为什么要闭环：开环大力矩激励会让机械臂 2 秒内甩到几百度外（实测），
                  闭环 PD 跟踪平滑轨迹才能得到有界且信息量足够的数据。
    """
    spec = mujoco.MjSpec.from_file(模型路径)
    for 连杆, 质量 in (质量覆盖 or {}).items():
        spec.body(连杆).mass = float(质量)
    模型 = spec.compile()
    d = mujoco.MjData(模型)
    mujoco.mj_resetDataKeyframe(模型, d, 0)
    mujoco.mj_forward(模型, d)
    home = d.qpos.copy()

    时间, qs, vs, us = [], [], [], []
    for k in range(int(时长 / 模型.opt.timestep)):
        t = k * 模型.opt.timestep
        期望 = 默认激励(t + 模型.opt.timestep, home)
        力矩 = KP*(期望 - d.qpos) - KD*d.qvel + d.qfrc_bias
        d.ctrl[:] = np.clip(力矩, -150, 150)
        mujoco.mj_step(模型, d)
        时间.append(d.time); qs.append(d.qpos.copy())
        vs.append(d.qvel.copy()); us.append(d.ctrl.copy())
    return 采集数据(np.array(时间), np.array(qs), np.array(vs), np.array(us),
                    模型路径=模型路径, 备注=备注)


# ---------------------------------------------------------------------------
# ② 辨识（Gauss-Newton + 一步预测残差）
# ---------------------------------------------------------------------------
def _造模型(模型路径: str, 值: dict, 参数们: list[参数定义]) -> mujoco.MjModel:
    """按参数值造模型（带边界夹取，避免非法模型让编译器抛错）。"""
    spec = mujoco.MjSpec.from_file(模型路径)
    for p in 参数们:
        v = float(np.clip(值[p.名称], p.下界, p.上界))
        _写参数(spec, p.目标, v)
    return spec.compile()


def _写参数(spec: mujoco.MjSpec, 目标: tuple[str, str], 值: float) -> None:
    """把参数值写进模型。`目标` = (body名, 字段)，字段为 mass / com_x / com_y / com_z。"""
    体名, 字段 = 目标
    body = spec.body(体名)
    if body is None:
        raise KeyError(f"模型里没有连杆「{体名}」")
    if 字段 == "mass":
        body.mass = 值
        return
    if 字段 in ("com_x", "com_y", "com_z"):
        序 = {"com_x": 0, "com_y": 1, "com_z": 2}[字段]
        ipos = np.asarray(body.ipos, dtype=float).copy()
        ipos[序] = 值
        body.ipos = ipos
        return
    raise KeyError(f"不支持的字段「{字段}」（支持 mass / com_x / com_y / com_z）")


def 辨识(数据: 采集数据, 参数们: list[参数定义], 抽稀: int = 5,
         最大轮数: int = 25, 打印=print) -> 辨识结果:
    """用一步预测误差做 Gauss-Newton 辨识。返回 辨识结果。"""
    模型路径 = 数据.模型路径
    参数名 = [p.名称 for p in 参数们]
    下 = np.array([p.下界 for p in 参数们], dtype=float)
    上 = np.array([p.上界 for p in 参数们], dtype=float)
    x = np.array([p.初值 for p in 参数们], dtype=float)

    下标 = np.arange(1, len(数据.时间), max(1, int(抽稀)))
    合计 = [0]

    # ★ 关节数从数据里取，不要写死 —— 以前这里硬编码 6（UR5e 是 6 轴），
    #   换成 Franka Panda / iiwa14 / xArm7（7 轴）会报
    #   `could not broadcast input array from shape (7,) into shape (6,)`（实测）。
    自由度 = int(np.asarray(数据.qpos).shape[-1])

    def 残差(值向量):
        """一步预测误差：每个采样点重置到记录真状态，只推进一步。"""
        值 = {名: float(v) for 名, v in zip(参数名, np.asarray(值向量).ravel())}
        try:
            模型 = _造模型(模型路径, 值, 参数们)
        except Exception:                                        # noqa: BLE001
            return np.full(len(下标) * 自由度, 1e3)
        d = mujoco.MjData(模型)
        偏差 = np.empty((len(下标), 自由度))
        for 序, k in enumerate(下标):
            d.qpos[:] = 数据.qpos[k - 1]
            d.qvel[:] = 数据.qvel[k - 1]
            mujoco.mj_forward(模型, d)
            d.ctrl[:] = 数据.ctrl[k]         # 偏移 1：τ[k] 把状态从 q[k-1] 推到 q[k]
            mujoco.mj_step(模型, d)
            偏差[序] = d.qpos - 数据.qpos[k]
        合计[0] += 1
        return 偏差.ravel()

    t0 = time.time()
    r = 残差(x)
    代价 = float(r @ r)
    历史 = [代价]
    打印(f"  初值 {np.round(x, 4)} → 残差 {代价:.8f}")

    for 轮 in range(最大轮数):
        J = np.zeros((r.size, x.size))
        for j in range(x.size):
            步 = max(1e-6, 1e-4 * abs(x[j]))
            xj = x.copy()
            xj[j] = np.clip(xj[j] + 步, 下[j], 上[j])
            实际步 = xj[j] - x[j]
            if 实际步 == 0:
                continue
            J[:, j] = (残差(xj) - r) / 实际步
        JTJ = J.T @ J + 1e-9 * np.eye(x.size)
        g = J.T @ r
        增益, 改进 = 1.0, False
        for _ in range(12):                       # 回溯线搜索
            尝试 = np.clip(x - 增益 * np.linalg.solve(JTJ, g), 下, 上)
            if np.allclose(尝试, x):
                break
            r新 = 残差(尝试)
            代价新 = float(r新 @ r新)
            if 代价新 < 代价:
                x, r, 代价 = 尝试, r新, 代价新
                改进 = True
                break
            增益 *= 0.5
        历史.append(代价)
        if 轮 % 5 == 0 or not 改进:
            打印(f"  轮 {轮+1:2d}: 残差 {代价:.10f}  参数 {np.round(x, 4)}")
        if not 改进 and 增益 < 1e-3:
            打印(f"  轮 {轮+1:2d}: 无法继续改进，停止")
            break

    return 辨识结果(参数=参数们, 估计值=x, 残差历史=历史,
                    往返次数=合计[0], 耗时=time.time() - t0)
