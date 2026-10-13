# 经典机器人仿真器 功能事实清单（用于差距对标）

调研日期：2025 年（以各官方文档当前版本为准）
调研方式：仅采信官方文档 / 官方仓库 / 权威论文；查不到的一律写「未查证」，不做推测。
版本核验：**Webots 部分已于 2026-09-22 经第二轮逐节点复核并更正**（更正项已用 ⚠️ 标出，详见 Webots 段落 B/C/D/E/H/I 各项）。

---

## 软件名：Gazebo Sim（gz-sim，原名 Ignition Gazebo）
现役版本：**Jetty（第 10 个主版本，LTS，支持至 2031-05）**；上两个 LTS 为 **Harmonic（2023-09 ~ 2029-05）**、Fortress（至 2027-05）
- **一句话定位**：Open Robotics（现 Intrinsic）主导的**开源机器人仿真"基础设施"**，以 SDFormat + 模块化 C++ 库（gz-physics / gz-sensors / gz-rendering / gz-transport / gz-gui）为核心，是 ROS 2 生态的默认仿真后端。
- **许可证 / 闭源商用**：**Apache-2.0**（Debian 版权文件明确 `Files: * → License: Apache-2`，版权方含 Open Source Robotics Foundation / Google）。可直接闭源商用、可再分发。
- **支持平台（含 macOS）**：Ubuntu 为主要支持平台（22.04/24.04/26.04）；**macOS 有 Homebrew 二进制**（`brew install gz-harmonic`，官方称支持 Big Sur、Monterey，当前文档推荐 Mac Ventura/Monterey），但官方明确警告：**macOS 上 GUI 已知不稳定**（Component Inspector 等 GUI 插件可能崩溃），需开两个终端分别跑 server 与 GUI；Windows 仅 Conda-Forge 且"未完全可用"。
- **A 物理引擎**：物理引擎以**插件**形式接入，**默认 DART**；随发行版自带 **DART、Bullet、TPE**（TPE 为轻量无接触求解器），**ODE / Simbody 在 Gazebo Sim 中尚未迁回（官方 issue）**；支持 `GZ_SIM_PHYSICS_ENGINE_PATH` 自定义引擎插件，可在 SDF、命令行 `--physics-engine`、C++ `ServerConfig::SetPhysicsEngine` 三处切换。接触模型可配：碰撞位掩码（collide bitmasks）、恢复系数（restitution）、碰撞检测器、求解器可选。软体：**无原生软体**（对比表列出 Hydrodynamics 与 Ocean currents 为 Gazebo Sim 新增，但未见软体/流体求解器）。颗粒/流体：未查证（仅有浮力 Buoyancy、水动力 Hydrodynamics、洋流 Ocean currents 系统插件）。
- **B 传感器**：官方特性对比表逐项列出——相机、深度相机、RGBD 相机、**分割相机（Segmentation camera）**、GPU Lidar（原 GPU Ray）、IMU、力/力矩、GPS/NavSat、接触传感器、气压、高度计、磁力计、DVL、逻辑相机、逻辑音频、**光学触觉传感器**、热成像相机、触发相机、广角相机、包围盒相机、无线通信（RFComms）。**噪点模型：支持高斯噪声（Gaussian noise）**，且支持自定义更新率、相机畸变、激光回反射、自定义传感器。Ray/Sonar/RFID/多相机在 Gazebo Sim 中缺失（有对应 issue）。
- **C 建模**：主格式 **SDFormat（SDF 1.9+）**，支持 **URDF 导入**（`spawn_urdf` 教程）；**SDF ↔ MJCF 双向转换**（`sdformat_mjcf`，需 SDFormat ≥ 13）、**SDF ↔ USD 转换**（gz-usd）；网格支持 COLLADA / OBJ / STL / USD；SDF 支持参数化（parametrization）、嵌套模型、封闭运动链（Gazebo Sim 中仍为 issue）、Population（issue）。关节/传动：关节控制器（JointController / JointTrajectory）、执行器插件、**可变齿轮箱（VariableGearbox，仅 Classic）**、**轮滑/摩擦（WheelSlip）**，Jetty 新增 **LookupWheelSlip**（用 8 位 RGB 贴图动态改摩擦）。**CAD（STEP/IGES）原生导入：未查证（仅网格级 STL/OBJ/DAE/USD）**。
- **D 算法生态**：**ROS 2 集成通过 `ros_gz`**（Harmonic 对应 ROS 2 Jazzy；Jetty 对应更新版本），Jetty 新增 **ROS 标准 Sim Interface**（`simulation_interfaces`，跨仿真器可移植）；Jetty 新增 **Zenoh transport**（`GZ_TRANSPORT_IMPLEMENTATION=zenoh`）；Jetty 官方发布**强化学习教程（Cartpole + Stable-Baselines3）**；导航栈配套：Jetty 新增 **occupancy grid 导出**（`/scan_image` topic，供 Nav2/SLAM 使用）；MoveIt：**未在 Gazebo 官方文档中查证**（属 ROS 侧组件，非 Gazebo 功能）；控制器插件：System 插件（模型/世界/传感器/GUI/视觉）体系完善。
- **E 仿真能力**：**并行/批量仿真**——可同时运行多个 server 实例、GZ transport 分布式（"Distribute simulation across processes"标注为 coming up）；**headless GPU 渲染**：支持 `--headless-rendering`（EGL，仅 OGRE2），可在 AWS GPU 实例无 X server 跑相机类传感器；**GPU 加速**：渲染由 OGRE2 + OptiX（部分支持）承担，物理为 CPU；领域随机化：**未查到官方专门的 domain randomization 工具**（可用插件自行实现）；**日志/回放**：官方 GUI 功能表列出 Log recording / playback ✓；增量加载关卡（Incrementally load levels）✓；保存仿真状态（Saved simulation states）在 Gazebo Sim 中仍为 issue；录屏（Video recording）✓、截图 ✓。
- **F 界面与交互**：Qt6 GUI（Jetty 从 Qt5 升级到 Qt6，插件需迁移），工具栏 + 右侧插件面板 + 3D 场景；**面板体系即 GUI 插件系统**（Component Inspector、Entity Tree、Grid Config、World Control、Image Viewer、Topic Echo、Plotting 等，可从菜单加载 GUI 插件）；可视化开关丰富（碰撞、惯量、质心、接触点、关节、光源、半透明、线框）；**撤销/重做在 Gazebo Sim 中仍为 issue（Claasic 有）**；模型编辑器（Model editor）在 Gazebo Sim 中为 issue，但可插入 Fuel/本地模型与基本图元。**界面中文：GUI 无官方中文界面（未查证任何 GUI 本地化）；但官方文档有社区中文翻译（LocalizeTheDocs，zh-cn / zh-tw 均可达）**。脚本：C++（插件）、Python（SDF Python bindings ✓）。
- **G 可视化**：**PBR ✓**（需 Ogre2 等支持引擎）、环境贴图 ✓、光照贴图 ✓、粒子效果 ✓、法线贴图 ✓、天空 ✓；**Ogre 1.x / Ogre 2.x 双渲染引擎 + OptiX（部分）**，渲染引擎可插件化（自定义渲染插件）；**雾（Fog）在 Gazebo Sim 中缺失**；深度图/分割图：由深度相机与**分割相机**输出（官方传感器表 ✓）；视频录制 ✓；多视口：官方对比表把 Classic 的 Multi-camera 标为 ✕，建议"用多个同更新率相机替代"。
- **H 部署**：**headless**：`gz sim -s`（仅 server）✓，`--headless-rendering`（EGL）✓，可脱离 GUI 跑（macOS 亦以 `-s` 单独启动 server）；远程/Web：官方有 **Web Visualization 教程**（Classic 的 GzWeb 未迁移）；容器化/CI：官方有 "Continuous Integration For Gazebo Packages" 指南，AWS GPU 实例 headless 教程；**许可证允许闭源商用与再分发（Apache-2.0）**。
- **I 精度实时性**：GUI 内置 **RTF（real time factor）**显示与 **Play/Step/Reset**（可设步长），支持定步长与可配物理步长；数值可复现性：**官方无明确"可复现性"承诺——未查证**（第三方论文观测到多实例间任务结果不一致，但非 Gazebo 官方声明）。
- **J 生态**：资产库 **Gazebo Fuel**（app.gazebosim.org/fuel，含模型与世界，Jetty 改为并行后台下载、启动更快；内置示范世界 jetty_demo 仓库含仓库环境 + 自主叉车 + Open-RMF 演示）；文档质量高（版本化教程 + library API reference + 迁移指南）；更新频率高（每年 1 个主版本 + LTS 周期，Jetty 的 Test & Tutorial Party 一次性关闭 388 个 issue、148/148 Ubuntu 票）；社区：community.gazebosim.org 论坛 + robotics.stackexchange。
- **这个软件独有 / 明显强于别人的 3 项**：
  1. **模块化库架构 + 插件化物理/渲染引擎**：物理与渲染引擎均可运行时切换和自定义接入，无需改核心源码，且 SDF/URDF/MJCF/USD 互转工具链最完整。
  2. **面向云/大规模部署的 headless GPU 渲染（EGL）+ 官方 AWS 教程 + 容器 CI 指南**，服务器/云上跑相机类传感器有官方路径。
  3. **ROS 2 生态绑定最深**：ros_gz + Jetty 的 ROS 标准 Sim Interface + Zenoh transport + occupancy grid 导出 + 官方 RL（SB3）教程，把仿真直接嵌进 ROS 2/RL 工作流。
- **已知短板 2~3 项**：
  1. **macOS 上 GUI 被官方标注为"currently known to be unstable"**，部分 GUI 插件会崩溃；Windows 支持也未完全可用。
  2. **功能相对 Gazebo Classic 仍有缺口**：ODE/Simbody 引擎、多相机、Sonar/Ray/RFID、雾、撤销重做、模型编辑器、保存仿真状态等仍为 open issue。
  3. **无原生软体/流体求解器**，接触与软体建模能力弱于 MuJoCo 系（CoppeliaSim/Webots 通过 MuJoCo 可补）。
- **来源链接**：
  - 特性对比（逐项传感器/插件/物理/渲染/GUI/平台）：https://gazebosim.org/docs/harmonic/comparison/
  - 物理引擎切换（默认 DART，DART/TPE/Bullet）：https://gazebosim.org/api/physics/8/switchphysicsengines.html
  - headless 渲染（EGL + AWS）：https://gazebosim.org/api/sim/7/headless_rendering.html
  - 传感器教程（IMU/接触/Lidar）：https://gazebosim.org/docs/harmonic/sensors/
  - GUI 与 RTF/单步：https://gazebosim.org/docs/harmonic/gui/
  - macOS 二进制安装：https://gazebosim.org/docs/harmonic/install_osx/
  - 平台总览与 macOS 说明：https://gazebosim.org/docs/latest/getstarted/
  - Jetty 发布说明（Qt6/Zenoh/RL/占用栅格/自动惯量/轮滑摩擦）：https://gazebosim.org/docs/latest/release_notes/
  - SDF↔MJCF/USD 互转：https://sdformat.org/tutorials/developers/interoperability_formats/12/
  - Fuel 资产库：https://gazebosim.org/docs/harmonic/fuel/
  - 许可证（Apache-2）：https://metadata.ftp-master.debian.org/changelogs//main/g/gazebo/gazebo_11.1.0+dfsg-6_copyright
  - 中文文档翻译：https://projects.localizethedocs.org/gazebosim-docs-l10n/

---

## 软件名：Webots（Cyberbotics）
现役版本：**R2025a（2025-01-31 发布）——经核验仍是当前最新正式版；R2025b 至 2026-09 仍未发布（changelog 的 R2025b 章节无 "Released on" 行、GitHub 无 tag，仅 nightly 有产物）**。**R2024 整年跳版**：`changelog-r2024.md` 不存在（实测 404），R2023b(2023-06) → R2025a(2025-01) 间隔约 19 个月。自 R2019a 起转为开源
- **一句话定位**：源自 EPFL（1996）、由 Cyberbotics 维护的**教学/科研导向开源 3D 机器人仿真器**，提供"建模 + 编程 + 仿真"一体 IDE、内置 PROTO 资产库与大量循序渐进教程，上手门槛低。
- **许可证 / 闭源商用**：**Apache-2.0**（官方 License Agreement：source code 采用 Apache 2.0，"permits use for any purpose, including commercial applications"）；示例仿真与资产多数 Apache-2.0，少数机器人/物体 PROTO 走 Webots Assets 许可。**闭源商用：允许**。
- **支持平台（含 macOS）**：**Linux（x86-64，Ubuntu 22.04 / 24.04 LTS 保证，不支持 22.04 之前）/ Windows 10、11（64 位）/ macOS 12 Monterey、13 Ventura、14 Sonoma**；官方 CI 对 Linux、Windows、macOS **三平台 nightly 构建与测试**；macOS 提供 `.dmg` 与 Homebrew cask（`brew install --cask webots`），**官方 release 下载表明确写 "macOS — Apple Silicon & Intel"（单一 .dmg，原生支持 Apple Silicon）**，并**专门给出 Apple Silicon（arm64）排障说明（关闭 Rosetta）**。硬件要求：2 GHz 双核 + 2 GB RAM（推荐四核），**需 NVIDIA/AMD OpenGL ≥ 3.3、≥512 MB**，不推荐 Intel 核显。
- **A 物理引擎**：**核心依赖 ODE（Open Dynamics Engine）分支，且没有引擎选择字段**（经核验 R2025a 官方文档中**无 Newton / Bullet / PhysX / MuJoCo**；`WorldInfo.physics` 字段填的是**物理插件名**而非引擎名）；**自定义物理插件（physics plugin）通过 ODE 低层 API，且仅能用 C/C++ 编写**，源码置于 `plugins/physics/<name>/<name>.c`，编译为 `.so/.dll/.dylib` 后以 `WorldInfo.physics=<name>` 启用；回调为 `webots_physics_step`/`cleanup`（必需）与 `webots_physics_init`/`step_end`/`collide`（可选），配套工具函数为 `dWebotsGetBodyFromDEF` 等（⚠️ **不存在 `wb_physics_*` API**），可实现自定义力/力矩、额外关节、自定义碰撞检测与非均匀摩擦、空气动力/水动力模型。`WorldInfo` 物理字段：`gravity` 9.81、`CFM` 1e-5、`ERP` 0.2、`basicTimeStep` 32、`physicsDisableTime` 1、`physicsDisable{Linear,Angular}Threshold` 0.01、`defaultDamping`。**刚体/运动学双模式**：`Solid.physics` 为空即按**运动学（kinematics）**仿真，可整场景禁用物理；差速轮机器人在无 Physics 时走特殊运动学算法。接触模型**可配**（`ContactProperties` 节点按材质对配置：`coulombFriction`（1~4 值，支持各向异性摩擦）、`frictionRotation`、`rollingFriction`、`bounce`、`bounceVelocity`、`forceDependentSlip`、`softERP`/`softCFM`、`maxContactJoints`）。**软体/流体：无原生软体求解器**（节点表中有 `Fluid` 节点用于流体对刚体的作用/浸没，但无软体、无颗粒）。**多物理耦合：未查证**。
- **B 传感器**：官方 Reference 节点清单中的传感器/器件包括——**Camera（RGB，支持 planar/spherical/cylindrical 投影、曝光、抗锯齿、AO、bloom、motionBlur、lens/focus/zoom/lensFlare）、RangeFinder（可作深度相机）、Lidar（可设层数/水平分辨率/垂直 FOV/固定或旋转/near/far/noise）、DistanceSensor（generic/infra-red/sonar/laser，numberOfRays、aperture、gaussianWidth、resolution）、GPS（accuracy/noiseCorrelation(Gauss-Markov 漂移模型)/speedNoise）、Accelerometer、Gyro、Compass、InertialUnit、LightSensor、TouchSensor、Force/力反馈（Joint 力/力矩读数）、PositionSensor、Radar、Receiver/Emitter（无线通信）、Speaker、Display、Pen、Propeller、Muscle、VacuumGripper、Connector、Charger、Joystick、Keyboard、Mouse**。
  **噪点模型：强，但字段名不统一（已逐节点核验，勿一刀切）**——`Camera.noise`（[0,1]，1.0 ≈ 标准差 255）+ `Camera.noiseMaskUrl`（自定义 PNG 噪声遮罩，随机平移产生闪烁）/`resolution`；`Lidar.noise`（1.0 ≈ maxRange 米）+ `resolution`；`RangeFinder.noise`；`InertialUnit.noise`；`PositionSensor.noise`；⚠️ **`GPS` 没有 `noise` 字段**，改用 `accuracy`（位置高斯噪声标准差）+ `noiseCorrelation`（Gauss-Markov 相关噪声，模拟 GPS 漂移）+ `speedNoise` + `speedResolution`；⚠️ **`Accelerometer` / `Gyro` 没有 `noise` 字段**，只有 `resolution`（与 `lookupTable`）；`DistanceSensor` / `LightSensor` 靠 `lookupTable` 第 3 列做非线性/饱和；`Receiver`/`Emitter` 有 `signalStrengthNoise`/`directionNoise`。
  **语义/实例分割：支持**——`Camera.recognition` 挂 `Recognition` 节点（字段 `maxRange`/`maxObjects`/`occlusion`/`segmentation`/`frameColor`/`frameThickness`），仅识别 `recognitionColors` 非空的 Solid，输出 **id（可经 Supervisor 换回节点）/相对位姿/尺寸/像素 bbox/colors/model**；分割真值图经 `wb_camera_recognition_get_segmentation_image` / `save_segmentation_image` 导出（⚠️ **更正：Camera 节点没有 `recognitionSegmentation` 字段**，实测 `resources/nodes/Camera.wrl` 字段表仅有 `noise`/`noiseMaskUrl`/`recognition`，分割开关在 `Recognition.segmentation`）。
  其他传感器细节：**Lidar 由 OpenGL 深度缓冲实现（非光线投射）**，`type` fixed/rotating，`projection` 仅 planar/cylindrical，点云 API 文档称开销大；`DistanceSensor.type` = generic/infra-red/sonar/laser；**`TouchSensor.type` = bumper/force/**force-3d** → 「force-3d」只给 3 轴力，文档未记载力矩**（`Connector`/`VacuumGripper` 也只有 presence + 拉伸/剪切强度）；`Speaker` 可播 WAV 与 SSML TTS（pico/microsoft，多语言音色）。⚠️ **`Microphone` 节点在引擎内存在（`resources/nodes/Microphone.wrl`，字段 aperture/sensitivity）但参考手册无此页（未文档化）→ 实际能力未查证**；另有未文档化的 Experimental `Radio` 节点。
- **C 建模**：主格式为 **PROTO（基于 VRML 的节点 + 参数化模板）**，`.wbt` 世界文件；**CAD 导入**：`CadShape` 支持 **Collada（.dae）与 Wavefront（.obj）**（含路径引用纹理、可远程 URL）；网格 `Mesh` 节点（STL 等）；**URDF/Xacro 导入**经 ROS 2 侧 `webots_ros2_importer`（urdf2proto / xacro2proto）或独立 `urdf2webots` 转换器（⚠️ 核心参考手册中**无 URDF 导入章节**）；MJCF：**未查证**。过程式 PROTO 脚本语言为 **JavaScript**（`# template language: javascript`，`%< %>` 语法，QJSEngine）——**Lua 已于 R2025a 移除**。关节与传动：`HingeJoint` / `SliderJoint` / `Hinge2Joint` / `BallJoint` + `JointParameters`（含 `minStop`/`maxStop`/`springConstant`/`dampingConstant`/`staticFriction`）、`RotationalMotor`/`LinearMotor`/`Brake`/`Motor`，电机具 **`maxVelocity`、`maxForce`/`maxTorque`、`acceleration`、`controlPID`（P/I/D 增益）、`multiplier`（减速比/传动倍数：位置/速度/力命令的乘数）、软限位 `minPosition`/`maxPosition`**；摩擦由 `ContactProperties` 与 `Solid.contactMaterial` 建模；**减速器/齿轮箱建模：通过 `multiplier` 与 `Muscle`/关节参数近似，专门"减速器"模型未查证**。
- **D 算法生态**：**ROS 2 官方接口 `webots_ros2`**（Apache-2.0，官方标注 **MAINTAINED，版本 2025.0.1**，支持 humble/jazzy/kilted/rolling，Foxy/Galactic 已弃；共 **14 个包**：`_driver`/`_control`/`_importer`/`_msgs` 及 tiago/turtlebot/universal_robot/epuck/mavic/tesla/crazyflie/husarion 等；driver 可**自动从 Webots 模型生成 ROS 2 接口**、URDF 配置与 pluginlib 扩展）；⚠️ **ROS 1 支持已在 R2025a 明确移除**（changelog 原文 "Remove ROS (1) support"），旧 `webots_ros` 停在 2019 年；**MoveIt 2：有 UR5e demo**（moveit_ur5e.srdf + controllers/kinematics/movegroup 配置与 launch），但**非 `webots_ros2` 的包依赖**，属独立 demo；**导航/SLAM：有** nav2（turtlebot/tiago/epuck）+ Cartographer 与 slam_toolbox（TIAGo）及对应系统测试；**控制器语言：C / C++ / Java / Python(≥3.8) / MATLAB**（MATLAB 需许可证 ≥2015b），C API 约 200 个函数，标准循环 `wb_robot_init(); while(wb_robot_step(ms)!=-1){} wb_robot_cleanup();`；**extern controller**：`Robot.controller="<extern>"` + 独立启动器 `webots-controller`（`--protocol=ipc|tcp`、`--ip-address`、`--port`、`--robot-name`，**可跨机**；⚠️ **不存在 `--extern` 选项，也不存在 WEBOTS_CONTROLLER_URL**），第三方语言需自建 TCP/IP（自带 khepera_tcpip 示例）；**强化学习：无官方 Gym/RL 接口**（官方仅文档化数值优化 GA/PSO/退火，走 Supervisor），社区方案为 **deepbots（GPL-3.0）** 与 deepworlds。
- **E 仿真能力**：**单世界内多机器人**仿真（示例与竞赛项目常见）；**并行/批量**：官方提供 **Docker 镜像（`cyberbotics/webots`，Docker Hub，Ubuntu 22.04 基础，内置 Xvfb；tag `latest` / `R2023b-ubuntu22.04`）**用于 CI 无 GUI 运行，可启动多容器；**多实例可用 `--port`（默认 1234，多实例端口连续递增）+ extern launcher 定向**；webots.cloud 的 session server 按负载分发；**单实例内批量多环境并行：未查证**；**GPU 加速**：渲染走 OpenGL（要求 3.3+，官方推荐 NVIDIA/AMD），物理为 CPU；`WorldInfo.optimalThreadCount` 可**多线程计算物理**；领域随机化：**未查证官方工具**（但 `randomSeed` 可设定内部随机种子）；**时间倒带：未查证**；**无内置 CSV 导出**（所有已核对文档均无 CSV，需控制器/Supervisor 自行写文件）；**回放/录制**：Supervisor API 提供 **`wb_supervisor_movie_start_recording` / `wb_supervisor_movie_stop_recording` / `wb_supervisor_movie_is_ready`**（输出 **.mp4，仅 MPEG-4/AVC**，Linux 需 ffmpeg / libavcodec-extra / H.264）、**`wb_supervisor_animation_start_recording`（输出 .html/W3D 动画）**、**`wb_supervisor_export_image`（导出主窗口 JPEG）**、**节点导出（`wb_supervisor_node_export_string`）**；状态存取：`world_save`/`load`/`reload`、`simulation_reset(_physics)`、`node_reset_physics`。
- **F 界面与交互**：完整 IDE —— **Scene Tree（场景树 + 字段编辑器，可直接拖拽/改字段）、3D 窗口、文本编辑器、控制台、机器人窗口（robot window）、Preferences**；模型可在场景树中直接编辑，支持拖拽 PROTO 节点、改关节参数、施加力/力矩（`dragForceScale`/`dragTorqueScale`）；**内置代码编辑器**；**中文界面：支持但不保证完整**（官方原文："translated into French, German, Spanish, **Chinese** and Japanese (and partially into Italian). However … may not always be complete or accurate"；Preferences → General → Language 可切换、需重启；**官方中文文档未查证**）；脚本语言：控制器用 C/C++/Java/Python/MATLAB，PROTO 用类 VRML 节点语言（可内嵌 JS/Python 生成过程化模型）；快捷键：**未查证官方快捷键清单**。
- **G 可视化**：OpenGL 3.3+ 实时渲染；`PBRAppearance` 节点 → **PBR 材质支持**；相机节点支持 `exposure`、`antiAliasing`、`ambientOcclusionRadius`（AO）、`bloomThreshold`、`motionBlur`、`lensFlare`、`Lens`/`Focus`/`Zoom`（景深/对焦/变焦）；阴影由光源（`castShadows`）与 CadShape/Shape 的 `castShadows` 控制；**深度图：RangeFinder 输出深度（可导出）**；**分割图：Recognition.segmentation 输出 ground truth 分割图**；**视频录制导出：MPEG-4（Supervisor movie API），截图 JPEG**；**多视口：有相机叠加**——Overlays 菜单可叠加 Camera(品红)/Display(青)/RangeFinder(黄)，双击可弹出独立窗口（⚠️ Viewpoint 参考页**无 overlays 字段**，隐藏字段未查证）。另：**wren 渲染特性 = PBRAppearance（Lambert 漫反射 + Cook-Torrance 高光 + Fresnel-Schlick GGX + IBL + normal/occlusion/emissive 贴图）+ HDR 立方体贴图背景 + GTAO + SMAA 1x + bloom + 镜头光晕 + 曝光 + 运动模糊 + 阴影开关**。
- **H 部署**：**headless：支持**——`xvfb-run webots --mode=fast --no-rendering --stdout --stderr --minimize --batch <world>`（官方 Server Edition 文档）；⚠️ **必须有 X11 连接**（官方称无法把图形输出重定向到别的机器），headless 一律靠 Xvfb；Docker 内 `xvfb-run webots --stdout --stderr --batch --mode=realtime <world>`。**官方 CLI 选项（完整）**：`--batch`（禁阻塞弹窗）、`--minimize`（自动 Fast 模式）、`--no-rendering`、`--mode=pause|realtime|fast`、`--stdout/--stderr`、`--port`(1234)、`--log-performance`、`--sysinfo`、`--version`、`--help`、`--clear-cache`、`--stream[=w3d|mjpeg]`、`--extern-urls`、`--heartbeat`、`convert`(PROTO→URDF/WBO/WRL)；**远程/Web：支持**——官方"Starting Webots Remotely (ssh)"文档、**`--stream` 流式访问 http://IP:port/index.html（w3d 默认 / mjpeg，⚠️ 只能观看漫游、不能控制仿真）**、W3D 场景导出（WebGL 2，Skin/Pen 不支持）、Web Animation（W3D+JSON，仅记录 LED.color、Material.diffuse/emissiveColor、TextureTransform.translation、Pose.rotation/translation、Light.color/on，节点增删不记录）、**webots.cloud**（官方 session + simulation server 架构，可分享/办赛/GPU 云端跑）；沙盒限制：Snap 包内无法运行 MATLAB 控制器、无法改内置依赖（需用 extern controller 绕过）；**闭源商用再分发：Apache 2.0 §4 允许**。
- **I 精度实时性**：**定步长闭环**：`WorldInfo.basicTimeStep`（默认 32 ms）固定仿真步长，`FPS`（默认 60）限制主窗口刷新率；`optimalThreadCount` 控制物理线程数；**实时倍数**：支持 `--mode=realtime` 与 `--mode=fast`（快于实时），GUI 有 Real-time / Run / Pause 模式；物理稳定性辅助：`physicsDisableTime`/`physicsDisableLinearThreshold`/`physicsDisableAngularThreshold`（静止物体自动休眠）；**数值可复现性：有条件保证（非无条件）**——官方文档称"只要函数调用序列不变，各语言给出完全相同结果"，但 `optimalThreadCount > 1` 时"can result in non replicable simulations"，且 `randomSeed = -1` 不可复现；官网宣传语为 "robust, deterministic and well documented"。
- **J 生态**：**内置 PROTO 资产库，实测 master 仓库共 1,045 个 `.proto`**（objects 310 / robots 256 / vehicles 126 / appearances 68 / devices 32 / humans 21，另有 furniture 39、building 46、animal 8、floor 11；统一在 https://webots.cloud/proto 按 keyword 浏览）；按需从官方资产缓存下载、可离线打包（R2025a 整包缓存 zip ≈ 693 MB），含 Webots Assets 许可；仓库 4,647★ / 2,062 forks；文档质量高（User Guide + Reference Manual，每个 API 带 C/C++/Java/Python/MATLAB 标签页 + 教程 1–8 + 年度 changelog）；**发布节奏：历史约每年 2 版（R2018a 2017-12 → R2023b 2023-06），但 R2024 整年跳版、R2023b→R2025a 间隔 19 个月、R2025b 至 2026-09 未发布（见上文短板）**，另有 nightly 构建与三平台 CI；社区：Discord、GitHub Discussions、Stack Overflow（官方监控）、YouTube；2018 年开源后由 Cyberbotics 以付费支持/培训/咨询持续开发。
- **这个软件独有 / 明显强于别人的 3 项**：
  1. **开箱即得的高保真地面真值感知**：`Recognition` 直接给出 id（可经 Supervisor 换回节点）、相对位姿、尺寸、像素 bbox、colors、model，并可直出**分割真值图**；再配合细粒度噪声字段（Camera `noise[0,1]`、Lidar `noise`、GPS `accuracy`+`noiseCorrelation`、Receiver `signalStrengthNoise`），非常适合感知/数据集生成/RL。
  2. **三平台（含 macOS Apple Silicon）官方二进制 + nightly CI 全平台验证**，并**内置多语言界面（含中文）**——对标清单里 F/H 两项的稀缺优势。
  3. **"IDE 式"一体化体验**：Scene Tree 字段级编辑 + 内置代码编辑器 + 一键 MPEG-4 录制 + 内置 PROTO 资产库 + 大量教程，个人/教学上手成本最低。
- **已知短板 2~3 项**：
  1. **物理引擎单一、无软体**：只有官方 ODE 分支且**无引擎切换字段**（文档中无 Newton/Bullet/PhysX/MuJoCo），自定义物理插件只能用 C/C++，`Muscle`/`Skin` 仅图形、**Soft-body/FEM 未查证存在**；关节摩擦只有 `staticFriction`（无 `dynamicFriction`），接触参数需手调 `ContactProperties`。
  2. **发布节奏停滞 + 跳版**：历史约每年 2 版，但 **R2024 整年缺席**，R2023b(2023-06) → R2025a(2025-01) 间隔约 19 个月，**R2025b 到 2026-09 仍未发布**（changelog 无 Released on、GitHub 无 tag、Homebrew/APT/latest 全为 2025a），对需跟进 ROS 2 新发行版的稳定版用户有风险。
  3. **无官方 GPU 并行/批量环境采样能力**（物理 CPU、无 Gym 风格批量 API，官方 RL 接口缺失、社区仅 deepbots GPL-3.0），大规模 RL 训练不如 MuJoCo MJX/Warp 或 Isaac 系；另 **CSV/数据导出、完整快捷键表、官方中文文档、第一方论坛均空缺**；**URDF 仅经 ROS 包/转换器导入、MJCF 未见支持，CAD 仅 Collada/OBJ（无 STEP/IGES）**。
- **来源链接**（官方文档源文件；`cyberbotics.com/doc/*` 为 JS 壳页，故经 CDN 镜像 `https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/**` 读取仓库 markdown 原文；下列 github.com/blob 链接为等价的人类可读入口）：
  - 仓库 README（定位/历史/平台/许可证徽章）：https://github.com/cyberbotics/webots/blob/master/README.md
  - 许可证：https://github.com/cyberbotics/webots/blob/master/docs/guide/webots-license-agreement.md
  - 系统需求与 OS 支持：https://github.com/cyberbotics/webots/blob/master/docs/guide/system-requirements.md
  - 安装（macOS/Apple Silicon/Docker/Server headless）：https://github.com/cyberbotics/webots/blob/master/docs/guide/installation-procedure.md
  - 界面多语言（含中文）：https://github.com/cyberbotics/webots/blob/master/docs/guide/translating-webots-to-your-own-language.md
  - 物理（Physics 节点、kinematics 模式、Solid 合并）：https://github.com/cyberbotics/webots/blob/master/docs/reference/physics.md
  - ODE 依赖说明：https://github.com/cyberbotics/webots/blob/master/docs/reference/ode-open-dynamics-engine.md
  - 物理插件（仅 C/C++）：https://github.com/cyberbotics/webots/blob/master/docs/reference/introduction-of-the-physics-plugins.md
  - 接触模型：https://github.com/cyberbotics/webots/blob/master/docs/reference/contactproperties.md
  - 相机（noise / noiseMaskUrl / recognition）：https://github.com/cyberbotics/webots/blob/master/docs/reference/camera.md
  - 分割真值（Recognition）：https://github.com/cyberbotics/webots/blob/master/docs/reference/recognition.md
  - Lidar：https://github.com/cyberbotics/webots/blob/master/docs/reference/lidar.md
  - GPS（Gauss-Markov 噪声）：https://github.com/cyberbotics/webots/blob/master/docs/reference/gps.md
  - DistanceSensor：https://github.com/cyberbotics/webots/blob/master/docs/reference/distancesensor.md
  - Motor（PID/acceleration/multiplier）：https://github.com/cyberbotics/webots/blob/master/docs/reference/motor.md
  - WorldInfo（basicTimeStep/optimalThreadCount/randomSeed）：https://github.com/cyberbotics/webots/blob/master/docs/reference/worldinfo.md
  - 节点与 API 全清单（参考手册收录 92 个节点）：https://github.com/cyberbotics/webots/blob/master/docs/reference/nodes-and-api-functions.md
  - CadShape（Collada/OBJ 导入）：https://github.com/cyberbotics/webots/blob/master/docs/reference/cadshape.md
  - Supervisor（movie/export API）：https://github.com/cyberbotics/webots/blob/master/docs/reference/supervisor.md
  - 控制器语言（C/C++/Java/Python/MATLAB）：https://github.com/cyberbotics/webots/blob/master/docs/guide/language-setup.md
  - ROS 2 接口：https://github.com/cyberbotics/webots_ros2 ；https://docs.ros.org/en/ros2_packages/kilted/api/webots_ros2/
  - URDF/Xacro 导入：https://docs.ros.org/en/ros2_packages/kilted/api/webots_ros2_importer/
  - 变更日志（R2025a 发布日期 / ROS 1 移除 / R2025b 未发布）：https://github.com/cyberbotics/webots/blob/master/docs/reference/changelog-r2025.md
  - 当前版本号（实测 `R2025a`）：https://github.com/cyberbotics/webots/blob/master/resources/version.txt
  - 最短路径取文档原文（本环境 web 抓取受限时使用）：https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/index.md

---

## 软件名：CoppeliaSim（原 V-REP）
现役版本：**V4.10.0（2025-05-14，rev0）**；V4.9.0（2025-01-10）、V4.8.0（2024-10-31）、V4.7.0（2024-06-14）、V4.6.0（2023-10-21）
- **一句话定位**：Coppelia Robotics 的**老牌"混合作业型"机器人仿真器**：不追求纯物理，而是**运动学（IK/FK）+ 动力学混合**以求效率，主打分布式控制架构、5 套物理引擎、7 种编程语言与极丰富的可定制场景对象。
- **许可证 / 闭源商用**：**三档授权**——**Edu（教育版，免费但仅限学生/教师/学校与大学，不可商用、不可用于企业/研究机构/非营利组织/基金会）、Pro（商业，需询价）、Lite（用于嵌入并随自有产品分发的运行时，需询价）**。官方 Edu 界面上带 "EDU" 水印且许可条款要求不得移除。**闭源商用：可以（走 Pro / Lite 商业授权）。**
- **支持平台（含 macOS）**：官方主页/代理商页面标注 **Windows / macOS / Linux 三平台**；官方文档命令行示例直接给出 **Mac 启动路径**（`./coppeliaSim.app/Contents/MacOS/coppeliaSim`），Ubuntu 上自 V4.6 起用 Qt5.15.2、Windows/Mac/Linux 自 V3.2.2 起统一 Qt5。**Apple Silicon 原生版本：未查证**。
- **A 物理引擎**：**5 套引擎可随时切换**——**Bullet、ODE、MuJoCo、Vortex Studio（闭源商业，需向 CM Labs 注册获取免费 license key）、Newton Dynamics**；官方说明各引擎算法与参数不同、结果不同，**引擎参数按引擎分别调**（形状动力学、关节动力学、全局引擎属性，通过 JSON 编辑器配置）。**刚体**（全部引擎）；**软体/绳索/布料：仅 MuJoCo 支持**（含 clothes、ropes、tendon，经 XML 注入或 `simMujoco.addFlexcomp`，V4.9 起支持 grid 型 flexcomp 并弃用旧 composite 类型）；**颗粒/流体：未查证**；**接触模型可配**：显示接触点、引擎级/形状级/关节级参数、`sim.computeMassAndInertia`；**多物理耦合：无（同一时刻一个引擎）**。官方明确"**非纯物理引擎中心的仿真器，而是运动学+动力学混合**"，并建议机械臂尽量用运动学、只在夹爪/移动机器人等必要时用动力学。
- **B 传感器**：**接近传感器（proximity sensor）**——官方称"精确最小距离计算"、可自定义检测体、作用于 mesh / OC tree / 点云，可模拟超声到红外的各种近距传感器，比离散射线更连续；**视觉传感器（vision sensor）**——固定分辨率、图像内容可经 API 访问、支持视觉回调函数（vision callback）做自定义图像处理、可模拟温度/物体 handle 等自定义通道；**深度：`sim.getVisionSensorDepthBuffer` 官方 API 可取深度缓冲**；**相机对象（camera，用于显示与人眼观察，图像不经 API）**；Velodyne VPL-16 / HDL-64E S2 等 **Lidar 模型**；**力/力矩传感器**（关节动力学力/力矩读数）；**传感器噪声模型：未见官方内建噪声选项——未查证**；**语义/实例分割：未查到官方分割真值功能（但视觉传感器可按 handle 渲染/检测，且可用 IM 插件做 ArUco 标记检测）**。
- **C 建模**：**原生 `.ttt` 场景 / `.ttm` 模型**（单一可移植文件，可内含控制代码）；**导入导出格式：URDF、SDF、Collada、STL、DXF、OBJ、glTF**（GLTF 导出器 V4.7 起支持透明与背面剔除），**LDraw（ldr/mpd）插件**，URDF 导入导出器在 V4.5.1 得到改进（双向）；**STEP/IGES：未查证**。**关节与传动**：运动学关节可经 `sim.setJointTargetPosition`/`sim.setJointTargetVelocity` 驱动并带**最大速度/加速度/ jerk 约束的运动轮廓**；**动力学关节控制模式明确区分：free、force/torque、velocity、position、spring、custom**；关节动力学参数（弹簧 K/阻尼 C、力矩上限、`armature` 转子惯量——MuJoCo 专有且对电机化关节稳定性影响大）；**齿轮/关节依赖（joint dependencies）**可建模（有 gears 演示场景）；**执行器/电机模型**：提供 motor controller 示例场景（力/速度/位置自定义控制器）、`sim.ruckigPos`/`sim.ruckigVel`/`sim.moveToConfig`/`sim.moveToPose`（Ruckig 在线轨迹生成）、Reflexxes 运动库、V4.8 集成 **TOPPRA 时间最优路径参数化**；**IK/FK**：任意机构（分支、闭链、冗余、嵌套环）、可嵌入机器人本体、可算 Jacobian、支持零空间投影、IK 世界可视化调试；**质量/惯量**：可自动计算凸形状质量与惯量矩阵。
- **D 算法生态**：**ROS 接口**（publishers / subscribers / service calls，支持全部标准消息且可扩展；V4.4 起支持 ROS 2 Humble，另有 RosPlugin `simROS2` 与 `sim.callScriptFunction`）；**路径/运动规划：通过 OMPL 插件的 `simOMPL`**（V4.5.1 新增 `simOMPL.createStateSpaceForJoint`、`setStateSpaceForJoints`）；**编程方式 5 种、语言 7 种**：嵌入式脚本（Python 或 Lua）、插件（C/C++）、**远程 API（ZeroMQ remote API：Python、C/C++、Java、JavaScript、MATLAB、Octave、Lua、Rust）**、自定义方案；**强化学习 Gym 接口：未查证**；**MoveIt：未见官方集成（有 OMPL 插件与 ROS 接口，可自行对接）**。
- **E 仿真能力**：**数据记录与可视化**：大量可记录数据流（含用户自定义）→ 时间图 / x-y 图 / 3D 曲线（graphs 模块）；**电影录制器（movie recorder）**、**多级撤销/重做**、**three.js 浏览器查看器**、绘制/焊接缝仿真、OC tree、点云；**时间倒带：未查证**（有 playback 工具模型可手动步进）；**并行/批量仿真：未查到官方批量多环境 API**（可用远程 API 起多个实例，`COPPELIASIM_USER_SETTINGS_FOLDER_SUFFIX` 便于多实例不同配置，但非官方批量采样）；**GPU 加速：未见官方 GPU 物理**（渲染走 OpenGL，另有 POV-Ray 光线追踪插件可软渲染高质量图）。
- **F 界面与交互**：**完整场景层级视图**（显示别名、类型、关联脚本、闭环、选择/可见性、警告）、**模型浏览器支持拖拽（仿真运行中也可拖拽装配）**、**仿真中完全交互**（模型及其嵌入脚本可整体移动/旋转/复制粘贴/缩放/删除而无需改代码）；**内嵌代码编辑器**（V4.5.1 起高亮选中词全部出现、代码折叠、Ctrl+F 搜索；V4.7 统一着色）；**状态栏 commander REPL**（可切 Python/Lua 解释器，支持历史与 TAB 补全，headless 下亦可用）；**自定义 UI 插件（CustomUI / QML / simUI）可建无限量自定义界面元素**；**网格编辑模式**（半自动图元提取、凸分解 HACD/V-HACD/CoACD、网格简化）；**属性浏览器（Property explorer）**与事件查看器；**中文界面：未查证（V4.6 有"preferred language selection"截图，但未见官方中文界面文档）**。
- **G 可视化**：OpenGL 实时渲染（参考帧/包围盒/操作叠加层渲染持续改进；V4.5.1 起核心库全面双精度）；**PBR：未查证官方 PBR 管线**（有材质与纹理系统、可经 Vision Sensor 做图像处理）；**深度图导出：有**（`sim.getVisionSensorDepthBuffer`）；**分割图：未查证**；**视频录制导出：有电影录制器**（另有 POV-Ray 光线追踪插件可出高质量/软阴影/焦外模糊图，及高分辨率截图工具）；**多视口：视图页面可包含无数个视图（官方中文导览称"页面中可以包含无数个视图"）**。
- **H 部署**：**headless：强支持**——`-H` **真 headless**（用 `coppeliaSimHeadless` 库，无 GUI 依赖，但仍需 display server；此时视觉传感器不工作，除非走 POV-Ray 渲染插件）、`-h` **模拟 headless**（仅隐藏 GUI）、`-s<ms>` 自动跑指定时长、`-q` 跑完自动退出，可组合成 `coppeliaSim -h -s5000 -q myScene.ttt` 的 CI 命令；**无 Qt 依赖编译**（V-REP 时代即支持，但视觉传感器需插件渲染）；**远程/Web**：远程 API 客户端（可从另一台 PC 或真实机器人控制）、WebSockets 插件（V4.10 起支持客户端与服务端）、ZeroMQ、**three.js 浏览器查看器**；**许可证：闭源商用需 Pro/Lite 商业授权**。
- **I 精度实时性**：**双时间步明确分离**——`simulation dt`（仿真步长，官方强烈建议 50 ms，即主脚本每次执行推进的仿真时间）与 `dynamics dt`（物理引擎步长，官方强烈建议 5 ms；默认组合为每个仿真步 10 次动力学计算）；`simulation dt` 不得小于 `dynamics dt`；**Simulation passes per frame (ppf)** 控制一个渲染帧前跑多少个仿真步；**实时倍数**：可勾选 "Real-time simulation, multiplication factor X" 把仿真时间钳制到实时（甚至 X 倍实时）；可设"仿真时间超过某值自动暂停"与"脚本错误时暂停"；**引擎全局参数可调（Engine properties，JSON 编辑器）**；**数值可复现性：官方未给承诺——未查证**（V4.5.1 起全面双精度，Newton Dynamics 宣称使用确定性求解器）。
- **J 生态**：**模型库**（整合模型浏览器，**每次发行都有更新**，用户可在 `<userSettingsDir>/userContent/models/<category>/` 与 overlay 仓库中扩展并自动叠加到浏览器）；**插件与 add-on 生态庞大**：simIK（IK）、simOMPL（规划）、simEigen（特征值/线性代数，V4.10 新增快速向量与数学运算）、simIGL（几何处理：测地线、扫掠体、布尔运算、凸包、四面体化等）、simIM（图像/标记）、simUI/CustomUI/QML、simWS（WebSockets）、simPovRay（光追）、simQHull、simConvexDecompose、simOpenMesh、simCHAI3D（触觉）、simCmd（commander）、V4.10 新增 **simEvents（事件过滤）** 与 **MIDI I/O 插件**；**文档**：官方称"exhaustive documentation"，含大量 demo 场景（scenes/...）；**更新频率：约每 4~9 个月一次功能版本 + 年内 rev 修补**（V4.8→4.9→4.10 均在 8~9 个月内）；商业支持需为付费客户。
- **这个软件独有 / 明显强于别人的 3 项**：
  1. **广度之王：5 套物理引擎（含商业级 Vortex 与高保真 MuJoCo）+ 7 种语言 + 5 种编程方式 + 海量插件/add-on**，同一场景可随任务切换引擎，工程验证/数字孪生场景覆盖最广。
  2. **精确接近传感器与几何能力**：官方称在自定义检测体内做**精确最小距离**计算（作用于 mesh / OC tree / 点云），配合 IGL/QHull/凸分解插件，是清单里几何与碰撞/距离查询能力最强的。
  3. **运动学优先的混合仿真 + 极强远程/分布式控制**：IK/FK 可嵌入机器人本体、ZeroMQ 远程 API 覆盖 8 种语言、仿真中可自由增删改场景对象而不破坏脚本，非常适合算法原型与 HIL/远程监控。
- **已知短板 2~3 项**：
  1. **不是纯物理仿真器**：官方自己建议机械臂"尽量用运动学"，软体仅 MuJoCo 支持，无颗粒/流体，接触保真度与可复现性缺乏官方保证。
  2. **许可对商用不友好**：Edu 免费但**严格禁止企业/研究机构/非营利使用**且带 EDU 水印；商用必须购买 Pro，嵌入式分发需 Lite；Vortex 引擎还需单独向 CM Labs 注册。
  3. **传感器与噪声模型薄弱**：无内建传感器噪声模型、无官方分割真值、PBR/多视口/GPU 物理均未见官方支持，macOS 的 Apple Silicon 原生版本也未查证。
- **来源链接**：
  - 产品主页（引擎清单/API/特性/三档授权）：https://www.coppeliarobotics.com/
  - 主特性页（5 引擎、软体、导入导出格式、模型浏览器、Edu/Lite）：https://manual.coppeliarobotics.com/en/coppeliaSimFeatures.htm
  - 动力学模块（5 引擎详述、混合仿真定位）：https://manual.coppeliarobotics.com/en/dynamicsModule.htm
  - 引擎差异（软体/绳索/连续关节/动态内容修改/非凸/静态形状/表面速度）：https://manual.coppeliarobotics.com/en/physicsEngineDifferences.htm
  - 许可条款（Edu/Pro/Lite）：https://manual.coppeliarobotics.com/en/licensing.htm
  - 仿真设置（simulation dt / dynamics dt / ppf / 实时倍数）：https://manual.coppeliarobotics.com/en/simulationPropertiesDialog.htm
  - 命令行（-H 真 headless / -h / -s / -q / Mac 路径 / 环境变量）：https://manual.coppeliarobotics.com/en/commandLine.htm
  - 脚本（Lua/Python、脚本类型）：https://manual.coppeliarobotics.com/en/scripts.htm
  - 接近传感器：https://manual.coppeliarobotics.com/en/proximitySensors.htm
  - 视觉传感器：https://manual.coppeliarobotics.com/en/visionSensors.htm
  - 版本历史（V4.10.0/4.9/4.8/4.7/4.6 特性与日期）：https://manual.coppeliarobotics.com/en/versionInfo.htm
  - 深度缓冲 API：https://manual.coppeliarobotics.com/en/sim/simGetVisionSensorDepthBuffer.htm

---

## 软件名：PyBullet / Drake / MATLAB Simscape（第 4 组，简要）
### PyBullet（Bullet Physics SDK 的 Python 模块）
- **定位**：基于 Bullet 的 Python 快速仿真模块，物理仿真 + 机器人 + 深度强化学习；可加载 **URDF、SDF** 等格式的铰接体，提供正/逆动力学、正/逆运动学、碰撞与射线查询。
- **许可证 / 闭源商用**：**zlib/libpng（zlib）**，允许闭源商用。
- **平台（含 macOS）**：PyPI 标称 MacOS / Windows / Linux；**官方 `pybullet` 包在 macOS（Apple Silicon）上的构建存在问题，社区维护了 fork `pybullet-arm64`（版本 3.2.8）作为 drop-in 替代**，提供 macosx 10.9+/10.13+ universal2 与 11.0+/14.0+ ARM64 wheel——即 **macOS arm64 属"第三方修复"而非官方**。
- **A 物理引擎**：Bullet（刚体 + 软体；PyBullet 支持 soft body / cloth）；可设 `setPhysicsEngineParameter` 等引擎参数。
- **B 传感器**：`getCameraImage` 提供 **CPU 渲染器（TinyRenderer）与 OpenGL 可视化**，可出 RGB / 深度 / 分割（含 `ER_SEGMENTATION_MASK_OBJECT_AND_LINKINDEX` 分割渲染标志）；射线查询 `rayTest`；**IMU/GPS 等传感器需自行从状态计算**。
- **C 建模**：URDF、SDF、MJCF（经转换）、OBJ/STL 网格；关节与电机模型较简，宜在 Python 侧实现控制器。
- **D 算法生态**：ROS 支持弱（需第三方 bridge）；**Gym 风格批量环境生态强**（`DIRECT` 无界面模式 + 多个 client 并行，典型如 gym-pybullet-drones）；**MoveIt：无**。
- **E 仿真能力**：**DIRECT（headless，无 GUI）与 GUI 两种连接模式**，可在同一进程/多进程创建多个物理 client 做批量采样；**GPU：渲染有 OpenGL，物理 CPU**；时间倒带/回放：有 `saveState`/`restoreState` 与 `saveBullet` 等状态存取；录制：可逐帧 `getCameraImage` 自行编码。
- **F/G/H**：GUI 为简易 OpenGL 调试界面（非本清单软件的完整编辑器）；无中文界面资料；headless 靠 DIRECT；**无独立实体编辑器**（建模靠代码 + URDF 文件）。
- **I 精度实时性**：定步长 `setTimeStep`/`stepSimulation`，实时倍数可调（`setRealTimeSimulation` 等）；**数值可复现性：官方未见严格承诺——未查证**。
- **J 生态**：文档为官方 Quickstart Guide（PDF），生态以 RL 社区（gym-pybullet-drones 等）为主，**资产生物库规模远小于 Fuel/PROTO 库**。
- **独有/强项**：① Python 原生、pip 一行安装、RL 批量采样生态最成熟；② 同时提供 CPU 渲染器（无需 GPU 也能出分割/深度图）；③ zlib 许可极宽松。
- **短板**：① **无完整 GUI 建模/场景编辑器**，可视化与交互远弱于前三者；② **macOS arm64 依赖第三方 fork**；③ 无 ROS 2 官方集成、无 MoveIt、传感器噪声与分割 ground truth 需自行实现。
- **来源**：https://pypi.org/project/pybullet-arm64/ ；https://pybullet.org/wordpress/ ；Quickstart：https://github.com/bulletphysics/bullet3/blob/master/docs/pybullet_quickstartguide.pdf

### Drake（MIT / Toyota Research Institute）
- **定位**：以**优化为核心**的 C++/Python 工具箱，强调"暴露动力学方程结构（稀疏性、解析梯度、多项式结构、不确定性量化）"而非黑箱仿真，面向基于模型的设计与验证。
- **许可证**：**BSD 系（RobotLocomotion/drake 的 LICENSE.TXT，v1.44.0）**——需以官方文件为准；**许可允许商用**（BSD 系），但**具体条款未逐条核验**。
- **平台**：官方 pip wheel 覆盖 **Ubuntu（APT）与 macOS（pip）**，文档要求 macOS 使用 Homebrew Python（非系统 Python）；**平台支持矩阵细节未查证**。
- **A 物理引擎**：**自研多体动力学 + 接触求解器**，主打 **hydroelastic contact（水弹性接触）**（把接触面建模为压力场，官方有 Hydroelastic Contact 教程与用户指南）；摩擦、接触、空气动力学；**Soft body / 流体 / 颗粒：未查证**。
- **B 传感器**：**未见内建传感器套件**；提供渲染与仿真示例（pydrake）供自行搭建感知。
- **C 建模**：**URDF / SDF 导入**（`authoring_multibody_simulation` 教程），SceneGraph 用于几何与碰撞；执行器模型丰富（含电机/PD 等）。
- **D 算法生态**：**ROS 2 集成标为 "unsupported"（drake-ros 仓库）**；LCM 消息；Julia 绑定 unsupported；**MoveIt 需经 ROS 侧**；强项是数学规划/求解器（MathematicalProgram，含 SNOPT）与基于优化的控制。
- **E 仿真**：Drake Visualizer 可视化；**批量/并行未见官方批量环境 API——未查证**；GPU：**未查证**；回放/录制：**未查证**。
- **F/G/H/I/J**：无面向终端用户的完整 GUI 建模编辑器（以 Python/Jupyter 教程 + 可视化器为主）；无中文界面资料；**平台与 headless 细节未查证**；精度与接触保真度是其强项（解析梯度、水弹性接触），**实时性能非其目标**；生态为学术/研究型（MIT Underactuated、Robotic Manipulation 课程）。
- **独有/强项**：① **优化优先**：解析梯度、稀疏结构、MathematicalProgram 与 SDP/SNOPT 求解器一体化；② **水弹性接触**提供比点接触更真实的接触力分布；③ 与 MIT 课程体系深度绑定，教学/科研示例质量极高。
- **短板**：① **ROS 2 集成官方标注 unsupported**，无 MoveIt/导航栈绑定；② 非"开箱即用"仿真器（无完整 GUI 编辑器与资产库）；③ 平台支持矩阵、批量仿真、GPU 等关键项官方资料不足（未查证）。
- **来源**：https://drake.mit.edu/ ；https://drake.mit.edu/pip.html ；水弹性接触：https://drake.mit.edu/tutorials/hydroelastic_contact_basics.html 与 https://drake.mit.edu/doxygen_cxx/group__hydroelastic__user__guide.html ；许可证：https://github.com/RobotLocomotion/drake/blob/v1.44.0/LICENSE.TXT

### MATLAB/Simulink Robotics System Toolbox + Simscape Multibody
- **定位**：**商业闭源**的模型化设计（MBD）工具链，机器人算法 + 多体动力学 + 控制系统一体，走 MathWorks 商业授权（需相应工具箱许可）。
- **平台（含 macOS）**：MATLAB 支持 Windows / Linux / **macOS**（含 Apple Silicon 原生版本）——属该清单中 macOS 支持最完整的商业方案之一；**具体版本矩阵未逐项查证**。
- **A 物理引擎**：**非通用刚体/软体物理引擎**，而是**基于物理建模的 Simscape Multibody 多体动力学**；接触需 **Simscape Multibody Contact Forces Library**（如 Spatial Contact Force 模块，R2019b 起加入）；**软体/流体/颗粒：需 Simscape Fluids/Flexible Body 等额外产品，未逐项查证**。
- **B 传感器**：**未见内建通用传感器仿真套件**（相机/Lidar/IMU 需经 Automated Driving / Navigation Toolbox 等，未查证）。
- **C 建模**：**URDF 导入（Simscape Multibody "Import URDF Models"）**；CAD 经 Simscape Multibody Link 从 SolidWorks 等导入（**未逐项查证**）；关节/传动/电机模型经 Simscape 物理网络逐块搭建。
- **D 算法生态**：**ROS/ROS 2 官方支持**（ROS Toolbox，含与 Gazebo 的协同仿真文档）；MoveIt/SLAM：需经 ROS Toolbox 与外部 ROS 组件；**强化学习：有 Reinforcement Learning Toolbox（未逐项查证与仿真器的对接）**。
- **E/F/G/H/I/J**：批量/并行可用 Parallel Computing Toolbox（**与仿真器批量环境的对接未查证**）；无开源资产库；**闭源商用需购买授权**；文档为 MathWorks 官方帮助中心（**本次抓取被 403 拒绝，多项细节未查证**）。
- **独有/强项**：① **控制系统/模型化设计（MBD）闭环最强**（Simulink 自动代码生成、HIL 测试）；② 与 MATLAB 数学/优化/数据处理无缝；③ 企业级商业支持与 macOS 支持完整。
- **短板**：① **闭源付费**，成本高、工具链重；② **非通用机器人物理引擎**，无软体/颗粒/流体等通用物理能力（需额外产品）；③ 无内置机器人资产库与场景编辑器，接触建模需额外 Contact Forces Library。
- **来源**（本次可核验部分）：URDF 导入：https://www.mathworks.com/help/sm/ug/urdf-import.html （抓取 403，搜索结果确认页面存在）；Contact Forces Library：https://www.mathworks.com/matlabcentral/fileexchange/47417-simscape-multibody-contact-forces-library ；ROS Toolbox 文档：https://www.mathworks.com/help/releases/r2025a/pdf_doc/ros/ros_ug.pdf 。**注：MathWorks 站点对本环境返回 403，除上述外多项未查证。**

---

## 这类软件的共同点（3~5 条）
1. **"开源 + Apache/BSD/zlib 宽松许可"已是主流，闭源商用不再需要换工具**：Gazebo（Apache-2.0）、Webots（Apache-2.0）、PyBullet（zlib）、Drake（BSD 系）都可直接闭源商用；只有 CoppeliaSim 与 MATLAB 走商业授权（CoppeliaSim Edu 还明确禁止企业与研究机构使用）。**因此"许可证"本身已很难成为自研软件的差异化卖点，反而"商业授权 + 企业级支持"是 CoppeliaSim/MATLAB 相对开源方案的收费点。**
2. **物理引擎已普遍"插件化 + 多引擎可选"，且引擎能力分层明显**：Gazebo 默认 DART 并可插 Bullet/TPE/自定义；CoppeliaSim 一场景可切 5 引擎；Webots 绑 ODE 但开放 C++ 物理插件；MuJoCo（经 CoppeliaSim/MJX）提供软体、绳索、布料、tendon。**共同天花板是：通用机器人仿真器普遍不做颗粒/流体/多物理耦合，软体基本只有 MuJoCo 系有。**
3. **传感器仿真的"标配"已经很高，噪声与真值图成为分水岭**：三款主力都覆盖 RGB / 深度 / LiDAR / IMU / 力扭矩 / GPS / 接触；**Gazebo 有分割相机与高斯噪声配置**，**Webots 有最完整的噪声建模（相机噪声掩码、GPS Gauss-Markov 漂移）与分割 ground truth**，**CoppeliaSim 强在精确近距/最小距离与深度缓冲但不提供噪声模型与分割真值**。**"噪声可配 + 语义/实例分割真值可导出"是高端仿真器的实际门槛。**
4. **ROS 2 集成深度决定生态地位，但"仿真器 ≠ 算法栈"**：ROS 2 集成最完整的是 Gazebo（ros_gz + 标准 Sim Interface + Zenoh + 占用栅格导出 + 官方 RL 教程），Webots 次之（webots_ros2 官方包与多机器人示例），CoppeliaSim 提供 ROS 消息/服务接口但不绑定规划栈，Drake 的 ROS 2 明确标注 unsupported。**MoveIt / SLAM / 导航栈在任何一款仿真器里都不是"仿真器功能"，而是 ROS 侧组件——对标时不应把 MoveIt 计入仿真器能力。**
5. **"批量并行 + GPU + 可复现性"是全体经典仿真器的共同短板，也是新入者的机会窗口**：Gazebo 靠多实例/EGL headless 与 Zenoh 分布式（进程间分布仍标 coming up）、Webots 靠 Docker 多容器 + `--port` 多实例、PyBullet 靠 DIRECT 多 client、Drake/CoppeliaSim 无官方批量采样；**三款主力的物理都在 CPU**。可复现性方面唯一给出**条件性**保证的是 Webots（"只要函数调用序列不变，各语言给出完全相同结果"，但 `optimalThreadCount>1` 或 `randomSeed=-1` 即失效），**没有任何一款承诺无条件的跨平台数值可复现**。**"GPU 物理 + 官方批量多环境 + 无条件可复现性保证"是当前最清晰的差异化空位。**
6. **维护节奏本身就是竞争力，而三款主力都出现过节奏波动**：Webots 历史上约每年 2 版，但 **R2024 整年跳版、R2023b→R2025a 间隔 19 个月、R2025b 到 2026-09 仍未发布**；Gazebo 相对规律（年 1 主版本 + LTS），但从 Classic 到 Sim 的迁移缺口长期未补齐（ODE/Simbody、多相机、模型编辑器等仍为 open issue）。**"稳定可预期的发版节奏 + 明确的 LTS 承诺"可作为自研软件的一项可比优势写入对标表。**
