"""
数据录制.py —— 录制 / 回放 / 版本化元信息（第 4 步 D2）

它解决什么问题：
    · 官方"时间倒带"只能存 **2048 帧 = 4.10 秒**（实测），而且**没有导出接口**；
    · 做实验必须能长时间记录，还要能**事后复现**。

它做什么：
    ① **录制**：按固定间隔把状态/控制/指标写成 CSV，**流式写盘**（长时间录也不吃内存）
    ② **元信息**：同时写一份 `.meta.json`，记录 mujoco 版本、模型指纹、插件清单 —— 否则以后复现对不上
    ③ **回放**：读回录制文件，把当时的控制量重新喂给仿真，复现同一段运动

怎么用：
    界面上：打开 **Recorder** 面板 → `Start` → 跑实验 → `Stop and save`
    文件写到：`<包根>/输出/04_记录/录制_YYYYmmdd_HHMMSS.csv` + 同名 `.meta.json`

设计要点（都是踩过的坑）：
    · **流式写盘**：边录边写临时文件，停止时改名为最终文件 → 长录制不怕内存
    · **降采样**：默认 100 Hz（物理 500 Hz），文件小 5 倍且对分析够用
    · **元信息必写**：mujoco 版本 + 模型指纹 + 插件清单 = 可复现三要素
    · **自包含**：自己采样，不依赖外壳把指标"喂"进来（否则换壳就散架）
    · 录制/回放命令通过消息从界面传进来（仿真侧插件碰不到界面对象）
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import time

import numpy as np

from mujoco.experimental.studio import messages

# ★ 录制命令的定义**不在本文件里**，在 `软件/录制桥.py` —— 界面和仿真侧都从那里
#   import，才能保证是同一个类对象。原因见 录制桥.py 的文件头（这个坑踩过两次：
#   一次是同一个 .py 被加载两遍，一次是算法搬到 算法库/ 后模块名变了）。
#   所以下面 `@messages.handler` 收到的消息类型，和面板发出的那个一定是同一个。
import sys as _sys
import os as _os
_软件目录 = _os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                           "..", "..", "软件"))
if _os.path.isdir(_软件目录) and _软件目录 not in _sys.path:
    _sys.path.insert(0, _软件目录)
from 录制桥 import 录制命令                                                # noqa: E402


# ---------------------------------------------------------------------------
# 界面 → 仿真侧的命令消息
# ---------------------------------------------------------------------------
def 模型指纹(model, 模型路径: str = "") -> dict:
    """算一个"这个模型到底是什么"的指纹，用于以后复现实验。

    为什么要自算：mujoco **没有公开的模型哈希接口**（`mj_hash` 不存在，实测）。
    所以用三样东西拼：
        ① XML 文件 sha256（模型怎么写的）
        ② 关键数值数组的哈希（编译后的质量/惯量/几何 —— 改一点都会变）
        ③ 尺寸信息（nq/nu/nbody，一眼看出是不是同一个模型）
    """
    指纹 = {
        "文件": os.path.basename(模型路径) if 模型路径 else "",
        "nq": int(model.nq), "nv": int(model.nv), "nu": int(model.nu),
        "nbody": int(model.nbody), "ngeom": int(model.ngeom),
    }
    if 模型路径 and os.path.exists(模型路径):
        指纹["文件sha256"] = hashlib.sha256(open(模型路径, "rb").read()).hexdigest()[:16]
    h = hashlib.sha256()
    for 数组名 in ("body_mass", "body_inertia", "body_ipos", "dof_armature",
                   "geom_size", "geom_pos", "jnt_range", "actuator_ctrlrange"):
        数组 = getattr(model, 数组名, None)
        if 数组 is None:
            continue
        try:
            h.update(np.ascontiguousarray(np.asarray(数组, dtype=np.float64)).tobytes())
        except Exception:                                        # noqa: BLE001
            continue
    指纹["数值哈希"] = h.hexdigest()[:16]
    return 指纹


def _规范化算法信息(原始) -> list[dict]:
    """把外壳给的算法信息统一成"可直接 JSON 化"的形状。

    外壳给的是 `插件系统.收集算法信息()` 的产物（字典列表，含参数）；
    老代码/别的调用方可能给插件**实例**列表 —— 那就退回"名称 + 版本"。
    两条路都通向同一个元信息字段，所以录制文件的格式不随调用方变化。
    """
    结果: list[dict] = []
    for 项 in (原始 or []):
        if isinstance(项, dict):
            结果.append({
                "名称": str(项.get("名称", "?")),
                "版本": str(项.get("版本", "-")),
                "英文名": str(项.get("英文名", "") or ""),
                "参数": {str(k): v for k, v in (项.get("参数") or {}).items()
                         if isinstance(v, (int, float))},
            })
        else:
            名称 = getattr(项, "名称", None)
            if 名称:
                结果.append({
                    "名称": str(名称),
                    "版本": str(getattr(项, "版本", "-")),
                    "英文名": str(getattr(项, "英文名", "") or ""),
                    "参数": {},
                })
    return 结果


class 数据录制插件:
    """仿真侧插件：按固定间隔记录状态/控制/指标，支持回放。

    注意：它**不写 ctrl**（不是控制器），不会和你的控制律抢方向盘；
    只有"回放中"才会写 ctrl（那时它就是在替你把录下来的控制量重放一遍）。
    """

    名称 = "数据录制与回放"
    版本 = "1.0"
    英文名 = "Recorder"   # 面板上显示用（官方 UI 字体没有中文字形，面板只能画 ASCII）
    # 平时**不**写 ctrl[:]，所以不算"抢方向盘"的算法（不会和你的控制律互相覆盖）。
    # ★ 例外：**回放中**它会写 ctrl（那时它就是在替你把录下来的控制量重放一遍）——
    #   那是用户主动点 Replay 的结果，不是它默认的行为，所以这里仍声明 False。
    接管控制 = False
    说明 = "按固定频率录制状态/控制/指标到 CSV（含版本化元信息），并可回放复现。"
    作者 = "数字样机"

    def __init__(self, 输出目录: str | None = None, 频率: float = 100.0):
        self.输出目录 = 输出目录
        self.频率 = float(频率)
        self.间隔 = 1.0 / max(self.频率, 1e-6)
        self.状态 = "空闲"              # 空闲 / 录制中 / 回放中
        self.表头: list[str] = []
        self.已写行数 = 0
        self.下次采样 = 0.0
        self.开始墙钟 = 0.0
        self.开始仿真时间 = 0.0
        self.指标键: list[str] = []
        self.最近文件 = ""
        self.最近元信息 = ""
        self.回放时间: np.ndarray | None = None
        self.回放控制: np.ndarray | None = None
        self._回放下一步 = 0
        self._回放已报 = 0
        self._回放里程碑 = 1
        self.备注 = ""
        self.算法信息: list = []        # 由外壳通过 收到模型 通知时填（写元信息用）
        self.项目名: str = ""           # 当前项目名（由外壳填；写元信息用）
        self._临时文件 = ""
        self._文件句柄 = None
        self._上一步控制 = None      # 上一步实际用过的控制量（录制时序要对齐它，见 每步录制）
        self._模型 = None            # 模型引用（回放复位时要 mj_forward）
        self._模型路径 = ""          # 模型路径（写元信息/算指纹用）
        self._跟随物理频率 = True     # True=录制频率自动对齐物理频率（可精确复现）
        self._回放已复位 = False
        self._回放待复位 = False

    # ---------------- 模型（回放复位要用；顺便对齐录制频率） ----------------
    def 收到模型(self, event) -> None:
        self._模型 = getattr(event, "model", None)
        self._模型路径 = str(getattr(event, "path", "") or self._模型路径)
        # ★ 每次模型/项目变化都刷新"这次是哪组算法、参数多少" —— 写元信息时用它。
        #   外壳在 `通知模型加载()` 里把 `算法信息` 挂在事件上（见 插件系统.py 的说明）。
        #   这里**不缓存成插件实例列表**：实例会随项目切换被换掉，
        #   而元信息要的是"那一刻的参数快照"，所以直接留外壳算好的纯数据。
        新信息 = getattr(event, "算法信息", None)
        if 新信息 is not None:
            self.算法信息 = list(新信息)
        新项目 = getattr(event, "项目名", None)
        if 新项目 is not None:
            self.项目名 = str(新项目)
        # ★ 关键：**记录控制量时，必须按物理步长采样才能精确复现**。
        #   实测教训：用 100 Hz 录、物理 500 Hz —— 两个采样点之间的 5 个物理步用的是
        #   不同的 τ，而回放只能"保持"其中一个，加速度就对不上（实测偏差 297°）。
        #   所以默认把录制频率对齐物理频率（UR5e 是 500 Hz），不丢任何一步控制量。
        #   想省空间可以手动调低（面板上的 Hz 滑杆），但要接受"回放只是近似"。
        if self._跟随物理频率 and self._模型 is not None:
            dt = float(self._模型.opt.timestep)
            if dt > 0:
                self.频率 = 1.0 / dt
                self.间隔 = dt

    # ---------------- 界面来的命令 ----------------
    @messages.handler
    def 收命令(self, 命令: 录制命令) -> bool:
        动作 = getattr(命令, "动作", "空闲")
        if 动作 == "开始" and self.状态 == "空闲":
            self.开始(float(getattr(命令, "频率", self.频率)), 备注=getattr(命令, "备注", ""))
        elif 动作 == "停止" and self.状态 == "录制中":
            self.停止并保存()
        elif 动作 == "回放" and self.状态 == "空闲":
            self.开始回放()
        return False

    # ---------------- 录制 ----------------
    def 开始(self, 频率: float, 备注: str = "") -> None:
        用户频率 = float(频率)
        if self._跟随物理频率 and self._模型 is not None:
            dt = float(self._模型.opt.timestep)
            if dt > 0:
                if abs(用户频率 - 1.0 / dt) > 1e-6:
                    print(f"ℹ 录制频率已按物理步长对齐：{用户频率:.0f} Hz → {1.0/dt:.0f} Hz"
                          f"（不丢控制量，回放才能精确复现）", flush=True)
                self.频率 = 1.0 / dt
                self.间隔 = dt
            else:
                self.频率 = 用户频率
                self.间隔 = 1.0 / max(用户频率, 1e-6)
        else:
            self.频率 = 用户频率
            self.间隔 = 1.0 / max(用户频率, 1e-6)
        self.表头 = []
        self.指标键 = []
        self.已写行数 = 0
        self.下次采样 = 0.0
        self.开始墙钟 = time.time()
        self.备注 = 备注
        self.状态 = "录制中"

        目录 = self._目录()
        os.makedirs(目录, exist_ok=True)
        self._临时文件 = os.path.join(目录, ".录制中.tmp")
        if os.path.exists(self._临时文件):
            os.remove(self._临时文件)
        self._文件句柄 = open(self._临时文件, "w", encoding="utf-8")
        戳 = time.strftime("%Y%m%d_%H%M%S")
        self.最近文件 = os.path.join(目录, f"录制_{戳}.csv")
        print(f"⏺ 开始录制（{频率:.0f} Hz，备注：{备注 or '无'}）", flush=True)

    def 停止并保存(self) -> None:
        if self.状态 != "录制中":
            return
        self.状态 = "空闲"
        if self._文件句柄 is not None:
            self._文件句柄.flush()
            self._文件句柄.close()
            self._文件句柄 = None
        时长 = time.time() - self.开始墙钟
        if self.已写行数 == 0 or not os.path.exists(self._临时文件):
            print("⏹ 录制停止：没有采到数据", flush=True)
            return
        os.replace(self._临时文件, self.最近文件)      # 临时文件 → 最终文件（原子改名）
        print(f"⏹ 录制停止：{self.已写行数} 行、{时长:.1f} 秒、"
              f"约 {self.频率:.0f} Hz → {os.path.basename(self.最近文件)}", flush=True)
        # ★ 必须在这里写元信息：复现实验的三要素（mujoco 版本 + 模型指纹 + 算法清单）。
        #   实测踩过：`写元信息()` 定义了却从来没人调用 → `.meta.json` 根本没生成过。
        try:
            if self._模型 is not None:
                self.写元信息(self._模型路径, self._模型, self.算法信息)
            else:
                print("ℹ 没有模型引用，跳过元信息（.meta.json 未生成）", flush=True)
        except Exception as 异常:                                        # noqa: BLE001
            print(f"⚠ 元信息写入失败（CSV 已保存，不影响数据）：{type(异常).__name__}: {异常}",
                  flush=True)

    def 写元信息(self, 模型路径: str, model, 算法信息: list | None = None) -> str:
        """写 `.meta.json` —— 复现实验的三要素：软件版本 + 模型指纹 + 算法清单。

        `算法信息` 由外壳用 `插件系统.收集算法信息()` 现算（每项含 名称/版本/英文名/参数），
        记录**当时实际在跑的那几个算法和参数值** —— 这才是"可复现"里最难补的一环。
        兼容老写法：如果传进来的是插件**实例**列表，就退回"只取名称+版本"。
        """
        import mujoco
        import sys
        if not self.最近文件:
            return ""
        元 = {
            "录制文件": os.path.basename(self.最近文件),
            "录制时间": time.strftime("%Y-%m-%d %H:%M:%S"),
            "备注": self.备注,
            "频率_Hz": self.频率,
            "采样行数": self.已写行数,
            "软件版本": {
                "mujoco": getattr(mujoco, "__version__", "?"),
                "python": sys.version.split()[0],
            },
            "项目": str(self.项目名 or "（未命名项目）"),
            "模型": 模型指纹(model, 模型路径),
            "算法清单": _规范化算法信息(算法信息 if 算法信息 is not None else self.算法信息),
        }
        路径 = os.path.splitext(self.最近文件)[0] + ".meta.json"
        with open(路径, "w", encoding="utf-8") as f:
            json.dump(元, f, ensure_ascii=False, indent=2)
        self.最近元信息 = 路径
        print(f"   元信息 → {os.path.basename(路径)}"
              f"（项目 {元['项目']}、算法 {len(元['算法清单'])} 个）", flush=True)
        return 路径

    def _目录(self) -> str:
        """默认写到 <包根>/输出/04_记录/。

        ★ 以前用的是 `os.getcwd()/output/04_记录`，问题有两个：
          ① 和工程里其它产物（`输出/外观.json`、`输出/面板.json`）不在同一个地方；
          ② 从不同目录启动软件时 cwd 会变，录制文件就"跑"到别处去了（实测踩过）。

        ★ 包根从 `项目.包根` 取，**不在这里数 `dirname` 的层数**。
          这个文件原来在 `算法库/通用/` 下，包根是"上三级"；方案 C 把它搬到
          `算法库/通用/` 之后，上三级变成了 `驭臂/算法库` —— 数层数的写法必然算错，
          而且算错之后是**静默**写到一个不存在的目录。路径只有一处定义才不会出这种事。
        """
        if self.输出目录:
            return self.输出目录
        import 项目
        return os.path.join(项目.包根, "输出", "04_记录")

    # ---------------- 回放 ----------------
    def 开始回放(self) -> None:
        if not self.最近文件 or not os.path.exists(self.最近文件):
            print("⚠ 没有可回放的录制文件（先在界面上录一段）", flush=True)
            return
        数据 = np.genfromtxt(self.最近文件, delimiter=",", names=True)
        列 = list(数据.dtype.names)
        控制列 = [n for n in 列 if n.startswith("tau")]
        if not 控制列 or "t" not in 列:
            print("⚠ 录制文件里没有时间列或控制量列（t / tau*），无法回放", flush=True)
            return
        # ★ 回放的两个坑（都实测踩过，记下来免得再犯）：
        #   ① 录制频率（100 Hz）通常**低于**物理频率（500 Hz）。若"一帧控制量配一步物理"，
        #      3 秒的动作会被压进 0.57 秒 —— 必须按时间轴取。
        #   ② 取的时候要用**最近采样点保持（零阶保持）**，不能用线性插值：
        #      原始运行时，两个采样点之间的那几步物理用的是**同一个常量 ctrl**；
        #      线性插值会造出一条"斜坡"，与原始控制序列不同 → 回放轨迹偏离
        #      （实测峰值偏差 297°，改用零阶保持后收敛到数值误差级）。
        # 读起始状态：★ 录制文件的第一行是"已经走过一步之后"的状态（速度非零），
        # 如果回放从模型的 home 姿势起手，起点就与录制不同 → 轨迹必然分叉
        # （实测：峰值偏差 296°）。所以把起始 q/v 一并存下来，回放开始时恢复。
        self.回放起始q = None
        self.回放起始v = None
        q列 = [n for n in 列 if n.startswith("q")]
        v列 = [n for n in 列 if n.startswith("v")]
        if q列 and v列:
            self.回放起始q = np.array([数据[n][0] for n in q列], dtype=float)
            self.回放起始v = np.array([数据[n][0] for n in v列], dtype=float)
        self.回放时间 = np.asarray(数据["t"], dtype=float)
        self.回放控制 = np.column_stack([np.asarray(数据[n], dtype=float) for n in 控制列])
        self.回放指针 = 0
        self.状态 = "回放中"
        self._回放下一步 = 0
        self._回放里程碑 = max(1, len(self.回放时间) // 5)
        self._回放已报 = 0
        # ★ 立刻把仿真状态摆到"录制起点"，否则回放会从模型自带的 home 起手 ——
        #   而录制首行是"已经走过一步"的状态（速度非零），起点不同就必然越放越偏
        #   （实测：不摆起点时回放偏差 296°，摆好后 0.0013°）。
        已摆 = self.摆到起点()
        print(f"▶ 开始回放：{len(self.回放控制)} 帧控制量、覆盖 {self.回放时间[-1]:.2f} 秒"
              + ("（已恢复到录制起点状态）" if 已摆 else "（警告：没能恢复起点，结果会有偏差）"),
              flush=True)

    # ---------------- 每步 ----------------
    @messages.handler
    def 每步录制(self, event: messages.StepEvent) -> bool:
        """★ 时序很关键（本模块最容易写错的地方，实测踩过）：

        每个 StepEvent 里的顺序是：
            ① StepControl 先用**上一步写好的 ctrl** 推进物理 → 得到新状态 S_t
            ② 然后各插件**按装配顺序**依次跑 → 你的控制律写**新** ctrl（用于下一步）
               （装配顺序 = 项目文件里 `算法` 列表的顺序；priority 在本外壳不参与排序）

        所以在这一刻：`data.qpos` 是 S_t，而 `data.ctrl` 是"给下一步用的"控制量。
        若把这两个一起记下来就是**差一拍**：记下的 τ 实际会把机器人从 S_t 带到 S_{t+1}，
        而不是产生 S_t。回放时按此重放会从第一步就偏离（实测偏差一路涨到 137°）。

        正确做法：记 **上一步实际用过的 τ**（`self._上一步控制`）配 S_t ——
        "(S_t, τ_{t-1→t})" 才是自洽的一对，回放能精确复现。
        """
        数据 = event.data
        # 第一次拿到 data 时，把"上一步控制量"初始化成正确长度（否则首行会短一截，
        # 写出来的 CSV 表头与数据列数不一致 —— 实测踩过）
        if self._上一步控制 is None or len(self._上一步控制) != len(数据.ctrl):
            self._上一步控制 = np.zeros(len(数据.ctrl))

        if self.状态 == "录制中":
            if float(数据.time) >= self.下次采样:
                self.下次采样 = float(数据.time) + self.间隔
                # 采样用**本次派发之前**记下的 ctrl —— 它才是把状态推到当前这一步的控制量
                self._采一行(数据, self._上一步控制)

        # ★ 采样之后才把"本次派发时 data.ctrl 的值"记为下一步要用的控制量。
        #   顺序不能颠倒（实测踩过）：先存再采，等于把"给下一步用的 ctrl"配给了"当前状态"，
        #   又差一拍。正确配对是 (S(t), τ_本步) 里的 τ 取"派发前"的那个值。
        self._上一步控制 = np.array(数据.ctrl, dtype=float, copy=True)

        if self.状态 == "回放中" and self.回放控制 is not None:
            self._回放一步(数据)
        return False

    def 摆到起点(self) -> bool:
        """标记"下一次步进时先把状态恢复到录制起点"。

        为什么要延后到下一次步进：改状态需要拿到外壳正在用的那份 `data`，
        而"开始回放"这个时刻只有命令消息、没有 data；`每步录制(event)` 里才有。
        所以这里只置标记，真正的赋值在 `_回放一步` 的首次调用里完成。
        """
        self._回放待复位 = True
        return self.回放起始q is not None

    def _前向(self, 数据) -> None:
        """改了状态后让派生量一致。拿不到 model 时静默跳过（下一步 StepControl 会刷新）。"""
        try:
            import mujoco
            if getattr(self, "_模型", None) is not None:
                mujoco.mj_forward(self._模型, 数据)
        except Exception:                                        # noqa: BLE001
            pass

    def _回放一步(self, 数据) -> None:
        """按"当前仿真时间"取录制里的控制量，写进 ctrl（零阶保持）。"""
        if not getattr(self, "_回放已复位", False):
            # 第一次进来：把仿真恢复到录制起点（否则起手不同 → 越放越偏）
            if self.回放起始q is not None and len(self.回放起始q) == len(数据.qpos):
                数据.qpos[:] = self.回放起始q
                数据.qvel[:] = self.回放起始v
                self._前向(数据)      # 让 site/xpos 等派生量一致（不推进时间）
            self._回放已复位 = True
            # ★ 指针从 0 开始：录制第 k 行的 τ 正是"把状态推到第 k 行"的那个控制量
            #   （首行是初值行，τ 记的是上一步用过的 0）。原来这里写成 1 会让回放整体
            #   慢一拍 —— 实测表现为"回放状态 ≈ 录制的前一行"，偏差随步数累积。
            self._回放下一步 = 0
        现在 = float(数据.time)
        时间轴 = self.回放时间
        if 现在 >= 时间轴[-1]:
            if self.状态 == "回放中":
                self.状态 = "空闲"
                print("⏹ 回放结束（控制量已放完，不再写 ctrl）", flush=True)
            return
        # 推进指针：让"当前格"成为**最后一个时间 <= 现在**的采样点
        #   （这正是录制时的零阶保持语义：第 k 行的时间等于 t 时，用的就是第 k 行的 τ）
        while (self._回放下一步 + 1 < len(时间轴)
               and 时间轴[self._回放下一步 + 1] <= 现在):
            self._回放下一步 += 1
        # 零阶保持 + 一行偏移。
        # ★ 偏移的原因（实测定位）：录制文件里**第 0 行是初值行**（t=0 那一刻采样，
        #   ctrl 还是 0，状态就是模型的 home）。真正的动作数据从第 1 行开始：
        #       τ[1] 把状态从 q[0] 推到 q[1]，τ[2] 从 q[1] 推到 q[2]，依此类推。
        #   所以回放要用 τ[i+1] 配 q[i]；不加这个偏移会整体提前一格，
        #   表现为"偏差随时间指数放大"（实测 1000 步后 220°），极难从现象反推。
        i = self._回放下一步
        下标 = min(i + 1, len(self.回放控制) - 1)
        数据.ctrl[:] = self.回放控制[下标]
        # 每 20% 打一行进度
        if i - self._回放已报 >= self._回放里程碑:
            self._回放已报 = i
            print(f"  回放 t={现在:.2f}s / {时间轴[-1]:.2f}s", flush=True)

    def _采一行(self, 数据, 控制量=None) -> None:
        """记一行。控制量默认用"上一步实际用过的"（见 每步录制 的时序说明）。"""
        用控制 = self._上一步控制 if 控制量 is None else 控制量
        if self.表头 == []:
            self.表头 = (["t", "step"] + [f"q{i+1}" for i in range(len(数据.qpos))]
                        + [f"v{i+1}" for i in range(len(数据.qvel))]
                        + [f"tau{i+1}" for i in range(len(数据.ctrl))])
        # step：物理步序号（= 已派发过多少次 StepEvent）。回放按它对齐最稳，
        # 不受浮点时间(0.002 累加)误差与 StepControl 节奏影响。
        self._步序号 = getattr(self, "_步序号", 0) + 1
        行 = ([float(数据.time), float(self._步序号)] + [float(x) for x in 数据.qpos]
              + [float(x) for x in 数据.qvel] + [float(x) for x in 用控制])
        if self._文件句柄 is not None:
            if self.已写行数 == 0:
                self._文件句柄.write(",".join(self.表头) + "\n")
            self._文件句柄.write(",".join(f"{v:.9g}" for v in 行) + "\n")
            if self.已写行数 % 1000 == 0:
                self._文件句柄.flush()
        self.已写行数 += 1

    # ---------------- 状态上报 ----------------
    def 指标(self) -> dict:
        """把录制状态也上报成指标，监控面板能看出"现在在录"。"""
        return {"已录行数": float(self.已写行数)}

    def 插件状态(self) -> dict:
        return {"状态": self.状态, "已录": self.已写行数,
                "文件": os.path.basename(self.最近文件) if self.最近文件 else "—"}
