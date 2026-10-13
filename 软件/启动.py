"""
启动.py —— macOS 上唯一能开窗的线程排法（第 2 步预研实测结论）

背景（这个坑很硬，必须先讲清楚）：
  官方给的写法是 `launch_passive(...)`，它内部用 launch_native → launch_thread，
  **把创建窗口的活儿丢给一个 daemon 线程**。而 macOS 规定：NSWindow 只能在主线程创建。
  实测结果：无论用 python 还是 mjpython，都立刻报
      ERROR: Error creating window: NSWindow should only be instantiated on the main thread!
  也就是说官方这套 launch_passive 在 macOS 上目前是坏的（mujoco 3.13.0 实测）。

我们的排法（把两个线程的任务对调）：
  ┌─ 主线程   ：跑 viewer（建窗口 + 渲染 + 界面）   ← macOS 要求窗口在这儿
  └─ 后台线程 ：跑仿真（算控制律 + 推进物理 + 发状态）
  两者之间用官方现成的 endpoints 消息通道通信（线程安全队列，官方自己就是这么设计的）。

这个文件就是上面那套排法的落地。**你不需要改它**，除非官方修好了 launch_passive。

★ 方案 C 之后本文件多了一项职责：**换模型时按项目重新装配控制算法**
  （见 `启动外壳` 里的 `_装配项目()`）。所以它同时是"线程排法"和"项目装配的执行点"。
  装配的规则本身在 `项目.py`（读声明）和 `装配器.py`（把声明变成实例），
  本文件只负责"什么时候装、装完通知谁"。
"""
from __future__ import annotations

import os
import sys
import threading
import traceback

# 让本模块无论在哪个目录被导入，都能 import 到同目录的 项目 / 装配器 / 模型桥
_软件目录 = os.path.dirname(os.path.abspath(__file__))
if _软件目录 not in sys.path:
    sys.path.insert(0, _软件目录)

import 插件系统 as 插件框架                                              # noqa: E402
import 项目 as _项目                                                      # noqa: E402

# `模型桥` 同时被界面侧和仿真侧用，这里在模块级导入一次：
# `_装配项目()` 与主循环都要发 `项目状态`（方案 C：算法列表随项目变化）。
# 它只依赖官方 messages 与标准库，不建窗口，所以导入是安全的。
import 模型桥 as _模型桥                                                  # noqa: E402
import 重力桥 as _重力桥                                                  # noqa: E402
from 模型桥 import 项目状态                                               # noqa: E402


def 应用主题(窗口插件: list) -> None:
    """界面主题不在这里应用 —— 见下方说明。

    ★ 踩过的坑：官方 `ux.setup_theme()` 必须在**窗口和 ImGui 上下文都建好之后**才能调用。
      在窗口创建之前调用会直接 **段错误（segfault）**，整个进程崩掉、连窗口都开不出来。
      所以主题的实际应用放在 `界面桥.py` 的「首帧」处理器里（那时上下文已经就绪）。

    主题值也可以手动改：~/.mujoco.ini 里的 `[Studio][UX] theme=0/1/2`
    （0=浅色 1=深色 2=经典），或者在窗口里打开 Options → Theme 菜单改。
    """
    return None


def 启动外壳(配置, 模型路径: str, 窗口类, 插件列表: list, 注册表, 通知模型加载,
            项目名: str = ""):
    """启动官方 Studio 窗口 + 我们的插件。

    参数
      配置        : 官方 ViewerConfig（标题、宽高、gfx 模式）
      模型路径    : 要加载的 MJCF/XML
      窗口类      : 官方 viewer_app.ViewerApp（19 个现成面板都靠它）
      插件列表    : 启动时按项目装配出来的控制算法实例（方案 C：见 项目.py / 装配器.py）
      注册表      : 插件系统.安全注册表（带出错隔离）
      通知模型加载: 插件系统.通知模型加载（让插件拿到 model/data）
      项目名      : 启动时选中的项目名（换模型后会被换成新项目的名字）

    ★ 方案 C 之后这个函数多做一件事：**换模型时按项目重新装配算法**。
      以前"用哪些算法"是启动时定死的；现在点 UR5e 会装 `项目/UR5e_基础PD.json`
      里声明的那一组，点 xArm7 换成另一组。装配逻辑集中在 `_装配项目()` 里，
      三条入口（启动 / 界面点模型 / 把 xml 拖进窗口）都走它。

    返回：0 正常 / 1 出错
    """
    import mujoco
    from mujoco.experimental.studio import (launch_native, launch_thread,
                                            messages, viewer_handle)

    # ---- 1. 线程安全的双向消息通道（官方现成实现）----
    查看端点, 仿真端点 = launch_thread.make_thread_endpoints()

    # ---- 2. 仿真侧句柄：它负责"每转一圈派发 StepEvent"这件事 ----
    #         注意：这里不把插件交给官方句柄，而是交给我们自己的安全注册表，
    #         所以下面循环里调的是 注册表.处理消息(...) 而不是 句柄.sync(...)。
    句柄 = viewer_handle.ViewerHandle(仿真端点)

    停止 = threading.Event()
    出错 = {}

    # ---- 3. 仿真线程 ----
    def 仿真循环():
        try:
            import time as _time
            import numpy as _np

            # 当前项目名（换模型时变）+ 当前算法实例表。
            # ★ 用 nonlocal 让下面的 `_装配项目()` 能改写它们：
            #   仿真循环里的 插件列表 必须**始终是当前这一组**，
            #   否则每步派发用的还是启动时那一批老算法。
            当前项目名 = str(项目名 or "")

            # 这两样在下面创建，但 `_装配项目()` 要用 —— 所以先声明成 None 占位。
            # ★ 为什么允许它们是 None：装配通道和参数/发布通道是**互相独立**的，
            #   任何一条起不来都不应该让另一条失效（各自 try/except 兜底）。
            #   启动时的第一次装配发生在它们就绪之前，所以必须能容忍 None。
            参数应用器 = None
            项目发布 = None
            模型应用器 = None
            重力应用器 = None            # 内置件，注册在下面；这里先占位给 `_装配项目` 用
            当前算法信息: list = []
            当前控盘 = ""            # 真正驱动机械臂的那个算法（界面显示用）
            当前被覆盖: list = []      # 输出被整体盖掉的算法（界面显示用）
            当前已存盘 = True            # 当前这组算法是否与项目文件一致（界面 Save 按钮用）
            当前算法库: list = []        # 算法库里全部可选算法（算法变化时才重算，见 装配前刷新）

            model = mujoco.MjModel.from_xml_path(模型路径)
            data = mujoco.MjData(model)
            关键字 = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, "home")
            if 关键字 >= 0:
                mujoco.mj_resetDataKeyframe(model, data, 关键字)
            mujoco.mj_forward(model, data)

            def _重置姿态(模型, 数据) -> str:
                """把机器人摆回**默认姿态**（home 关键帧），并清掉速度。返回一句说明。

                ★ 为什么要有它（用户实测报上来的问题）：
                  换算法时物理状态**默认是不动的**，而多数控制算法"拿第一次看到的位置
                  当基准"。于是从算法 1 切到算法 2 时，算法 2 是在**算法 1 留下的姿态**
                  上开始控制的 —— 现象就是"机器人再也回不到默认位置了"。
                  实测：正弦摆动跑 400 步后偏离默认姿态 0.33 rad，切到关节 PD 后
                  它把这个姿态当了基准。

                做法与内置件 `重力应用器._自己复位()` 是同一套（一致很重要，
                否则同一个概念会有两种行为）：
                  ① 有 `home` 关键帧 → 用它（模型自带的"默认姿势"）
                  ② 没有 → `mj_resetData`（回到 XML 里的初始 qpos）
                  ③ 最后必须 `mj_forward`：复位只写了 qpos/qvel，
                     派生量（site 位置、雅可比等）要重算，否则画面和算法读到的还是旧值。
                """
                if 模型 is None or 数据 is None:
                    return ""
                try:
                    有home = mujoco.mj_name2id(模型, mujoco.mjtObj.mjOBJ_KEY, "home") >= 0
                    if 有home:
                        键 = mujoco.mj_name2id(模型, mujoco.mjtObj.mjOBJ_KEY, "home")
                        mujoco.mj_resetDataKeyframe(模型, 数据, 键)
                    else:
                        mujoco.mj_resetData(模型, 数据)
                    数据.qvel[:] = 0.0            # 关键帧不一定清速度；不清就会"带着旧速度出发"
                    数据.ctrl[:] = 0.0            # 上一组算法写下的力矩也清掉
                    mujoco.mj_forward(模型, 数据)
                    return (f"（已把机器人重置到默认姿态"
                            f"{'（home 关键帧）' if 有home else '（模型初始 qpos）'}）")
                except Exception as 异常:                                      # noqa: BLE001
                    return f"⚠ 重置姿态失败（算法照常在当前姿态上接手）：{type(异常).__name__}: {异常}"

            # ---- 项目装配：换模型 → 换一组算法（方案 C 的核心）----
            def _装配项目(新项目名: str, 新模型, 新数据, 新模型路径: str,
                          算法覆盖: list | None = None, 落盘: bool = False,
                          重置姿态: bool = False) -> list[str]:
                """按项目清单重新装配算法，装进注册表并通知各插件。

                返回给人看的报告行（会打进终端）。**这个函数必须在仿真线程里调用** ——
                它要换掉正在被仿真的那组插件实例。

                `算法覆盖` / `落盘` / `重置姿态` 给【Algorithms】面板用（界面当场选算法）：
                  · `算法覆盖` 非 None → 用用户选的这一组，**忽略项目文件里的 `算法` 字段**；
                  · `落盘=True` → 同时把这组选择写回项目文件（【Save】按钮）。
                    两者分开是刻意的：Apply 只临时生效（试错不会弄坏预设），Save 才落盘；
                  · `重置姿态=True` → 装配**之前**先把机器人摆回默认姿态（home 关键帧）。
                    ★ 这一条是"换算法后机器人回不到默认位置"的解药，见下面 `_重置姿态()`。
                """
                nonlocal 插件列表, 当前项目名, 项目发布, 当前算法信息, 当前已存盘
                nonlocal 当前控盘, 当前被覆盖, 重力应用器
                import 装配器 as _装配器

                数据 = _项目.读项目(新项目名) if 新项目名 else None

                # ★ 重置必须在**装配之前**：多数算法的设计是"拿第一次看到的位置当基准"
                #   （关节pd控制的 `目标`、正弦摆动的 `基准`）。先把机器人摆回默认姿态，
                #   新算法接手时看到的基准才是干净的。
                #   放装配之后就晚了 —— 那时算法的 `收到模型()` 已经拿旧姿态跑过一轮，
                #   有的算法（正弦摆动）在第一步就把 `基准` 定下来了。
                重置说明 = _重置姿态(新模型, 新数据) if 重置姿态 else ""

                新实例, 报告 = _装配器.按项目装配(数据, 新项目名, 模型=新模型,
                                                 算法覆盖=算法覆盖)
                if 重置说明:
                    报告.insert(0, 重置说明)

                # ① 把项目里存过的参数灌回插件（"上次调好的 KP/KD"要能延续）
                恢复 = _恢复参数(新项目名, 新实例)
                if 恢复:
                    报告.append(恢复)

                # ② 换掉注册表里的用户算法（内部插件保持不动，见 插件系统.设用户插件）
                注册表.设用户插件(新实例)

                # ③ 让常驻的内部插件重新认识这一组算法。
                #    ★ 这一步不能省：参数应用器原来只在启动时绑定一次，
                #      不重绑的话界面滑杆会"拖了没反应且不报错"（静默失效）。
                #    ★ 用 `is not None` 判断而不是无条件调用：启动时的第一次装配
                #      发生在参数桥建好**之前**（那时它还不存在），这是正常的 ——
                #      装配和参数桥是两条独立的通道，谁先就绪都不该让另一个失败。
                if 参数应用器 is not None:
                    参数应用器.重绑(注册表)

                # ④ 通知每个插件"模型 + 这一组算法是什么"
                算法信息 = 插件框架.收集算法信息(新实例)
                #   谁在控盘 / 谁被覆盖 —— 供界面显示（见 装配器._抢方向盘体检 的说明）。
                #   判定依据是算法自己声明的 `接管控制`（默认 True）：
                #   多个都声明接管时，**只有最后一个真正生效**，前面的被整体覆盖。
                _控盘 = [a["名称"] for a in 算法信息 if a.get("接管控制", True)]
                控盘 = ""
                被覆盖: list = []
                if len(_控盘) == 1:
                    控盘 = _控盘[0]
                elif len(_控盘) > 1:
                    控盘, 被覆盖 = _控盘[-1], _控盘[:-1]
                当前控盘, 当前被覆盖 = 控盘, 被覆盖
                # ★ 通知"所有插件"，不只是新装配的用户算法 —— 内置件也要收到模型。
                #   这里踩过一个很隐蔽的坑：原来传的是 `新实例`（只含用户算法），
                #   于是 `重力应用器` 这种**内置件永远收不到 `收到模型`**：
                #   它就不复位、不冻结，而物理从第一帧就在跑 —— 现象是
                #   "刚进模型就掉到偏离 home 0.77 rad 的位置，然后被冻在那个歪姿上"。
                #   通知列表改用 `注册表._目标`（= StepControl + 用户算法 + 全部内置件）。
                #   `算法信息` 仍然只含用户算法 —— 它表达的是"这一组装了哪些算法"，
                #   内置件不该出现在算法清单与录制元信息里。
                通知模型加载(list(getattr(注册表, "_目标", 新实例)), 新模型, 新数据,
                              算法信息, 新项目名)
                for _p in 新实例:
                    if hasattr(_p, "绑定模型路径"):
                        try:
                            _p.绑定模型路径(新模型路径)
                        except Exception as _异常:                         # noqa: BLE001
                            print(f"⚠ 插件【{getattr(_p, '名称', _p)}】的 绑定模型路径() 出错：{_异常}")
                    if hasattr(_p, "模型已切换"):
                        try:
                            _p.模型已切换(新模型路径, 新模型, 新数据)
                        except Exception as _异常:                         # noqa: BLE001
                            print(f"⚠ 插件【{getattr(_p, '名称', _p)}】的 模型已切换() 出错：{_异常}")

                插件列表 = 新实例
                当前项目名 = str(新项目名 or "")
                当前算法信息 = 算法信息
                _项目.保存上次项目(当前项目名)

                # ★ "这一组算法和项目文件一致吗" —— 界面上的 Save 按钮靠它决定是否可用
                当前已存盘 = 算法覆盖 is None
                if 落盘 and 算法覆盖 is not None and 数据 is not None:
                    # 【Save】：把界面上选的那组写回项目文件（只动 `算法` 字段，别的字段原样）
                    写回 = dict(数据)
                    写回.pop("_顺序说明", None)          # 那是给人看的说明，重写一份新的
                    写回["算法"] = [{"插件": str(x)} for x in 算法覆盖 if str(x).strip()]
                    写回["_顺序说明"] = (
                        "列表顺序 = 每步的执行顺序：最后一项最后写 ctrl[:]，所以它说了算。"
                        "（本列表由界面【Algorithms】面板的 Save 写回）")
                    if _项目.保存项目(写回):
                        当前已存盘 = True
                        报告.append(f"（已把这组算法写回 项目/{新项目名}.json）")
                    else:
                        报告.append("✗ 写回项目文件失败（选择已在本次运行生效，但没记住）")

                # ★ 模型应用器也要知道"当前是哪个模型/项目"（它 2 Hz 往界面报）：
                #   这两个字段以前在 `切换模型()` 里更新，现在收进这里 ——
                #   `切换模型()` 负责"换物理对象"，`_装配项目()` 负责"换工作环境"，
                #   同一个状态只在**一个地方**写，才不会出现两边不一致。
                if 模型应用器 is not None:
                    模型应用器.当前路径 = str(新模型路径 or "")
                    模型应用器.当前显示名 = (_项目.显示模型名(新模型路径)
                                            if 新模型路径 else "（外来模型）")
                    if 新模型路径:
                        try:
                            _模型桥.记住模型(新模型路径)       # 启动默认②"记住上次模型"
                        except Exception:                              # noqa: BLE001
                            pass

                # ⑤ 立刻发一条项目状态给界面（点模型 → 界面马上更新算法列表）。
                #    这里**主动发**、不等节拍：节拍是 2 秒一次的兜底，
                #    而"点一下就要看到算法列表变了"是交互体验的硬要求。
                if 项目发布 is not None:
                    项目发布.发布(项目状态(
                        项目=当前项目名,
                        模型路径=新模型路径,
                        模型显示名=_项目.显示模型名(新模型路径) if 新模型路径 else "",
                        算法=算法信息,
                        报告=报告,
                        算法库=当前算法库,
                        已存盘=当前已存盘,
                        控盘=控盘,
                        被覆盖=被覆盖,
                        重力开=bool(重力应用器.重力开) if 重力应用器 is not None else False,
                    ))
                return 报告

            句柄.send_to_viewer(messages.ModelEvent(model=model, path=模型路径))

            def _恢复参数(名: str, 实例表: list) -> str:
                """把项目文件里存过的参数灌回插件。返回一句给人看的说明（空串=没有）。

                ★ 为什么在**装配之后**马上灌一次：参数面板拖出来的值只活在内存里，
                  换项目 / 重启就没了。项目文件里存着上一次调好的值，
                  装配完立刻回填，用户点回来看到的就是上次那组参数。
                """
                if not 名:
                    return ""
                存的 = _项目.读参数(名)
                if not 存的:
                    return ""
                恢复数 = 0
                for _p in 实例表:
                    该插件 = 存的.get(str(getattr(_p, "名称", ""))) or {}
                    for _参数名, _值 in 该插件.items():
                        设 = getattr(_p, "设置参数", None)
                        if 设 is None:
                            continue
                        try:
                            if not 设(str(_参数名), float(_值)):
                                恢复数 += 1
                        except Exception:                                  # noqa: BLE001
                            continue
                return f"（已恢复项目里存的 {恢复数} 个参数值）" if 恢复数 else ""

            # ★ 算法库里有哪些可选算法 —— **只在这里算一次**。
            #   为什么不放进 `_装配项目()` 或发布循环：它要扫盘（os.walk），
            #   而主循环是 ~500 Hz 的热路径，每次扫盘会白白吃掉性能。
            #   它的用途有两个：① 发给界面做【Algorithms】面板的候选列表
            #   ② 进发布指纹，好让"往算法库里加了个 .py"这件事能被界面看见。
            try:
                当前算法库 = [d["插件"] for d in _项目.发现的算法()]
                print(f"【算法库】可选算法 {len(当前算法库)} 个：{'、'.join(当前算法库)}", flush=True)
            except Exception as 异常:                                      # noqa: BLE001
                print(f"⚠ 算法库扫描失败（界面上的算法列表会是空的）：{type(异常).__name__}: {异常}")

            # ---- 【Display】重力开关：**内置常驻**，与"挂不挂算法"完全无关 ----
            #   ★ 必须在**首次装配之前**注册：重力应用器要在第一次 `通知模型加载`
            #     时就收到模型、把机器人复位到默认位置并冻结。注册晚了（原来是放在
            #     模型桥那一段之后）的后果实测过：**首次加载没人复位**，
            #     而物理从屏幕第一帧就开始推进 —— 等应用器上线时模型已经掉到偏离
            #     home 0.74 rad 的位置，然后被冻在**那个歪姿**上，不是默认位置。
            #
            #   ★ 为什么是内置件而不是算法：
            #     需求是"**所有模型进去都静止**"，不能取决于"恰好装了某个算法"。
            #     它曾经是 算法库/通用/展示姿态.py 里的算法插件 —— 一旦用户把算法列表
            #     清空（正是现在要的默认状态），开关就静默失效。所以收进外壳：
            #     注册成内置件，不进 `_用户插件`，换算法时不会被换掉，也不出现在算法列表里。
            def _重置姿态回调() -> str:
                """给重力应用器的复位回调：无参、返回一句"怎么复位的"说明。

                复用 `_重置姿态()`，这样"换算法时重置"和"取消加载重力时复位"
                走的是**同一套代码** —— 否则同一个概念会长出两种行为。
                """
                新模型 = getattr(句柄, "model", None)
                新数据 = getattr(句柄, "data", None)
                if 新模型 is None or 新数据 is None:
                    return ""
                return _重置姿态(新模型, 新数据)

            重力应用器 = _重力桥.重力应用器(复位回调=_重置姿态回调)
            注册表.加插件(重力应用器)          # 让它收到 重力状态
            重力应用器.登记到注册表(注册表)     # ★ 登记"世界冻结"判据 —— 冻结靠这个生效
                                                #   （不能用"改暂停快照"实现：官方不发快照）
            print("【重力】开关已就绪（默认冻结在默认位置；勾选【Display】的"
                  "「加载重力」才施用重力）", flush=True)

            # 启动时也走同一条装配路径（保证"启动"和"点模型"行为完全一致）
            try:
                项目发布 = _模型桥.项目状态发布器(仿真端点.send_to_viewer)
                报告 = _装配项目(当前项目名, model, data, 模型路径)
                for _行 in 报告:
                    print(f"  {_行}", flush=True)
            except Exception as 异常:                                      # noqa: BLE001
                print(f"⚠ 项目装配不可用（本组算法保持 主程序.py 里装好的那一批）："
                      f"{type(异常).__name__}: {异常}")

            print("【仿真线程】模型已发送给窗口，开始跑控制回路…", flush=True)
            print("（下面每 2 秒打一行插件状态，可以据此判断算法到底有没有在干活）\n", flush=True)

            上次状态 = 0.0

            # ------------------------------------------------------------------
            # 模型桥：把"换模型"收敛到这一个函数里（见 模型桥.py 的说明）
            #
            # ★ 为什么必须自己做这件事（踩过的坑）：
            #   官方推荐的循环是 handle.sync(...)，它会把 viewer 事件派发给插件；
            #   而我们为了做出错隔离把 sync() 拆开自己写，viewer 事件进的是
            #   **我们的注册表**，里面没有 ViewerHandle。
            #   于是用户在窗口里拖进一个模型时：窗口侧的画面换了，仿真侧的
            #   model/data 却没人接 —— 画面和物理对不上。这里补上这一环。
            # ------------------------------------------------------------------
            模型应用器 = None
            try:
                def 切换模型(模型=None, 路径: str = "", 通知窗口: bool = True):
                    """加载并重绑一个新模型。返回 (是否成功, 给人看的一句话)。"""
                    if 模型 is None:
                        if not 路径 or not os.path.exists(路径):
                            return False, f"模型文件不存在：{路径 or '（空路径）'}"
                        起点 = _time.perf_counter()
                        try:
                            模型 = mujoco.MjModel.from_xml_path(路径)
                        except Exception as 异常:                          # noqa: BLE001
                            # ★ 加载失败绝不能影响正在跑的旧模型（用户可能只是选错了文件）
                            return False, f"加载失败（已保留原模型）：{type(异常).__name__}: {异常}"
                        耗时 = _time.perf_counter() - 起点
                    else:
                        耗时 = 0.0

                    数据 = mujoco.MjData(模型)
                    键 = mujoco.mj_name2id(模型, mujoco.mjtObj.mjOBJ_KEY, "home")
                    if 键 >= 0:
                        mujoco.mj_resetDataKeyframe(模型, 数据, 键)
                    mujoco.mj_forward(模型, 数据)

                    # ① 重绑外壳正在用的这一份（循环末尾会从 句柄 读回去）
                    句柄.model, 句柄.data = 模型, 数据
                    # ② 告诉窗口侧（拖拽那条路窗口自己已经有了，就不用回发）
                    if 通知窗口:
                        句柄.send_to_viewer(messages.ModelEvent(model=模型, path=路径))
                    # ③ ★ 换算法组：按模型反查项目，再按项目重新装配
                    #    - 空场景 / 外来模型 / 没有项目的模型 → 项目名为空 → 空算法集
                    #      （以前这两种情况会留着上一个模型的控制律继续跑，既危险又费解）
                    新项目名 = _项目.按模型找项目(路径) if 路径 else ""
                    # 换模型也重置姿态：这是新加载的 MjData，本来就该从默认姿态开始
                    # （否则若模型没换、只是重新加载，同样会把"上一次的姿态"当基准）
                    报告 = _装配项目(新项目名, 模型, 数据, 路径, 重置姿态=True)
                    for _行 in 报告:
                        print(f"  {_行}", flush=True)

                    if 模型应用器 is not None:
                        模型应用器.自由度 = int(模型.nq)
                        模型应用器.执行器数 = int(模型.nu)
                        模型应用器.耗时 = 耗时
                    显示 = _模型桥.显示名(路径) if 路径 else "（外来模型）"
                    return True, (f"已切换到 {显示}（{int(模型.nq)} 轴、"
                                  f"{len(插件列表)} 个算法、耗时 {耗时*1000:.0f} ms）" if 耗时
                                  else f"已切换到 {显示}（{int(模型.nq)} 轴、{len(插件列表)} 个算法）")

                模型应用器 = _模型桥.模型应用器(切换模型)
                # ★ 当前路径/显示名/自由度/执行器数**不在这里设**：
                #   `_装配项目()` 刚才已经填过一遍（它同时知道项目名与显示名）。
                #   同一份状态两处赋值，迟早会出现"面板显示的和实际跑的不是一回事"。
                注册表.加插件(模型应用器)          # 让它收到 换模型命令 / 拖拽的 ModelEvent
                模型发布 = _模型桥.发布器(仿真端点.send_to_viewer, 频率=2.0)

                # ---- 【Algorithms】面板的落地端：界面选了算法 → 在这里重新装配 ----
                #   ★ 为什么要有这个回调：装配必须换掉**正在被仿真的那批插件实例**，
                #     而界面线程不能碰仿真侧的对象（跨线程改状态）。所以界面只"说想要哪几个"，
                #     装配在这里做（`_装配项目()` 的 算法覆盖 参数）。
                def 换算法(算法列表: list, 落盘: bool = False, 重置姿态: bool = True):
                    """界面选了一组算法 → 按它重新装配。返回 (是否成功, 给人看的一句话)。"""
                    if not 算法列表:
                        return False, "一个算法都没选（至少勾一个；只想空跑请用 --无插件）"
                    报告 = _装配项目(当前项目名, 句柄.model, 句柄.data, 模型应用器.当前路径,
                                     算法覆盖=算法列表, 落盘=落盘, 重置姿态=重置姿态)
                    失败 = [行 for 行 in 报告 if str(行).startswith("✗")]
                    已装 = len(插件列表)
                    尾巴 = "并已写回项目文件" if 落盘 else "（临时生效，未写回项目文件）"
                    return (not 失败), f"已装配 {已装} 个算法{尾巴}" + (
                        f"；{len(失败)} 个失败（见终端）" if 失败 else "")

                算法选择器 = _模型桥.算法选择器(换算法)
                注册表.加插件(算法选择器)          # 让它收到 应用算法命令
                print(f"【模型】模型库已就绪（当前：{模型应用器.当前显示名}）"
                      f"—— 界面【模型库】面板可切换，也可以把 .xml 拖进窗口", flush=True)
                print("【算法】算法选择面板已就绪（界面【Algorithms】页签可勾选/调序/应用）",
                      flush=True)
            except Exception as 异常:                                     # noqa: BLE001
                print(f"⚠ 模型桥不可用（将无法在界面里切换模型）：{type(异常).__name__}: {异常}")
                模型发布 = None

            # 参数通道：把"插件声明了哪些可调参数"周期性发给界面（第 4 步 参数面板）
            try:
                import 参数桥 as _参数桥

                def _参数存盘(插件名: str, 值表: dict) -> None:
                    """把界面上拖出来的参数写回**当前项目文件**（方案 C：参数可复现）。

                    ★ 为什么由外壳提供这个回调、而不是让参数桥自己读写项目文件：
                      "当前是哪个项目"这本账在外壳手里（换模型时会变），
                      参数桥只管"界面 → 插件"这条线。职责分开，换项目时才不会写错文件。
                    """
                    if not 当前项目名:
                        return                     # 没有项目 → 参数无处可存（正常，不是错误）
                    _项目.保存参数(当前项目名, 插件名, 值表)

                参数发布 = _参数桥.发布器(仿真端点.send_to_viewer)
                应用器 = _参数桥.参数应用器(参数存盘=_参数存盘).绑定(注册表)
                参数应用器 = 应用器              # 给 `_装配项目()` 用（它每次装配后会重绑）
                注册表.加插件(应用器)                          # 让它也收到参数消息
                print("【参数】控制器参数面板已就绪"
                      "（界面里拖滑杆即可实时改参数；改动会写回当前项目文件）", flush=True)
            except Exception as 异常:                                     # noqa: BLE001
                print(f"⚠ 参数桥不可用（参数面板将无法改参数）：{type(异常).__name__}: {异常}")
                参数发布, 应用器 = None, None

            # 辨识通道：把"参数辨识插件"的状态周期性发给界面（第 4 步 D3 界面化）
            try:
                import 辨识桥 as _辨识桥
                辨识发布 = _辨识桥.发布器(仿真端点.send_to_viewer)
                # ★ 这里不再逐个插件调 `绑定模型路径`：那件事已经收进 `_装配项目()`
                #   （装配完就通知，换模型时也会重来一遍）。以前在这里做，
                #   等价于"启动时通知一次"，换模型后就不再同步了。
                print("【辨识】参数辨识面板已就绪（激励采样 → 后台辨识 → 看拟合改善）", flush=True)
            except Exception as 异常:                                     # noqa: BLE001
                print(f"⚠ 辨识桥不可用（辨识面板将无法工作）：{type(异常).__name__}: {异常}")
                辨识发布 = None
            # 指标发布器：把插件 指标() 报上来的数送给窗口侧面板画曲线（第 4 步 D1）
            # 限频到 ~30 Hz（物理 500 Hz，曲线不需要那么密），失败不影响控制回路
            try:
                import 指标桥 as _指标桥
                指标发布 = _指标桥.发布器(仿真端点.send_to_viewer)
            except Exception as 异常:                                     # noqa: BLE001
                print(f"⚠ 指标桥不可用（监控面板将没有数据）：{异常}")
                指标发布 = None
            while not 停止.is_set():
                # 官方 ViewerHandle.sync 做了三件事，我们拆开自己做，好插入出错隔离：
                #   ① 处理 viewer 发来的事件/快照  ② 派发 StepEvent  ③ 回发状态快照
                #   ★ 其中第 ② 步的"推进物理"由官方的 StepControl 插件完成（见 插件系统.py 的说明），
                #     它同时负责暂停/单步/倍速/噪声/发散后自动重置 —— 所以这里不再自己管节拍。
                句柄.model, 句柄.data = model, data

                for 事件 in 仿真端点.get_viewer_events():
                    注册表.处理消息(事件)
                for 快照 in 仿真端点.get_viewer_snapshots():
                    注册表.处理消息(快照)

                if 句柄.model is None:
                    break
                model, data = 句柄.model, 句柄.data

                # 派发 StepEvent：StepControl（内置）推进物理 + 你的插件写控制量
                注册表.处理消息(messages.StepEvent(model=model, data=data))

                # 送一帧指标给界面（内部按 30 Hz 限频，不会每圈都发）
                if 指标发布 is not None:
                    指标发布.也许发布(注册表, float(data.time), _time.perf_counter())
                # 周期性送"可调参数表"给界面（10 Hz 够了，滑杆不需要更密）
                if 参数发布 is not None:
                    参数发布.也许发布(注册表, float(data.time), _time.perf_counter())
                # 辨识状态（5 Hz 够了：采样/辨识都是秒级过程）
                if 辨识发布 is not None:
                    辨识发布.也许发布(注册表, _time.perf_counter())
                # 当前模型状态（2 Hz 够了：只在切换时才会变）
                if 模型发布 is not None:
                    模型发布.也许发布(模型应用器, _time.perf_counter())
                # 当前项目状态（哪个项目 / 挂了哪些算法 / 参数多少）。
                # ★ 装配完成时会**主动发**一条（点模型立刻更新），这里只是兜底重发：
                #   内容没变时 `也许发布` 内部会跳过，所以不构成额外负担。
                #   算法信息用装配时算好的快照，**不在这个循环里重算** ——
                #   这里是 ~500 Hz 的热路径，而 `收集算法信息()` 要遍历全部插件、
                #   还会调用它们的 `可调参数()`，放在循环里是纯浪费。
                if 项目发布 is not None:
                    项目发布.也许发布(项目状态(
                        项目=当前项目名,
                        模型路径=(模型应用器.当前路径 if 模型应用器 is not None else ""),
                        模型显示名=(模型应用器.当前显示名 if 模型应用器 is not None else ""),
                        算法=当前算法信息,
                        算法库=当前算法库,
                        已存盘=当前已存盘,
                        控盘=当前控盘,
                        被覆盖=当前被覆盖,
                        重力开=bool(重力应用器.重力开) if 重力应用器 is not None else False,
                    ), _time.perf_counter())

                集成签名 = int(mujoco.mjtState.mjSTATE_INTEGRATION)
                集成状态 = _np.empty(mujoco.mj_stateSize(model, 集成签名), _np.float64)
                mujoco.mj_getState(model, data, 集成状态, 集成签名)
                仿真端点.send_to_viewer(
                    messages.StateSnapshot(state=集成状态, state_sig=集成签名))

                # 官方 StepControl 自己会按刷新预算等待；这里补一点点，避免极端情况下空转
                _time.sleep(0.0002)

                # ---- 每 2 秒在终端打一行插件状态（看得见"算法正在干活"）----
                现在 = _time.perf_counter()
                if 现在 - 上次状态 >= 2.0:
                    上次状态 = 现在
                    行 = 注册表.插件快照()
                    if 行:
                        print(f"  [t={data.time:6.2f}s] {行}", flush=True)
        except KeyboardInterrupt:
            print("\n【仿真线程】收到 Ctrl+C，正在退出…", flush=True)
        except Exception as 异常:                             # noqa: BLE001
            出错["异常"] = 异常
            print(f"\n✗ 仿真线程出错：{type(异常).__name__}: {异常}")
            traceback.print_exc(limit=6)
        finally:
            停止.set()
            try:
                句柄.close()
            except Exception:                                 # noqa: BLE001
                pass

    线程 = threading.Thread(target=仿真循环, daemon=True, name="仿真线程")
    线程.start()

    # ---- 4. 主线程跑窗口（这一步必须在主线程，否则 macOS 直接拒绝）----
    #      窗口侧挂三个插件：
    #        窗口类()   —— 官方 19 个面板（外面包了一层，用于主题与实例传递）
    #        界面桥()   —— 滑杆值送进仿真侧（见 界面桥.py）
    #        监控面板() —— 把我们自己的指标画成实时曲线（见 面板/监控面板.py，第 4 步 D1）
    窗口插件 = []
    try:
        import 界面桥 as _界面桥
        窗口实例 = _界面桥.制作窗口类(窗口类)()          # 包一层：主题/实例传递用
        窗口插件 = [窗口实例, _界面桥.界面桥()]
    except Exception as 异常:                                 # noqa: BLE001
        print(f"⚠ 界面桥加载失败（{异常}），只开官方界面")
        窗口插件 = [窗口类()]

    #   ★ 面板目录里的每个 .py 都会被自动加载（约定：模块里有 `面板类` 这个名字）。
    #     所以"加一个面板"= 往 面板/ 放一个文件，**不用改这个启动文件**。
    面板目录 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "面板")
    try:
        import sys as _sys
        if 面板目录 not in _sys.path:
            _sys.path.insert(0, 面板目录)
        已加载 = []
        待填信息 = []
        for 文件名 in sorted(os.listdir(面板目录)):
            if not 文件名.endswith(".py") or 文件名.startswith("_") or 文件名 == "曲线基类.py":
                continue
            模块名 = 文件名[:-3]
            try:
                模块 = __import__(模块名)
                面板类 = getattr(模块, "面板类", None)
                if 面板类 is None:
                    continue                      # 不是面板文件（比如纯工具模块）
                实例 = 面板类()
                窗口插件.append(实例)
                已加载.append(getattr(面板类, "面板显示名", 模块名))
                # 关于面板需要知道"谁在控制、用的什么模型、有哪些面板" → 启动后填进去
                if hasattr(实例, "设置信息"):
                    待填信息.append(实例)
            except Exception as 异常:                                 # noqa: BLE001
                print(f"⚠ 面板 {文件名} 加载失败（跳过）：{type(异常).__name__}: {异常}")
        for 实例 in 待填信息:
            try:
                实例.设置信息(插件列表, 模型路径, 已加载)
            except Exception as 异常:                                 # noqa: BLE001
                print(f"⚠ 面板信息注入失败：{type(异常).__name__}: {异常}")
        if 已加载:
            print(f"【界面】已加载 {len(已加载)} 个自定义面板：{'、'.join(已加载)}", flush=True)
    except Exception as 异常:                                 # noqa: BLE001
        print(f"⚠ 面板目录加载失败（不影响使用）：{type(异常).__name__}: {异常}")

    try:
        launch_native.run_native_viewer(配置, 查看端点, plugins=窗口插件)
    except KeyboardInterrupt:
        print("\n收到 Ctrl+C，正在关闭窗口…", flush=True)

    停止.set()
    线程.join(timeout=2.0)
    if "异常" in 出错:
        print(f"（仿真线程的异常已在上面打印）")
        return 1
    print("窗口已关闭。")
    return 0
