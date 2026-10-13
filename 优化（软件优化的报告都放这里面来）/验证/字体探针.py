"""
字体探针.py —— 判定"换掉 assets 里的 .ttf 能不能让面板显示中文"

为什么要单独做这个判定：
    官方 UI 字体 Atkinson Hyperlegible 没有任何中文字形，ImGui 缺字形时回退画
    `ImFont::FallbackChar`（默认 '?'）→ 面板上就是一串问号。
    `界面文字.py` 里写的结论是"这个 Python 绑定没有任何字体接口，所以要 CJK 只能在
    C++ 里 AddFontFromFileTTF" —— 那句话对"运行时注入"成立，但漏了一条路：
    **字体是按文件名从 assets/ 加载的，换文件不用碰二进制。**

    这条路能不能成，取决于官方后端用的是哪一代字体图集：
      · 新式（ImGui 1.92+ 动态图集，RendererHasTextures）→ 用到哪个码位现烘焙哪个
        → 只要文件里有汉字字形，就能显示 ★
      · 旧式（预烘焙 + GetGlyphRangesDefault）→ 只烘焙拉丁范围 → 换文件也没用
    只看二进制里的字符串分不出来，所以必须实测。

怎么判定（不靠肉眼）：
    用 `imgui.CalcTextSize()` 量宽度。缺字形时 ImGui 返回**回退字形（'?'）的 advance**，
    所以：
        CalcTextSize("中").x == CalcTextSize("?").x   → 缺字形（判定失败）
        CalcTextSize("中").x ≈ GetFontSize()          → 有汉字字形（判定成功，全角≈字号）
    同一帧里连量多帧，取最后一帧（动态图集可能第一帧还没烘好）。

跑法（会在屏幕上开一个 900x600 的窗口，约 1 秒后自己关掉）：
    .venv/bin/python 优化（软件优化的报告都放这里面来）/验证/字体探针.py
    .venv/bin/python 优化（软件优化的报告都放这里面来）/验证/字体探针.py --秒 8   # 停留 8 秒，肉眼看看
    # 输出同时写入 优化（...）/验证/字体探针_输出.txt，测量值写入 字体探针_测量.json
"""
from __future__ import annotations

import os
import sys
import threading
import time
import traceback

# ---- 路径：本文件在 <包根>/优化（...）/验证/ 下 ----
本目录 = os.path.dirname(os.path.abspath(__file__))
包根 = os.path.dirname(os.path.dirname(本目录))
软件目录 = os.path.join(包根, "软件")
for p in (软件目录, os.path.join(软件目录, "面板")):
    if p not in sys.path:
        sys.path.insert(0, p)

import 插件系统 as 插件框架                                              # noqa: E402
from mujoco.experimental.dear_imgui import dear_imgui as imgui           # noqa: E402
from mujoco.experimental.studio import (launch_native, launch_thread,    # noqa: E402
                                        messages, viewer_protocol)

报告: list[str] = []
测量历史: list[dict] = []
结束帧 = 40                      # 跑约 40 帧（~1 秒）后自己关窗；`--秒 N` 可以待久一点

# `--秒 8` → 窗口停留约 8 秒，方便肉眼看看面板上的汉字到底画出来没有
for _i, _a in enumerate(sys.argv):
    if _a in ("--秒", "--seconds") and _i + 1 < len(sys.argv):
        try:
            结束帧 = max(10, int(float(sys.argv[_i + 1]) * 60))
        except ValueError:
            pass

# 取样字符：'?' 是回退字形；'A' 是确定存在的拉丁；'中/文/汉/字' 是待测汉字
取样 = {
    "?": "?",
    "A": "A",
    "·": "·",                    # Atkinson 确实有的非 ASCII 符号（对照组）
    "中": "中",
    "文": "文",
    "汉": "汉",
    "字": "字",
    "中文汉字": "中文汉字",
    "驭臂": "驭臂",
    # 补丁顺带加进来的符号（原本 Atkinson 也没有 → 原版应等于回退宽度）
    "←": "←",
    "→": "→",
    "○": "○",
    "●": "●",
    "「": "「",
    "，": "，",
}

# ★ 拉丁基准样本：合并字体若是"Atkinson 拉丁 + 汉字补充"，这些宽度必须与原始字体**逐位相同**。
#   用它来证明"补汉字没有改坏拉丁观感"——比肉眼看截图更硬。
拉丁样本 = {
    "拉丁_句子": "The quick brown fox jumps over the lazy dog",
    "拉丁_数字": "0123456789 ()[]{}:;.,%-+/=<>",
    "拉丁_标题": "Model library / Appearance / Controller params",
    "拉丁_大小写": "ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz",
    "拉丁_常用符号": "·…±°",
}


def 记录(行: str) -> None:
    print(行, flush=True)
    报告.append(行)


class 字体探针面板:
    """唯一的探针：每帧量一次字符宽度，画一个窗口把汉字显示出来。"""

    def __init__(self) -> None:
        self.viewer = None
        self.帧 = 0

    @messages.handler(priority=messages.Priority.CRITICAL)
    def _记下viewer(self, event: viewer_protocol.ViewerInitEvent) -> bool:
        self.viewer = event.viewer
        return False

    @messages.handler
    def 画(self, event: messages.BuildGuiEvent) -> bool:
        self.帧 += 1
        try:
            字号 = float(imgui.GetFontSize())
            量 = {名: float(imgui.CalcTextSize(文本).x) for 名, 文本 in 取样.items()}
            拉丁 = {名: float(imgui.CalcTextSize(文本).x) for 名, 文本 in 拉丁样本.items()}
            测量历史.append({"帧": self.帧, "字号": 字号, **量, **拉丁})
        except Exception as 异常:                                        # noqa: BLE001
            记录(f"⚠ 第 {self.帧} 帧测量失败：{type(异常).__name__}: {异常}")
            return False

        # 把汉字真的画出来（给"肉眼复核"留一条路；判定本身不依赖它）
        try:
            imgui.SetNextWindowSize(imgui.Vec2(520.0, 260.0), imgui.Cond.FirstUseEver.value)
            开, _ = imgui.Begin("Font probe — 中文字体探针", True, 0)
            if 开:
                imgui.Text("ASCII : The quick brown fox jumps over the lazy dog 0123")
                imgui.Text("CJK   : 中文汉字 / 驭臂 / 关节 PD 位置控制 / 参数辨识 / 数据录制")
                imgui.Text("判断  : 上面这行如果是一串问号，说明字体没有汉字字形")
                imgui.Text("符号  : ← → ○ ● 「」【】（） ，。：；")
                imgui.Text(f"宽度  : w('?')={量['?']:.2f}  w('中')={量['中']:.2f}  "
                           f"w('←')={量['←']:.2f}  font={字号:.2f}")
                imgui.Text("说明  : w('中') 等于 w('?') → 缺字形；明显更大 → 有汉字字形")
            imgui.End()
        except Exception:                                                # noqa: BLE001
            pass

        if self.帧 >= 结束帧:
            self._出报告()
            try:
                self.viewer._is_running = False                          # noqa: SLF001（探针专用）
            except Exception:                                            # noqa: BLE001
                pass
        return False

    def _出报告(self) -> None:
        if not 测量历史:
            记录("✗ 一帧都没量到")
            return
        首, 末 = 测量历史[0], 测量历史[-1]
        记录("")
        记录("=" * 70)
        记录("  字体探针报告")
        记录("=" * 70)
        记录(f"  帧数 {len(测量历史)}｜最后一帧（动态图集可能首帧还没烘好，所以看末帧）")
        记录("")
        记录(f"  GetFontSize()        = {末['字号']:.2f}")
        for 名 in 取样:
            记录(f"  CalcTextSize({名!r:<10}).x = {末[名]:.2f}"
                 + (f"     （首帧 {首[名]:.2f}）" if abs(首[名] - 末[名]) > 1e-6 else ""))
        记录("")

        # ---- 判定 ----
        宽问号, 宽中, 宽字号 = 末["?"], 末["中"], 末["字号"]
        if 宽问号 <= 0:
            记录("  ⚠ '?' 宽度为 0，测量不可信")
            return
        比值 = 宽中 / 宽问号
        记录(f"  判据：w('中') / w('?') = {宽中:.2f} / {宽问号:.2f} = {比值:.2f}")
        记录(f"        全角汉字应 ≈ GetFontSize() = {宽字号:.2f}")
        记录("")
        if 比值 > 1.15:
            记录("  ✓ 判定：**面板已经能拿到汉字字形** —— 动态字体图集成立，换 .ttf 这条路通")
            记录(f"     （'中' 宽 {宽中:.2f} 明显不同于回退字形 '?' 的 {宽问号:.2f}）")
        else:
            记录("  ✗ 判定：汉字仍在走回退字形（宽度等于 '?'）—— 官方走后端不支持"
                 "RendererHasTextures 的旧式预烘焙路径，换 .ttf 无效")
            记录("     下一步：只能走「显示层全英文」或改自编 imgui，不要再在字体上投入")
        # 顺带核对拉丁与已知符号没被换坏
        记录("")
        记录(f"  对照：w('A')={末['A']:.2f}（拉丁应正常）、w('·')={末['·']:.2f}（Atkinson 本来就有）")
        记录("")
        记录("  ── 拉丁基准（用于比对『合并字体没改坏拉丁观感』）──")
        for 名 in 拉丁样本:
            记录(f"    {名:<14}= {末[名]:.2f}")
        记录("=" * 70)
        # 机器可读：给 工具/打补丁_中文字体.py 的验收做逐位比对
        try:
            import json
            路径 = os.path.join(本目录, "字体探针_测量.json")
            with open(路径, "w", encoding="utf-8") as f:
                json.dump({"字号": 末["字号"],
                           "取样": {k: 末[k] for k in 取样},
                           "拉丁样本": {k: 末[k] for k in 拉丁样本}},
                          f, ensure_ascii=False, indent=2)
        except Exception as 异常:                                        # noqa: BLE001
            记录(f"⚠ 写 JSON 失败：{异常}")


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
            while not 停止.is_set():
                for _ in 仿真端点.get_viewer_events():
                    pass
                for _ in 仿真端点.get_viewer_snapshots():
                    pass
                time.sleep(0.01)
        except Exception as 异常:                                        # noqa: BLE001
            print(f"⚠ 仿真线程出错：{type(异常).__name__}: {异常}", flush=True)

    threading.Thread(target=仿真线程, daemon=True, name="字体探针仿真线程").start()

    import 界面桥

    窗口插件 = [界面桥.界面桥(), 字体探针面板()]

    配置 = viewer_protocol.ViewerConfig(title="字体探针（约 1 秒后自动关闭）",
                                        width=900, height=600, gfx="")
    try:
        launch_native.run_native_viewer(配置, 查看端点, plugins=窗口插件)
    except Exception as 异常:                                            # noqa: BLE001
        print(f"✗ 窗口异常：{type(异常).__name__}: {异常}", flush=True)
        traceback.print_exc(limit=6)
        停止.set()
        return 1
    停止.set()
    return 0


if __name__ == "__main__":
    码 = 主流程()
    输出路径 = os.path.join(本目录, "字体探针_输出.txt")
    with open(输出路径, "w", encoding="utf-8") as f:
        f.write("\n".join(报告) + "\n")
    print(f"\n（已写入 {输出路径}）")
    raise SystemExit(码)
