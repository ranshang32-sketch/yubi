"""
生成图标.py —— 给 .app 画一个图标（不依赖设计软件）

它做什么：
    用 Pillow 画一个"抽象机械臂"图标（圆角深色底 + 基座 + 两节臂 + 关节），
    然后生成 macOS 需要的 .iconset 并用系统自带的 `iconutil` 转成 .icns。

为什么自己画：
    项目里没有设计资源，也没有设计软件。图标只要能表达"机械臂仿真软件"即可，
    用代码画的好处是**可重现**：改几行参数就能换配色/换造型，不用找设计师。

用法：
    .venv/bin/python 工具/生成图标.py                      # 默认输出到 包根/图标.icns
    .venv/bin/python 工具/生成图标.py --输出 某处/我的.icns
    .venv/bin/python 工具/生成图标.py --底色 "#1b2a41" --主色 "#4cc2ff"

技术要点（踩过的）：
    · macOS 图标必须留出"安全边距"（内容不能占满整张图），否则在 Dock 里显得比别人大
    · .icns 必须由 `iconutil` 从 .iconset 目录生成，且文件名有固定命名规则
    · 16/32 这种小尺寸下细节会糊，所以画的是"少而粗"的几何形状，不画细节
"""
from __future__ import annotations

import argparse
import math
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFilter


def 画图标(尺寸: int, 底色: str, 主色: str, 强调色: str) -> Image.Image:
    """画一张 `尺寸×尺寸` 的图标。所有坐标按比例算，任何尺寸都清晰。"""
    # 超采样 4 倍再缩小 → 边缘平滑（省得手写抗锯齿）
    倍 = 4
    S = 尺寸 * 倍
    图 = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    笔 = ImageDraw.Draw(图)

    # ---- 背景：圆角方块（macOS 风格安全边距 = 8%）----
    边距 = int(S * 0.08)
    圆角 = int(S * 0.22)
    笔.rounded_rectangle([边距, 边距, S - 边距, S - 边距], radius=圆角, fill=底色)

    # 背景上加一点从左上到右下的渐变感（叠一层半透明）
    亮 = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    亮笔 = ImageDraw.Draw(亮)
    亮笔.rounded_rectangle([边距, 边距, S - 边距, S - 边距], radius=圆角,
                           fill=(255, 255, 255, 26))
    亮 = 亮.filter(ImageFilter.GaussianBlur(S * 0.02))
    图 = Image.alpha_composite(图, 亮)
    笔 = ImageDraw.Draw(图)

    def 点(x: float, y: float) -> tuple[float, float]:
        """把 0~1 的相对坐标换算成像素坐标。"""
        return (S * x, S * y)

    # ---- 基座（底部梯形 + 一条底座线）----
    笔.polygon([点(0.28, 0.82), 点(0.72, 0.82), 点(0.64, 0.70), 点(0.36, 0.70)],
               fill=主色)
    笔.rounded_rectangle([点(0.24, 0.82)[0], 点(0.24, 0.82)[1],
                          点(0.76, 0.88)[0], 点(0.76, 0.88)[1]],
                         radius=S * 0.015, fill=主色)

    # ---- 肩关节（基座上方的圆）----
    肩 = 点(0.50, 0.68)
    笔.ellipse([肩[0] - S * 0.055, 肩[1] - S * 0.055,
                肩[0] + S * 0.055, 肩[1] + S * 0.055], fill=强调色)

    # ---- 上臂：从肩关节斜向左上 ----
    肘 = 点(0.34, 0.44)
    笔.line([肩, 肘], fill=主色, width=int(S * 0.085))
    笔.ellipse([肘[0] - S * 0.05, 肘[1] - S * 0.05,
                肘[0] + S * 0.05, 肘[1] + S * 0.05], fill=强调色)

    # ---- 前臂：从肘斜向右上 ----
    腕 = 点(0.62, 0.28)
    笔.line([肘, 腕], fill=主色, width=int(S * 0.07))
    笔.ellipse([腕[0] - S * 0.042, 腕[1] - S * 0.042,
                腕[0] + S * 0.042, 腕[1] + S * 0.042], fill=强调色)

    # ---- 末端工具：一小段"手指/夹爪"----
    尖 = 点(0.74, 0.19)
    笔.line([腕, 尖], fill=强调色, width=int(S * 0.035))
    笔.ellipse([尖[0] - S * 0.028, 尖[1] - S * 0.028,
                尖[0] + S * 0.028, 尖[1] + S * 0.028], fill=主色)

    # ---- 末端画一条淡淡的运动弧线（暗示"在运动"）----
    弧 = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    弧笔 = ImageDraw.Draw(弧)
    弧笔.arc([点(0.30, 0.06)[0], 点(0.30, 0.06)[1],
              点(1.04, 0.66)[0], 点(1.04, 0.66)[1]],
             start=200, end=300, fill=(255, 255, 255, 110), width=int(S * 0.012))
    图 = Image.alpha_composite(图, 弧)

    # 缩回目标尺寸
    return 图.resize((尺寸, 尺寸), Image.LANCZOS)


def 生成_icns(输出路径: str, 底色: str, 主色: str, 强调色: str) -> bool:
    """生成 .icns。需要系统的 iconutil（macOS 自带）。"""
    if shutil.which("iconutil") is None:
        print("✗ 找不到 iconutil（macOS 才能用）")
        return False

    with tempfile.TemporaryDirectory() as 临时:
        iconset = os.path.join(临时, "图标.iconset")
        os.makedirs(iconset)
        # macOS 规定的命名与尺寸
        规格 = [(16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2),
                (256, 1), (256, 2), (512, 1), (512, 2)]
        for 基准, 倍率 in 规格:
            像素 = 基准 * 倍率
            名 = f"icon_{基准}x{基准}" + ("@2x" if 倍率 == 2 else "") + ".png"
            画图标(像素, 底色, 主色, 强调色).save(os.path.join(iconset, 名), "PNG")
        结果 = subprocess.run(["iconutil", "-c", "icns", iconset, "-o", 输出路径],
                              capture_output=True, text=True)
        if 结果.returncode != 0:
            print(f"✗ iconutil 失败：{结果.stderr.strip()}")
            return False
    return True


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="生成 .app 图标")
    ap.add_argument("--输出", default=None, help="输出的 .icns 路径")
    ap.add_argument("--底色", default="#16233a", help="背景色（默认深蓝）")
    ap.add_argument("--主色", default="#c9d6e6", help="机械臂主体色（默认浅灰蓝）")
    ap.add_argument("--强调色", default="#4cc2ff", help="关节高亮色（默认亮蓝）")
    args = ap.parse_args(argv)

    if args.输出:
        输出 = args.输出
    else:
        这里 = os.path.dirname(os.path.abspath(__file__))
        输出 = os.path.normpath(os.path.join(这里, "..", "图标.icns"))

    os.makedirs(os.path.dirname(os.path.abspath(输出)), exist_ok=True)
    print("=" * 66)
    print("生成图标")
    print("=" * 66)
    print(f"  底色 {args.底色} / 主色 {args.主色} / 强调色 {args.强调色}")
    if not 生成_icns(输出, args.底色, args.主色, args.强调色):
        return 1
    大小 = os.path.getsize(输出) / 1024
    print(f"  ✓ 已生成 {输出}（{大小:.0f} KB）")
    # 顺便导出一张预览 PNG（方便在文档/PPT 里用）
    预览 = os.path.splitext(输出)[0] + "_预览.png"
    画图标(512, args.底色, args.主色, args.强调色).save(预览, "PNG")
    print(f"  ✓ 预览图 {预览}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
