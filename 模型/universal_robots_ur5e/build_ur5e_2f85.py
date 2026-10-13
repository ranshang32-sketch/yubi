"""
build_ur5e_2f85.py —— 用 MuJoCo 官方模型组合 API（MjSpec.attach）造一台"带真实夹爪的机械臂"

组合：
    Universal Robots UR5e（真实量产六轴工业臂）  ← ../../../03_模型库/menagerie/universal_robots_ur5e/ur5e.xml
  + Robotiq 2F-85（真实量产二指自适应夹爪）      ← ../../../03_模型库/menagerie/robotiq_2f85/2f85.xml
  挂载点：UR5e 的 attachment_site（法兰坐标系；局部 +z = 工具外伸方向）

产物（都写在本目录，可直接用 mujoco-simulate / mjpython ... viewer 打开）：
    ur5e_2f85.xml          组合后的真实机器人模型（28 个网格：20 个 UR5e OBJ + 8 个 2F-85 STL）
    grasp_scene_2f85.xml   抓取场景：+ 地面 + 工作台 + 50mm 工件 + 放置区 + 灯光 + 相机

运行：python build_ur5e_2f85.py     （在哪个目录执行都行，路径自适应）

三个进阶知识点（都是这次实跑踩出来的）：
  1. 子模型的 <option> 与父模型冲突时"父模型赢"（会打印 Attach conflict 警告）。2F-85 的
     cone=elliptic、impratio=10 是它抓取稳定的关键参数，必须显式搬到父模型上，否则抓取会打滑；
  2. 组合后只保留一个 meshdir（父模型的 "assets"），所以子模型的网格路径要重写成
     "../../robotiq_2f85/assets/xxx.stl"（相对 UR5e 模型目录）；两个模型的网格文件名不重名，
     因此可以共用 meshdir；
  3. 组合模型必须和 ur5e.xml 放在同一目录：含 include 的模型/场景在别处加载时，
     meshdir 会按主文件所在目录解析（教程 FAQ Q1），换目录就会报 assets 找不到。
"""
import os
import mujoco

HERE = os.path.dirname(os.path.abspath(__file__))              # .../03_模型库/menagerie/universal_robots_ur5e
MENAGERIE = os.path.abspath(os.path.join(HERE, ".."))          # .../03_模型库/menagerie
UR5E_XML = os.path.join(HERE, "ur5e.xml")
GRIPPER_XML = os.path.join(MENAGERIE, "robotiq_2f85", "2f85.xml")

ROBOT_OUT = os.path.join(HERE, "ur5e_2f85.xml")
SCENE_OUT = os.path.join(HERE, "grasp_scene_2f85.xml")

for f in (UR5E_XML, GRIPPER_XML):
    if not os.path.exists(f):
        raise SystemExit(f"缺少模型文件 {f}\n（menagerie 是 sparse-checkout，先执行：\n"
                         f"  cd {MENAGERIE} && git sparse-checkout set universal_robots_ur5e robotiq_2f85)")

# ---------------- 1. 读入两个官方模型 ----------------
robot = mujoco.MjSpec.from_file(UR5E_XML)         # 父：UR5e（网格 meshdir="assets"）
gripper = mujoco.MjSpec.from_file(GRIPPER_XML)    # 子：Robotiq 2F-85

# ---------------- 2. 子模型网格路径重写（共用父模型的 meshdir） ----------------
for mesh in gripper.meshes:                       # 从 UR5e 目录看，2F-85 的资产在 ../../robotiq_2f85/assets
    mesh.file = "../../robotiq_2f85/assets/" + mesh.file

# ---------------- 3. 搬运求解器参数（否则被父模型默认值覆盖） ----------------
robot.option.cone = gripper.option.cone           # elliptic 椭圆摩擦锥
robot.option.impratio = gripper.option.impratio   # 10

# ---------------- 4. 把夹爪挂到法兰上（自动加前缀，避免关节/网格重名） ----------------
robot.attach(gripper, prefix="gripper_", site=robot.site("attachment_site"))

# ---------------- 5. 编译 + 保存 ----------------
model = robot.compile()
robot.to_file(ROBOT_OUT)
print("【组合完成】UR5e + Robotiq 2F-85")
print(f"  关节 {model.njnt} 个（6 臂关节 + 8 个夹爪四连杆关节）")
print(f"  执行器 {model.nu} 个：{', '.join(model.actuator(i).name for i in range(model.nu))}")
print(f"  夹爪指令 ctrlrange = {model.actuator('gripper_fingers_actuator').ctrlrange}（0=张开 85mm，255=闭合）")
print(f"  nq={model.nq} nv={model.nv} nmesh={model.nmesh}")
print(f"  → {ROBOT_OUT}")

# ---------------- 6. 生成抓取场景 ----------------
SCENE = '''<mujoco model="ur5e_2f85_grasp">
  <!--
    grasp_scene_2f85.xml —— UR5e + Robotiq 2F-85 抓取场景（进阶教程 09 用）
    由 build_ur5e_2f85.py 生成。含 include 的场景必须与模型同目录、用 from_xml_path 加载（教程 FAQ Q1）。
  -->
  <include file="ur5e_2f85.xml"/>

  <visual>
    <headlight diffuse="0.6 0.6 0.6" ambient="0.35 0.35 0.35" specular="0.1 0.1 0.1"/>
    <global azimuth="140" elevation="-20" offwidth="960" offheight="720"/>
  </visual>

  <worldbody>
    <light name="key_light" pos="0.6 -1.2 1.8" dir="0 0.4 -1" diffuse="0.8 0.8 0.8"/>
    <light name="fill_light" pos="-1.0 0.8 1.5" dir="0.4 -0.4 -1" diffuse="0.35 0.35 0.35"/>
    <geom name="floor" type="plane" size="2 2 0.05" rgba="0.30 0.33 0.38 1"/>

    <!-- 工作台：台面 z = 0.22 m -->
    <body name="worktable" pos="0.45 0 0.11">
      <geom name="table_top" type="box" size="0.20 0.25 0.11" rgba="0.62 0.58 0.52 1"
            friction="1.0 0.005 0.0001"/>
    </body>

    <!-- 待抓工件：50mm 立方体（2F-85 行程 85mm，留出进出间隙），自由体 -->
    <body name="part" pos="0.38 -0.06 0.245">
      <freejoint name="part_free"/>
      <geom name="part_geom" type="box" size="0.025 0.025 0.025" density="900"
            friction="1.0 0.01 0.0001" condim="4" rgba="0.15 0.45 0.85 1"/>
    </body>

    <!-- 放置区标记：纯视觉（contype=0 不参与碰撞） -->
    <geom name="place_pad" type="box" size="0.045 0.045 0.0015" pos="0.50 0.06 0.2215"
          contype="0" conaffinity="0" rgba="0.10 0.85 0.30 0.45"/>

    <!-- 演示相机（离屏录 GIF 用） -->
    <camera name="demo_cam" pos="1.166 -0.706 0.694" xyaxes="0.7071 0.7071 0 -0.2534 0.2534 0.9336"/>
  </worldbody>
</mujoco>
'''
with open(SCENE_OUT, "w", encoding="utf-8") as f:
    f.write(SCENE)

# ---------------- 7. 立刻回读验证 ----------------
m2 = mujoco.MjModel.from_xml_path(ROBOT_OUT)
print(f"  回读 ur5e_2f85.xml 成功：nq={m2.nq} nu={m2.nu} nmesh={m2.nmesh}")
m3 = mujoco.MjModel.from_xml_path(SCENE_OUT)
print(f"  回读 grasp_scene_2f85.xml 成功：nbody={m3.nbody}（工件质量 {float(m3.body_mass[mujoco.mj_name2id(m3, mujoco.mjtObj.mjOBJ_BODY, 'part')]):.3f} kg）")
print(f"  → {SCENE_OUT}")
