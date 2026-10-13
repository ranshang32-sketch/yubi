# Webots（Cyberbotics）特性对比事实表

**核查日期**：2026-09-22（沙箱系统时间）｜**方法**：仅采信官方文档/官方仓库/官方发布渠道；站点为 JS 渲染，`cyberbotics.com/doc/*` 抓取仅得壳页，故文档事实经官方仓库 markdown 的 CDN 镜像核对。

**链接简写**：
- `docs/<路径>` = `https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/<路径>`（官方仓库 `cyberbotics/webots` 的 docs 源文件镜像，master = 2026-09-21 提交 `d2ba706`）
- `repo/<路径>` = `https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/<路径>`

> 凡未能从来源核实的，一律标注 **未查证**，不做推测。

---

## 1. 最新版本 / 定位

- **最新正式版：R2025a**（2025-01-31 发布，GitHub release 于 2025-02-04 发布）。`repo/resources/version.txt` 在 master 与最新 nightly 提交上均为 `R2025a`；GitHub Releases API 的 `latest` 亦为 R2025a；Homebrew cask、Cyberbotics APT 仓库（`Version: 2025a`）同样停在 2025a。
  - <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/resources/version.txt>
  - <https://ungh.cc/repos/cyberbotics/webots/releases/latest>
  - <https://formulae.brew.sh/cask/webots>
- **R2025b 尚未正式发布**：`docs/reference/changelog-r2025.md` 中 R2025b 章节**没有** “Released on …” 行，且 GitHub 无 `R2025b` release（`/releases/R2025b` 返回 404）。仅存在 nightly 预发布构建（含 `webots-R2025b*.dmg/.deb/.exe` 产物），说明 R2025b 是当前开发目标。
  - <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/changelog-r2025.md>
  - <https://ungh.cc/repos/cyberbotics/webots/releases>
- **一句话定位**：开源、跨平台的桌面机器人仿真器，提供“建模—编程—仿真”完整开发环境；核心技术栈为 Qt GUI + **ODE 分支物理引擎** + OpenGL 3.3 渲染引擎（wren），常用于工业、教育与科研。
  - <https://cyberbotics.com/>
  - <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/README.md>

## 2. 许可证 / 商业闭源使用

- **Apache License 2.0**（仓库根 `LICENSE` 即 Apache 2.0 全文）。官方许可页明确：“permits everyone to use a software source code, free of charge, **for any purpose, including commercial applications**” → **允许闭源商业使用与再分发**。
  - <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/LICENSE>
  - <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/webots-license-agreement.md>
- **2018 年前为商业软件，已核实**：R2019a release 说明写明 “Webots R2019a is the first version of Webots released under the Apache 2.0 open source license”（R2019a 发布于 2018-12-17）；README 亦载“1998 年起由 Cyberbotics 商业化开发，2018 年 12 月开源”；FAQ 称 **R2018 及更早版本仍保留商业授权系统**。
  - <https://ungh.cc/repos/cyberbotics/webots/releases/R2019a>
  - <https://gcore.jsdelivr.net/gh/cyberbotics/webots@R2022b/docs/guide/general-faq.md>
- **例外**：少量机器人/物体 PROTO 资产采用单独的 “Webots Assets license agreement”，另有用户贡献样例采用各自许可（文件内均已标注）。商用闭源时须逐项核对资产许可。
  - <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/webots-license-agreement.md>

## 3. 支持的操作系统（含 macOS Intel / Apple Silicon）

- **Linux**：官方保证最新 Ubuntu LTS（22.04、24.04）；**仅提供 x86-64**；不支持 Ubuntu 22.04 以下。发行包 `.deb` / `.tar.bz2` / `.snap`。
- **Windows**：Windows 10 / 11（**仅 64 位**）。
- **macOS**：macOS 12 Monterey、13 Ventura、14 Sonoma（master 及最新 nightly 的 system-requirements 均如此，macOS 15+ 未列为官方支持）。
- **Apple Silicon：支持**。R2025a release 的下载表中 macOS 一栏明确标注 “**Apple Silicon & Intel**”，只提供一个 `.dmg`；安装文档专设 “Troubleshooting for Apple Silicon Users”（Rosetta/arm64 架构问题）；R2025b changelog 亦修复 “`webots-controller` executable … on arm-based mac devices”。
  - <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/system-requirements.md>
  - <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/installation-procedure.md>
  - <https://ungh.cc/repos/cyberbotics/webots/releases/latest>

## 4. 物理引擎 / 刚体软体 / 自定义插件 / 运动学模式

- **引擎：只有 ODE（Open Dynamics Engine）**，且是官方维护的 fork：“Webots relies on ODE, the Open Dynamics Engine, for physics simulation”。在所有已核对的文档中**均无** Newton / Bullet / PhysX / MuJoCo 的支持说明，也**没有任何场景字段可选择物理引擎**（`WorldInfo.physics` 是“物理插件名”，不是引擎选择器）。
  - <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/ode-open-dynamics-engine.md>
  - <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/worldinfo.md>
  - ODE 定制（官方 fork 的增强）：Hinge2 悬架任意轴（`dParamSuspensionERP/CFM`）、插件可自建接触约束与非均匀摩擦等。
    <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/ode-improvements.md>
- **刚体建模**：`Solid` + `Joint` + `Physics` 层级；`Physics` 字段 `density`(默认1000) / `mass` / `centerOfMass` / `inertiaMatrix` / `damping`；`Damping` 有 `linear`、`angular`（默认各 0.2）。无关节的 Solid 子节点会在引擎层合并为同一刚体。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/physics.md>
- **软体 / 变形体：无物理意义上的软体支持（未查证存在 FEM/软体求解器）**。`Muscle` 仅为显示收缩的椭球（无物理）；`Skin` 为 FBX 网格动画，可纯图形或由 Solid/Joint 骨架驱动；`BallJoint` 的弹簧-阻尼可用于“模拟绳索与柔性梁的弹性变形”。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/muscle.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/skin.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/balljoint.md>
- **运动学模式 / 关闭物理：可。**`Solid.physics = NULL` 即进入 **kinematics 模式**：只按目标速度运动、**不产生接触力**（文档原话：物体可立即达到目标速度）；差速轮机器人可在无 Physics 下按专门运动学算法移动；`Solid.boundingObject` 为 NULL 时 `physics` 必须为 NULL。Supervisor 另有 `wb_supervisor_node_set_velocity()` 直接设定 Solid 绝对线/角速度。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/physics.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/solid.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/supervisor.md>
- **自定义物理插件**：C/C++ 编写；源码置于 `my_project/plugins/physics/<name>/<name>.c(.cpp)`，编译为 `.so/.dll/.dylib`；在 `WorldInfo.physics` 填 `<name>` 启用。必备回调 `webots_physics_step()`、`webots_physics_cleanup()`，可选 `webots_physics_init(dWorldID,dSpaceID,dJointGroupID)`、`int webots_physics_collide(dGeomID,dGeomID)`、`webots_physics_step_end()`；工具函数为 `dWebotsGetBodyFromDEF`、`dWebotsGetGeomFromDEF`、`dWebotsGetContactJointGroup`、`dWebotsSend/Receive`、`dWebotsGetTime` 等。
  ⚠️ 该 API **不叫** `wb_physics_*`，也没有 `wb_physics_apply_force`（文档中不存在）。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/plugin-setup.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/callback-functions.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/utility-functions.md>
- 物理相关 `WorldInfo` 字段：`gravity` 9.81、`CFM` 0.00001、`ERP` 0.2、`physics`(插件名)、`basicTimeStep` 32、`physicsDisableTime` 1、`physicsDisableLinearThreshold` 0.01、`physicsDisableAngularThreshold` 0.01、`defaultDamping`。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/worldinfo.md>

## 5. 传感器清单 / 噪声 / 地面真值识别

| 传感器 | 关键结论（含噪声建模） | 来源 |
|---|---|---|
| Camera | RGB；`noise` SFFloat[0,1]（逐通道高斯噪声，1.0≈std 255）+ `noiseMaskUrl`；另有 `recognition` SFNode | `docs/reference/camera.md` |
| **Recognition（真值识别）** | 字段 `maxRange`/`maxObjects`/`occlusion`/**`segmentation`**/`frameColor`/`frameThickness`；仅识别 `recognitionColors` 非空的 Solid；输出真值：`id`、相对相机的 `position`/`orientation`/`size`、像素包围盒 `position_on_image`/`size_on_image`、`colors`、`model`；分割图 API `wb_camera_recognition_get_segmentation_image` / `..._save_segmentation_image` | `docs/reference/recognition.md`、`docs/reference/camera.md` |
| ⚠️ 更正 | Camera **没有** `recognitionSegmentation` 字段（`docs/reference/camera.md` 与 `repo/resources/nodes/Camera.wrl` 的字段表中只有 `recognition`）——分割开关在 **`Recognition.segmentation`** | `repo/resources/nodes/Camera.wrl` |
| RangeFinder（深度相机） | z-buffer 线性化为米制深度；`fieldOfView`/`width`/`height`/`projection`/`near`/`minRange`/`maxRange`/`motionBlur`/**`noise`**/`resolution` | `docs/reference/rangefinder.md` |
| Lidar | **基于 OpenGL 深度缓冲渲染**（非光线投射）；`type`{fixed,rotating}、`numberOfLayers`、`verticalFieldOfView`、`projection`{planar,cylindrical}、`tiltAngle`、**`noise`**（1.0≈`maxRange` 米的高斯 std）、`resolution`；点云 `wb_lidar_enable_point_cloud`/`get_point_cloud`（文档称计算开销大） | `docs/reference/lidar.md` |
| DistanceSensor | 射线探针；`type`{generic, infra-red, sonar, laser}、`numberOfRays`、`aperture`、`gaussianWidth`；**无 `noise` 字段**，噪声由 `lookupTable` 第 3 列（百分比）给出 | `docs/reference/distancesensor.md` |
| GPS | **无 `noise` 字段**；噪声以 `accuracy`（位置高斯 std，米）、`noiseCorrelation`（Gauss-Markov 漂移）、`speedNoise`、`speedResolution` 建模 | `docs/reference/gps.md` |
| InertialUnit（IMU 姿�态） | 有 `noise`（默认 0，1.0≈std π/2 rad）与 `resolution`；输出 roll/pitch/yaw + 四元数（真值姿态，无传感器融合） | `docs/reference/inertialunit.md` |
| Accelerometer / Gyro | **无 `noise` 字段**；仅有 `lookupTable`、`xAxis/yAxis/zAxis`、`resolution` | `docs/reference/accelerometer.md`、`docs/reference/gyro.md` |
| Compass / PositionSensor / LightSensor | Compass 存在；PositionSensor 有 `noise`（m/rad）；LightSensor 无 `noise`，噪声由 `lookupTable` 第 3 列给出 | `docs/reference/positionsensor.md`、`docs/reference/lightsensor.md` |
| TouchSensor / 力觉 | `type`{bumper, force, **force-3d**}；`wb_touch_sensor_get_values` 返回 **3 轴力**——文档中**未记载力矩输出**（连接器 Connector / VacuumGripper 亦只给 presence 与拉伸/剪切强度上限） | `docs/reference/touchsensor.md` |
| Emitter / Receiver（无线通信） | `type`{radio, serial, infra-red}、`channel`（0 留给物理插件）、`baudRate`、`range`/`maxRange`、`aperture`；噪声字段为 `signalStrengthNoise`、`directionNoise`；`wb_receiver_get_emitter_direction` 返回归一化方向，信号强度 ∝ 1/r² | `docs/reference/emitter.md`、`docs/reference/receiver.md` |
| Radar | 多目标距离/速度/方位/接收功率；噪声 `rangeNoise`/`speedNoise`/`angularNoise`；目标需设 `radarCrossSection` | `docs/reference/radar.md` |
| Altimeter | 存在（`accuracy`、`resolution`） | `docs/reference/altimeter.md` |
| Speaker | 播放 WAV（`wb_speaker_play_sound`）+ SSML 文本转语音（`wb_speaker_speak`，引擎 pico/microsoft，语言 en-US/…/it-IT） | `docs/reference/speaker.md` |
| Microphone | **引擎内有 `Microphone` 节点**（字段 `aperture`、`sensitivity` dB，见 `repo/resources/nodes/Microphone.wrl`），但**官方参考手册无该页**（`docs/reference/microphone.md` 不存在，节点总表亦未列）→ 属于未文档化节点，能力**未查证** | `repo/resources/nodes/Microphone.wrl` |
| (另有) `Radio` 节点 | 引擎内存在且自述 “Experimental”，同样未文档化 → **未查证** | `repo/resources/nodes/Radio.wrl` |

结论：**噪声可建模**，但字段名不统一——Camera/Lidar/RangeFinder/InertialUnit/PositionSensor 用 `noise`，GPS 用 `accuracy`+`noiseCorrelation`，Accelerometer/Gyro 只有 `resolution`，DistanceSensor/LightSensor 靠 `lookupTable` 第 3 列。**地面真值物体识别与分割**由 `Recognition` 节点提供，仅对设置了 `recognitionColors` 的 Solid 生效。

## 6. 机器人建模：PROTO / 关节 / 电机 / 摩擦

- **PROTO**：`.proto` 文本，VRML/X3D 风格节点集扩展，文件头 `#VRML_SIM {{ webots.version.major }} utf8`；结构 `PROTO name [ fields ] { body }`，字段 `field <type> <name> <default>`，支持 `IS`、取值约束、`unconnectedField`；存于项目 `protos/`。**过程式 PROTO 脚本语言 = JavaScript**（`# template language: javascript`，`%< %>` / `%<= %>`，QJSEngine；模块 wbrandom/wbrotation/wbvector2-3/wbgeometry/wbutility/wbfile；`nonDeterministic`、`indirectFieldAccess` 标签）。**Lua 已于 R2025a 移除**。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/proto-definition.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/javascript-procedural-proto.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/changelog-r2025.md>
- **CAD / 网格导入格式**：`Mesh` 支持 **STL / OBJ / DAE(Collada)**（可作 boundingObject）；`CadShape` 仅 **DAE / OBJ**（自带外观）；FBX 仅经 `Skin` 使用。（几何节点另有 Box/Capsule/Cylinder/Sphere/Plane/ElevationGrid/IndexedFaceSet/PointSet/Group/Transform。）
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/mesh.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/cadshape.md>
- **URDF / Xacro 导入：有，但通过 ROS 2 侧工具**：`webots_ros2_importer` 提供 `urdf2proto` / `xacro2proto`，把 URDF/Xacro 转为 PROTO；独立转换器 `urdf2webots`（Cyberbotics 官方仓库）。核心参考手册中**未**记载 URDF 导入页（未查证为核心功能）。
  <https://docs.ros.org/en/ros2_packages/kilted/api/webots_ros2_importer/> ｜ <https://cyberbotics.com/>
- **关节类型**：`HingeJoint`、`SliderJoint`、`BallJoint`(3-DOF)、`Hinge2Joint`、`Track`+`TrackWheel`；参数节点 `JointParameters`(`position`、`axis`、`minStop`、`maxStop`、`springConstant`、`dampingConstant`、**`staticFriction`**)、`HingeJointParameters`(`anchor`、`suspensionSpringConstant`、`suspensionDampingConstant`、`suspensionAxis`、`stopERP`、`stopCFM`)。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/jointparameters.md>
- **电机 / 执行器**：抽象 `Motor` 字段 `acceleration`(-1)、`consumptionFactor`(10)、**`controlPID`(10 0 0)**、`minPosition`/`maxPosition`、`maxVelocity`(10)、**`multiplier`**、`sound`；`RotationalMotor.maxTorque`(默认 10)、`LinearMotor.maxForce`(默认 10)。控制模式：位置 `wb_motor_set_position`、速度（position=INFINITY + `wb_motor_set_velocity`）、力/力矩 `wb_motor_set_force/torque`（绕过 PID）；另有 `set_acceleration`、`set_control_pid`、`set_available_force/torque`。
  ⚠️ **没有 `gear` 字段**：减速比用 `multiplier` + 命名 “`motor::specifier`” 的耦合电机（差速）建模。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/motor.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/rotationalmotor.md>
- **摩擦**：关节侧只有 `JointParameters.staticFriction`（无 dynamicFriction 字段）；接触侧 `ContactProperties` 提供 `coulombFriction`（1–4 值，可非对称）、`frictionRotation`、`rollingFriction`、`bounce`、`bounceVelocity`、`forceDependentSlip`、`softERP`、`softCFM`、`maxContactJoints`；`Brake` 叠加关节阻尼。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/contactproperties.md>

## 7. 算法生态：ROS 2 / MoveIt / 导航 SLAM / 语言 / RL

- **ROS 2（`webots_ros2`，Apache-2.0，官方维护 MAINTAINED）**：当前发布版 **2025.0.1**，覆盖 humble / jazzy / kilted / rolling（Jazzy 支持于 2024-08 加入；Foxy、Galactic 已弃）。共 **14 个包**：`webots_ros2`、`_control`、`_crazyflie`、`_driver`、`_epuck`、`_husarion`、`_importer`、`_mavic`、`_msgs`、`_tesla`、`_tests`、`_tiago`、`_turtlebot`、`_universal_robot`。driver 可**自动从 Webots 机器人模型生成 ROS 2 接口**，并支持 URDF 配置与 pluginlib 扩展。
  <https://index.ros.org/p/webots_ros2/> ｜ <https://docs.ros.org/en/ros2_packages/rolling/api/webots_ros2_driver/>
- **ROS 1 支持已移除**：R2025a cleanup 明确 “**Remove ROS (1) support**”；旧 `webots_ros`（catkin，lunar，2.0.4）最后更新停留在 2019。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/changelog-r2025.md> ｜ <https://index.ros.org/p/webots_ros/>
- **MoveIt 2：有可运行示例（UR5e）**，仓库内含 `moveit_ur5e.srdf`（group `ur5e_arm`）、`moveit_controllers.yaml`、`moveit_kinematics.yaml`、`moveit_movegroup.yaml`、`launch/robot_launch/robot_moveit_nodes_launch.py`；但 MoveIt2 **不是 `webots_ros2_universal_robot` 的硬依赖**（包依赖列表中无 moveit2），属独立 demo。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots_ros2@master/webots_ros2_universal_robot/resource/moveit_ur5e.srdf> ｜ <https://docs.ros.org/en/ros2_packages/rolling/api/webots_ros2_universal_robot/>
- **导航 / SLAM 示例：有**——Navigation2（turtlebot、tiago、epuck 的 `nav2_params.yaml`）、Cartographer 与 slam_toolbox（TIAGo）、以及测试 `test_system_turtlebot_tutorial_navigation.py` / `..._slam.py`。
  <https://docs.ros.org/en/ros2_packages/rolling/api/webots_ros2/__CHANGELOG.html> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots_ros2@master/webots_ros2_tiago/resource/slam_toolbox_params.yaml>
- **控制器语言**：**C、C++、Java、Python（≥3.8）、MATLAB**（MATLAB 需 64 位 ≥2015b 且需许可证）；C 是事实标准（约 200 个函数），C++ 封装 C，Java 由 SWIG 生成。控制循环固定为 `wb_robot_init(); while (wb_robot_step(ms) != -1) {...} wb_robot_cleanup();`。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/programming-fundamentals.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/controller-programming.md>
- **Extern 控制器**：`Robot.controller` 设为 `"<extern>"`，再用 `$WEBOTS_HOME/webots-controller` 启动，支持 `--protocol=ipc|tcp`、`--ip-address`、`--port`、`--robot-name`，可跨机 TCP。其他语言（Lisp/LabVIEW 等）需自建 TCP/IP 协议（自带 `khepera_tcpip.wbt` 示例）。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/running-extern-robot-controllers.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/interfacing-webots-to-third-party-software-with-tcp-ip.md>
- **强化学习：无官方 Gym/RL 接口**。官方仅文档化“数值优化方法”（系统化/随机搜索、遗传算法、PSO、模拟退火，经 Supervisor 实现）。社区最知名的是 **deepbots**（Python 3，GPL-3.0，274★，另有配套 deepworlds），以及用户自行接 Stable-Baselines3。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/using-numerical-optimization-methods.md> ｜ <https://github.com/aidudezzz/deepbots> ｜ <https://deepbots.readthedocs.io/en/latest/>

## 8. 仿真能力：多机 / 并行 / GPU / 录制 / 状态

- **单世界多机器人：支持**。每个 `Robot` 节点自带 `controller`(+`controllerArgs`)；文档明示“两个机器人 → 三个进程（Webots + 2 个控制器）”。**并行多实例**：`--port`（默认 1234，多实例端口依次递增）+ extern launcher 的 `--port`/`--robot-name` 定向连接；webots.cloud 的 session server 会把会话分配到负载最低的 simulation server。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/controller-programming.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/starting-webots.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/session-server.md>
- **GPU / 渲染引擎**：渲染为自研 **wren**（OpenGL ≥3.3）；Lidar 与 RangeFinder 的深度由 OpenGL 深度缓冲生成 → **感知是 GPU 加速的**；**物理为 CPU 上的 ODE**（未见 GPU 物理说明）。支持的显卡要求 NVIDIA/AMD，明确不推荐 Intel 核显。
  <https://cyberbotics.com/> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/system-requirements.md>
- **域随机化（domain randomization）：官方无专门功能文档 → 未查证**。可用手段仅为 `WorldInfo.randomSeed = -1`（不可复现）、PROTO `nonDeterministic` 标签、以及 Supervisor 运行时改参数。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/worldinfo.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/programming-fundamentals.md>
- **时间/录制/导出**：`wb_supervisor_movie_start_recording(...)` 录制 **.mp4（仅 MPEG-4/AVC）**；`wb_supervisor_animation_start_recording(...)` 导出 **.html（W3D 动画）**；`wb_supervisor_export_image` 导出主窗口 JPEG；`wb_camera_save_image`、`wb_camera_recognition_save_segmentation_image`、`Display.imageSave` 导出图像。**没有内置 CSV 数据导出**（全部已核对文档中无 CSV 功能，需在控制器里自行写文件）。**回放** = 播放录制的影片/动画，或 reset 重跑。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/supervisor.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/camera.md>
- **状态保存/恢复**：`wb_supervisor_world_save` / `world_load` / `world_reload`、`simulation_reset`、`simulation_reset_physics`、`node_reset_physics`、`simulation_set_mode`、`simulation_quit`（无完整“快照回滚”语义，属重置/存档世界文件级别）。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/supervisor.md>

## 9. GUI 与交互 / 本地化 / 脚本语言

- **界面**：8 个菜单（File/Edit/View/Simulation/Build/Overlays/Tools/Help）；**场景树**支持字段**就地编辑**（Enter 应用、↑/↓ 调数值、Space 切布尔，3D 实时更新）、`IMPORTABLE EXTERNPROTO` 面板、右键启动机器人窗口/控制器；**3D 视图**支持轴对齐平移/旋转手柄、Alt+拖拽施加**力/力矩**、Follow Object、正交/透视、Plain/Wireframe；内置**文本编辑器**（控制器与 PROTO，带自动补全）、**Robot Window 插件**（HTML/JS）；Tools 菜单含 3D View、Scene Tree、Text Editor、Documentation、Edit Physics Plugin、Preferences。**完整快捷键表未查证**（文档无快捷键页，仅上述场景树/3D 视图操作与 Blender 风格鼠标模式）。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/the-user-interface.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/the-scene-tree.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/the-3d-window.md>
- **脚本语言**：**PROTO 过程式生成 = JavaScript**（Lua 已移除）；**控制器 = C / C++ / Java / Python / MATLAB**（+ 任意语言经 TCP/IP）。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/javascript-procedural-proto.md>
- **中文界面：有**。官方页写明 “Webots is already translated into French, German, Spanish, **Chinese** and Japanese (and partially into Italian). However … these translations may not always be complete or accurate.”；Preferences → General → **Language** 可切换（需重启）。→ 中文 UI 存在但**不保证完整/准确**（“英文是唯一完整维护语言”属推断，官方无此原话）。**中文文档/中文手册：未查证**。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/translating-webots-to-your-own-language.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/preferences.md>

## 10. 可视化质量 / 图像与视频导出 / 多视口

- **渲染**：自研 wren，OpenGL ≥3.3；`PBRAppearance` = Lambertian 漫反射 + Cook-Torrance 高光 + Fresnel-Schlick GGX + **IBL**（`IBLStrength`）+ normal/occlusion/emissive 贴图；HDR/辐照度立方体贴图背景；**GTAO 环境光遮蔽**、SMAA 1x 抗锯齿、bloom、镜头光晕、曝光、运动模糊、阴影开关、相机 `noise`/`noiseMaskUrl`。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/pbrappearance.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/background.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/preferences.md>
- **多视口 / 相机叠加**：`Overlays` 菜单把 Camera（品红）/ Display（青）/ RangeFinder（黄）以可移动可缩放浮层叠加在 3D 视图上，双击可**弹出独立窗口**。（⚠️ `Viewpoint` 参考页**没有** `overlays` 字段——若存在隐藏字段则**未查证**。）
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/the-3d-window.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/display.md>
- **深度/分割图像导出：可**——`wb_camera_save_image`（彩色图）、`wb_camera_recognition_save_segmentation_image`（分割真值图）、RangeFinder 以浮点数组读深度、`wb_supervisor_export_image`（主窗口 JPEG）。**视频导出**：`wb_supervisor_movie_start_recording` → .mp4（H.264，Linux 需 ffmpeg）、`wb_supervisor_animation_start_recording` → HTML 动画，另可 Web 流式。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/camera.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/supervisor.md>

## 11. 部署：headless / Web / Docker / 商用再分发

- **命令行选项（仅 `docs/guide/starting-webots.md` 记载）**：`--batch`（阻止阻塞式弹窗）、`--minimize`（启动最小化，且**自动使用 Fast 模式**）、`--no-rendering`（禁用主 3D 视图渲染）、`--mode=<pause|realtime|fast>`、`--stdout`/`--stderr`（把控制器输出转到终端）、`--port`（默认 1234）、`--log-performance=<file>[,<steps>]`、`--sysinfo`、`--version`、`--help`、`--clear-cache`、`--stream[=w3d|mjpeg]`、`--extern-urls`、`--heartbeat[=time]`、`convert`(PROTO→URDF/WBO/WRL)。
  ⚠️ **不存在 `--extern` 选项**（extern 用 `Robot.controller "<extern>"` + `webots-controller` 启动器）。
- **必须能拿到 X11 连接**：官方明言无法把图形输出重定向到另一台机器，**headless 靠虚拟帧缓冲**。官方给出的服务器/CI 命令：
  `xvfb-run --auto-servernum webots --mode=fast --no-rendering --stdout --stderr --minimize --batch /path/to/world`
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/starting-webots.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/installation-procedure.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/starting-webots-remotely-ssh.md>
- **Docker：官方镜像有** —— `cyberbotics/webots`（Docker Hub，基于 Ubuntu 22.04，内置 Xvfb），标签形如 `latest`、`R2023b-ubuntu22.04`；webots.cloud 另有 `cyberbotics/webots.cloud:<major>-ubuntu22.04[-numpy]`。仓库根无 `Dockerfile`（404）。
  <https://hub.docker.com/r/cyberbotics/webots> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/installation-procedure.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/simulation-server.md>
- **Web / 远程**：`--stream` 启动流服务器，浏览器访问 `http://IP:port/index.html`，模式 `w3d`（默认，WebSocket 传 W3D+动画）或 `mjpeg`；**限制：只能观看与漫游，不能控制仿真执行或改控制器**。W3D/Web Scene 导出为 HTML5 播放器（WebGL 2，`Skin`/`Pen` 不支持，Safari 当时不支持）；Web Animation 导出 W3D+JSON（仅记录 LED.color、Material.diffuseColor/emissiveColor、TextureTransform.translation、Pose.rotation/translation、Light.color/on，节点增删不记录）。另有官方 session server + simulation server 架构（参考实现 `cyberbotics/webots-server`）。**webots.cloud** 可分享模型/仿真、举办比赛，并在 GPU 容器里跑云端仿真。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/web-streaming.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/web-scene.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/web-animation.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/webots-cloud.md>
- **闭源商业再分发：允许**（Apache 2.0 §4：可再分发源码/目标码，须附许可证、标注修改、保留版权与 NOTICE；§6 不授予商标权）。注意部分 PROTO 资产适用单独的 Webots Assets license。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/LICENSE> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/webots-license-agreement.md>

## 12. 精度 / 实时性 / 确定性

- **固定步长**：`WorldInfo.basicTimeStep` 默认 **32 ms**（最小 1 ms）、`FPS` 60；控制器用 `wb_robot_step(ms)` 推进，步长**必须是 basicTimeStep 的整数倍**；`Robot.synchronization` 默认 TRUE。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/worldinfo.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/robot.md>
- **模式与实时因子**：`pause` / `realtime` / `fast`（尽可能快跑）；界面速度计/虚拟时间可显示实时因子 >1；`--minimize` 会自动切到 Fast。R2025b 变更：“Made the timestep algorithm more consistent when running in realtime mode”。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/the-user-interface.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/changelog-r2025.md>
- **确定性：有承诺但有条件**。文档称 “As long as the sequence of function/method calls does not vary, every programming language will yield exactly the same simulation results”；但 `WorldInfo.optimalThreadCount > 1` “can result in non replicable simulations”，`randomSeed = -1` 亦为不可复现；官网宣传语为 “robust, **deterministic** and well documented”。→ **可复现性为限定条件保证，非无条件。**
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/programming-fundamentals.md> ｜ <https://cyberbotics.com/>

## 13. 社区 / 资产库 / 文档 / 发布节奏

- **资产库规模（实测计数，master@2026-09-21）**：仓库内共 **1,045 个 `.proto`**；分布：`projects/objects` 310、`projects/robots` 256、`projects/vehicles` 126、`projects/appearances` 68、`projects/devices` 32、`projects/humans` 21，另有 furniture 39 / building 46 / animal 8 / floor 11 等关键词命中。官方资产统一在 **webots.cloud/proto** 按 keyword 浏览与贡献（robot/vehicle/actuator/sensor/joint/appearance 等类别）；R2025a 的整包资产缓存 zip 约 **693 MB**。
  <https://ungh.cc/repos/cyberbotics/webots/files/master> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/assets.md> ｜ <https://webots.cloud/proto>
- **文档质量**：完整 Webots User Guide + Reference Manual（每个 API 带 C/C++/Java/Python/MATLAB 标签页）、教程 1–8、样例与 FAQ（FAQ 在 master 已移除，仅存于 R2022b 等旧版）；changelog 按年份归档。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/menu.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/menu.md>
- **社区渠道**：**Discord**（<https://discordapp.com/invite/nTWbN9m>，Cyberbotics 团队至少欧洲工作时间在线）、Stack Overflow `webots` 标签（官方监控）、GitHub Issues/Discussions。**没有第一方论坛（Discourse）→ 未查证**（forum.cyberbotics.com 等无法解析）。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@R2022b/docs/guide/general-faq.md> ｜ <https://cyberbotics.com/>
- **GitHub 星标（2026-09 快照）**：`cyberbotics/webots` **4,647★ / 2,062 forks / 79 watchers / 229 open issues**（Apache-2.0，创建于 2018-11-05）；`cyberbotics/webots_ros2` 546★。
  <https://ungh.cc/repos/cyberbotics/webots> ｜ <https://api.github.com/repos/cyberbotics/webots_ros2>
- **发布节奏（官方 changelog 日期）**：R2018a 2017-12-20、R2018b 2018-07-05、**R2019a 2018-12-17（首个 Apache 2.0 版）**、R2019b 2019-06-25、R2020a 2019-12-18、R2020b 2020-07-29、R2021a 2020-12-15、R2021b 2021-07-16、R2022a 2021-12-21、R2022b 2022-09-13、R2023a 2022-11-29、R2023b 2023-06-28、**R2025a 2025-01-31**。→ 历史节奏约**每年 2 个版本**；**但完全跳过了 “R2024”**（`changelog-r2024.md` 不存在，changelog 索引与 GitHub Releases 均无 R2024），R2023b→R2025a 间隔约 19 个月，**R2025b 至今未发**（>19 个月无稳定版，仅 nightly）。
  <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/changelog.md> ｜ <https://ungh.cc/repos/cyberbotics/webots/releases>

---

## 对提问中若干前提的更正（均已核实）

| 常见说法 | 事实 |
|---|---|
| Camera 有 `recognitionSegmentation` 字段 | ❌ Camera 只有 `recognition`；分割开关是 **`Recognition.segmentation`**（`repo/resources/nodes/Camera.wrl`） |
| Camera/Lidar/**GPS**/**IMU** 都有 `noise` 字段 | ⚠️ Camera/Lidar/RangeFinder/InertialUnit/PositionSensor 有 `noise`；**GPS 用 `accuracy`+`noiseCorrelation`+`speedNoise`**，**Accelerometer/Gyro 只有 `resolution`**，DistanceSensor/LightSensor 靠 `lookupTable` 第 3 列 |
| Webots 支持 ODE/Newton 等引擎可选 | ❌ **只有 ODE 分支**，无引擎选择字段，无 Newton/Bullet/PhysX/MuJoCo 文档 |
| 物理插件用 `wb_physics_*` API | ❌ 回调是 `webots_physics_init/step/step_end/collide/cleanup`，工具是 `dWebots*` |
| 有 `--extern` 启动参数 | ❌ 只有 `--extern-urls`；extern 靠 `Robot.controller "<extern>"` + `webots-controller` |
| 最新版是 R2025b | ❌ 最新**正式版仍为 R2025a**（2025-01）；R2025b 仅在 nightly 中 |
| Webots 能做 CSV 数据导出 | ❌ 无内置 CSV 导出，需控制器自行写文件 |
| MoveIt 是 webots_ros2 的集成依赖 | ⚠️ 有 UR5e MoveIt 2 demo 与配置文件，但非包依赖（独立 demo） |

---

## Webots 明显强于他人的 3 项

1. **许可证 + 全栈一体化**：Apache 2.0，官方明确允许“任何目的、含商业应用”，且物理、PBR 渲染、完整传感器套件、控制器 API、ROS 2、Docker/CI 工作流都在**同一个官方发行包**里——不存在 Gazebo/Ignition 那种“引擎与插件版本矩阵”问题；同时仍是商业公司（Cyberbotics）长期维护、1998 年至今连续开发。
   证据：<https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/webots-license-agreement.md> ｜ <https://cyberbotics.com/>（“ODE fork + wren 渲染引擎 + Qt GUI”一体；Cyberbotics 自 1998 年持续维护）
2. **开箱即得的高保真地面真值感知**：`Recognition` 节点直接给出被识别物体的 id（可用 Supervisor 换回节点）、相对相机位姿、尺寸、像素包围盒、颜色与 `model`，并能直出**分割真值图**（`wb_camera_recognition_get_segmentation_image`）；配合各传感器细粒度噪声字段（Camera `noise`[0,1]、Lidar `noise`、GPS `accuracy`+`noiseCorrelation`、Receiver `signalStrengthNoise`）非常适合感知算法、数据集生成与 RL 训练。
   证据：<https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/recognition.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/camera.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/gps.md>
3. **可移植的桌面应用 + 极轻量的 headless/CI/Web 部署路径**：一个安装包覆盖 Windows 10/11、Ubuntu 22.04/24.04、macOS 12–14（**Apple Silicon 原生**，官方明确 “Apple Silicon & Intel”），服务器侧只需 `xvfb-run … --batch --minimize --no-rendering --mode=fast`，并有官方 Docker 镜像（内置 Xvfb）与 webots.cloud/Web Streaming/W3D 在线分享链路。
   证据：<https://ungh.cc/repos/cyberbotics/webots/releases/latest>（macOS “Apple Silicon & Intel”）｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/installation-procedure.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/webots-cloud.md>

## 已知短板 2~3 项

1. **物理引擎单一、缺少软体**：只有官方 ODE 分支，文档中不存在 Newton/Bullet/PhysX/MuJoCo，也没有引擎切换字段；`Muscle`/`Skin` 仅为图形，Soft-body/FEM **未查证存在**；关节摩擦只有 `staticFriction`（无 dynamicFriction 字段），接触参数靠 `ContactProperties` 手调。对需要多引擎交叉验证或可变形体仿真的用户是硬约束。
   证据：<https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/ode-open-dynamics-engine.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/physics.md> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/muscle.md>
2. **发布节奏停滞 + 跳版**：历史上约半年一个版本，但 **R2024 被整年跳过**（无 changelog、无 release），R2023b(2023-06) → R2025a(2025-01) 间隔 19 个月；而 **R2025b 到 2026-09 仍未发布**（changelog 无 “Released on”，GitHub 无该 tag，只有 nightly），Homebrew / APT / GitHub latest 全部停在 2025a。对需要稳定版跟进 ROS 2 新发行版（如 kilted/rolling 后续）的项目存在风险。
   证据：<https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/changelog.md> ｜ <https://ungh.cc/repos/cyberbotics/webots/releases/latest> ｜ <https://formulae.brew.sh/cask/webots>
3. **生态空缺项较多**：无内置 CSV/数据导出；**无第一方 Gym/RL 接口**（只能靠社区 deepbots，GPL-3.0）；**ROS 1 支持已在 R2025a 移除**（旧 `webots_ros` 停在 2019）；Web 流式**只读、不能控制仿真**；`Viewpoint` 参考中无 `overlays` 字段；第一方论坛缺失（仅 Discord/SO）；Microphone、Radio 等节点在引擎内存在但**未文档化**。
   证据：<https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/changelog-r2025.md>（Remove ROS (1) support）｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/guide/web-streaming.md> ｜ <https://github.com/aidudezzz/deepbots> ｜ <https://gcore.jsdelivr.net/gh/cyberbotics/webots@master/docs/reference/supervisor.md>（无 CSV）

---

### 仍未查证（明确列出）

- 域随机化是否有官方专门机制（文档无对应页面）。
- 软体/FEM 物理是否存在（仅见图形化 Muscle/Skin）。
- Microphone、Radio 节点的实际运行时能力（引擎有节点，参考手册无页）。
- Webots 文档是否有官方中文版本；中文 UI 翻译的完整度。
- 完整键盘快捷键清单（文档无快捷键页）。
- `WEBOTS_INSTANCE_PATH` 环境变量（多实例文档中未出现）。
- 官方 Webots 论坛（Discourse）是否存在。
- 精确的物理求解器精度/误差指标（官方未给定量对比数据）。
