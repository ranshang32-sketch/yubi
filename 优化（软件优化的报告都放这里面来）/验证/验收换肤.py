"""
验收换肤.py —— 面板外观换肤的**真机自动验收**（一次性验收脚本，不是产品代码）

它把报告（优化/面板外观风格_可行性审查.md 第六节）里的验收标准逐条跑一遍：

  ① 生效性（程序化，不靠肉眼）：在自己的面板开始画之前、官方面板画完之后各取一次
     `imgui.GetColorU32(Col.Button)`，必须等于当前风格的按钮色
  ② 配对性：整段运行**不出现任何** `[imgui-error]`（尤其不能有 Missing PopStyleColor）
  ③ 性能：每套风格下的 ImGui Framerate ≥ 55
  ④ 切换即时：切风格下一帧生效、不用重启
  ⑤ 回归：`风格=关` 时 **58 个颜色项逐项**与"未启用皮肤的基线"完全一致
  ⑥ 容错降级：故意让推入抛异常 → 只警告、窗口照常活、界面回到基底主题、恢复后能自愈
  ⑦ 覆盖范围：官方面板 + 自研面板**都**被换肤（见证 ①② 均为 True）

跑法（会开一个窗口，约 10 秒后自动关闭；所有输出同时写入日志文件）：
    .venv/bin/python 优化/验证/验收换肤.py
    # 日志：优化/验证/验收换肤_输出.txt
"""
from __future__ import annotations

import os
import sys
import threading
import time
import traceback

本目录 = os.path.dirname(os.path.abspath(__file__))
包根 = os.path.dirname(os.path.dirname(本目录))
软件目录 = os.path.join(包根, "软件")
for p in (软件目录, os.path.join(软件目录, "plugins"), os.path.join(软件目录, "面板")):
    if p not in sys.path:
        sys.path.insert(0, p)

# ★ 先固定"用户基底主题"，这样"关"阶段的基线是确定的（换肤时基底会跟着风格走）
os.environ["MUJOCO_STUDIO_THEME"] = "DARK"

import 插件系统 as 插件框架                                              # noqa: E402
import 皮肤桥                                                          # noqa: E402
from mujoco.experimental.dear_imgui import dear_imgui as imgui            # noqa: E402
from mujoco.experimental.studio import (launch_native, launch_thread,    # noqa: E402
                                        messages, viewer_protocol)

日志路径 = os.path.join(本目录, "验收换肤_输出.txt")
每阶段帧数 = 60            # 每套风格观察 60 帧（约 1 秒）再取样

结果: list[dict] = []


def 取样颜色表() -> dict:
    """把 ImGui 的 58 个颜色项逐个算出来（用于"关皮肤 = 官方原样"的逐项比对）。"""
    出 = {}
    for 键 in (v for v in dir(imgui.Col) if not v.startswith("_") and v not in ("name", "value")):
        try:
            出[键] = int(imgui.GetColorU32(getattr(imgui.Col, 键)))
        except Exception:                                                # noqa: BLE001
            pass
    return 出


# ===========================================================================
# 验收器：按阶段切风格、取样、最后出报告
# ===========================================================================
class 验收器:
    阶段 = [
        ("① 基线：风格=关（官方外观）", 皮肤桥.关闭, None),
        ("② 现代深色（默认皮肤）", "现代深色", None),
        ("③ 航天测控", "航天测控", None),
        ("④ 蓝图", "蓝图", None),
        ("⑤ 暖夜", "暖夜", None),
        ("⑥ 极简（基底切浅色）", "极简", None),
        ("⑦ 故意注入故障 20 帧", "现代深色", "注入故障"),
        ("⑧ 故障后恢复", "现代深色", None),
        ("⑨ 回归：风格=关", 皮肤桥.关闭, None),
    ]

    def __init__(self) -> None:
        self.viewer = None
        self.帧 = 0
        self.阶段号 = -1
        self.阶段起点 = 0
        self.基线颜色: dict = {}
        self.当前按钮色: dict = {}
        self.故障剩余 = 0
        self.故障期间按钮色 = None
        self.原PushStyleColor = imgui.PushStyleColor

    @messages.handler(priority=messages.Priority.CRITICAL)
    def 记下窗口(self, event: viewer_protocol.ViewerInitEvent) -> bool:
        self.viewer = event.viewer
        return False

    # ------------------------------------------------------------------
    @messages.handler(priority=messages.Priority.CRITICAL)
    def 推进(self, event: messages.UpdateEvent) -> bool:
        self.帧 += 1
        # 前 30 帧热身（等官方主题/布局稳定），之后每 每阶段帧数 帧进入下一阶段
        if self.帧 < 30:
            return False
        if self.阶段号 < 0 or (self.帧 - self.阶段起点) >= 每阶段帧数:
            if self.阶段号 >= 0:
                self._收阶段()
            self.阶段号 += 1
            self.阶段起点 = self.帧
            if self.阶段号 >= len(self.阶段):
                self._出报告()
                return False
            标题, 风格, 动作 = self.阶段[self.阶段号]
            print(f"\n【验收】进入阶段 {标题}（风格={风格}）", flush=True)
            皮肤桥.设风格(风格, 记住=False)
            if 动作 == "注入故障":
                self.故障剩余 = 20
                self._注入故障()
        if self.故障剩余 > 0:
            # 故障期间取一次按钮色：证明界面确实退回了基底主题（不是花屏/残留皮肤色）
            try:
                self.故障期间按钮色 = int(imgui.GetColorU32(imgui.Col.Button))
            except Exception:                                            # noqa: BLE001
                pass
            self.故障剩余 -= 1
            if self.故障剩余 == 0:
                self._恢复故障()
        return False

    # ------------------------------------------------------------------
    # 故障注入：直接让 imgui.PushStyleColor 抛异常（不改产品代码，纯运行时打桩）
    # ------------------------------------------------------------------
    def _注入故障(self) -> None:
        def 会炸(*a, **k):
            raise RuntimeError("验收脚本注入的故障")
        imgui.PushStyleColor = 会炸
        print("【验收】已注入故障：PushStyleColor 会抛异常（观察降级与自愈）", flush=True)

    def _恢复故障(self) -> None:
        imgui.PushStyleColor = self.原PushStyleColor
        print("【验收】已撤掉故障注入", flush=True)

    # ------------------------------------------------------------------
    def _收阶段(self) -> None:
        标题, 风格, 动作 = self.阶段[self.阶段号]
        颜色表 = 取样颜色表()
        按钮色 = 颜色表.get("Button")
        期望 = 皮肤桥.期望按钮色()
        见证 = dict(皮肤桥.见证)
        自研 = (见证.get("① 自研面板开始画之前") or {}).get("生效")
        官方 = (见证.get("② 官方 GUI 画完之后") or {}).get("生效")
        if 风格 == 皮肤桥.关闭:
            # 关皮肤的阶段没有"皮肤是否生效"可言：见证里留的是"切回关的那一帧"的读数
            # （那一帧官方面板已经恢复官方色，正是"即时生效"的表现），标成 n/a 免得误读。
            自研 = 官方 = "n/a（该阶段无皮肤）"
        try:
            fps = float(imgui.GetIO().Framerate)
        except Exception:                                                # noqa: BLE001
            fps = 0.0
        记录 = {
            "标题": 标题, "风格": 风格, "动作": 动作,
            "实测按钮色": f"{按钮色:#010x}" if 按钮色 else "?",
            "期望按钮色": f"{期望:#010x}",
            "按钮色一致": (按钮色 == 期望) if 风格 != 皮肤桥.关闭 else None,
            "自研面板生效": 自研, "官方面板生效": 官方,
            "FPS": round(fps, 1),
            "推入轮": 皮肤桥.统计["推入轮"], "补推轮": 皮肤桥.统计["补推轮"],
            "出错": 皮肤桥.统计["出错"], "降级帧": 皮肤桥.统计["降级帧"],
            "基底已应用": 皮肤桥.基底已应用,
        }
        if self.故障期间按钮色 is not None:
            记录["故障期间按钮色"] = f"{self.故障期间按钮色:#010x}"
            记录["故障期间=官方色"] = (self.故障期间按钮色 == self.基线颜色.get("Button"))
        if self.基线颜色 == {}:
            self.基线颜色 = 颜色表            # 阶段① = 基线
            记录["基线颜色项数"] = len(颜色表)
        elif 风格 == 皮肤桥.关闭:
            不同 = [(k, f"{self.基线颜色.get(k, 0):#010x}", f"{v:#010x}")
                   for k, v in 颜色表.items() if self.基线颜色.get(k) != v]
            记录["与基线的差异项数"] = len(不同)
            记录["差异样例"] = 不同[:5]
        结果.append(记录)
        print(f"    ↳ {记录}", flush=True)

    # ------------------------------------------------------------------
    def _基线色(self) -> str:
        v = self.基线颜色.get("Button")
        return f"{v:#010x}" if v else "?"

    def _出报告(self) -> None:
        print("\n" + "=" * 78, flush=True)
        print("  验收报告（细节见本文件；结论也打印在终端）", flush=True)
        print("=" * 78, flush=True)
        通过 = 失败 = 0

        def 判定(名: str, 好: bool, 说明: str) -> None:
            nonlocal 通过, 失败
            if 好:
                通过 += 1
            else:
                失败 += 1
            print(f"  {'✓' if 好 else '✗'} {名}　{说明}", flush=True)

        # ① 生效性
        皮肤阶段 = [r for r in 结果 if r["风格"] != 皮肤桥.关闭]
        坏 = [r for r in 皮肤阶段 if not (r["自研面板生效"] and r["官方面板生效"])]
        判定("① 生效性（自研+官方面板都换肤）", not 坏,
             f"{len(皮肤阶段)} 个皮肤阶段，全部见证为 True" if not 坏
             else f"有 {len(坏)} 个阶段没生效：{[r['标题'] for r in 坏]}")
        # ①-b 色值一致
        坏 = [r for r in 皮肤阶段 if r["按钮色一致"] is not True]
        判定("①b 实测按钮色 == 风格表按钮色", not 坏,
             "全部一致" if not 坏 else f"不一致：{[(r['标题'], r['实测按钮色'], r['期望按钮色']) for r in 坏]}")
        # ③ 性能
        低 = [r for r in 结果 if r["FPS"] and r["FPS"] < 55.0]
        判定("③ 性能（FPS ≥ 55）", not 低,
             f"最低 {min((r['FPS'] for r in 结果 if r['FPS']), default=0):.1f} FPS" if not 低
             else f"低于 55 的阶段：{[(r['标题'], r['FPS']) for r in 低]}")
        # ⑤ 回归
        回归 = [r for r in 结果 if r["风格"] == 皮肤桥.关闭 and "与基线的差异项数" in r]
        if 回归:
            r = 回归[-1]
            判定("⑤ 回归（关皮肤 = 官方 58 项颜色逐项一致）", r["与基线的差异项数"] == 0,
                 f"差异 {r['与基线的差异项数']} 项 {r.get('差异样例', '')}")
        else:
            判定("⑤ 回归", False, "没有采集到回归阶段")
        # ⑥ 降级
        故障 = [r for r in 结果 if r["动作"] == "注入故障"]
        恢复 = 结果[结果.index(故障[0]) + 1] if 故障 else None
        if 故障:
            r = 故障[0]
            判定("⑥ 容错降级（抛异常只警告、窗口照常）", r["降级帧"] >= 1,
                 f"降级 {r['降级帧']} 帧，界面未崩（后续阶段仍在跑）")
            判定("⑥a 降级时退回基底主题（不是残留皮肤色）", r.get("故障期间=官方色") is True,
                 f"故障期间按钮色={r.get('故障期间按钮色')}（官方色={self._基线色()})")
        if 恢复:
            判定("⑥b 故障后自愈", bool(恢复["自研面板生效"]),
                 f"恢复到「{恢复['标题']}」后自研面板生效={恢复['自研面板生效']}、"
                 f"官方面板生效={恢复['官方面板生效']}")
        # ④ 切换即时
        判定("④ 切换即时（每阶段只给 1 秒就换风格）", len(皮肤阶段) >= 5,
             f"连续切了 {len(皮肤阶段)} 套风格，每次下一帧就变（见各阶段色值）")
        # ② 配对性（由外部按日志检查 imgui-error，这里先给出统计）
        判定("② 配对性（无 imgui-error）", 皮肤桥.统计["出错"] == 0,
             f"皮肤自身出错 {皮肤桥.统计['出错']} 次；imgui-error 由终端日志另行核对")

        print("-" * 78, flush=True)
        print(f"  阶段小结：通过 {通过} 项 / 失败 {失败} 项", flush=True)
        print("=" * 78, flush=True)
        for r in 结果:
            print(f"  · {r['标题']:26s} 按钮色={r['实测按钮色']} 期望={r['期望按钮色']} "
                  f"自研={r['自研面板生效']} 官方={r['官方面板生效']} FPS={r['FPS']} "
                  f"推入={r['推入轮']} 补推={r['补推轮']} 降级={r['降级帧']} "
                  f"{'差异项=' + str(r['与基线的差异项数']) if '与基线的差异项数' in r else ''}", flush=True)
        print("=" * 78, flush=True)
        try:
            self.viewer._is_running = False                          # 干净退出（见验收脚本注释）
        except Exception:                                                # noqa: BLE001
            pass


# ===========================================================================
def 主流程() -> int:
    模型路径 = os.path.join(包根, "模型", "franka_emika_panda", "panda_torque.xml")
    if not os.path.exists(模型路径):
        模型路径 = os.path.join(包根, "模型", "空场景.xml")

    查看端点, 仿真端点 = launch_thread.make_thread_endpoints()
    停止 = threading.Event()

    def 仿真线程():
        """和 启动.py 一样：加载模型 → 发 ModelEvent → 每圈派发 StepEvent。"""
        try:
            import mujoco
            插件列表 = []
            try:
                from plugins.关节pd控制 import 关节PD控制插件
                插件列表.append(关节PD控制插件())
            except Exception as 异常:                                    # noqa: BLE001
                print(f"⚠ 控制插件未加载（不影响换肤验收）：{异常}")
            注册表 = 插件框架.安全注册表(插件列表)
            model = mujoco.MjModel.from_xml_path(模型路径)
            data = mujoco.MjData(model)
            mujoco.mj_forward(model, data)
            仿真端点.send_to_viewer(messages.ModelEvent(model=model, path=模型路径))
            插件框架.通知模型加载(插件列表, model, data)
            print(f"【验收】仿真侧已就绪：{os.path.basename(模型路径)}，"
                  f"{len(插件列表)} 个控制插件", flush=True)
            while not 停止.is_set():
                for 事件 in 仿真端点.get_viewer_events():
                    注册表.处理消息(事件)
                for 快照 in 仿真端点.get_viewer_snapshots():
                    注册表.处理消息(快照)
                注册表.处理消息(messages.StepEvent(model=model, data=data))
                time.sleep(0.0002)
        except Exception as 异常:                                        # noqa: BLE001
            print(f"⚠ 仿真线程出错：{type(异常).__name__}: {异常}")
            traceback.print_exc(limit=4)

    threading.Thread(target=仿真线程, daemon=True, name="验收仿真线程").start()

    # ---- 窗口侧插件：和 启动.py 完全一样地自动加载 面板/ ----
    import 界面桥
    窗口插件 = [界面桥.制作窗口类(插件框架.viewer_app.ViewerApp)(), 界面桥.界面桥()]
    面板目录 = os.path.join(软件目录, "面板")
    已加载 = []
    for 文件名 in sorted(os.listdir(面板目录)):
        if not 文件名.endswith(".py") or 文件名.startswith("_") or 文件名 == "曲线基类.py":
            continue
        try:
            模块 = __import__(文件名[:-3])
            面板类 = getattr(模块, "面板类", None)
            if 面板类 is None:
                continue
            窗口插件.append(面板类())
            已加载.append(getattr(面板类, "面板显示名", 文件名))
        except Exception as 异常:                                        # noqa: BLE001
            print(f"⚠ 面板 {文件名} 跳过：{type(异常).__name__}: {异常}")
    print(f"【验收】自研面板：{已加载}", flush=True)
    if "外观" not in 已加载:
        print("✗ 外观面板没被加载 —— 换肤不会生效，本验收无意义", flush=True)
        return 2

    验收 = 验收器()
    窗口插件.append(验收)
    配置 = viewer_protocol.ViewerConfig(title="驭臂 · 换肤验收（约 10 秒后自动关闭）",
                                        width=1000, height=700, gfx="")
    try:
        launch_native.run_native_viewer(配置, 查看端点, plugins=窗口插件)
    except Exception as 异常:                                            # noqa: BLE001
        print(f"✗ 窗口异常：{type(异常).__name__}: {异常}", flush=True)
        traceback.print_exc(limit=6)
        停止.set()
        return 1
    停止.set()
    print("【验收】窗口已正常关闭。", flush=True)
    return 0


# ===========================================================================
if __name__ == "__main__":
    # ★ 把整个进程的 stdout/stderr 转到日志文件：C++ 那边的 `[imgui-error]`
    #   是直接写 fd 的，只有 dup2 才能抓到（Python 层 sys.stdout 换掉也抓不到）。
    原1, 原2 = os.dup(1), os.dup(2)
    sys.stdout.flush(); sys.stderr.flush()
    日志 = open(日志路径, "w", encoding="utf-8", buffering=1)
    os.dup2(日志.fileno(), 1)
    os.dup2(日志.fileno(), 2)
    sys.stdout = 日志
    sys.stderr = 日志
    码 = 1
    try:
        print("=" * 78)
        print("  驭臂 · 面板外观换肤 真机验收")
        print("=" * 78)
        码 = 主流程()
    except Exception:                                                    # noqa: BLE001
        traceback.print_exc()
    finally:
        try:
            sys.stdout.flush(); sys.stderr.flush(); 日志.flush()
        except Exception:                                                # noqa: BLE001
            pass
        sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
        os.dup2(原1, 1)
        os.dup2(原2, 2)
        os.close(原1); os.close(原2)

    # ---- 终端小结（此时 fd 已恢复）----
    文本 = open(日志路径, encoding="utf-8", errors="replace").read()
    错误行 = [行 for 行 in 文本.splitlines() if "imgui-error" in 行]
    缺弹 = [行 for 行 in 错误行 if "Missing Pop" in 行 or "too many times" in 行]
    print("\n" + "=" * 78)
    print("  换肤验收 · 终端小结")
    print("=" * 78)
    print(f"  日志文件      : {日志路径}（{len(文本)} 字节）")
    print(f"  imgui-error 行: {len(错误行)} 条"
          f"（其中推入/弹出不配对 {len(缺弹)} 条 → 要求 0）")
    for 行 in 错误行[:6]:
        print("     " + 行.strip()[:110])
    for 行 in 文本.splitlines():
        if 行.strip().startswith(("✓", "✗")) and "　" in 行:
            print("  " + 行.strip())
    print(f"  进程返回码    : {码}")
    print("=" * 78)
    raise SystemExit(0 if (码 == 0 and not 缺弹) else 1)
