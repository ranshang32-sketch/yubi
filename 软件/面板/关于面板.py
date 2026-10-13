"""
面板/关于面板.py —— 关于页面（第 5 步收尾）

它显示什么：
    · 软件名与版本、构建日期
    · 运行时信息（mujoco 版本、Python 版本）
    · 已加载的插件清单（谁在控制这台机器人）
    · 当前模型
    · **合规声明**（这是必写的，见下）

为什么必须有关闭声明：
    MuJoCo 的许可证是 Apache-2.0，第 6 条明确**不授予商标权**：
    可以用它的代码、改它的代码、闭源卖钱，但不能让人以为你是官方。
    所以软件名里不能出现 "MuJoCo"，并且要在"关于"里写明与 Google DeepMind 无关联。
    这条在第 0 步的调研报告（2.6 节）里就确认过，这里是落地。
"""
from __future__ import annotations

import os as _os
import sys as _sys
import time

_外壳目录 = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _外壳目录 not in _sys.path:
    _sys.path.insert(0, _外壳目录)

from mujoco.experimental.dear_imgui import dear_imgui as imgui       # noqa: E402
from mujoco.experimental.studio import messages                       # noqa: E402

import 文案
import 面板注册表                                                      # noqa: E402
import 界面文字                                                        # noqa: E402

# 软件版本（改了这里就相当于发新版本；.app 的 Info.plist 里也有一个版本号，两处一起改）
#
# ★ 名字分成两个是有原因的（踩过）：面板上**只能画 ASCII** ——
#   官方 UI 字体没有中文字形，ImGui 遇到缺字形会回退画 `?`。
#   本文件原来只有 `软件名 = "数字样机 Studio"`，画在面板上时经 界面文字.英文() 剥成 ASCII，
#   结果**只剩一个 "Studio"**（中文全被剥掉），既看不出软件名、也让人以为渲染坏了。
#   所以：`软件名` 给终端/元信息用（可以中文），`软件名英文` 给面板用（必须 ASCII）。
软件名 = "小软件"
软件名英文 = "XiaoRuanJian  Studio"
版本 = "0.4.1"
构建日期 = "2026-09-23"


class 关于面板:
    """显示软件信息与合规声明。信息由外壳在启动时填进来。"""

    面板显示名 = "关于"
    页签名 = "About"

    def __init__(self):
        self.可见 = True
        self.插件清单: list[tuple[str, str]] = []      # [(名称, 版本)]
        self.模型 = ""
        self.面板清单: list[str] = []
        self.绘制次数 = 0
        self.命令次数 = 0

    # ------------------------------------------------------------------
    def 设置信息(self, 插件清单, 模型: str, 面板清单) -> "关于面板":
        self.插件清单 = [(str(getattr(p, "名称", type(p).__name__)),
                          str(getattr(p, "版本", "-"))) for p in 插件清单]
        self.模型 = 模型
        self.面板清单 = list(面板清单)
        return self

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
        展开, self.可见 = imgui.Begin(文案.取("关于.标题"), self.可见, 0)
        面板注册表.记录(self)
        try:
            if not 展开:
                return False
            self._画内容()
        except Exception as 异常:                                        # noqa: BLE001
            if self.绘制次数 <= 2:
                print(f"⚠ 关于面板绘制出错：{type(异常).__name__}: {异常}")
        finally:
            imgui.End()
        return False

    def _画内容(self) -> None:
        # 容器把本面板画在页签里时，容器负责跳过"没打开的页签"；这里再挡一道
        if not self.可见:
            return
        self.绘制次数 += 1
        from mujoco.experimental.dear_imgui import dear_imgui as ig
        import mujoco
        import platform

        高亮 = ig.Vec4(0.30, 0.76, 1.00, 1.0)
        暗 = ig.Vec4(0.65, 0.68, 0.72, 1.0)

        # 面板上优先用英文名（见文件上方说明：中文会被剥成空串或只剩 "Studio"）
        ig.TextColored(高亮, f"{软件名英文 or 软件名}")
        ig.TextDisabled(f"version {版本}   built {构建日期}")
        ig.Separator()

        ig.Text(文案.取("关于.运行环境"))
        ig.BulletText(f"MuJoCo {getattr(mujoco, '__version__', '?')}")
        ig.BulletText(f"Python {platform.python_version()} ({platform.machine()})")
        ig.BulletText(f文案.取("关于.后端"))
        ig.Separator()

        ig.Text(文案.取("关于.已加载算法"))
        if self.插件清单:
            for 名, 版 in self.插件清单:
                ig.BulletText(f"{名}  v{版}")
        else:
            ig.TextDisabled(文案.取("关于.无算法"))
        ig.Separator()

        ig.Text(文案.取("关于.面板"))
        ig.TextDisabled("  " + (", ".join(self.面板清单) if self.面板清单 else "(none)"))
        ig.Separator()

        ig.Text(文案.取("关于.模型"))
        ig.TextDisabled(f"  {_os.path.basename(self.模型) if self.模型 else '?'}")

        ig.Separator()
        ig.TextColored(暗, 文案.取("关于.声明"))
        ig.TextWrapped(文案.取("关于.声明一"))
        ig.TextWrapped(文案.取("关于.声明二"))
        ig.TextWrapped(文案.取("关于.声明三"))
        ig.Separator()
        ig.TextDisabled(f"drawn {self.绘制次数} times")


# 启动器约定：模块里叫"面板类"的就是要实例化的面板
面板类 = 关于面板
