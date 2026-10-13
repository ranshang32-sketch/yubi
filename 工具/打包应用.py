"""
打包应用.py —— 生成 macOS 的 .app（双击即启动）

为什么不用 Platypus / PyInstaller：
    macOS 的 .app 本质就是一个"有固定目录结构的文件夹"：
        驭臂.app/Contents/Info.plist           ← 名字/版本/版权声明（XML）
        驭臂.app/Contents/MacOS/驭臂            ← **原生 arm64 启动器**（编译出来的小可执行文件）
        驭臂.app/Contents/Resources/启动.sh      ← 启动逻辑（bash 脚本，真正干活的那个）
    ★ Contents/MacOS/ 里只放 Mach-O，不放脚本 —— 这样整个 .app 才能被签名，
      也避免系统在判断架构时看到"非 Mach-O 的可执行文件"而产生歧义。
    PyInstaller 会试图把整个 Python 环境和 mujoco 的 16 个 .so 一起打包，
    mujoco 包里还带 Filament 材质资产，很容易漏文件；而我们的 .venv 本来就现成，
    启动脚本直接调它即可 —— **更小、更可控、不依赖打包工具**。

★ 为什么需要那个"原生 arm64 启动器"（踩过的坑，别删）：
    最初 .app 的 CFBundleExecutable 直接指向一个 **bash 脚本**。
    脚本没有架构信息 → macOS 查不到 `kMDItemExecutableArchitectures`（返回 null）
    → 在 Apple Silicon 上无法确认是原生应用 → **双击时弹"要安装 Rosetta"**。
    明明整个软件都是 arm64 原生的，却被要求装 Intel 翻译层。
    解决：编译一个几行的 arm64 C 程序作为 CFBundleExecutable，它只负责
    "算出自己在哪 → exec /bin/bash 那个脚本"。这样 macOS 一眼看出是原生 arm64，
    不再提示 Rosetta；而启动逻辑仍然留在 bash 脚本里（改代码不用重新打包）。

特点：
    · 启动器自己算"包根"（四级回退），所以**整个包搬到任何目录都能跑**
    · 环境缺失时弹中文对话框提示，而不是闪退
    · 运行日志写到 包根/启动日志.txt（双击时看不到终端，靠这个排查）
    · Bundle Identifier 自动保证唯一（避免两个 .app 撞 id、互相干扰）

用法：
    .venv/bin/python 工具/打包应用.py                  # 在资料包根目录生成 .app
    .venv/bin/python 工具/打包应用.py --包根 /路径       # 指定包根
    .venv/bin/python 工具/打包应用.py --名字 "小软件"     # 换软件名
    .venv/bin/python 工具/打包应用.py --标识 local.digitwin.yubi   # 显式指定 bundle id
"""
from __future__ import annotations

import argparse
import hashlib
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------------------
# ① bash 启动器（真正的启动逻辑）
#    ★ 三个踩过的坑都体现在这里：
#      ① bash 变量名只能用 ASCII（用中文会报 "No such file or directory"）
#      ② Contents/MacOS → Contents → .app → 包根，是上 3 级（写成 4 级会去找 /tmp/.venv）
#      ③ 用 exec 让 Python 接管进程，关窗口即退出，Dock 不留残影
# ---------------------------------------------------------------------------
启动器模板 = """#!/bin/bash
# {软件名} 启动器（由 .app 双击调用；真正的启动逻辑都在这里）
#
# ★ 定位"包根"（装 .venv 和代码的那个目录）用了**四级回退**，
#   因为 .app 会被放到桌面、Dock、甚至别的目录 —— 写死相对路径一挪就废。
#   顺序：① 应用包内配置 → ② 环境变量 → ③ 常见位置搜 → ④ 相对路径（兼容老布局）
#
# ★ 本脚本住在 X.app/Contents/Resources/ 里，由 Contents/MacOS/ 下的
#   原生 arm64 启动器（{软件名}）exec 调起 —— 这样 macOS 才能认出这是原生应用、
#   不提示安装 Rosetta。（脚本不放 MacOS/ 是为了让整个 .app 能被签名。）
set -u
RES_DIR="$(cd "$(dirname "$0")" && pwd)"        # …/X.app/Contents/Resources
APP_CONTENTS="$(cd "$RES_DIR/.." && pwd)"       # …/X.app/Contents
PKG_DIR=""

# ① 应用包内配置（打包时写入，最准）
if [ -z "$PKG_DIR" ] && [ -f "$RES_DIR/包路径.txt" ]; then
  CAND="$(head -1 "$RES_DIR/包路径.txt" | tr -d '\\r\\n')"
  [ -n "$CAND" ] && [ -d "$CAND" ] && PKG_DIR="$CAND"
fi
# ② 环境变量（方便你自己指定）
if [ -z "$PKG_DIR" ] && [ -n "${小软件_包路径:-}" ] && [ -d "${小软件_包路径}" ]; then
  PKG_DIR="${小软件_包路径}"
fi
# ③ 常见位置搜一遍（桌面 / 家目录 / 文档）
if [ -z "$PKG_DIR" ]; then
  for CAND in "$HOME/Desktop/{包文件夹名}" "$HOME/{包文件夹名}" "$HOME/Documents/{包文件夹名}"; do
    if [ -x "$CAND/.venv/bin/python" ]; then PKG_DIR="$CAND"; break; fi
  done
fi
# ④ 相对路径（.app 仍在包内时的老布局）：Contents/../.. 就是包根
if [ -z "$PKG_DIR" ]; then
  CAND="$(cd "$APP_CONTENTS/../.." && pwd)"
  [ -x "$CAND/.venv/bin/python" ] && PKG_DIR="$CAND"
fi

if [ -z "$PKG_DIR" ]; then
  osascript -e 'display dialog "找不到{软件名}的安装位置（含 .venv 的包文件夹）。\n\n请把整个包文件夹放到桌面，或设置环境变量 小软件_包路径 指向它。" buttons {{"好"}} default button 1 with icon stop' 2>/dev/null
  exit 1
fi
LOG="$PKG_DIR/启动日志.txt"
echo "===== $(date '+%Y-%m-%d %H:%M:%S') 启动，包根=$PKG_DIR =====" >> "$LOG"

PY="$PKG_DIR/.venv/bin/python"
if [ ! -x "$PY" ]; then
  osascript -e 'display dialog "找到了包文件夹，但里面没有运行环境（.venv）。\n\n请先在终端执行：\nbash 工具/重建环境.sh" buttons {{"好"}} default button 1 with icon stop' 2>/dev/null
  echo "✗ 找不到 $PY" >> "$LOG"; exit 1
fi

# 主程序位置：不同包结构不一样（资料包 / 独立包），逐个试
APP_PY=""
for CAND in "$PKG_DIR/{主程序相对路径}" "$PKG_DIR/软件/主程序.py" "$PKG_DIR/软件/主程序.py"; do
  if [ -f "$CAND" ]; then APP_PY="$CAND"; break; fi
done
if [ -z "$APP_PY" ]; then
  osascript -e 'display dialog "找到了包文件夹，但里面找不到主程序（主程序.py）。\n\n期望位置：{主程序相对路径} 或 软件/主程序.py" buttons {{"好"}} default button 1 with icon stop' 2>/dev/null
  echo "✗ 找不到主程序（试过 {主程序相对路径} / 软件/主程序.py / 软件/主程序.py）" >> "$LOG"; exit 1
fi

cd "$PKG_DIR" || exit 1
exec "$PY" -u "$APP_PY" "$@" >> "$LOG" 2>&1
"""

# ---------------------------------------------------------------------------
# ② 原生 arm64 启动器（C 源码，编译成 Contents/MacOS/<软件名>）
#
#    它只做一件事：找到自己所在的目录 → exec /bin/bash 同目录下的"启动"脚本，
#    并把命令行参数原样转发。这样 CFBundleExecutable 是一个真正的 arm64 Mach-O，
#    macOS 就能确定这是原生应用 —— **不再提示安装 Rosetta**。
#
#    ★ 为什么用 /bin/bash 显式执行，而不是直接 exec 脚本：
#      脚本可能因为 zip/拷贝丢了可执行位，显式用 bash 更稳。
#    ★ 为什么用 _NSGetExecutablePath + realpath：
#      双击启动时工作目录是 /，argv[0] 可能不完整；必须自己问系统要绝对路径。
# ---------------------------------------------------------------------------
启动器源码 = r"""// {软件名} 原生 arm64 启动器（由 工具/打包应用.py 生成，勿手改）
//
// 存在意义：让 macOS 认出 .app 是原生 arm64 应用，不提示安装 Rosetta。
// 做法：算出自己的绝对路径 → 上一级的 Resources/启动.sh → 转发全部参数。
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <mach-o/dyld.h>

int main(int argc, char** argv) {
  char 自身[PATH_MAX];
  uint32_t 长度 = sizeof(自身);
  if (_NSGetExecutablePath(自身, &长度) != 0) {
    fprintf(stderr, "{软件名}: 无法获取自身路径（路径过长？）\n");
    return 1;
  }
  char 真实[PATH_MAX];
  if (realpath(自身, 真实) == NULL) {
    fprintf(stderr, "{软件名}: 无法解析自身路径\n");
    return 1;
  }
  // 目录 = …/X.app/Contents/MacOS
  char* 斜杠 = strrchr(真实, '/');
  if (斜杠 == NULL) {
    fprintf(stderr, "{软件名}: 自身路径异常：%s\n", 真实);
    return 1;
  }
  *斜杠 = '\0';

  char 脚本[PATH_MAX];
  if (snprintf(脚本, sizeof(脚本), "%s/../Resources/启动.sh", 真实) >= (int)sizeof(脚本)) {
    fprintf(stderr, "{软件名}: 路径过长\n");
    return 1;
  }
  if (access(脚本, R_OK) != 0) {
    fprintf(stderr, "{软件名}: 找不到启动脚本：%s\n", 脚本);
    return 1;
  }

  // argv = ["/bin/bash", 脚本, 原参数…, NULL]
  char** 新参数 = (char**)calloc((size_t)argc + 3, sizeof(char*));
  if (新参数 == NULL) {
    fprintf(stderr, "{软件名}: 内存不足\n");
    return 1;
  }
  新参数[0] = (char*)"/bin/bash";
  新参数[1] = 脚本;
  for (int i = 1; i < argc; i++) {
    新参数[i + 1] = argv[i];
  }
  新参数[argc + 1] = NULL;

  execv("/bin/bash", 新参数);
  fprintf(stderr, "{软件名}: 无法执行 /bin/bash\n");
  return 1;
}
"""


def _标识片段(软件名: str) -> str:
    """把软件名转成 bundle id 里可用的一段（必须是 ASCII）。

    纯 ASCII 名字直接用（去掉非法字符）；中文等非 ASCII 名字用名字的 sha256 前 8 位，
    保证"同一个名字每次都得到同一个 id"，且不会和别的软件撞。
    """
    干净 = "".join(c.lower() for c in 软件名 if c.isascii() and (c.isalnum() or c == "-"))
    if 干净:
        return 干净
    return hashlib.sha256(软件名.encode("utf-8")).hexdigest()[:8]


def 编译原生启动器(目标路径: str, 软件名: str, 语言目录: str) -> tuple[bool, str]:
    """把 启动器源码 编译成 arm64 可执行文件。返回 (是否成功, 说明)。"""
    编译器 = shutil.which("cc") or shutil.which("clang")
    if 编译器 is None:
        return False, "找不到 cc / clang（需要 Xcode 命令行工具：xcode-select --install）"
    源文件 = os.path.join(语言目录, "启动器.c")
    with open(源文件, "w", encoding="utf-8") as f:
        f.write(启动器源码.replace("{软件名}", 软件名))
    # -arch arm64：明确只要 arm64 切片，让 macOS 一眼看出是原生应用
    命令行 = [编译器, "-arch", "arm64", "-O2", "-Wall", "-o", 目标路径, 源文件]
    结果 = subprocess.run(命令行, capture_output=True, text=True)
    if 结果.returncode != 0:
        return False, (结果.stderr or 结果.stdout or "编译失败").strip()[:400]
    if not os.path.exists(目标路径):
        return False, "编译命令返回成功但没有产出文件"
    os.chmod(目标路径, os.stat(目标路径).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return True, 编译器


def 生成(包根: str, 软件名: str, 主程序相对路径: str, 标识: str | None, 版本: str,
         图标: str | None = None) -> str:
    app = os.path.join(包根, f"{软件名}.app")
    os.makedirs(os.path.join(app, "Contents", "MacOS"), exist_ok=True)
    资源目录 = os.path.join(app, "Contents", "Resources")
    os.makedirs(资源目录, exist_ok=True)
    plist路径 = os.path.join(app, "Contents", "Info.plist")

    # 图标：把 .icns 复制进 Resources，并在 Info.plist 里声明 CFBundleIconFile
    图标名 = ""
    if 图标 and os.path.exists(图标):
        shutil.copyfile(图标, os.path.join(资源目录, "图标.icns"))
        图标名 = "图标"
    else:
        print("  ℹ 没找到 .icns 图标（可先跑 工具/生成图标.py），本次不设图标")

    # ---- ① 先写 bash 启动脚本（启动逻辑）----
    #      放在 Resources/ 而不是 MacOS/：MacOS/ 里只留 Mach-O，整个 .app 才能签名
    脚本路径 = os.path.join(资源目录, "启动.sh")
    包文件夹名 = os.path.basename(os.path.normpath(包根))
    # ★ 用 replace 而不是 str.format：启动器里有大量 shell 的 ${变量} 和 {{ }}，
    #   用 format 会把它们当占位符（实测报 KeyError: '驭臂_包路径'）。
    脚本 = (启动器模板
            .replace("{软件名}", 软件名)
            .replace("{主程序相对路径}", 主程序相对路径)
            .replace("{包文件夹名}", 包文件夹名))
    # 上面把 shell 里被误写的 {{ }} 还原成 { }
    脚本 = 脚本.replace("{{", "{").replace("}}", "}")
    with open(脚本路径, "w", encoding="utf-8") as f:
        f.write(脚本)
    os.chmod(脚本路径, os.stat(脚本路径).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    # 清掉老版本遗留在 MacOS/ 里的脚本（否则签名会失败：MacOS/ 里混进了非 Mach-O 文件）
    旧脚本 = os.path.join(app, "Contents", "MacOS", "启动")
    if os.path.exists(旧脚本):
        os.remove(旧脚本)
        print("  ℹ 已移除老布局遗留的 Contents/MacOS/启动（脚本现位于 Resources/启动.sh）")

    # ---- ② 编译原生 arm64 启动器，作为 CFBundleExecutable ----
    可执行名 = 软件名
    可执行路径 = os.path.join(app, "Contents", "MacOS", 可执行名)
    with tempfile.TemporaryDirectory(prefix="小软件打包_") as 语言目录:
        成功, 说明 = 编译原生启动器(可执行路径, 软件名, 语言目录)
    if 成功:
        print(f"  ✓ 已编译原生 arm64 启动器：Contents/MacOS/{可执行名}")
        可执行文件 = 可执行名
    else:
        # 兜底：退回老做法（CFBundleExecutable 直接指向 bash 脚本）。
        # 副作用：double-click 时 macOS 可能提示安装 Rosetta（因为脚本没有架构信息）。
        print(f"  ⚠ 原生启动器编译失败，退回脚本启动器：{说明}")
        print("     → 副作用：双击时 macOS 可能提示安装 Rosetta（软件本身其实全是 arm64 原生）")
        print("     → 修好编译环境后重跑本脚本即可解决")
        可执行文件 = "启动"

    # ---- ③ Bundle Identifier：显式 > 沿用已有的 > 按名字自动派生 ----
    #     为什么重要：两个 .app 用同一个 id 会互相干扰（实测踩过：
    #     驭臂.app 与 数字样机.app 撞 id，撞出一条带 LSArchitecturePriority 的旧记录，
    #     让 macOS 误判架构）。
    if 标识:
        bundle标识, 来源 = 标识, "命令行 --标识"
    elif os.path.exists(plist路径):
        try:
            with open(plist路径, "rb") as f:
                旧 = plistlib.load(f).get("CFBundleIdentifier", "") or ""
        except Exception:                                          # noqa: BLE001
            旧 = ""
        if 旧:
            bundle标识, 来源 = 旧, "沿用上一次的 id"
        else:
            bundle标识, 来源 = f"local.digitwin.{_标识片段(软件名)}", "按名字自动派生"
    else:
        bundle标识, 来源 = f"local.digitwin.{_标识片段(软件名)}", "按名字自动派生"
    print(f"  Bundle ID：{bundle标识}（{来源}）")

    # ---- ④ Info.plist ----
    #     版权声明里写清与 Google DeepMind 无关联（Apache-2.0 的商标要求）
    信息 = {
        "CFBundleName": 软件名,
        "CFBundleDisplayName": 软件名,
        "CFBundleIdentifier": bundle标识,
        "CFBundleExecutable": 可执行文件,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": 版本,
        "CFBundleVersion": 版本,
        # ★ 声明"这是 macOS 原生应用"，配合原生启动器可彻底避免 Rosetta 提示
        "CFBundleSupportedPlatforms": ["MacOSX"],
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": (
            "本项目与 Google DeepMind 无关联，未获其背书。"
            "基于 MuJoCo（Apache-2.0）。"
        ),
    }
    # ★ 刻意不写 LSArchitecturePriority：写了反而可能让系统误判该用哪个架构。
    if 图标名:
        信息["CFBundleIconFile"] = 图标名
    with open(plist路径, "wb") as f:
        plistlib.dump(信息, f)

    # 把"包根"写进应用包，启动器优先读它 —— 这样 .app 放到哪里都能找到代码
    with open(os.path.join(资源目录, "包路径.txt"), "w", encoding="utf-8") as f:
        f.write(包根 + "\n")

    # ---- ⑤ 对 .app 做 ad-hoc 签名 ----
    #     Apple Silicon 上所有可执行文件都必须有签名（编译时已自动 ad-hoc 签过 Mach-O），
    #     这里把整个 bundle 也签一下，让 macOS 把它当成一个"正常应用"，
    #     避免 LaunchServices / Gatekeeper 因为"未签名的 bundle"产生额外的架构猜测。
    if 成功:
        _签bundle(app)
    return app


def _签bundle(app: str) -> None:
    """对整个 .app 做 ad-hoc 签名（失败只提示，不影响使用）。"""
    if shutil.which("codesign") is None:
        print("  ℹ 找不到 codesign，跳过签名（不影响使用）")
        return
    结果 = subprocess.run(["codesign", "--force", "--sign", "-", app],
                          capture_output=True, text=True)
    if 结果.returncode == 0:
        print("  ✓ 已对 .app 做 ad-hoc 签名")
    else:
        说明 = (结果.stderr or 结果.stdout or "").strip().replace("\n", " ")[:300]
        print(f"  ⚠ .app 签名失败（不影响启动）：{说明}")


def 刷新系统注册(app: str) -> None:
    """让 LaunchServices 重新读一遍这个 .app（清掉旧的架构缓存）。

    为什么需要：macOS 会把 app 的架构信息缓存进 LaunchServices 数据库。
    换过启动器之后不刷新，系统可能还按旧记录判断 —— 于是仍然提示装 Rosetta。
    """
    lsr = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/"
           "LaunchServices.framework/Support/lsregister")
    if not os.path.exists(lsr):
        print("  ℹ 找不到 lsregister，跳过刷新（重启 Finder 或重新登录后也会自动刷新）")
        return
    结果 = subprocess.run([lsr, "-f", app], capture_output=True, text=True)
    if 结果.returncode == 0:
        print("  ✓ 已刷新 LaunchServices 注册（清掉旧的架构缓存）")
    else:
        print(f"  ⚠ 刷新 LaunchServices 失败（不影响使用）：{(结果.stderr or '').strip()[:200]}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="生成 macOS .app（双击启动）")
    ap.add_argument("--包根", default=None, help="资料包根目录（默认：本脚本的上上级）")
    ap.add_argument("--名字", default="小软件", help="软件名（会作为 .app 文件名）")
    ap.add_argument("--主程序", default="软件/主程序.py",
                    help="主程序相对于包根的路径")
    ap.add_argument("--标识", default=None,
                    help="Bundle Identifier（默认：沿用已有的；没有则按名字自动派生一个唯一 id）")
    ap.add_argument("--版本", default="0.3", help="版本号")
    ap.add_argument("--图标", default=None, help=".icns 路径（默认：包根/图标.icns）")
    ap.add_argument("--不刷新注册", action="store_true",
                    help="不调用 lsregister 刷新系统注册")
    args = ap.parse_args(argv)

    # 本脚本在 <包根>/工具/ 下 → 上一级就是包根
    #   （原来写的是上两级，那是"脚本在 工具/打包/ 里"的老结构，早已不成立）
    包根 = args.包根 or os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

    print("=" * 68)
    print("生成 macOS .app")
    print("=" * 68)
    print(f"  包根    : {包根}")
    if not os.path.isdir(包根):
        print("  ✗ 包根不存在")
        return 1
    if not os.path.exists(os.path.join(包根, args.主程序)):
        print(f"  ⚠ 主程序不在预期位置：{args.主程序}")
        print("     （仍会生成，但双击时会弹'找不到主程序'）")

    图标 = args.图标 or os.path.join(包根, "图标.icns")
    app = 生成(包根, args.名字, args.主程序, args.标识, args.版本, 图标)

    if not args.不刷新注册:
        刷新系统注册(app)

    print(f"  已生成  : {app}")
    print()
    print("  .app 结构：")
    for root, dirs, files in os.walk(app):
        for f in files:
            p = os.path.join(root, f)
            print(f"    {os.path.relpath(p, app)}")
    print()
    print("  双击即可启动。若没反应，看包根下的 启动日志.txt。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
