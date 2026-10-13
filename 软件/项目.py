"""
项目.py —— 项目清单：「哪个模型 + 用哪些算法 + 参数是多少」的**唯一数据源**

它解决什么问题（方案 C）
----------------------------------------------------------------------------
在这之前，"用哪些控制算法"这件事写在 `主程序.py` 的【插件清单】里：
一份硬编码的 Python 列表，加一个算法要改代码、注释一大段、重启软件。
于是有三个后果：
    ① 换模型不会换算法 —— 点 UR5e 和点 xArm7，界面上挂的是同一套算法；
    ② 同一个算法想用在两台模型上，只能"两份代码"或者"全局都挂上"；
    ③ 「当时跑的是哪个算法、参数多少」没有任何地方记录（录制元信息里的插件清单是空的）。

现在改成**声明式装配**：

    模型（物理对象）  ──┐
    算法（写一次）    ──┼──►  项目文件（一份 JSON）  ──►  外壳按它 new 出插件实例
    参数（旋钮）      ──┘       项目/xxx.json

一个"项目" = (模型 × 算法列表 × 参数) 的一次命名快照。三者解耦的好处：
    · 同一个算法用在两台模型上 → 写两个项目文件，算法只有一份；
    · 同一个模型跑两组参数     → 写两个项目文件；
    · 同一个模型换一组算法     → 还是项目文件。
所以**项目不是模型的附庸，模型只是项目里的一个字段**（`模型`）。

为什么不做成"一个模型一个目录"（那种方案的代价）
----------------------------------------------------------------------------
把算法按模型分目录，看着直观，但会在三处卡住：
    ① 同一个模型上对比 PD / 计算力矩 / 自适应 → 算法该放哪个"模型的目录"？
    ② 在 UR5e 上调好的算法想拿到 xArm7 上验证 → 复制一份还是共享？
    ③ 同一模型跑两组参数做消融 → 又得复制。
本模块的目录布局是"线性的"（`算法库/` 下平铺），而**项目文件里的算法是一个列表**，
所以上面三件事都只是"多写一个项目文件 / 多写一行"，不需要复制代码。

文件长什么样
----------------------------------------------------------------------------
`项目/UR5e_基础PD.json`：

    {
      "_说明": "给人看的说明（可选）",
      "项目": "UR5e_基础PD",
      "模型": "模型/universal_robots_ur5e/ur5e_torque.xml",
      "算法": [
        {"插件": "关节PD控制", "类": "关节PD控制插件"},
        {"插件": "数据录制",   "类": "数据录制插件"}
      ],
      或者 "算法": "*"  = 用算法库里的全部算法（探索阶段省事，加新算法不用改项目文件）
      "参数": {"关节 PD 位置控制": {"KP": 320.0, "KD": 42.0}},
      "外观": {"风格": "现代深色", "主题": "dark"},
      "备注": "论文第三章的基线"
    }

字段的三种写法（`模型` 与 `算法[].插件` 通用）
    · 绝对路径                 "/Users/…/ur5e_torque.xml"
    · 相对包根（**推荐**）      "模型/universal_robots_ur5e/ur5e_torque.xml"
    · 只写文件名               "ur5e_torque.xml"      —— 按 `模型库.json` 反查
`算法[].类` 可以省：省了就用该模块里唯一的 `控制插件` 子类；有多个才必须写。

怎么找项目
----------------------------------------------------------------------------
点模型时按"**项目里的 `模型` 字段指到这个模型**"反查，全部扫一遍 `项目/*.json`。
匹配用的是**规范化后的绝对路径**，所以同一个模型写 `模型/x/y.xml` 或绝对路径都认得。
一个模型可以对应多个项目（同一模型两组参数）；这时取文件名排序第一个，
并把"还有哪几个"打进终端 —— 界面上的完整选择器是后续的事，先把链路跑通。

用法
----------------------------------------------------------------------------
    import 项目
    表 = 项目.读项目("UR5e_基础PD")          # → dict 或 None
    名 = 项目.按模型找项目(模型绝对路径)      # → 项目名 或 ""
    项目.保存参数(项目名, 插件名, {"KP": 320.0})
    项目.保存上次项目(项目名) / 项目.读取上次项目()
"""
from __future__ import annotations

import glob
import json
import os
import sys

# ---------------------------------------------------------------------------
# 路径（相对本文件定位，跟着包走 —— 不写死任何绝对路径）
# ---------------------------------------------------------------------------
软件目录 = os.path.dirname(os.path.abspath(__file__))
包根 = os.path.dirname(软件目录)
项目目录 = os.path.join(包根, "项目")
算法库目录 = os.path.join(包根, "算法库")
模型目录 = os.path.join(包根, "模型")
设置路径 = os.path.join(包根, "输出", "设置.json")

# 项目文件的后缀（`项目/索引.json` 这种不是项目，靠"必须有 `项目` 与 `模型` 字段"排除）
后缀 = ".json"


def _读json(路径: str) -> dict:
    """读一个 JSON 文件；失败返回 {}（并打一句人话提示，不抛异常）。

    ★ 为什么这里要临时抬高递归上限（这是个踩出来的坑）：
      `mujoco.MjModel.from_xml_path()` 是原生扩展，调用它会吃掉 Python 解释器
      **C 层的递归余量**。之后再用 `json.load` 解析中等嵌套深度的文件（本项目的
      `模型库.json` 就够深）会抛 `RecursionError: maximum recursion depth exceeded
      while decoding a JSON array` —— 而 `sys.getrecursionlimit()` 明明还是 1000，
      看起来"上限没变"，所以这个错很难理解。
      实测复现条件：**在循环里**先建 MjModel、再读模型库。
      代价很隐蔽：`_读json` 返回 {} → 模型库"看起来是空的" → 界面列表为空、
      路径反查全部退化成全盘搜索。所以这里在解析期间临时抬高上限，读完还原。
    """
    旧上限 = sys.getrecursionlimit()
    try:
        if 旧上限 < 8000:
            sys.setrecursionlimit(8000)
        with open(路径, encoding="utf-8") as f:
            数据 = json.load(f)
        return 数据 if isinstance(数据, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as 异常:                                          # noqa: BLE001
        print(f"⚠ 读取失败 {os.path.basename(路径)}：{type(异常).__name__}: {异常}")
        return {}
    finally:
        sys.setrecursionlimit(旧上限)


def _写json(路径: str, 数据: dict) -> bool:
    """原子写一个 JSON 文件（先写 .tmp 再 replace —— 中途崩了不会留下半个文件）。"""
    try:
        os.makedirs(os.path.dirname(路径), exist_ok=True)
        临时 = 路径 + ".tmp"
        with open(临时, "w", encoding="utf-8") as f:
            json.dump(数据, f, ensure_ascii=False, indent=2)
        os.replace(临时, 路径)
        return True
    except Exception as 异常:                                          # noqa: BLE001
        print(f"⚠ 保存失败 {os.path.basename(路径)}：{type(异常).__name__}: {异常}")
        return False


# ---------------------------------------------------------------------------
# 路径解析
# ---------------------------------------------------------------------------
def 绝对(路径: str) -> str:
    """把项目文件里的路径写法规范成绝对路径。

    三种输入都要能吃下（顺序就是判断顺序）：
      · 已经是绝对路径且存在        → 原样
      · 相对包根（`模型/x/y.xml`）  → 拼包根
      · 只有文件名（`y.xml`）       → 先在 `模型库.json` 里反查，再全库搜一遍
    找不到就返回"按相对包根拼出来"的结果（让调用方拿到一个能显示给人看的路径）。

    ★ 反查模型库时走的是 `_模型库里的写法()` + `_直接解析()`（纯字符串处理），
      **不能**在反查分支里递归调回本函数 —— `模型库.json` 的 `扭矩模型` 字段本身
      就是相对路径，递归会变成"绝对 → 查模型库 → 绝对 → 查模型库"的无限递归。
      实测撞上过：5 个模型的循环里抛 `RecursionError: maximum recursion depth exceeded`，
      看起来像 mujoco 的问题，其实是本函数自己绕圈。
    """
    文本 = str(路径 or "").strip()
    if not 文本:
        return ""
    for 候选 in (文本, os.path.join(包根, 文本)):
        if os.path.exists(候选):
            return os.path.abspath(候选)

    # 只有文件名 → 查模型库（用纯字符串候选，见下面的★）
    名 = os.path.basename(文本)
    for 原始 in _模型库里的写法(名):
        命中 = _直接解析(原始)
        if 命中:
            return 命中

    # 再全库搜一遍（模型库里没登记的模型也能用）
    for 根 in (模型目录, 算法库目录, 项目目录):
        if not os.path.isdir(根):
            continue
        for 当前, _目录, 文件们 in os.walk(根):
            if 名 in 文件们:
                return os.path.abspath(os.path.join(当前, 名))
    return os.path.normpath(os.path.join(包根, 文本))


def _直接解析(写法: str) -> str:
    """只做"绝对路径 / 相对包根"两种解析，**不反查模型库**（用来打断递归）。"""
    文本 = str(写法 or "").strip()
    if not 文本:
        return ""
    for 候选 in (文本, os.path.join(包根, 文本)):
        if os.path.exists(候选):
            return os.path.abspath(候选)
    return ""


def _模型库里的写法(文件名: str) -> list[str]:
    """在模型库索引里找出某个文件名对应的**原始写法**（只做字符串比较，不解析路径）。"""
    结果: list[str] = []
    for m in 模型库条目():
        if not isinstance(m, dict):
            continue
        for 键 in ("扭矩模型", "位置模型", "路径", "XML"):
            候选 = str(m.get(键) or "")
            if 候选 and os.path.basename(候选.replace("\\", "/")) == 文件名:
                结果.append(候选)
    return 结果


def 相对包根(路径: str) -> str:
    """把绝对路径写回项目文件时用：能相对包根就相对，否则保留绝对。"""
    绝对路径 = 绝对(路径)
    前缀 = 包根 + os.sep
    return 绝对路径[len(前缀):] if 绝对路径.startswith(前缀) else 绝对路径


def 模型库条目() -> list[dict]:
    """读 `模型/模型库.json` 的条目（读不到就返回空表，调用方按"没有"处理）。"""
    数据 = _读json(os.path.join(模型目录, "模型库.json"))
    条目 = 数据.get("模型", [])
    return 条目 if isinstance(条目, list) else []


def 显示模型名(模型绝对路径: str) -> str:
    """给一个模型路径起个给人看的名字（模型库里有就用库里的显示名）。"""
    目标 = os.path.normpath(绝对(模型绝对路径))
    for m in 模型库条目():
        for 键 in ("扭矩模型", "位置模型", "路径", "XML"):
            候选 = str(m.get(键) or "")
            if 候选 and os.path.normpath(绝对(候选)) == 目标:
                return str(m.get("显示名") or m.get("标识") or os.path.basename(目标))
    return os.path.basename(目标)


# ---------------------------------------------------------------------------
# 项目清单：扫描 / 读 / 写
# ---------------------------------------------------------------------------
def 列出项目(只列有效: bool = True) -> list[str]:
    """列出所有项目名（按名字排序）。

    怎么判断"这是一个项目文件"：**必须是 dict 且有非空的 `项目` 与 `模型` 两个字段**。
    所以 `项目/索引.json`、`.DS_Store`、临时文件都会被自动跳过，不需要额外维护排除表。
    """
    结果 = []
    for 路径 in sorted(glob.glob(os.path.join(项目目录, "*" + 后缀))):
        if os.path.basename(路径).startswith("_"):
            continue
        数据 = _读json(路径)
        if not 数据:
            continue
        if 只列有效 and not (数据.get("项目") and 数据.get("模型")):
            continue
        结果.append(str(数据.get("项目") or os.path.splitext(os.path.basename(路径))[0]))
    return 结果


def 项目文件路径(项目名: str) -> str:
    """项目名 → 文件路径。优先同名文件；找不到就按名字新建一个（保存时用）。"""
    候选 = os.path.join(项目目录, str(项目名) + 后缀)
    if os.path.exists(候选):
        return 候选
    for 路径 in sorted(glob.glob(os.path.join(项目目录, "*" + 后缀))):
        数据 = _读json(路径)
        if str(数据.get("项目") or "") == str(项目名):
            return 路径
    return 候选


def 读项目(项目名: str) -> dict | None:
    """按名字读一个项目；不存在返回 None。"""
    路径 = 项目文件路径(项目名)
    if not os.path.exists(路径):
        return None
    数据 = _读json(路径)
    return 数据 or None


def 保存项目(数据: dict) -> bool:
    """整体写回一个项目（`数据["项目"]` 必须有名字）。"""
    名 = str(数据.get("项目") or "").strip()
    if not 名:
        print("⚠ 项目没有名字，拒绝保存")
        return False
    return _写json(项目文件路径(名), 数据)


def 按模型找项目(模型路径: str) -> str:
    """★ 核心入口：点一个模型 → 找到它对应的项目名。

    匹配规则 = **项目里的 `模型` 字段规范化后相等**。一个模型对应多个项目时，
    取名字排序第一个，并把其余几个打到终端（提示还有别的选择）。
    找不到返回空串 —— 调用方按"这个模型还没有项目"处理（用空算法集启动）。
    """
    目标 = os.path.normpath(绝对(模型路径)) if 模型路径 else ""
    if not 目标:
        return ""
    命中 = []
    for 名 in 列出项目():
        数据 = 读项目(名) or {}
        if os.path.normpath(绝对(str(数据.get("模型") or ""))) == 目标:
            命中.append(名)
    if not 命中:
        return ""
    if len(命中) > 1:
        print(f"ℹ 模型「{显示模型名(模型路径)}」对应 {len(命中)} 个项目：{'、'.join(命中)}"
              f" —— 本次用第一个「{命中[0]}」（切换项目：改 项目/{命中[0]}{后缀}，"
              f"或删掉其余几个的同名 `模型` 字段）", flush=True)
    return 命中[0]


# ---------------------------------------------------------------------------
# 算法解析
# ---------------------------------------------------------------------------
def 算法文件(条目) -> str:
    """算法条目 → 绝对文件路径。

    条目可以是两种写法：
        {"插件": "关节PD控制", "类": "关节PD控制插件"}      ← 推荐
        "关节PD控制"                                        ← 简写（类由扫描推断）
    """
    模块名 = str((条目 or {}).get("插件") if isinstance(条目, dict) else 条目 or "").strip()
    if not 模块名:
        return ""
    if os.path.isabs(模块名) and 模块名.endswith(".py"):
        return 模块名
    # ① 算法库里找（含子目录，所以"通用/关节pd控制"这种写法也认）
    候选 = os.path.join(算法库目录, 模块名.replace("\\", "/"))
    for 试 in (候选 + ".py", 候选, os.path.join(软件目录, "plugins", 模块名 + ".py")):
        if os.path.isfile(试):
            return os.path.abspath(试)
    # ② 全库按文件名找（大小写与中文都按原样比）
    for 根 in (算法库目录, os.path.join(软件目录, "plugins")):
        if not os.path.isdir(根):
            continue
        for 当前, _目录, 文件们 in os.walk(根):
            for 文件 in 文件们:
                if 文件 == 模块名 + ".py" or os.path.splitext(文件)[0] == 模块名:
                    return os.path.abspath(os.path.join(当前, 文件))
    return ""


def 解析算法(数据: dict | None) -> list[dict]:
    """项目数据 → 规范化后的算法条目列表（外壳装配插件时用）。

    三种写法都收：
        "算法": "*"                        → 算法库里的**全部**算法
        "算法": ["关节PD控制", "数据录制"]  → 这些（简写：类名由装配时按模块推断）
        "算法": [{"插件": …, "类": …}]      → 这些（显式指定类名，模块里有多个子类时必须写）
    不认识的条目只打警告、跳过 —— 一个写错的项目文件不该让整个软件起不来。
    """
    原始 = (数据 or {}).get("算法", "*")
    已知 = 发现的算法()                      # 只扫一次目录（扫盘不便宜，别在循环里反复扫）
    if isinstance(原始, str):
        if 原始.strip() in ("*", "全部", "all"):
            条目 = [{"插件": d["插件"], "文件": d["文件"]} for d in 已知]
        elif 原始.strip():
            条目 = [{"插件": 原始.strip()}]
        else:
            条目 = []
    elif isinstance(原始, list):
        条目 = list(原始)
    else:
        条目 = []

    结果: list[dict] = []
    认识 = {d["插件"] for d in 已知}
    for 一条 in 条目:
        名 = str((一条 or {}).get("插件") if isinstance(一条, dict) else 一条 or "").strip()
        if not 名:
            continue
        if 名 not in 认识:
            print(f"⚠ 项目里写了算法「{名}」，但算法库里找不到这个文件（已跳过）。"
                  f"现有：{'、'.join(sorted(认识)) or '（空）'}")
            continue
        规范 = {"插件": 名}
        if isinstance(一条, dict):
            if 一条.get("类"):
                规范["类"] = str(一条["类"])
            if 一条.get("文件"):
                规范["文件"] = str(一条["文件"])
        结果.append(规范)
    return 结果


def 发现的算法() -> list[dict]:
    """扫一遍算法库，返回"有哪些算法、各自在哪个文件、类名是什么"。

    这一步**只读文件、不 import**（import 有副作用，不能在扫描阶段做）：
    类名靠"条目里写了就用条目的，没写就等装配时按模块里的子类推断"。
    界面上的"可选算法清单"、`工具/` 下的检查脚本都用它。
    """
    结果: list[dict] = []
    根们 = [算法库目录, os.path.join(软件目录, "plugins")]
    for 根 in 根们:
        if not os.path.isdir(根):
            continue
        for 当前, 目录们, 文件们 in os.walk(根):
            目录们[:] = [d for d in 目录们 if not d.startswith(("_", ".")) and d != "__pycache__"]
            for 文件 in sorted(文件们):
                if not 文件.endswith(".py") or 文件.startswith("_"):
                    continue
                模块名 = os.path.splitext(文件)[0]
                # 模板不是算法：文件名里带「模板」的一律跳过（`我的控制律_模板.py` 这种），
                # 否则它会被当成一个可装配的算法，而它里面的 `我的插件` 只是给人抄的示例。
                if "模板" in 模块名:
                    continue
                结果.append({
                    "插件": 模块名,
                    "文件": os.path.abspath(os.path.join(当前, 文件)),
                    "相对包根": 相对包根(os.path.join(当前, 文件)),
                    "分组": os.path.relpath(当前, 根).replace("\\", "/")
                            if os.path.relpath(当前, 根) != "." else "",
                })
    return 结果


# ---------------------------------------------------------------------------
# 参数（按项目持久化）
# ---------------------------------------------------------------------------
def 读参数(项目名: str) -> dict:
    """读一个项目里已保存的参数：{插件名: {参数名: 值}}。"""
    return dict((读项目(项目名) or {}).get("参数") or {})


def 保存参数(项目名: str, 插件名: str, 参数: dict) -> bool:
    """把某个插件的参数写回项目文件（其它插件的参数保持不动）。

    ★ 为什么要落盘：参数面板拖出来的值今天只活在内存里，换项目/重启就没了。
      落到项目文件之后，"这一组参数"成了实验记录的一部分 —— 这正是方案 C 要的。
    """
    数据 = 读项目(项目名)
    if 数据 is None:
        return False
    if not 参数:
        return True
    全部 = dict(数据.get("参数") or {})
    该插件 = dict(全部.get(插件名) or {})
    该插件.update({str(k): float(v) for k, v in 参数.items()})
    全部[插件名] = 该插件
    数据["参数"] = 全部
    return 保存项目(数据)


# ---------------------------------------------------------------------------
# 记住"上次用的项目"（启动时恢复用）
# ---------------------------------------------------------------------------
def _读设置() -> dict:
    数据 = _读json(设置路径)
    return 数据


def 读取上次项目() -> str:
    """上次用的项目名；没有 / 项目文件已不在 → 返回空串。"""
    名 = str(_读设置().get("上次项目") or "")
    if 名 and 读项目(名) is None:
        return ""
    return 名


def 保存上次项目(项目名: str) -> None:
    """记住这次用的项目（空串 = 清掉）。写失败不影响使用。"""
    数据 = _读设置()
    if 数据.get("上次项目") == 项目名:
        return
    if 项目名:
        数据["上次项目"] = 项目名
    else:
        数据.pop("上次项目", None)
    os.makedirs(os.path.dirname(设置路径), exist_ok=True)
    _写json(设置路径, 数据)
