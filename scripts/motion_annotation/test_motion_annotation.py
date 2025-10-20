import argparse

import numpy as np
from scipy.spatial.transform import Rotation as R

from robocoin_dataset.annotation.motion_annotation.compute_lerobot_eef import LerobotFkSolver
from robocoin_dataset.annotation.motion_annotation.configs.agilex_cobot_magic import (
    AgilexCobotMagicConfig,
    AgilexCobotMagicWithoutEEFConfig,
)
from robocoin_dataset.annotation.motion_annotation.configs.galaxea_ri_lite import (
    GalaxeaR1LiteConfig,
)
from robocoin_dataset.annotation.motion_annotation.configs.realman_rmc_aidal_config import (
    RealmanRmcAidalSimFkConfig,
)
from robocoin_dataset.annotation.motion_annotation.configs.unitree_g1 import (
    UnitreeG129DofConfig,
)


def euler_to_quaternion(euler_batch: np.ndarray) -> np.ndarray:
    """
    将一批欧拉角 (N, 3) 转换为四元数 (N, 4)
    euler_batch: np.array, shape (..., 3), 最后一维是 [rx, ry, rz] 弧度
    返回: 四元数 (..., 4)，格式为 [x, y, z, w]
    """
    # 展平以便处理
    original_shape = euler_batch.shape
    euler_flat = euler_batch.reshape(-1, 3)  # (M, 3)

    # 转换：注意顺序是 'xyz'
    rot = R.from_euler("xyz", euler_flat, degrees=False)
    quat_flat = rot.as_quat()  # (M, 4) → [x, y, z, w]

    return quat_flat.reshape(*original_shape[:-1], 4)


def get_pos_in_list(data_list: list[np.ndarray]) -> list[np.ndarray]:
    new_list = []

    for arr in data_list:
        # 提取各部分
        pos1 = arr[0:3]  # (T, 3)
        pos2 = arr[6:9]  # (T, 3)

        new_arr = np.concatenate([pos1, pos2], axis=0)  # (T, 14)

        new_list.append(new_arr)

    return new_list


def get_quat_in_list(data_list: list[np.ndarray]) -> list[np.ndarray]:
    new_list = []

    for arr in data_list:
        # 提取各部分
        euler1 = arr[3:6]  # (T, 3)
        euler2 = arr[9:12]  # (T, 3)

        # 转换为四元数
        quat1 = euler_to_quaternion(euler1)  # (T, 4)
        quat2 = euler_to_quaternion(euler2)  # (T, 4)

        # 拼接成新数组：[pos1(3), quat1(4), pos2(3), quat2(4)] → (T, 14)
        # 注意：你原始说 0-3 是位置，但 0:3 是 3 维，所以假设是 0:3, 3:6 等
        new_arr = np.concatenate([quat1, quat2], axis=0)  # (T, 14)

        new_list.append(new_arr)

    return new_list


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("repo_path", type=str)

    parser.add_argument("frequency", type=int)

    args = parser.parse_args()

    config = RealmanRmcAidalSimFkConfig()
    config = AgilexCobotMagicConfig()
    config = AgilexCobotMagicWithoutEEFConfig()
    config = GalaxeaR1LiteConfig()
    config = UnitreeG129DofConfig()
    config = RealmanRmcAidalSimFkConfig()

    solver = LerobotFkSolver(config, args.repo_path)

    solver.start_viewer()
    solver._load

    episode_num = solver.get_episode_num()

    eefpos_and_eefeuler = solver.get_episode_eefpos_and_eefeuler(0, is_state=True)
    fk_result = solver.episode_fk(0, is_state=False)
    print(fk_result[0])

    # eefpos = get_pos_in_list(eefpos_and_eefeuler)
    # fk_result_pos = get_pos_in_list(fk_result)

    # delta_eef_pos_data = [data - eefpos[0] for data in eefpos]
    # delta_fk_pos_data = [data - fk_result_pos[0] for data in fk_result_pos]

    # max_error = 0
    # for data1, data2 in zip(delta_eef_pos_data, delta_fk_pos_data):
    #     error = data1 - data2
    #     if max_error < np.max(np.abs(error)):
    #         max_error = np.max(np.abs(error))
    #     max_error = np.max(np.abs(error))
    # print(max_error)

    # eefquat = get_quat_in_list(eefpos_and_eefeuler)
    # fk_result_quat = get_quat_in_list(fk_result)

    # delta_eef_quat_data = [data - eefquat[0] for data in eefquat]
    # delta_fk_quat_data = [data - fk_result_quat[0] for data in fk_result_quat]

    # for data1, data2 in zip(eefquat, fk_result_quat):
    #     print(data1)
    #     print(data2)
    #     print("\n")
    solver.close_viewer()


"""usage:
python scripts/motion_annotation/test_motion_annotation.py /mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_wipe_table/ 30
"""
