# Ultralytics YOLO：模块 ↔ 算法 的封装方式，以及"是否等价于插件系统"

> **本文件是 `文档/架构对比_模块算法封装_对照Ultralytics.md` 的附件**：主报告给结论与改进建议，
> 本附件是 Ultralytics 侧的逐文件源码取证（682 行，每条结论带 `文件:行号`）。
> 主报告第五节取自本附件，并已按本附件给出的更正修订（见主报告 §5.5）。

> 分析对象：本机研究用的 Ultralytics 源码快照（未随本项目分发；`__version__ = "8.4.160"`，见 `ultralytics/__init__.py:3`）
> 分析方式：纯静态阅读，**未修改任何文件**。所有结论均给出 `文件:行号` 证据。
> 本地环境无 `torch`（`/usr/bin/python3 -c "import torch"` → `ModuleNotFoundError`），因此**没有做运行时实验**，全部为代码级证据。

---

## 一句话总结

**Ultralytics 没有插件系统。**它的"模块 ↔ 算法"关系由**一个字符串名字解析器**（`parse_model` 里的 `globals()[m]`，`ultralytics/nn/tasks.py:2104-2110`）实现，所谓"注册表"就是 `tasks.py` 顶部那 90 行人工维护的 `from ultralytics.nn.modules import (...)`（`tasks.py:18-105`）；唯一接近插件机制的是**回调（hook）体系**（`ultralytics/utils/callbacks/base.py:121-151` 的事件名→回调列表字典），但它只有"插"没有"系统"：**无发现、无契约、无清单、无错误隔离、无版本协商、无优先级**——而这六件事你的 `软件/插件系统.py` 全部实现了。

---

## 一、模块注册与发现机制

### 1.1 YAML → `nn.Module` 的编译：`parse_model`

`parse_model(d, ch, verbose=True)`（`ultralytics/nn/tasks.py:2007-2218`）是唯一的"声明→对象"编译器。

**（a）全局参数解析（2021-2042）**

```python
nc, act, scales, end2end = (d.get(x) for x in ("nc", "activation", "scales", "end2end"))   # 2024
reg_max = d.get("reg_max", 16)                                                             # 2025
depth, width, kpt_shape = (d.get(x, 1.0) for x in ("depth_multiple", "width_multiple", "kpt_shape"))  # 2026
scale = d.get("scale")                                                                     # 2027
if scales:
    if not scale: ... LOGGER.warning(f"no model scale passed. Assuming scale='{scale}'.")   # 2029-2031
    depth, width, max_channels = scales[scale]                                              # 2032
```
`act` 走 `eval(act)`（2038）——这是全仓库唯一一处对 YAML 求值的地方；受限加载模式下改走 `_SafeLoad.activation`（2038、`tasks.py:1730-1758`，AST 白名单，只允许 `nn.Xxx(literal...)`）。

**（b）三级名字解析（2104-2110）—— 核心**

```python
m = (
    getattr(torch.nn, m[3:])                              # "nn.Upsample" → torch.nn.Upsample
    if m.startswith("nn.")
    else getattr(__import__("torchvision").ops, m[16:])   # "torchvision.ops.XXX"
    if m.startswith("torchvision.ops.")
    else globals()[m]                                     # 其它 → tasks.py 模块自己的全局命名空间
)  # get module
```
- 第三级 `globals()` 是 **`ultralytics/nn/tasks.py` 自己的模块字典**。
- 因此一个模块类"可被 YAML 寻址"的**充分必要条件**是：它被显式导入到了 `tasks.py` 的模块命名空间（`tasks.py:18-105`）。
- `globals()` 里同时存在 `torch`、`nn`、`re`、`Path`、`deepcopy`、`np`、`contextlib` 等非模块对象，且**不做类型检查**（除非开启受限加载，见 2111-2113）——理论上 YAML 写 `- [-1, 1, Path, [...]]` 会解析成功，直到实例化才炸。
- 官方文档把这个三级机制当作正式 API 记录：`docs/en/guides/model-yaml-config.md:205-224`。

**（c）args 字符串解析（2114-2117）**

```python
for j, a in enumerate(args):
    if isinstance(a, str):
        with contextlib.suppress(ValueError):
            args[j] = locals()[a] if a in locals() else ast.literal_eval(a)
```
- 先在 `parse_model` 的 `locals()` 里找（`nc`/`reg_max`/`width`/`max_channels`/`kpt_shape`/`legacy`/`ch`/`d`…），否则用 `ast.literal_eval`。
- 这是 YAML 能写 `[nc]`、`[nc, kpt_shape]` 的原因。实例：`ultralytics/cfg/models/26/yolo26-pose.yaml` 末行 `- [[16, 19, 22], 1, Pose26, [nc, kpt_shape]]`；`yolo26.yaml` 末行 `- [[16, 19, 22], 1, Detect, [nc]]`。
- 注意 `contextlib.suppress(ValueError)`：解析失败**静默保留字符串**，错误推迟到构造函数。

**（d）深度增益（2118）**

```python
n = n_ = max(round(n * depth), 1) if n > 1 else n
```

**（e）`base_modules`（2046-2083）—— 通道注入协议**

33 个类（`Classify, Conv, ConvTranspose, GhostConv, Bottleneck, GhostBottleneck, SPP, SPPF, C2fPSA, C2PSA, DWConv, Focus, BottleneckCSP, C1, C2, C2f, C3k2, RepNCSPELAN4, ELAN1, ADown, AConv, SPPELAN, C2fAttn, C3, C3TR, C3Ghost, torch.nn.ConvTranspose2d, DWConvTranspose2d, C3x, RepC3, PSA, SCDown, C2fCIB, A2C2f`）。命中后：

```python
c1, c2 = ch[f], args[0]                                                     # 2120
if m is not Classify:
    c2 = make_divisible(min(c2, max_channels) * width, 8)                    # 2122
args = [c1, c2, *args[1:]]                                                  # 2133
if m in repeat_modules:
    args.insert(2, n); n = 1                                                # 2134-2136
```
即 **YAML 里写 `[c2, 其余...]`，`c1` 和 `n` 由解析器补齐**。实例链路：YAML `- [-1, 2, C3k2, [256, True]]` → `args=[c1,256,True]` → insert(2, 2) → `C3k2(c1, 256, 2, True)`，对应签名 `C3k2.__init__(self, c1, c2, n=1, c3k=False, e=0.5, attn=False, g=1, shortcut=True)`（`ultralytics/nn/modules/block.py:1075-1085`）。

`repeat_modules`（2084-2102）是 15 个可重复块的子集。

**（f）逐个硬编码的特例分支（2123-2202）**

| 行号 | 模块 | 特例内容 |
|---|---|---|
| 2123-2131 | `C2fAttn` | 重算 `args[2]`（头数）与 `args[1]`（隐藏通道），并 `raise ValueError` 做整除校验 |
| 2137-2140 | `C3k2` | M/L/X 尺度下 `args[3:4] = [True]`，并翻转 `legacy=False` |
| 2141-2146 | `A2C2f` / `C2fCIB` | L/X 下 `args.extend((True, 1.2))` / `legacy=False` |
| 2147-2148 | `AIFI` | `args = [ch[f], *args]` |
| 2149-2154 | `HGStem`/`HGBlock` | `c1, cm, c2` 三通道；HGBlock 还 `insert(4, n)` |
| 2155-2156 | `ResNetLayer` | `c2 = args[1] if args[3] else args[1]*4` |
| 2157-2158 | `torch.nn.BatchNorm2d` | `args = [ch[f]]` |
| 2159-2160 | `Concat` | `c2 = sum(ch[x] for x in f)` |
| **2161-2180** | **10 个检测头** | `args.extend([reg_max, end2end, [ch[x] for x in f]])`；Segment 系再缩放 `args[2]`；除 `v10Detect` 外统一打 `m.legacy = legacy` |
| 2181-2182 | `Depth` | `args = [*args[:1], [ch[x] for x in f]]` |
| 2183-2184 | `SemanticSegment` | `args.append([ch[x] for x in f])` |
| 2185-2186 | `v10Detect` | `args.append([ch[x] for x in f])` |
| 2187-2188 | `ImagePoolingAttn` | `args.insert(1, [ch[x] for x in f])` |
| 2189-2190 | `RTDETRDecoder` | `args.insert(1, [ch[x] for x in f])` |
| 2191-2196 | `CBLinear` / `CBFuse` | `c2 = args[0]` / `c2 = ch[f[-1]]` |
| 2197-2200 | `TorchVision` / `Index` | `c2 = args[0]; args = [*args[1:]]` |
| **2201-2202** | **兜底** | **`else: c2 = ch[f]`** —— 未知模块静默假设"输出通道 == 输入通道" |

**（g）实例化与元数据（2204-2218）**

```python
m_ = torch.nn.Sequential(*(m(*args) for _ in range(n))) if n > 1 else m(*args)  # 2204
t = str(m)[8:-2].replace("__main__.", "")                                        # 2208
m_.np = sum(x.numel() for x in m_.parameters())                                  # 2209
m_.i, m_.f, m_.type = i, f, t                                                    # 2210  ← 运行时协议字段
save.extend(x % i for x in ([f] if isinstance(f, int) else f) if x != -1)        # 2213
...
return torch.nn.Sequential(*layers), sorted(save)                                # 2218
```
`m_.i / m_.f / m_.type` 是**注入到实例上的三个属性**，供 `_predict_once` 的跨层跳连使用（`tasks.py:194-195`、`199`）。

### 1.2 `nn/modules/__init__.py` 的聚合方式

`ultralytics/nn/modules/__init__.py`（194 行）是**纯手写清单**，没有任何自动化：
- 4 个子模块 re-export：`.block`（20-62）、`.conv`（63-78）、`.head`（79-97）、`.transformer`（98-109）
- `__all__` 显式列出约 100 个字符串（111-194）
- **没有 `__getattr__` 懒加载、没有 `glob(path)`、没有 `pkgutil.iter_modules`、没有命名约定推导**。

### 1.3 新模块要"可寻址"必须动的地方

官方文档给出的三步（`docs/en/guides/model-yaml-config.md:243-289`）与代码完全一致：

1. 在 `ultralytics/nn/modules/{block,conv,head,transformer}.py` 定义类
2. 在 `ultralytics/nn/modules/__init__.py` import + 加入 `__all__`（111-194）
3. **在 `ultralytics/nn/tasks.py:18-105` 的 `from ultralytics.nn.modules import (...)` 里 import** ← **这一步才是真正的"注册"**
4. （可选，推荐）加入 `base_modules`（2046-2083）/ `repeat_modules`（2084-2102），否则走 `else: c2 = ch[f]` 兜底（2201-2202）
5. 写 YAML

> AGENTS.md 也把这条写成硬规则：`AGENTS.md:94`「New layer → … export it from `nn/modules/__init__.py`, **import it into `nn/tasks.py` so `parse_model` can resolve it**」。

**结论：不存在"注册 API"，只有"Python 模块全局命名空间 + 人工 import"。**

### 1.4 显式插件式注册：**明确不存在**

执行的搜索与结果：

```bash
$ grep -rn "pluggy\|entry_points\|pkgutil\|stevedore\|register(" --include=*.py ultralytics/
（0 命中）
```

| 候选机制 | 结果 |
|---|---|
| `pluggy` | **0 命中** |
| `pkgutil` / 目录扫描 | **0 命中** |
| `entry_points` | **0 命中**（`pyproject.toml` 只有 `[project.scripts] yolo = "ultralytics.cfg:entrypoint"`、`ultralytics = "ultralytics.cfg:entrypoint"`，第 189-191 行；**没有 `[project.entry-points."组名"]` 段**） |
| `register()` / `@register` 装饰器 | 全仓库唯一命中 `ultralytics/trackers/track.py:133 def register_tracker(model, persist)`——它是往 `model.callbacks` 塞两个跟踪回调的便捷函数（`track.py:146-155`），本质仍是回调机制，不是模块注册表 |
| `importlib` | 存在但**与发现无关**：`ultralytics/__init__.py:42,46` 懒加载 `ultralytics.models`/`ultralytics_platform`；`nn/tasks.py:1607,1617,1688` 的 `temporary_modules()` 旧路径兼容 + 受限加载 allow-list 构造；`utils/checks.py:18 from importlib import metadata` 读包版本；`utils/__init__.py:885 importlib.util.find_spec` 判断是否 pip 包 |
| "plugin" 字面量 | 仅第三方库术语：ONNX Runtime EP plugin（`nn/backends/qnn.py:19,24,40-41`）、OpenVINO CPU plugin（`nn/backends/openvino.py:57`）、PIL HEIF plugin（`utils/patches.py:56-86`）、onnxruntime-qnn（`utils/export/qnn.py:14,75`）、ModelOpt torch plugins（`utils/torch_utils.py:426`）、mkdocs-macros-plugin（`pyproject.toml:93`）。**没有一处是 Ultralytics 自己的插件系统。** |

### 1.5 唯一像"模块白名单注册表"的东西：`_SafeLoad`（安全用途，非扩展用途）

`ultralytics/nn/tasks.py:1638-1812`：
- 由 `ULTRALYTICS_SAFE_LOAD` 环境变量开关（`tasks.py:1835` 读 `SAFE_LOAD`；定义在 `utils/__init__.py:73 SAFE_LOAD = env_bool("ULTRALYTICS_SAFE_LOAD")`），默认 **关**。
- `_SafeLoad._build()`（1760-1812）手工维护一张 `"新类 ↔ 旧 pickled 名"` 别名表，例如 `(nn.Identity, "ultralytics.nn.modules.block.Silence")`、`(DetectionModel, "ultralytics.nn.tasks.YOLOv10DetectionModel")`、`(ul_loss.E2EDetectLoss, "ultralytics.utils.loss.v10DetectLoss")`（1791-1795）。
- `loading()`（1663-1728）用 `torch.serialization.get_unsafe_globals_in_checkpoint` 扫描 checkpoint 实际引用的全局名，只注册需要的（注释明确解释为何不用 `safe_globals()` 上下文：进程级集合并发下会被别的线程提前摘掉）。
- 开启后 `parse_model` 只允许 `torch.nn.Module` 子类做层，否则 `raise TypeError`（2111-2113）。

**这是全仓库唯一的"白名单注册表"，但它是安全沙箱，且默认关闭。它同时说明了一个设计取舍：可扩展性（任意 `globals()[m]`）与安全性（allow-list）在 Ultralytics 里是互斥的。**

另有 `AutoBackend._BACKEND_MAP`（`ultralytics/nn/autobackend.py:153-180`，24 个格式→后端类）是"注册表风格字典"的另一实例，消费点在 232-246，未命中时给出友好 `TypeError` 并列出支持格式（234-239）。这是全仓库**错误信息质量最高的注册表**。

---

## 二、模块 ↔ 算法契约

### 2.1 构造函数契约（隐式，无强制）

| 层级 | 要求 | 谁负责注入 |
|---|---|---|
| **L1 叶子模块** | `forward(x)` 张量进张量出即可；**不要求** `(c1,c2)` | 无。argv 全写在 YAML `args` 里 |
| **L2 标准块** | `__init__(self, c1, c2, *rest)` | `parse_model` 只在模块属于 `base_modules`（2046-2083）时注入 `c1 = ch[f]`、`c2 = make_divisible(min(args[0], max_channels)*width, 8)`（2120-2122、2133） |
| **L2+ 可重复块** | 第 3 个位置参数必须是 `n` | 属于 `repeat_modules`（2084-2102）才会 `args.insert(2, n)`（2135） |
| **L3 头/特殊段** | 必须在 `parse_model` 里有专属 `elif m is X:` 分支 | 例如 Detect 系依赖 `args.extend([reg_max, end2end, [ch[x] for x in f]])`（2176） |

**没有任何 ABC / Protocol / `__init_subclass__` / 运行时 `inspect.signature` 校验。** 违反契约的后果是构造期 `TypeError: __init__() missing 1 required positional argument` 或更晚的 shape mismatch。

### 2.2 `forward` 契约：`(x)` vs `(x, y)`

**基础执行器只支持单参数调用**——`BaseModel._predict_once`（`tasks.py:179-204`）：

```python
for m in self.model:
    if m.f != -1:
        x = y[m.f] if isinstance(m.f, int) else [x if j == -1 else y[j] for j in m.f]   # 194-195
    ...
    x = m(x)  # 198  ← 永远是单参数
```
多输入通过 **`f` 是 list** 表达：此时 `x` 是 `list[Tensor]`，模块收到**一个 list 参数**（典型：`Concat.forward(self, x: list[torch.Tensor])`，`ultralytics/nn/modules/conv.py:633-642`）。

**真正的两输入 `(x, y)` 只存在于任务专用的 `predict()` 覆写里，且是硬编码的 `isinstance` 名单：**

`WorldModel.predict`（`tasks.py:1160-1195`）：
```python
if isinstance(m, C2fAttn):          x = m(x, txt_feats)          # 1184-1185
elif isinstance(m, WorldDetect):    x = m(x, ori_txt_feats)      # 1186-1187
elif isinstance(m, ImagePoolingAttn): txt_feats = m(x, txt_feats)# 1188-1189
else:                               x = m(x)                     # 1192
```
`YOLOEModel.predict`（`tasks.py:1410-1450`）在处理 `YOLOEDetect` 时同样手工拼 `cls_pe` 再 `x = m(x)`（1430-1444）。

对应的双输入模块：`SAVPE.forward(self, x, guide)`（`block.py:596`）、`C3k2`+attn 路径、`AAttn.forward(self, x, w)`（`block.py:766`）、`ImagePoolingAttn.forward(self, x, vp)`（`block.py:1959`）、`WorldDetect.forward(self, x, text)`（`head.py:912`）。

> **这是一处必须强调的脆弱点**：新增一个双输入模块，不仅要改 `parse_model`，还要再改一个 `predict()` 覆写里的 `isinstance` 清单。对比你的 `插件系统.py` 用 `plugin_registry._discover_handlers(插件)` 按**类型标注**自动匹配消息类型——你无意中做对了 Ultralytics 做错的事。

**`forward_fuse` 约定**：`BaseModel.fuse()`（`tasks.py:240-277`）会把可融合模块的 `m.forward` **原地替换**成 `m.forward_fuse`（262、266、269、272 行）。因此任何带 BN 的自定义模块若想在推理时融合，必须同时提供 `forward_fuse`（参考 `conv.py:80,129,260,398`；`block.py:810,1159`）。这是**通过猴子补丁实例属性实现的接口替换**，没有任何声明。

### 2.3 检测头契约（`self.stride / nc / no / yaml`）

`Detect`（`ultralytics/nn/modules/head.py:38-236`）必备要素：

| 要求 | 证据 |
|---|---|
| 类属性默认值：`dynamic/export/format/max_det/agnostic_nms/shape/anchors/strides/legacy/xyxy` | `head.py:79-88` |
| `__init__(self, nc=80, reg_max=16, end2end=False, ch: tuple = ())` | `head.py:107` |
| 必须设 `self.nc`、`self.nl = len(ch)`、`self.reg_max`、`self.no = nc + reg_max*4`、`self.stride = torch.zeros(self.nl)` | `head.py:117-121` |
| `forward(x: list[Tensor])`：training 返回 dict，inference 返回 `y if self.export else (y, preds)` | `head.py:179-193` |
| **必须实现 `bias_init()`** | `head.py:218-230`；被 `DetectionModel.__init__` 无条件调用（`tasks.py:506`） |
| 必须支持 `self.end2end` property/setter | `head.py:154-166`（setter 里有对无 one2one 头的 warning 降级） |

`self.stride` 的实际计算在 `DetectionModel.__init__`（`tasks.py:489-507`）：`eval()` 模式 + `m.training = True`，用 256×256 零张量跑一次前向，按 `s / x.shape[-2]` 反推每个检测层的 stride，然后 `self.stride = m.stride`（504-505）。**这就是为什么新头必须能被空跑。**

> **重要更正**：`self.yaml` **不在 head 上，在 `BaseModel` 上**。`_initialize_yolo_model`（`tasks.py:430-446`）设 `model.yaml = cfg dict`（432）、`model.yaml["channels"] = ch`（440）、按需覆写 `nc`（441-443）、`model.names`（445）、`model.inplace`（446）。
> `grep -rn "self\.yaml" ultralytics/nn/modules/*.py` → **0 命中**。唯一从 `self.yaml` 读自定义键的是 `YOLOEModel.__init__`：`self.text_model = self.yaml.get("text_model", "mobileclip:blt")`（`tasks.py:1253`）——**这是模型 YAML 唯一被当作"可扩展配置"使用的地方，且没有任何 schema 校验**。

`self.nc / self.names / self.args` 在**训练时挂到模型（不是 head）**上：`DetectionTrainer.set_model_attributes`（`ultralytics/models/yolo/detect/train.py:145-147`）：
```python
self.model.nc = self.data["nc"]
self.model.names = self.data["names"]
self.model.args = self.args
```
loss 侧再反向取：`v8DetectionLoss.__init__`（`ultralytics/utils/loss.py:345-357`）
```python
h = model.args                 # 346  ← 超参来源
m = model.model[-1]            # 348  ← head
self.stride = m.stride; self.nc = m.nc; self.no = m.nc + m.reg_max*4; self.reg_max = m.reg_max  # 351-354
```
> 也就是说 **"算法"（loss/criterion）通过 `model.args` + `model.model[-1]` 这两个约定接口读取一切**，head 与 loss 之间没有显式传参——这是纯隐式耦合。

### 2.4 `BaseModel` 的 train / infer 分派

```
forward(x, *args, **kwargs)                        tasks.py:146-161
├── isinstance(x, dict)  → self.loss(x)            # 159-160  训练/验证中
└── else                 → self.predict(x)         # 161      推理

predict(x, profile, augment, embed)                tasks.py:163-177
├── augment=True  → _predict_augment(x)            # 175-176
└── else          → _predict_once(x, profile, embed)# 177

_predict_once(x, profile, embed)                   tasks.py:179-204   基础实现（单参数 m(x)）
_predict_augment(x)                                tasks.py:206-212   基类仅告警并退回单尺度
                                                   tasks.py:541-563   DetectionModel 实现 3 尺度 × flip TTA
                                                                      （end2end 或非纯 Detect 头时自动退回）

loss(batch, preds=None)                            tasks.py:411-423
├── self.criterion = self.init_criterion()  （惰性，仅一次）  416-417
├── preds = self.forward(batch["img"])                       420
└── return self.criterion(preds, batch)                      421
```
注意 **`loss` 走 `self.forward(...)` 而不是 `self.predict(...)`**（420），因此 head 在 `training=True` 时返回 dict（`head.py:188-189`），loss 直接吃 dict。

`init_criterion()` 是**每个任务的算法接入点**：

| 模型 | 行号 | 返回 |
|---|---|---|
| `BaseModel`（基类） | `tasks.py:425-427` | `raise NotImplementedError("compute_loss() needs to be implemented by task heads")` |
| `DetectionModel` | `605-607` | `E2ELoss(self)`（有 one2one 头）或 `v8DetectionLoss(self)` |
| `OBBModel` | `637-639` | `E2ELoss(self, v8OBBLoss)` / `v8OBBLoss(self)` |
| `SegmentationModel` | `669-675` | `E2ELoss(self, v8SegmentationLoss)` / `v8SegmentationLoss(self)` |
| `SemanticSegmentationModel` | `737-739` | `SemanticSegmentationLoss(self)` |
| `PoseModel` | `786-789` | `E2ELoss(self, PoseLoss26)` / `PoseLoss26(self)`（按 head 是 `Pose26` 与否选） |
| `DepthModel` | `807-810` | `DepthLoss26(self)` |
| `ClassificationModel` | `899-901` | `v8ClassificationLoss()` |

### 2.5 超参与尺度参数化

**YAML `args` → 构造函数**：见 2.1。

**`scales` / `width_multiple` / `depth_multiple`**：
- YAML 顶层 `scales: {n: [depth, width, max_channels], ...}`（实例 `ultralytics/cfg/models/26/yolo26.yaml:11-17`），`parse_model:2028-2032` 按字符取三元组。
- `yaml_model_load(path)`（`tasks.py:2221-2241`）：
  - `-p6` 旧名自动改名（2231-2234，仅告警）
  - `unified_path = re.sub(r"(\d+)([nslmx])(.+)?$", r"\1\3", str(path))`（2236）→ `yolov8x.yaml` 退化成 `yolov8.yaml`
  - `yaml_file = check_yaml(path, hard=False) or check_yaml(unified_path)`（2237）——**第一条软失败（不抛）自动退到统一名，第二条才硬失败**
  - `d["scale"] = guess_model_scale(path)`（2239）、`d["yaml_file"] = str(path)`（2240）
- `guess_model_scale(path)`（`tasks.py:2244-2256`）：正则 `r"yolo(e-)?[v]?\d+([nslmx])"` 抓 n/s/m/l/x，`AttributeError` → 返回 `""`
- `make_divisible(x, divisor)`（`ultralytics/utils/ops.py:168-180`）：`math.ceil(x / divisor) * divisor`；`parse_model` 用 `make_divisible(min(c2, max_channels) * width, 8)`（2122）与 `make_divisible(min(args[2], max_channels) * width, 8)`（2178）
- 训练超参（`lr0/box/cls/momentum/...`）**不走模型 YAML**，走 `cfg/default.yaml` → `get_cfg` → `Trainer.args`（`trainer.py:138`）→ `model.args`（`detect/train.py:147`）→ loss（`loss.py:346`）。两条配置链完全独立。

---

## 三、任务与求解器抽象

### 3.1 没有 `TASK_MAP` 字典（重要更正）

```bash
$ grep -rn "TASK_MAP" --include=*.py .
（0 命中）
```
实际是一个 **property**：
- 基类 `engine/model.py:1194`：`raise NotImplementedError("Please provide task map for your model!")`
- `models/yolo/model.py:98-147` 在 `YOLO` 上实现，返回 `{task: {"model":..., "trainer":..., "validator":..., "predictor":...}}`，7 个任务：`classify / detect / segment / pose / obb / depth / semantic`
- 其它家族各自实现：`models/rtdetr/model.py:50`、`models/nas/model.py:88`、`models/fastsam/model.py:77`、`models/sam/model.py:154`（后者只有 predictor）
- 消费点 `Model._smart_load(key)`（`engine/model.py:1165-1188`）：
  ```python
  try:
      return self.task_map[self.task][key]
  except Exception as e:
      name = self.__class__.__name__
      mode = inspect.stack()[1][3]      # 用调用栈帧名反推 mode，仅用于拼错误信息
      raise NotImplementedError(f"'{name}' model does not support '{mode}' mode for '{self.task}' task.") from e
  ```
  （`except Exception` 包一切，把 `KeyError`/`TypeError` 统一转成 `NotImplementedError`——**这是少数几处做了错误翻译的地方**。）
- 9 个调用点：`engine/model.py:216`（`_new` 建网络）、`540`（predict）、`636`/`671`（val）、`784`（export 直接 `Exporter`）、`850`/`870`（train）、`945`（Tuner）、`1005`；`models/yolo/model.py:452`（YOLOWorld.val 覆写）
- 注意 `engine/model.py:850`：`use_python_trainer = trainer is not None or self.callbacks != callbacks.get_default_callbacks()` —— **只要用户加了自定义回调，就走 Python 训练路径而非子进程**。

### 3.2 任务字符串从哪来 / `guess_model_task`

`Model.__init__`（`engine/model.py:106-134`）：
```python
if str(model).endswith((".yaml", ".yml")):  self._new(model, task=task, verbose=verbose)   # 130-131
else:                                       self._load(model, task=task)                  # 133
```

`guess_model_task(model)`（`tasks.py:2259-2344`）是**四级字符串/类型猜测**：
1. **dict → `cfg2task`**（2269-2285）：取 `cfg["head"][-1][-2].lower()`，依次 `in` 判断 `classify/classifier/cls/fc` → `"detect" in m` → `"semanticsegment" in m` → `"segment" in m` → `"pose" in m` → `"obb" in m` → `"depth" in m`
2. **`torch.nn.Module`**（2292-2313）：先试 `model.args["task"]`（2293-2295，用 `eval("model.args")` 之类的属性路径字符串！），再试 `model.yaml`（2296-2298），最后 `for m in model.modules(): isinstance(m, (Segment, Classify, Pose, OBB, Depth, Detect, ...))` 类型判定（2299-2313）
3. **`str`/`Path`**（2315-2336）：先读导出模型内嵌 metadata 的 `task`（2316-2319），再按文件名 `-sem/-seg/-cls/-pose/-obb/-depth` 或路径 parts 判定
4. **兜底**（2338-2344）：`LOGGER.warning("Unable to automatically guess model task, assuming 'task=detect'...")` + `return "detect"` —— **不报错，静默假设**

### 3.3 `YOLO("yolo11n.yaml")` vs `YOLO("yolo11n.pt")`

| | `.yaml` → `_new`（`engine/model.py:197-226`） | `.pt` → `_load`（`228-262`） |
|---|---|---|
| 后端 | `yaml_model_load(cfg)` → `guess_model_task` → `_smart_load("model")` → `(cfg_dict, verbose=...)` | `load_checkpoint(weights)`（`tasks.py:1958-2004`）反序列化整个 `nn.Module` |
| 架构来源 | **`parse_model` 从 YAML 现场编译**（`tasks.py:444`） | **pickle 进来的**，不解析 YAML、不走 `parse_model` |
| task | `task or guess_model_task(cfg_dict)`（215） | `self.model.task`（251）；非 `.pt` 格式才 `guess_model_task`（257） |
| 权重 | 随机初始化 + `initialize_weights` | 反序列化即得 |
| self.cfg | = cfg 路径（217） | `None` |
| self.ckpt | `{}` | 完整 checkpoint dict |
| overrides | `{**DEFAULT_CFG_DICT, **self.overrides}`（222） | `self._reset_ckpt_args(self.model.args)`（252） |
| 文件名归一 | `yaml_model_load` 的 `unified_path`/`-p6` | `check_model_file_from_stem`（242，`checks.py:744-756`，只对 `GITHUB_ASSETS_STEMS` 补 `.pt`） |

**这条差异是整个设计里最关键的"隐藏分支"**：`.pt` 路径完全绕过 `parse_model`，架构由 pickle 决定。这就是为什么需要 `temporary_modules()` 旧路径兼容（`tasks.py:1607-1623`）和 `_SafeLoad` allow-list（1638-1812）——**版本兼容靠"运行时别名"，而不是版本号**。

另外 `YOLO.__init__`（`models/yolo/model.py:65-95`）还会**原地替换 `self.__class__`**：
```python
if "-world" in path.stem and path.suffix in {".pt",".yaml",".yml"}: ... YOLOWorld   # 76-79
elif "yoloe" in path.stem and ...:                                  ... YOLOE      # 80-83
else:
    super().__init__(...)
    head = self.model.model[-1]._get_name() ...                                     # 87
    if "RTDETR" in head:      → RTDETR                                              # 90-93
    elif isinstance(self.model, WorldModel): → YOLOWorld                            # 94-96
```
**这是第三层字符串分派**（第一层 `guess_model_task`、第二层 `task_map`、第三层这里）。

### 3.4 每任务的 Trainer/Validator/Predictor 三件套

- 目录：`ultralytics/models/yolo/{classify,detect,depth,obb,pose,segment,semantic}/`，每包 `__init__.py` 导出三件套（例：`detect/__init__.py:3-5` 导出 `DetectionPredictor/DetectionTrainer/DetectionValidator`）
- 基类：`engine/trainer.py:BaseTrainer`、`engine/validator.py:BaseValidator`、`engine/predictor.py:BasePredictor`、`engine/exporter.py:Exporter`、`engine/tuner.py:Tuner`
- 回调通过 **`_callbacks=` 构造参数**一路透传：`engine/model.py:540/636/671/784/870/945/1005`，`models/yolo/model.py:452/539`
- `models/yolo/__init__.py:3-16` 显式 import 全部子包并写 `__all__`

### 3.5 配置 / 设置系统

**A. `ultralytics/cfg/__init__.py`（训练配置）**
- `MODES = ("train","val","predict","export","track","benchmark")`（59）
- `TASKS = ("detect","segment","semantic","depth","classify","pose","obb")`（60）—— **单一事实来源，顺序被 AGENTS.md 强制要求全仓库一致**
- `TASK2DATA`（61-69）、`TASK2CALIBRATIONDATA`（70-78）、`TASK2MODEL`（79-87）、`TASK2METRIC`（88-96）
- 类型白名单：`CFG_FLOAT_KEYS`（202）、`CFG_FRACTION_KEYS`（222）、`CFG_INT_KEYS`（252）、`CFG_INT_MIN`（267）、`CFG_BOOL_KEYS`（276）、`CFG_STR_KEYS`（312）—— **全部手写**
- `get_cfg(cfg, overrides)`（349-388）：`_handle_deprecation` → `check_dict_alignment` → 类型转换 → `check_cfg`（391+）→ `IterableSimpleNamespace`
- **`check_dict_alignment`（622-659）是全仓库错误处理最好的地方**：
  ```python
  from difflib import get_close_matches                     # 645
  matches = get_close_matches(x, base_keys)                 # 651
  LOGGER.info(CLI_HELP_MSG); raise SyntaxError(string)      # 657-658
  ```
  给拼错的键**猜最近的合法键**并提示 `Similar arguments are i.e. [...]`。
- `entrypoint`（989+）：CLI 入口；`special` 子命令字典（1016-1025）；`full_args_dict = {**DEFAULT_CFG_DICT, **{k:None for k in TASKS}, **{k:None for k in MODES}, **special}`（1029）；按 `Path(model).stem` 里的 `rtdetr/fastsam/sam_` 选模型类（1111-1126）——**第四层字符串分派**；`task not in TASKS` 时 `raise ValueError`（1091-1098）（track 特判降级为 detect+mode=track）。

**B. `ultralytics/utils/__init__.py`（横切工具 + 用户设置）**
- `DEFAULT_CFG_PATH = ROOT / "cfg/default.yaml"`（69）→ `DEFAULT_CFG_DICT` / `DEFAULT_CFG_KEYS` / `DEFAULT_CFG`（710-712）
- `SETTINGS = SettingsManager()`（1527）；`SettingsManager`（1367+）带**独立 schema 版本** `version="0.0.8"`（1393）和 `_validate_settings`（1440-1446）：keys / types / version 三者任一不符 → `LOGGER.warning` + 重置全部用户设置
- 每个集成的开关就在 settings 里：`clearml/comet/dvc/mlflow/raytune/tensorboard/wandb`（1414-1420），全部 `bool`
- `SAFE_LOAD`（73）、`RANK/WORLD_SIZE/LOCAL_RANK`（55-57）、`LOGGER`、`colorstr`、`emojis`、`YAML`、`temporary_modules`、`ThreadingLocked` 等横切工具都在这里
- **两套配置系统互不相干**：`DEFAULT_CFG`（训练超参、YAML、键名严格校验）vs `SETTINGS`（用户全局偏好、JSON、带 schema 版本）

---

## 四、回调（hook）扩展机制 —— 最接近"插件系统"的地方

### 4.1 数据结构

`ultralytics/utils/callbacks/base.py`：
- 25 个空函数定义（10-118），每个只有 docstring
- `default_callbacks` 字典（121-151）：`事件名 -> [函数]`
- `get_default_callbacks()`（154-167）：`return defaultdict(list, deepcopy(default_callbacks))` —— **每次调用返回深拷贝**，所以 `model.add_callback` 不会污染全局默认
- `ultralytics/utils/callbacks/__init__.py:3-5` 只导出 `add_integration_callbacks, default_callbacks, get_default_callbacks`

**25 个事件名（按引擎分组）**

| 引擎 | 事件 |
|---|---|
| Trainer（14） | `on_pretrain_routine_start`, `on_pretrain_routine_end`, `on_train_start`, `on_train_epoch_start`, `on_train_batch_start`, `optimizer_step`, `on_before_zero_grad`, `on_train_batch_end`, `on_train_epoch_end`, `on_fit_epoch_end`, `on_model_save`, `on_train_end`, `on_params_update`, `teardown` |
| Validator（4） | `on_val_start`, `on_val_batch_start`, `on_val_batch_end`, `on_val_end` |
| Predictor（5） | `on_predict_start`, `on_predict_batch_start`, `on_predict_postprocess_end`, `on_predict_batch_end`, `on_predict_end` |
| Exporter（2） | `on_export_start`, `on_export_end` |

- 其中 3 个是"**保留但核心从不触发**"：`optimizer_step`（`base.py:31` 注释 "Reserved for custom integrations; not called by default"）、`on_before_zero_grad`（35）、`on_params_update`（61）。
- 另有 1 个**不在 `default_callbacks` 里却被调用**的事件：`self.run_callbacks("on_batch_end")`（`engine/trainer.py:613`）。因为 `run_callbacks` 用 `self.callbacks.get(event, [])`，未注册的事件是**静默 no-op**——这是隐式扩展点，也是隐式 bug 源（事件名拼错不报错）。

### 4.2 调用路径（**四处重复实现，全部无隔离**）

| 引擎 | 定义位置 | 实现 |
|---|---|---|
| Trainer | `engine/trainer.py:223-226` | `for callback in self.callbacks.get(event, []): callback(self)` |
| Validator | `engine/validator.py:365-368` | 同上 |
| Predictor | `engine/predictor.py:551-553` | 同上 |
| Exporter | `engine/exporter.py:1819-1822` | 同上 |

**四处都没有 `try/except`，没有任何隔离。**

初始化（每处都是"用户传入优先，否则深拷贝默认"）：
`trainer.py:174`（`copy(_callbacks) if _callbacks else callbacks.get_default_callbacks()`，175-176 再逐键 `.copy()`）、`predictor.py:156`、`validator.py:144`、`exporter.py:571`、`tuner.py:132`、`model.py:109`。

Trainer 触发点（行号）：`188`（注入集成）→ `189` `on_pretrain_routine_start` → `455` `on_pretrain_routine_end` → `469` `on_train_start` → `486` `on_train_epoch_start` → `507` `on_train_batch_start` → `613` `on_batch_end` → `617` `on_train_batch_end` → `632` `on_train_epoch_end` → `655` `on_model_save` → `668` `on_fit_epoch_end` → `688` `on_train_end`；`258` `teardown`；`999` 再次 `on_fit_epoch_end`。
Predictor：`341/344/365/393/420`。Validator：`233/244/270/279`。Exporter：`968/1004`。

### 4.3 第三方集成如何接入（**它们并没有"不改核心代码"**）

`add_integration_callbacks(instance)`（`base.py:170-206`）—— 这是全部机制：

```python
from ultralytics.utils.events import callbacks as events_cb        # 185
callbacks_list = [events_cb]                                        # 187
if "Trainer" in instance.__class__.__name__:                        # 190  ← 按类名字符串判断！
    from .clearml import callbacks as clear_cb                      # 191
    from .comet import callbacks as comet_cb                        # 192
    from .dvc import callbacks as dvc_cb                            # 193
    from .mlflow import callbacks as mlflow_cb                      # 194
    from .platform import callbacks as platform_cb                  # 195
    from .raytune import callbacks as tune_cb                       # 196
    from .tensorboard import callbacks as tb_cb                     # 197
    from .wb import callbacks as wb_cb                              # 198
    callbacks_list.extend([platform_cb, clear_cb, comet_cb, dvc_cb, mlflow_cb, tune_cb, tb_cb, wb_cb])  # 200
for callbacks in callbacks_list:                                    # 203
    for k, v in callbacks.items():                                  # 204
        if v not in instance.callbacks[k]:                          # 205  ← 身份比较，不是语义去重
            instance.callbacks[k].append(v)                         # 206
```

**集成的约定（三件套）**：
1. 模块级 `try: assert SETTINGS["<name>"] is True; import <pkg>; ... except (ImportError, AssertionError): <pkg> = None`
2. 定义若干 `on_xxx(instance)` 顶层函数
3. 模块底部 `callbacks = ({事件名: 函数, ...} if <pkg> else {})`

实证：
- `ultralytics/utils/callbacks/wb.py:6-16`
  ```python
  try:
      assert not TESTS_RUNNING
      assert SETTINGS["wandb"] is True       # 8  ← import 期判定
      import wandb as wb
      assert hasattr(wb, "__version__")
      _processed_plots = {}
  except (ImportError, AssertionError):
      wb = None
  ```
  尾部：`callbacks = ({...4 个事件...} if wb else {})`
- `ultralytics/utils/callbacks/raytune.py:5-12` 同款（`assert SETTINGS["raytune"] is True; from ray import tune; assert hasattr(tune,"get_context")`），只挂 1 个事件 `on_fit_epoch_end`
- `ultralytics/utils/callbacks/platform.py` 尾部 `callbacks = {on_pretrain_routine_start, on_pretrain_routine_end, on_fit_epoch_end, on_model_save, on_train_end}`
- `ultralytics/utils/callbacks/mlflow.py:60` 有一句自白式注释：「`add_integration_callbacks` imports this module on the first training, which may run with mlflow off.」
- `ultralytics/utils/events.py`（匿名遥测）是第 9 个，**对 Predictor/Validator 也注入**（`base.py:185-187` 在 `if` 之外）

**结论：启用条件 = 「settings 开关 + 依赖装没装」，在进程内首次训练时一次性判定，之后不可变更。没有 enable/disable API，没有重载，没有 manifest。**

### 4.4 用户侧扩展 API

- `Model.add_callback(event, func)`（`engine/model.py:1052-1072`）：`self.callbacks[event].append(func)`
- `Model.clear_callback(event)`（1074-1099）
- `Model.reset_callbacks()`（1101-1120）：`for event in callbacks.default_callbacks: self.callbacks[event] = [callbacks.default_callbacks[event][0]]` —— **只保留每个事件的第 0 个默认函数**，用户加的全部丢弃
- `Trainer.add_callback`（`trainer.py:216-217`，追加）/ `set_callback`（220-221，**覆盖** `[callback]`）
- 透传：`Model.train` 把 `_callbacks=self.callbacks` 交给 Trainer（`engine/model.py:870`；子进程路径 855）
- 范例：`register_tracker(model, persist)`（`ultralytics/trackers/track.py:133-155`）用 `getattr(cb, "func", None) is fn` 做**幂等注册**，再 `model.add_callback(event, partial(fn, persist=persist))`

### 4.5 与你的 `插件系统.py` 的能力对照

| 能力 | Ultralytics callback | 你的 `软件/插件系统.py` |
|---|---|---|
| 发现 | ❌ 硬编码 import 清单（`base.py:191-200`） | ✅ 主程序显式插件列表 |
| 契约/基类 | ❌ 无，仅约定 `fn(instance)` | ✅ `class 控制插件` + 类属性 `名称/版本/说明/作者` |
| 清单/manifest | ❌ 无 | ✅ `打印插件清单()` 输出名字/版本/作者/说明/状态 |
| **错误隔离** | ❌ **裸循环，无 try/except** | ✅ `安全注册表._单独派发()` 逐个 try/except |
| 故障降级 | ❌ 无 | ✅ 出错计数，第二次出错自动 `_已停用` |
| 可读报错 | ❌ 原始 traceback | ✅ 中文报错 + 只提取"插件自己文件的帧" |
| **版本协商** | ❌ 无（`wb.py` 只 `assert hasattr(wb,"__version__")`） | ✅ `版本自检()`：mujoco 版本 + `ViewerConfig` 字段/GFX 模式数/消息类数指纹 vs `已知可用版本` |
| 优先级 | ❌ 仅 list 顺序 | ✅ `messages.Priority`（CRITICAL/USER/LIBRARY/INTERNAL） |
| 运行期启停 | ❌ 不可 | ✅ `_已停用` 集合 |
| 参数面板 | ❌ 无（超参走 `DEFAULT_CFG` 白名单） | ✅ `可调参数()` / `设置参数()` 驱动滑杆 |
| 状态回显 | ❌ 无 | ✅ `插件状态()` |
| API 隔离层 | ❌ 集成直接 import 内部符号（如 `from ultralytics.utils import SETTINGS, TESTS_RUNNING`） | ✅ 「唯一直接碰官方实验性 API 的文件」 |

---

## 五、错误隔离、版本管理与健壮性

### 5.1 回调路径：**零隔离**

- 4 处 `run_callbacks` 全是裸循环（`trainer.py:225`、`validator.py:367`、`predictor.py:553`、`exporter.py:1821`）。任何一个回调抛异常 → 直接冒泡进训练主循环（`507`/`613`/`617`/`632` 全在 `for epoch` 内），**训练崩溃，没有 per-callback try/except、没有禁用计数、没有降级**。
- `base.py:205` 的 `if v not in instance.callbacks[k]` 只在"加"的时候比较，运行期无锁。
- **脆弱耦合实证**：`engine/trainer.py:404-406`
  ```python
  callbacks_backup = callbacks.default_callbacks.copy()   # 404
  self.amp = torch.tensor(check_amp(self.model), device=self.device)
  callbacks.default_callbacks = callbacks_backup          # 406
  ```
  因为 `check_amp` 会重置 `callbacks.default_callbacks`，所以这里**打补丁式地备份/还原一个模块级全局字典**。

### 5.2 `parse_model` 的错误处理

| 情形 | 行为 |
|---|---|
| 未知模块名 | **裸 `KeyError: 'MyBlock'`**（在 2109 处 `globals()[m]` 抛出），**没有任何 try/except、没有候选名建议** |
| 官方对此的态度 | 文档把它当 FAQ 列出：`docs/en/guides/model-yaml-config.md:397` → `\| KeyError: 'ModuleName' \| Module not imported \| Add to tasks.py imports \|` |
| 未命中任何分支的已知模块 | 静默走 `else: c2 = ch[f]`（2201-2202），假设"输出通道 = 输入通道" |
| 主动校验 | 仅 `C2fAttn` 的整除检查 `raise ValueError`（2126-2130）；受限加载下的 `TypeError`（2111-2113） |
| YAML 顶层键 | **完全不校验**（模型 YAML 没有 schema；只有 `cfg/default.yaml` 那侧有 `check_dict_alignment`） |

**YAML/资产的加载错误处理**（这部分做得较好）：
- `check_yaml(file, suffix=(".yaml",".yml"), hard=True)`（`checks.py:816-827`）= `check_file(file, suffix, hard=hard)`
- `check_file(file, suffix="", download=True, download_dir=".", hard=True)`（`checks.py:759-814`）：平台 URI 归一化（772）→ 后缀校验（773）→ 本地存在即返回（776-781）→ `ul://` 走签名 URL + 路径穿越防护（`ValueError(f"Unsafe Ultralytics Platform URI path: {file}")`，789）→ `REMOTE_FILE_PREFIXES` 下载（797+）；`check_is_path_safe`（830-842）
- `yaml_model_load`（2221-2241）用 `check_yaml(path, hard=False) or check_yaml(unified_path)`（2237）实现"软失败再退化"的两级查找

### 5.3 版本管理

- `ultralytics/__init__.py:3` `__version__ = "8.4.160"`；由 `pyproject.toml` 动态读取（`[tool.setuptools.dynamic] version = { attr = "ultralytics.__version__" }`）
- `check_version(current="0.0.0", required="0.0.0", name="version", hard=False, verbose=False, msg="")`（`checks.py:291-...`）：支持 pip 风格范围表达式（`">20.04,<22.04"`）、支持 `current` 传包名（走 `importlib.metadata.version`，329-343）、`hard=True` 抛 `ModuleNotFoundError`（340-341）。**这是给第三方依赖用的，不是给插件 API 用的。**
- 模块导入期自动检查（`checks.py:1186-1187`）：
  ```python
  check_python("3.8", hard=False, verbose=True)
  check_torchvision()
  ```
  `check_torchvision`（665-698）内置 torch↔torchvision 兼容表，不兼容只 `LOGGER.warning`
- 更新提示（`checks.py:405-421`）：`if check_version(__version__, f"<{latest}")` → 打印 PyPI 提示；`except Exception: pass`（420-421）全吞
- **不存在的**：checkpoint 格式版本号校验、YAML schema 版本、插件/回调 API 版本。`load_checkpoint`（`tasks.py:1958-2004`）只做两件事：`isinstance(candidate, nn.Module)` 检查（1976-1982，`raise TypeError` 才是清晰报错）+ 属性补丁（`if not hasattr(model,"stride"): model.stride = tensor([32.0])`，1991-1992；`torch.nn.Upsample.recompute_scale_factor`，2000-2001）
- **兼容性靠"运行时别名"而非版本号**：
  - `temporary_modules(modules={...}, attributes={...})`（`tasks.py:1607-1623`）：把 `ultralytics.yolo.utils → ultralytics.utils`、`ultralytics.yolo.v8 → ultralytics.models.yolo`、`ultralytics.yolo.data → ultralytics.data` 动态注入 `sys.modules`；属性级别名如 `ultralytics.nn.modules.block.Silence → torch.nn.Identity`（1849）
  - `_SafeLoad._build()`（1760-1812）：`"新类" ↔ "旧 pickled 名"` 双向别名表
- 唯一近似"版本自检"的机制：`_SafeLoad.SUPPORTED = hasattr(torch.serialization, "get_unsafe_globals_in_checkpoint")`（1650，注释写明需要 torch 2.6+，低版本自动降级为标准加载）。**对比你的 `版本自检()` 指纹法，Ultralytics 完全没有等价物。**

### 5.4 资产/权重的管理

- `ultralytics/utils/downloads.py`：
  - `GITHUB_ASSETS_REPO = "ultralytics/assets"`（19）
  - `GITHUB_ASSETS_NAMES`：frozenset，枚举 yolov8/yolo11/yolo12/… 各 scale × 各任务后缀的全部官方权重名（20-52）
  - `GITHUB_ASSETS_STEMS`（53）
  - `attempt_download_asset(file, repo="ultralytics/assets", release="v8.4.0", **kwargs)`（557-609）：本地 → `SETTINGS["weights_dir"]`（585-586）→ 直链 URL（591-597）→ 官方 release 白名单（599-600）→ GitHub API 查 assets（602-607），一律 `safe_download(..., min_bytes=1e5)`
  - `download()`（612+）
- `checks.check_model_file_from_stem`（744-756）：`yolo26n` → `yolo26n.pt`，且**仅当 stem 在 `GITHUB_ASSETS_STEMS` 里**
- `SETTINGS`（`utils/__init__.py:1527`，默认值 1405-1423）决定 `weights_dir / datasets_dir / runs_dir`
- **代码 / 结构 / 权重三分**：
  - 代码：`ultralytics/nn/modules/*.py`
  - 结构：`ultralytics/cfg/models/**/*.yaml`（随 wheel 打包：`pyproject.toml` `package-data = { "ultralytics" = ["**/*.yaml", ...] }`）
  - 权重：GitHub release + 本地 `SETTINGS["weights_dir"]`
  - 因此 **YAML 可以在不改代码的情况下换结构，但只能换"已注册模块"的排列组合**；这也解释了为什么 Ultralytics 的模型版本（v3/v5/v6/v8/v9/v10/v11/v12/26）表现为一堆 YAML 目录而不是插件。

---

## 六、扩展配方

### 6.1 加一个新模块（例如注意力块 `MyAttn`）：**改 3 处（+1 推荐）**

| # | 文件 | 改什么 | 必需 |
|---|---|---|---|
| 1 | `ultralytics/nn/modules/block.py`（或 conv/head/transformer） | 加类。`__init__(self, c1, c2, ...)`、`forward(self, x)` | ✅ |
| 2 | `ultralytics/nn/modules/__init__.py` | `from .block import MyAttn`（20-62 区）+ 加入 `__all__`（111-194） | ✅ |
| 3 | **`ultralytics/nn/tasks.py`** | 在 `from ultralytics.nn.modules import (...)`（18-105）加 `MyAttn` | ✅ **这一步才是注册** |
| 4 | `ultralytics/nn/tasks.py` | `base_modules` frozenset（2046-2083）加 `MyAttn` → 自动获得 `(c1, c2)` 注入 + `width/max_channels` 缩放；若接受 repeats，同时加进 `repeat_modules`（2084-2102） | ⭐ 强烈推荐 |
| 5 | 新建 `my.yaml` | `- [-1, 1, MyAttn, [256]]`，然后 `YOLO("my.yaml")` | ✅ |

- 官方同款步骤：`docs/en/guides/model-yaml-config.md:243-289`
- 官方收录的失败模式：`docs/en/guides/model-yaml-config.md:397` `KeyError: 'ModuleName' → Module not imported → Add to tasks.py imports`
- **不做第 3 步的后果**：`KeyError`，且错误信息不含"你可能忘了 import"。
- **不做第 4 步的后果**：走 `else: c2 = ch[f]`（2201-2202），`c2` 被当成输入通道数，通常在下游 `Concat` 或 loss 处才炸成 shape mismatch。
- **要特别注意**：如果新模块是**双输入**（`forward(x, y)`），还必须在 `WorldModel.predict`（`tasks.py:1183-1192`）或 `YOLOEModel.predict` 的 `isinstance` 链里再加一个分支——**这是第 6 处改动，且它与模块定义物理分离**。
- 若模块带 BN 且希望推理融合，还需提供 `forward_fuse`（参考 `conv.py:80`），因为 `BaseModel.fuse()` 会 `m.forward = m.forward_fuse`（`tasks.py:262`）。
- **如果想完全不改 Python，只改 YAML**：只能用已在 `tasks.py` globals 里的那约 100 个名字。

### 6.2 加一个新任务（例如 `keypoint3d`）：**约 8 处**

| # | 文件 | 改什么 |
|---|---|---|
| 1 | `ultralytics/nn/modules/head.py` | 新 head 类，满足 §2.3 契约（`nc/nl/reg_max/no/stride` + `bias_init()` + train/infer 双态 `forward`） |
| 2 | `ultralytics/nn/tasks.py` | 新 `XxxModel`，覆写 `init_criterion()`（§2.4） |
| 3 | `ultralytics/nn/tasks.py:2161-2175` | 若新 head 需要 `[ch[x] for x in f]`，加入这个 head frozenset（否则走 `else: c2 = ch[f]`） |
| 4 | `ultralytics/nn/tasks.py:2269-2285 / 2299-2313` | `guess_model_task` 的字符串匹配 / `isinstance` 链加分支 |
| 5 | `ultralytics/models/yolo/keypoint3d/{__init__,train,val,predict}.py` | 三件套（照抄 `models/yolo/detect/`） |
| 6 | `ultralytics/models/yolo/model.py:98-147` | `task_map` property 加 `"keypoint3d": {"model":…, "trainer":…, "validator":…, "predictor":…}` |
| 7 | `ultralytics/models/yolo/__init__.py:3-16` | 加子包 import + `__all__` |
| 8 | `ultralytics/cfg/__init__.py` | **五处**：`TASKS`(60)、`TASK2DATA`(61)、`TASK2CALIBRATIONDATA`(70)、`TASK2MODEL`(79)、`TASK2METRIC`(88) |
| 9 | `ultralytics/cfg/models/<gen>/<task>.yaml` | 新增模型 YAML |

- 官方清单：`AGENTS.md:96`
- 注意 `TASKS` 的顺序是**代码/文档/平台三处强一致**的硬约定（`AGENTS.md` 的 Conventions 段明确要求）
- **没有任何"注册 API"能避免改核心文件。** 若坚持不改核心，唯一的办法是子类化 `YOLO` 并覆写 `task_map` property（`models/yolo/model.py:98`），再用 `model.train(trainer=MyTrainer)` 注入——但 `TASKS`、`guess_model_task`、`build_yolo_dataset`、`Results` 类型仍不认识这个新任务字符串。

### 6.3 加一个新集成（回调）：两条路

**路 A —— 不改核心（推荐给用户）**
```python
model = YOLO("yolo26n.pt")
model.add_callback("on_train_start", my_fn)   # engine/model.py:1052
model.train(data="coco8.yaml")
```
或 `model.train(..., trainer=MyTrainer)`（`engine/model.py:870`）。零核心改动，但**没有清单、没有隔离、没有开关、没有版本协商**。

**路 B —— 做成与 wb/comet 同级的"一等公民"：改 1 个核心文件 + 2 个白名单**

| # | 文件 | 改什么 |
|---|---|---|
| 1 | 新建 `ultralytics/utils/callbacks/myint.py` | 顶部 `try: assert SETTINGS["myint"] is True; import myint; ... except (ImportError, AssertionError): myint = None`；底部 `callbacks = ({...} if myint else {})` |
| 2 | **`ultralytics/utils/callbacks/base.py:191-200`** | 加 `from .myint import callbacks as myint_cb` + 加进 `callbacks_list.extend([...])` ← **必须改核心** |
| 3 | `ultralytics/utils/__init__.py:1405-1423` | `SettingsManager.defaults` 加 `"myint": False`；**同时把 `version` 从 `"0.0.8"` 升一位（1393）**，否则 `_validate_settings`（1440-1446）会因 keys/version 不匹配而**重置用户全部设置** |
| 4 | `ultralytics/cfg/__init__.py` | 若要在 CLI 有开关，改 `handle_yolo_settings` |

**结论：第三方集成不能通过 entry_points / 目录扫描接入；`add_integration_callbacks` 是一张硬编码白名单。**

---

## 七、这套设计的优点与代价（批判性）

### 值得借的优点

1. **单点解析器**：只有 `parse_model` 一个地方把"声明"变成"对象"，YAML 是唯一的网络 DSL。收益是极强的可复现性——一个 YAML + 一个 scale 字母 = 架构完全确定。你的 `安全注册表.处理消息` 也是单点派发，思路一致。
2. **字符串名 = 稳定 ID**：YAML 存类名、checkpoint 里 `yaml` 也存类名，跨版本靠 `temporary_modules()`（`tasks.py:1607-1623`）和 `_SafeLoad` 别名表（1760-1812）兜住，而不是靠版本号。
3. **契约分层清晰（虽隐式）**：L1 模块只要 `forward(x)` 就能用，接入成本近乎零。
4. **回调事件名是事实上的稳定公开 API**，`Model.add_callback` 给了用户零核心改动的扩展口。
5. **`check_dict_alignment` 的拼写建议**（`cfg/__init__.py:645-658`）是全仓库错误信息质量最高的地方——「Similar arguments are i.e. ['epochs=100']」这种提示**值得你在插件加载器里照抄**。
6. **`AutoBackend._BACKEND_MAP`**（`autobackend.py:153-180` + 未命中时列出支持格式的 `TypeError`，234-239）是"注册表 + 友好报错"的正确写法样板。

### 代价与脆弱点

1. **`globals()[m]` 是隐式注册表**：命名空间即注册表，import 顺序即注册顺序。代价是：
   - 无法查询"这个模块被哪些 YAML 用了"；
   - 同名类**静默覆盖**；
   - 循环导入风险（`modules` ↔ `tasks`）；
   - `globals()` 里还有 `nn`/`torch`/`re`/`Path`/`deepcopy` 等非模块对象，YAML 写到它们会通过名字解析直到实例化才炸。
2. **错误发生在很远的地方**：`KeyError` 无提示（只能写进 FAQ，`docs:397`）；`else: c2 = ch[f]`（2201-2202）让 shape 错误推迟到 forward。
3. **分支爆炸**：`parse_model` 里 20 多个 `elif m is X`（2147-2200）意味着**每加一个特殊模块就要改解析器**。你的 MuJoCo 外壳用 `_discover_handlers` 按类型标注自动匹配，恰好绕开了这个问题。
4. **回调零隔离**：wandb/comet 网络抖动抛异常 = 训练崩。你的 `安全注册表` 的"逐个 try/except + 出错两次停用 + 只打印插件自己文件的帧"是正解。
5. **回调无优先级、无顺序契约**：只靠 `extend` 的位置，加一个集成可能改变另一个集成的执行时序。
6. **集成开关在 import 期冻结**：`SETTINGS["wandb"]` 在模块 import 时判定（`wb.py:8`），之后改 settings 必须重启进程；且 `settings` schema 与 defaults 强耦合（加一个 key 就得升 `version`，否则用户设置被重置）。
7. **隐式字符串分派泛滥**：同一条信息（"这是什么任务/模型"）在全仓库至少有 **6 套独立判据**：
   - `yaml_model_load` 的正则（2231-2236）
   - `guess_model_scale` 的正则（2254）
   - `guess_model_task` 的 `cfg2task` 字符串 `in`（2269-2285）
   - `guess_model_task` 的 `isinstance` 链（2299-2313）
   - `YOLO.__init__` 的 `"-world"/"yoloe"` 文件名判断（`models/yolo/model.py:76,80`）
   - `entrypoint` 的 `"rtdetr"/"fastsam"/"sam_"` 判断（`cfg/__init__.py:1111-1126`）+ `add_integration_callbacks` 的 `"Trainer" in instance.__class__.__name__`（`base.py:190`）
   
   **没有单一权威解析器**。
8. **无版本协商**：没有插件 API 版本、没有 YAML schema 版本。最近似的只有 settings 的 `"0.0.8"`（`utils/__init__.py:1393`）和 `_SafeLoad.SUPPORTED` 的 torch 版本探测（`tasks.py:1650`）。
9. **安全性与可扩展性互斥**：`_SafeLoad` 的 allow-list（2111-2113 拒绝未知层）默认关闭（`ULTRALYTICS_SAFE_LOAD`）。要么能 `globals()` 任意名字（可扩展但不安全），要么只跑白名单（安全但不可扩展）。**这是最值得你警惕的设计取舍。**
10. **测试覆盖缺口**：`tests/test_engine.py:253` 只测了"state_dict checkpoint 给出清晰 TypeError"，对**未知模块名**和**未知事件名**这两类最常见的用户错误没有测试。

### 给消费者的三条可操作结论

1. **对齐点**：你的 `插件系统.py` 在四件事上**比 Ultralytics 更完备**——错误隔离、版本自检、插件清单、逐插件状态/参数。不要把 Ultralytics 当"插件系统"的参考；要参考的是它的**声明式装配**。
2. **从 Ultralytics 借三样**：
   - **YAML/JSON 声明式插件清单**（把插件列表从 `主程序.py` 的代码挪到一个可 diff、可复现的清单文件；这是 Ultralytics 的 `parse_model` + model YAML 最核心的收益）
   - **`check_dict_alignment` 式的键名纠错**（`cfg/__init__.py:645-658`，用 `difflib.get_close_matches` 给参数名/插件名猜最近候选）
   - **名字即稳定 ID**（清单里存 `模块.类名` 字符串而不是对象引用，跨版本靠别名表而非版本号）
3. **不要学的地方**：`globals()[m]` 命名空间即注册表、`else: c2 = ch[f]` 的静默兜底、回调裸循环、按类名/文件名做字符串分派。这四处正是你在 `插件系统.py` 里已经做对的反面教材。
