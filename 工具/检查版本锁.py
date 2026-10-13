"""
检查版本锁.py —— 当前环境是否与"实测跑通过"的版本一致

为什么要有它（第 3 步 C1）：
    官方把插件系统所在模块标为 experimental，官方升级会直接冲击外壳。
    我们把实测通过的版本钉在 `requirements.lock` 里，用这个脚本随时核对：
      · 版本一致 → 放心
      · 版本不同 → 明确警告（并告出怎么退回实测版本）
    配合 `软件/骨架/官方接口清单.py` 的 21 项接口自检，
    形成"版本 + 接口"两道防线：版本对了接口不一定对，接口对了版本也未必对，两道都要。

用法：
    .venv/bin/python 工具/检查版本锁.py
    .venv/bin/python 工具/检查版本锁.py --锁 某个别的.lock
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from importlib import metadata


def 解析锁文件(路径: str) -> tuple[dict[str, str], dict[str, str]]:
    """返回 (必需包, 可选包)。规则：'# ===== 可选' 之后的条目算可选。"""
    必需: dict[str, str] = {}
    可选: dict[str, str] = {}
    当前 = 必需
    for 行 in open(路径, encoding="utf-8"):
        行 = 行.strip()
        if 行.startswith("#"):
            if "可选" in 行:
                当前 = 可选
            continue
        if not 行:
            continue
        匹配 = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s#]+)", 行)
        if 匹配:
            当前[匹配.group(1)] = 匹配.group(2)
            continue
        匹配 = re.match(r"^([A-Za-z0-9_.\-]+)\s*(#.*)?$", 行)
        if 匹配:
            当前.setdefault(匹配.group(1), "")   # 只声明不钉版本
    return 必需, 可选


def 已装版本(包名: str) -> str | None:
    try:
        return metadata.version(包名)
    except metadata.PackageNotFoundError:
        return None


def main(argv: list[str]) -> int:
    这里 = os.path.dirname(os.path.abspath(__file__))
    默认锁 = os.path.normpath(os.path.join(这里, "..", "..", "requirements.lock"))
    # 兼容资料包结构（工具/ 在包根下）
    if not os.path.exists(默认锁):
        默认锁 = os.path.normpath(os.path.join(这里, "..", "requirements.lock"))

    ap = argparse.ArgumentParser(description="核对版本锁")
    ap.add_argument("--锁", default=默认锁, help="锁文件路径")
    args = ap.parse_args(argv)

    if not os.path.exists(args.锁):
        print(f"✗ 找不到锁文件：{args.锁}")
        return 2

    必需, 可选 = 解析锁文件(args.锁)
    print("=" * 74)
    print("版本锁核对")
    print(f"  锁文件：{args.锁}")
    print("=" * 74)

    不一致: list[str] = []
    缺失: list[str] = []

    print("【必需】外壳运行靠这些")
    for 包, 期望 in sorted(必需.items()):
        实际 = 已装版本(包)
        if 实际 is None:
            缺失.append(包)
            print(f"  ✗ {包:16s} 未安装（锁要求 {期望 or '任意版本'}）")
        elif 期望 and 实际 != 期望:
            不一致.append(f"{包}: 装的是 {实际}，锁要求 {期望}")
            print(f"  ⚠ {包:16s} 装的是 {实际}，锁要求 {期望}")
        else:
            print(f"  ✓ {包:16s} {实际}")

    print("\n【可选】第 4 步 D3（参数辨识）用")
    for 包, 期望 in sorted(可选.items()):
        实际 = 已装版本(包)
        if 实际 is None:
            print(f"  – {包:16s} 未安装（不影响外壳；装法见 requirements.lock 注释）")
        else:
            print(f"  ✓ {包:16s} {实际}")

    print()
    if 不一致 or 缺失:
        print("⚠ 环境与实测版本不一致 —— 官方 API 可能已变，建议：")
        print("   ① 先跑接口自检：  .venv/bin/python 软件/主程序.py --自检")
        print("   ② 若自检有失败项，退回实测版本：")
        print("      .venv/bin/pip install -r requirements.lock")
        return 1
    print("✓ 必需包全部与实测版本一致")
    print("  提示：版本一致不代表接口一定对，请再跑一次 `主程序.py --自检`（21 项）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
