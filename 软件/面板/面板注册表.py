"""
面板注册表.py —— 统一管理"我们自定义面板"的登记 / 面板窗托管 / 恢复 / 记忆

★ 它为什么长这样（三次真实踩坑 + 一次可行性验证的结论，改之前请先读完）：

  【坑 ①】官方的 `ux.configure_docking_layout()` **只停靠官方那 19 个面板**，
     我们自己的面板不在停靠布局里 → ImGui 只能把它们渲染成**一堆独立浮动窗口**，
     一开软件就堆在 3D 视图上面；而且面板原来写的是 `imgui.Begin(标题, None, 0)`，
     ImGui 规定 `p_open=None` 就不画关闭按钮 → **既挪不走也关不掉**。
     （修法：`Begin` 传 p_open，右上角有 ×。）

  【坑 ②】用户真正遇到过的那个：**"打开软件 5 个面板全不见了，按 F9 也没反应"**。
     两个原因叠在一起：a) "面板被关掉"这个状态被写进了 `输出/面板状态.json`，下次启动
     先按它把所有面板设成不可见；b) ImGui 把浮动窗口的停靠信息存在 `~/.mujoco.ini`，
     用户把两个面板拖到一起就留下一个**脱离主布局的 DockNode**，下次启动窗口被塞进那个
     谁也不认领的节点 → **有绘制次数、屏幕上什么都没有**。
     → 所以：**不再持久化"面板被关掉"这个状态**，可见性每帧由容器统一广播；
       Shift+F9 / `--恢复默认界面` 负责清掉 ini 里的痕迹。

  【坑 ③ / 2026-10-06】"把自研面板停靠进官方 Dockspace（Options / Inspector 栏，
     或 Inspector 页签旁边那个空位）"**已证伪**。9 组现场实验（切在官方之前/之后、
     `DockBuilderFinish` 调/不调、往 ini 里写 `DockId`、直接塞官方已有节点 `0x06`/`0x08`、
     整套 `RemoveNode→AddNode→切片→Finish` 重建）结论一致：**`DockId` 记得住，
     但 ImGui 永不真的启用停靠**；手写 ini 造出的空节点会被剪掉；整套重建的版面
     **下一帧就被官方抢回去**。证据：`优化（软件优化的报告都放这里面来）/报告/界面侧栏改造_设计规格.md` §1.2。
     → 所以现在是【面板窗】（`面板/面板窗.py`）：一个**假页签**紧挨官方 `Inspector`，
       内容窗摆在右栏、页签栏正下方。**不要再尝试 Dockspace 停靠。**

★ 现在的规矩（面板窗版）：
  ① 一个【Panels】窗，里面 7 个面板**竖排成可折叠的段**（可以同时展开多个）
  ② `面板窗可见` 是唯一的开/关状态；关掉它 = 官方 Inspector 的内容露出来
  ③ **F9 一键恢复**：显示面板窗；一段都没展开时展开第一段
  ④ **Shift+F9 重置版面**：清掉我们在 `~/.mujoco.ini` 里的窗口痕迹 + 记"重开一次"
     命令行等价物：`--恢复默认界面`（下次启动生效）
  ⑤ `独立窗口 = True` 的面板（展示=物理总闸 / 外观）**不进面板窗**，也不受窗口开关连坐
  ⑥ `不可关闭 = True` 的面板（模型库：选机械臂的唯一入口）自己开窗口时没有 ×

用法（面板作者只需在 `画面板()` 开头加三行，见 曲线基类.py 的现成写法）：

    @messages.handler
    def 画面板(self, event: messages.BuildGuiEvent) -> bool:
        面板注册表.每帧(self)                 # ★ 必须放在"可见性检查"之前（F9 靠它）
        if not self.可见:
            return False
        if 面板注册表.画在容器里(self):        # ★ 由面板窗托管 → 本面板不自己开窗口
            ...
            return False
        ...

约定：
    · 面板名取 `面板显示名`（没有就用类名）—— 就是状态文件里的键
    · 页签名取 `页签名`（没有就用 `面板显示名`）—— 独立窗口的标题用它
    · 本模块**没有** `面板类` 这个名字，所以 `启动.py` 的面板自动加载会跳过它
"""
from __future__ import annotations

import json
import os
import re

from mujoco.experimental.dear_imgui import dear_imgui as imgui

# ---------------------------------------------------------------------------
# 名册：谁进面板窗、按什么顺序（顺序 = 从上到下的段顺序）
#   ★ 放在注册表而不是面板窗里：这是"名册"数据，注册表是它的主人；
#     面板窗（面板/面板窗.py）只负责画，并从这里 import，避免两个模块互相 import 成环。
# ---------------------------------------------------------------------------
名册 = ("模型库", "算法", "控制器参数", "参数辨识", "实时监控", "数据录制", "关于")

# 状态文件：<包根>/输出/面板.json（版本 3）
#   ★ 只记"哪些段展开着 / 上次跳到哪一段"；**窗口开没开、面板有没有被关掉，一律不落盘**
#     （坑 ②：一旦落盘，用户下次启动就会看到"面板全不见了"）。
_面板目录 = os.path.dirname(os.path.abspath(__file__))
_包根 = os.path.dirname(os.path.dirname(_面板目录))
状态文件 = os.path.join(_包根, "输出", "面板.json")
状态文件版本 = 3

# 老状态文件（记"每个面板关没关"）：只在第一次启动时读一次，把"用户明确关过面板"
# 这个意图迁移成"面板窗收起"，之后就不再使用它了。文件本身不再改写。
_老状态文件 = os.path.join(_包根, "输出", "面板状态.json")

# 恢复全部面板的快捷键。★ F9 没被官方占用（官方用了 F2/F3/F6/F7 与 W/A/S/D/Q/E）
#   F9       = 全部恢复（显示面板窗；一段都没展开就展开第一段）
#   Shift+F9 = 重置版面（清我们窗口的记录，下次启动回出厂位置）
恢复快捷键 = imgui.Key.F9

# ImGui 的配置文件（窗口位置/停靠信息都在里面）
_IMGUI配置 = os.path.expanduser("~/.mujoco.ini")
_待重开标记 = os.path.join(_包根, "输出", "重启界面.flag")

# 我们自己的窗口名（重置版面时只清这些，不动官方那 19 个面板的布局）
#   ★ "Workbench" 是旧版页签容器的窗口名，留着它只为了把历史遗留段清干净。
_我们的窗口名 = ("Appearance", "About", "Monitor (metrics)", "Recorder",
                "Controller params", "System identification", "Model library",
                "Workbench")

_面板: dict[str, object] = {}        # 名字 → 面板实例（供面板窗/菜单/F9 用）
_展开的段: dict[str, bool] = {}      # 名字 → 这一段是否展开着
_已读 = False
_面板窗可见 = True                   # 【Panels】窗开没开
_上次展开 = ""                       # 上一次从菜单/快捷键跳到哪一段（只记录，启动不自动展开）
_上一帧 = -1
_注册首帧 = -1
_已提醒卡住 = False
_面板窗已就位 = False
_已迁移 = False


def _名字(面板) -> str:
    """面板在状态文件里的键（优先 面板显示名，退化到类名）。"""
    return str(getattr(面板, "面板显示名", None) or type(面板).__name__)


def 页签名(面板) -> str:
    """独立窗口的标题（面板窗里的段用它做标题）。"""
    名 = str(getattr(面板, "页签名", "") or "")
    return 名 or _名字(面板)


def 在名册(名: str) -> bool:
    """这个面板进不进面板窗（不在名册里的让它自己开窗口，见 `画在容器里`）。"""
    return 名 in 名册


def 重置缓存() -> None:
    """把本模块的内存状态清空（重新从状态文件读）。

    ★ 它是给**自检**用的（`验证/面板注册表自检.py` 要反复换状态文件验证语义）。
      正常运行不需要它：进程启动时 `_已读=False`，第一次 `每帧()` 自然会读一次。
    """
    global _已读, _面板窗可见, _展开的段, _上次展开
    global _上一帧, _注册首帧, _已提醒卡住, _面板窗已就位, _已迁移
    _面板.clear()
    _展开的段 = {}
    _已读 = False
    _面板窗可见 = True
    _上次展开 = ""
    _上一帧 = -1
    _注册首帧 = -1
    _已提醒卡住 = False
    _面板窗已就位 = False
    _已迁移 = False


# ---------------------------------------------------------------------------
# 持久化
# ---------------------------------------------------------------------------
def _读取() -> None:
    global _已读, _面板窗可见, _展开的段, _上次展开
    if _已读:
        return
    _已读 = True
    try:
        with open(状态文件, encoding="utf-8") as f:
            数据 = json.load(f)
    except FileNotFoundError:
        _迁移老状态()
        return
    except Exception as 异常:                                            # noqa: BLE001
        print(f"⚠ 面板状态读取失败（按「显示面板窗」处理）：{type(异常).__name__}: {异常}")
        return
    if not isinstance(数据, dict):
        return
    # ★ 窗口开关**故意不读**：启动一律"显示面板窗"。
    #   理由就是文件头【坑 ②】那条教训 —— 一旦把"面板被关掉"持久化，用户下次开软件
    #   就会看到"面板全不见了、按 F9 也没反应"（2026-10-06 实测又踩了一次：
    #   取证脚本把它设成关，用户重启后红框位置空空如也）。
    #   所以 `面板窗可见` 只是**本次运行**的开关，不落盘。
    _面板窗可见 = True
    # 展开的段：v3 用「展开的段」；v2 的「钉住」语义相同（常驻展开），照收
    段 = 数据.get("展开的段")
    if not isinstance(段, dict):
        段 = 数据.get("钉住") or {}
    if isinstance(段, dict):
        _展开的段 = {str(k): bool(v) for k, v in 段.items() if v}
    # ★ v1 的「弹出」「当前页签」**不迁移**：那是独立浮动窗口的概念，
    #   迁移过来会让用户一开软件就被面板压住（"默认先让出 3D"是这一版的取向）。
    _上次展开 = str(数据.get("上次展开") or "")


def _迁移老状态() -> None:
    """第一次跑新版：把老的"每个面板关没关"迁移成"面板窗开没开"。

    老文件里如果**所有**面板都是关的，说明用户当时想清屏 → 面板窗默认收起；
    否则默认打开（面板一律回到面板窗，不再有"某几个不见了"）。
    """
    global _面板窗可见
    try:
        with open(_老状态文件, encoding="utf-8") as f:
            老 = json.load(f)
        if isinstance(老, dict) and 老 and not any(bool(v) for v in 老.values()):
            _面板窗可见 = False
            print("【面板】检测到旧版把面板全关了 → 这次也从「面板窗已收起」开始，按 F9 或 "
                  "菜单 Panels → Show panels window 打开", flush=True)
    except FileNotFoundError:
        pass
    except Exception:                                                    # noqa: BLE001
        pass


def _保存() -> None:
    try:
        os.makedirs(os.path.dirname(状态文件), exist_ok=True)
        with open(状态文件, "w", encoding="utf-8") as f:
            json.dump({"版本": 状态文件版本,
                       "展开的段": _展开的段,
                       "上次展开": _上次展开},
                      f, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception as 异常:                                            # noqa: BLE001
        print(f"⚠ 面板状态保存失败（不影响使用）：{type(异常).__name__}: {异常}")


# ---------------------------------------------------------------------------
# 对外查询（面板窗 / 菜单 / 各面板用）
# ---------------------------------------------------------------------------
def 全部面板() -> list:
    """按名册顺序返回已登记的面板（面板窗画段、菜单列条目都用它）。"""
    顺序 = 面板顺序()
    return [_面板[名] for 名 in 顺序 if 名 in _面板]


def 面板顺序() -> list[str]:
    """面板窗里的段顺序：名册里的 7 个（未登记的跳过），末尾补漏网的面板。

    ★ 排除两类，和旧容器的 `_可切换面板()` 同一套判断：
      · 面板窗**自己**（不然会递归地给自己画一段）
      · `独立窗口 = True` 的面板（展示 / 外观 —— 它们永远以自己的窗口出现）
    """
    def 能进(名: str) -> bool:
        面板 = _面板.get(名)
        if 面板 is None:
            return False
        if type(面板).__name__ == "面板窗":
            return False
        return not bool(getattr(面板, "独立窗口", False))

    名单 = [名 for 名 in 名册 if 能进(名)]
    名单 += [名 for 名 in _面板 if 名 not in 名单 and 能进(名) and not 在名册(名)]
    return 名单


def 面板窗可见() -> bool:
    return _面板窗可见


def 设面板窗可见(值: bool) -> None:
    global _面板窗可见
    # ★ 先 `_读取()`：状态文件是**懒加载**的，如果调用方在任何 `每帧()` 之前就设值，
    #   晚一步的读取会把刚设的值覆盖掉（自检里实测踩到）。设置器必须先物化状态。
    _读取()
    if _面板窗可见 != bool(值):
        _面板窗可见 = bool(值)
        _保存()
        print(f"【面板】面板窗 → {'已打开' if _面板窗可见 else '已收起（菜单 Panels 或 F9 找回）'}",
              flush=True)


def 段展开(面板或名) -> bool:
    名 = 面板或名 if isinstance(面板或名, str) else _名字(面板或名)
    return bool(_展开的段.get(名, False))


def 设段展开(面板或名, 值: bool) -> None:
    global _展开的段, _上次展开
    名 = 面板或名 if isinstance(面板或名, str) else _名字(面板或名)
    if not 名:
        return
    _读取()
    if bool(值):
        _展开的段[名] = True
        _上次展开 = 名
    else:
        _展开的段.pop(名, None)
    _保存()


def 展开的段() -> list[str]:
    """当前展开着的段（过滤掉名册里已经不存在的名字 —— 改名/删面板后不许崩）。"""
    return sorted(名 for 名 in _展开的段 if 在名册(名) or 名 in _面板)


def 全部段(值: bool) -> None:
    """一次展开/收起所有段（面板窗标题行的 all / none 按钮）。"""
    global _展开的段, _上次展开
    _读取()
    if 值:
        _展开的段 = {名: True for 名 in 面板顺序()}
        if _展开的段:
            _上次展开 = list(_展开的段)[0]
        _保存()
    elif _展开的段:
        _展开的段 = {}
        _保存()


def 跳到段(面板或名) -> None:
    """菜单 / Ctrl+数字：显示面板窗并把这一段展开。"""
    名 = 面板或名 if isinstance(面板或名, str) else _名字(面板或名)
    if not 名 or not 在名册(名):
        return
    设面板窗可见(True)
    设段展开(名, True)


def 上次展开() -> str:
    """上一次跳到哪一段（只用于菜单显示与排查；**启动时不自动展开**，理由见 `_读取`）。"""
    return _上次展开


def 有容器() -> bool:
    """面板窗在不在这一批面板里。"""
    return any(type(p).__name__ == "面板窗" for p in _面板.values())


def 确保状态文件() -> None:
    """面板窗启动时调：① 保证状态文件一定存在 ② 只做一次地清掉旧版留下的坏停靠记录。

    ★ 两件事都必须发生在**第一帧之前**（面板窗一被实例化就调），因为
      `~/.mujoco.ini` 是 ImGui 在启动时读进去的 —— 晚一帧就没用了。
    """
    _读取()
    _保存()
    清理旧停靠记录()


def 画在容器里(面板) -> bool:
    """这一帧本面板的内容应该由面板窗画（= 不要自己开窗口）。

    ★ 三条边界，缺一条就会出现"面板两头都不画、用户以为不见了"：
      · 面板窗收起时：谁都不画（`每帧()` 已经把 `面板.可见` 设成 False）
      · `独立窗口 = True`：永远不进面板窗
      · **不在名册里的面板**：让它自己开窗口（否则它既不在面板窗、又不自己画 = 消失）
    ★ 这里必须和 `每帧()` 用同一套判断（含第 1 帧的"面板窗即将出现"预判），
      否则第 1 帧本面板会抢在面板窗前面自己开一个浮动窗口（实测：闪一下）。
    """
    if not _面板窗可见:
        return False
    if bool(getattr(面板, "独立窗口", False)):
        return False
    if not 在名册(_名字(面板)):
        return False
    return 有容器() or _面板窗即将出现()


def _面板窗即将出现() -> bool:
    """面板窗文件在不在（只用来兜住"第 1 帧面板窗还没登记"这个空档）。"""
    global _面板窗已就位
    if _面板窗已就位:
        return True
    try:
        _面板窗已就位 = os.path.exists(os.path.join(_面板目录, "面板窗.py"))
    except Exception:                                                    # noqa: BLE001
        _面板窗已就位 = False
    return _面板窗已就位


def 记录(面板) -> None:
    """面板自己开的窗口里，`imgui.Begin(...)` **之后**调用。

    ★ 面板窗时代这个方法**什么也不做**，但它必须继续存在：面板文件里都在调它。
      旧语义是"点 × = 收回页签容器"；现在面板要么归面板窗管（自己不开窗口），
      要么是 `独立窗口`（要不要关由它自己决定，例如【外观】用菜单开关）。
    """
    return None


# ---------------------------------------------------------------------------
# 面板每一帧要调的两个函数
# ---------------------------------------------------------------------------
def 每帧(面板) -> bool:
    """面板的 `画面板()` **开头**调用（必须在 `if not self.可见` 之前）。

    做四件事：登记面板 → 处理快捷键 → 广播可见性 → 返回这一帧该不该画。

    ★ 可见性规则：`面板窗可见 and 面板窗在`；但 **`独立窗口 = True` 的面板不受连坐**
      ——【展示】是"加载重力/冻结"的物理总闸，面板窗一收起就把它一起藏了，
      用户会以为软件坏了。
    """
    global _注册首帧
    _读取()
    名 = _名字(面板)
    if 名 not in _面板:
        _面板[名] = 面板
        if _注册首帧 < 0:
            _注册首帧 = _帧号()
    处理快捷键()
    _安全网()

    独立 = bool(getattr(面板, "独立窗口", False))
    容器在 = 有容器() or _面板窗即将出现()
    面板.可见 = True if 独立 else bool(_面板窗可见 and 容器在)
    面板._不可关闭生效 = bool(getattr(面板, "不可关闭", False))
    return bool(getattr(面板, "可见", True))


# ---------------------------------------------------------------------------
# 一键恢复 / 重置版面
# ---------------------------------------------------------------------------
def 全部显示() -> None:
    """F9：显示面板窗；一段都没展开时展开名册第一段。

    ★ 顺手把已登记面板的 `可见` 立刻置 True：面板的可见性是每帧由 `每帧()` 广播的，
      如果只改面板窗状态，得等下一帧才看见效果（自检里就会读出"还是不可见"）。
    """
    设面板窗可见(True)
    if not 展开的段():
        名单 = 面板顺序()
        if 名单:
            设段展开(名单[0], True)
    for 面板 in _面板.values():
        if not bool(getattr(面板, "独立窗口", False)):
            try:
                面板.可见 = True
            except Exception:                                            # noqa: BLE001
                continue
    print("【面板】已恢复：面板窗显示"
          f"（展开着：{'、'.join(展开的段()) or '无'}）。点段标题即可展开/收起", flush=True)


def 重置版面() -> None:
    """Shift+F9：清掉 ~/.mujoco.ini 里我们这些窗口的痕迹，下次启动回到出厂位置。

    ★ 为什么需要它：ImGui 会把窗口位置/停靠信息写进 ini。用户把窗口拖到屏幕外、
      或者旧版本留下一个"脱离主布局的 DockNode"时，窗口就会**画了但看不见**，
      而且在运行中没有任何办法把它拽回来（那是 ini 加载时就决定的）。
      唯一可靠的办法就是清掉那些记录 + 重开软件。
    """
    设面板窗可见(True)
    全部段(True)
    _保存()
    清过 = _清理ini()
    try:
        os.makedirs(os.path.dirname(_待重开标记), exist_ok=True)
        with open(_待重开标记, "w", encoding="utf-8") as f:
            f.write("请手动关闭本窗口再打开一次（或直接跑 启动.sh），版面即回到出厂状态。\n")
    except Exception:                                                    # noqa: BLE001
        pass
    print("\n" + "=" * 78, flush=True)
    print("【面板】已重置版面：清理了 ~/.mujoco.ini 里我们这些窗口的记录"
          f"（{'成功' if 清过 else '无需清理'}）", flush=True)
    print("        ★ 请关闭本窗口再打开一次（关窗口 = 存盘，重开 = 生效）", flush=True)
    print("=" * 78 + "\n", flush=True)


def 清理旧停靠记录() -> bool:
    """**只做一次**：把 `~/.mujoco.ini` 里我们这些窗口的旧停靠记录清掉。

    ★ 它修的是用户遇到的那个真实故障：老版本里用户把两个浮动面板拖到一起，ImGui 就在
      ini 里留下一个**脱离主布局的 DockNode**。之后每次启动，ImGui 都把窗口塞进那个
      没人认领的节点里 → **窗口有绘制次数，屏幕上什么都没有**。
      新版面板归面板窗管、不再产生这种节点，所以这条清理只需要跑一次。
    """
    global _已迁移
    if _已迁移:
        return False
    # ★ 用**新**标记文件：容器换形态是一次机制变更，得让它再清一次，
    #   把旧版【工作台】窗口（`[Window][Workbench]`）与它那个悬浮停靠节点一并抹掉。
    _需要清理 = os.path.join(_包根, "输出", ".面板窗已迁移")
    if os.path.exists(_需要清理):
        _已迁移 = True
        return False
    清过 = _清理ini()
    if not 清过:
        # ★ 这次没清成（比如 ini 不可写）→ **不写标记**，下次启动再试。
        return False
    _已迁移 = True
    try:
        os.makedirs(os.path.dirname(_需要清理), exist_ok=True)
        with open(_需要清理, "w", encoding="utf-8") as f:
            f.write("面板改面板窗后已经清理过一次 ~/.mujoco.ini 里的旧停靠记录。\n"
                    "删掉本文件会在下次启动时再清理一次。\n")
    except Exception as 异常:                                            # noqa: BLE001
        print(f"⚠ 迁移标记写入失败（不影响使用，下次启动会再清理一次）：{type(异常).__name__}: {异常}")
    if 清过:
        print("【面板】检测到旧版的窗口停靠记录（会让面板「画了但看不见」）—— "
              "已清理 ~/.mujoco.ini 里我们这些窗口的段落，本次启动即生效", flush=True)
    return 清过


def _清理ini() -> bool:
    """把 ~/.mujoco.ini 里我们自己的窗口段落与停靠记录删掉。

    只删"我们的窗口名"对应的 `[Window][xxx]` 段，以及所有 `DockId=` 行
    （官方那 19 个面板的布局由官方 `configure_docking_layout()` 重建，
    所以删掉 DockId 不会破坏官方界面；反而能清掉那些没人认领的 DockNode）。

    ★ 踩过的坑：判断"跳过"的那一位**必须在遇到任何新的段落头时复位**，否则删掉
      `[Window][Model library]` 之后会把后面所有段落（包括官方的 `[Docking][Data]`、
      主题 `[Studio][UX]`）一起吞掉 —— 实测把官方布局和主题都删没了。
    """
    try:
        if not os.path.exists(_IMGUI配置):
            return False
        with open(_IMGUI配置, encoding="utf-8") as f:
            行 = f.readlines()
        结果, 跳过 = [], False
        for 原行 in 行:
            内容 = 原行.rstrip("\n")
            if 内容.startswith("[") and 内容.endswith("]"):
                跳过 = (内容.startswith("[Window][")
                        and any(内容[len("[Window]["):-1] == 名 or
                                内容[len("[Window]["):-1].startswith(名)
                                for 名 in _我们的窗口名))
                if 跳过:
                    continue
            elif 跳过:
                continue
            if re.match(r"^\s*DockId\s*=", 内容):
                continue
            结果.append(原行)
        with open(_IMGUI配置, "w", encoding="utf-8") as f:
            f.writelines(结果)
        return True
    except Exception as 异常:                                            # noqa: BLE001
        print(f"⚠ 清理 {_IMGUI配置} 失败（不影响使用）：{type(异常).__name__}: {异常}")
        return False


# ---------------------------------------------------------------------------
# 快捷键
# ---------------------------------------------------------------------------
def 有界面上下文() -> bool:
    """ImGui 上下文在不在。

    ★ 为什么必须问这一句：`imgui.IsKeyPressed(...)` 在没有上下文时不是抛异常，
      而是**直接段错误**（实测）。本模块在"没开窗口"的场合也会被用到
      （例如 `验证/面板注册表自检.py` 直接调 每帧/全部显示），
      所以凡是要碰 ImGui 的地方都先过这一关。
    """
    try:
        问 = getattr(imgui, "GetCurrentContext", None)
        return bool(问()) if 问 is not None else False
    except Exception:                                                    # noqa: BLE001
        return False


_有界面上下文 = 有界面上下文          # 旧名保留（模块内与老脚本都在用）


def _帧号() -> int:
    """当前帧号；**没有 ImGui 上下文时返回 -1**（`GetFrameCount()` 无上下文会段错误）。"""
    if not 有界面上下文():
        return -1
    try:
        return int(imgui.GetFrameCount())
    except Exception:                                                    # noqa: BLE001
        return -1


def 处理快捷键() -> None:
    """轮询快捷键。每帧只真正轮询一次（面板有 8 个，都会调本函数）。"""
    global _上一帧
    if not 有界面上下文():
        return
    帧 = _帧号()
    if 帧 >= 0 and 帧 == _上一帧:
        return                                   # 同一帧已经处理过
    _上一帧 = 帧
    try:
        if not imgui.IsKeyPressed(恢复快捷键):
            return
        if imgui.GetIO().KeyShift:
            重置版面()
        else:
            全部显示()
    except Exception:                                                # noqa: BLE001
        pass                                     # 快捷键失败绝不能影响面板绘制


def _安全网() -> None:
    """万一面板窗没画出来（界面被拖到屏幕外等），终端要吭声，而不是让用户干瞪眼。"""
    global _已提醒卡住
    if _已提醒卡住 or _注册首帧 < 0 or not 有容器():
        return
    帧 = _帧号()
    if 帧 < 0 or 帧 - _注册首帧 < 180:          # 约 3 秒
        return
    _已提醒卡住 = True
    if not _面板窗可见:
        print("【面板】面板窗当前是【收起】状态。按 F9 或菜单 Panels → Show panels window 打开；"
              "Shift+F9 = 重置版面（下次启动回到出厂位置）", flush=True)
