"""
打补丁_中文字体.py —— 让面板能显示中文（把汉字字形并进官方那份 UI 字体）

★ 它解决什么问题
    官方 MuJoCo Studio 往 ImGui 字体图集里只装 Atkinson Hyperlegible（纯拉丁，362 个码位）
    + fontawesome。ImGui 遇到图集里没有的字符会回退画 `ImFont::FallbackChar`（默认 '?'），
    于是面板上任何中文都是一串 `?????`。

★ 为什么以前认为"做不到"，而其实做得到
    `软件/界面文字.py` 里写过："这个 Python 绑定没有任何字体接口，要 CJK 只能在 C++ 里
    AddFontFromFileTTF" —— 那句话对「运行时注入」成立（实测 dear_imgui 里跟字体有关的只有
    GetFontSize / GetFontTexUvWhitePixel / PopFont / SetWindowFontScale，连 IO.Fonts 都没有）。
    但它漏了一条路：**字体是按文件名从 assets/ 加载的，换文件不用碰二进制。**

    关键前提（已用 字体探针.py 实测坐实）：
      官方用的是 Dear ImGui 1.92.6 的**动态字体图集** —— 用到哪个码位就现烘焙哪个。
      所以只要文件里有汉字字形，面板就能显示，不需要预先声明 CJK 范围。

★ 判定证据（字体探针.py，实测数值）
    原始字体： CalcTextSize('中').x = 6.00 = CalcTextSize('?').x   ← 走回退字形
    补丁之后： CalcTextSize('中').x = 13.00 ≠ 6.00                 ← 拿到真汉字字形
    而且 5 组拉丁样本宽度（242/158/257/361/23）**逐位不变** → 拉丁观感没被改坏。

★ 做法（保留 Atkinson 的拉丁设计，只补汉字）
    ① 从 macOS 自带的 STHeiti Light 里子集化出需要的字（仓库用到的字 + GB2312 一级字库 + 符号）
       —— 选 STHeiti 是因为它和 Atkinson **同为 glyf 轮廓、同为 unitsPerEm=1000**，不用缩放。
       （Hiragino Sans GB / PingFang 是 CFF 轮廓，和 glyf 混merge 会失败；Arial Unicode 是 2048。）
    ② Atkinson 是可变字体（wght 200–800），Merger 会在 HVAR 的 VarStore 上炸
       → 先按**默认实例 wght=400** 静态化（官方二进制里没有任何 wght 引用，用的就是默认档）。
    ③ 两份字体都精简到**同一组表**再合并：Merger 的 mergeObjects 会把"只在一边存在的表"
       取成 NotImplemented，然后在比较时抛 TypeError。丢掉 GSUB/GPOS/GDEF 是安全的
       —— ImGui 用 stb_truetype 渲染，本来就不做 OpenType 形状化/字距调整。

★ 许可（为什么生成物**不入库**）
    · Atkinson Hyperlegible 是 SIL OFL 1.1（Braille Institute）
    · STHeiti 是 Apple 随 macOS 附带的字体，**许可只允许在 macOS 上使用**
    把两者合并出来的文件提交进仓库 = 再分发 Apple 的字体数据，有许可风险。
    所以本工具**在你本机现场生成**、只写进 .venv，生成物与原字体备份都在 .gitignore 里。

用法：
    .venv/bin/python 工具/打补丁_中文字体.py --状态     # 看现在是不是补丁状态
    .venv/bin/python 工具/打补丁_中文字体.py --建立     # 本机生成合并字体（需要 fontTools）
    .venv/bin/python 工具/打补丁_中文字体.py --安装     # 备份官方字体 → 装上合并字体
    .venv/bin/python 工具/打补丁_中文字体.py            # --建立 + --安装
    .venv/bin/python 工具/打补丁_中文字体.py --还原     # 还原官方字体（面板重新变回纯 ASCII）

验证补丁真的生效（要开一次窗口，约 1 秒）：
    .venv/bin/python 优化（软件优化的报告都放这里面来）/验证/字体探针.py
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys

本目录 = os.path.dirname(os.path.abspath(__file__))
包根 = os.path.dirname(本目录)

# 补丁工作区（都在 .gitignore 里）
补丁目录 = os.path.join(本目录, "字体补丁")
备份目录 = os.path.join(补丁目录, "官方原字体")
生成目录 = os.path.join(补丁目录, "生成物")

# 要补的字体（主字体 + 等宽字体）。fontawesome 不动：它是图标，upem=1792，且不需要汉字。
要补的字体 = ["AtkinsonHyperlegibleNext[wght].ttf", "AtkinsonHyperlegibleMono-Regular.ttf"]
只备份不补 = ["fontawesome-webfont.ttf"]

# 合并后保留的表：两边都精简成这一组，Merger 才不会在 NotImplemented 上炸
保留表 = {"OS/2", "cmap", "glyf", "head", "hhea", "hmtx", "loca", "maxp", "name", "post"}

# 汉字来源（macOS 自带；glyf 轮廓 + upem=1000，与 Atkinson 一致 → 不用缩放）
汉字源 = "/System/Library/Fonts/STHeiti Light.ttc"

# 仓库里要扫的文件类型（把实际用到的字都收进来，避免"面板上刚好缺那个字"）
扫的文件后缀 = (".py", ".md", ".json", ".txt", ".sh")
扫的目录 = ["软件", "算法库", "项目", "工具", "文档", "优化（软件优化的报告都放这里面来）"]
扫的文件 = ["使用说明.md", "使用手册.md", "CHANGELOG.md"]

# 除了汉字本身，还想要这些符号/标点（都来自 STHeiti，同 upem，零风险）
#   ★ 不含 ✓(U+2713) / ✗(U+2717)：STHeiti 没有，macOS 上其它有的字体全是 upem=2048，
#     混进来要缩放，风险大于收益。面板上继续用 ASCII 的 [ok]/[fail] 与 * 即可。
额外符号 = ("←→↑↓○●■□▲▼±°·…—–「」『』【】〔〕（）［］｛｝｜‖　・"
           "、。：；！？《》〈〉“”‘’％＃＠＆＊＋－／＝～")

CJK有字形 = re.compile(r"[\u4e00-\u9fff]")


def 资源目录() -> str:
    """官方字体所在的 assets 目录（跟着 .venv 里的 mujoco 包走）。"""
    import mujoco  # noqa: PLC0415
    包 = os.path.dirname(os.path.abspath(mujoco.__file__))
    return os.path.join(包, "experimental", "studio", "assets")


def 字体汉字数(路径: str) -> int:
    """这个字体文件里有多少个汉字码位（用来判断"打过补丁没有"）。"""
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return -1
    if not os.path.exists(路径):
        return -2
    try:
        cm = TTFont(路径, fontNumber=0).getBestCmap()
    except Exception:                                                    # noqa: BLE001
        # .ttc 需要指定序号，重试
        try:
            cm = TTFont(路径, fontNumber=None).getBestCmap()
        except Exception:                                                # noqa: BLE001
            return -3
    return sum(1 for cp in cm if 0x4e00 <= cp <= 0x9fff)


def 收集字符() -> set[str]:
    字: set[str] = set()
    模式 = re.compile(r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]")
    for 目录 in 扫的目录:
        p = os.path.join(包根, 目录)
        if not os.path.isdir(p):
            continue
        for dp, dn, fn in os.walk(p):
            dn[:] = [d for d in dn if d not in ("__pycache__", "字体补丁", "_字体补丁备份")]
            for f in fn:
                if f.endswith(扫的文件后缀):
                    try:
                        with open(os.path.join(dp, f), encoding="utf-8", errors="ignore") as fh:
                            字.update(模式.findall(fh.read()))
                    except Exception:                                    # noqa: BLE001
                        pass
    for f in 扫的文件:
        p = os.path.join(包根, f)
        if os.path.exists(p):
            字.update(模式.findall(open(p, encoding="utf-8", errors="ignore").read()))
    # GB2312 一级字库（3755 字）：覆盖绝大多数常用中文，避免"以后新写的文案缺字"
    for hi in range(0xB0, 0xD8):
        for lo in range(0xA1, 0xFF):
            try:
                字.add(bytes([hi, lo]).decode("gb2312"))
            except Exception:                                            # noqa: BLE001
                pass
    字.update(额外符号)
    return 字


def 建_子集(出路径: str) -> int:
    """从 STHeiti 子集化出需要的字，写成一份临时 ttf。返回字数。"""
    from fontTools import subset                                            # noqa: PLC0415
    from fontTools.ttLib import TTFont                                      # noqa: PLC0415
    字 = 收集字符()
    src = TTFont(汉字源, fontNumber=0)
    opt = subset.Options()
    opt.name_IDs = ["*"]
    opt.notdef_outline = True
    # 丢掉 OpenType 形状化与 hinting 表：ImGui 用 stb_truetype，本来就不用它们，
    # 而且留着会和 Atkinson 的表集合不一致（见文件头 ③）
    opt.drop_tables += ["GSUB", "GPOS", "GDEF", "morx", "kerx", "meta",
                        "bsln", "cvt ", "fpgm", "hdmx", "vhea", "vmtx", "feat"]
    s = subset.Subsetter(options=opt)
    s.populate(unicodes=[ord(c) for c in 字])
    s.subset(src)
    精简(src)
    src.save(出路径)
    return len(字)


def 精简(font) -> None:
    """只留下 保留表 —— 让参与合并的两份字体表集合完全一致。"""
    for t in [t for t in font.keys() if t not in 保留表 and t != "GlyphOrder"]:
        del font[t]


def 建_一份(源路径: str, 子集路径: str, 出路径: str) -> None:
    """把一份官方字体 + 汉字子集 合并，写到出路径。"""
    from fontTools.merge import Merger                                      # noqa: PLC0415
    from fontTools.ttLib import TTFont                                      # noqa: PLC0415

    主 = TTFont(源路径)
    if "fvar" in 主:
        # 可变字体 → 默认实例静态化。不静态化的话 Merger 会在 HVAR 的 VarStore 上抛
        # AttributeError: type object 'VarStore' has no attribute 'mergeMap'
        from fontTools.varLib import instancer                              # noqa: PLC0415
        轴 = {a.axisTag: a.defaultValue for a in 主["fvar"].axes}
        主 = instancer.instantiateVariableFont(主, 轴, inplace=False)
    精简(主)
    临时 = 出路径 + ".main.ttf"
    主.save(临时)
    try:
        Merged = Merger().merge([临时, 子集路径])
        Merged.save(出路径)
    finally:
        if os.path.exists(临时):
            os.remove(临时)


def 建立(打印=print) -> int:
    """生成本机的合并字体（写到 工具/字体补丁/生成物/）。返回失败数。"""
    os.makedirs(生成目录, exist_ok=True)
    子集 = os.path.join(生成目录, "_cjk_subset.ttf")
    try:
        字数 = 建_子集(子集)
    except ImportError:
        打印("✗ 需要 fontTools。当前解释器里没有：")
        打印(f"    {sys.executable}")
        打印("  解决：.venv/bin/pip install fonttools    （或把 fonttools 的 wheel 放进 离线依赖/）")
        return 1
    打印(f"  ① 汉字子集：{字数} 个字符 → {os.path.getsize(子集) / 1024:.0f} KB（源：{汉字源}）")
    源目录 = 资源目录()
    失败 = 0
    for 名 in 要补的字体:
        源 = os.path.join(备份目录 if os.path.exists(os.path.join(备份目录, 名)) else 源目录, 名)
        出 = os.path.join(生成目录, 名)
        try:
            建_一份(源, 子集, 出)
            打印(f"  ② 合并 {名} → {os.path.getsize(出) / 1024:.0f} KB"
                 f"（汉字 {字体汉字数(出)} 个）")
        except Exception as 异常:                                        # noqa: BLE001
            失败 += 1
            打印(f"  ✗ 合并 {名} 失败：{type(异常).__name__}: {异常}")
    os.remove(子集)
    if not 失败:
        打印(f"  生成物在 {生成目录}")
    return 失败


def 安装(打印=print) -> int:
    """备份官方字体，然后把合并字体装进 assets。"""
    源目录 = 资源目录()
    os.makedirs(备份目录, exist_ok=True)

    # ---- ① 备份官方原字体（只在确认"当前资产是原版"时做，避免把补丁版当原版备份）----
    for 名 in 要补的字体 + 只备份不补:
        现 = os.path.join(源目录, 名)
        备 = os.path.join(备份目录, 名)
        if os.path.exists(备):
            continue
        if not os.path.exists(现):
            if 名 in 只备份不补:
                continue
            打印(f"✗ 找不到官方字体：{现}")
            return 1
        if 名 in 要补的字体:
            汉字 = 字体汉字数(现)
            if 汉字 > 0:
                打印(f"✗ {名} 里已经有 {汉字} 个汉字 —— 看起来已经是补丁版了，"
                     f"拒绝把它当原版备份。先 --还原 或手工清掉 {备份目录}")
                return 1
        shutil.copy2(现, 备)
        打印(f"  ① 已备份官方原字体 → {os.path.relpath(备, 包根)}")

    # ---- ② 装合并字体 ----
    失败 = 0
    for 名 in 要补的字体:
        出 = os.path.join(生成目录, 名)
        if not os.path.exists(出):
            打印(f"✗ 还没有生成物 {os.path.relpath(出, 包根)} —— 先跑 --建立")
            失败 += 1
            continue
        shutil.copy2(出, os.path.join(源目录, 名))
        打印(f"  ② 已安装 {名}（汉字 {字体汉字数(os.path.join(源目录, 名))} 个）")
    return 失败


def 还原(打印=print) -> int:
    """把官方原字体放回去。"""
    源目录 = 资源目录()
    if not os.path.isdir(备份目录):
        打印(f"✗ 没有备份目录 {备份目录} —— 只能重建环境：rm -rf .venv && bash 工具/重建环境.sh")
        return 1
    n = 0
    for 名 in 要补的字体 + 只备份不补:
        备 = os.path.join(备份目录, 名)
        if os.path.exists(备):
            shutil.copy2(备, os.path.join(源目录, 名))
            打印(f"  已还原 {名}")
            n += 1
    if not n:
        打印("✗ 备份目录是空的")
        return 1
    打印("✓ 已还原官方字体。面板从此只画 ASCII（中文会重新变成 ?）")
    return 0


def 状态(打印=print) -> int:
    try:
        源目录 = 资源目录()
    except Exception as 异常:                                            # noqa: BLE001
        打印(f"✗ 找不到 mujoco 包：{异常}")
        return 1
    打印(f"assets：{源目录}")
    打印("")
    打印(f"  {'字体':<40}{'汉字码位':>9}  状态")
    for 名 in 要补的字体 + 只备份不补:
        路径 = os.path.join(源目录, 名)
        汉字 = 字体汉字数(路径)
        if 名 in 只备份不补:
            态 = "（不需补丁：图标字体）"
        elif 汉字 > 0:
            态 = "★ 已打补丁（面板能显示中文）"
        elif 汉字 == 0:
            态 = "官方原版（面板只能画 ASCII）"
        else:
            态 = f"读不出来（{汉字}）"
        打印(f"  {名:<40}{汉字:>9}  {态}")
    有生成 = os.path.isdir(生成目录) and any(
        os.path.exists(os.path.join(生成目录, 名)) for 名 in 要补的字体)
    有备份 = os.path.isdir(备份目录)
    打印("")
    打印(f"  生成物：{'有' if 有生成 else '无'}    备份：{'有' if 有备份 else '无'}")
    打印(f"  验证：.venv/bin/python 优化（软件优化的报告都放这里面来）/验证/字体探针.py")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="把汉字字形并进官方 UI 字体，让面板能显示中文（不改二进制）")
    ap.add_argument("--状态", action="store_true", help="看当前是不是补丁状态")
    ap.add_argument("--建立", action="store_true", help="本机生成合并字体（需要 fontTools）")
    ap.add_argument("--安装", action="store_true", help="备份官方字体并装上合并字体")
    ap.add_argument("--还原", action="store_true", help="还原官方字体")
    args = ap.parse_args()

    print("=" * 78)
    print("  中文字体补丁 —— 让面板能显示中文")
    print("=" * 78)

    if args.状态:
        return 状态()
    if args.还原:
        return 还原()

    要建 = args.建立 or not (args.建立 or args.安装)
    要装 = args.安装 or not (args.建立 or args.安装)

    if 要建:
        print("\n【① 建立】")
        if 建立():
            return 1
    if 要装:
        print("\n【② 安装】")
        if 安装():
            return 1

    print()
    状态()
    print("\n★ 补丁只在**本机**生效，且 .venv 一重建就没了（工具/重建环境.sh 里已挂上自动重打）。")
    print("  想在界面上看到中文，把要显示的中文交给 imgui 画即可 —— 但**终端仍是中文、"
          "面板原来只允许 ASCII** 那套纪律现在可以放宽了（见 软件/界面文字.py）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
