"""
检查字体覆盖.py —— 换字体前先跑这个，别等界面出豆腐块才发现

用途：
    把一个 .ttf 字体文件拖进来，看它有没有你要用的字。
    背景：官方自带的 3 个字体**完全不含中文**（实测），
          所以界面里写中文会显示成豆腐块；而 Python 层又**没有加载字体的接口**。
          这个脚本用来看"某个字体到底有没有某个字"，避免白折腾。

用法：
    .venv/bin/python 工具/检查字体覆盖.py 字体1.ttf [字体2.ttf ...]
    .venv/bin/python 工具/检查字体覆盖.py --默认测试 字体.ttf      # 用内置的一组测试字

原理：
    直接读 TrueType 的 cmap 表（字符码位 → 字形索引的映射），不依赖任何字体库。
    支持 cmap 格式 4（BMP）与 12（含扩展平面，如 𠮷 U+20BB7）。
"""
from __future__ import annotations

import os
import struct
import sys

# 默认测试字：中英数 + 几个本项目常用的中文词
# 注：从"实际要用到的字"里挑，比如软件名、面板标题、按钮文字
默认测试 = {
    "A": 0x41, "1": 0x31, "a": 0x61,
    "机": 0x673A, "器": 0x5668, "人": 0x4EBA,
    "仿": 0x4EFF, "真": 0x771F, "样": 0x6837,
    "控": 0x63A7, "制": 0x5236, "律": 0x5F8B,
    "参": 0x53C2, "辨": 0x8FA8, "识": 0x8BC6,
    "据": 0x636E, "记": 0x8BB0, "录": 0x5F55,
    "生僻𠮷": 0x20BB7,
}
# 判定"含中文"时只看这几个常用字
核心中文 = ("机", "器", "人", "仿", "真", "样")


def _读cmap子表位置(data: bytes):
    """返回 (cmap 表偏移, 选中的子表偏移) 或 None。"""
    if len(data) < 12:
        return None
    num = struct.unpack(">H", data[4:6])[0]
    cmap_off = None
    for i in range(num):
        off = 12 + i * 16
        if data[off:off + 4] == b"cmap":
            cmap_off = struct.unpack(">I", data[off + 8:off + 12])[0]
            break
    if cmap_off is None:
        return None
    n = struct.unpack(">H", data[cmap_off + 2:cmap_off + 4])[0]
    候选 = []
    for i in range(n):
        rec = cmap_off + 4 + i * 8
        pid, eid, sub = struct.unpack(">HHI", data[rec:rec + 8])
        # 3,10 = Windows UCS-4；0,4 = Unicode 2.0+；3,1 = Windows BMP；0,3 = Unicode 2.0
        优先 = {(3, 10): 0, (0, 4): 1, (3, 1): 2, (0, 3): 3}.get((pid, eid))
        if 优先 is not None:
            候选.append((优先, cmap_off + sub))
    if not 候选:
        return None
    候选.sort()
    return cmap_off, 候选[0][1]


def 覆盖情况(路径: str, 测试: dict[str, int]) -> dict:
    try:
        data = open(路径, "rb").read()
    except Exception as 异常:                                     # noqa: BLE001
        return {"_错误": f"读不了文件：{异常}"}

    位置 = _读cmap子表位置(data)
    if 位置 is None:
        return {"_错误": "找不到可用的 cmap 子表"}
    _, best = 位置
    fmt = struct.unpack(">H", data[best:best + 2])[0]

    def 有(cp: int) -> bool | None:
        if fmt == 4:
            segX2 = struct.unpack(">H", data[best + 6:best + 8])[0]
            seg = segX2 // 2
            基 = best + 14
            ends = struct.unpack(f">{seg}H", data[基:基 + segX2])
            基2 = best + 16 + segX2
            starts = struct.unpack(f">{seg}H", data[基2:基2 + segX2])
            for s, e in zip(starts, ends):
                if s <= cp <= e:
                    return True
            return False
        if fmt == 12:
            ngroups = struct.unpack(">I", data[best + 12:best + 16])[0]
            for g in range(ngroups):
                o = best + 16 + g * 12
                s, e, _ = struct.unpack(">III", data[o:o + 12])
                if s <= cp <= e:
                    return True
            return False
        return None

    结果 = {名字: 有(cp) for 名字, cp in 测试.items()}
    结果["_格式"] = fmt
    结果["_大小KB"] = round(len(data) / 1024)
    return 结果


def main(argv: list[str]) -> int:
    测试 = dict(默认测试)
    if argv and argv[0] == "--默认测试":
        argv = argv[1:]

    if not argv:
        print(__doc__)
        print("当前默认会测试这些字：", " ".join(k for k in 测试 if not k.startswith("生僻")))
        return 1

    print("=" * 68)
    for 路径 in argv:
        if not os.path.exists(路径):
            print(f"✗ 文件不存在：{路径}")
            continue
        结果 = 覆盖情况(路径, 测试)
        print(f"【{os.path.basename(路径)}】", end="  ")
        if "_错误" in 结果:
            print(结果["_错误"])
            continue
        print(f"cmap 格式 {结果['_格式']}，{结果['_大小KB']} KB")
        有 = [k for k, v in 结果.items() if not k.startswith("_") and v is True]
        无 = [k for k, v in 结果.items() if not k.startswith("_") and v is False]
        print(f"  ✅ 有：{' '.join(有) if 有 else '（无）'}")
        print(f"  ❌ 无：{' '.join(无) if 无 else '（无）'}")
        中文 = [k for k in 核心中文 if 结果.get(k)]
        if len(中文) == len(核心中文):
            print("  → 这个字体含中文，可以用（但注意：能否装进界面还取决于加载接口）")
        elif not 中文:
            print("  → 这个字体不含中文，界面写中文会显示成豆腐块")
        else:
            print(f"  → 部分覆盖（{len(中文)}/6），谨慎使用")
    print("=" * 68)
    print("提醒：字体好不好用 ≠ 能不能装上。官方界面（ImGui）在 Python 层没有加载字体的接口，")
    print("      所以即使字体含中文，也无法直接让官方界面显示中文。详见《对第三方规划的评判报告》。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
