from dataclasses import dataclass
from pathlib import Path

import mujoco
import mujoco.viewer
import numpy as np
from scipy.spatial.transform import Rotation as R


@dataclass
class JointsConfig:
    joints_dict: dict[str, str] | None = None
    eef_pos_names: dict[str, str | None] | None = None
    eef_euler_names: dict[str, str | None] | None = None


class MujocoReplay:
    def __init__(
        self,
        mjcf_file_path: str | Path,
        site_names: list[str],
    ) -> None:
        self.mjcf_file_path = Path(mjcf_file_path).expanduser().resolve()
        self.site_names = site_names
        try:
            self.model = mujoco.MjModel.from_xml_path(str(self.mjcf_file_path))
            self.data = mujoco.MjData(self.model)
            self.site_ids = [self.model.site(name).id for name in self.site_names]
            self.viewer = None
        except Exception as e:
            raise Exception(f"Error loading MJCF model: {e}")

    def start_viewer(self) -> None:
        if self.viewer is None:
            self.viewer = mujoco.viewer.launch_passive(self.model, self.data)
            self.viewer.sync()

    def get_joint_names(self) -> list[str]:
        njoints = self.model.njnt
        return [self.model.joint(i).name for i in range(njoints)]

    def get_joint_id(self, name: str) -> int:
        return self.model.joint(name).id

    def fk(self, qpos_dict: dict[int, float]) -> np.ndarray:
        try:
            for joint_id, qpos in qpos_dict.items():
                addr = self.model.jnt_qposadr[joint_id]
                self.data.qpos[addr] = qpos

            mujoco.mj_forward(self.model, self.data)
            if self.viewer is not None:
                self.viewer.sync()
            results = np.array([], dtype=np.float32)
            for site_id in self.site_ids:
                site_pos = self.data.site_xpos[site_id]
                site_rot = self.data.site_xmat[site_id]
                site_rot_euler = R.from_matrix(site_rot.reshape(3, 3)).as_euler(
                    "xyz", degrees=False
                )
                results = np.concatenate([results, site_pos, site_rot_euler], axis=0)
        except Exception as e:
            raise Exception(f"Error in FK computation: {e}")

        return results

    def close_viewer(self) -> None:
        if self.viewer is not None:
            self.viewer.close()
        self.viewer = None


# def mujoco_fk(
#     mjcf_file_path: str | Path, site_names: list[str], qpos: list[float] | np.ndarray
# ) -> tuple[np.ndarray, np.ndarray]:
#     mjcf_file_path = Path(mjcf_file_path).expanduser().resolve()
#     model = mujoco.MjModel.from_xml_path(str(mjcf_file_path))
#     data = mujoco.MjData(model)
#     data.qpos[: len(qpos)] = qpos
#     mujoco.mj_forward(model, data)
#     site_ids = [model.site(name).id for name in site_names]

#     site_id = model.site(site_name).id
#     site_pos = data.site_xpos[site_id]
#     site_rot = data.site_xmat[site_id]
#     site_rot_euler = R.from_matrix(site_rot.reshape(3, 3)).as_euler("xyz", degrees=False)
#     return site_pos, site_rot_euler


# def normalize_angle(angle: float) -> float:
#     """
#     将角度归一化到 [0, 2*pi] 区间
#     :param angle: 输入的角度（弧度制）
#     :return: 归一化后的角度
#     """
#     return angle % (2 * np.pi)


# with mujoco.viewer.launch_passive(model, data) as viewer:
#     # 初始同步

#     parquet_data[0]
#     init_eef_pos = parquet_data[0][eefpos_from_idx:eefpos_to_idx]
#     for idx, frame_data in enumerate(parquet_data):
#         qpos = frame_data[joint_from_idx:joint_to_idx]
#         data.qpos[: len(qpos)] = qpos
#         mujoco.mj_forward(model, data)
#         viewer.sync()

#         site_pos_mj = data.site_xpos[site_id]
#         site_rot_mj = data.site_xmat[site_id]
#         site_rot_euler_mj = R.from_matrix(site_rot_mj.reshape(3, 3)).as_euler("xyz", degrees=False)

#         if idx == 0:
#             init_mj_pos_x = site_pos_mj[0]
#             init_mj_pos_y = site_pos_mj[1]
#             init_mj_pos_z = site_pos_mj[2]

#         eef_pos = frame_data[eefpos_from_idx:eefpos_to_idx]
#         eef_rot = frame_data[eefrot_from_idx:eefrot_to_idx]

#         pos_dx.append(eef_pos[0] - init_eef_pos[0])
#         pos_dy.append(eef_pos[1] - init_eef_pos[1])
#         pos_dz.append(eef_pos[2] - init_eef_pos[2])

#         rot_dx.append(normalize_angle(eef_rot[0]))
#         rot_dy.append(normalize_angle(eef_rot[1]))
#         rot_dz.append(normalize_angle(eef_rot[2]))

#         mj_pos_dx.append(site_pos_mj[0] - init_mj_pos_x)
#         mj_pos_dy.append(site_pos_mj[1] - init_mj_pos_y)
#         mj_pos_dz.append(site_pos_mj[2] - init_mj_pos_z)

#         mj_rot_dx.append(normalize_angle(site_rot_euler_mj[0]))
#         mj_rot_dy.append(normalize_angle(site_rot_euler_mj[1]))
#         mj_rot_dz.append(normalize_angle(site_rot_euler_mj[2]))

#         pos_err = site_pos_mj - eef_pos
#         rot_err = site_rot_euler_mj - eef_rot
#         time.sleep(0.03)

# 初始同步

# parquet_data[0]
# st = time.time()
# init_eef_pos = parquet_data[0][eefpos_from_idx:eefpos_to_idx]
# for idx, frame_data in enumerate(parquet_data):
#     qpos = frame_data[joint_from_idx:joint_to_idx]
#     data.qpos[: len(qpos)] = qpos
#     mujoco.mj_forward(model, data)

#     site_pos_mj = data.site_xpos[site_id]
#     site_rot_mj = data.site_xmat[site_id]
#     site_rot_euler_mj = R.from_matrix(site_rot_mj.reshape(3, 3)).as_euler("xyz", degrees=False)

#     if idx == 0:
#         init_mj_pos_x = site_pos_mj[0]
#         init_mj_pos_y = site_pos_mj[1]
#         init_mj_pos_z = site_pos_mj[2]

#     eef_pos = frame_data[eefpos_from_idx:eefpos_to_idx]
#     eef_rot = frame_data[eefrot_from_idx:eefrot_to_idx]

#     pos_dx.append(eef_pos[0] - init_eef_pos[0])
#     pos_dy.append(eef_pos[1] - init_eef_pos[1])
#     pos_dz.append(eef_pos[2] - init_eef_pos[2])

#     rot_dx.append(normalize_angle(eef_rot[0]))
#     rot_dy.append(normalize_angle(eef_rot[1]))
#     rot_dz.append(normalize_angle(eef_rot[2]))

#     mj_pos_dx.append(site_pos_mj[0] - init_mj_pos_x)
#     mj_pos_dy.append(site_pos_mj[1] - init_mj_pos_y)
#     mj_pos_dz.append(site_pos_mj[2] - init_mj_pos_z)

#     mj_rot_dx.append(normalize_angle(site_rot_euler_mj[0]))
#     mj_rot_dy.append(normalize_angle(site_rot_euler_mj[1]))
#     mj_rot_dz.append(normalize_angle(site_rot_euler_mj[2]))

#     pos_err = site_pos_mj - eef_pos
#     rot_err = site_rot_euler_mj - eef_rot

# print(f"Time: {time.time() - st}")

# # 创建时间轴（步数）
# steps = range(len(pos_dx))

# # 创建子图：2 行 1 列
# fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

# # 第一个子图：位置数据对比
# ax1.plot(steps, pos_dx, label="X Position", color="red", linewidth=1.5)
# ax1.plot(steps, pos_dy, label="Y Position", color="green", linewidth=1.5)
# ax1.plot(steps, pos_dz, label="Z Position", color="blue", linewidth=1.5)
# ax1.plot(
#     steps,
#     mj_pos_dx,
#     label="Measured X Position",
#     linestyle="--",
#     color="red",
#     alpha=0.7,
#     linewidth=1.5,
# )
# ax1.plot(
#     steps,
#     mj_pos_dy,
#     label="Measured Y Position",
#     linestyle="--",
#     color="green",
#     alpha=0.7,
#     linewidth=1.5,
# )
# ax1.plot(
#     steps,
#     mj_pos_dz,
#     label="Measured Z Position",
#     linestyle="--",
#     color="blue",
#     alpha=0.7,
#     linewidth=1.5,
# )
# ax1.set_ylabel("Position")
# ax1.set_title("Position Comparison")
# ax1.legend()
# ax1.grid(True, alpha=0.3)

# # 第二个子图：旋转数据对比
# ax2.plot(steps, rot_dx, label="Roll", color="orange", linewidth=1.5)
# ax2.plot(steps, rot_dy, label="Pitch", color="purple", linewidth=1.5)
# ax2.plot(steps, rot_dz, label="Yaw", color="brown", linewidth=1.5)
# ax2.plot(
#     steps,
#     mj_rot_dx,
#     label="Measured Roll",
#     linestyle="--",
#     color="orange",
#     alpha=0.7,
#     linewidth=1.5,
# )
# ax2.plot(
#     steps,
#     mj_rot_dy,
#     label="Measured Pitch",
#     linestyle="--",
#     color="purple",
#     alpha=0.7,
#     linewidth=1.5,
# )
# ax2.plot(
#     steps, mj_rot_dz, label="Measured Yaw", linestyle="--", color="brown", alpha=0.7, linewidth=1.5
# )
# ax2.set_xlabel("Timestep")
# ax2.set_ylabel("Rotation")
# ax2.set_title("Rotation Comparison")
# ax2.legend()
# ax2.grid(True, alpha=0.3)

# # 自动调整布局
# plt.tight_layout()

# # 显示或保存
# plt.show()
# plt.savefig("./datas/comparison_plot.png", dpi=350)


# """_summary_
# python scripts/temp/validate_mujoco_fk.py \
#     ~/work/mjcf_models/agilex_cobot_magic/aloha_v1.xml \
#     --end_effector fl_link6_site \
#     --parquet_file_path /mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_wipe_table/data/chunk-000/episode_000000.parquet \
#     --joint-from-idx 0 \
#     --joint-to-idx 6 \
#     --eefpos-from-idx 7 \
#     --eefpos-to-idx 10 \
#     --eefrot-from-idx 10 \
#     --eefrot-to-idx 13

# """
