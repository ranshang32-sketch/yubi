"""
模型桥.py —— 「模型库 / 换模型」的界面↔仿真通道（方案 A 的核心）

它解决什么问题：
    需求是"启动先给空白界面，然后在界面里选/切换机械臂"。
    官方底座其实已经把"换模型"做成了一等公民能力（发一条 `ModelEvent` 就会
    重建 model/data、重置节拍、重置界面状态），但**我们自己的外壳绕过了官方的
    `ViewerHandle.sync()`**（为了做出错隔离），所以那条路只走了一半：
    窗口侧的画面换了，仿真侧的物理还在旧模型上跑。

    这个模块把"换模型"收敛到**一个地方**，两条入口都经过它：
      ① 界面【模型库】面板发来的 `换模型命令`
      ② 窗口侧发来的 `messages.ModelEvent`（官方内建的"把文件拖进窗口"）
    真正的加载与"重绑 model/data + 通知插件"由外壳注入的回调完成（见 启动.py）。

另外它负责"记住上次用的模型"（启动默认②）：
    `输出/设置.json` 里存 `上次模型`，启动时优先用它，没有才回落到空场景。
    由谁记住：`主程序.py`（启动时）和 `启动.py`（每次切换成功后）。

用法（界面侧）：
    from 模型桥 import 换模型命令, 模型状态, 读取模型库, 选择本地模型文件
    self.viewer.send_to_sim(换模型命令(路径=…, 显示名=…))
"""
from __future__ import annotations

import dataclasses
import json
import os
import subprocess
from typing import Any, Callable

from mujoco.experimental.studio import messages

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
_软件目录 = os.path.dirname(os.path.abspath(__file__))
包根 = os.path.dirname(_软件目录)
模型目录 = os.path.join(包根, "模型")
库索引路径 = os.path.join(模型目录, "模型库.json")
设置路径 = os.path.join(包根, "输出", "设置.json")
空场景路径 = os.path.join(模型目录, "空场景.xml")


# ---------------------------------------------------------------------------
# 模型库（界面侧与仿真侧都能直接读，不需要走消息）
# ---------------------------------------------------------------------------
def 读取模型库(只取机械臂: bool = True) -> list[dict]:
    """读 `模型/模型库.json`，返回可选的模型条目。

    只取机械臂时过滤掉夹爪 / 不可控制的模型 —— 界面上列出来点一下就报错的条目没有意义。
    """
    try:
        with open(库索引路径, encoding="utf-8") as f:
            索引 = json.load(f)
    except FileNotFoundError:
        return []
    except Exception as 异常:                                       # noqa: BLE001
        print(f"⚠ 模型库索引读取失败：{type(异常).__name__}: {异常}")
        return []
    条目 = 索引.get("模型", [])
    if 只取机械臂:
        条目 = [m for m in 条目 if m.get("类别") == "arm" and m.get("可控制")]
    return 条目


def 绝对路径(相对包根的路径: str) -> str:
    """把模型路径规范成绝对路径。

    三种输入都要能吃下：
      · 已经是绝对路径            → 原样返回
      · 相对包根（模型库索引里的写法，如 `universal_robots_ur5e/ur5e_torque.xml`）
      · 相对当前工作目录（用户手输的 `模型/xxx.xml`）
    判断办法：先看这个路径本身存不存在，存在就认它。
    """
    路径 = str(相对包根的路径 or "")
    if not 路径:
        return ""
    for 候选 in (路径, os.path.join(包根, 路径)):
        if os.path.exists(候选):
            return os.path.abspath(候选)
    return os.path.normpath(os.path.join(模型目录, 路径))


def 显示名(路径: str) -> str:
    """给一个模型路径起个人看的名字（能在模型库里查到就用库里的显示名）。"""
    绝对 = 绝对路径(路径)
    if 绝对 and os.path.normpath(绝对) == os.path.normpath(空场景路径):
        return "空场景（无机械臂）"
    for m in 读取模型库(只取机械臂=False):
        if os.path.normpath(绝对路径(m.get("扭矩模型", ""))) == os.path.normpath(绝对):
            return str(m.get("显示名") or m.get("标识") or os.path.basename(路径))
    return os.path.basename(路径)


# ---------------------------------------------------------------------------
# 记住上次用的模型（启动默认②）
# ---------------------------------------------------------------------------
def _读设置() -> dict:
    try:
        with open(设置路径, encoding="utf-8") as f:
            数据 = json.load(f)
        return 数据 if isinstance(数据, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as 异常:                                        # noqa: BLE001
        print(f"⚠ 设置读取失败（按默认处理）：{type(异常).__name__}: {异常}")
        return {}


def _写设置(数据: dict) -> None:
    try:
        os.makedirs(os.path.dirname(设置路径), exist_ok=True)
        with open(设置路径, "w", encoding="utf-8") as f:
            json.dump(数据, f, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception as 异常:                                        # noqa: BLE001
        print(f"⚠ 设置保存失败（不影响使用）：{type(异常).__name__}: {异常}")


def 读取设置(键: str, 默认=None):
    """读一个设置项（`输出/设置.json`）。"""
    return _读设置().get(键, 默认)


def 写入设置(键: str, 值) -> None:
    """写一个设置项。"""
    数据 = _读设置()
    if 数据.get(键) == 值:
        return
    数据[键] = 值
    _写设置(数据)


def 读取上次模型() -> str:
    """返回上次成功加载的模型路径；没有 / 文件已不在 → 返回空串。"""
    路径 = str(_读设置().get("上次模型") or "")
    if 路径 and os.path.exists(路径):
        return 路径
    return ""


def 记住模型(路径: str) -> None:
    """记住这次用的模型。空场景也记（等价于"上次我就是要空着"）。"""
    数据 = _读设置()
    if 数据.get("上次模型") == 路径:
        return
    数据["上次模型"] = 路径
    _写设置(数据)
    print(f"【模型】已记住：{显示名(路径)}（下次启动自动加载；想清掉删 输出/设置.json）", flush=True)


# ---------------------------------------------------------------------------
# 界面 → 仿真侧：换模型命令
# ---------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class 换模型命令(messages.Snapshot):
    """面板发来的"换到这个模型"。

    ★ Snapshot 语义（只保留最新一条）正合适：用户连点几个模型时，
      旧的那些还没处理就已经过期了，最新的才是要的。
    """

    路径: str = ""
    显示名: str = ""


# ---------------------------------------------------------------------------
# 仿真侧 → 界面：当前模型状态
# ---------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class 模型状态(messages.Snapshot):
    当前路径: str = ""
    当前显示名: str = ""
    自由度: int = 0
    执行器数: int = 0
    状态: str = "就绪"          # 就绪 / ✓ … / ✗ …
    耗时: float = 0.0


# ---------------------------------------------------------------------------
# 仿真侧：唯一负责"把模型换掉"的插件
# ---------------------------------------------------------------------------
class 模型应用器:
    """仿真侧插件。它自己**不加载模型** —— 加载与重绑由外壳注入的 `换模型回调` 做。

    这样安排的原因：重绑 model/data 必须动 `ViewerHandle` 和外壳的局部变量，
    那些东西只有 `启动.py` 拿得到。这个插件只负责"把消息翻译成一次回调调用"。
    """

    名称 = "模型应用器"
    版本 = "1.0"

    def __init__(self, 换模型回调: Callable[..., tuple[bool, str]]):
        self._换模型 = 换模型回调
        self.状态 = "就绪"
        self.当前路径 = ""
        self.当前显示名 = ""
        self.自由度 = 0
        self.执行器数 = 0
        self.耗时 = 0.0

    # ---- 入口 ①：我们自己的面板 ----
    @messages.handler
    def 收命令(self, 命令: 换模型命令) -> bool:
        路径 = str(getattr(命令, "路径", "") or "")
        if not 路径 or os.path.normpath(路径) == os.path.normpath(self.当前路径):
            return False
        成功, 说明 = self._换模型(路径=路径, 通知窗口=True)
        self._记(路径, 成功, 说明)
        return False

    # ---- 入口 ②：官方内建的"把文件拖进窗口" ----
    #   窗口侧已经把文件解析成 MjModel 了（event.model），直接采用它的对象，
    #   不重复解析；也不需要再回发 ModelEvent（窗口自己已经有了）。
    @messages.handler
    def 收拖拽模型(self, event: messages.ModelEvent) -> bool:
        模型 = getattr(event, "model", None)
        路径 = str(getattr(event, "path", "") or "")
        if 模型 is None:
            return False
        成功, 说明 = self._换模型(模型=模型, 路径=路径, 通知窗口=False)
        self._记(路径, 成功, f"（拖拽）{说明}")
        return False

    def _记(self, 路径: str, 成功: bool, 说明: str) -> None:
        self.状态 = ("✓ " if 成功 else "✗ ") + 说明
        if 成功:
            self.当前路径 = 路径
            self.当前显示名 = 显示名(路径) if 路径 else "（未知来源）"
        print(f"【模型】{self.状态}", flush=True)

    # ---- 给发布器用 ----
    def 状态消息(self) -> 模型状态:
        return 模型状态(当前路径=self.当前路径, 当前显示名=self.当前显示名,
                        自由度=self.自由度, 执行器数=self.执行器数,
                        状态=self.状态, 耗时=self.耗时)


class 发布器:
    """周期性把当前模型状态发给界面（默认 2 Hz —— 只在切换时才会变，不用更密）。"""

    def __init__(self, 发送函数: Callable[[Any], None], 频率: float = 2.0):
        self._发送 = 发送函数
        self._间隔 = 1.0 / max(频率, 1e-6)
        self._下次 = 0.0
        self.已发布 = 0

    def 也许发布(self, 应用器, 墙钟: float) -> bool:
        if 墙钟 < self._下次:
            return False
        self._下次 = 墙钟 + self._间隔
        if 应用器 is None:
            return False
        try:
            self._发送(应用器.状态消息())
            self.已发布 += 1
            return True
        except Exception as 异常:                                     # noqa: BLE001
            if self.已发布 == 0:
                print(f"⚠ 模型状态发布失败（不影响控制）：{type(异常).__name__}: {异常}")
            return False


# ---------------------------------------------------------------------------
# 仿真侧 → 界面：当前**项目**状态（方案 C：点模型 → 界面更新算法列表）
# ---------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class 项目状态(messages.Snapshot):
    """当前项目 + 这一组装了哪些算法。

    ★ 为什么和 `模型状态` 分成两条消息（而不是合并成一条）：
      `模型状态` 变的是**物理对象**（哪台机械臂、多少轴、切换耗时）；
      `项目状态` 变的是**工作环境**（哪个项目、挂了哪些算法、参数多少）。
      两者的更新时机不同（换算法不一定换模型），关心它们的界面也不同
      （【Model library】关心前者，【Controller params】关心后者）。
      合成一条会让"只想知道算法列表"的面板每 2 Hz 收一堆无关字段。

    `算法` 是 `插件系统.收集算法信息()` 的产物：
        [{"名称": …, "版本": …, "英文名": …, "参数": {...}}, …]
    """

    项目: str = ""
    模型路径: str = ""
    模型显示名: str = ""
    算法: list = dataclasses.field(default_factory=list)
    报告: list = dataclasses.field(default_factory=list)   # 装配结果（✓/✗ 各一行）
    算法库: list = dataclasses.field(default_factory=list)  # 算法库里**全部**可选算法（给界面做选择器）
    已存盘: bool = False        # 这一组是否与项目文件一致（False = 是界面上临时 Apply 的）
    # ---- 抢方向盘提示（多个算法都写 ctrl[:] 时，只有最后一个真正生效）----
    #   `控盘`   = 真正在驱动机器人的那个算法的**显示名**（没有则为空串）
    #   `被覆盖` = 输出被整体盖掉、基本等于没挂的那些算法（显示名列表）
    #   ★ 为什么要在状态里带上：用户看不到终端，而"挂了的算法其实没生效"必须让他看见，
    #     否则只会觉得"这个算法的效果怎么是这样"。检测逻辑见 装配器._抢方向盘体检()。
    控盘: str = ""
    被覆盖: list = dataclasses.field(default_factory=list)
    # `重力开` = 物理现在跑不跑。★ 必须发给界面：用户看到"算法挂上了但模型不动"，
    #   最可能的原因就是它处于冻结（装载算法 ≠ 物理开始跑，两个开关是独立的）。
    #   界面拿它来提示"还要勾『加载重力』"，否则用户只会以为算法没生效。
    重力开: bool = False


# ---------------------------------------------------------------------------
# 界面 → 仿真侧：换一组算法（【Algorithms】面板的 Apply / Save）
# ---------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class 应用算法命令(messages.Snapshot):
    """把用户在界面上勾出来的一组算法交给仿真侧去装配。

    ★ 为什么必须走消息、不能在界面里直接改：
      装配要换掉**正在被仿真的那批插件实例**（`注册表.设用户插件()` + 参数应用器重绑 +
      通知各插件）。这些对象归仿真线程所有，界面线程去碰就是跨线程改状态。
      所以界面只负责"说想要哪几个"，装配由仿真线程做。

    `算法` = 插件名（模块名）的**有序**列表；顺序就是每步的执行顺序，
    **最后一项最后写 `ctrl[:]`，它说了算**（见 项目.py 的说明）。
    `落盘=True` 表示同时把这组选择写回项目文件（对应【Save】按钮）。
    Snapshot 语义（只保留最新一条）正合适：连点 Apply 时旧的那些本来也已过期。
    """

    算法: list = dataclasses.field(default_factory=list)
    落盘: bool = False
    重置姿态: bool = True
    #   ★ 为什么要有这个开关（这是实测出来的真实困扰）：
    #     换算法时**物理状态（qpos/qvel）默认是不动的**，而多数控制算法的设计是
    #     "拿第一次看到的位置当基准"（例如 关节pd控制 的 `目标`、正弦摆动 的 `基准`）。
    #     于是新算法会在**上一个算法留下的姿态**上开始控制 —— 表现就是
    #     "机器人回不到默认位置了"。
    #     实测数据：默认姿态误差 0 → 正弦摆动跑 400 步后偏离 0.33 rad →
    #     切到关节 PD 时它把这个姿态当了基准（目标 = 离开姿态 + 抬臂偏移）。
    #     所以默认 True：每次 Apply/Save 都把机器人摆回默认姿态再让新算法接手。
    #     想看"接着上一个算法的姿态继续"就把这个勾去掉（研究切换过程时会要）。


class 算法选择器:
    """仿真侧插件：收 `应用算法命令` → 调外壳注入的回调重新装配。

    它自己**不装配** —— 真正的装配在外壳的 `_装配项目()` 里（那里才拿得到
    句柄、注册表、参数应用器）。本插件只把消息翻译成一次回调调用，
    和 `模型应用器` 完全同一个套路。
    """

    名称 = "算法选择器"          # 有名字 → 会出现在算法清单/状态里，便于排查
    版本 = "1.0"

    def __init__(self, 换算法回调: Callable[..., tuple[bool, str]]):
        self._换 = 换算法回调
        self.已应用 = 0
        self.最近 = ""

    @messages.handler
    def 收命令(self, 命令: 应用算法命令) -> bool:
        算法 = [str(x) for x in (getattr(命令, "算法", None) or [])]
        落盘 = bool(getattr(命令, "落盘", False))
        重置 = bool(getattr(命令, "重置姿态", True))
        成功, 说明 = self._换(算法, 落盘, 重置)
        self.最近 = ("✓ " if 成功 else "✗ ") + 说明
        if 成功:
            self.已应用 += 1
        print(f"【算法】{self.最近}", flush=True)
        return False


class 项目状态发布器:
    """把当前项目状态发给界面。

    ★ 只在信息**真的变了**的时候才发（内容比对）。
      理由有两个：
        ① `Snapshot` 语义是"只保留最新一条"，每 2 Hz 重发一模一样的内容纯浪费；
        ② 更关键的是"点模型 → 界面**立刻**更新算法列表"这条体验要求
           —— 必须在装配完成的那一刻主动发，而不是等下一个 2 秒的节拍。
      所以主路径是装配完调一次 `发布()`；`也许发布()` 只作兜底
      （界面万一漏收了，最迟 0.5 秒后还能对上）。
    """

    def __init__(self, 发送函数: Callable[[Any], None], 频率: float = 2.0):
        self._发送 = 发送函数
        self._间隔 = 1.0 / max(频率, 1e-6)
        self._下次 = 0.0
        self._上次内容: tuple | None = None
        self.已发布 = 0

    @staticmethod
    def _指纹(状态: 项目状态) -> tuple:
        """把状态压成一个可比较的元组（用来判断"变没变"）。

        参数值也进指纹：拖滑杆改了参数，界面上的算法列表那一行也该跟着变。
        """
        return (
            str(状态.项目),
            str(状态.模型路径),
            str(状态.模型显示名),
            bool(状态.已存盘),
            str(状态.控盘),
            tuple(str(x) for x in (状态.被覆盖 or [])),
            bool(状态.重力开),
            # 可选算法库：**必须进指纹** —— 否则往算法库里加/删一个 .py 之后，
            # 【Algorithms】面板上的候选列表不会刷新（内容没变就不发，见类文档）。
            tuple(sorted(str(x) for x in (状态.算法库 or []))),
            tuple((str(a.get("名称")), str(a.get("版本")),
                   tuple(sorted((str(k), float(v)) for k, v in (a.get("参数") or {}).items())))
                  for a in (状态.算法 or []) if isinstance(a, dict)),
        )

    def 发布(self, 状态: 项目状态, 强制: bool = False) -> bool:
        """发一条项目状态。内容没变就跳过（除非 `强制=True`）。"""
        指纹 = self._指纹(状态)
        if not 强制 and 指纹 == self._上次内容:
            return False
        try:
            self._发送(状态)
        except Exception as 异常:                                         # noqa: BLE001
            if self.已发布 == 0:
                print(f"⚠ 项目状态发布失败（不影响控制）：{type(异常).__name__}: {异常}")
            return False
        self._上次内容 = 指纹
        self.已发布 += 1
        return True

    def 也许发布(self, 状态: 项目状态, 墙钟: float) -> bool:
        """按节拍兜底重发（内容没变就什么都不做，见类文档）。"""
        if 墙钟 < self._下次:
            return False
        self._下次 = 墙钟 + self._间隔
        return self.发布(状态)


# ---------------------------------------------------------------------------
# 界面侧：调 macOS 原生文件选择器
# ---------------------------------------------------------------------------
def 选择本地模型文件(起始目录: str = "") -> str:
    """弹 macOS 原生"打开文件"对话框，返回选中的路径（取消返回空串）。

    ★ 为什么不用官方接口：mujoco 的 Python 层**没有**暴露任何文件选择器
      （File 菜单只有 Quit，也没有 tinyfd 绑定）。而本项目已有用 osascript
      弹中文对话框的先例（见启动器脚本），所以这里沿用同一条路 —— 零新依赖。

    ★ 注意：这个函数是**阻塞**的（对话框关掉才返回）。在窗口线程里直接调用
      会把整个界面冻住（3D 视图不刷新，看起来像卡死），所以界面请用下面的
      `后台选择器` 包一层。
    """
    目录 = 起始目录 or 模型目录
    脚本 = (
        'try\n'
        f'  set f to choose file with prompt "选择 MuJoCo 模型（.xml / .mjb / .mjz）" '
        f'default location POSIX file "{目录}" of type {{"xml", "mjb", "mjz"}}\n'
        '  return POSIX path of f\n'
        'on error number -128\n'
        '  return ""\n'
        'end try\n'
    )
    try:
        结果 = subprocess.run(["osascript", "-e", 脚本],
                              capture_output=True, text=True, timeout=600)
    except Exception as 异常:                                        # noqa: BLE001
        print(f"⚠ 打开文件对话框失败：{type(异常).__name__}: {异常}")
        return ""
    if 结果.returncode != 0:
        错误 = (结果.stderr or "").strip()
        if 错误:
            print(f"⚠ 文件选择器返回错误：{错误[:200]}")
        return ""
    return (结果.stdout or "").strip()


class 后台选择器:
    """把阻塞的文件对话框丢到后台线程，界面就不会被冻住。

    用法：
        选择器.开始(起始目录)      # 点按钮时
        if 选择器.进行中: …        # 界面上显示"选择中…"
        路径 = 选择器.取()         # 每帧调一次；没选完返回 None，选完返回路径（只返回一次）
    """

    def __init__(self):
        import threading
        self._线程类 = threading
        self._线程 = None
        self._结果: str | None = None
        self.进行中 = False

    def 开始(self, 起始目录: str = "") -> None:
        if self.进行中:
            return
        self.进行中 = True
        self._结果 = None
        self._线程 = self._线程类.Thread(target=self._跑, args=(起始目录,), daemon=True)
        self._线程.start()

    def _跑(self, 起始目录: str) -> None:
        try:
            self._结果 = 选择本地模型文件(起始目录)
        except Exception as 异常:                                     # noqa: BLE001
            print(f"⚠ 文件选择器线程出错：{type(异常).__name__}: {异常}")
            self._结果 = ""
        finally:
            self.进行中 = False

    def 取(self) -> str | None:
        """每帧调一次。有结果就返回并清空（只返回一次）；否则 None。"""
        if self.进行中 or self._结果 is None:
            return None
        结果 = self._结果
        self._结果 = None
        return 结果
