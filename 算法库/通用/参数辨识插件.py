"""
参数辨识插件.py —— D3 的界面后端（仿真侧）

它把已验证的 `参数辨识.py` 接到界面上：
    ① 激励采样：在当前模型上做一段闭环激励，记录 q/v/τ（用于辨识）
    ② 辨识：后台线程跑 Gauss-Newton，不阻塞实时仿真
    ③ 用新参数验证：把辨识结果写进模型并重编译，和"贡献"对照

为什么辨识要放后台线程：
    一次辨识约 1 秒、上百次模型前向。如果塞进 每步控制() 里跑，
    仿真会卡住 1 秒（界面看起来像死了）。所以开线程，用状态消息把进度发回界面。

★ 验证指标的诚实说明（这条很重要，免得误判）：
    我们只能拿"**贡献模型的响应**"当参考，而不是真机。
    所以验证只能说明"辨识结果比原始标称值更贴近这段数据"，**不能**说明"找到了真值"。
    真正证明算法能找到真值的证据，是 `验证参数辨识.py` 那个离线闭环实验
    （造已知真值 → 辨识 → 误差 1.47%）。
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time

import numpy as np

from mujoco.experimental.studio import messages

# ★ 本文件在 `算法库/通用/` 下，但它要 import 外壳侧的 `参数辨识`、`辨识桥`、`项目`
#   —— 那三个在 `软件/` 里。所以先保证 `软件/` 在 sys.path 上。
#   （外壳通过 `装配器` 装配时也会加，但本文件被单独 import 时同样要能跑，
#     所以这一道自己带 —— 不能依赖调用方帮忙铺路。）
import os as _os
import sys as _sys
_软件目录 = _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                           "..", "..", "软件"))
if _os.path.isdir(_软件目录) and _软件目录 not in _sys.path:
    _sys.path.insert(0, _软件目录)

from 参数辨识 import 参数定义, 采数据, 辨识                              # noqa: E402
from 辨识桥 import 辨识命令, 辨识状态                                     # noqa: E402

# ★ 模型目录不在这里数 `dirname` 的层数：本文件原来在 `算法库/通用/` 下，
#   方案 C 搬到 `算法库/通用/` 之后层数变了，数层数的写法会**静默**指到别的目录
#   （读不到参数表 → 所有模型都显示"不支持辨识"，很难查）。
#   统一从 `项目.py` 取，路径只有一处定义。
import 项目 as _项目                                                     # noqa: E402
_模型目录 = _项目.模型目录
_参数表路径 = os.path.join(_模型目录, "辨识参数表.json")


def 读取参数表() -> dict:
    """读 `模型/辨识参数表.json`（每个模型可辨识哪些连杆）。读不到就返回空表。"""
    try:
        with open(_参数表路径, encoding="utf-8") as f:
            数据 = json.load(f)
        return 数据.get("模型", {}) if isinstance(数据, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as 异常:                                        # noqa: BLE001
        print(f"⚠ 辨识参数表读取失败：{type(异常).__name__}: {异常}")
        return {}


def 查参数表(模型路径: str) -> tuple[list[tuple] | None, str]:
    """按模型路径查可辨识参数。返回 (参数列表, 说明)；查不到返回 (None, 原因)。

    ★ 为什么要按模型查（而不是像以前那样写死）：
      UR 系列的连杆叫 forearm_link / upper_arm_link / wrist_1_link，
      而 Panda 是 link4、iiwa 是 link2、xArm7 是 link1 —— 名字完全不同。
      以前写死 UR5e 的名字，换成别的机械臂后点"辨识"只会得到一堆无效结果，
      用户看不出来为什么。现在按模型查表，表里没有的模型就**明说"不支持"**。
    """
    if not 模型路径:
        return None, "还不知道模型路径"
    表 = 读取参数表()
    if not 表:
        return None, "找不到 模型/辨识参数表.json"
    规范 = os.path.normpath(模型路径).replace("\\", "/")
    部件 = 规范.split("/")
    键2 = "/".join(部件[-2:]) if len(部件) >= 2 else 规范
    键1 = 部件[-1]
    for 键, 条目 in 表.items():
        if 键 == 键2 or os.path.basename(键) == 键1:
            参数 = [(p["名称"], (p["连杆"], p["字段"]), float(p["初值"]),
                     (float(p["下界"]), float(p["上界"])))
                    for p in 条目.get("参数", [])]
            if 参数:
                return 参数, str(条目.get("显示名", 键))
    return None, f"模型库里没有「{键1}」的辨识参数配置"


class 参数辨识插件:
    """仿真侧插件：接收界面命令，执行辨识，回传状态。

    ★ 可辨识参数**按模型查表**（`模型/辨识参数表.json`），不再写死 UR5e 的连杆名。
      表里没有的模型会明确显示"不支持"，而不是假装跑一遍。
    """

    名称 = "参数辨识"
    版本 = "1.1"
    英文名 = "System identification"   # 面板上显示用（官方 UI 字体没有中文字形，面板只能画 ASCII）
    # 不写 ctrl[:]（不抢方向盘）→ 不会和别的算法互相覆盖
    接管控制 = False
    说明 = "在界面上做闭环激励采样 → 后台辨识惯性参数 → 用新参数验证轨迹拟合。"
    作者 = "数字样机"

    def __init__(self, 模型路径: str = ""):
        self.模型路径 = 模型路径
        self.状态 = "空闲"          # 空闲 / 采样中 / 辨识中 / 不支持
        self.进度 = ""
        self.结果行: list[tuple] = []      # [(名称, 标称, 估计值, 误差%)]
        self.拟合 = {}                     # {"标称": …, "辨识后": …}
        self.采样步数 = 0
        self.耗时 = 0.0
        self.日志: list[str] = []
        self._线程 = None
        self._数据 = None
        self._标称值 = {}
        self._模型 = None
        self.可辨识: list[tuple] = []      # 当前模型的可辨识参数（由 _刷新参数表 填）
        self.支持 = False
        self.不支持原因 = ""
        self._刷新参数表()

    # ------------------------------------------------------------------
    def _刷新参数表(self) -> None:
        """按当前 模型路径 换一张可辨识参数表。"""
        参数, 说明 = 查参数表(self.模型路径)
        if 参数 is None:
            self.支持 = False
            self.可辨识 = []
            self.不支持原因 = 说明
            self.状态 = "不支持"
            self.进度 = 说明
        else:
            self.支持 = True
            self.可辨识 = 参数
            self.不支持原因 = ""
            if self.状态 == "不支持":
                self.状态 = "空闲"
                self.进度 = ""

    def 收到模型(self, event) -> None:
        self._模型 = getattr(event, "model", None)
        if not self.模型路径:
            self.模型路径 = getattr(event, "路径", "") or self.模型路径
            self._刷新参数表()

    def 绑定模型路径(self, 路径: str) -> "参数辨识插件":
        self.模型路径 = 路径
        self._刷新参数表()
        return self

    def 模型已切换(self, 路径: str, 模型, 数据) -> None:
        """外壳在换模型后调用：清掉跟旧模型绑定的采样数据与结果。"""
        self.模型路径 = 路径
        self._数据 = None
        self._标称值 = {}
        self._模型 = 模型
        self.结果行 = []
        self.拟合 = {}
        self.采样步数 = 0
        self.耗时 = 0.0
        self.状态 = "空闲"
        self.进度 = ""
        self._刷新参数表()
        if self.支持:
            self._记(f"模型已切换为 {os.path.basename(路径)}（可辨识 "
                     f"{len(self.可辨识)} 个连杆质量）")
        else:
            self._记(f"⚠ 模型已切换为 {os.path.basename(路径)}，但{self.不支持原因}")

    # ------------------------------------------------------------------
    @messages.handler
    def 收命令(self, 命令: 辨识命令) -> bool:
        动作 = getattr(命令, "动作", "空闲")
        if 动作 == "采样":
            self._开始采样(float(getattr(命令, "时长", 1.0)))
        elif 动作 == "辨识":
            self._开始辨识()
        return False

    # ------------------------------------------------------------------
    def _记(self, 行: str) -> None:
        self.日志.append(行)
        if len(self.日志) > 12:
            self.日志 = self.日志[-12:]
        print(f"  [辨识] {行}", flush=True)

    def _开始采样(self, 时长: float) -> None:
        if self.状态 != "空闲":
            return
        if not self.模型路径:
            self._记("✗ 不知道模型路径，无法采样")
            return
        if not self.支持:
            # ★ 表里没有这个模型 → 明说，不要假装跑一遍（见 查参数表 的说明）
            self._记(f"✗ 当前模型不支持参数辨识：{self.不支持原因}")
            self._记("  要支持它，请在 模型/辨识参数表.json 里为它加一条配置")
            return
        self.状态 = "采样中"
        self.进度 = f"正在激励采样（{时长:.1f} 秒）…"
        try:
            t0 = time.time()
            self._数据 = 采数据(self.模型路径, 时长=时长)
            self.采样步数 = self._数据.步数
            # 记下当前模型的标称值（用于对比）
            self._标称值 = {名: 初 for 名, _, 初, _ in self.可辨识}
            self._记(f"✓ 采到 {self.采样步数} 步（{time.time()-t0:.1f}s）")
            # 顺手算一个"标称模型的拟合残差"作为基线
            self.拟合["标称"] = self._拟合残差(self._标称值)
            self._记(f"  标称参数下的拟合残差 {self.拟合['标称']:.6f}")
        except Exception as 异常:                                     # noqa: BLE001
            self._记(f"✗ 采样失败：{type(异常).__name__}: {异常}")
        finally:
            self.状态 = "空闲"
            self.进度 = ""

    def _拟合残差(self, 值表: dict) -> float:
        """给定参数，用记录的 τ 做一步预测，返回残差范数（越小越贴合数据）。"""
        数据 = self._数据
        参数们 = [参数定义(名, 目标, 值表.get(名, 初), 界[0], 界[1])
                  for 名, 目标, 初, 界 in self.可辨识]
        try:
            模型 = _按参数造模型(self.模型路径, 参数们)
        except Exception:                                            # noqa: BLE001
            return float("inf")
        import mujoco
        d = mujoco.MjData(模型)
        下标 = np.arange(1, len(数据.时间), 5)
        平方 = 0.0
        for k in 下标:
            d.qpos[:] = 数据.qpos[k - 1]
            d.qvel[:] = 数据.qvel[k - 1]
            mujoco.mj_forward(模型, d)
            d.ctrl[:] = 数据.ctrl[k]
            mujoco.mj_step(模型, d)
            平方 += float(np.sum((d.qpos - 数据.qpos[k]) ** 2))
        return float(np.sqrt(平方 / max(len(下标), 1)))

    def _开始辨识(self) -> None:
        if self.状态 != "空闲":
            return
        if not self.支持:
            self._记(f"✗ 当前模型不支持参数辨识：{self.不支持原因}")
            return
        if self._数据 is None:
            self._记("✗ 还没有采样数据，先点「激励采样」")
            return
        self.状态 = "辨识中"
        self.进度 = "辨识中（后台线程）…"
        self._线程 = threading.Thread(target=self._辨识线程, daemon=True)
        self._线程.start()

    def _辨识线程(self) -> None:
        try:
            参数们 = [参数定义(名, 目标, 初, 界[0], 界[1])
                      for 名, 目标, 初, 界 in self.可辨识]
            结果 = 辨识(self._数据, 参数们, 抽稀=5,
                        打印=lambda 行: self._记(行.strip()))
            self.耗时 = 结果.耗时
            估计 = {名: float(v) for (名, _, _, _), v in
                    zip(self.可辨识, 结果.估计值)}
            self.结果行 = []
            for 名, _, 初, _ in self.可辨识:
                估 = 估计[名]
                误 = abs(估 - 初) / max(abs(初), 1e-9) * 100
                self.结果行.append((名, 初, 估, 误))
            self.拟合["辨识后"] = self._拟合残差(估计)
            改善 = (self.拟合.get("标称", 0) / max(self.拟合.get("辨识后", 1e-12), 1e-12))
            self._记(f"✓ 辨识完成：耗时 {self.耗时:.1f}s")
            self._记(f"  拟合残差 {self.拟合.get('标称', float('nan')):.6f} → "
                     f"{self.拟合.get('辨识后', float('nan')):.6f}（改善 {改善:.1f}×）")
        except Exception as 异常:                                     # noqa: BLE001
            self._记(f"✗ 辨识失败：{type(异常).__name__}: {异常}")
        finally:
            self.状态 = "空闲"
            self.进度 = ""

    # ------------------------------------------------------------------
    def 指标(self) -> dict:
        return {"已采样步数": float(self.采样步数)}

    def 插件状态(self) -> dict:
        return {"状态": self.状态, "采样": self.采样步数,
                "拟合改善": (f"{self.拟合.get('标称',0)/max(self.拟合.get('辨识后',1),1e-12):.1f}×"
                            if "辨识后" in self.拟合 else "—")}

    def 状态消息(self) -> 辨识状态:
        """打包给界面的状态。"""
        return 辨识状态(状态=self.状态, 进度=self.进度, 采样步数=self.采样步数,
                        结果=list(self.结果行), 拟合=dict(self.拟合),
                        耗时=self.耗时, 日志=list(self.日志[-8:]))


def _按参数造模型(模型路径: str, 参数们: list[参数定义]):
    """按参数造模型（复用 参数辨识 里的边界夹取与写入逻辑）。"""
    import mujoco
    from 参数辨识 import _写参数
    spec = mujoco.MjSpec.from_file(模型路径)
    for p in 参数们:
        _写参数(spec, p.目标, float(np.clip(p.初值, p.下界, p.上界)))
    return spec.compile()
