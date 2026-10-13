# 工程化管理：Ultralytics YOLO 做了什么，驭臂该抄哪几条

> 调研时间：2026-09-22
> 调研对象：[ultralytics/ultralytics](https://github.com/ultralytics/ultralytics)（AGPL-3.0）
> 调研方式：拉取仓库根目录清单 + 全部 11 个 workflow 原文 + `pyproject.toml` + `AGENTS.md` + `CONTRIBUTING.md` + `tests/` 测试骨架，逐条读原文（不是看二手介绍）
> 结论一句话：**值得抄的有 8 条，但真正卡住驭臂的只有第 1 条。**

---

## 一、Ultralytics 的实测数据（先量一下对手）

| 指标 | 实测值 | 说明 |
|---|---|---|
| Star / Fork / 贡献者 | 61,904 / 11,794 / **约 460 人** | 460 页 contributor 分页，每页 1 人 |
| 开放 issue | 73 | 相对规模极低 |
| 提交节奏 | **每天 5～10 次合并**，连续多日 | 最近 15 次提交全部在 9/21–9/22 |
| 发版节奏 | **每天 1～2 个版本**（v8.4.155 → v8.4.159） | 版本号 `MAJOR.MINOR.PATCH`，不许带后缀 |
| CI 工作流 | **11 个** | `ci.yml` 单文件 **673 行** |
| 测试代码量 | 约 **19 万行**（`test_python.py` 单个文件 10.7 万行） | 源码 6.2 万 KB 仓库总量 |
| 强制检查工具 | ruff + docformatter + prettier + codespell + license header | 全部由机器人自动提交 |
| 发版 | 改 `__version__` → push main → 自动打 tag + Release + PyPI + SBOM | 无人值守 |
| 额外 | 每天 02:00 UTC 跑 **蒙特卡洛 fuzz**，确认的缺陷自动开 issue | 4 种"人格" × 3 系统 |

---

## 二、他们做的 8 件关键事（附真实证据）

### 1. 分支纪律写进给 AI 的说明书里

`AGENTS.md`（`CLAUDE.md` 是它的符号链接）里原文：

> NEVER push to `main`. NEVER force push. Always start work in a new git worktree (`git worktree add`) on a feature branch and open a PR — never edit the primary checkout directly, it may hold in-flight work.

把"不许直接改主检出"当成铁律交给 agent，是因为他们每天几十个 PR，主检出随时有在途工作。

### 2. "三选一"改动优先级：**删除 > 替换 > 新增**

`AGENTS.md` 的 Core Principles 第一条就是：

> **Less is more. The simplest solution is the best solution.** The action hierarchy for every change: **Delete > Replace > Add**.

并且配了一条**评审门禁**：对任何新增，评审人必须回答"删掉或改写已有代码能不能解决？能，就是阻塞级问题"。

还有硬性门槛：

> Treat new arguments and PRs with more than **50 net added non-documentation code lines** … as high-barrier exceptions.

### 3. 双层测试：快的每次提交都跑，慢的隔离

`pyproject.toml` 里注册了 marker，`tests/conftest.py` 里实现过滤：

```toml
markers = ["slow: skip slow tests unless --slow is set"]
```

```python
if not config.getoption("--slow"):
    items[:] = [item for item in items if "slow" not in item.keywords]
```

CI 里对应拆成 `Tests`（每次 PR/push）和 `SlowTests`（单独 job），再加 `GPU` / `RaspberryPi` / `NVIDIA_Jetson` 这些**跑不动的平台单独成 job**，而不是让主 job 挂一堆 skip。测试还用 `--dist=loadfile` 并行，并按机器规格**显式降并发**：

```bash
xdist="-n auto --dist=loadfile"
[[ "${{ matrix.os }}" == "macos-26" ]] && xdist="-n 2 --dist=loadfile"   # 3 vCPU/7GB，防止内存饿死
[[ "${{ matrix.os }}" == "ubuntu-24.04-arm" ]] && xdist=""               # xdist 下会掉线
```

### 4. 握手资料全部版本化、可机器校验

- `pyproject.toml` 里**每条**依赖都带"为什么钉这个版本"的注释：
  ```toml
  "opencv-python>=4.7.0,!=4.13.0.90", # 4.13.0.90 FIPS selftest crash <issue 链接>
  "torch>=1.8.0,!=2.4.0; sys_platform == 'win32'", # Windows CPU errors w/ 2.4.0
  ```
- `uv` 的互斥声明写进配置，而不是靠文档口口相传：
  ```toml
  [tool.uv]
  conflicts = [[{ extra = "export" }, { extra = "export-executorch" }, { extra = "export-legacy-torch" }], ...]
  ```
- 每个文件头是机器加的固定 license header，**不靠人记得加**。

### 5. 构建/发布流水线不靠人

`publish.yml`：检测 `__version__` 增量 → 打 tag → 生成 AI 摘要的 Release → PyPI trusted publishing → 生成 SBOM 挂到 Release → Slack 通知成功/失败。失败还会清掉残留 attestation 后重试一次。

### 6. 给"未来维护者"留地图，而不是留文档

`AGENTS.md` 最后一节叫 **Where to look**，写的是"症状 → 去哪个文件"的对照表：

> - 训练循环、AMP、EMA、resume、DDP → `engine/trainer.py`, `utils/torch_utils.py` …
> - 新 layer → `nn/modules/` 对应文件 … 然后 `nn/tasks.py` 让 `parse_model` 能解析
> - 数据集缓存或标注错误 → `data/dataset.py`（删掉过期的 `.cache`）

还有 **Extension boundaries** 一节明确写"哪里不许动"：

> 继承任务无关的引擎、覆写钩子；**不要 fork 训练或预测循环**。

### 7. 注册表式扩展点 + 注册清单同步校验

新增一个能力要同时登记到一串清单，`AGENTS.md` 把它们一条不落地列出来：

> 新增可训练任务 → `TASKS`、`TASK2DATA`、`TASK2CALIBRATIONDATA`、`TASK2MODEL`、`TASK2METRIC`；还要看 `guess_model_task()`、`build_yolo_dataset()`、`Results` 类型。

新 export 格式 → `export_formats()` 一行 + `EXPORT_ENVS` 配方 + 转换代码 + runtime 类 + `_BACKEND_MAP` 注册 + 测试。

### 8. 多平台/多版本的兼容债集中登记、显式注释

`pyproject.toml` 里 20 多个 export extra 全是条件依赖，每条都注明平台和原因。这是"我们已知哪些组合有毒"的**唯一台账**。

---

## 三、驭臂现在有什么（不是从零开始）

必须先说清楚：**驭臂的工程化程度明显高于一般个人项目。** 以下 6 件事，Ultralytics 也在做，而驭臂已经做了——只是做法不同：

| 驭臂已有 | 位置 | 对照 Ultralytics |
|---|---|---|
| **版本锁 + 逐包理由** | `requirements.lock`（头部写明"为什么钉、何时才能升级"） | 对应 `pyproject.toml` 依赖注释，风格一致 |
| **接口清单（21 项可执行检查表）** | `软件/骨架/官方接口清单.py` | 对应 `_BACKEND_MAP` / `parse_model` 注册表，但驭臂做成了**可自检的合同**，更进一步 |
| **版本 + 接口两道防线** | + `工具/检查版本锁.py` | Ultralytics 没有这么明确的"边界合同"概念 |
| **不变量可执行化** | `软件/零改动自检.py`（哈希证明"加算法不动外壳"） | 对应他们的回归测试；**想法比他们更贴题** |
| **数据驱动 + 生成产物** | `软件/风格表.json` → `优化/风格样张.html` | 对应 `docs/build_reference.py` 从 docstring 生成文档 |
| **实测台账** | `优化（软件优化的报告都放这里面来）/验证/implot样式项安全矩阵.txt`（20 项里 9 项段错误 → 明确不用）、`外观探针_输出.txt`、`字体覆盖_实测.txt` | 对应他们 issue 里对 bug 的钉版本注释，驭臂做成了**成体系的实测表** |

而且这些验证脚本**今天全绿**（我实际跑了）：

```
优化（软件优化的报告都放这里面来）/验证/校验风格表.py      → exit 0 · 395 个颜色值 + 140 个样式值全部合法
优化（软件优化的报告都放这里面来）/验证/验收面板文字.py    → exit 0 · 41 项通过 / 0 失败
优化（软件优化的报告都放这里面来）/验证/面板注册表自检.py  → exit 0 · 15/15 项通过
软件/零改动自检.py           → exit 0 · 核心逻辑零改动 ✅
```

**所以这份报告的基调不是"你缺什么"，而是"你已经有的东西，缺一层把它们固定下来的机制"。**

---

## 四、按优先级：该抄的 8 条

### 🔴 P0 — 建 git 仓库（这一条压倒其余全部）

**当时的现状（历史记录）**：项目目录尚未纳入 git 管理（`fatal: not a git repository`）。

**这不是理论风险，已经造成实际损失**：

| 证据 | 后果 |
|---|---|
| 桌面上的旧 `软件/` 副本仍在（Sep 17，现副本 Sep 22） | 项目存在**两份分叉的代码**，谁是准的靠文件名猜 |
| 旧副本**缺 9 个文件**：`模型桥.py`、`界面文字.py`、`皮肤桥.py`、`重力桥.py` + 面板层的 `外观面板.py`、`展示面板.py`、`模型库面板.py`、`面板容器.py`、`面板注册表.py` | 旧副本已无法运行 |
| **13 个文件内容不同**（主程序 157→246 行、参数辨识插件 199→294 行、启动 239→316 行…） | 9/17–9/22 的工作在旧目录里**没有对应记录** |
| 全项目 **133 处**引用旧路径 `数字样机/MuJoCoStudio_调研成果/03_实施` | 文档、启动器、报告里的路径已经和实际布局脱节 |
| `.DS_Store` ×6、`__pycache__` ×5、`启动日志.txt` 3.1 MB、`.venv` | 每次拷贝/打包都在搬运垃圾，日志里可能含本机路径 |

**为什么 P0 是 git 而不是别的**：

1. **`零改动自检.py` 的原理就是 git**。它现在用"哈希对基准文件"来模拟"哪些文件被改过"——这正是 `git status` / `git diff` 的职责。有了 git，它能升级成 `git diff --name-only` 的精确判定，还能顺带回答"谁、什么时候、为什么改的"。
2. **Ultralytics 的分支纪律（`AGENTS.md` 第一条铁律）以 git 为载体**。没有 git，"不许直接改主检出"这条无从落地。
3. **它是后面 7 条的地基**：changelog、CI、回归测试、PR 描述规范，全部挂在 git 上。

**最小可执行动作**（约 15 分钟）：

```bash
cd "$HOME/Desktop/驭臂"
git init -b main

# 先写 .gitignore，再 add —— 顺序反了会把 .venv 和日志塞进历史
cat > .gitignore <<'EOF'
# 环境与依赖（可用 工具/重建环境.sh 重建，不进版本库）
.venv/
离线依赖/

# Python 缓存
__pycache__/
*.py[cod]

# macOS
.DS_Store

# 运行时产物（每次跑都会变）
启动日志.txt
MUJOCO_LOG.TXT
输出/04_记录/*.csv
输出/04_记录/*.meta.json
输出/设置.json
输出/面板.json
输出/外观.json

# 验证脚本的临时输出（实测台账 .txt 要保留）
优化（软件优化的报告都放这里面来）/验证/*_输出.txt
EOF

git add -A
git commit -m "chore: 首次纳入版本管理（当前工作状态）"
```

然后**马上做一次"处女提交 + 打 tag"**，作为可回退的基线：

```bash
git tag -a v0.3-基线 -m "纳入版本管理时的可用状态：5 模型 / 8 面板 / 6 插件 / 自检全绿"
```

**旧副本怎么处理**：不要直接删。用 git 做一次"并集"确认——把旧副本里**有而新副本没有**的东西找出来（我已确认：`studio_shell` 层面旧副本是纯子集，没有独有文件），确认后归档到仓库外（如 `~/Desktop/_归档_数字样机_20260922/`），并在 `文档/` 留一行说明它为什么被归档。

> ⚠️ **不要做的事**：`git add 离线依赖/` 和 `.venv/`。前者是 300+ MB 二进制，后者可以用 `工具/重建环境.sh` 重建。大文件一旦进历史，`git clone` 会永久背这个包袱——Ultralytics 用 `actions/cache` 缓存测试资产，同样不把二进制放进仓库。

---

### 🟠 P1 — 试验 Changelog（你每天在发版，却没有发版说明）

**Ultralytics 的做法**：版本号写在 `ultralytics/__init__.py` 的 `__version__`，push main 自动打 tag + 生成 Release note；**每天 1～2 个版本**，Release note 就是当天改动的清单。

**驭臂的现状**：
- C 端版本散落：`工具/打包应用.py --版本` 默认 `0.3`、插件类里各写 `版本 = "0.1"`、`风格表.json` 里有 `"_版本": "v1 · 2026-09-17"`、`requirements.lock` 是另一套版本口径。
- `优化/风格表.json` 和 `软件/风格表.json` 是**同一份文件的两份拷贝**（我实测：逐字节相同，都是 24,588 字节）。这个"两份拷贝"本身就是没版本库的产物——今天一致，改一份就会漂移。有 git 之后应该只留一份（或在 `CHANGELOG` 里说明为什么必须有两份）。
- 全项目 **0 处** `TODO/FIXME/待办` 标记，说明没有承载"已知未完成项"的地方。

**这一条对你为什么比 Ultralytics 更重要**：他们的用户是 API 调用者，看文档就行；**你的用户是"自己"**——每天在切模型、调皮肤、改面板。三周后你只会记得"上次那版 PD 控制挺稳"，不会记得"是哪一版、当时 mujoco 是哪个版本、动了哪个文件"。

**最小动作**：建 `CHANGELOG.md`，每个 tag 一段，四行就够：

```markdown
## v0.3 — 2026-09-22
- 环境：mujoco 3.13.0（requirements.lock 未变）
- 新增：模型库面板（5 台机械臂，可热切换）
- 修复：面板注册表清理时吞掉官方停靠数据段（见 优化（软件优化的报告都放这里面来）/验证/面板注册表自检.py 回归项）
- 已知未完成：外观面板只覆盖 5 套风格，implot StyleVar 9 项段错误仍避开
```

配合 git 一条命令生成草稿：

```bash
git log --oneline --no-merges v0.2..v0.3
```

---

### 🟠 P1 — 统一测试入口：把散落的验证脚本收成两条命令

**Ultralytics 的做法**：
```bash
# 快测：每次提交都跑
pytest -n auto --dist=loadfile --cov=ultralytics/ tests/ --export-env base
# 含慢测
pytest --slow tests/
```
CI 里 `Tests`（每次 PR/push）与 `SlowTests`（独立 job）分离，`GPU`/`RaspberryPi`/`Jetson` 各自独立 job。

**驭臂的现状**：`优化（软件优化的报告都放这里面来）/验证/` 下有 **8 个验证脚本，天赋极好但没人统一调度**。我实测它们**全都自带断言和 exit code**——这已经就是测试了，只差一个入口：

| 脚本 | 能否无头跑 | 今天实测 |
|---|---|---|
| `校验风格表.py` | ✅ 不用开窗 | exit 0 |
| `验收面板文字.py` | ✅ 不用开窗（内部转调 `字体覆盖.py`） | exit 0 |
| `面板注册表自检.py` | ✅ 不用开窗 | exit 0 |
| `字体覆盖.py` | ✅ 不用开窗 | exit 0 |
| `软件/零改动自检.py` | ✅ 不用开窗 | exit 0 |
| `验收换肤.py` | ❌ **要开真窗口** | 未跑 |
| `外观探针.py` | ❌ 要开真窗口 | 未跑 |
| `生成样张.py` | — 生成 HTML 产物 | 未跑 |

**这一条直接解决一个真实痛点**：README 反复强调"必须用 `.venv` 的 python"，而每次改完插件，上面 5 个无头脚本理论上都该重跑一遍——**现在全靠人记得**，所以迟早会忘。

**最小动作 A（不改任何现有脚本，15 行搞定）**：建 `工具/跑检查.sh`：

```bash
#!/bin/bash
# 驭臂 · 快速检查（全部无头，不用开窗口，秒级）
# 对应 Ultralytics 的 Tests job。改完插件/面板/风格表，提交前跑这个。
set -u
cd "$(dirname "$0")/.."
PY=".venv/bin/python"
失败=0

跑() {
  echo "──────── $1 ────────"
  if "$PY" "$1" > /tmp/驭臂检查.log 2>&1; then
    echo "  ✓ 通过    $(tail -1 /tmp/驭臂检查.log)"
  else
    echo "  ✗ 失败（exit=$?）"; tail -20 /tmp/驭臂检查.log; 失败=$((失败+1))
  fi
}

跑 "软件/零改动自检.py"
跑 "优化（软件优化的报告都放这里面来）/验证/校验风格表.py"
跑 "优化（软件优化的报告都放这里面来）/验证/验收面板文字.py"
跑 "优化（软件优化的报告都放这里面来）/验证/面板注册表自检.py"

echo
if [ "$失败" -eq 0 ]; then echo "全部通过 ✅"; else echo "$失败 项失败 ❌"; fi
exit "$失败"
```

**最小动作 B（想进一步对齐 Ultralytics）**：装 pytest，把现有脚本包成测试，获得"一个失败不影响其余 + 汇总报告"：

```bash
.venv/bin/pip install pytest
```

```python
# 优化（软件优化的报告都放这里面来）/验证/test_检查.py —— 薄壳，逻辑仍在原脚本里（不改动它们）
import subprocess, sys, pytest

无头脚本 = [
    "软件/零改动自检.py",
    "优化（软件优化的报告都放这里面来）/验证/校验风格表.py",
    "优化（软件优化的报告都放这里面来）/验证/验收面板文字.py",
    "优化（软件优化的报告都放这里面来）/验证/面板注册表自检.py",
]

@pytest.mark.parametrize("脚本", 无头脚本)
def test_无头检查(脚本):
    """每个脚本自带断言与 exit code，这里只负责汇总（对应 Ultralytics 的 Tests job）。"""
    r = subprocess.run([sys.executable, 脚本], capture_output=True, text=True)
    assert r.returncode == 0, f"{脚本} 失败：\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}"
```

再加一个"要开窗"的 marker，对齐他们的 `--slow` 分层：

```python
# 优化（软件优化的报告都放这里面来）/验证/conftest.py
import pytest

def pytest_addoption(parser):
    parser.addoption("--开窗", action="store_true", default=False,
                     help="跑需要真实窗口的验收（验收换肤/外观探针），对应 Ultralytics 的 --slow")

def pytest_collection_modifyitems(config, items):
    if not config.getoption("--开窗"):
        items[:] = [i for i in items if "开窗" not in i.keywords]
```

用法就和 Ultralytics 一模一样了：

```bash
.venv/bin/python -m pytest 优化（软件优化的报告都放这里面来）/验证/           # 秒级快测，每次提交
.venv/bin/python -m pytest --开窗 优化（软件优化的报告都放这里面来）/验证/    # 含真窗口验收
```

---

### 🟡 P2 — 三份 JSON 清单加校验（照抄你自己的 `校验风格表.py` 思路）

**Ultralytics 的做法**：能力必须**同时**登记到一串清单，`AGENTS.md` 明确列出漏一个都不行（`TASKS` / `TASK2DATA` / `TASK2METRIC` / `_BACKEND_MAP` …）。

**驭臂的现状**：注册表已经做得很好——`模型/模型库.json` ↔ `模型/` 目录我实测**完全一致**（6 台，无孤儿、无缺失），`工具/模型清单.json` 也是。但**没有任何脚本在校验它们**，纯靠手工纪律；一旦漂移，表现是"模型列表里点一台，程序报错"。

**关键洞察**：`校验风格表.py` 已经解决了**同一个问题的一个实例**——它逐键校验 `风格表.json` 里的键名是否真实存在于绑定枚举中（"写错一个字母，换肤那一行就抛 `AttributeError`"）。把同一个思路复制到另外三份清单即可：

```python
# 优化（软件优化的报告都放这里面来）/验证/校验模型库.py（新）—— 复用 校验风格表.py 的写法
# 校验点：① 模型库.json 声明的每台机器，模型/<目录>/ 真的存在
#         ② 每台机器的 XML 能被 mujoco.MjModel.from_xml_path() 加载
#         ③ 模型/ 下有目录但未声明 → 警告（孤儿资产）
#         ④ 声明的执行器/关节名能在 XML 里找到（拼错就是运行时 KeyError）
```

同时**给 `外壳指纹.json` 补时间戳**，解决一个真实的可维护性坑：

```json
{
  "_说明": "零改动自检的哈希基准。改了核心文件后跑 `--建立` 更新，并在 CHANGELOG 里记一行改了哪个文件、为什么。",
  "_建立时间": "2026-09-22",
  "_对应版本": "v0.3",
  "核心文件": { ... }
}
```

为什么重要：`零改动自检.py` 的语义是"核心文件没被动过"，但它**不区分**"健康的零改动"和"某人图省事跑了 `--建立` 把越界改动洗白"。加时间戳 + CHANGELOG 记录后，这个数字就有了审计含义——这正是 Ultralytics `AGENTS.md` 里那条准则的落地：**代码改动必须能回答"为什么"**。

---

### 🟡 P2 — 按"症状 → 去哪个文件"重写文档入口

**Ultralytics 的做法**：`AGENTS.md` 结尾的 **Where to look** 是整份文档最有价值的部分——不写"模块介绍"，写**故障定位表**：

> 数值不对 / mAP 异常 → `engine/validator.py`, `models/yolo/<task>/val.py`, `utils/metrics.py`

**驭臂的现状**：文档量**远超需要**（`使用手册.md` 197 KB、`文档/驭臂_完整工作报告.md` 244 KB、`启动日志.txt` 3.1 MB），但入口是"按功能罗列"，不是"按症状索引"。加上 133 处路径已经指向旧目录 `数字样机/MuJoCoStudio_调研成果/03_实施`（**该目录今天还在**，所以文档"看起来没错"，实际两套路径并存）。

**最小动作**：在 `软件/README.md` 顶部加一节，只写症状：

```markdown
## 出问题了？先查这里

| 症状 | 去哪个文件 | 自检命令 |
|---|---|---|
| 面板上出现一串 `?` | `软件/界面文字.py` 术语表 | `.venv/bin/python 优化（软件优化的报告都放这里面来）/验证/验收面板文字.py` |
| 换了风格但面板没变 | `软件/皮肤桥.py`（官方 `ux.setup_theme()` 之后要补推一次） | `.venv/bin/python 优化（软件优化的报告都放这里面来）/验证/校验风格表.py` |
| 启动就报 `ImportError: cannot import name 'sim'...` | 用错环境了（conda 的 mujoco 是零件版） | `.venv/bin/python 软件/主程序.py --检查` |
| 官方升级后某处崩了 | `软件/骨架/官方接口清单.py` 的 21 项 | `.venv/bin/python 软件/主程序.py --自检` |
| 环境版本和实测不一致 | `requirements.lock` | `.venv/bin/python 工具/检查版本锁.py` |
| 换布局后官方面板消失 | `软件/面板/面板注册表.py` 的清理逻辑 | `.venv/bin/python 优化（软件优化的报告都放这里面来）/验证/面板注册表自检.py` |
```

**再补一步**：把 133 处旧路径统一成"相对包根"的写法。这件事 git 之后变得安全（可回退），且能顺手验证启动器：

```bash
# 先看清楚要改哪些（别直接 -i）
grep -rln "数字样机\|MuJoCoStudio_调研成果" --include="*.py" --include="*.md" --include="*.sh" . \
  | grep -v "^./.venv" | grep -v "^./离线依赖"
```

> 顺带一个实测发现：`驭臂.app/Contents/Resources/启动.sh` 里搜主程序的候选列表是 `"$PKG_DIR/软件/主程序.py" "$PKG_DIR/软件/主程序.py" "$PKG_DIR/软件/主程序.py"`——**前两项完全相同**，而且报错文案也是"期望位置：软件/主程序.py 或 软件/主程序.py"。显然是改名时漏改的，删掉重复项、只留 `软件/主程序.py` + 一个兼容项即可。这类小瑕疵正是"没有 diff 审查"的典型产物。

---

### 🟢 P3 — `AGENTS.md`：给 AI 助手写一份项目说明书

**Ultralytics 的做法**：`AGENTS.md` 13.5 KB，是**唯一**一份写给"改代码的人（含 AI）"的文档，内容全是硬约束：

- Core Principles（Delete > Replace > Add、最小改动、先搜后建）
- PR Review（50 行门槛、拒绝兼容 shim、拒绝 mock 测试）
- Commands（可直接复制的命令）
- Conventions（版本号格式、license header、docstring 风格、任务顺序必须全局一致）
- Where to look / Extension boundaries

**为什么对驭臂价值极高**：你的项目**已经在用 AI 协作了**——`零改动自检.py` 的注释里赫然写着"★ 写算法时要记住的一条（**踩过**）：面板上只能显示 ASCII"，模板里也写了"踩过"。这些是**血泪经验，但埋在各个文件里**，每次开新会话都要重新发现一遍。

**最小动作（照抄结构，内容换成驭臂的）**：

```markdown
# AGENTS.md —— 给改这个项目的人（含 AI）的说明书

## 铁律
- 不许直接改 `软件/插件系统.py`、`软件/启动.py`、`软件/界面桥.py` —— 改了就过不了 `零改动自检.py`
- 所有官方 API 调用**只能**出现在 `软件/插件系统.py` 和 `软件/骨架/官方接口清单.py` 里；用新的官方接口前**先在清单里登记**
- 面板上只能显示 ASCII（官方字体只装了 Atkinson Hyperlegible）。要加中文字符串 → 先查 `软件/界面文字.py`；新增中文标签前跑 `优化（软件优化的报告都放这里面来）/验证/验收面板文字.py`
- 不许动 `implot` 的 StyleVar（20 项有 9 项段错误，见 `优化（软件优化的报告都放这里面来）/验证/implot样式项安全矩阵.txt`）

## 改完必须跑
    bash 工具/跑检查.sh

## 加一个新控制算法
    ① 复制 `算法库/通用/我的控制律_模板.py`
    ② 写 `每步控制()`（面板要显示的名字写 `英文名`，ASCII）
    ③ 在 `软件/主程序.py` 的【插件清单】加 import + 一个实例
    ④ 跑 `零改动自检.py`：应该只看到"插件清单区段有改动 + 新增插件"两行

## 出问题了去哪个文件
（接上面那张症状表）

## 环境
- 必须用 `.venv/bin/python`（conda 的 mujoco 是零件版，无界面层）
- mujoco 钉在 3.13.0，见 `requirements.lock`；升级前必须跑完 `--自检` 21 项 + 开窗 + 控制律
```

---

### 🟢 P3 — CI（可以不要 GitHub，但要"每次提交自动跑"）

**Ultralytics 的做法**：11 个 workflow、`ci.yml` 673 行。**这一条你必须按比例缩**——你是单人本地项目，61.9k star 的矩阵策略对你毫无意义。

**真正可抄的只有两个机制**：

1. **提交前自动跑**（最省事的版本是 git hook，不需要任何云服务）：

   ```bash
   # 工具/安装钩子.sh —— 跑一次即可
   cat > .git/hooks/pre-commit <<'EOF'
   #!/bin/bash
   # 提交前跑快速检查；失败则拒绝提交（对应 Ultralytics 的 Tests job）
   exec "$(git rev-parse --show-toplevel)/工具/跑检查.sh"
   EOF
   chmod +x .git/hooks/pre-commit
   ```

   > `.git/hooks/` 不进版本库。如果想让它随仓库走，放到 `工具/git-hooks/pre-commit` 并让 `安装钩子.sh` 做软链接。

2. **定时跑"重"检查**（对齐他们的 `schedule: cron` 每日跑）：
   - 驭臂对应的不是"每天"，而是**"每次官方 mujoco 升级后"**和**"每次改完面板后"**。
   - 用 `launchd` 或最简单的 `cron`，每周跑一次 `--开窗` 验收（`验收换肤.py` / `外观探针.py`）并把输出覆盖到 `优化（软件优化的报告都放这里面来）/验证/*_输出.txt`，这样**实测台账自动保鲜**。

**明确不建议抄的 Ultralytics 实践**（对驭臂是负收益）：

| 他们的做法 | 为什么驭臂不该抄 |
|---|---|
| 673 行多平台 CI 矩阵 | 单人本地 macOS 项目，维护成本 >> 收益 |
| CLA 机器人 / `stale.yml` / `merge-main-into-prs.yml` | 没有外部贡献者，纯粹是负担 |
| 460 人协作的 50 行 PR 门槛 | 你一个人开发，门槛会卡住自己 |
| 每日蒙特卡洛 fuzz | 他们的输入空间是"无数参数组合"；你的边界是"6 台模型 × 官方升级"，**用 `校验模型库.py` 定点覆盖更划算** |
| AI 自动 PR 摘要 + Slack 通知 | 无意义 |
| 19 万行测试 | 驭臂 1 万行源码，8 个验证脚本已经是合理密度，**该做的是统一入口而不是扩规模** |

---

## 五、执行顺序（一张表看完）

| 优先级 | 动作 | 产出物 | 预计耗时 | 卡的痛点 |
|---|---|---|---|---|
| 🔴 P0 | `git init` + `.gitignore` + 首次提交 + 打基线 tag | `.gitignore`、`v0.3-基线` | 15 分钟 | 两份分叉副本；无法回退 |
| 🔴 P0 | 归档旧目录 `数字样机/MuJoCoStudio_调研成果/03_实施` | 归档目录 + 一行说明 | 10 分钟 | 改错副本 |
| 🟠 P1 | `工具/跑检查.sh`（把 5 个无头脚本收成一个入口） | 1 个脚本 | 15 分钟 | "改完忘了跑自检" |
| 🟠 P1 | `CHANGELOG.md` + 每个 tag 一段 | 1 个文件 | 持续 | 三周后不记得改了什么 |
| 🟡 P2 | 装 pytest + `test_检查.py` 薄壳 + `--开窗` marker | 2 个文件 | 30 分钟 | 想一次跑完并看汇总 |
| 🟡 P2 | `优化（软件优化的报告都放这里面来）/验证/校验模型库.py`（照抄 `校验风格表.py`） | 1 个脚本 | 40 分钟 | 清单漂移 → 点模型报错 |
| 🟡 P2 | `外壳指纹.json` 加 `_建立时间` / `_对应版本` | 改 1 处 | 10 分钟 | 指纹被"洗白"无法审计 |
| 🟡 P2 | `软件/README.md` 加"症状 → 文件"表 + 清理 133 处旧路径 | 文档 | 1 小时 | 文档路径与实际布局脱节 |
| 🟢 P3 | `AGENTS.md`（含 ASCII 铁律、implot 禁用法、加插件三步） | 1 个文件 | 1 小时 | 踩过的坑每次重新踩 |
| 🟢 P3 | `工具/安装钩子.sh`（pre-commit 自动跑检查） | 1 个脚本 | 10 分钟 | 提交即验证 |
| 🟢 P3 | 每周跑的"开窗"验收（台账自动保鲜） | cron/launchd | 20 分钟 | 真机验收容易过时 |

---

## 六、一句话总结

Ultralytics 值得学的**不是**它那 11 个 workflow 和 19 万行测试——那是 460 人、6 万 star 规模的产物，照搬会把自己压死。

值得学的是它的**三条底层习惯**：

1. **不变量要能机器验证**（他们的注册表清单 = 你的 `零改动自检.py` + `官方接口清单.py`，**你已经做到了，而且更贴题**）；
2. **每次改动都要能回答"为什么"和"改了哪里"**（依赖钉版本的注释、release note、`AGENTS.md` 的踩坑记录 = 你的 `requirements.lock` 注释、实测台账、插件模板里那句"踩过"）；
3. **重复动作交给机器，不靠人记得**（CI、pre-commit、自动发布）。

**驭臂在第 1、2 条上已经领先于大多数个人项目；缺的是第 3 条，以及承载第 3 条的 git。**

所以答案回到最开始那句：**值得参考的地方很多，但今天最该做的一件事是 `git init`。** 其余 7 条都以它为地基——没有版本历史，"零改动"无法证明，changelog 无处可写，回归测试无处可依。

---

## 附：证据清单（可复核）

| 结论 | 复核方式 |
|---|---|
| 驭臂非 git 仓库 | `cd ~/Desktop/驭臂 && git status` → `fatal: not a git repository` |
| 两份分叉副本 | `ls ~/Desktop/数字样机/MuJoCoStudio_调研成果/03_实施/软件/` |
| 旧副本缺 9 个文件（4 模块 + 5 面板） | 逐文件对比两个目录 |
| 13 个文件内容不同 | `diff` 逐文件（主程序 157 vs 246 行） |
| 133 处旧路径 | `grep -rn "数字样机" --include="*.py" --include="*.md" .` |
| 5 个验证脚本今天全绿 | `for t in ...; do .venv/bin/python "$t"; echo $?; done` |
| 脚本自带 exit code | `tail -20 优化（软件优化的报告都放这里面来）/验证/校验风格表.py`（`raise SystemExit(main())`） |
| 模型库清单与目录一致 | 比对 `模型/模型库.json` 与 `ls 模型/`（6 台，无孤儿） |
| 启动器候选路径重复 | `cat 驭臂.app/Contents/Resources/启动.sh` 搜主程序那段 |
| Ultralytics CI 规模 | `.github/workflows/ci.yml` 673 行；11 个 workflow 文件 |
| Ultralytics 提交/发版节奏 | GitHub API `commits?per_page=15`、`releases?per_page=5` |
| 460 名贡献者 | GitHub API `contributors?anon=true` → `rel="last"` 页 460 |
| AGENTS.md 铁律原文 | `AGENTS.md` 的 Core Principles / PR Review / Conventions 三节 |
