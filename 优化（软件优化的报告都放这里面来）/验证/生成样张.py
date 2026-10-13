"""
生成样张.py —— 从 软件/风格表.json（实现用的那一份）生成 优化/风格样张.html（可视预览）

为什么要有样张：
    风格名（"蓝图""暖夜"…）每个人脑补的样子都不一样。先给一张
    **能在浏览器里打开、五套风格并排对比**的样张，比在真界面里来回切要快得多，
    也方便拍板"就要这套"。样张里的每个颜色/圆角/边框宽度都直接取自风格表，
    所以样张与将来真界面的外观是同一份数据（不是另画的一版效果图）。

跑法：
    .venv/bin/python 优化/验证/生成样张.py
    open 优化/风格样张.html
"""
from __future__ import annotations

import json
import os
import re

本目录 = os.path.dirname(os.path.abspath(__file__))
包根 = os.path.dirname(os.path.dirname(本目录))


def 转rgba(值: str, 默认不透明: float = 1.0) -> str:
    """#RRGGBB / #RRGGBBAA → rgba(r,g,b,a)。ImGui 的 #RRGGBBAA 是 RGBA 顺序。"""
    h = 值.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    a = int(h[6:8], 16) / 255 if len(h) == 8 else 默认不透明
    return f"rgba({r},{g},{b},{a:.3f})"


def 调色(风格: dict) -> dict:
    """把一套风格压成 CSS 变量。"""
    c = {k: 转rgba(v) for k, v in 风格["颜色"].items()}
    for k, v in 风格["曲线"]["implot"].items():
        c["im_" + k] = 转rgba(v)
    return c


def 主() -> int:
    with open(os.path.join(包根, "软件", "风格表.json"), encoding="utf-8") as f:
        表 = json.load(f)

    卡片 = []
    for 名, 风格 in 表["风格"].items():
        c = 调色(风格)
        s = 风格["样式"]
        调色板 = 风格["曲线"]["调色板"]
        线 = "".join(
            f'<polyline fill="none" stroke="{色}" stroke-width="2" points="'
            + " ".join(f"{i * 34},{58 - (abs(((i * 7 + k * 13) % 19) - 9) * 5.2) - k * 3:.1f}"
                       for i in range(11)) + '"/>'
            for k, 色 in enumerate(调色板[:4])
        )
        色块 = "".join(
            f'<span class="sw" style="background:{色}" title="{色}"></span>' for 色 in 调色板)

        def v(键, 默认=0.0):
            x = s.get(键, 默认)
            return x[0] if isinstance(x, list) else x

        def pq(键, 默认=(0.0, 0.0)):
            x = s.get(键, 默认)
            return f"{x[0]:.0f},{x[1]:.0f}"

        卡片.append(f"""
  <section class="card" style="
      --win-bg:{c['WindowBg']}; --child-bg:{c['ChildBg']};
      --border:{c['Border']}; --bw:{v('WindowBorderSize')}px;
      --fbn:{v('FrameBorderSize')}px;
      --rad:{v('WindowRounding')}px; --frad:{v('FrameRounding')}px;
      --title:{c['TitleBg']}; --title-on:{c['TitleBgActive']};
      --text:{c['Text']}; --dim:{c['TextDisabled']}; --link:{c['TextLink']};
      --frame:{c['FrameBg']}; --frame-h:{c['FrameBgHovered']}; --frame-a:{c['FrameBgActive']};
      --btn:{c['Button']}; --btn-h:{c['ButtonHovered']}; --btn-a:{c['ButtonActive']};
      --hdr:{c['Header']}; --hdr-h:{c['HeaderHovered']}; --hdr-a:{c['HeaderActive']};
      --sep:{c['Separator']}; --check:{c['CheckMark']}; --grab:{c['SliderGrab']};
      --grab-a:{c['SliderGrabActive']}; --th:{c['TableHeaderBg']}; --row:{c['TableRowBg']};
      --row-alt:{c['TableRowBgAlt']}; --tbl:{c['TableBorderStrong']}; --tbl-l:{c['TableBorderLight']};
      --plot-bg:{c['im_PlotBg']}; --plot-bd:{c['im_PlotBorder']}; --grid:{c['im_AxisGrid']};
      --axis-t:{c['im_AxisText']}; --tbw:{v('TabBarBorderSize')}px;
      --wp:{v('WindowPadding', [12, 10])}px; --fp:{v('FramePadding', [8, 4])}px;
  ">
    <h2>{风格['显示名']}</h2>
    <p class="desc">{风格['一句话']}</p>
    <p class="meta">基底主题 <b>{风格['基底主题']}</b> ｜ 圆角 <b>{v('WindowRounding')}px</b>
       ｜ 窗口边框 <b>{v('WindowBorderSize')}px</b> ｜ 控件边框 <b>{v('FrameBorderSize')}px</b>
       ｜ 窗口内边距 <b>{pq('WindowPadding')}</b>
       ｜ 控件内边距 <b>{pq('FramePadding')}</b>
       ｜ 滚动条 <b>{v('ScrollbarSize'):.0f}px</b> ｜ 颜色项 <b>{len(风格['颜色'])}</b></p>

    <div class="mock">
      <div class="titlebar"><span class="dot"></span>{风格['显示名'].split(' ')[0]} 面板<span class="x">×</span></div>
      <div class="body">
        <div class="row"><span class="t">正文文字 Text</span><span class="d">次要文字 Disabled</span><span class="l">文字链接 Link</span></div>
        <div class="btns">
          <button class="b">按钮</button>
          <button class="b hov">悬停</button>
          <button class="b act">按下</button>
          <button class="b sel">✓ 选中行</button>
        </div>
        <div class="row">
          <div class="frame">输入框 / 下拉框</div>
          <div class="slider"><i></i></div>
        </div>
        <div class="tabs"><span class="tab">标签一</span><span class="tab s">标签二</span><span class="tab">标签三</span></div>
        <div class="hr"></div>
        <table><thead><tr><th>关节</th><th>目标 (°)</th><th>实际 (°)</th></tr></thead>
          <tbody><tr><td>shoulder</td><td>-90.0</td><td class="mono">-89.97</td></tr>
          <tr class="alt"><td>elbow</td><td>0.0</td><td class="mono">0.02</td></tr></tbody></table>
        <div class="plot">
          <svg viewBox="0 0 340 62" preserveAspectRatio="none">{线}</svg>
        </div>
        <div class="swrow">{色块}<span class="d">曲线调色板</span></div>
      </div>
    </div>
  </section>""")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>驭臂 · 面板外观风格样张（5 套）</title>
<style>
  body {{ margin:0; padding:28px; background:#0e1014; color:#dfe3ea;
         font:14px/1.6 -apple-system,"PingFang SC","Helvetica Neue",sans-serif; }}
  h1 {{ font-size:22px; margin:0 0 6px; }}
  .lead {{ color:#98a2b3; margin:0 0 26px; max-width:900px; }}
  .lead code {{ background:#1b1f27; padding:1px 5px; border-radius:3px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(390px,1fr)); gap:22px; }}
  .card h2 {{ font-size:16px; margin:0 0 4px; color:#fff; }}
  .desc {{ color:#8f99a8; margin:0 0 6px; font-size:13px; }}
  .meta {{ color:#6f7a8a; margin:0 0 12px; font-size:12px; }}
  .meta b {{ color:#aab4c4; }}
  .mock {{ background:var(--win-bg); border:var(--bw) solid var(--border);
          border-radius:var(--rad); overflow:hidden; box-shadow:0 6px 26px #0008; }}
  .titlebar {{ background:var(--title); color:var(--text); padding:7px 10px;
              font-weight:600; display:flex; align-items:center; gap:8px;
              border-bottom:var(--tbw) solid var(--sep); }}
  .titlebar .x {{ margin-left:auto; opacity:.75; }}
  .dot {{ width:9px; height:9px; background:var(--check); display:inline-block; }}
  .body {{ padding:var(--wp); color:var(--text); }}
  .row {{ display:flex; gap:10px; align-items:center; margin-bottom:9px; flex-wrap:wrap; }}
  .t {{ color:var(--text); }} .d {{ color:var(--dim); font-size:12px; }}
  .l {{ color:var(--link); text-decoration:underline; }}
  .btns {{ display:flex; gap:8px; margin-bottom:9px; flex-wrap:wrap; }}
  .b {{ background:var(--btn); color:var(--text); border:var(--fbn,1px) solid var(--border);
       border-radius:var(--frad); padding:var(--fp); font:inherit; font-size:13px; cursor:default; }}
  .b.hov {{ background:var(--btn-h); }} .b.act {{ background:var(--btn-a); }}
  .b.sel {{ background:var(--hdr-a); }}
  .frame {{ background:var(--frame); border:1px solid var(--border); border-radius:var(--frad);
           padding:var(--fp); flex:1; min-width:130px; font-size:13px; }}
  .slider {{ background:var(--frame); border:1px solid var(--border); border-radius:var(--frad);
            flex:1; min-width:90px; padding:var(--fp); }}
  .slider i {{ display:block; height:6px; background:var(--grab);
              border-radius:calc(var(--frad)/2); width:62%; }}
  .tabs {{ display:flex; gap:3px; border-bottom:var(--tbw) solid var(--sep); margin-bottom:9px; }}
  .tab {{ background:var(--frame); padding:5px 12px; font-size:13px;
         border-radius:var(--frad) var(--frad) 0 0; }}
  .tab.s {{ background:var(--hdr); box-shadow:inset 0 2px 0 var(--check); }}
  .hr {{ height:2px; background:var(--sep); margin:10px 0; }}
  table {{ width:100%; border-collapse:collapse; font-size:12.5px; }}
  th {{ background:var(--th); text-align:left; padding:5px 7px;
       border-bottom:1px solid var(--tbl); }}
  td {{ padding:4px 7px; background:var(--row); border-bottom:1px solid var(--tbl-l); }}
  tr.alt td {{ background:var(--row-alt); }}
  .mono {{ font-family:ui-monospace,Menlo,monospace; }}
  .plot {{ margin-top:10px; background:var(--plot-bg); border:1px solid var(--plot-bd);
          border-radius:var(--frad); padding:6px; }}
  .plot svg {{ width:100%; height:62px; display:block;
              background:repeating-linear-gradient(90deg,var(--grid) 0 1px,transparent 1px 34px),
                         repeating-linear-gradient(0deg,var(--grid) 0 1px,transparent 1px 15px); }}
  .swrow {{ display:flex; gap:5px; align-items:center; margin-top:9px; }}
  .sw {{ width:17px; height:17px; display:inline-block; border:1px solid #0006; }}
  footer {{ margin-top:30px; color:#6f7a8a; font-size:12.5px; }}
</style></head><body>
<h1>驭臂 · 面板外观风格样张</h1>
<p class="lead">这份样张里的每个颜色、圆角、边框宽度都<b>直接取自</b> <code>优化/风格表.json</code>，
  也就是将来真界面要用的同一份数据（每套风格覆盖 55 个颜色项 + 28 个样式项 + 16 个曲线颜色项）。
  想改哪套，改 JSON 再重跑 <code>.venv/bin/python 优化/验证/生成样张.py</code> 即可。</p>
<p class="lead">★ 说明：真实界面用的是 ImGui 内置字体（<b>无法换字体</b>），所以下面这张样张的
  字体只是示意；能确定的差异是颜色、圆角、边框粗细、内边距与信息密度。</p>
<div class="grid">{''.join(卡片)}
</div>
<footer>生成时间：由 优化/验证/生成样张.py 自动生成 ｜ 风格表版本：{表.get('_版本','?')}</footer>
</body></html>"""

    输出 = os.path.join(包根, "优化", "风格样张.html")
    with open(输出, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ 已生成 {输出}（{len(html)} 字节，{len(表['风格'])} 套风格）")
    return 0


if __name__ == "__main__":
    raise SystemExit(主())
