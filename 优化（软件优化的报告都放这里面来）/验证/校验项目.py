"""
校验项目.py —— 项目 / 模型 / 算法 三者的交叉一致性自检（方案 C 专用）

为什么需要它
----------------------------------------------------------------------------
方案 C 把"用哪些算法"从代码搬到了数据（`项目/*.json` + `算法库/`）。数据化的代价是
**对不上不会报错，只会静默少东西**：
    · 项目里写了一个算法名，但算法库里没有那个文件 → 装配报告里一行 ✗，容易没看见
    · 算法库里躺着一个从没被任何项目用到的算法 → 你以为在用，其实从没加载过
    · 两个算法文件里的插件类**重名** → 参数面板按"插件名"寻址，会串台
    · 项目指向的模型文件被挪走/改名 → 点开这个项目就是空场景

这些都属于"改一处忘了改另一处"，正是应该交给脚本看住的那类问题。
本脚本只读不写（`--修复` 除外，它只补 `_说明` 之类的注释字段，不动你的算法列表）。

用法
----------------------------------------------------------------------------
    .venv/bin/python 优化（软件优化的报告都放这里面来）/验证/校验项目.py
    .venv/bin/python 优化（软件优化的报告都放这里面来）/验证/校验项目.py --详表

退出码：0 = 全部通过；1 = 有错误（可直接接进 pre-commit 或 工具/跑检查.sh）
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

# ---- 定位包根：本文件在 优化（…）/验证/ 下，上两级是包根 ----
本目录 = os.path.dirname(os.path.abspath(__file__))
包根 = os.path.dirname(os.path.dirname(本目录))
软件目录 = os.path.join(包根, "软件")
if 软件目录 not in sys.path:
    sys.path.insert(0, 软件目录)

import 项目                                                          # noqa: E402
import 装配器                                                        # noqa: E402


class 结果:
    """收集"通过 / 警告 / 错误"三类结论，最后统一决定退出码。

    为什么警告不算失败：有些问题是**设计选择**而不是缺陷（比如一个算法暂时没被
    任何项目用到，可能是在等一个新的实验项目）。警告打出来给人看，但不拦提交。
    """

    def __init__(self) -> None:
        self.通过 = 0
        self.警告: list[str] = []
        self.错误: list[str] = []

    def 检查(self, 说明: str, 成立: bool, 失败原因: str = "") -> bool:
        if 成立:
            self.通过 += 1
        else:
            self.错误.append(f"{说明} —— {失败原因}" if 失败原因 else 说明)
        return 成立

    def 提醒(self, 说明: str) -> None:
        self.警告.append(说明)


def 有未定义全局(函数, 模块) -> list[str]:
    """从一个函数的字节码里找出"被当成全局名读取、但模块里没有"的名字。

    ★ 为什么要走字节码（而不是"调一次试试"）：
      第一版实现是"给每个消息处理器喂一个假事件、看它抛不抛异常"。它对
      `展示姿态插件` 那个真实的 bug **完全无效** —— 因为 `改暂停状态()` 开头是

          if not self._关闭:      # 假事件里 _关闭 是 False
              return False        # ← 提前返回，后面用 `sim` 的那段根本没执行

      也就是说"冒烟调用"只覆盖了提前返回的那条分支，检查是**假绿**的。
      要抓住"搬运漏导入"，必须做**静态**检查，不能靠跑一遍。
      （实测确认过：拿掉 `sim` 的导入，冒烟版仍然全绿。）

    原理与边界：
      · `LOAD_GLOBAL` 在 CPython 3.10 里只由 `LOAD_FAST` 指令消解遮蔽 ——
        所以"同一个名字、前面紧邻的是 LOAD_FAST"就是局部赋值的情况，跳过。
      · 只对**本模块自己定义**的函数/方法做检查（不递归进 import 来的函数）。
      · 名字在内建里（`len`/`print`…）通过 `builtins` 兜底，不算未定义。
    """
    import builtins
    import dis

    if not hasattr(函数, "__code__"):
        return []
    码 = 函数.__code__
    名字集 = set(码.co_names) | {c for c in 码.co_consts if isinstance(c, str)}
    未定义: list[str] = []
    上一条 = None
    for 指令 in dis.get_instructions(函数):
        if 指令.opname == "LOAD_GLOBAL" and 指令.argval not in ("__name__", "__file__"):
            名 = str(指令.argval)
            if 名 in 码.co_varnames:              # 同名局部变量会遮蔽全局 → 误报，跳过
                上一条 = 指令
                continue
            if not hasattr(模块, 名) and not hasattr(builtins, 名):
                未定义.append(名)
        # 记录"上一条是不是 LOAD_FAST 同名"（判断遮蔽）
        上一条 = 指令
    return sorted(set(未定义))


def 扫算法文件的名字解析(路径: str) -> list[str]:
    """扫一个算法文件：所有**本文件定义**的函数/方法里，有没有用未定义的全局名。"""
    import ast
    import types

    答案: list[str] = []
    try:
        with open(路径, encoding="utf-8") as f:
            语法树 = ast.parse(f.read(), filename=路径)
    except SyntaxError as 异常:
        return [f"语法错误：{异常}"]

    模块, 原因 = 装配器.导入算法文件(路径)
    if 模块 is None:
        return []                              # 导入失败在上面已经报过了，不重复
    本文件名 = os.path.abspath(路径)

    类, 原因 = 装配器.找插件类(模块)
    if 类 is None:
        return []                              # 定位不到插件类，上面也报过了
    本文件名 = os.path.abspath(路径)

    def 查(函数, 显示名: str) -> None:
        if not callable(函数) or not hasattr(函数, "__code__"):
            return
        if os.path.abspath(函数.__code__.co_filename) != 本文件名:
            return                             # import 来的，不查（不是本文件的代码）
        缺 = 有未定义全局(函数, 模块)
        if 缺:
            答案.append(f"{显示名} 用到未定义的名字：{'、'.join(缺)}")
        # 内层函数 / lambda 是独立 code object，单独扫一遍
        for 常量 in 函数.__code__.co_consts:
            if isinstance(常量, types.CodeType):
                缺内 = 有未定义全局(常量, 模块)
                if 缺内:
                    答案.append(f"{显示名}.{常量.co_name}() 用到未定义的名字："
                                f"{'、'.join(缺内)}")

    # ① 插件类自己的方法
    #   ★ 必须从**类**上取方法，不能在模块命名空间里找：本项目的算法方法
    #     （`改暂停状态` / `每步控制` …）全是类的方法，`getattr(模块, 名字)` 是 None，
    #     于是整个扫描一条都查不出来（第一版就是这么写的，**静默假绿**）。
    for 节点 in ast.walk(语法树):
        if not isinstance(节点, ast.ClassDef) or getattr(类, "__name__", "") != 节点.name:
            continue
        for 成员 in 节点.body:
            if isinstance(成员, (ast.FunctionDef, ast.AsyncFunctionDef)):
                查(getattr(类, 成员.name, None), f"{节点.name}.{成员.name}()")

    # ② 模块级的普通函数（算法文件里也可能有辅助函数）
    for 节点 in 语法树.body:
        if isinstance(节点, (ast.FunctionDef, ast.AsyncFunctionDef)):
            查(getattr(模块, 节点.name, None), f"{节点.name}()")
    return 答案


def 收集赋值目标(节点) -> set[str]:
    """从一个 AST 子树里收集所有"被赋值的名字"（含元组/列表解包）。

    ★ 为什么单独写一个：`a, b = f()` 的 target 是 `ast.Tuple` 而不是 `ast.Name`，
      只判断 `ast.Name` 会把整条赋值漏掉（实测误报过）。
      星号解包 `a, *rest = ...` 里的 `ast.Starred` 也要递归进去。
    """
    import ast

    答案: set[str] = set()
    for 子 in ast.walk(节点):
        if isinstance(子, ast.Name) and isinstance(子.ctx, ast.Store):
            答案.add(子.id)
        elif isinstance(子, (ast.AnnAssign, ast.AugAssign)):
            t = 子.target
            if isinstance(t, ast.Name):
                答案.add(t.id)
        elif isinstance(子, ast.NamedExpr) and isinstance(子.target, ast.Name):
            答案.add(子.target.id)
    return 答案


def 扫主程序未定义名(路径: str) -> list[str]:
    """扫 `主程序.py` 里"被读取但从未被赋值/导入/声明"的名字。

    ★ 为什么专门给主程序做这一层（这是**闪退级**事故换来的）：
      方案 C 改造时把主程序里旧的局部变量名 `插件` 删掉了，
      但 `注册表 = 插件框架.安全注册表(插件)` 这一行漏改 ——
      于是**双击图标直接闪退**：`NameError: name '插件' is not defined`。

      更难受的是：当时"开窗冒烟测试"是全绿的 —— 因为它直接调
      `启动.启动外壳()`，绕过了 `主程序.main()`；而 `--检查` 又在开窗前就 `return 0`。
      于是这条真实路径**没有任何检查覆盖**。教训：入口必须有自己的检查，
      只测内部函数不算测过。

    实现：只做函数作用域内的名字解析；模块级名字（含条件分支里定义的）与内建算已知。
    `for` / 推导式 / `except as` / 内层 def-class-import / `with as` 都要收进局部名，
    否则会大量误报。
    """
    import ast
    import builtins

    try:
        with open(路径, encoding="utf-8") as f:
            语法树 = ast.parse(f.read(), filename=路径)
    except SyntaxError as 异常:
        return [f"语法错误：{异常}"]

    模块级: set[str] = set()
    for 节点 in 语法树.body:
        if isinstance(节点, (ast.Import, ast.ImportFrom)):
            for a in 节点.names:
                模块级.add((a.asname or a.name).split(".")[0])
        elif isinstance(节点, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            模块级.add(节点.name)
        else:
            # 模块级的任何赋值都要算已知：**元组解包**、注解赋值、增强赋值、walrus、
            # 以及 if/try/for/while 体内定义的。漏掉元组解包会误报 ——
            # 实测 `启动模型, 启动模型原因 = 决定启动模型()` 就被误报成未定义。
            模块级.update(收集赋值目标(节点))

    答案: list[str] = []
    for 节点 in ast.walk(语法树):
        if not isinstance(节点, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        局部: set[str] = {a.arg for a in 节点.args.args} | {a.arg for a in 节点.args.kwonlyargs}
        if 节点.args.vararg:
            局部.add(节点.args.vararg.arg)
        if 节点.args.kwarg:
            局部.add(节点.args.kwarg.arg)
        声明: set[str] = set()
        for 子 in ast.walk(节点):
            if isinstance(子, ast.Global):
                声明.update(子.names)
            if isinstance(子, ast.Name) and isinstance(子.ctx, ast.Store):
                局部.add(子.id)
            if isinstance(子, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and 子 is not 节点:
                局部.add(子.name)
            if isinstance(子, (ast.Import, ast.ImportFrom)):
                for a in 子.names:
                    局部.add((a.asname or a.name).split(".")[0])
            if isinstance(子, ast.ExceptHandler) and 子.name:
                局部.add(子.name)
            if isinstance(子, ast.comprehension) and isinstance(子.target, ast.Name):
                局部.add(子.target.id)
            if isinstance(子, (ast.For, ast.AsyncFor)) and isinstance(子.target, ast.Name):
                局部.add(子.target.id)
            if isinstance(子, ast.withitem) and isinstance(子.optional_vars, ast.Name):
                局部.add(子.optional_vars.id)
        缺 = sorted({
            子.id for 子 in ast.walk(节点)
            if isinstance(子, ast.Name) and isinstance(子.ctx, ast.Load)
            and 子.id not in 局部 and 子.id not in 模块级 and 子.id not in 声明
            and not hasattr(builtins, 子.id)
        })
        if 缺:
            答案.append(f"{节点.name}() 里用到未定义的名字：{'、'.join(缺)}")
    return 答案


def main() -> int:
    ap = argparse.ArgumentParser(description="项目 / 模型 / 算法 一致性自检")
    ap.add_argument("--详表", action="store_true", help="逐项打印，而不只打印结论")
    args = ap.parse_args()

    结 = 结果()
    print("=" * 74)
    print("  校验项目 —— 项目 / 模型 / 算法 三者对不对得上（方案 C）")
    print("=" * 74)

    # ---- ① 算法库本身 ----
    算法们 = 项目.发现的算法()
    结.检查("算法库非空", bool(算法们),
            f"{项目.相对包根(项目.算法库目录)} 里一个算法都没有")
    算法名 = [d["插件"] for d in 算法们]
    重名 = sorted({n for n in 算法名 if 算法名.count(n) > 1})
    结.检查("算法文件名互不重复", not 重名, f"重复的是：{'、'.join(重名)}")

    # 每个算法文件都要能导入、且能唯一定位到一个插件类
    类名表: dict[str, list[str]] = {}
    导入失败: list[str] = []
    for d in 算法们:
        模块, 原因 = 装配器.导入算法文件(d["文件"])
        if 模块 is None:
            导入失败.append(f"{d['插件']}（{原因}）")
            continue
        类, 原因 = 装配器.找插件类(模块)
        if 类 is None:
            导入失败.append(f"{d['插件']}（{原因}）")
            continue
        类名表.setdefault(类.__name__, []).append(d["插件"])
    结.检查("每个算法文件都能导入并定位到唯一插件类", not 导入失败,
            "；".join(导入失败))

    # 插件**类名**重名：装配器按类名去重，参数面板按插件名寻址，重名会串台
    类重名 = {k: v for k, v in 类名表.items() if len(v) > 1}
    结.检查("插件类名互不重复", not 类重名,
            "；".join(f"{k} 出现在 {v}" for k, v in 类重名.items()))

    # ---- ①-b 名字解析检查：抓"搬运漏导入"这类只有运行到才暴露的错误 ----
    #   为什么要静态查而不是"调一次"：调用只能覆盖到提前返回的分支。
    #   实测教训：`展示姿态插件` 从 重力桥.py 搬走时漏了 `sim` 导入，
    #   而 `改暂停状态()` 开头 `if not self._关闭: return False` 会提前返回 ——
    #   喂假事件的冒烟检查给了**假绿**，一开窗才每帧 NameError（然后被永久停用）。
    名字问题: list[str] = []
    for d in 算法们:
        名字问题.extend(f"{d['插件']}：{p}" for p in 扫算法文件的名字解析(d["文件"]))
    结.检查("算法文件里没有未定义的全局名（抓搬运漏导入）", not 名字问题,
            "；".join(名字问题))

    # ---- ①-c 入口检查：主程序里有没有"未定义的名字"（闪退级事故的防线）----
    #   背景：`注册表 = 插件框架.安全注册表(插件)` 漏改成 `插件清单`，
    #   导致双击图标闪退；而开窗冒烟测试因为绕过 main() 而全绿。
    主程序 = os.path.join(软件目录, "主程序.py")
    入口问题 = 扫主程序未定义名(主程序) if os.path.exists(主程序) else ["找不到 软件/主程序.py"]
    结.检查("主程序.py 里没有未定义的名字（会闪退）", not 入口问题, "；".join(入口问题))

    # ---- ①-c2 每个软件模块都能 import（抓"类声明被写坏"这类问题）----
    #   为什么单独查这一条：本轮真出过一次 —— 加字段时注释插错位置，把
    #   `class 算法选择器:` 这一行连同类体吃进了上一个类的 docstring，于是
    #   `模型桥.py` 一 import 就抛 TypeError（报的是"消息类型不对"，
    #   根因却是**类嵌套错了**，症状很绕）。逐模块 import 能直接指出是哪个文件。
    import importlib
    模块名们 = sorted(
        os.path.splitext(f)[0] for f in os.listdir(软件目录)
        if f.endswith(".py") and f != "主程序.py"      # 主程序由下面的 --冒烟 覆盖
    )
    if 软件目录 not in sys.path:
        sys.path.insert(0, 软件目录)
    导入失败 = []
    for 名 in 模块名们:
        try:
            importlib.import_module(名)
        except Exception as 异常:                                          # noqa: BLE001
            导入失败.append(f"{名}.py → {type(异常).__name__}: {异常}")
    结.检查(f"软件/ 下 {len(模块名们)} 个模块都能 import", not 导入失败,
            "；".join(导入失败))

    # ---- ①-d 入口能走到"开窗前"那一步（真跑一遍 main()，不靠"看着对"）----
    #   ★ 用 `--冒烟` 而不是 `--检查`：`--检查` 在装配之后就 return 了，
    #     而 `注册表 = 插件框架.安全注册表(插件清单)` 那一行在它**之后** ——
    #     当初漏改变量名导致双击闪退，正是崩在这一行，而当时的自检全是绿的。
    #     `--冒烟` 会把 环境自检 → 装配 → 参数解析 → 注册表组装 → ViewerConfig
    #     全部真跑一遍，只差最后"开窗"这一步，所以闪退类缺陷无处可藏。
    进程 = subprocess.run([sys.executable, 主程序, "--冒烟"], cwd=包根,
                          capture_output=True, text=True, timeout=180)
    结.检查("`主程序.py --冒烟` 能走到开窗前（exit=0）", 进程.returncode == 0,
            (进程.stderr or 进程.stdout or "")[-500:])
    结.检查("`主程序.py --检查` 能正常跑完（exit=0）",
            subprocess.run([sys.executable, 主程序, "--检查"], cwd=包根,
                          capture_output=True, text=True, timeout=120).returncode == 0,
            "见上面输出")
    结.检查("`主程序.py --列项目` 能正常跑完（exit=0）",
            subprocess.run([sys.executable, 主程序, "--列项目"], cwd=包根,
                          capture_output=True, text=True, timeout=180).returncode == 0,
            "见上面输出")

    # ---- ② 项目文件 ----
    项目们 = 项目.列出项目()
    结.检查("存在至少一个项目", bool(项目们),
            f"{项目.相对包根(项目.项目目录)} 下没有有效的项目文件")

    被引用的算法: set[str] = set()
    模型清单: list[tuple[str, str]] = []
    for 名 in 项目们:
        数据 = 项目.读项目(名)
        if not 结.检查(f"项目「{名}」可读", 数据 is not None):
            continue

        # 模型字段必须能解析到一个存在的文件
        模型写法 = str(数据.get("模型") or "")
        模型绝对 = 项目.绝对(模型写法)
        结.检查(f"项目「{名}」的模型文件存在", bool(模型写法) and os.path.exists(模型绝对),
                f"写法 {模型写法!r} → 解析为 {模型绝对}（不存在）")
        模型清单.append((名, os.path.normpath(模型绝对)))

        # 算法字段：解析出来的条目必须和"项目里写的"一样多（少一个就说明有引用不到的）
        原始 = 数据.get("算法", "*")
        条目 = 项目.解析算法(数据)
        想要数 = len(算法们) if isinstance(原始, str) and 原始.strip() in ("*", "全部", "all") \
            else (len(原始) if isinstance(原始, list) else 0)
        结.检查(f"项目「{名}」声明的算法都能解析", len(条目) == 想要数,
                f"声明 {想要数} 个、解析出 {len(条目)} 个（详见上面的警告）")
        被引用的算法.update(str(a.get("插件")) for a in 条目)

        # 装配一遍（不带模型 → 不做兼容性预检，只看"装得出来吗"）
        实例, 报告 = 装配器.按项目装配(数据, 名)
        失败行 = [行 for 行 in 报告 if str(行).startswith("✗")]
        结.检查(f"项目「{名}」能装配出算法", not 失败行, "；".join(失败行))
        if not 实例:
            结.提醒(f"项目「{名}」装配出 0 个算法（算法字段是空的？）")
        if args.详表:
            print(f"\n── 项目 {名}（{len(实例)} 个算法）")
            for 行 in 报告:
                print(f"     {行}")

    # ---- ③ 模型 ↔ 项目 的对应关系 ----
    # 规则：每个可控制的机械臂都应该能在项目里找到归宿（否则点它就没算法）
    未覆盖: list[str] = []
    for m in 项目.模型库条目():
        if not m.get("可控制"):
            continue
        路径 = os.path.normpath(项目.绝对(str(m.get("扭矩模型") or "")))
        命中 = [n for n, p in 模型清单 if p == 路径]
        if not 命中:
            未覆盖.append(str(m.get("显示名") or m.get("标识")))
    if 未覆盖:
        结.提醒(f"这些机械臂还没有对应的项目（点开它们不会挂任何算法）：{'、'.join(未覆盖)}")

    # 一个模型挂多个项目 → 不算错，但要说清楚（点模型时只会用第一个）
    from collections import Counter
    计数 = Counter(p for _n, p in 模型清单)
    for 路径, 数 in 计数.items():
        if 数 > 1:
            相关 = [n for n, p in 模型清单 if p == 路径]
            结.提醒(f"同一个模型有 {数} 个项目：{'、'.join(相关)}"
                    f" —— 点这个模型时只会用文件名排序第一个（这是设计如此，不是错误）")

    # ---- ⑤ 桌面的"启动项"链接是否还有效（这一次就是它断掉，用户以为软件坏了）----
    #   背景：`.app` 改名后，桌面上那个软链还指着旧名字 → 点下去毫无反应。
    #   程序本身没问题，但用户看到的现象是"软件打不开"，所以必须看住。
    import glob as _glob
    桌面 = os.path.expanduser("~/Desktop")
    链接们 = [p for p in _glob.glob(os.path.join(桌面, "*"))
             if os.path.islink(p)]
    断的 = [os.path.basename(p) for p in 链接们 if not os.path.exists(p)]
    结.检查("桌面上的符号链接都没有断", not 断的,
            f"这些链接指向的目标不存在：{'、'.join(断的)}"
            f"（软件改名/移动后要更新链接，否则双击没反应）")
    # 顺带确认"至少有一个指向本项目的启动项"
    指向本项目 = [p for p in 链接们
                if os.path.exists(p) and os.path.realpath(p).startswith(os.path.realpath(包根))]
    if not 指向本项目:
        结.提醒(f"桌面上没有指向本项目的启动项（{桌面}）—— "
                f"想双击启动可以建一个指向 <包根>/*.app 的链接")

    # ---- ④ 没被任何项目用到的算法 ----
    没用到 = sorted(set(算法名) - 被引用的算法)
    if 没用到:
        结.提醒(f"这些算法没被任何项目用到（算法库里放着但不会加载）：{'、'.join(没用到)}")

    # ---- ⑤ 老目录是否还留着（迁移残留会让"到底加载哪个"变得含糊）----
    老目录 = os.path.join(软件目录, "plugins")
    if os.path.isdir(老目录):
        残留 = sorted(f for f in os.listdir(老目录) if f.endswith(".py"))
        if 残留:
            结.提醒(f"老算法目录 软件/plugins/ 里还有 .py：{'、'.join(残留)}"
                    f" —— 装配器仍会扫它，建议全部迁到 算法库/ 后删掉这个目录")

    # ---- 结论 ----
    print()
    for 报 in 结.警告:
        print(f"⚠ {报}")
    if 结.警告:
        print()
    for 错 in 结.错误:
        print(f"✗ {错}")
    print()
    print("=" * 74)
    if 结.错误:
        print(f"  结果：{结.通过} 项通过 / {len(结.警告)} 条提醒 / "
              f"**{len(结.错误)} 项错误** —— 请先修上面的 ✗")
    else:
        print(f"  结果：{结.通过} 项全部通过"
              + (f"（另有 {len(结.警告)} 条提醒，不影响使用）" if 结.警告 else "，没有提醒"))
    print("=" * 74)
    return 1 if 结.错误 else 0


if __name__ == "__main__":
    raise SystemExit(main())
