from pathlib import Path
import logging
import numpy as np
import yaml
import importlib
import pandas as pd
from pathlib import Path

from robocoin_dataset.sim_replay.lerobot_sim_replayer import LerobotSimReplayer
from .state_action_data_processor_base import StateActionDataPostProcessorBase

logger = logging.getLogger(__name__)

class AgilexCobotDecoupledMagicProcessor(StateActionDataPostProcessorBase):
    def __init__(self, convert_path: str | Path) -> None:
        super().__init__(convert_path)
        self.replayer: LerobotSimReplayer | None = self._setup_replayer()
        self.episode_index = 0  # 默认值

    def _setup_replayer(self) -> LerobotSimReplayer | None:
        """动态加载并实例化 LerobotSimReplayer"""
        try:
            project_root = Path(__file__).resolve().parents[4]
            config_path = project_root / "scripts/sim_replay/configs/sim_replay_config_path.yaml"

            if not config_path.exists():
                logger.warning(f"Sim replay config file not found at {config_path}. Replayer will not be available.")
                return None

            with open(config_path, "r") as f:
                all_configs = yaml.safe_load(f)

            device_configs = all_configs.get("agilex_cobot_decoupled_magic", [])
            config_info = next((c for c in device_configs if c.get("version") == "default_version"), None)

            if not config_info:
                logger.warning("Config for 'agilex_cobot_decoupled_magic' with 'default_version' not found. Replayer will not be available.")
                return None

            module_name = config_info["mujoco_sim_replay_config_module"]
            class_name = config_info["mujoco_sim_replay_config_class"]

            module = importlib.import_module(module_name)
            config_class = getattr(module, class_name)
            replay_config = config_class()

            # repo_path 是 LeRobot 数据集目录
            return LerobotSimReplayer(replay_config=replay_config, repo_path=self.convert_path)

        except Exception as e:
            logger.error(f"Failed to setup LerobotSimReplayer. Reason: {e}", exc_info=True)
            return None

    def set_episode_index(self, episode_index: int):
        """设置当前处理的 episode 索引"""
        self.episode_index = episode_index

    def prepare_processing(self) -> None:
        pass

    def _swap_left_right(self, data: np.ndarray) -> np.ndarray:
        """交换前13维和后13维"""
        if data.ndim != 2 or data.shape[1] < 26:
            return data
        swapped_data = data.copy()
        left = swapped_data[:, :13].copy()
        right = swapped_data[:, 13:26].copy()
        swapped_data[:, :13] = right
        swapped_data[:, 13:26] = left
        return swapped_data

    def _scale_columns(self, data: np.ndarray) -> np.ndarray:
        """如果第7或第20列的最大值 > 0.8，则该列整体除以10"""
        scaled_data = data.copy()
        for col_idx in (6, 19):
            try:
                col_max = float(np.max(scaled_data[:, col_idx]))
                if col_max > 0.8:
                    logger.info(f"Episode {self.episode_index}: Column {col_idx} max value is {col_max} > 0.8, scaling it by dividing by 10.")
                    scaled_data[:, col_idx] = scaled_data[:, col_idx] / 10.0
            except (IndexError, ValueError) as e:
                logger.warning(f"Episode {self.episode_index}: Could not process column {col_idx}. Reason: {e}")
                continue
        return scaled_data

    def process_episode_data(self, ori_data: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """
        重写此方法以实现完整的处理逻辑：
        1. 交换 state 和 action 的左右臂数据。
        2. 根据条件缩放特定列。
        3. 使用模拟器获取EEF数据，判断是否需要撤销交换。
        """
        # 步骤 1 & 2: 初始处理 state 和 action
        processed_state = self._scale_columns(self._swap_left_right(ori_data["observation.state"]))
        processed_action = self._scale_columns(self._swap_left_right(ori_data["action"]))

        central_logger = logging.getLogger("state action data post process server")
        # 步骤 3: 调用模拟器并根据EEF距离决定是否再次交换
        if self.replayer is None:
            central_logger.warning(f"Episode {self.episode_index}: Replayer not available, skipping EEF distance check. The arm data remains swapped.")
        else:
            try:
                # 假设 replayer 已经配置好，直接调用
                self.replayer.mjcf_model.opt.gravity[2] = -9.81 # 确保重力正确
                eef_data_list_state = self.replayer.replay_episode_background(self.episode_index, is_state=True)
                
                if eef_data_list_state and len(eef_data_list_state) > 0 and eef_data_list_state[0].shape[0] >= 12:
                    eef_data = np.array(eef_data_list_state)
                    # 左臂夹爪在第7个元素(index 6)，右臂夹爪在第20个元素(index 19)
                    left_gripper = processed_state[:, 6]
                    right_gripper = processed_state[:, 19]
                    
                    gripper_distances = np.abs(left_gripper - right_gripper)
                    last_frame_gripper_distance = gripper_distances[-1]
                    mean_gripper_distance = np.mean(gripper_distances)

                    central_logger.info(f"Episode {self.episode_index}: Last frame gripper distance: {last_frame_gripper_distance:.4f}, Mean gripper distance: {mean_gripper_distance:.4f}")

                    if mean_gripper_distance < last_frame_gripper_distance:
                        central_logger.info(f"Episode {self.episode_index}: Mean gripper distance > Last frame gripper distance. Swapping arms back to original order.")
                        # 再次交换，恢复原状
                        processed_state = self._swap_left_right(processed_state)
                        processed_action = self._swap_left_right(processed_action)
                    else:
                        central_logger.info(f"Episode {self.episode_index}: Mean gripper distance <= Last frame gripper distance. Keeping the arms swapped.")
                else:
                    central_logger.warning(f"Episode {self.episode_index}: EEF data is invalid or insufficient. Skipping distance check. Data shape: {eef_data_list_state[0].shape if eef_data_list_state else 'Empty'}")

            except Exception as e:
                central_logger.error(f"Episode {self.episode_index}: Failed to get EEF data or perform distance check. Reason: {e}", exc_info=True)

        return {
            "observation.state": processed_state,
            "action": processed_action,
        }

    # 该方法将ori_state_data进行后处理，返回结果为后处理后的数据
    def process_episode_state_data(self, ori_state_data: np.ndarray) -> np.ndarray:
        # 这个方法现在由 process_episode_data 调用，逻辑已集中处理
        return ori_state_data

    # 该方法将ori_action_data进行后处理，返回结果为后处理后的数据
    def process_episode_action_data(self, ori_action_data: np.ndarray) -> np.ndarray:
        # 这个方法现在由 process_episode_data 调用，逻辑已集中处理
        return ori_action_data
    def get_modified_feature_names(self):
        return super().get_modified_feature_names()

    def get_modified_info_state_names(self) -> dict[str, str]:
        return {}

    # 该方法返回处理后的action数据名称
    def get_modified_info_action_names(self) -> dict[str, str]:
        return {}

    def get_modified_state_feature_names(self)-> list[str]:
        return [
                "left_arm_joint_1_rad",
                "left_arm_joint_2_rad",
                "left_arm_joint_3_rad",
                "left_arm_joint_4_rad",
                "left_arm_joint_5_rad",
                "left_arm_joint_6_rad",
                "left_gripper_open",
                "left_eef_pos_x_m",
                "left_eef_pos_y_m",
                "left_eef_pos_z_m",
                "left_eef_rot_euler_x_rad",
                "left_eef_rot_euler_y_rad",
                "left_eef_rot_euler_z_rad",
                "right_arm_joint_1_rad",
                "right_arm_joint_2_rad",
                "right_arm_joint_3_rad",
                "right_arm_joint_4_rad",
                "right_arm_joint_5_rad",
                "right_arm_joint_6_rad",
                "right_gripper_open",
                "right_eef_pos_x_m",
                "right_eef_pos_y_m",
                "right_eef_pos_z_m",
                "right_eef_rot_euler_x_rad",
                "right_eef_rot_euler_y_rad",
                "right_eef_rot_euler_z_rad"
            ]
    def get_modified_action_feature_names(self)-> list[str]:
        return [
                "left_arm_joint_1_rad",
                "left_arm_joint_2_rad",
                "left_arm_joint_3_rad",
                "left_arm_joint_4_rad",
                "left_arm_joint_5_rad",
                "left_arm_joint_6_rad",
                "left_gripper_open",
                "left_eef_pos_x_m",
                "left_eef_pos_y_m",
                "left_eef_pos_z_m",
                "left_eef_rot_euler_x_rad",
                "left_eef_rot_euler_y_rad",
                "left_eef_rot_euler_z_rad",
                "right_arm_joint_1_rad",
                "right_arm_joint_2_rad",
                "right_arm_joint_3_rad",
                "right_arm_joint_4_rad",
                "right_arm_joint_5_rad",
                "right_arm_joint_6_rad",
                "right_gripper_open",
                "right_eef_pos_x_m",
                "right_eef_pos_y_m",
                "right_eef_pos_z_m",
                "right_eef_rot_euler_x_rad",
                "right_eef_rot_euler_y_rad",
                "right_eef_rot_euler_z_rad"
            ]



class AgilexCobotDecoupledRealsenseMagicProcessor(StateActionDataPostProcessorBase):
    def __init__(self, convert_path: str | Path) -> None:
        super().__init__(convert_path)

    def prepare_processing(self) -> None:
        pass

    def _smooth_gripper_open_data(self, data: np.ndarray) -> np.ndarray:
        smoothed = data.copy()
        return smoothed

    # 该方法将ori_state_data进行后处理，返回结果为后处理后的数据
    def process_episode_state_data(self, ori_state_data: np.ndarray) -> np.ndarray:
        new_state_data = ori_state_data.copy()
        return new_state_data

    # 该方法将ori_action_data进行后处理，返回结果为后处理后的数据
    def process_episode_action_data(self, ori_action_data: np.ndarray) -> np.ndarray:
        new_action_data = ori_action_data.copy()
        return new_action_data
    def get_modified_feature_names(self):
        return super().get_modified_feature_names()

    def get_modified_info_state_names(self) -> dict[str, str]:
        return {}

    # 该方法返回处理后的action数据名称
    def get_modified_info_action_names(self) -> dict[str, str]:
        return {}

    def get_modified_state_feature_names(self)-> list[str]:
        return [
                "left_arm_joint_1_rad",
                "left_arm_joint_2_rad",
                "left_arm_joint_3_rad",
                "left_arm_joint_4_rad",
                "left_arm_joint_5_rad",
                "left_arm_joint_6_rad",
                "left_gripper_open",
                "left_eef_pos_x_m",
                "left_eef_pos_y_m",
                "left_eef_pos_z_m",
                "left_eef_rot_euler_x_rad",
                "left_eef_rot_euler_y_rad",
                "left_eef_rot_euler_z_rad",
                "right_arm_joint_1_rad",
                "right_arm_joint_2_rad",
                "right_arm_joint_3_rad",
                "right_arm_joint_4_rad",
                "right_arm_joint_5_rad",
                "right_arm_joint_6_rad",
                "right_gripper_open",
                "right_eef_pos_x_m",
                "right_eef_pos_y_m",
                "right_eef_pos_z_m",
                "right_eef_rot_euler_x_rad",
                "right_eef_rot_euler_y_rad",
                "right_eef_rot_euler_z_rad"
            ]
    def get_modified_action_feature_names(self)-> list[str]:
        return [
                "left_arm_joint_1_rad",
                "left_arm_joint_2_rad",
                "left_arm_joint_3_rad",
                "left_arm_joint_4_rad",
                "left_arm_joint_5_rad",
                "left_arm_joint_6_rad",
                "left_gripper_open",
                "left_eef_pos_x_m",
                "left_eef_pos_y_m",
                "left_eef_pos_z_m",
                "left_eef_rot_euler_x_rad",
                "left_eef_rot_euler_y_rad",
                "left_eef_rot_euler_z_rad",
                "right_arm_joint_1_rad",
                "right_arm_joint_2_rad",
                "right_arm_joint_3_rad",
                "right_arm_joint_4_rad",
                "right_arm_joint_5_rad",
                "right_arm_joint_6_rad",
                "right_gripper_open",
                "right_eef_pos_x_m",
                "right_eef_pos_y_m",
                "right_eef_pos_z_m",
                "right_eef_rot_euler_x_rad",
                "right_eef_rot_euler_y_rad",
                "right_eef_rot_euler_z_rad"
            ]

class AgilexCobotDecoupledMagicH5Mp4Processor(StateActionDataPostProcessorBase):
    def __init__(self, convert_path: str | Path) -> None:
        super().__init__(convert_path)
        self.episode_index = 0  # 默认值

    def set_episode_index(self, episode_index: int):
        """设置当前处理的 episode 索引"""
        self.episode_index = episode_index

    def prepare_processing(self) -> None:
        self.left_gripper_open_state_data_idx = 6
        self.right_gripper_open_state_data_idx = 13
        # self.left_gripper_open_action_data_idx = self.left_gripper_open_state_data_idx
        # self.right_gripper_open_action_data_idx = self.right_gripper_open_state_data_idx
        pass

    def _scale_columns(self, data: np.ndarray) -> np.ndarray:
        """如果第7或第14列的最大值 > 0.8，则该列整体除以10; 如果 < 0.08, 则乘以10"""
        scaled_data = data.copy()
        # h5_mp4 state/action 特征只有14维
        for col_idx in (6, 13):
            try:
                col_max = float(np.max(scaled_data[:, col_idx]))
                if col_max > 0.8:
                    logger.info(f"Episode {self.episode_index}: Column {col_idx} max value is {col_max} > 0.8, scaling it by dividing by 10.")
                    scaled_data[:, col_idx] = scaled_data[:, col_idx] / 10.0
                elif col_max < 0.08:
                    logger.info(f"Episode {self.episode_index}: Column {col_idx} max value is {col_max} < 0.08, scaling it by multiplying by 10.")
                    scaled_data[:, col_idx] = scaled_data[:, col_idx] * 10.0
            except (IndexError, ValueError) as e:
                logger.warning(f"Episode {self.episode_index}: Could not process column {col_idx}. Reason: {e}")
                continue
        return scaled_data

    def _smooth_joint_data(self, data: np.ndarray, window_size: int = 16) -> np.ndarray:
        """对所有关节数据应用平滑滤波"""
        if data.ndim != 2 or data.shape[0] < window_size:
            return data
        
        smoothed_data = data.copy()
        # 对每一列（每个关节）应用移动平均滤波
        for i in range(data.shape[1]):
            # 使用 pandas 的 rolling mean 来处理，center=True 确保窗口居中
            series = pd.Series(data[:, i])
            smoothed_series = series.rolling(window=window_size, min_periods=1, center=True).mean()
            smoothed_data[:, i] = smoothed_series.to_numpy()
            
        return smoothed_data

    # 该方法将ori_state_data进行后处理，返回结果为后处理后的数据
    def process_episode_state_data(self, ori_state_data: np.ndarray) -> np.ndarray:
        new_state_data = ori_state_data.copy()
        left_data = ori_state_data[:, 0:self.left_gripper_open_state_data_idx + 1]
        right_data = ori_state_data[:, self.left_gripper_open_state_data_idx + 1:self.right_gripper_open_state_data_idx + 1]

        new_state_data[:, 0:self.left_gripper_open_state_data_idx + 1] = right_data
        new_state_data[:, self.left_gripper_open_state_data_idx + 1:self.right_gripper_open_state_data_idx + 1] = left_data

        scaled_data = self._scale_columns(new_state_data)
        smoothed_data = self._smooth_joint_data(scaled_data)
        return smoothed_data

    # 该方法将ori_action_data进行后处理，返回结果为后处理后的数据
    def process_episode_action_data(self, ori_action_data: np.ndarray) -> np.ndarray:
        new_action_data = ori_action_data.copy()
        left_data = ori_action_data[:, 0:self.left_gripper_open_state_data_idx + 1]
        right_data = ori_action_data[:, self.left_gripper_open_state_data_idx + 1:self.right_gripper_open_state_data_idx + 1]

        new_action_data[:, 0:self.left_gripper_open_state_data_idx + 1] = right_data
        new_action_data[:, self.left_gripper_open_state_data_idx + 1:self.right_gripper_open_state_data_idx + 1] =  left_data
        
        scaled_data = self._scale_columns(new_action_data)
        smoothed_data = self._smooth_joint_data(scaled_data)
        return smoothed_data

    # 忽略原始 action 数据，全部使用 state 数据覆盖
    def process_episode_data(self, ori_data: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        processed_state = self.process_episode_state_data(ori_data["observation.state"])
        # action 特征在本 processor 中与 state 特征长度一致，直接复制
        processed_action = processed_state.copy()

        # 打印原始夹爪数据的最大值（在处理完成后）
        central_logger = logging.getLogger("state action data post process server")
        try:
            orig_state = ori_data.get("observation.state")
            left_idx = getattr(self, "left_gripper_open_state_data_idx", 6)
            right_idx = getattr(self, "right_gripper_open_state_data_idx", 13)
            if orig_state is not None and orig_state.ndim == 2:
                left_max = float(np.max(orig_state[:, left_idx]))
                right_max = float(np.max(orig_state[:, right_idx]))
                central_logger.info(
                    f"Episode {self.episode_index}: Original gripper max values - left(col {left_idx}): {left_max}, right(col {right_idx}): {right_max}"
                )
            else:
                central_logger.warning(f"Episode {self.episode_index}: Original state data missing or malformed; cannot compute gripper max values.")
        except Exception as e:
            central_logger.warning(f"Episode {self.episode_index}: Could not compute original gripper max values. Reason: {e}")

        return {"observation.state": processed_state, "action": processed_action}

    # 该方法返回处理后的state数据名称
    def get_modified_feature_names(self):
        return super().get_modified_feature_names()

    def get_modified_info_state_names(self) -> dict[str, str]:
        return {}

    # 该方法返回处理后的action数据名称
    def get_modified_info_action_names(self) -> dict[str, str]:
        return {}

    def get_modified_state_feature_names(self)-> list[str]:
        return [
                "left_arm_joint_1_rad",
                "left_arm_joint_2_rad",
                "left_arm_joint_3_rad",
                "left_arm_joint_4_rad",
                "left_arm_joint_5_rad",
                "left_arm_joint_6_rad",
                "left_gripper_open",
                "right_arm_joint_1_rad",
                "right_arm_joint_2_rad",
                "right_arm_joint_3_rad",
                "right_arm_joint_4_rad",
                "right_arm_joint_5_rad",
                "right_arm_joint_6_rad",
                "right_gripper_open"
            ]
    def get_modified_action_feature_names(self)-> list[str]:
        return [
                "left_arm_joint_1_rad",
                "left_arm_joint_2_rad",
                "left_arm_joint_3_rad",
                "left_arm_joint_4_rad",
                "left_arm_joint_5_rad",
                "left_arm_joint_6_rad",
                "left_gripper_open",
                "right_arm_joint_1_rad",
                "right_arm_joint_2_rad",
                "right_arm_joint_3_rad",
                "right_arm_joint_4_rad",
                "right_arm_joint_5_rad",
                "right_arm_joint_6_rad",
                "right_gripper_open"
            ]


class AgilexCobotDecoupledMagicMultSensorProcessor(StateActionDataPostProcessorBase):
    def __init__(self, convert_path: str | Path) -> None:
        super().__init__(convert_path)

    def prepare_processing(self) -> None:
        pass

    def _smooth_gripper_open_data(self, data: np.ndarray) -> np.ndarray:
        smoothed = data.copy()
        return smoothed

    # 该方法将ori_state_data进行后处理，返回结果为后处理后的数据
    def process_episode_state_data(self, ori_state_data: np.ndarray) -> np.ndarray:
        new_state_data = ori_state_data.copy()
        return new_state_data

    # 该方法将ori_action_data进行后处理，返回结果为后处理后的数据
    def process_episode_action_data(self, ori_action_data: np.ndarray) -> np.ndarray:
        new_action_data = ori_action_data.copy()
        return new_action_data
    def get_modified_feature_names(self):
        return super().get_modified_feature_names()

    def get_modified_state_feature_names(self)-> list[str]:
        return []
    
    def get_modified_action_feature_names(self)-> list[str]:
        return []

    def get_modified_info_state_names(self) -> dict[str, str]:
        return {}

    # 该方法返回处理后的action数据名称
    def get_modified_info_action_names(self) -> dict[str, str]:
        return {}

    def get_modified_state_feature_names(self)-> list[str]:
        return [
                "left_arm_joint_1_rad",
                "left_arm_joint_2_rad",
                "left_arm_joint_3_rad",
                "left_arm_joint_4_rad",
                "left_arm_joint_5_rad",
                "left_arm_joint_6_rad",
                "left_gripper_open",
                "left_eef_pos_x_m",
                "left_eef_pos_y_m",
                "left_eef_pos_z_m",
                "left_eef_rot_euler_x_rad",
                "left_eef_rot_euler_y_rad",
                "left_eef_rot_euler_z_rad",
                "right_arm_joint_1_rad",
                "right_arm_joint_2_rad",
                "right_arm_joint_3_rad",
                "right_arm_joint_4_rad",
                "right_arm_joint_5_rad",
                "right_arm_joint_6_rad",
                "right_gripper_open",
                "right_eef_pos_x_m",
                "right_eef_pos_y_m",
                "right_eef_pos_z_m",
                "right_eef_rot_euler_x_rad",
                "right_eef_rot_euler_y_rad",
                "right_eef_rot_euler_z_rad"
            ]

    def get_modified_action_feature_names(self)-> list[str]:
        return [
                "left_arm_joint_1_rad",
                "left_arm_joint_2_rad",
                "left_arm_joint_3_rad",
                "left_arm_joint_4_rad",
                "left_arm_joint_5_rad",
                "left_arm_joint_6_rad",
                "left_gripper_open",
                "left_eef_pos_x_m",
                "left_eef_pos_y_m",
                "left_eef_pos_z_m",
                "left_eef_rot_euler_x_rad",
                "left_eef_rot_euler_y_rad",
                "left_eef_rot_euler_z_rad",
                "right_arm_joint_1_rad",
                "right_arm_joint_2_rad",
                "right_arm_joint_3_rad",
                "right_arm_joint_4_rad",
                "right_arm_joint_5_rad",
                "right_arm_joint_6_rad",
                "right_gripper_open",
                "right_eef_pos_x_m",
                "right_eef_pos_y_m",
                "right_eef_pos_z_m",
                "right_eef_rot_euler_x_rad",
                "right_eef_rot_euler_y_rad",
                "right_eef_rot_euler_z_rad"
            ]

