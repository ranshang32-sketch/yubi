"""
导入模型.py —— 从 MuJoCo Menagerie 导入机器人模型，并自动生成"扭矩接口变体"

★ 为什么需要"扭矩接口变体"（这是本项目的一个硬约束）：
    驭臂的控制插件往 `event.data.ctrl[:]` 里写的是**关节力矩**（N·m）。
    但 menagerie 的模型默认用的是**位置伺服**：
        <general gainprm="2000" biasprm="0 -2000 -400"/>   →   τ = kp·(ctrl − q) − kd·q̇
    这种模型的 ctrl 是"目标关节角"，不是力矩。直接拿它跑我们的 PD 插件，
    控制量会被当成"目标角度"，机械臂行为完全不对。
    所以每个导入的模型都会额外生成一个 `<模型>_torque.xml`：把执行器换成
        <motor ctrlrange="-上限 上限"/>                        →   τ = ctrl（力矩接口）
    本项目默认的 `ur5e_torque.xml` 就是这么来的。

★ 另一条硬约束：`nu` 必须等于 `nv`
    `关节pd控制.py` 的算法是 `数据.ctrl[:] = KP*误差 - KD*数据.qvel + 数据.qfrc_bias`，
    `qvel`/`qfrc_bias` 的长度是 nv，所以 ctrl 的长度必须是 nv。
    但有些模型带夹爪（Panda 的 `panda.xml` 是 nq=9/nu=8；xArm7 带 gripper），
    长度对不上，插件会直接抛广播错误。
    解决办法：**优先用 menagerie 自带的 `<模型>_nohand.xml`**，并且扭矩变体
    **只为"关节类执行器"生成 motor**（丢掉 tendon/夹爪执行器），保证 nu == nv == 自由度。

用法：
    # 列出可导入的机械臂（24 个，全部是 MIT / BSD-3 / Apache-2.0 许可）
    .venv/bin/python 工具/导入模型.py --列表

    # 导入指定的几个
    .venv/bin/python 工具/导入模型.py franka_emika_panda universal_robots_ur10e

    # 导入清单里全部 24 个机械臂（约 40 MB 下载 / 250 MB 解包）
    .venv/bin/python 工具/导入模型.py --全部

    # 已经下过、想重新生成扭矩变体
    .venv/bin/python 工具/导入模型.py franka_emika_panda --只生成扭矩

    # 换下载通道（默认走 gh-proxy 代理，因为国内直连 GitHub 常常不通）
    .venv/bin/python 工具/导入模型.py ... --直连
    .venv/bin/python 工具/导入模型.py ... --代理 https://gh-proxy.com/

网络：GitHub 直连不通时用 `--代理`（默认 https://gh-proxy.com/ ）。不需要 pip 装任何东西。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

本目录 = os.path.dirname(os.path.abspath(__file__))
包根 = os.path.normpath(os.path.join(本目录, ".."))
模型目录 = os.path.join(包根, "模型")
清单路径 = os.path.join(本目录, "模型清单.json")
库索引路径 = os.path.join(模型目录, "模型库.json")

# ---------------------------------------------------------------------------
# 模型自身没给 forcerange 时，用这里的实测/手册扭矩上限（N·m）兜底
#   来源：厂家公开的关节峰值扭矩指标（只用于把位置伺服换成力矩接口时限幅，不影响动力学）
#   ★ 单位是 N·m，顺序与模型里的关节顺序一致
# ---------------------------------------------------------------------------
扭矩上限补充表: dict[str, list[float]] = {
    # KUKA LBR iiwa 14 R820：A1/A2 320、A3/A4 176、A5 110、A6/A7 40
    "kuka_iiwa_14": [320.0, 320.0, 176.0, 176.0, 110.0, 40.0, 40.0],
}

# ---------------------------------------------------------------------------
# 关节"电枢惯量"（armature）兜底值
#
# ★ 为什么必须补（实测踩过）：
#   KUKA iiwa14 的 menagerie 模型里 `<joint>` 既没有 armature 也没有 damping
#   （UR5e / Panda 都有 armature="0.1"）。原模型能稳，是因为它用**位置伺服**
#   （biasprm 给了 kd=200）——那个阻尼把"腕部关节惯量几乎为 0"这件事盖住了。
#   一旦换成力矩电机、用我们默认的 KP=200/KD=30、步长 0.002 s，腕关节就变成
#   数值发散（实测末误差 130°，机械臂乱甩）。
#   补上 armature=0.1（等效于减速器/转子折算到关节侧的惯量，真机本来就有，
#   menagerie 自己的 UR5e/Panda 也这么写）之后：实测末误差 0.0000°。
#
#   注意：只在**原值为 0 且该关节被我们驱动**时才补，不动其它关节。
# ---------------------------------------------------------------------------
默认电枢惯量 = 0.1


def 读清单() -> dict:
    if not os.path.exists(清单路径):
        raise SystemExit(
            f"✗ 找不到模型清单：{清单路径}\n"
            f"  这个文件记录了 menagerie 各模型的下载地址与 sha256，是导入工具的依据。")
    with open(清单路径, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 下载
# ---------------------------------------------------------------------------
def 下载(地址: str, 目标: str, 代理前缀: str = "") -> None:
    """下载到目标路径（带进度百分比）。代理前缀用于 gh-proxy 这类反代。"""
    完整 = (代理前缀 + 地址) if 代理前缀 else 地址
    print(f"  ↓ {完整}")
    请求 = urllib.request.Request(完整, headers={"User-Agent": "yubi-import/1.0"})
    上次 = -1
    with urllib.request.urlopen(请求, timeout=120) as 响应, open(目标, "wb") as 输出:
        总长 = int(响应.headers.get("Content-Length") or 0)
        while True:
            块 = 响应.read(1 << 16)
            if not 块:
                break
            输出.write(块)
            if 总长:
                百分比 = int(输出.tell() * 100 / 总长)
                if 百分比 // 10 != 上次 // 10:
                    上次 = 百分比
                    print(f"      {百分比:3d}%  ({输出.tell()/1e6:.1f}/{总长/1e6:.1f} MB)", flush=True)


def 校验(路径: str, 期望: str) -> bool:
    h = hashlib.sha256()
    with open(路径, "rb") as f:
        for 块 in iter(lambda: f.read(1 << 20), b""):
            h.update(块)
    return h.hexdigest().lower() == 期望.lower()


# ---------------------------------------------------------------------------
# 生成扭矩变体
# ---------------------------------------------------------------------------
def _选基础XML(名字: str, 目录: str, 信息: dict) -> str:
    """挑扭矩变体的基础 XML。

    优先 `*_nohand.xml`：它去掉了夹爪，能让 nu == nv == 自由度，
    正好符合我们控制插件"ctrl 长度 = qvel 长度"的假设。
    """
    默认 = 信息["默认模型"]
    候选 = []
    if f"{默认}_nohand" in 信息.get("入口", []):
        候选.append(f"{默认}_nohand.xml")
    候选 += [f"{默认}.xml"]
    for c in 候选:
        p = os.path.join(目录, c)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(f"{目录} 里找不到 {默认}.xml")


def 生成扭矩变体(名字: str, 目录: str, 信息: dict, 扭矩上限: list[float] | None,
                 打印=print) -> tuple[str, dict]:
    """把位置伺服换成力矩电机，输出 `<模型>_torque.xml`。返回 (路径, 统计信息)。"""
    import mujoco

    基础 = _选基础XML(名字, 目录, 信息)
    模型 = mujoco.MjModel.from_xml_path(基础)

    # ---- 解析出每个执行器的"传动对象"和"扭矩上限"（forcerange 已经把 class 继承算好了）----
    执行器 = []
    for i in range(模型.nu):
        名称 = mujoco.mj_id2name(模型, mujoco.mjtObj.mjOBJ_ACTUATOR, i) or f"act{i}"
        类型 = 模型.actuator_trntype[i]
        目标号 = int(模型.actuator_trnid[i, 0])
        if 类型 == mujoco.mjtTrn.mjTRN_JOINT:
            关节 = mujoco.mj_id2name(模型, mujoco.mjtObj.mjOBJ_JOINT, 目标号)
            上限 = [float(x) for x in 模型.actuator_forcerange[i]]
            执行器.append({"名称": 名称, "关节": 关节, "上限": 上限, "是关节": True})
        else:
            执行器.append({"名称": 名称, "关节": None, "上限": None, "是关节": False})

    关节执行器 = [e for e in 执行器 if e["是关节"]]
    丢掉 = [e["名称"] for e in 执行器 if not e["是关节"]]

    # ---- 决定每个关节执行器的扭矩上限 ----
    上限列表 = []
    for e in 关节执行器:
        lo, hi = e["上限"]
        if abs(lo) < 1e-9 and abs(hi) < 1e-9:          # 模型没给 → 用补充表 / 命令行
            if 扭矩上限:
                值 = float(扭矩上限[len(上限列表)])
                lo, hi = -abs(值), abs(值)
            else:
                raise SystemExit(
                    f"✗ {名字} 的执行器「{e['名称']}」没有 forcerange（扭矩无限），"
                    f"无法自动生成扭矩变体。\n"
                    f"  请在 工具/导入模型.py 的 扭矩上限补充表 里为 {名字} 补一组关节扭矩上限，"
                    f"或用 --扭矩上限 320,320,176,176,110,40,40 指定。")
        上限列表.append(max(abs(lo), abs(hi)))

    # ---- 找出"电枢惯量为 0 且被我们驱动"的关节，准备补上默认值 ----
    补电枢 = []
    for e in 关节执行器:
        关节号 = mujoco.mj_name2id(模型, mujoco.mjtObj.mjOBJ_JOINT, e["关节"])
        if 关节号 < 0:
            continue
        自由度序 = int(模型.jnt_dofadr[关节号])
        if 自由度序 >= 0 and float(模型.dof_armature[自由度序]) < 1e-9:
            补电枢.append(e["关节"])

    # ---- XML 手术：换掉 <actuator>，修好 <keyframe> ----
    #   insert_comments=True 保留原文件的注释（menagerie 的 XML 注释很有价值）
    解析器 = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    树 = ET.parse(基础, parser=解析器)
    根 = 树.getroot()

    执行器节点 = 根.find("actuator")
    if 执行器节点 is None:
        raise SystemExit(f"✗ {基础} 里没有 <actuator> 段")
    for 子 in list(执行器节点):
        执行器节点.remove(子)

    for e, 上限 in zip(关节执行器, 上限列表):
        电机 = ET.SubElement(执行器节点, "motor")
        电机.set("name", str(e["名称"]))
        电机.set("joint", str(e["关节"]))
        电机.set("gear", "1")
        # ctrlrange = 扭矩上限：MuJoCo 会把 ctrl 夹到这个范围内，等价于力矩限幅
        电机.set("ctrlrange", f"{-上限:g} {上限:g}")

    # 补电枢惯量（见上面 默认电枢惯量 的说明：不补的话某些模型力矩模式下会发散）
    if 补电枢:
        需要 = set(补电枢)
        for 关节节点 in 根.iter("joint"):
            if 关节节点.get("name") in 需要:
                关节节点.set("armature", f"{默认电枢惯量:g}")

    # keyframe 的 ctrl 长度变了，必须重写（否则加载时报尺寸不符）
    新nu = len(关节执行器)
    关键帧 = 根.find("keyframe")
    if 关键帧 is not None:
        for 帧 in 关键帧.findall("key"):
            if 帧.get("ctrl") is not None:
                帧.set("ctrl", " ".join(["0"] * 新nu))

    ET.indent(树, space="  ")                            # 让输出可读
    输出路径 = os.path.join(目录, f"{信息['默认模型']}_torque.xml")
    头部 = (
        f"<!-- ============================================================================\n"
        f"     {os.path.basename(输出路径)} —— {信息['显示名']} 的**力矩接口**变体\n"
        f"     由 工具/导入模型.py 自动生成，**请勿手工编辑**（重新导入会覆盖）。\n"
        f"     来源模型 : {os.path.relpath(基础, 包根)}\n"
        f"     改了什么 : ① 执行器 <general> 位置伺服 → <motor> 力矩电机（ctrl 就是关节力矩 N·m）\n"
        f"                ② 丢掉非关节执行器（{'、'.join(丢掉) if 丢掉 else '无'}）→ 保证 nu == nv\n"
        f"                ③ keyframe 的 ctrl 重写为 {新nu} 个 0\n"
        f"                ④ 补电枢惯量 armature={默认电枢惯量:g}："
        f"{'、'.join(补电枢) if 补电枢 else '（本模型已自带，无需补）'}\n"
        f"     扭矩上限 : {', '.join(f'{x:g}' for x in 上限列表)} N·m\n"
        f"     为什么   : 驭臂的控制插件往 data.ctrl[:] 写的是力矩，位置伺服模型会把力矩\n"
        f"                当成目标角度，行为完全不对。④ 是因为位置伺服的 kd 掩盖了\n"
        f"                \"关节电枢惯量为 0\"，换成力矩接口后会数值发散。\n"
        f"     详见     : 工具/导入模型.py 顶部说明\n"
        f"     ============================================================================ -->\n"
    )
    tree_xml = ET.tostring(根, encoding="unicode")
    with open(输出路径, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n')
        f.write(头部)
        f.write(tree_xml + "\n")

    统计 = {
        "基础XML": os.path.relpath(基础, 包根),
        "扭矩对象": len(关节执行器),
        "丢掉执行器": 丢掉,
        "扭矩上限": 上限列表,
        "补电枢惯量": 补电枢,
    }
    return 输出路径, 统计


# ---------------------------------------------------------------------------
# 验证：扭矩变体能不能被我们的控制律控制住
# ---------------------------------------------------------------------------
def 验证扭矩变体(路径: str, 步数: int = 1500) -> dict:
    """用与 `关节pd控制.py` 完全相同的 PD 算式跑一段无窗口仿真，看是否收敛。"""
    import mujoco
    import numpy as np

    模型 = mujoco.MjModel.from_xml_path(路径)
    数据 = mujoco.MjData(模型)
    键 = mujoco.mj_name2id(模型, mujoco.mjtObj.mjOBJ_KEY, "home")
    if 键 >= 0:
        mujoco.mj_resetDataKeyframe(模型, 数据, 键)
    mujoco.mj_forward(模型, 数据)

    if not (模型.nu == 模型.nv == 模型.nq):
        return {"通过": False, "原因": f"nu={模型.nu} nv={模型.nv} nq={模型.nq}（需要三者相等）"}

    目标 = 数据.qpos.copy()
    目标[1] += 0.35                      # 和默认插件一样：抬一下肩
    KP, KD = 200.0, 30.0
    最大误差 = 0.0
    for _ in range(步数):
        误差 = 目标 - 数据.qpos
        数据.ctrl[:] = KP * 误差 - KD * 数据.qvel + 数据.qfrc_bias
        mujoco.mj_step(模型, 数据)
        最大误差 = max(最大误差, float(np.abs(误差).max()))
    末误差 = float(np.abs(目标 - 数据.qpos).max())
    # 判定"收敛"：末误差 < 0.5°。
    #   为什么不是更严：模型里若带关节阻尼/摩擦，纯 PD（无积分项）本来就会有微小静差。
    #   实测参考：Panda 0.0000°、UR10e 0.0100°、xArm7 0.139°（都在正常范围）；
    #             发散的话会是几十到上百度的量级，一眼可分。
    return {
        "通过": bool(np.isfinite(末误差) and 末误差 < np.radians(0.5)),
        "末误差_度": float(np.degrees(末误差)),
        "历史最大误差_度": float(np.degrees(最大误差)),
    }


# ---------------------------------------------------------------------------
# 模型库索引（界面选模型时会读它）
# ---------------------------------------------------------------------------
def _识别许可(目录: str) -> str:
    """读模型目录里的 LICENSE 文件，判断许可类型（清单里有准确值时优先用清单）。"""
    for 名 in ("LICENSE", "license", "LICENCE"):
        p = os.path.join(目录, 名)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8", errors="replace") as f:
            全文 = f.read()
        if "Apache License" in 全文 or "apache.org/licenses/LICENSE-2.0" in 全文:
            return "Apache-2.0"
        if "BSD" in 全文 or "Redistribution and use in source and binary forms" in 全文:
            # 三条款 vs 二条款：看有没有"endorse"那一条
            return "BSD-3-Clause" if "endorse" in 全文 or "promote" in 全文 else "BSD-2-Clause"
        if "MIT License" in 全文 or "Permission is hereby granted, free of charge" in 全文:
            return "MIT"
        return "见目录内 LICENSE"
    return "未知"


def 更新库索引(打印=print) -> str:
    """扫描 模型/ 目录，重建 模型库.json（界面选模型时会读它）。"""
    try:
        清单模型 = 读清单()["模型"]
    except SystemExit:
        清单模型 = {}

    条目 = []
    for 子 in sorted(os.listdir(模型目录)):
        目录 = os.path.join(模型目录, 子)
        if not os.path.isdir(目录) or 子.startswith("."):
            continue
        扭矩 = sorted(f for f in os.listdir(目录) if f.endswith("_torque.xml"))
        全部XML = sorted(f for f in os.listdir(目录) if f.endswith(".xml"))
        if not 全部XML:
            continue
        主XML = 扭矩[0] if 扭矩 else 全部XML[0]
        自由度 = 执行器数 = -1
        可控制 = False
        try:
            import mujoco
            模型 = mujoco.MjModel.from_xml_path(os.path.join(目录, 主XML))
            自由度, 执行器数 = int(模型.nq), int(模型.nu)
            # "可控制" = 本项目控制插件能直接驱动它：ctrl 长度必须等于 qvel 长度
            可控制 = bool(模型.nu == 模型.nv == 模型.nq and 模型.nu > 0)
        except Exception:                                        # noqa: BLE001
            pass

        信息 = 清单模型.get(子, {})
        许可 = 信息.get("许可") or _识别许可(目录)
        if 可控制 and 自由度 >= 6:
            类别 = "arm"
        elif 可控制 and 自由度 in (1, 2):
            类别 = "gripper"
        elif 可控制:
            类别 = "other"
        else:
            类别 = "不可直接控制"          # 例如位置伺服模型、带夹爪导致 nu != nv 的模型
        条目.append({
            "标识": 子,
            "显示名": 信息.get("显示名") or 子,
            "类别": 类别,
            "目录": 子,
            "扭矩模型": f"{子}/{主XML}",
            "可控制": 可控制,
            "自由度": 自由度,
            "执行器数": 执行器数,
            "许可": 许可,
            "模型文件": [f"{子}/{f}" for f in 全部XML],
        })

    索引 = {
        "说明": ("驭臂的模型库索引，由 工具/导入模型.py 自动生成。"
                 "『扭矩模型』是推荐加载的那个 —— 它的 ctrl 就是关节力矩，能被本项目控制插件直接驱动；"
                 "『可控制』= true 表示 nu==nv==nq（控制插件写 ctrl 的前提）。"
                 "界面按『类别=arm』列出可选机械臂。"),
        "根目录": "模型",
        "模型": 条目,
    }
    with open(库索引路径, "w", encoding="utf-8") as f:
        json.dump(索引, f, ensure_ascii=False, indent=2)
    臂 = sum(1 for e in 条目 if e["类别"] == "arm")
    打印(f"  ✓ 已更新模型库索引：模型/模型库.json（{len(条目)} 个模型，其中可控制机械臂 {臂} 个）")
    return 库索引路径


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def 导入一个(名字: str, 信息: dict, 代理前缀: str, 只生成扭矩: bool,
             扭矩上限: list[float] | None, 强制: bool, 打印=print) -> dict:
    目录 = os.path.join(模型目录, 名字)
    打印(f"\n【{名字}】{信息['显示名']}　{信息['许可']}　"
         f"下载 {信息['下载字节']/1e6:.1f} MB / 解包 {信息['解包字节']/1e6:.1f} MB")

    if not 只生成扭矩:
        if os.path.isdir(目录) and not 强制:
            现有 = [f for f in os.listdir(目录) if f.endswith((".xml", ".stl", ".obj"))]
            if 现有:
                打印(f"  ℹ 已存在（{len(现有)} 个模型文件），跳过下载；要重下加 --强制")
        else:
            地址 = f"{信息.get('资产基地址') or 清单基地址}/{信息['资产']}"
            with tempfile.TemporaryDirectory(prefix="小软件导入_") as 临时:
                包 = os.path.join(临时, 信息["资产"])
                下载(地址, 包, 代理前缀)
                if not 校验(包, 信息["sha256"]):
                    raise SystemExit(f"  ✗ sha256 校验失败：{信息['资产']}"
                                     f"\n     可能是代理返回了错误页，换 --直连 或别的 --代理 再试")
                打印("  ✓ sha256 校验通过")
                os.makedirs(模型目录, exist_ok=True)
                with tarfile.open(包, "r:xz") as tf:
                    try:
                        # filter="data" 是 Python 3.12+ 的安全解包参数；
                        # 3.10 会 TypeError，所以退化为普通解包
                        tf.extractall(模型目录, filter="data")
                    except TypeError:
                        tf.extractall(模型目录)
            打印(f"  ✓ 已解包到 模型/{名字}/")

    扭矩路径, 统计 = 生成扭矩变体(名字, 目录, 信息, 扭矩上限, 打印)
    打印(f"  ✓ 扭矩变体：模型/{os.path.relpath(扭矩路径, 模型目录)}"
         f"（{统计['扭矩对象']} 个力矩电机，上限 "
         f"{'/'.join(f'{x:g}' for x in 统计['扭矩上限'])} N·m）")
    if 统计["丢掉执行器"]:
        打印(f"    丢了非关节执行器：{'、'.join(统计['丢掉执行器'])}（保证 nu == nv）")

    结果 = 验证扭矩变体(扭矩路径)
    if 结果["通过"]:
        打印(f"  ✓ 闭环验证通过：PD 控制后残差 {结果['末误差_度']:.4f}°"
             f"（历史最大 {结果['历史最大误差_度']:.1f}°）")
    else:
        打印(f"  ✗ 闭环验证未通过：{结果.get('原因') or 结果}")
    return {"名字": 名字, "统计": 统计, "验证": 结果}


清单基地址 = ""


def main(argv: list[str]) -> int:
    global 清单基地址
    ap = argparse.ArgumentParser(description="从 MuJoCo Menagerie 导入机械臂模型")
    ap.add_argument("模型", nargs="*", help="要导入的模型标识（见 --列表）")
    ap.add_argument("--列表", action="store_true", help="列出清单里可导入的模型")
    ap.add_argument("--索引", action="store_true", help="只重建 模型/模型库.json（不下载）")
    ap.add_argument("--全部", action="store_true", help="导入清单里全部模型")
    ap.add_argument("--代理", default=None,
                    help="下载代理前缀（默认取清单里的『代理前缀』；传空字符串表示直连）")
    ap.add_argument("--直连", action="store_true", help="不用代理，直连 GitHub")
    ap.add_argument("--只生成扭矩", action="store_true", help="不下载，只重新生成扭矩变体")
    ap.add_argument("--扭矩上限", default=None,
                    help="模型没给 forcerange 时用的扭矩上限，逗号分隔，如 320,320,176,176,110,40,40")
    ap.add_argument("--强制", action="store_true", help="已存在也重新下载")
    args = ap.parse_args(argv)

    清单 = 读清单()
    清单基地址 = 清单["资产基地址"]
    全部 = 清单["模型"]

    if args.索引:
        print("重建模型库索引…")
        更新库索引()
        return 0

    if args.列表:
        print("=" * 96)
        print(f"可导入的机械臂（{len(全部)} 个）—— 来源：{清单['来源']}")
        print("=" * 96)
        print(f"  {'标识':26s}{'名称':30s}{'许可':15s}{'下载':>7s}{'解包':>8s}")
        for 名, 信息 in sorted(全部.items(), key=lambda kv: kv[1]["显示名"]):
            已装 = "✓" if os.path.isdir(os.path.join(模型目录, 名)) else " "
            print(f"  {已装}{名:25s}{信息['显示名'][:28]:30s}{信息['许可']:15s}"
                  f"{信息['下载字节']/1e6:6.1f}M{信息['解包字节']/1e6:7.1f}M")
        print(f"\n  合计下载 {sum(v['下载字节'] for v in 全部.values())/1e6:.0f} MB、"
              f"解包 {sum(v['解包字节'] for v in 全部.values())/1e6:.0f} MB")
        print(f"  协议：全部为 MIT / BSD-3-Clause / Apache-2.0，可自由使用与分发")
        return 0

    要导入 = list(args.模型)
    if args.全部:
        要导入 = sorted(全部)
    if not 要导入:
        ap.print_help()
        return 1

    未知 = [n for n in 要导入 if n not in 全部]
    if 未知:
        print(f"✗ 清单里没有这些模型：{未知}")
        print("  用 --列表 看可用的标识。")
        return 2

    代理前缀 = "" if args.直连 else (清单.get("代理前缀", "") if args.代理 is None else args.代理)
    扭矩上限 = ([float(x) for x in args.扭矩上限.replace("，", ",").split(",") if x.strip()]
                if args.扭矩上限 else None)

    print("=" * 96)
    print(f"导入机械臂模型 → {模型目录}")
    print(f"下载通道：{'直连 GitHub' if not 代理前缀 else 代理前缀}")
    print("=" * 96)

    成功, 失败 = [], []
    for 名 in 要导入:
        补充 = 扭矩上限 or 扭矩上限补充表.get(名)
        try:
            成功.append(导入一个(名, 全部[名], 代理前缀, args.只生成扭矩, 补充, args.强制))
        except SystemExit as e:
            失败.append((名, str(e)))
            print(f"  ✗ 跳过：{e}")
        except Exception as e:                                  # noqa: BLE001
            失败.append((名, f"{type(e).__name__}: {e}"))
            print(f"  ✗ 失败：{type(e).__name__}: {e}")

    print()
    更新库索引()

    print()
    print("=" * 96)
    print(f"完成：成功 {len(成功)} 个、失败 {len(失败)} 个")
    for r in 成功:
        print(f"  ✓ {r['名字']:24s} 扭矩模型 {'通过' if r['验证']['通过'] else '未通过'}")
    for 名, 因 in 失败:
        print(f"  ✗ {名:24s} {因[:100]}")
    print()
    print("  加载某个模型：")
    print("    ./.venv/bin/python 软件/主程序.py --模型 模型/<标识>/<默认模型>_torque.xml")
    return 0 if not 失败 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
