"""
官方接口清单.py —— 我们依赖官方的**全部**接口，一处声明，多处使用

它是什么：
    一份"边界合同"。外壳能用的官方东西只有下面清单里这些；
    清单之外如果谁偷偷用了官方内部 API，就是越界（`--自检` 会提醒）。

为什么要有它（第 3 步要解决的问题）：
    官方的插件系统在 `mujoco.experimental.studio` 里，官方自己标注"实验性、随时可能改"。
    官方的 C++ 扩展（窗口/渲染/界面/物理）**永远拷不走**，所以"搬代码"不能消除风险。
    能消除风险的办法只有一个：**把边界钉死，并且盯住它**——
    官方一改，启动自检立刻告诉你"哪一条断了、该改我们哪个文件"。

怎么用：
    ① 外壳代码需要官方东西时，从这里拿：`官方.取("viewer_app.ViewerApp")`
    ② 想检查边界是否完好：跑 `python 软件/主程序.py --自检`
    ③ 想加一个新的官方依赖：**先在清单里加一条**，再用它（这样它才会被看住）

约定：
    · `取值` 是一个 Python 表达式，在模块命名空间里求值（允许 `模块.属性` 链）
    · `检查` 是一个函数，返回 True/False + 说明文字（检查"形状对不对"，不只是"有没有"）
    · `修复` 是给人看的话：这条断了要去改我们哪个文件
"""
from __future__ import annotations

import dataclasses
import importlib
from typing import Any, Callable

# ---------------------------------------------------------------------------
# 模块名（集中在这里，官方哪天改了模块路径，只改这几行）
# ---------------------------------------------------------------------------
官方包前缀 = "mujoco.experimental.studio"
模块 = {
    "messages": 官方包前缀 + ".messages",
    "step_control": 官方包前缀 + ".step_control",
    "viewer_app": 官方包前缀 + ".viewer_app",
    "viewer_protocol": 官方包前缀 + ".viewer_protocol",
    "launch_native": 官方包前缀 + ".launch_native",
    "launch_thread": 官方包前缀 + ".launch_thread",
    "viewer_handle": 官方包前缀 + ".viewer_handle",
    "endpoints": 官方包前缀 + ".endpoints",
    "plugin_registry": 官方包前缀 + ".plugin_registry",
    "ux": 官方包前缀 + ".ux",
    "dear_imgui": "mujoco.experimental.dear_imgui.dear_imgui",
    "implot": "mujoco.experimental.implot.implot",
    "核心": "mujoco",
}


@dataclasses.dataclass(frozen=True)
class 接口项:
    """一条"我们依赖官方"的记录。"""
    编号: str            # 唯一 id，形如 "messages.handler"
    说明: str            # 人话说明它干什么
    所在模块: str        # 模块字典的 key
    取值: str            # 表达式，例如 "messages.handler"
    检查: Callable[[Any], tuple[bool, str]]   # 形状检查
    修复: str            # 断了改我们哪个文件
    被谁用: str          # 我们这边哪些文件依赖它


def _有属性(*名字):
    def 检查(对象):
        缺 = [n for n in 名字 if not hasattr(对象, n)]
        if 缺:
            return False, f"缺少属性/方法：{缺}"
        return True, "、".join(名字) + " 都在"
    return 检查


def _签名里有(*参数名, 位置=None):
    """检查函数签名里的参数名（比"有没有"更严，能发现官方改了参数名）。"""
    import inspect

    def 检查(对象):
        try:
            签名 = inspect.signature(对象)
        except (TypeError, ValueError):
            return True, "（C++ 内置，无法检查签名，只确认存在）"
        名字集 = set(签名.parameters)
        缺 = [n for n in 参数名 if n not in 名字集]
        if 缺:
            return False, f"签名 {签名} 里缺少参数 {缺}"
        return True, f"签名 {签名}"
    return 检查


def _可包装模块属性(*属性名):
    """检查"模块属性可写" —— 我们靠它把官方函数包一层（皮肤补推、主题同步都要）。

    ★ 这是本项目里**唯一**一处"改官方对象"的地方（皮肤桥包装 ux.setup_theme）。
      所以不能只检查"函数在不在"，还要实测"这个属性写得进去吗"：
      写法是**写回原值**（不改变任何行为），只是探一下可写性。
    """
    def 检查(对象):
        缺 = [n for n in 属性名 if not hasattr(对象, n)]
        if 缺:
            return False, f"缺少属性：{缺}"
        for n in 属性名:
            原值 = getattr(对象, n)
            if not callable(原值):
                return False, f"{n} 不可调用（无法包装）"
            try:
                setattr(对象, n, 原值)          # 写回原值：只探可写性，不改行为
            except Exception as 异常:                        # noqa: BLE001
                return False, f"{n} 属性不可写（包装会失败）：{type(异常).__name__}: {异常}"
        return True, "、".join(属性名) + " 存在、可调用、可包装（写回原值验证）"
    return 检查


def _是类(基类名=None, 模块键="messages"):
    def 检查(对象):
        if not isinstance(对象, type):
            return False, f"{对象!r} 不是类"
        if 基类名 is not None:
            基 = getattr(模块.get(模块键) and _模块缓存.get(模块键), 基类名, None)
            if 基 is None or not issubclass(对象, 基):
                return False, f"{对象.__name__} 不是 {基类名} 的子类"
            return True, f"{对象.__name__} 是 {基类名} 的子类"
        return True, f"{对象.__name__}"
    return 检查


def _返回元组长度(长度: int):
    def 检查(对象):
        try:
            import inspect
            返回 = inspect.signature(对象).return_annotation
        except (TypeError, ValueError):
            return True, "（内置，跳过返回类型检查）"
        return True, f"（返回标注 {返回}，运行期再验）"
    return 检查


# ---------------------------------------------------------------------------
# ★ 清单本体：我们依赖官方的每一样东西
# ---------------------------------------------------------------------------
清单: list[接口项] = [
    接口项(
        编号="mujoco.MjModel/MjData/MjSpec",
        说明="物理引擎本体：加载模型、造状态、改模型后重编译",
        所在模块="核心", 取值="mujoco",
        检查=_有属性("MjModel", "MjData", "MjSpec", "mj_step", "mj_forward"),
        修复="几乎不用改：这是最底层的接口，真断了说明 mujoco 大版本变了，需要重新验收",
        被谁用="启动.py / plugins/*",
    ),
    接口项(
        编号="messages.handler",
        说明="插件贴标签用的装饰器（@每步）",
        所在模块="messages", 取值="messages.handler",
        检查=_签名里有("priority", "fn"),
        修复="插件系统.py → 每步 = messages.handler；若参数名变了，改这一行",
        被谁用="插件系统.py（所有插件都通过它）",
    ),
    接口项(
        编号="messages.Priority",
        说明="执行优先级档位（INTERNAL/LIBRARY/USER/CRITICAL）",
        所在模块="messages", 取值="messages.Priority",
        检查=lambda o: (all(hasattr(o, n) for n in ("INTERNAL", "LIBRARY", "USER", "CRITICAL")),
                       "四档齐全" if all(hasattr(o, n) for n in ("INTERNAL", "LIBRARY", "USER", "CRITICAL")) else "档位缺失"),
        修复="插件系统.py → 优先级 = messages.Priority；若有档位改名，改用到的地方",
        被谁用="插件系统.py / plugins/末端两点运动.py",
    ),
    接口项(
        编号="messages.Message/Snapshot/Event",
        说明="消息三基类：可靠事件 vs 最新覆盖快照",
        所在模块="messages", 取值="messages",
        检查=_有属性("Message", "Snapshot", "Event"),
        修复="界面桥.py 的自定义消息继承自 messages.Snapshot",
        被谁用="界面桥.py / 参数面板.py / plugins/录制数据.py",
    ),
    接口项(
        编号="messages.StepEvent",
        说明="每步仿真事件：带 model 和 data（控制律的入口）",
        所在模块="messages", 取值="messages.StepEvent",
        检查=lambda o: ((o.__dataclass_fields__.keys() >= {"model", "data"}) if hasattr(o, "__dataclass_fields__") else (False, "不是 dataclass"),
                       "字段 model/data 齐全" if hasattr(o, "__dataclass_fields__") and o.__dataclass_fields__.keys() >= {"model", "data"} else "字段不符"),
        修复="插件系统.py 的文档与所有插件的 每步控制(self, event) 签名",
        被谁用="全部控制插件 / plugins/录制数据.py",
    ),
    接口项(
        编号="messages.ModelEvent",
        说明="把模型送到窗口的事件",
        所在模块="messages", 取值="messages.ModelEvent",
        检查=_是类(),
        修复="启动.py → 句柄.send_to_viewer(messages.ModelEvent(model=..., path=...))",
        被谁用="启动.py",
    ),
    接口项(
        编号="messages.StateSnapshot",
        说明="把每步状态回发给窗口的快照",
        所在模块="messages", 取值="messages.StateSnapshot",
        检查=_是类(),
        修复="启动.py 的回发状态那几行",
        被谁用="启动.py",
    ),
    接口项(
        编号="messages.BuildGuiEvent",
        说明="窗口每帧画界面时的事件（自定义面板的挂载点）",
        所在模块="messages", 取值="messages.BuildGuiEvent",
        检查=_是类(),
        修复="参数面板.py / 界面桥.py 的 BuildGuiEvent 处理函数",
        被谁用="参数面板.py",
    ),
    接口项(
        编号="messages.UpdateEvent",
        说明="窗口每帧更新事件（在画界面之前）",
        所在模块="messages", 取值="messages.UpdateEvent",
        检查=_是类(),
        修复="界面桥.py（每帧发滑杆值）",
        被谁用="界面桥.py / 参数面板.py",
    ),
    接口项(
        编号="viewer_protocol.ViewerConfig",
        说明="窗口配置：标题/宽高/渲染后端",
        所在模块="viewer_protocol", 取值="viewer_protocol.ViewerConfig",
        检查=lambda o: ((set(f.name for f in dataclasses.fields(o)) >= {"title", "width", "height", "gfx"})
                       if dataclasses.is_dataclass(o) else (False, "不是 dataclass"),
                       "字段 " + str([f.name for f in dataclasses.fields(o)]) if dataclasses.is_dataclass(o) else "不是 dataclass"),
        修复="主程序.py 里构造 配置 = viewer_protocol.ViewerConfig(...) 的地方",
        被谁用="主程序.py",
    ),
    接口项(
        编号="viewer_protocol.ViewerInitEvent",
        说明="窗口初始化事件：插件借此拿到 viewer 对象",
        所在模块="viewer_protocol", 取值="viewer_protocol.ViewerInitEvent",
        检查=_是类(),
        修复="界面桥.py / 参数面板.py 里 _记下viewer",
        被谁用="界面桥.py / 参数面板.py",
    ),
    接口项(
        编号="viewer_app.ViewerApp",
        说明="官方 GUI 主程序（19 个现成面板都靠它）",
        所在模块="viewer_app", 取值="viewer_app.ViewerApp",
        检查=_是类(),
        修复="启动.py 的窗口插件列表；主程序.py 传给 启动外壳 的窗口类参数",
        被谁用="启动.py / 主程序.py",
    ),
    接口项(
        编号="step_control.StepControl",
        说明="★ 官方步进插件：真正推进物理的就是它（不是 sync）",
        所在模块="step_control", 取值="step_control.StepControl",
        检查=_是类(),
        修复="插件系统.py 的安全注册表 → self._目标 = [step_control.StepControl(), *插件列表]",
        被谁用="插件系统.py",
    ),
    接口项(
        编号="launch_thread.make_thread_endpoints",
        说明="造一对线程安全的收发端点（仿真侧↔窗口侧）",
        所在模块="launch_thread", 取值="launch_thread.make_thread_endpoints",
        检查=lambda o: (callable(o), "可调用" if callable(o) else "不可调用"),
        修复="启动.py → 查看端点, 仿真端点 = launch_thread.make_thread_endpoints()",
        被谁用="启动.py",
    ),
    接口项(
        编号="launch_native.run_native_viewer",
        说明="在主线程里跑窗口循环（macOS 必须这样）",
        所在模块="launch_native", 取值="launch_native.run_native_viewer",
        检查=_签名里有("config", "endpoint", "plugins"),
        修复="启动.py 的最后一段（run_native_viewer 调用）",
        被谁用="启动.py",
    ),
    接口项(
        编号="viewer_handle.ViewerHandle",
        说明="仿真侧句柄：发送模型/状态、判断窗口是否还开着",
        所在模块="viewer_handle", 取值="viewer_handle.ViewerHandle",
        检查=_有属性("send_to_viewer", "is_running", "close"),
        修复="启动.py → 句柄 = viewer_handle.ViewerHandle(仿真端点)",
        被谁用="启动.py",
    ),
    接口项(
        编号="endpoints.SimEndpoint",
        说明="仿真侧端点：收窗口事件、发状态快照",
        所在模块="endpoints", 取值="endpoints.SimEndpoint",
        检查=_有属性("get_viewer_events", "get_viewer_snapshots", "send_to_viewer"),
        修复="启动.py 的仿真循环（注意：没构造它，是 make_thread_endpoints 返回的）",
        被谁用="启动.py",
    ),
    接口项(
        编号="plugin_registry._discover_handlers",
        说明="扫描插件里贴了 @每步 的方法（我们做逐个隔离时要用它）",
        所在模块="plugin_registry", 取值="plugin_registry._discover_handlers",
        检查=lambda o: (callable(o), "可调用" if callable(o) else "不可调用"),
        修复="插件系统.py → 安全注册表._单独派发()。★ 这是私有函数（带下划线），"
             "官方若改名/改返回值，隔离机制要跟着改——自检会第一时间报出来",
        被谁用="插件系统.py",
    ),
    接口项(
        编号="ux.GuiTheme / setup_theme / save_settings",
        说明="界面主题（深色/浅色）与设置保存",
        所在模块="ux", 取值="ux",
        检查=_有属性("GuiTheme", "setup_theme", "save_settings"),
        修复="界面桥.py 的 _应用主题 / 制作窗口类",
        被谁用="界面桥.py / 主程序.py",
    ),
    接口项(
        编号="ux.reset_config",
        说明="清掉保存的界面布局/主题",
        所在模块="ux", 取值="ux.reset_config",
        检查=lambda o: (callable(o), "可调用" if callable(o) else "不可调用"),
        修复="主程序.py 的 --恢复默认界面",
        被谁用="主程序.py",
    ),
    接口项(
        编号="dear_imgui 基础控件",
        说明="画自定义面板用的 ImGui 控件（我们的参数面板靠它）",
        所在模块="dear_imgui", 取值="dear_imgui",
        检查=_有属性("Button", "Checkbox", "Text", "Separator", "SameLine",
                   "SliderFloat", "SliderInt", "Begin", "End"),
        修复="参数面板.py / plugins/录制数据.py 的面板绘制部分",
        被谁用="参数面板.py / plugins/录制数据.py",
    ),
    # ---------------------------------------------------------------------
    # ↓↓↓ 下面 3 项是"面板外观换肤"新增的依赖（2026-09-17，清单 21 → 24 项）
    # ---------------------------------------------------------------------
    接口项(
        编号="dear_imgui 样式推入接口",
        说明="★ 换肤机制的全部家当：逐帧推入颜色/形状再弹出（绑定里没有"
             "全局 SetStyleColor，所以只能这样）",
        所在模块="dear_imgui", 取值="dear_imgui",
        检查=_有属性("PushStyleColor", "PopStyleColor", "PushStyleVar", "PopStyleVar",
                   "GetColorU32", "Col", "StyleVar", "Vec4", "Vec2", "GetIO", "ColorButton"),
        修复="皮肤桥.py 的 _推入一套()/帧结束()；若官方绑定改名，换肤会整体失效但不会崩",
        被谁用="皮肤桥.py / 面板/外观面板.py",
    ),
    接口项(
        编号="implot 样式推入接口",
        说明="曲线面板的换肤（曲线图框/网格/图例颜色；★ 线条颜色由 implot 内部 "
             "colormap 决定，本绑定改不了）",
        所在模块="implot", 取值="implot",
        检查=_有属性("PushStyleColor", "PopStyleColor", "PushStyleVar", "PopStyleVar", "Col"),
        修复="皮肤桥.py 的 _推入一套()（曲线那两行）",
        被谁用="皮肤桥.py",
    ),
    接口项(
        编号="ux.setup_theme 可包装",
        说明="★ 官方每帧都会重设主题（viewer_app.build_gui 第一行），会把我们的皮肤抹掉；"
             "只有把它包一层、设完补推，官方那 19 个面板才会一起换肤",
        所在模块="ux", 取值="ux",
        检查=_可包装模块属性("setup_theme"),
        修复="皮肤桥.py 的 安装包装()。★ 这一项失败不影响开窗：皮肤会自动退回"
             "「只换自研面板」模式（见 皮肤桥.包装是否失效）",
        被谁用="皮肤桥.py",
    ),
]


# ---------------------------------------------------------------------------
# 取用与检查
# ---------------------------------------------------------------------------
_模块缓存: dict[str, Any] = {}
_取值缓存: dict[str, Any] = {}


def 取(编号: str) -> Any:
    """按编号取一个官方对象（第一次用到才 import，不拖慢启动）。"""
    if 编号 in _取值缓存:
        return _取值缓存[编号]
    for 项 in 清单:
        if 项.编号 == 编号:
            break
    else:
        raise KeyError(f"官方接口清单里没有「{编号}」—— 想用新的官方接口，先把它加进 清单 里")
    模块对象 = 模块.get(项.所在模块)
    if 模块对象 is None:
        raise KeyError(f"清单里「{编号}」的模块键 {项.所在模块!r} 在 模块 字典里不存在")
    if 项.所在模块 not in _模块缓存:
        _模块缓存[项.所在模块] = importlib.import_module(模块对象)
    _模块缓存.setdefault(模块对象, _模块缓存[项.所在模块])   # 同时登记"模块真名"，供 取值 表达式使用
    try:
        值 = eval(项.取值, {}, {**_模块缓存, 项.所在模块.split(".")[-1]: _模块缓存[项.所在模块]})  # noqa: S307
    except Exception as 异常:                                   # noqa: BLE001
        raise RuntimeError(f"取官方接口「{编号}」失败（{项.取值}）：{异常}") from 异常
    _取值缓存[编号] = 值
    return 值


def 检查一条(项: 接口项) -> tuple[bool, str]:
    """检查一条接口。返回 (是否正常, 说明)。"""
    try:
        模块对象 = 模块.get(项.所在模块)
        if 项.所在模块 not in _模块缓存:
            _模块缓存[项.所在模块] = importlib.import_module(模块对象)
        _模块缓存.setdefault(模块对象, _模块缓存[项.所在模块])   # 同时登记"模块真名"（如 mujoco）
        # 让 取值 表达式能同时用"模块真名"和"短名"
        环境 = {**_模块缓存, 项.所在模块.split(".")[-1]: _模块缓存[项.所在模块]}
        for 键, 模块名 in 模块.items():
            if 键 in _模块缓存:
                环境[键] = _模块缓存[键]
        值 = eval(项.取值, {}, 环境)  # noqa: S307
    except Exception as 异常:                                   # noqa: BLE001
        return False, f"取不到（{type(异常).__name__}: {异常}）"
    try:
        结果 = 项.检查(值)
        if isinstance(结果, tuple):
            return bool(结果[0]), str(结果[1])
        return bool(结果), ""
    except Exception as 异常:                                   # noqa: BLE001
        return False, f"检查函数本身出错：{type(异常).__name__}: {异常}"


def 全量检查(打印=print, *, 只列失败: bool = False) -> tuple[int, int]:
    """逐条检查整份清单。返回 (正常数, 失败数)。

    参数
      只列失败: True 时只打印失败项（启动路径用，避免刷屏）；
                False 时全列（人工排查用，`--自检` 走这个）。
    """
    正常 = 失败 = 0
    for 项 in 清单:
        好, 说明 = 检查一条(项)
        if 好:
            正常 += 1
            if not 只列失败:
                打印(f"  ✓ {项.编号:44s} {说明}")
        else:
            失败 += 1
            打印(f"  ✗ {项.编号:44s} {说明}")
            打印(f"      → 该改我们这边：{项.修复}")
            打印(f"      → 受影响：{项.被谁用}")
    return 正常, 失败
