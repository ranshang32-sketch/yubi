"""
面板/算法面板.py —— 【Algorithms】算法选择面板（选哪些算法挂在这台模型上）

它解决什么问题
----------------------------------------------------------------------------
方案 C 之后"装哪几个算法"写在 `项目/*.json` 的 `算法` 字段里 —— 数据化了，但
**界面上没有地方能改它**：想换算法只能手工编辑 JSON 再重启软件。
这个面板就是把那件事搬到界面上：勾选、调序、Apply 立即生效。

界面上有什么
----------------------------------------------------------------------------
    Project: UR5e_基础PD                  ← 当前项目（只读）
    Library (6 available)   Selected (0)  ← 左：算法库全部；右：已选，带执行序号
                                              （默认**一个都没选**：进去是静止的）
     [x] 关节 PD 位置控制     (nothing selected)
     [ ] 末端两点运动         勾一个、按 Apply 才开始运动控制
     ...                      [^] [v]     ← 上下调序（★ 见下）
    [Apply]  [Save to project file]  [Revert]

★ 为什么必须有"上下调序"（这不是可选功能）：
  外壳的派发**只看装配顺序**，排在最后的算法最后写 `ctrl[:]` —— **它说了算**。
  （`messages.Priority` 在本外壳里不参与排序，这一条已实测。）所以"选哪些"和
  "谁赢"是同一件事：想换控制律，就是把它调到列表最后。界面上必须能调。

★ Apply 只是**临时生效**，Save 才写回项目文件 —— 这是刻意的：
  试错（"我想看看正弦摆动单独跑什么样"）不该弄坏项目里存好的预设。
  Apply 之后状态消息里 `已存盘=False`，面板上会显示"temporary - not in project file"。

★ 为什么按 Apply 而不是勾一下立即生效：
  装配要换掉**正在被仿真的那批插件实例**，这些对象归仿真线程所有。界面只能
  发一条 `应用算法命令` 请求，由仿真线程去装（见 模型桥.py 的说明）。

★ 名字的三层（别混）：
  · **插件名**（`关节pd控制`）= 模块名，项目文件与装配用它，界面发给仿真侧也用它；
  · **显示名**（`关节 PD 位置控制`）= 插件类上的 `名称`，终端里用；
  · **面板名**（ASCII）= 插件类上的 `英文名`，只有界面用（官方 UI 字体没有中文字形）。
  本面板内部一律用**插件名**做键，显示时才翻成面板名 —— 这样换模型、改项目都不会串。

★ 面板上的文字**只能是 ASCII**：官方 UI 字体没有中文字形，画中文会变成 `?`。
  中文原名与细节留在终端。校验：`.venv/bin/python "优化（软件优化的报告都放这里面来）/验证/字体覆盖.py"`
"""
from __future__ import annotations

import os as _os
import sys as _sys

_外壳目录 = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _外壳目录 not in _sys.path:
    _sys.path.insert(0, _外壳目录)

from mujoco.experimental.dear_imgui import dear_imgui as imgui       # noqa: E402
from mujoco.experimental.studio import messages, viewer_protocol      # noqa: E402

from 模型桥 import 应用算法命令, 项目状态                             # noqa: E402

import 文案
import 面板注册表                                                      # noqa: E402
import 界面文字                                                        # noqa: E402

绿 = lambda: imgui.Vec4(0.30, 0.85, 0.40, 1.0)      # noqa: E731
橙 = lambda: imgui.Vec4(0.95, 0.45, 0.30, 1.0)      # noqa: E731
黄 = lambda: imgui.Vec4(0.95, 0.80, 0.25, 1.0)      # noqa: E731
灰 = lambda: imgui.Vec4(0.65, 0.68, 0.72, 1.0)      # noqa: E731


def 读算法目录() -> dict:
    """{插件名: {"显示名":…, "面板名":…}} —— 只读文件、**不 import 算法**。

    为什么不 import：import 会执行算法模块（有副作用），而面板每帧都要画，
    绝不能在这里反复加载模块。扫描只读文件名；显示名/英文名靠**静态解析**
    模块顶层的两个类属性（正则就够了，插件类的元信息就是两行字面量）。
    拿不到就退回插件名本身（面板上显示模块名也完全可用，不会崩）。
    """
    import re
    import 项目

    结果: dict[str, dict] = {}
    try:
        条目 = 项目.发现的算法()
    except Exception:                                                    # noqa: BLE001
        return 结果
    for d in 条目:
        插件名 = str(d.get("插件") or "")
        if not 插件名:
            continue
        显示名 = 面板名 = 插件名
        try:
            with open(d["文件"], encoding="utf-8") as f:
                源码 = f.read()
            m = re.search(r'^\s{4}名称\s*=\s*"([^"]*)"', 源码, re.M)
            if m:
                显示名 = m.group(1)
            m = re.search(r'^\s{4}英文名\s*=\s*"([^"]*)"', 源码, re.M)
            if m:
                面板名 = m.group(1)
        except Exception:                                                # noqa: BLE001
            pass
        结果[插件名] = {"显示名": 显示名, "面板名": 面板名}
    return 结果


class 算法面板:
    """窗口侧插件：勾选/调序算法 → Apply（临时）或 Save（写回项目文件）。"""

    面板显示名 = "算法"
    页签名 = "Algorithms"

    def __init__(self):
        self.viewer = None
        self.可见 = True
        self.绘制次数 = 0
        self.错误次数 = 0
        # ---- 来自仿真侧（项目状态消息）----
        self.项目 = ""
        self.可选: list[str] = []            # 算法库里全部算法的**插件名**（有序）
        self.在跑: list[str] = []            # 当前真正在跑的那组（插件名，有序）
        self.不兼容: list[str] = []          # 与当前模型不兼容、被预检跳过的（显示名）
        self.控盘 = ""                       # 真正在驱动机器人的那个（显示名）
        self.被覆盖: list[str] = []           # 输出被整体盖掉、等于没挂的（显示名）
        self.重力开 = False                  # 物理跑不跑（仿真侧的状态）
        self.已存盘 = True
        self.报告: list[str] = []
        # ---- 界面本地状态（用户编辑，未 Apply 之前只在这里）----
        self.勾选: list[str] = []
        self._脏 = False
        self._上次可选: tuple = ()
        self.提交次数 = 0
        # ★ 换算法时是否把机器人摆回默认姿态（默认勾上）—— 见 模型桥.应用算法命令 的说明：
        #   不重置的话，新算法会"拿上一个算法留下的姿态当基准"，
        #   表现就是"机器人再也回不到默认位置了"（实测偏离 0.33 rad）。
        self.重置姿态 = True
        self._已提醒空库 = False
        # 插件名 → 元信息（显示名/面板名）。扫描有 IO，缓存起来，算法库变化时才重扫。
        self._元 = 读算法目录()
        self._元指纹 = tuple(sorted(self._元))

    # ------------------------------------------------------------------
    @messages.handler(priority=messages.Priority.CRITICAL)
    def 记下窗口(self, event: viewer_protocol.ViewerInitEvent) -> bool:
        self.viewer = getattr(event, "viewer", None)
        return False

    @messages.handler
    def 收项目状态(self, 消息: 项目状态) -> bool:
        """仿真侧告诉我们：现在哪个项目、可选哪些算法、在跑哪些算法。

        ★ 草稿与真值的同步规则（这里错了用户会看到"我勾的被自己弹回去"）：
            · 用户**没有未提交改动** → 直接用真值刷新草稿（正常跟随）；
            · 用户**有未提交改动**   → 保留草稿，只刷新"可选列表"，
              并在面板上提示"你改了还没 Apply"，免得改动被悄悄吞掉。
        """
        新可选 = [str(x) for x in (getattr(消息, "算法库", None) or [])]
        self.项目 = str(getattr(消息, "项目", "") or "")
        self.已存盘 = bool(getattr(消息, "已存盘", True))
        self.报告 = [str(x) for x in (getattr(消息, "报告", None) or [])]
        self.不兼容 = [行.split("：", 1)[0].lstrip("– ").strip()
                     for 行 in self.报告 if 行.startswith("–")]
        self.控盘 = str(getattr(消息, "控盘", "") or "")
        self.被覆盖 = [str(x) for x in (getattr(消息, "被覆盖", None) or [])]
        self.重力开 = bool(getattr(消息, "重力开", False))

        # 在跑的算法：状态消息给的是**显示名**，转成插件名再比
        在跑 = []
        for a in (getattr(消息, "算法", None) or []):
            if isinstance(a, dict):
                在跑.append(self._插件名(str(a.get("名称", ""))))
        self.在跑 = 在跑

        if tuple(新可选) != self._上次可选:
            self._上次可选 = tuple(新可选)
            self.可选 = 新可选
            # 算法库变了 → 元信息缓存失效，重扫一次
            if tuple(sorted(新可选)) != self._元指纹:
                self._元 = 读算法目录()
                self._元指纹 = tuple(sorted(self._元))
            # 草稿里已经消失的算法要去掉（否则 Apply 会带上一个不存在的名字）
            self.勾选 = [x for x in self.勾选 if x in self.可选]

        if not self._脏:
            self.勾选 = list(self.在跑)
        return False

    def _插件名(self, 显示名: str) -> str:
        """显示名（`关节 PD 位置控制`）→ 插件名（`关节pd控制`）。对不上就原样返回。"""
        if 显示名 in self._元:
            return 显示名
        for 插件名, 元 in self._元.items():
            if 元["显示名"] == 显示名:
                return 插件名
        return 显示名

    def _面板名(self, 插件名: str) -> str:
        """插件名 → 面板上显示的 ASCII 名字。"""
        元 = self._元.get(插件名)
        if 元:
            名 = 元["面板名"] or 元["显示名"]
            return 界面文字.安全(界面文字.英文(名) or 名)
        return 界面文字.安全(界面文字.英文(插件名) or 插件名)

    def _被跳过(self, 插件名: str) -> bool:
        """这个算法是不是被兼容性预检跳过了（按显示名比对报告里的那一行）。"""
        显示 = (self._元.get(插件名) or {}).get("显示名", 插件名)
        return any(显示 and 显示 in 行 for 行 in self.不兼容)

    # ------------------------------------------------------------------
    @messages.handler
    def 画面板(self, event: messages.BuildGuiEvent) -> bool:
        # ★ 必须在"可见性检查"之前：面板收进容器/被关掉时也要能响应 F9
        面板注册表.每帧(self)
        if not self.可见:
            return False
        if 面板注册表.画在容器里(self):
            return False
        self.绘制次数 += 1
        展开, self.可见 = imgui.Begin("Algorithms", self.可见, 0)
        面板注册表.记录(self)
        try:
            if 展开:
                self._画内容()
        except Exception as 异常:                                          # noqa: BLE001
            self.错误次数 += 1
            if self.错误次数 <= 2:
                print(f"⚠ 算法面板绘制出错：{type(异常).__name__}: {异常}")
        finally:
            imgui.End()
        return False

    # ------------------------------------------------------------------
    def _画内容(self) -> None:
        if not self.可见:
            return
        self.绘制次数 += 1

        # ---- 当前项目 + 这一组是否已写回 ----
        imgui.Text("Project")
        imgui.SameLine()
        if self.项目:
            imgui.TextColored(绿(), 界面文字.英文(self.项目))
        else:
            imgui.TextColored(灰(), 文案.取("算法.无项目"))
        imgui.SameLine()
        if self._脏:
            imgui.TextColored(黄(), 文案.取("算法.未保存"))
        elif self.已存盘:
            imgui.TextDisabled(文案.取("算法.已存盘"))
        else:
            imgui.TextColored(黄(), 文案.取("算法.临时"))
        # ---- ★★ 最重要的一条提示：物理跑不跑 ----
        #   装载算法 ≠ 模型会动。物理是**另一个独立开关**（左上角【Display】的
        #   「Load gravity」）。用户看到"算法挂上了但机械臂一动不动"，
        #   第一反应一定是"这算法坏了/没生效" —— 所以这里必须直说，并且**给个开关**
        #   让他当场就能开，不用去别处找。
        if self.重力开:
            imgui.Text(文案.取("算法.物理"))
            imgui.SameLine()
            imgui.TextColored(绿(), 文案.取("算法.跑着"))
            imgui.SameLine()
            if imgui.SmallButton(文案.取("算法.冻结按钮")):
                self._发重力(False)
        else:
            imgui.TextColored(橙(), 文案.取("算法.冻结中"))
            imgui.SameLine()
            if imgui.SmallButton(文案.取("算法.跑物理按钮")):
                self._发重力(True)
            if self.勾选 or self.在跑:
                imgui.TextDisabled(文案.取("算法.挂了但冻结"))
                imgui.TextDisabled(文案.取("算法.去勾重力"))

        # ---- ★ 谁在控盘 / 谁被覆盖（"挂了的算法其实没生效"必须让人看见）----
        #   多个算法都写 ctrl[:] 时只有**最后一个**真正生效，前面那些等于没挂。
        #   以前这件事完全不可见，用户只会觉得"这个算法的效果怎么是这样"。
        #   检测逻辑在 装配器._抢方向盘体检()，经 项目状态 送过来。
        if self.控盘:
            imgui.Text("  Controls")
            imgui.SameLine()
            imgui.TextColored(绿(), 界面文字.安全(界面文字.英文(self.控盘) or self.控盘))
            if self.被覆盖:
                imgui.SameLine()
                imgui.TextColored(橙(), 文案.格式化("算法.覆盖数", "(masking {n})", n=len(self.被覆盖)))
        elif self.勾选:
            imgui.TextColored(灰(), 文案.取("算法.没人控"))
        #   ★ 这里**只能用 ASCII**：面板字面量的白名单检查（字体覆盖.py）仍然只认 ASCII。
        #     虽然主 UI 字体已打中文补丁（脚本自己会报"面板可以显示中文"），但那条白名单
        #     还没跟着放开 —— 两者目前是矛盾的，见 CHANGELOG v0.6.1 的记录。
        #     在规则统一之前，面板文字一律走 ASCII，中文说明留在终端。
        if self.被覆盖:
            imgui.TextColored(橙(), 文案.取("算法.被覆盖标头"))
            for 名 in self.被覆盖:
                imgui.TextDisabled(文案.格式化("算法.被覆盖行", "    - {名}",
                                                     名=文案.状态(名)))
            imgui.TextDisabled(文案.取("算法.挪到底部"))
        imgui.Separator()

        if not self.可选:
            imgui.TextColored(橙(), 文案.取("算法.空库"))
            imgui.TextDisabled(文案.取("算法.空库提示"))
            self._提醒空库()
            return

        # ---- 两栏：左 = 全部可选；右 = 已选且有序 ----
        #   用 Columns 并排，是因为"顺序"在本软件里是语义的一部分（最后一项说了算），
        #   藏进子窗口或折叠区就等于把最关键的规则藏起来。
        imgui.Columns(2, "##algo_cols", True)

        imgui.TextDisabled(文案.格式化("算法.库标头", "Library ({n} available)", n=len(self.可选)))
        for 插件名 in self.可选:
            选中 = 插件名 in self.勾选
            变了, 新值 = imgui.Checkbox(f"{self._面板名(插件名)}##pick_{插件名}", 选中)
            if 变了:
                if 新值:
                    if 插件名 not in self.勾选:
                        self.勾选.append(插件名)      # 新勾的放末尾（= 先被覆盖，符合直觉）
                else:
                    self.勾选 = [x for x in self.勾选 if x != 插件名]
                self._脏 = True
            if self._被跳过(插件名):
                imgui.SameLine()
                imgui.TextColored(橙(), 文案.取("算法.不兼容"))

        imgui.NextColumn()

        imgui.TextDisabled(文案.格式化("算法.已选标头",
                                             "Selected ({n}) - last one wins",
                                             n=len(self.勾选)))
        for i, 插件名 in enumerate(self.勾选):
            最后 = (i == len(self.勾选) - 1)
            imgui.TextColored(绿() if 最后 else 灰(), f"{i + 1}.")
            imgui.SameLine()
            imgui.Text(self._面板名(插件名))
            if 最后:
                imgui.SameLine()
                imgui.TextColored(绿(), 文案.取("算法.谁控盘"))
            # 上下调序：★ 顺序 = 谁说了算，所以这不是锦上添花，是核心功能
            imgui.SameLine()
            if i == 0:
                imgui.BeginDisabled()
            if imgui.SmallButton(f"^##up_{插件名}"):
                self.勾选[i - 1], self.勾选[i] = self.勾选[i], self.勾选[i - 1]
                self._脏 = True
            if i == 0:
                imgui.EndDisabled()
            imgui.SameLine()
            if 最后:
                imgui.BeginDisabled()
            if imgui.SmallButton(f"v##dn_{插件名}"):
                self.勾选[i + 1], self.勾选[i] = self.勾选[i], self.勾选[i + 1]
                self._脏 = True
            if 最后:
                imgui.EndDisabled()

        if not self.勾选:
            imgui.TextColored(橙(), 文案.取("算法.没勾"))

        imgui.Columns(1)
        imgui.Separator()

        # ---- 按钮 ----
        能提交 = bool(self.勾选) and self._脏
        if not 能提交:
            imgui.BeginDisabled()
        if imgui.Button(文案.取("算法.应用")):
            self._发送(落盘=False)
        if not 能提交:
            imgui.EndDisabled()

        imgui.SameLine()
        # Save 不要求先 Apply：仿真侧会一次装好并落盘（少一步操作，且顺序不会错）
        能存 = bool(self.勾选) and (self._脏 or not self.已存盘)
        if not 能存:
            imgui.BeginDisabled()
        if imgui.Button(文案.取("算法.保存")):
            self._发送(落盘=True)
        if not 能存:
            imgui.EndDisabled()

        imgui.SameLine()
        if imgui.Button(文案.取("算法.还原")):
            self.勾选 = list(self.在跑)
            self._脏 = False

        # ---- 换算法时是否重置机器人姿态（默认勾上）----
        #   ★ 这一条是用户实测报上来的问题：不重置的话，新算法会在**上一个算法留下的
        #     姿态**上开始控制（因为多数算法"拿第一次看到的位置当基准"），
        #     现象就是"试过几轮算法之后，机器人再也回不到默认位置了"。
        变了, self.重置姿态 = imgui.Checkbox(文案.取("算法.重置姿态"), bool(self.重置姿态))
        if 变了:
            print(f"【算法】换算法时{'重置' if self.重置姿态 else '不重置'}机器人姿态"
                  f"（不重置 = 接着上一个算法的姿态继续）", flush=True)
        imgui.SameLine()
        imgui.TextDisabled(文案.取("算法.不重置提示"))

        # ---- 说明与状态（面板上只能 ASCII）----
        imgui.TextDisabled(文案.取("算法.说明一"))
        imgui.TextDisabled(文案.取("算法.说明二"))
        imgui.TextDisabled(文案.取("算法.说明三"))
        if self._脏:
            imgui.TextColored(黄(), 文案.取("算法.改选提示"))
        if self.不兼容:
            imgui.TextColored(橙(), 文案.格式化("算法.跳过数",
                                              "{n} skipped (incompatible with this model)",
                                              n=len(self.不兼容)))
            imgui.TextDisabled(文案.取("算法.跳过详情"))
        imgui.TextDisabled(文案.格式化("算法.统计", "frames={帧}  submits={提交}",
                                            帧=self.绘制次数, 提交=self.提交次数))

    # ------------------------------------------------------------------
    def _发重力(self, 开: bool) -> None:
        """从本面板直接开关物理（等价于点左上角【Display】的「Load gravity」）。

        ★ 为什么这里要有一个：用户在这个面板挂好算法后，最自然的疑问就是
          "它怎么不动"。让他**就地**能把物理打开，比提示他去左上角找开关有效得多。
          两边发的是**同一条消息**（`重力桥.重力状态`），所以状态永远一致。
        """
        if self.viewer is None:
            print("⚠ 算法选择：还没拿到 viewer，无法发重力开关")
            return
        try:
            import 重力桥
            from 重力桥 import 重力状态
            self.viewer.send_to_sim(重力状态(重力开=bool(开)))
            # ★ 改**界面侧共享状态**，并同步给【Display】面板的勾选框。
            #   不同步的话：这里开了物理，那边勾选框还显示"没勾"，而它每 10 Hz
            #   发布的是**它自己那份状态** —— 于是下一拍又把物理关回去（踩过这个坑）。
            重力桥.设界面重力(bool(开))
            展示 = 面板注册表._面板.get("展示")
            if 展示 is not None:
                展示.加载重力 = bool(开)
                try:
                    展示._上次勾选 = bool(开)
                    展示._发布._上次值 = bool(开)      # 让它的发布器别拿旧值去顶
                except Exception:                                      # noqa: BLE001
                    pass
            self.重力开 = bool(开)
            print(f"【算法】界面把物理{'打开（加载重力）' if 开 else '冻结'}了"
                  f"（已同步左上角勾选框）", flush=True)
        except Exception as 异常:                                          # noqa: BLE001
            print(f"⚠ 重力开关发送失败：{异常}")

    def _发送(self, 落盘: bool) -> None:
        if self.viewer is None:
            print("⚠ 算法选择：还没拿到 viewer，无法发送（窗口还没初始化完？）")
            return
        try:
            self.viewer.send_to_sim(应用算法命令(算法=list(self.勾选), 落盘=落盘,
                                               重置姿态=bool(self.重置姿态)))
            self.提交次数 += 1
            # 乐观更新：真正的真值会由仿真侧发回的项目状态刷新（见 收项目状态）
            self.在跑 = list(self.勾选)
            self._脏 = False
            if 落盘:
                self.已存盘 = True
            print(f"【算法】界面提交 {len(self.勾选)} 个算法"
                  f"（{'写回项目文件' if 落盘 else '临时生效'}）：{'、'.join(self.勾选)}", flush=True)
        except Exception as 异常:                                          # noqa: BLE001
            print(f"⚠ 算法选择发送失败：{异常}")

    def _提醒空库(self) -> None:
        if self._已提醒空库:
            return
        self._已提醒空库 = True
        print("【算法】算法库是空的。把控制算法 .py 放进 <包根>/算法库/通用/（或 实验/）即可；"
              "模板见 算法库/通用/我的控制律_模板.py。", flush=True)


# 启动器约定：模块里叫"面板类"的就是要实例化的面板
面板类 = 算法面板
