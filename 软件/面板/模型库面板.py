"""
面板/模型库面板.py —— 模型库 / 切换机械臂 / 显示当前项目（方案 C 的界面）

它解决什么问题：
    以前一打开软件就直接加载 UR5e，用户没得选。现在启动是**空场景**，
    这个面板负责"选一台机械臂 / 换一台 / 从本地导入"。

★ 方案 C 之后它还负责显示**当前项目与算法列表**：
    点一个模型不只是换物理对象，还会按"哪个项目用了这个模型"把控制算法
    **整组换掉**（规则见 软件/项目.py，执行点见 软件/启动.py 的 `_装配项目()`）。
    所以面板上要多两行：
        Project: UR5e_基础PD
        Algorithms (5): 关节 PD 位置控制 v1.1 | 参数辨识 v1.1 | ...
    没有这两行，用户会疑惑"我点了 xArm7，怎么算法变了"，或者反过来"怎么没变"。
    数据来自仿真侧发的 `项目状态`（见 模型桥.py）；装配完成时**立刻**发一条，
    所以点下去马上就能看到更新，不用等 2 秒的节拍。

★ 它住在【侧栏】左栏的第一格（见 面板/侧栏.py），是"固定面板"而不是会消失的浮窗：
    ① 位置由侧栏统一算（贴在 3D 区左内侧），点标签即从边上抽出
    ② **不可关闭**（类属性 `不可关闭 = True`）：它是选机械臂的**唯一入口**，
       被关掉就麻烦了 —— 实测踩过：用户点了 × 之后每次启动都不显示，只能按 F9 找回来。
       （侧栏托管时开关由侧栏管；只有侧栏整个不可用、它自己开窗口时才用得上这条。）
    ③ 每次启动**必定出现**。

★ 为什么没有"停靠进官方左侧 Options 栏"（**已证伪，别再试**）：
    2026-10-06 用 9 组现场实验把这条路走死了 —— 切在官方之前/之后、
    `DockBuilderFinish` 调/不调、往 `~/.mujoco.ini` 里写 `DockId`、直接塞官方已有节点
    `0x06`/`0x08`、整套 `RemoveNode→AddNode→切片→Finish` 重建：结论一致，
    **`DockId` 记得住，但 ImGui 永不真的启用停靠**；手写 ini 造出的空节点会被剪掉；
    整套重建的版面**下一帧就被官方抢回去**（终局树只剩官方自己的 1/2/3/4）。
    完整实验记录：`优化（软件优化的报告都放这里面来）/报告/界面侧栏改造_设计规格.md` §1.2。
    所以现在是【侧栏】：纯窗口定位，收起态只占两侧各 26px、3D 视口一格不占。

界面上有什么：
    当前模型 + 状态 | 机械臂列表（点一下即切换，当前项打 ●）
    [从本地导入模型…]（macOS 原生文件选择器，后台线程不冻界面）  [空场景]  [重新加载当前]  [刷新列表]
    一个手输路径的输入框（给"路径不在模型库里"的场合兜底）

数据从哪来：
    · 列表：直接读 `模型/模型库.json`（由 工具/导入模型.py 生成），不占消息通道
    · 当前模型与状态：仿真侧每 2 Hz 发一条 `模型状态`（见 模型桥.py）

切换怎么走：
    面板 →（`换模型命令`）→ 仿真侧 `模型应用器` → 外壳真正加载并重绑 model/data
    →（`ModelEvent`）→ 窗口侧画面换掉。详见 模型桥.py 与 启动.py 的说明。

★ 也可以不用这个面板：官方 Studio 内建了"把 .xml 文件拖进窗口"的能力，
  拖拽那条路同样会被仿真侧的 `模型应用器` 接住（见 模型桥.py）。

★ 面板上的文字**只能是 ASCII**：官方 UI 字体（Atkinson Hyperlegible）没有中文字形，
  也没装 ● ○ ✓ ✗ （） 这些符号，ImGui 遇到缺字形会回退画 `?`（就是"弹窗里很多问号"）。
  所以这里：按钮/标签用英文，状态用 [ok]/[fail]/[..] 这类 ASCII 标记，
  中文的状态原文与路径留给终端（终端用系统字体，中文正常）。
  校验：./.venv/bin/python 优化（软件优化的报告都放这里面来）/验证/字体覆盖.py
"""
from __future__ import annotations

import os as _os
import sys as _sys

_外壳目录 = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _外壳目录 not in _sys.path:
    _sys.path.insert(0, _外壳目录)

from mujoco.experimental.dear_imgui import dear_imgui as imgui       # noqa: E402
from mujoco.experimental.studio import messages, viewer_protocol      # noqa: E402

import 模型桥                                                        # noqa: E402
from 模型桥 import (换模型命令, 模型状态, 项目状态, 读取模型库,      # noqa: E402
                    后台选择器, 空场景路径, 绝对路径, 模型目录)

import 文案
import 面板注册表                                                      # noqa: E402
import 界面文字                                                        # noqa: E402

# 配色（TextColored 只吃 Vec4 对象，传元组会报 "incompatible function calls"）
绿 = lambda: imgui.Vec4(0.30, 0.85, 0.40, 1.0)
橙 = lambda: imgui.Vec4(0.95, 0.45, 0.30, 1.0)
黄 = lambda: imgui.Vec4(0.95, 0.80, 0.25, 1.0)
灰 = lambda: imgui.Vec4(0.65, 0.68, 0.72, 1.0)

# 官方停靠栏的名字（Options / Inspector）曾经在这里，用来试着把面板停靠进去。
# ★ 2026-10-06 已证伪并删除：见 类文档 与 面板注册表.py 文件头的【坑 ③】。


class 模型库面板:
    """窗口侧插件：列出模型库、发换模型命令、显示当前模型。

    ★ 它现在住在【侧栏】左栏的第一格（见 面板/侧栏.py）：
      所以"固定在左上角 + 不可关闭"这两条只在**侧栏整个不可用**、它自己开窗口时才生效。
      在侧栏里它由侧栏统一管开关 —— 面板列表里它不会被误关，
      而"选机械臂"这个唯一入口也永远不会丢（实在找不到还有 F9 与菜单 Panels）。
    """

    面板显示名 = "模型库"
    页签名 = "Model library"

    # ★ 不可关闭：它是选机械臂的唯一入口（细节见 面板注册表.每帧 的说明）
    #   只有它自己开窗口时才有意义（侧栏托管时开关由侧栏管）。
    不可关闭 = True

    def __init__(self):
        self.viewer = None
        self.可见 = True
        self.模型列表: list[dict] = []
        self.当前路径 = ""
        self.当前显示名 = "（未知）"
        self.状态 = "等待仿真侧…"
        self.自由度 = 0
        self.收帧 = 0
        self.切换次数 = 0
        self.绘制次数 = 0
        self.错误次数 = 0
        self.手动路径 = ""
        # ---- 方案 C：当前项目与这一组装了哪些算法（由 项目状态 消息填）----
        self.当前项目 = ""
        self.算法列表: list[dict] = []
        self.装配报告: list[str] = []
        # 文件选择器跑在后台线程：直接调用会阻塞窗口线程、把 3D 视图冻住
        self.选择器 = 后台选择器()
        self._刷新列表()

    def _刷新列表(self) -> None:
        self.模型列表 = 读取模型库(只取机械臂=True)

    # ------------------------------------------------------------------
    # ★ 这里原来有一段"先试着停靠进官方 Options / Inspector，做不到就固定在左上角"的代码。
    #   2026-10-06 已经用 9 组实验证明**停靠这条路走不通**（DockId 记得住，但 ImGui
    #   永不真的启用停靠；手写 ini 造的节点会被剪掉；整套重建的版面下一帧被官方抢回去）。
    #   证据见 优化（软件优化的报告都放这里面来）/报告/界面侧栏改造_设计规格.md §1.2。
    #   现在本面板住在【侧栏】左栏第一格（面板/侧栏.py），位置由侧栏统一算，不再自己摆放。
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    @messages.handler(priority=messages.Priority.CRITICAL)
    def 记下窗口(self, event: viewer_protocol.ViewerInitEvent) -> bool:
        self.viewer = event.viewer
        return False

    @messages.handler
    def 收状态(self, 消息: 模型状态) -> bool:
        self.收帧 += 1
        self.当前路径 = getattr(消息, "当前路径", "") or ""
        self.当前显示名 = getattr(消息, "当前显示名", "") or "（未知）"
        self.状态 = getattr(消息, "状态", "") or "就绪"
        self.自由度 = int(getattr(消息, "自由度", 0) or 0)
        return False

    @messages.handler
    def 收项目状态(self, 消息: 项目状态) -> bool:
        """仿真侧告诉我们"现在是哪个项目、挂了哪些算法"。

        ★ 这就是"点模型 → 界面上算法列表自动更新"的落地点：
          装配完成时仿真侧会主动发一条，所以这里收到的就是最新的一组。
        """
        self.当前项目 = str(getattr(消息, "项目", "") or "")
        self.算法列表 = list(getattr(消息, "算法", None) or [])
        self.装配报告 = list(getattr(消息, "报告", None) or [])
        return False

    # ------------------------------------------------------------------
    def _发命令(self, 路径: str, 显示名: str = "") -> None:
        if self.viewer is None or not 路径:
            return
        try:
            self.viewer.send_to_sim(换模型命令(路径=路径, 显示名=显示名))
            self.切换次数 += 1
            self.状态 = f"正在加载 {显示名 or _os.path.basename(路径)} …"
        except Exception as 异常:                                       # noqa: BLE001
            print(f"⚠ 换模型命令发送失败：{异常}")

    # ------------------------------------------------------------------
    @messages.handler
    def 画面板(self, event: messages.BuildGuiEvent) -> bool:
        # ★ 必须在"可见性检查"之前：即使本面板归侧栏管，也要能响应 F9（何况它不可关闭）
        面板注册表.每帧(self)
        if not self.可见:
            return False
        if 面板注册表.画在容器里(self):
            return False
        self.绘制次数 += 1
        # ★ 这条只有在【侧栏整个不可用】时才会走到：它自己开一个不可关闭的窗口兜底
        # ★ 不传 p_open（第二项为 None）→ ImGui 不画关闭按钮 → 没有 ×
        #   （这是刻意的：见类文档 ②）
        展开, _ = imgui.Begin(文案.取("模型库.标题"), None, 0)
        try:
            if not 展开:
                return False
            self._画内容()
        except Exception as 异常:                                       # noqa: BLE001
            self.错误次数 += 1
            if self.错误次数 <= 2:
                print(f"⚠ 模型库面板绘制出错：{type(异常).__name__}: {异常}")
        finally:
            imgui.End()
        return False

    # ------------------------------------------------------------------
    # 面板上显示用的文字：一律 ASCII（见类文档）
    # ------------------------------------------------------------------
    def _界面状态(self) -> str:
        """把仿真侧的中文状态串翻成短英文（面板画中文会变成 ?）。"""
        原始 = str(self.状态 or "")
        if 原始.startswith("✗"):
            前缀, 余 = "[fail] ", 原始[1:]
        elif 原始.startswith("✓"):
            前缀, 余 = "[ok] ", 原始[1:]
        elif "…" in 原始:
            前缀, 余 = "[..] ", 原始
        else:
            前缀, 余 = "", 原始
        return 前缀 + (界面文字.英文(余.strip()) or "(status in terminal)")

    def _界面模型名(self) -> str:
        """当前模型的显示名（空场景那种中文名换成英文）。"""
        if self.当前路径 and _os.path.normpath(绝对路径(self.当前路径)) == _os.path.normpath(空场景路径):
            return "Empty scene (no robot)"
        return 界面文字.英文(self.当前显示名 or "(unknown)")

    def _画内容(self) -> None:
        # 容器把本面板画在页签里时，容器负责跳过"没打开的页签"；这里再挡一道
        if not self.可见:
            return
        self.绘制次数 += 1
        # 文件对话框的结果（后台线程，每帧查一次即可）
        选中的 = self.选择器.取()
        if 选中的:
            self._发命令(选中的, _os.path.basename(选中的))

        当前绝对 = _os.path.normpath(绝对路径(self.当前路径)) if self.当前路径 else ""

        # ---- 当前模型 ----
        imgui.Text("Current")
        imgui.SameLine()
        if self.当前路径 and 当前绝对 == _os.path.normpath(空场景路径):
            imgui.TextColored(灰(), self._界面模型名())
        else:
            imgui.TextColored(绿(), self._界面模型名())
            if self.自由度:
                imgui.SameLine()
                imgui.TextDisabled(文案.格式化("模型库.轴数", "({n} axes)", n=self.自由度))
        imgui.TextDisabled("  " + self._界面状态())
        imgui.Separator()

        # ---- 当前项目 + 这一组算法（方案 C：点模型会自动换一组算法）----
        #   面板上只能 ASCII，所以项目名走"能翻就翻、翻不了就原样"的兜底
        imgui.Text("Project")
        imgui.SameLine()
        if self.当前项目:
            imgui.TextColored(绿(), 界面文字.英文(self.当前项目))
        else:
            imgui.TextColored(灰(), 文案.取("模型库.无算法"))
        # 算法列表：名字 + 版本。用英文名（插件自己声明的 `英文名`），没有就查术语表。
        if self.算法列表:
            imgui.TextDisabled(文案.格式化("模型库.项目算法", "  Algorithms ({n}):",
                                                  n=len(self.算法列表)))
            for a in self.算法列表:
                名 = str(a.get("名称", "?"))
                英文 = str(a.get("英文名", "") or "") or 界面文字.英文(名)
                版 = str(a.get("版本", "-"))
                参数 = a.get("参数") or {}
                后缀 = "  " + 文案.格式化("模型库.参数数", "({n} params)", n=len(参数)) if 参数 else ""
                imgui.TextDisabled(文案.格式化("模型库.算法行", "    · {名} v{版}{后缀}",
                                                 名=文案.状态(英文), 版=版, 后缀=后缀))
        else:
            imgui.TextDisabled(文案.取("模型库.当前项目无算法"))
            imgui.TextDisabled(文案.取("模型库.加项目"))
            self._提醒项目说明()
        # 装配报告里如果有"被跳过"的算法，就在面板上提醒一句（细节在终端）
        跳过数 = sum(1 for 行 in self.装配报告 if str(行).startswith("–"))
        if 跳过数:
            imgui.TextColored(黄(), 文案.格式化("模型库.跳过算法",
                                              "  {n} algorithm(s) skipped (model incompatible)",
                                              n=跳过数))
            imgui.TextDisabled(文案.取("模型库.跳过详情"))
        imgui.Separator()

        # ---- 机械臂列表 ----
        imgui.TextDisabled(文案.格式化("模型库.列表标头",
                                            "Model library ({n} arms; click to switch)",
                                            n=len(self.模型列表)))
        if not self.模型列表:
            imgui.TextColored(橙(), 文案.取("模型库.空库"))
            imgui.TextDisabled(文案.取("模型库.空库提示"))
            self._提醒导入命令()
        for m in self.模型列表:
            路径 = 绝对路径(m.get("扭矩模型", ""))
            选中 = 当前绝对 == _os.path.normpath(路径)
            标记 = "*" if 选中 else " "
            标签 = f"{标记} {界面文字.英文(m.get('显示名', m.get('标识', '?')))}"
            if imgui.Selectable(f"{标签}##{m.get('标识', '')}", 选中):
                if not 选中:
                    self._发命令(路径, str(m.get("显示名", "")))
            imgui.SameLine()
            try:
                轴 = int(m.get("自由度", 0) or 0)
            except Exception:                                            # noqa: BLE001
                轴 = 0
            imgui.TextDisabled(文案.格式化("模型库.许可行", "{轴} axes | {许可}",
                                             轴=轴, 许可=文案.状态(m.get("许可", "?"))))

        imgui.Separator()

        # ---- 操作按钮 ----
        if self.选择器.进行中:
            imgui.BeginDisabled()
        if imgui.Button(文案.取("模型库.导入")):
            self.选择器.开始(起始目录=模型目录)
        if self.选择器.进行中:
            imgui.EndDisabled()
            imgui.SameLine()
            imgui.TextColored(黄(), 文案.取("模型库.导入中"))
        else:
            imgui.SameLine()
        if imgui.Button(文案.取("模型库.空场景")):
            self._发命令(空场景路径, "空场景（无机械臂）")
        imgui.SameLine()
        if imgui.Button(文案.取("模型库.重载")):
            if self.当前路径:
                self._发命令(self.当前路径, self.当前显示名)
        imgui.SameLine()
        if imgui.Button(文案.取("模型库.刷新")):
            self._刷新列表()

        # ---- 手输路径（兜底）----
        imgui.SetNextItemWidth(340.0)
        变了, self.手动路径 = imgui.InputText("##manual path", self.手动路径)
        imgui.SameLine()
        if imgui.Button(文案.取("模型库.走这个路径")):
            if self.手动路径.strip():
                self._发命令(self.手动路径.strip(), _os.path.basename(self.手动路径.strip()))
        if 变了 and self.手动路径 and not _os.path.exists(self.手动路径.strip()):
            imgui.TextColored(橙(), 文案.取("模型库.路径不存在"))

        imgui.Separator()
        imgui.TextDisabled(文案.取("模型库.拖拽提示"))
        imgui.TextDisabled(文案.取("模型库.拖拽注意"))
        imgui.TextDisabled(文案.格式化("模型库.统计",
                                           "frames={帧}  switches={切换}  draw={绘制}  lib={库}",
                                           帧=self.收帧, 切换=self.切换次数,
                                           绘制=self.绘制次数, 库=len(self.模型列表)))

    def _提醒项目说明(self) -> None:
        """没挂算法时，在终端说明"算法从哪来"（面板上画不了中文）。"""
        if getattr(self, "_已提醒项目", False):
            return
        self._已提醒项目 = True
        print("【项目】当前模型没有对应的项目，所以没挂任何控制算法。\n"
              "        算法由「项目」声明，不是写死在代码里：\n"
              "          · 看看有哪些项目：  ./.venv/bin/python 软件/主程序.py --列项目\n"
              "          · 新建一个项目：   在 项目/ 下加一个 .json，`模型` 字段指向本模型，\n"
              "                              `算法` 字段写 \"*\"（用算法库全部）或列出具体算法\n"
              "          · 加一个算法：     把 .py 放进 算法库/通用/ 或 算法库/实验/\n"
              "        详见 文档/架构… 与 算法库/通用/我的控制律_模板.py 的说明。", flush=True)

    def _提醒导入命令(self) -> None:
        """模型库为空时，把中文命令行提示打到终端（面板上画不了中文）。"""
        if getattr(self, "_已提醒导入", False):
            return
        self._已提醒导入 = True
        print("【模型库】库里没有可用的机械臂。导入命令（面板上显示不了中文，故在此提示）：\n"
              "        ./.venv/bin/python 工具/导入模型.py --列表\n"
              "        ./.venv/bin/python 工具/导入模型.py <模型名> [<模型名> ...]", flush=True)


# 启动器约定：模块里叫"面板类"的就是要实例化的面板
面板类 = 模型库面板
