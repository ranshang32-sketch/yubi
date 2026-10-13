"""
参数桥.py —— 把界面滑杆的值送回插件（第 4 步：控制器参数面板）

数据流向（和"指标"正好相反）：
    指标：  插件 → 外壳 → 界面（画曲线）
    参数：  界面 → 外壳 → 插件（改参数）

为什么不用直接调用：
    界面（viewer 侧）和插件（仿真侧）在两个线程/两个"世界"里，
    只能靠消息通信。所以定义一条参数消息：
        面板发 `参数消息`（改了哪些参数）→ 仿真侧的 `参数应用器` 收 → 调插件的 设置参数()

插件侧要做什么（就一步）：
    声明哪些类属性可以调，界面就会自动出现滑杆：

        def 可调参数(self) -> dict:
            return {"KP": {"值": self.KP, "范围": (10.0, 20000.0)},
                    "KD": {"值": self.KD, "范围": (0.0, 500.0)}}
"""
from __future__ import annotations

import dataclasses
from typing import Any

from mujoco.experimental.studio import messages


@dataclasses.dataclass(frozen=True)
class 参数表消息(messages.Snapshot):
    """仿真侧 → 界面：当前所有可调参数（值 + 范围）。

    为什么是 Snapshot：滑杆只需要"最新状态"，旧的不排队正合适。
    """

    参数: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class 参数消息(messages.Snapshot):
    """界面 → 仿真侧：这一帧被拖动过的参数。

    Snapshot 语义（只保留最新一条）在这里正合适：
    拖动滑杆会连续产生很多条，旧的没处理也无所谓 —— 最新值才是要的。
    """

    改动: dict = dataclasses.field(default_factory=dict)   # {参数名: 新值}


def 采集可调参数(注册表) -> dict[str, dict]:
    """向每个插件问一次"你有哪些可调参数"，合并成一张表。

    同名参数（比如两个插件都有 KP）会带上插件名前缀区分：
        "关节 PD 位置控制·KP"
    这样界面上不会互相串。

    ★ 只问**有 `名称` 的**对象，也就是项目声明的那些用户算法：
      注册表里还混着 StepControl / 模型应用器 / 参数应用器这些内部插件，
      它们不该出现在参数面板上（虽然它们本来也没实现 可调参数()，
      但靠"恰好没实现"来保证正确性太脆 —— 显式跳过更稳）。

    ★ 每个插件名后面缀上它的**版本号**也很重要：换项目时算法可能同名不同版本
      （比如 `算法库/实验/关节pd控制.py` 与 `算法库/通用/关节pd控制.py`），
      面板上要能看出来现在挂的是哪一个。
    """
    表: dict[str, dict] = {}
    for 插件 in getattr(注册表, "_目标", []):
        名 = getattr(插件, "名称", None)
        if not 名:
            continue
        问 = getattr(插件, "可调参数", None)
        if 问 is None:
            continue
        名 = str(名)
        英文 = str(getattr(插件, "英文名", "") or "")   # 面板上显示用（UI 字体无中文字形）
        try:
            一条 = 问() or {}
        except Exception as 异常:                                     # noqa: BLE001
            print(f"⚠ 插件【{名}】的可调参数() 出错（已跳过）：{type(异常).__name__}: {异常}")
            continue
        for 参数名, 信息 in 一条.items():
            范围 = 信息.get("范围") or (0.0, 1.0)
            表[f"{名}·{参数名}"] = {
                "插件": 名,
                "插件英文": 英文,
                "插件版本": str(getattr(插件, "版本", "-")),
                "参数": 参数名,
                "值": float(信息.get("值", 0.0)),
                "范围": (float(范围[0]), float(范围[1])),
                "步长": float(信息.get("步长", 0.0)),
                "单位": str(信息.get("单位", "")),
            }
    return 表


class 参数应用器:
    """仿真侧：收到参数消息后，把它转给对应插件的 设置参数()。

    插件的 每步控制() 读的是自己的类属性，所以改完**下一次步进就生效**，
    不需要插件写任何接收代码。

    ★ 方案 C 之后它还负责**把参数存回项目文件**（`参数存盘` 回调）：
      以前拖出来的值只活在内存里，换项目/重启就没了。存进项目文件之后，
      "这一组参数"成了实验记录的一部分（录制元信息里也会记下当时的参数值）。
    """

    def __init__(self, 参数存盘=None):
        self.已应用 = 0
        self.最近 = {}
        self.错误: list[str] = []
        self._插件名到实例 = {}
        # 存盘回调：(插件名, {参数名: 值}) -> None。由外壳注入（它知道"当前是哪个项目"）。
        self._参数存盘 = 参数存盘

    def 重绑(self, 注册表) -> "参数应用器":
        """`绑定` 的别名 —— 强调"换了一组算法之后要重新绑一次"这件事。

        ★ 保留 `绑定` 这个名字是为了不破坏已有调用（外壳启动时用的是它）。
          两个名字指向同一件事：把"插件名 → 实例"这本账重新拍一遍。
          详见 `绑定()` 的说明（不重绑会导致滑杆静默失效）。
        """
        return self.绑定(注册表)

    def 绑定(self, 注册表) -> "参数应用器":
        """记住插件实例，便于按名字找。**换项目 / 换一组算法之后必须再调一次。**

        ★ 为什么这是必须的（原来漏掉的一步）：
          这里把"插件名 → 实例"拍成一张快照。方案 C 之前插件集合启动后永不改变，
          所以绑定一次就够；现在点模型会换掉整组算法 —— 如果不再绑一次，
          下面 `收参数()` 里 `self._插件名到实例.get(插件名)` 会拿到**旧实例**（或 None），
          结果是：滑杆拖了没反应，而且**一句提示都没有**（`实例 is None` 时直接 continue）。
          这种"静默失效"比抛异常难查得多，所以**绑定必须和装配成对出现**。

        绑定时跳过没有 `名称` 的对象（注册表里混着 StepControl / 模型应用器 /
        参数应用器自己这些内部插件，它们本来也不该出现在参数面板上）。
        """
        self._插件名到实例 = {
            str(getattr(p, "名称", type(p).__name__)): p
            for p in getattr(注册表, "_目标", [])
            if getattr(p, "名称", None)
        }
        return self

    @messages.handler
    def 收参数(self, 消息: 参数消息) -> bool:
        改动 = getattr(消息, "改动", None) or {}
        按插件归并: dict[str, dict] = {}
        for 全名, 值 in 改动.items():
            插件名, _, 参数名 = 全名.partition("·")
            实例 = self._插件名到实例.get(插件名)
            if 实例 is None:
                # ★ 不再静默 continue：换项目/换算法组之后如果忘了重绑，
                #   这里就是"滑杆拖了没反应"的地方 —— 至少要说一声。
                print(f"ℹ 参数「{全名}」没有对应的算法实例（当前这一组里没有【{插件名}】）—— "
                      f"已忽略；如果刚换过模型，这是正常的（那个算法不在本项目里）")
                continue
            错 = 实例.设置参数(参数名, float(值))
            if 错:
                if 错 not in self.错误:
                    self.错误.append(错)
                    print(f"⚠ {错}")
                continue
            self.已应用 += 1
            self.最近[全名] = float(值)
            按插件归并.setdefault(插件名, {})[参数名] = float(值)

        # 存回项目文件（"上次调好的参数"要能延续到下次打开这个项目）
        if 按插件归并 and self._参数存盘 is not None:
            for 插件名, 值表 in 按插件归并.items():
                try:
                    self._参数存盘(插件名, 值表)
                except Exception as 异常:                                  # noqa: BLE001
                    if "存盘" not in getattr(self, "_存盘已报错", set()):
                        self._存盘已报错 = getattr(self, "_存盘已报错", set()) | {"存盘"}
                        print(f"⚠ 参数存盘失败（参数已生效，只是没记住）："
                              f"{type(异常).__name__}: {异常}")
        return False


class 发布器:
    """周期性把"可调参数表"发给界面（默认 10 Hz —— 滑杆不需要更密）。"""

    def __init__(self, 发送函数, 频率: float = 10.0):
        self._发送 = 发送函数
        self._间隔 = 1.0 / max(频率, 1e-6)
        self._下次 = 0.0
        self.已发布 = 0
        self.最近: dict[str, dict] = {}

    def 也许发布(self, 注册表, 仿真时间: float, 墙钟: float) -> bool:
        if 墙钟 < self._下次:
            return False
        self._下次 = 墙钟 + self._间隔
        表 = 采集可调参数(注册表)
        self.最近 = 表
        if not 表:
            return False                     # 没有可调参数就不发，省得界面刷空
        try:
            self._发送(参数表消息(参数=表))
            self.已发布 += 1
            return True
        except Exception as 异常:                                     # noqa: BLE001
            if self.已发布 == 0:
                print(f"⚠ 参数表发布失败（不影响控制）：{type(异常).__name__}: {异常}")
            return False
