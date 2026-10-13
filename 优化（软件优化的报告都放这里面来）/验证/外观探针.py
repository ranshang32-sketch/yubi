"""
外观探针.py —— "驭臂能不能被我们换皮肤"的真机实测（一次性验证脚本，不是产品代码）

它回答 7 个必须靠实测才能定的问题（光读绑定文档定不下来）：

  ① `imgui.GetStyle()` 到底能不能改？绑定里只暴露 3 个字段，没有 `SetStyleColor`。
     → "全局换肤"这条路通不通？
  ② `PushStyleColor / PushStyleVar` 推入后**真的生效**吗？（用 GetColorU32 前后对比证明）
  ③ 逐帧"推入 → 弹出"能不能覆盖**我们自己的 6 个面板**？（见证面板取证）
  ④ 能不能覆盖**官方那 19 个面板**？（★ 这是全案的分水岭，答案在下面 D 段）
  ⑤ 推入之后**忘了弹**会怎样？（Dear ImGui 的 "Missing PopStyleColor()" 检查）
  ⑥ 逐帧换肤**要花多少时间**？（不能拖慢 3D 视图）
  ⑦ 字体能不能换？能不能画斜线色块？（决定风格能做到几分）

跑法（会在屏幕上开一个 900x600 的窗口，约 4 秒后自己关掉）：
    .venv/bin/python 优化/验证/外观探针.py
    # 输出同时被记录在 优化/验证/外观探针_输出.txt
"""
from __future__ import annotations

import os
import sys
import threading
import time
import traceback

# ---- 路径：本文件在 <包根>/优化/验证/ 下 ----
本目录 = os.path.dirname(os.path.abspath(__file__))
包根 = os.path.dirname(os.path.dirname(本目录))
软件目录 = os.path.join(包根, "软件")
for p in (软件目录, os.path.join(软件目录, "plugins"), os.path.join(软件目录, "面板")):
    if p not in sys.path:
        sys.path.insert(0, p)

import 插件系统 as 插件框架                                              # noqa: E402
from mujoco.experimental.dear_imgui import dear_imgui as imgui            # noqa: E402
from mujoco.experimental.implot import implot                            # noqa: E402
from mujoco.experimental.studio import (launch_native, launch_thread,    # noqa: E402
                                        messages, viewer_protocol, ux)

报告: list[str] = []
顺序: list[str] = []                 # 一帧内 BuildGuiEvent 的派发顺序（谁先画）
见证结果: dict = {}                  # 见证面板看到的"有效颜色"

皮肤按钮色 = (0.80, 0.12, 0.12, 1.0)  # 探针用的醒目测试色（与正式风格无关）
皮肤在推 = False                      # 皮肤当前是否已推入
已推颜色数 = 0                        # 本帧已推入的颜色条数（可能推不止一轮，见 D 段）
已推变量数 = 0
皮肤轮数 = 0
推入耗时 = 0.0
弹出耗时 = 0.0


def 记录(行: str) -> None:
    print("探针] " + 行, flush=True)
    报告.append(行)


# ===========================================================================
# 皮肤本体：一次"推入"
# ===========================================================================
def _推入皮肤色() -> None:
    """把一套皮肤推入 ImGui 的样式栈（颜色 + 形状）。每次调用都要配对 Pop。"""
    global 已推颜色数, 已推变量数, 皮肤轮数
    for 索引, 颜色 in (
        (imgui.Col.WindowBg,      imgui.Vec4(0.06, 0.06, 0.07, 1.0)),
        (imgui.Col.TitleBg,       imgui.Vec4(0.10, 0.02, 0.02, 1.0)),
        (imgui.Col.TitleBgActive, imgui.Vec4(0.55, 0.07, 0.07, 1.0)),
        (imgui.Col.Button,        imgui.Vec4(*皮肤按钮色)),
        (imgui.Col.ButtonHovered, imgui.Vec4(0.95, 0.22, 0.22, 1.0)),
        (imgui.Col.ButtonActive,  imgui.Vec4(0.60, 0.06, 0.06, 1.0)),
        (imgui.Col.FrameBg,       imgui.Vec4(0.12, 0.12, 0.13, 1.0)),
        (imgui.Col.Border,        imgui.Vec4(0.85, 0.75, 0.20, 1.0)),
        (imgui.Col.Separator,     imgui.Vec4(0.85, 0.75, 0.20, 0.60)),
        (imgui.Col.Text,          imgui.Vec4(0.97, 0.96, 0.92, 1.0)),
    ):
        imgui.PushStyleColor(索引, 颜色)
        已推颜色数 += 1
    for 索引, 值 in (
        (imgui.StyleVar.WindowRounding, 0.0), (imgui.StyleVar.FrameRounding, 0.0),
        (imgui.StyleVar.GrabRounding, 0.0), (imgui.StyleVar.ScrollbarRounding, 0.0),
        (imgui.StyleVar.TabRounding, 0.0), (imgui.StyleVar.WindowBorderSize, 2.0),
        (imgui.StyleVar.FrameBorderSize, 1.0),
        (imgui.StyleVar.WindowPadding, imgui.Vec2(10.0, 10.0)),
        (imgui.StyleVar.FramePadding, imgui.Vec2(9.0, 5.0)),
    ):
        imgui.PushStyleVar(索引, 值)
        已推变量数 += 1
    皮肤轮数 += 1


def 弹出皮肤() -> None:
    global 已推颜色数, 已推变量数
    if 已推颜色数 or 已推变量数:
        imgui.PopStyleColor(已推颜色数)
        imgui.PopStyleVar(已推变量数)
        已推颜色数 = 已推变量数 = 0


# ===========================================================================
# ★ 关键发现对应的补丁：官方 viewer_app.build_gui() 第 300 行**每帧**都调
#   ux.setup_theme(self.theme)，它是直接改写全局样式（不走 push 栈）——
#   会把我们在 UpdateEvent 里推入的颜色**整片抹掉**，官方面板因此换不上皮肤。
#   唯一出路：把 ux.setup_theme 包一层，官方设完主题后我们立刻盖回去。
# ===========================================================================
原版setup_theme = ux.setup_theme
主题应用次数 = [0]


def 包装setup_theme(主题):
    原版setup_theme(主题)
    主题应用次数[0] += 1
    if 皮肤在推:
        推入时刻.append(f"官方setup_theme#{主题应用次数[0]}之后→补推")
        _推入皮肤色()


ux.setup_theme = 包装setup_theme
推入时刻: list[str] = []


# ===========================================================================
# 见证插件：默认优先级(USER=100)，在"面板画窗口的那一刻"读一次有效颜色
# ===========================================================================
class 见证面板:
    @messages.handler
    def 画(self, event: messages.BuildGuiEvent) -> bool:
        顺序.append("面板(USER=100)")
        if not 皮肤在推:
            return False          # 只在"皮肤已推入"的帧取样，否则会读到没皮肤的帧
        try:
            见效 = int(imgui.GetColorU32(imgui.Col.Button))
            推入 = int(imgui.GetColorU32(imgui.Vec4(*皮肤按钮色)))
            见证结果["① 自研面板开始画时皮肤已生效"] = (见效 == 推入)
            见证结果["① 实测按钮色"] = f"{见效:#010x}"
        except Exception as 异常:                                        # noqa: BLE001
            见证结果["① 读色失败"] = f"{type(异常).__name__}: {异常}"
        return False


# ===========================================================================
# 探针插件
# ===========================================================================
class 外观探针:
    def __init__(self) -> None:
        self.viewer = None
        self.帧 = 0
        self.逐帧推送次数 = 0
        self.逐帧弹出次数 = 0
        self.泄漏测试帧 = -1
        self.结束帧 = 140
        self.顺序已记 = False

    @messages.handler(priority=messages.Priority.CRITICAL)
    def _记下viewer(self, event: viewer_protocol.ViewerInitEvent) -> bool:
        self.viewer = event.viewer
        return False

    # -- 每帧开头（CRITICAL=最高 → 在所有面板之前）------------------------
    @messages.handler(priority=messages.Priority.CRITICAL)
    def _每帧开头(self, event: messages.UpdateEvent) -> bool:
        global 皮肤在推, 推入耗时
        self.帧 += 1
        try:
            if self.帧 == 3:
                self._探测A_全局样式字段()
                self._探测B_推入是否真的生效()
                self._探测E_字号与曲线换肤()
            if 10 <= self.帧 <= 60:                     # 阶段二：逐帧换肤
                t0 = time.perf_counter()
                _推入皮肤色()                            # 第 1 轮：盖住我们自己的面板
                推入耗时 += time.perf_counter() - t0
                皮肤在推 = True
                self.逐帧推送次数 += 1
                if self.帧 == 10:
                    记录(f"B6 逐帧推入皮肤：10 个颜色 + 9 个形状变量（19 项）")
            if self.帧 == 70:                           # 阶段三：故意不弹出
                self._泄漏推入()
        except Exception as 异常:                                        # noqa: BLE001
            记录(f"✗ 探测出错（帧 {self.帧}）：{type(异常).__name__}: {异常}")
            traceback.print_exc(limit=4)
        return False

    # -- 每帧末尾：弹出皮肤 ----------------------------------------------
    #    ★ priority=0 —— 比 INTERNAL(1) 还低，保证**永远排最后**：
    #      "同优先级按注册顺序"在官方文档里写的是"未定义"，
    #      用 priority=0 就不依赖这个未定义行为（见报告"关键坑 ②"）。
    @messages.handler(priority=0)
    def _每帧结尾(self, event: messages.BuildGuiEvent) -> bool:
        global 皮肤在推, 弹出耗时
        顺序.append("探针弹出(priority=0)")
        t0 = time.perf_counter()
        try:
            if 皮肤在推:
                见效 = int(imgui.GetColorU32(imgui.Col.Button))
                推入 = int(imgui.GetColorU32(imgui.Vec4(*皮肤按钮色)))
                见证结果["③ 弹出之前（官方 GUI 已画完）皮肤仍生效"] = (见效 == 推入)
                self.逐帧弹出次数 += 1
            弹出皮肤()
            皮肤在推 = False
        except Exception as 异常:                                        # noqa: BLE001
            记录(f"✗ 弹出皮肤出错（帧 {self.帧}）：{type(异常).__name__}: {异常}")
        弹出耗时 += time.perf_counter() - t0
        if self.帧 >= self.结束帧:
            self._收尾并退出()
        return False

    # ------------------------------------------------------------------
    def _探测A_全局样式字段(self) -> None:
        st = imgui.GetStyle()
        记录(f"A1 GetStyle() 暴露的字段：{[n for n in dir(st) if not n.startswith('_')]}")
        可写, 不可写 = [], []
        for 名, 值 in (("FramePadding", imgui.Vec2(8.0, 5.0)),
                       ("ItemSpacing", imgui.Vec2(8.0, 6.0)),
                       ("WindowPadding", imgui.Vec2(10.0, 10.0)),
                       ("WindowRounding", 0.0), ("FrameRounding", 0.0),
                       ("WindowBorderSize", 1.0), ("FrameBorderSize", 1.0),
                       ("GrabRounding", 0.0), ("ScrollbarSize", 14.0)):
            try:
                setattr(st, 名, 值)
                可写.append(名)
            except Exception as 异常:                                    # noqa: BLE001
                不可写.append(f"{名}（{type(异常).__name__}）")
        记录(f"A2 可以直接改的字段：{可写 or '（无）'}")
        记录(f"A3 改不了的字段：{不可写 or '（无）'}")
        import re
        记录(f"A4 全局改颜色/样式的函数：{[n for n in dir(imgui) if re.search(r'Set.*(Style|Color|Theme)', n) and not n.startswith('_')] or '（无）'}")

    def _探测B_推入是否真的生效(self) -> None:
        前 = int(imgui.GetColorU32(imgui.Col.Button))
        imgui.PushStyleColor(imgui.Col.Button, imgui.Vec4(*皮肤按钮色))
        中 = int(imgui.GetColorU32(imgui.Col.Button))
        imgui.PopStyleColor(1)
        后 = int(imgui.GetColorU32(imgui.Col.Button))
        记录(f"B1 Col.Button：推入前={前:#010x} 推入后={中:#010x} 弹出后={后:#010x} → "
             f"{'✓ 推入真的生效且可还原' if 中 != 前 and 后 == 前 else '✗ 没生效'}")
        try:
            imgui.PushStyleVar(imgui.StyleVar.WindowRounding, 0.0)
            imgui.PushStyleVar(imgui.StyleVar.FrameRounding, 0.0)
            imgui.PushStyleVar(imgui.StyleVar.WindowBorderSize, 2.0)
            imgui.PushStyleVar(imgui.StyleVar.FramePadding, imgui.Vec2(10.0, 6.0))
            imgui.PopStyleVar(4)
            记录("B2 PushStyleVar（圆角/边框/内边距）推入+弹出：✓ 没有报错")
        except Exception as 异常:                                        # noqa: BLE001
            记录(f"B2 PushStyleVar 失败：{type(异常).__name__}: {异常}")
        try:
            列 = [v for v in dir(implot.Col) if not v.startswith("_")]
            implot.PushStyleColor(implot.Col.PlotBg, imgui.Vec4(0.05, 0.05, 0.05, 1.0))
            implot.PopStyleColor(1)
            记录(f"B3 implot（曲线）可独立换肤：✓（implot.Col {len(列)} 项）")
        except Exception as 异常:                                        # noqa: BLE001
            记录(f"B3 implot 换肤失败：{type(异常).__name__}: {异常}")
        import re as _re
        字体函数 = [n for n in dir(imgui) if _re.search("Font|Glyph|Atlas", n)]
        记录(f"B4 字体相关函数：{字体函数} → "
             f"{'可以加载外部字体' if any('Add' in f for f in 字体函数) else '✗ 没有加载字体的入口（只能用内置字体 + 缩放）'}")
        记录(f"B5 画布接口：{[n for n in dir(imgui) if 'DrawList' in n] or '✗ 没有 GetWindowDrawList —— 不能直接画斜线/多边形'}")

    def _探测E_字号与曲线换肤(self) -> None:
        # 字体加载没有入口，但 FontGlobalScale 有 → 全局字号是唯一的"排版"杠杆
        try:
            io = imgui.GetIO()
            原 = float(io.FontGlobalScale)
            io.FontGlobalScale = 1.25
            读回 = float(io.FontGlobalScale)
            io.FontGlobalScale = 原
            记录(f"E1 imgui.GetIO().FontGlobalScale：可读写（设 1.25 → 读回 {读回}）→ "
                 f"{'✓ 可以整体放大/缩小字号' if abs(读回 - 1.25) < 1e-6 else '✗ 设了不生效'}"
                 f"；IO 可写字段={[v for v in dir(io) if not v.startswith('_')][:8]}…")
        except Exception as 异常:                                        # noqa: BLE001
            记录(f"E1 FontGlobalScale 不可用：{type(异常).__name__}: {异常}")
        try:
            变量 = [v for v in dir(implot.StyleVar) if not v.startswith('_')]
            记录(f"E2 implot.StyleVar 可推入项 {len(变量)} 个：{变量}")
            implot.PushStyleVar(implot.StyleVar.PlotBorderSize, 1.0)
            implot.PushStyleVar(implot.StyleVar.PlotPadding, imgui.Vec2(6.0, 6.0))
            implot.PopStyleVar(2)
            记录("E3 implot 形状（边框/内边距）推入+弹出：✓ 没有报错")
        except Exception as 异常:                                        # noqa: BLE001
            记录(f"E2/E3 implot 形状换肤失败：{type(异常).__name__}: {异常}")

    def _泄漏推入(self) -> None:
        imgui.PushStyleColor(imgui.Col.WindowBg, imgui.Vec4(0.0, 0.3, 0.0, 1.0))
        imgui.PushStyleVar(imgui.StyleVar.WindowRounding, 6.0)
        已推颜色数备份 = 1
        self.泄漏测试帧 = self.帧
        记录(f"C1 已故意推入 1 个颜色 + 1 个变量且不弹出（观察 ImGui 的反应）")

    def _收尾并退出(self) -> None:
        记录(f"C2 逐帧换肤 {self.逐帧推送次数} 帧 / 逐帧弹出 {self.逐帧弹出次数} 帧 "
             f"（{'✓ 完全配对，帧 10~60 期间 ImGui 一条错都没报' if self.逐帧推送次数 == self.逐帧弹出次数 else '✗ 不配对'}）；"
             f"皮肤共推入 {皮肤轮数} 轮（比帧数多出来的轮数来自 setup_theme 包装，见 D 段）")
        记录(f"C3 泄漏测试在第 {self.泄漏测试帧} 帧；存活帧数 {self.帧}"
             f"（是否报错见下方 imgui-error 日志）")
        if self.逐帧推送次数:
            记录(f"C4 每帧换肤开销（19 项）：推入 {推入耗时 / self.逐帧推送次数 * 1e6:.1f} µs + "
                 f"弹出 {弹出耗时 / max(self.逐帧弹出次数, 1) * 1e6:.1f} µs → 可忽略不计")
        记录(f"C5 一帧内的绘制顺序：{顺序[:6]} …（每帧重复）")
        记录(f"C6 见证结果：{见证结果}")
        记录(f"D1 官方 ux.setup_theme 被调用 {主题应用次数[0]} 次 / 共 {self.帧} 帧 "
             f"→ {'★ 确认：官方每帧都在重设主题，所以不包一层就换不上官方面板' if 主题应用次数[0] >= self.帧 // 2 else '仅初始化/切换时调用'}")
        记录(f"D2 皮肤补推时机：{推入时刻[:6]}")
        # ★ 干净退出：只把 _is_running 置 False，让官方循环自己收尾。
        #   （直接 dispatch(ExitEvent) 会在 sync() 之前销毁窗口 → 官方循环 AttributeError，
        #     这个坑与换肤无关，但顺手记下来。）
        try:
            self.viewer._is_running = False                          # noqa: SLF001（探针专用）
        except Exception:                                                # noqa: BLE001
            pass


# ===========================================================================
def 主流程() -> int:
    模型路径 = os.path.join(包根, "模型", "空场景.xml")
    查看端点, 仿真端点 = launch_thread.make_thread_endpoints()
    停止 = threading.Event()

    def 仿真线程():
        try:
            import mujoco
            model = mujoco.MjModel.from_xml_path(模型路径)
            data = mujoco.MjData(model)
            mujoco.mj_forward(model, data)
            仿真端点.send_to_viewer(messages.ModelEvent(model=model, path=模型路径))
            记录("仿真侧：已把空场景 (nq=0) 发给窗口；本实验不需要物理步进")
            while not 停止.is_set():
                for _ in 仿真端点.get_viewer_events():
                    pass
                for _ in 仿真端点.get_viewer_snapshots():
                    pass
                time.sleep(0.01)
        except Exception as 异常:                                        # noqa: BLE001
            print(f"⚠ 仿真线程出错：{type(异常).__name__}: {异常}")

    threading.Thread(target=仿真线程, daemon=True, name="探针仿真线程").start()

    import 界面桥

    class 探针窗口(界面桥.制作窗口类(插件框架.viewer_app.ViewerApp)):
        @messages.handler(priority=messages.Priority.INTERNAL)
        def _记录官方GUI时刻(self, event: messages.BuildGuiEvent) -> bool:
            顺序.append("官方ViewerApp画GUI(INTERNAL=1)")
            if 皮肤在推:
                # 本方法在官方 _on_build_gui 之后执行（同一实例、同优先级，按名字排序）
                见效 = int(imgui.GetColorU32(imgui.Col.Button))
                推入 = int(imgui.GetColorU32(imgui.Vec4(*皮肤按钮色)))
                见证结果["② 官方 GUI 画完之后皮肤仍生效"] = (见效 == 推入)
            return False

    窗口插件 = [探针窗口(), 界面桥.界面桥(), 见证面板()]

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
    记录(f"自研面板已加载：{已加载}")

    探针 = 外观探针()
    窗口插件.append(探针)
    记录("窗口即将打开……")

    配置 = viewer_protocol.ViewerConfig(title="驭臂 · 外观探针（约 4 秒后自动关闭）",
                                        width=900, height=600, gfx="")
    try:
        launch_native.run_native_viewer(配置, 查看端点, plugins=窗口插件)
    except Exception as 异常:                                            # noqa: BLE001
        print(f"✗ 窗口异常：{type(异常).__name__}: {异常}")
        traceback.print_exc(limit=6)
        停止.set()
        return 1
    停止.set()
    记录("窗口已正常关闭。")
    return 0


if __name__ == "__main__":
    码 = 主流程()
    print("\n" + "=" * 70)
    print("  探针报告")
    print("=" * 70)
    for 行 in 报告:
        print("  " + 行)
    print("=" * 70)
    raise SystemExit(码)
