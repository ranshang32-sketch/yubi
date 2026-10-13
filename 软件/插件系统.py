"""
插件系统.py —— 我们自己的插件兼容层（整个外壳里**唯一**直接碰官方实验性 API 的文件）

为什么要单独一个文件？
  官方的插件系统在 `mujoco.experimental.studio` 里，"experimental" = 官方不保证不改。
  11 周内它已经改过 4 次结构。所以我们把**所有官方调用集中在这一个文件**，
  以后官方再改，只需要改这里；主程序和 plugins/ 里的控制算法一行都不用动。

这个文件给外壳补了 3 件官方没有的东西：
  ① 插件出错隔离 —— 一个插件崩了，只停它自己，整个软件继续跑（官方会一起挂）
  ② 版本自检     —— 启动时打印 mujoco 版本 + API 指纹，跟"已知能跑"的版本比对
  ③ 插件清单     —— 每个插件的名字/版本/需要什么，启动时列一张表出来

★ 给用户（你）的规则：**写控制算法不需要看懂这个文件**，
  只要 `from 插件系统 import 控制插件, 每步, 滑块目标`，然后照着 plugins/ 里的例子写。
"""
from __future__ import annotations

import os
import sys
import traceback

# ---------------------------------------------------------------------------
# ① 官方 API 的唯一入口
# ---------------------------------------------------------------------------
MUJOCO版本要求 = ">=3.12"          # 插件系统从这个版本开始有
已知可用版本 = ("3.13.0",)          # 我们实测跑通过的 mujoco 版本（见第 0 步验收报告）


def _导入官方():
    """导入官方 studio 插件系统。失败时抛人话版异常（附解决办法）。"""
    try:
        import mujoco
        from mujoco.experimental import studio

        # 逐个点名导入，比 import * 更容易发现"哪个东西没了"
        from mujoco.experimental.studio import messages       # 消息类型 + handler 标签
        from mujoco.experimental.studio import step_control   # 官方默认步进插件
        from mujoco.experimental.studio import viewer_app     # 官方 GUI（19 个面板）
        from mujoco.experimental.studio import viewer_protocol  # 配置类
        from mujoco.experimental.studio import launch_native   # 原生窗口
        from mujoco.experimental.studio import launch_thread   # 线程版端点
        from mujoco.experimental.studio import viewer_handle   # 仿真侧句柄
        from mujoco.experimental.studio import endpoints       # 消息通道
    except ImportError as e:
        提示 = (
            f"\n✗ 当前 Python 环境里没有可用的 Studio 插件系统：{e}\n\n"
            f"  你现在用的是：{sys.executable}\n"
            f"  原因：Studio 插件系统只在官方 pip 包（mujoco >= 3.12 的完整版）里有，\n"
            f"        conda 渠道装的 mujoco 是「零件版」，不含界面层和插件系统。\n\n"
            f"  解决：用叠加层环境跑（第 0 步已经建好）：\n"
            f"    cd \"$HOME/Desktop/驭臂\"\n"
            f"    .venv/bin/python 软件/主程序.py\n"
        )
        raise SystemExit(提示) from e
    return mujoco, messages, step_control, viewer_app, viewer_protocol, launch_native, launch_thread, viewer_handle, endpoints


(mujoco, messages, step_control, viewer_app, viewer_protocol,
 launch_native, launch_thread, viewer_handle, endpoints) = _导入官方()

每步 = messages.handler                      # 贴标签：让这个方法参与每一步仿真

# ---------------------------------------------------------------------------
# 优先级：**仿真侧不参与排序**（但别搞混 —— 窗口侧是参与的，两侧行为不一样）
# ---------------------------------------------------------------------------
# ★ 先记住这条分界线，把两侧混起来想会得出错误结论：
#
#   ┌ 窗口侧（面板 / 界面桥 …）：走**官方**派发 → priority **有效**
#   │   插件由 `启动.py` 通过 `launch_native.run_native_viewer(..., plugins=窗口插件)`
#   │   交给官方；官方 `Viewer.dispatch` → `PluginRegistry.dispatch` 把同类型处理器
#   │   收成一条链并**按 priority 降序执行**（`sort(key=…, reverse=True)`，实测见
#   │   `mujoco/experimental/studio/plugin_registry.py`）。
#   │   所以面板里写 `priority=CRITICAL` 是**真起作用**的
#   │   （例如外观面板必须在所有窗口 Begin 之前跑完换肤）。
#   │
#   └ 仿真侧（控制算法 / 模型应用器 / 参数应用器 …）：走**我们的**派发 → priority **无效**
#       本文件为了做出错隔离没有走官方那条路：`安全注册表.处理消息()` 是**逐个插件**
#       依次调用（`for 插件 in self._目标`），顺序 = `_目标` 列表顺序 = 项目文件里
#       `算法` 列表的顺序（官方 StepControl 固定排在第 0 个）。
#
#   一句话：**面板看 priority，控制算法看装配顺序。**
#
# 仿真侧的三条后果（都实测过）：
#   ① **跨插件**"谁说了算"只看列表顺序：排在最后的最后写 `ctrl[:]`，它赢。
#      `@每步(priority=…)` 在这里**完全不起作用** —— 它只是把档位记在处理器上，
#      我们的 `_单独派发()` 不读它（官方 `_discover_handlers` 本身也不排序）。
#   ② **单个插件内部**的多个处理器按 `dir()` 字母序走，所以同一个插件里想控制先后，
#      别指望 priority，改方法名或合并成一个方法。
#   ③ 算法作者写的 priority 声明**不算白写**：保留它贴合官方语义，
#      日后若真改成按 priority 排序，这些声明会自然生效。
#
# 想让某个算法赢：在界面【Algorithms】面板把它调到列表最后，或改项目文件的算法列表。
# 历史教训：曾有 5 个项目都写 `"算法": "*"`，扫描顺序让【正弦摆动】排到最后，
# 于是它偷偷盖住了关节 PD（表现为"机械臂按正弦来回摆"）。见 CHANGELOG v0.4.1。
优先级 = messages.Priority                   # CRITICAL=1000 > USER=100（默认）> LIBRARY=10 > INTERNAL=1


# ---------------------------------------------------------------------------
# ② 插件基类：给用户一个"填空题"模板
# ---------------------------------------------------------------------------
class 控制插件:
    """所有控制算法的爸爸。子类只需要写：名称 + 每步控制()。

    类属性（写在子类里，纯数据，不执行代码）：
        名称    : str   插件名，启动清单里显示
        版本    : str   插件版本
        说明    : str   一句话说明（中文，可以写很清楚）
        作者    : str   谁写的（可选）
    方法（必须实现）：
        每步控制(self, event: messages.StepEvent) -> bool
            每转一圈仿真调用一次。在这里读状态、算力矩、写 event.data.ctrl[:]。
            ★ 必须写类型标注 event: messages.StepEvent，否则官方 @每步 会报错。
            ★ 返回 False = 不拦截（让别人也能看到）；返回 True = 吃掉消息（后面的人收不到）。
    """

    名称 = "未命名插件"
    版本 = "0.0"
    说明 = ""
    作者 = ""
    # 本算法是否"接管方向盘"——也就是会不会往 `event.data.ctrl[:]` 里写力矩。
    #
    # ★ 为什么要声明这件事（踩过的真实困扰）：
    #   多个算法都写 `ctrl[:]` 时，**后装配的整体覆盖前面的** —— 被覆盖的那个
    #   其实一步都没生效，但界面上照样显示"✓ 已加载"，用户完全看不出来。
    #   实测：`末端两点运动`(任务空间) + `关节pd控制` 同时挂、关节PD 在后时，
    #   末端算法的输出被整体盖掉，机械臂纹丝不动地按关节 PD 走，
    #   末端离目标点 394.7 mm（单独跑它时是 0.1 mm）。
    #
    #   有了这个声明，外壳就能在装配时报一句"这几个都在写 ctrl，只有最后一个生效"，
    #   把"静默被掩盖"变成"看得见的提示"。
    #
    # 语义说明（别当它保证"永不写 ctrl"）：这个标记表示**默认会不会驱动机器人**，
    # 用来判断"多个算法是否在抢同一个方向盘"。所以：
    #   · 默认 True —— 新写算法的人多半就是要控制机器人，忘了声明也不会被漏报；
    #   · 平时不写 ctrl 的算法（录制/辨识/展示）显式声明 False，
    #     否则会被算进"抢方向盘"的名单里、制造假警告；
    #   · 像"数据录制"这种**平时不写、回放时才写**的，仍算 False
    #     —— 回放是用户主动点的，不是它的默认行为。
    接管控制 = True

    # ---- 插件自己的状态（比如"跑了多少步"），由外壳负责收集 ----
    def 插件状态(self) -> dict:
        """返回要在启动清单里显示的一行摘要，例如 {'跟踪误差': '0.12 mm'}。"""
        return {}

    # ------------------------------------------------------------------
    # ★ 可调参数：让界面上的滑杆直接改你插件的参数（不用改文件、不用重启）
    #
    # 你在插件里声明"哪些类属性可以调"，界面上就会出现对应的滑杆：
    #
    #     def 可调参数(self) -> dict:
    #         return {"KP": {"值": self.KP, "范围": (10.0, 20000.0)},
    #                 "KD": {"值": self.KD, "范围": (0.0, 500.0)}}
    #
    # 键名必须是**插件的类属性名**（例如 KP）。界面拖动后，外壳会自动改它，
    # 你的 每步控制() 下一次执行就直接用上新值 —— 不需要写任何接收代码。
    #
    # 不声明 `可调参数()` 的插件不会出现在参数面板里，没有任何影响。
    # ------------------------------------------------------------------
    def 可调参数(self) -> dict:
        """返回 {参数名: {"值": 当前值, "范围": (最小, 最大), "步长": 可选, "单位": 可选}}。"""
        return {}

    def 设置参数(self, 名: str, 值: float) -> str:
        """外壳调这个来改参数。返回 "" 表示成功，否则返回失败原因。"""
        if not hasattr(self, 名):
            return f"插件 {type(self).__name__} 没有参数「{名}」"
        try:
            setattr(self, 名, float(值))
            return ""
        except Exception as 异常:                                    # noqa: BLE001
            return f"设置 {名} 失败：{异常}"

    def 收到模型(self, event) -> None:
        """可选：模型加载后调一次。要记住模型/数据对象时在这里拿（比如做逆运动学）。"""
        return None

    def 模型兼容性(self, 模型) -> str:
        """可选：**切换模型前**的兼容性预检。返回 "" = 兼容；否则返回人话原因。

        ★ 为什么要有这个钩子（这是踩过坑才加的）：
          以前一个算法在该模型上跑不了，只能"跑起来 → 抛异常 → 被出错隔离停用"。
          代价有三个，都很糟：
            ① 停用是**不可恢复**的（同一个插件再错一次才停，但换回合适的模型也不会自动
               恢复），用户看到的现象是"切回 UR5e 也不动了"；
            ② 异常发生在每步控制() 里，终端刷一堆堆栈，真正的原因被淹没；
            ③ 界面上的算法列表照样显示它挂着 —— 看起来在跑，其实早停了。

          有了这个钩子，外壳在**装配时**就问一遍：不兼容的算法**根本不启用**，
          并把原因写进项目状态发给界面。于是"挂着的算法"和"真正在跑的算法"
          永远一致，也不会有异常。

        写实现时的约定（两条，都很重要）：
          · **别抛异常**：拿不准就返回 ""（放行）。预检是为了少踩坑，不是为了拦人。
          · **用属性判断，别读 data**：这里只知道 model（`模型.nq` / `模型.nu` /
            `模型.nbody` / `模型.body()` / `模型.jnt_type` …），data 还没建好。
        """
        return ""

    def 绑定模型路径(self, 路径: str) -> None:
        """可选：模型文件路径变化时调一次（要按路径查表、重建模型的插件用它）。

        ★ 以前这个钩子只存在于 `外壳/启动.py` 的 `hasattr` 探测里，基类没声明，
          所以"有哪些扩展点"要靠读外壳代码才知道。现在收进基类，成为正式契约。
        """
        return None

    def 模型已切换(self, 路径: str, 模型, 数据) -> None:
        """可选：换模型**之后**调一次 —— 清掉跟旧模型绑定的缓存与中间结果。

        与 `模型兼容性` 的分工：
            `模型兼容性` 在换**之前**问"能不能跑"（不兼容就不启用）；
            `模型已切换` 在换**之后**通知"换好了"（清缓存、重建索引、重置状态）。

        典型实现见 `算法库/通用/参数辨识插件.py`：它在这里把采样数据、
        标称值、辨识结果全部清空，并按新模型重查可辨识参数表 —— 不清的话，
        你会看到"xArm7 的辨识结果"里混着 UR5e 的数据。
        """
        return None


# ---------------------------------------------------------------------------
# ③ 安全注册表：插件出错隔离（官方没有，这是我们要补的第一个功能）
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# ★★ 契约例外（2026-09-22，第 7 步"显示模式"）★★
# 本文件属于被 `零改动自检.py` 哈希钉住的 3 个核心文件之一。为了让仿真侧插件能
# "再派发一条消息"（【Display】展示模式要在官方 StepControl 之前改写暂停快照），
# 在这里加了下面这一小段（`_当前注册表` + `取注册表()`，共 ~10 行），
# 并在 `安全注册表.__init__` 里登记一行。**这是目前唯一的例外**，
# 已用 `零改动自检.py --建立` 更新基准；日后若要去掉，请同步删除这两处。
# 之所以不放在 启动.py：那样改的是"外壳主循环"，风险比加一个只读访问器大得多。
# ---------------------------------------------------------------------------
# 当前生效的注册表（给"仿真侧插件"一个正规的取用入口）
#
# ★ 为什么需要它：插件有时要"再派发一条消息"（例如【Display】展示模式要在官方 StepControl
#   之前把暂停状态改写掉）。派发的唯一入口是 `安全注册表.处理消息`，而插件拿不到它 —— 
#   这个函数就是那个入口。放在本文件而不是 启动.py，是为了**不动被哈希钉住的外壳核心文件**。
# ---------------------------------------------------------------------------
_当前注册表 = None

# `StepEvent` 的类型在这里缓存一次：`处理消息()` 是 ~500 Hz 的热路径，
# 每次去 `messages.StepEvent` 查属性是白花的时间。
_StepEvent类型 = messages.StepEvent


def 取注册表():
    """返回当前生效的安全注册表；还没建好时返回 None。"""
    return _当前注册表


# ---------------------------------------------------------------------------
# ★★ 契约例外 ②（方案 C，项目清单驱动装配）★★
# 背景：以前"用哪些算法"写在 `主程序.py` 的【插件清单】里，启动后永不改变；
#       方案 C 改成由 `项目/xxx.json` 声明，**点模型 → 换一组算法**。
#       于是需要"运行期替换用户算法集合"这个能力 —— 而它就是 `安全注册表` 的本职
#       （它拥有 `_用户插件` 这本账），所以加在这里，而不是让外壳去 append 私有列表。
#
# 加的东西（只有两处）：
#       ① `设用户插件(插件列表)` —— 把这个方法加在 `安全注册表` 上（见类里）
#       ② 本注释块（不影响行为，只是把这次例外登记在案）
#
# 与例外 ① 的关系：例外 ① 是"给插件一个只读入口"，例外 ② 是"让外壳换一组插件"。
# 两条都是**受控的、有名字的**改动，不是把私有属性捅开随便改。
#
# 日后若要去掉：删掉 `设用户插件` 这个方法 + 本注释块，并把 启动.py 里的
# `注册表.设用户插件(...)` 调用一起删掉；然后跑
#       .venv/bin/python 软件/零改动自检.py --建立
# 刷新哈希基准，并在 CHANGELOG 记一行"为什么改、删了什么"。
# ---------------------------------------------------------------------------
class 安全注册表:

    """包住官方的 PluginRegistry，给每个插件加「出错隔离」。

    官方行为：任何一个插件抛异常 → 整个 dispatch 中断 → 软件直接挂。
    我们的行为：某个插件抛异常 → 中文报错 + 关掉这一个插件 → 其余照常跑。

    ★ 一个必须记住的前提（我们踩过这个坑）：
      **真正"把物理往前推"的是官方的 StepControl 插件**，不是 ViewerHandle.sync。
      sync 只负责"派发 StepEvent"；StepControl 收到 StepEvent 才去 mj_step。
      所以这里必须把 StepControl 一起注册进来，否则你的控制律会被调用 25 万次，
      但仿真时间一直停在 0（机械臂纹丝不动）。
    """

    def __init__(self, 插件列表: list):
        global _当前注册表
        # 官方步进插件排在最前面（它的优先级是 INTERNAL，本来就最先执行）
        self._目标 = [step_control.StepControl(), *插件列表]
        _当前注册表 = self          # 登记给 取注册表() 用（见文件上方说明）
        self._用户插件 = list(插件列表)
        self._出错数: dict[str, int] = {}
        self._已停用: set[str] = set()
        # ---- ★ 契约例外 ③：世界冻结闸门（见文件上方那段说明）----
        #   `_冻结判据` 是一组无参可调用：任一返回 True 就**不派发步进事件** →
        #   官方 StepControl 收不到 StepEvent → 不调 advance() → 物理完全不走。
        self._冻结判据: list = []

    def 加插件(self, 插件) -> None:
        """运行期再挂一个插件进来（外壳内部用，比如参数应用器）。

        注意：不放进 `_用户插件`（那本账是给用户控制算法用的），
        所以它不会出现在插件清单/状态快照里，但同样享受逐个派发与出错隔离。
        """
        self._目标.append(插件)

    def 加冻结判据(self, 判据) -> None:
        """★ 契约例外 ③：登记一个"世界是否冻结"的判据（无参、返回 bool）。

        任一判据返回 True → `处理消息()` **不派发** `StepEvent` → 官方 StepControl
        收不到步进事件 → 不调 `advance()` → **物理完全不走**。

        为什么需要这个闸门（这是实测踩出来的）：
          「加载重力」曾经靠"在派发快照时改写 `StepControlSnapshot.pause_state`"来实现冻结。
          那条路**依赖官方 ViewerApp 每帧发快照**，而实测在真实运行里
          **6 秒内收到 0 条快照** —— 于是冻结从未生效，模型一进模型就掉到偏离默认位置
          0.5~0.8 rad 的地方。单独写小程序测时因为手工构造快照，反而是"通过"的。
          所以改成不依赖任何外部消息：直接在外壳唯一的派发入口上问一句。
        """
        if 判据 not in self._冻结判据:
            self._冻结判据.append(判据)

    def 移走冻结判据(self, 判据) -> None:
        """注销判据（换模型/卸载内置件时用）。"""
        try:
            self._冻结判据.remove(判据)
        except ValueError:
            pass

    def 世界已冻结(self) -> bool:
        """现在是否应冻结物理（任一判据为真即冻结）。"""
        for 判据 in list(self._冻结判据):
            try:
                if 判据():
                    return True
            except Exception:                                        # noqa: BLE001
                continue                    # 判据自己坏了不能把物理卡死/放开，按"不冻结"处理
        return False

    def 设用户插件(self, 插件列表: list) -> None:
        """★ 换掉整组**用户算法**（方案 C：点模型 → 按项目清单重新装配）。

        与 `加插件` 的分工（这条界线很重要，别混用）：
            · `加插件`    —— 外壳自己的内部插件（模型应用器 / 参数应用器 / 辨识…）。
                             它们**跨项目常驻**，不属于任何项目，换了模型也该继续在。
                             所以它们**不在本方法的清理范围内**。
            · `设用户插件` —— 项目声明的控制算法。换项目时整组换掉。

        怎么保证内部插件不被误删：`_目标` 里排在官方 StepControl 之后、但**不在**
        `_用户插件` 里的那些，就是内部插件 —— 重建时把它们原样接回去。

        ★ 换掉老算法时会顺手把它的"出错计数/停用状态"清掉（同一个插件名重新装配
          应该是一次干净的开始；旧环境的错误不该延续到新项目上）。这一点和
          P0-2（停用可恢复）想做的事是一致的，只是触发点是"换项目"。
        """
        # 内部插件 = 除了 StepControl 与旧用户插件之外的所有（保持原有相对顺序）
        旧用户 = {id(p) for p in self._用户插件}
        内部 = [p for p in self._目标[1:] if id(p) not in 旧用户]

        self._用户插件 = list(插件列表)
        self._目标 = [self._目标[0] if self._目标 else step_control.StepControl(),
                      *插件列表, *内部]
        self._出错数.clear()
        self._已停用.clear()

    def 插件快照(self) -> str:
        """收集所有**用户插件**的状态，拼成一行（终端实时反馈用）。"""
        行 = [f"已停用: {', '.join(sorted(self._已停用))}"] if self._已停用 else []
        for 插件 in self._用户插件:
            名 = self._名字(插件)
            if 名 in self._已停用:
                continue
            try:
                细节 = 插件.插件状态()
            except Exception:                                 # noqa: BLE001
                continue
            行.append(名 + "(" + "、".join(f"{k}={v}" for k, v in 细节.items()) + ")")
        return " | ".join(行)

    @staticmethod
    def _名字(插件) -> str:
        # 允许实例自带名字，否则用类名
        return str(getattr(插件, "名称", None) or type(插件).__name__)

    def 处理消息(self, 消息) -> None:
        """带隔离地派发一条消息。

        为什么不用官方的「一锅端」派发：官方 dispatch 里没有 try/except，
        任何一个插件抛异常都会中断整条链（后面的插件和内置逻辑全部收不到消息）。
        所以这里改成**逐个插件单独调用**，谁崩了只影响谁。

        ★ 顺序很关键：官方 StepControl 排在列表最前，所以它先推进物理，
          你的控制律再基于"这一步之后"的状态算力矩 —— 写进去的 ctrl 下一步生效，
          这正是标准控制回路的时序（和第 1 步教程里 while 循环的写法等价）。
        """
        # ★ 世界冻结闸门（契约例外 ③）：冻结时不派发步进事件。
        #   为什么拦的是"派发"而不是"推进物理"：真正推进物理的是官方的 `StepControl` 插件，
        #   它也是靠收 StepEvent 才去 `advance()`。所以让这条事件到不了它手上，
        #   物理就一步都不走 —— 比"改暂停状态"稳得多（不依赖任何外部消息）。
        #   注意只拦 `StepEvent`：其它消息（快照/命令/参数）照常派发，
        #   否则界面会失去响应。
        if self._冻结判据 and isinstance(消息, _StepEvent类型) and self.世界已冻结():
            return
        for 插件 in self._目标:
            名 = self._名字(插件)
            if 名 in self._已停用:
                continue
            self._单独派发(插件, 消息)

    def _单独派发(self, 插件, 消息) -> None:
        """只把消息交给这一个插件；它崩了就隔离它。"""
        from mujoco.experimental.studio import plugin_registry
        for info, 方法 in plugin_registry._discover_handlers(插件):  # noqa: SLF001
            # 按 MRO 匹配：消息类型是标注类型的子类也算命中（官方同款规则）
            if not issubclass(type(消息), info.message_type):
                continue
            try:
                方法(消息)
            except Exception as 异常:                        # noqa: BLE001
                self._处理异常(异常, 消息, 插件)

    def _处理异常(self, 异常, 消息, 插件) -> None:
        名 = self._名字(插件)
        self._出错数[名] = self._出错数.get(名, 0) + 1
        if self._出错数[名] == 1:
            print(f"⚠ 插件【{名}】出错（已隔离，软件继续运行）：{type(异常).__name__}: {异常}")
            # 只打印"出错在插件的哪一行"，不打印官方库内部的长堆栈（那会淹没重点）
            tb = 异常.__traceback__
            位置 = []
            while tb is not None:
                帧 = tb.tb_frame
                文件 = 帧.f_code.co_filename
                路径 = 文件.replace("\\", "/")
                # 跳过官方库（mujoco/experimental/…）和本兼容层自己的帧，只留"你的插件文件"
                if 文件.endswith(".py") and "mujoco/experimental" not in 路径 \
                        and not 路径.endswith("/插件系统.py"):
                    位置.append(f"{os.path.basename(文件)} 第 {tb.tb_lineno} 行（{帧.f_code.co_name}）")
                tb = tb.tb_next
            if 位置:
                print("  出错位置：" + " → ".join(位置[-3:]))
            print(f"  → 先跳过它继续跑；再错一次就停用它。改好代码后重启即可。")
        else:
            print(f"✗ 插件【{名}】再次出错 → 已停用。其他插件和界面不受影响。")
            self._已停用.add(名)

    # -- 给外面看的状态 --
    @property
    def 出错插件(self) -> dict[str, int]:
        return dict(self._出错数)

    @property
    def 停用插件(self) -> set[str]:
        return set(self._已停用)


# ---------------------------------------------------------------------------
# ④ 版本自检 + API 指纹（官方没有，这是我们要补的第二个功能）
# ---------------------------------------------------------------------------
def 版本自检() -> dict:
    """打印并返回环境指纹。官方升级导致 API 变化时，这张表能第一时间看出来。"""
    import platform

    指纹 = {
        "mujoco": getattr(mujoco, "__version__", "未知"),
        "python": platform.python_version(),
        "可执行文件": sys.executable,
        "ViewerConfig 字段": tuple(f.name for f in __import__("dataclasses").fields(viewer_protocol.ViewerConfig)),
        "gfx 模式数": len(getattr(viewer_protocol, "GFX_MODES", ())),
        "消息类型数": len([n for n in dir(messages) if isinstance(getattr(messages, n), type)
                          and issubclass(getattr(messages, n), messages.Message)]),
    }

    print("─" * 78)
    print("【环境自检】")
    print(f"  mujoco 版本 : {指纹['mujoco']}   （实测跑通过的版本：{', '.join(已知可用版本)}）")
    print(f"  Python      : {指纹['python']}  @ {指纹['可执行文件']}")
    print(f"  官方 API    : ViewerConfig{指纹['ViewerConfig 字段']}、gfx {指纹['gfx 模式数']} 种、"
          f"消息 {指纹['消息类型数']} 类")

    if 指纹["mujoco"] not in 已知可用版本:
        print(f"  ⚠ 当前 mujoco {指纹['mujoco']} 不在「实测跑通」名单里 —— "
              f"如果出现奇怪的报错，多半是官方 API 变了。请对照本文件开头的导入清单检查。")
    else:
        print("  ✓ 版本与实测一致")
    print("─" * 78)
    return 指纹


# ---------------------------------------------------------------------------
# ⑤ 插件清单
# ---------------------------------------------------------------------------
def 打印插件清单(插件列表: list, 项目名: str = "") -> None:
    """打印"这一组装了哪些算法"。

    ★ 方案 C 之后加算法**不再改代码**：把 .py 放进 `算法库/`，在项目的 `算法`
      字段里写上它（写 `"*"` 就是用全部）。所以这里的提示语跟着改了 ——
      以前写的是"新建 plugins/xx.py，再在 主程序.py 顶部加一个名字"。
    """
    抬头 = f"（项目：{项目名}）" if 项目名 else ""
    print(f"【已加载 {len(插件列表)} 个算法】{抬头}"
          f"（加算法：把 .py 放进 算法库/，在项目文件的 算法 字段里写上它；"
          f"参见 --列项目）")
    for i, 插件 in enumerate(插件列表, 1):
        名 = str(getattr(插件, "名称", type(插件).__name__))
        版 = str(getattr(插件, "版本", "-"))
        作 = str(getattr(插件, "作者", "") or "")
        说 = str(getattr(插件, "说明", "") or "")
        print(f"  {i}. 【{名}】 v{版}" + (f"  —— {作}" if 作 else ""))
        if 说:
            print(f"     {说}")
        try:
            额外 = 插件.插件状态()
        except Exception:                                     # noqa: BLE001
            额外 = {}
        if 额外:
            print("     " + "、".join(f"{k}={v}" for k, v in 额外.items()))
    print()


def 通知模型加载(插件列表: list, model, data, 算法信息: list | None = None,
                项目名: str = "") -> None:
    """模型准备好 / 换了模型之后，告诉每个插件一声。

    插件要缓存 model/data 时用 `event.model` / `event.data`。

    ★ `算法信息` 是**方案 C 之后新增的参数**（可选，默认 None）：
      一段"这次装的是哪些算法、各自参数多少"的描述，由外壳用
      `收集算法信息()` 现算出来。事件对象上带 `算法信息` 属性，插件直接取用：

          def 收到模型(self, event):
              self.算法信息 = getattr(event, "算法信息", [])   # 写录制元信息用

      为什么由外壳算、而不是让插件去问注册表：注册表里混着内部插件
      （模型应用器/参数应用器/StepControl），"哪些是用户算法"这本账只有外壳清楚。
      数据录制插件原来就是因为没有这条信息，写出来的元信息里算法清单一直是空的。

    ★ `项目名` 同样挂在事件上（`event.项目名`）：元信息里记下"这次属于哪个项目"，
      配合项目文件里的模型/参数，一条录制数据才真正可追溯。
    """
    信息 = list(算法信息 or [])
    # 事件对象用 type(...) 现场造：官方没有"模型加载"事件类型（StepEvent 是每步的），
    # 这里只要一个能挂属性的轻量载体，不值得为它往 messages 里加一个新类型。
    事件 = type("模型事件", (), {"model": model, "data": data,
                                 "算法信息": 信息, "插件列表": 插件列表,
                                 "项目名": str(项目名 or "")})()
    for 插件 in 插件列表:
        回调 = getattr(插件, "收到模型", None)
        if 回调 is None:
            continue
        try:
            回调(事件)
        except Exception as 异常:                                  # noqa: BLE001
            print(f"⚠ 插件【{getattr(插件, '名称', 插件)}】处理模型时出错：{异常}")


def 收集算法信息(插件列表: list) -> list[dict]:
    """把"这一组装了哪些算法、各自参数现在是多少"整理成可 JSON 序列化的描述。

    这是**可复现性**的关键一环：录制元信息、项目快照都靠它回答
    "当时跑的是哪个控制律、参数多少"。以前这份信息没人收集，
    所以录制出来的 `.meta.json` 里 `插件清单` 永远是空数组。

    返回形如：
        [{"名称": "关节 PD 位置控制", "版本": "1.1", "英文名": "Joint PD position control",
          "参数": {"KP": 200.0, "KD": 30.0}}, …]

    只收"插件自己声明过的可调参数"（`可调参数()` 的键），不 dump 整个 `__dict__` ——
    那里有 model/data 引用、numpy 数组、文件句柄，序列化不了也没意义。
    """
    结果: list[dict] = []
    for 插件 in 插件列表:
        名称 = str(getattr(插件, "名称", None) or type(插件).__name__)
        条目 = {
            "名称": 名称,
            "版本": str(getattr(插件, "版本", "-")),
            "英文名": str(getattr(插件, "英文名", "") or ""),
            # ★ `接管控制` 必须一起带上：外壳要靠它判断"几个算法在抢同一个方向盘"
            #   （多个都写 ctrl[:] 时只有最后一个生效，被覆盖的等于没挂）。
            #   漏带这个键的后果实测过：会被当成"全都接管"，于是默认项目也误报冲突。
            "接管控制": bool(getattr(插件, "接管控制", True)),
            "参数": {},
        }
        问 = getattr(插件, "可调参数", None)
        if 问 is not None:
            try:
                for 参数名, 信息 in (问() or {}).items():
                    try:
                        条目["参数"][str(参数名)] = float(信息.get("值"))
                    except (TypeError, ValueError, AttributeError):
                        continue          # 不是数字的参数不进元信息（元信息要能 JSON 化）
            except Exception as 异常:                                  # noqa: BLE001
                print(f"⚠ 收集【{名称}】的参数时出错（元信息里该算法的参数为空）：{异常}")
        结果.append(条目)
    return 结果


# ---------------------------------------------------------------------------
# ⑥ 给控制算法用的小工具
# ---------------------------------------------------------------------------
def 滑块目标(ux_state, 默认):
    """读取官方"控制"面板里的滑杆值（就是 GUI 里能拖的那 6 个目标）。

    有了它，你的控制律不用改代码就能在界面里实时调目标 —— 这就是"参数面板"的雏形。
    官方没提供（或者面板被关掉）时，返回 默认 值。
    """
    try:
        if ux_state is not None and getattr(ux_state, "ctrl_target", None) is not None:
            return ux_state.ctrl_target
    except Exception:                                         # noqa: BLE001
        pass
    return 默认


def 打印插件状态(插件列表: list, 间隔秒: float = 5.0) -> None:
    """（可选）定期在终端打印插件的运行状态。想要就在主程序里用。"""
    import time
    上次 = time.time()
    while True:
        time.sleep(0.5)
        if time.time() - 上次 < 间隔秒:
            continue
        上次 = time.time()
        行 = []
        for 插件 in 插件列表:
            try:
                行.append(f"{getattr(插件, '名称', '?')}: " +
                          "、".join(f"{k}={v}" for k, v in 插件.插件状态().items()))
            except Exception:                                 # noqa: BLE001
                continue
        if 行:
            print("  [状态] " + " | ".join(行), flush=True)
