"""
界面桥.py —— 把官方 GUI 面板的数值传给插件（viewer 侧插件）

为什么需要它：
  官方把程序分成两半 —— 仿真侧（sim）和窗口侧（viewer）。两边只能通过消息通信。
  窗口侧的 `ux_state.ctrl_target` 就是你拖【Controls】面板滑杆时改的那 6 个目标值，
  但它住在 viewer 侧；插件住在 sim 侧，默认拿不到。
  这个小插件住在 viewer 侧，每帧把 ctrl_target 塞进一条消息发给 sim 侧。

插件使用方式（见 plugins/关节pd控制.py）：
      @每步
      def 每步控制(self, event: messages.StepEvent) -> bool:
          目标 = 插件.滑块目标(界面.面板目标, 默认值)     # ← 界面滑杆优先
"""
from __future__ import annotations

import dataclasses
import os

from mujoco.experimental.studio import messages, viewer_protocol


@dataclasses.dataclass(frozen=True)
class 面板目标消息(messages.Snapshot):
    """一条「最新覆盖」消息：滑杆的当前值（Snapshot = 只保留最新一条，不排队）。

    注意：官方所有具体消息都是 dataclass 并且**必须加 @dataclasses.dataclass**，
    否则 pybind 侧的字段访问拿不到值（实测：不加时消息对象是空的）。
    """

    ctrl_target: object


class 界面桥:
    """viewer 侧插件：① 每帧把 Controls 面板的滑杆值发给仿真侧 ② 首帧应用界面主题。"""

    def __init__(self):
        self.viewer = None
        self.面板目标 = None                 # 给需要在 viewer 侧读的人用
        self._主题已应用 = False

    @messages.handler(priority=messages.Priority.CRITICAL)
    def _记下viewer(self, event: viewer_protocol.ViewerInitEvent) -> bool:
        self.viewer = event.viewer
        return False

    # ------------------------------------------------------------------
    # 界面主题：必须等窗口和 ImGui 上下文都建好之后才能设置。
    # ★ 踩过的坑：在窗口创建之前调用 ux.setup_theme() 会直接**段错误（segfault）**，
    #   整个程序崩掉、窗口都没有。所以放到首帧里做。
    # ------------------------------------------------------------------
    @messages.handler(priority=messages.Priority.CRITICAL)
    def _首帧应用主题(self, event: messages.UpdateEvent) -> bool:
        if self._主题已应用:
            return False
        self._主题已应用 = True
        self._应用主题()
        return False

    def _应用主题(self) -> None:
        from mujoco.experimental.studio import ux

        名字 = (os.environ.get("MUJOCO_STUDIO_THEME") or "").strip().upper()
        if not 名字:
            return
        表 = {"LIGHT": ux.GuiTheme.LIGHT, "浅色": ux.GuiTheme.LIGHT,
              "DARK": ux.GuiTheme.DARK, "深色": ux.GuiTheme.DARK,
              "CLASSIC": ux.GuiTheme.CLASSIC, "经典": ux.GuiTheme.CLASSIC}
        主题 = 表.get(名字)
        if 主题 is None:
            print(f"⚠ 认不出主题「{名字}」，可选：dark / light / classic")
            return
        try:
            # 官方 ViewerApp 关闭窗口时会用它自己记的 theme 再存一次设置，
            # 不告诉它的话，就会把我们刚设的深色覆盖回浅色（实测踩过）。
            # 这里把主题同步给官方 App：菜单显示、实际样式、保存的值三者一致。
            for 对象 in self._窗口侧对象():
                对象.theme = 主题
            ux.setup_theme(主题)
            ux.save_settings(主题)          # 存进 ~/.mujoco.ini，下次启动仍是这个主题
            print(f"【界面主题】已设为 {主题.name}"
                  f"（改：--主题 dark/light/classic，或窗口里 Options → Theme）", flush=True)
        except Exception as 异常:           # noqa: BLE001 —— 主题失败不能影响使用
            print(f"⚠ 主题设置失败（不影响使用）：{异常}")

    def _窗口侧对象(self):
        """窗口侧带 theme 属性的插件（就是官方 ViewerApp）。

        官方 Viewer 只保留 PluginRegistry、不保留插件实例列表，
        所以由我们的窗口子类在构造时把实例挂到 viewer.app 上（见 制作窗口类）。
        """
        窗口 = getattr(self.viewer, "app", None)
        return [窗口] if 窗口 is not None else []

    @messages.handler
    def _每帧发目标(self, event: messages.UpdateEvent) -> bool:
        viewer = self.viewer
        if viewer is None:
            return False
        ux_state = getattr(viewer, "ux_state", None)
        目标 = getattr(ux_state, "ctrl_target", None) if ux_state is not None else None
        if 目标 is None:
            return False
        self.面板目标 = 目标
        try:
            viewer.send_to_sim(面板目标消息(ctrl_target=目标.copy()))
        except Exception:                      # noqa: BLE001 —— 界面桥绝不能拖垮窗口
            pass
        return False


def 制作窗口类(官方窗口基类):
    """把官方 ViewerApp 包一层：让界面桥能拿到它，从而正确设置/保留界面主题。

    为什么需要：
      官方 Viewer 只保留了 PluginRegistry，没有保留插件实例列表 —— 界面桥要同步主题
      就得能拿到 ViewerApp 本体，所以在这里把本窗口挂到 `viewer.app`。
      之后 `界面桥._应用主题()` 会把主题同时写进：官方 App 的 theme（菜单显示）、
      ImGui 样式（实际外观）、ini 文件（下次启动的值），三者保持一致。
    """
    from mujoco.experimental.studio import ux

    class 我们的窗口(官方窗口基类):
        主题名 = (os.environ.get("MUJOCO_STUDIO_THEME") or "").strip().upper()

        @messages.handler(priority=messages.Priority.CRITICAL)
        def _把app挂到viewer上(self, event: viewer_protocol.ViewerInitEvent) -> bool:
            event.viewer.app = self
            return False

        @messages.handler(priority=messages.Priority.INTERNAL)
        def _退出时按CLI主题保存(self, event: messages.ExitEvent) -> bool:
            # 官方紧接着也会存一次；这里先按 CLI 指定的主题存，避免被旧值覆盖
            表 = {"LIGHT": ux.GuiTheme.LIGHT, "DARK": ux.GuiTheme.DARK, "CLASSIC": ux.GuiTheme.CLASSIC}
            if self.主题名 in 表:
                self.theme = 表[self.主题名]
                ux.save_settings(self.theme)
            return False

    return 我们的窗口
