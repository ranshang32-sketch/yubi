"""
面板/辨识面板.py —— 参数辨识界面（第 4 步 D3 界面化）

三个按钮，一条流程：
    ① Excitation sample  —— 在当前模型上做一段闭环激励，记录数据
    ② Identify           —— 后台跑辨识（界面不卡，进度实时更新）
    ③ 结果表             —— 标称值 → 估计值，以及"拟合残差改善多少倍"

★ 结果怎么看（这决定了你会不会被误导）：
    我们能对照的只有"贡献模型的响应"，不是真机。所以：
      · **拟合残差显著下降** → 这组参数更贴合这段数据（可信）
      · **估计值离标称值多远** → 只说明"标称值和这段数据不一致"，不代表标称值错
    真正证明"能把真值找回来"的，是离线闭环实验 `验证参数辨识.py`
    （造已知真值 2.5/10.0/1.5 → 辨识 → 误差 1.47%）。

为什么只辨识质量：
    实测质心位置在这类轨迹上**不可辨识**（估计值基本不动），
    所以默认只放 3 个连杆质量，避免出现"看起来跑了但其实没收敛"的参数。
"""
from __future__ import annotations

import os as _os
import sys as _sys

_外壳目录 = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _外壳目录 not in _sys.path:
    _sys.path.insert(0, _外壳目录)

from mujoco.experimental.dear_imgui import dear_imgui as imgui       # noqa: E402
from mujoco.experimental.studio import messages, viewer_protocol      # noqa: E402
from 辨识桥 import 辨识命令, 辨识状态                                  # noqa: E402

import 文案
import 面板注册表
import 界面文字                                                      # noqa: E402


class 辨识面板:
    """参数辨识的界面：发命令、显示状态与结果。"""

    面板显示名 = "参数辨识"
    页签名 = "System identification"

    def __init__(self):
        self.viewer = None
        self.可见 = True
        self.状态 = 辨识状态()
        self._已打日志: set[str] = set()
        self.采样时长 = 1.0
        self.发出命令 = 0
        self.上次动作 = ""
        self.收帧 = 0
        self.绘制次数 = 0
        self.错误次数 = 0

    # ------------------------------------------------------------------
    @messages.handler(priority=messages.Priority.CRITICAL)
    def 记下窗口(self, event: viewer_protocol.ViewerInitEvent) -> bool:
        self.viewer = event.viewer
        return False

    @messages.handler
    def 收状态(self, 消息: 辨识状态) -> bool:
        self.收帧 += 1
        self.状态 = 消息
        return False

    def _画日志(self) -> None:
        """画辨识日志。

        ★ 日志行是仿真侧拼的中文句子，而官方 UI 字体没有中文字形（画出来是 ?）。
          所以：能画成 ASCII 的就直接画；画不出来的**原样打到终端一次**（终端中文正常），
          面板上只留一个计数占位 —— 信息不丢，观感也不脏。
        """
        隐藏 = 0
        for 行 in reversed(self.状态.日志):
            文本 = str(行)[:96]
            if 界面文字.可用(文本):
                imgui.TextDisabled("  " + 文本)
                continue
            隐藏 += 1
            if 文本 not in self._已打日志:
                self._已打日志.add(文本)
                print(f"【辨识】{文本}", flush=True)
        if 隐藏:
            imgui.TextDisabled(文案.格式化("辨识.隐藏日志",
                                                  "  (+{n} non-ASCII log line(s) - shown in terminal)",
                                                  n=隐藏))

    def _发命令(self, 动作: str) -> None:
        self.上次动作 = 动作
        self.发出命令 += 1
        if self.viewer is None:
            return
        try:
            self.viewer.send_to_sim(辨识命令(动作=动作, 时长=float(self.采样时长)))
        except Exception as 异常:                                       # noqa: BLE001
            print(f"⚠ 辨识命令发送失败：{异常}")

    # ------------------------------------------------------------------
    @messages.handler
    def 画面板(self, event: messages.BuildGuiEvent) -> bool:
        # ★ 必须在"可见性检查"之前：即使本面板被收进容器/关掉，也要能响应 F9 恢复
        面板注册表.每帧(self)
        if not self.可见:
            return False
        if 面板注册表.画在容器里(self):
            return False
        self.绘制次数 += 1
        # ★ 第二项传 self.可见（= ImGui 的 p_open）：传了它右上角才有 × 关闭按钮。
        #   原来传 None → ImGui 不画关闭按钮 → 窗口关不掉。
        展开, self.可见 = imgui.Begin(文案.取("辨识.标题"), self.可见, 0)
        面板注册表.记录(self)
        try:
            if not 展开:
                return False
            self._画内容()
        except Exception as 异常:                                        # noqa: BLE001
            self.错误次数 += 1
            if self.错误次数 <= 2:
                print(f"⚠ 辨识面板绘制出错：{type(异常).__name__}: {异常}")
        finally:
            imgui.End()
        return False

    def _画内容(self) -> None:
        # 容器把本面板画在页签里时，容器负责跳过"没打开的页签"；这里再挡一道
        if not self.可见:
            return
        self.绘制次数 += 1
        忙 = self.状态.状态 != "空闲"

        # ---- 按钮行 ----
        if 忙:
            imgui.BeginDisabled()
        if imgui.Button(文案.取("辨识.第一步")):
            self._发命令("采样")
        imgui.SameLine()
        if imgui.Button(文案.取("辨识.第二步")):
            self._发命令("辨识")
        if 忙:
            imgui.EndDisabled()
        imgui.SameLine()
        imgui.SetNextItemWidth(90.0)
        _, self.采样时长 = imgui.SliderFloat(文案.取("辨识.采样时长"), float(self.采样时长), 0.5, 3.0)

        # ---- 状态行 ----
        if 忙:
            imgui.TextColored(imgui.Vec4(0.95, 0.80, 0.25, 1.0),
                              f"{界面文字.英文(self.状态.状态)}: "
                              f"{界面文字.英文(self.状态.进度)}")
        else:
            imgui.TextDisabled(文案.格式化("辨识.空闲状态",
                                                   "idle   sampled steps={步数}",
                                                   步数=self.状态.采样步数)
                               + (f"   last={self.上次动作}" if self.上次动作 else ""))

        # ---- 结果表 ----
        if self.状态.结果:
            imgui.Separator()
            imgui.Text(文案.取("辨识.结果表头"))
            for 名, 标称, 估, 误 in self.状态.结果:
                imgui.BulletText(f"{名}:  {标称:.4g} -> {估:.4g}   ({误:+.1f}%)")

        # ---- 拟合残差（判断"是否更贴合数据"的唯一可信指标）----
        拟合 = self.状态.拟合 or {}
        if 拟合.get("标称") is not None and 拟合.get("辨识后") is not None:
            改善 = 拟合["标称"] / max(拟合["辨识后"], 1e-12)
            imgui.Separator()
            imgui.Text(文案.格式化("辨识.拟合行",
                                              "Fit residual:  {前:.6f} -> {后:.6f}",
                                              前=拟合["标称"], 后=拟合["辨识后"]))
            imgui.SameLine()
            imgui.TextColored(imgui.Vec4(0.30, 0.85, 0.40, 1.0) if 改善 > 1.5
                              else imgui.Vec4(0.95, 0.45, 0.30, 1.0),
                              文案.格式化("辨识.改善", "({倍:.1f}x better)", 倍=改善))
            imgui.TextDisabled(文案.取("辨识.残差说明一"))
            imgui.TextDisabled(文案.取("辨识.残差说明二"))

        # ---- 日志 ----
        if self.状态.日志:
            imgui.Separator()
            imgui.TextDisabled(文案.取("辨识.日志"))
            self._画日志()

        imgui.Separator()
        imgui.TextDisabled(文案.格式化("辨识.统计行",
                                           "frames={帧}  cmds={命令}  draw={画}",
                                           帧=self.收帧, 命令=self.发出命令,
                                           画=self.绘制次数))


# 启动器约定：模块里叫"面板类"的就是要实例化的面板
面板类 = 辨识面板
