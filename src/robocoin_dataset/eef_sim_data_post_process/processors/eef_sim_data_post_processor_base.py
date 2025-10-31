import numpy as np
from pathlib import Path
from robocoin_dataset.data_post_process import DataPostProcessorBase
from robocoin_dataset.sim_replay.lerobot_sim_replayer import LerobotSimReplayer
from robocoin_dataset.sim_replay.configs.lerobot_sim_replay_config import (
    LerobotSimReplayConfig,
)

class EefSimDataPostProcessorBase(DataPostProcessorBase):
    def __init__(
        self,
        convert_path: str | Path,
        sim_replay_config: LerobotSimReplayConfig,
    ) -> None:
        # 将 has_gripper 传入实例，后续用于决定生成的特征名称
        self.has_gripper = bool(sim_replay_config.has_gripper)
        self.gripper_value_open = sim_replay_config.gripper_value_open
        self.gripper_value_close = sim_replay_config.gripper_value_close
        self.sim_replay_config = sim_replay_config

        # 所以这里 data_feature_keys 使用输入数据的键名
        super().__init__(
            convert_path=convert_path,
            data_post_process_type="eef_sim",
            data_feature_keys={
                "observation.state",
                "action",
            },
        )
        
        # 创建 simulator（使用父类已经设置的 self.convert_path）
        self.simulator = LerobotSimReplayer(self.sim_replay_config, self.convert_path)
        
    def prepare_processing(self) -> None:
        pass
    
    def process_episode_data(self, ori_data: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        state_arr = ori_data.get("observation.state")
        action_arr = ori_data.get("action")

        new_state = self.process_episode_state_data(state_arr) if state_arr is not None else None
        new_action = self.process_episode_action_data(action_arr) if action_arr is not None else None

        # 根据 has_gripper 决定输出结构
        if self.has_gripper:
            # 分离 EEF 和夹爪数据
            num_sites = len(self.sim_replay_config.mjcf_site_names)
            num_eef_cols = num_sites * 6
            
            state_eef = new_state[:, :num_eef_cols] if new_state is not None else None
            state_gripper = new_state[:, num_eef_cols:] if new_state is not None else None
            
            action_eef = new_action[:, :num_eef_cols] if new_action is not None else None
            action_gripper = new_action[:, num_eef_cols:] if new_action is not None else None
            
            return {
                "eef_sim_state": state_eef,
                "eef_sim_action": action_eef,
                "gripper_state": state_gripper,
                "gripper_action": action_gripper,
            }
        else:
            # 没有夹爪，只返回 EEF 数据
            return {
                "eef_sim_state": new_state,
                "eef_sim_action": new_action,
            }
    
    def get_output_feature_keys(self) -> set[str]:
        """返回输出数据的特征键（与输入可能不同）"""
        if self.has_gripper:
            return {"eef_sim_state", "eef_sim_action", "gripper_state", "gripper_action"}
        else:
            return {"eef_sim_state", "eef_sim_action"}
    
    def process(self) -> None:
        """重写process方法以支持输入输出键名不同的情况，并传递 episode_idx"""
        from tqdm import tqdm
        import pandas as pd
        import pyarrow as pa
        import pyarrow.parquet as pq
        
        self.write_new_info_file()
        output_keys = self.get_output_feature_keys()
        
        for episode_idx in tqdm(
            range(len(self.parquet_files)), desc="Processing episodes", unit="episode"
        ):
            # 保存当前 episode_idx 供子方法使用
            self.current_episode_idx = episode_idx
            
            self.prepare_processing()
            ori_data = self.get_ori_episode_data(episode_idx)
            new_datas: dict[str, np.ndarray] = self.process_episode_data(ori_data)

            for key, arr in new_datas.items():
                if isinstance(arr, np.ndarray) and np.issubdtype(arr.dtype, np.floating):
                    new_datas[key] = arr.astype(np.float32)
            
            # 使用 output_keys 而不是 self.data_features 进行验证
            if new_datas.keys() != output_keys:
                raise ValueError(
                    f"new_datas keys {new_datas.keys()} != output_keys {output_keys}"
                )

            # 验证数据长度一致性（使用第一个非 None 的输入数据）
            for ori_key, ori_arr in ori_data.items():
                if ori_arr is not None:
                    expected_length = ori_arr.shape[0]
                    for new_key, new_arr in new_datas.items():
                        if new_arr is not None and new_arr.shape[0] != expected_length:
                            raise ValueError(
                                f"ori_data[{ori_key}] shape {ori_arr.shape}[0] != "
                                f"new_datas[{new_key}] shape {new_arr.shape}[0]"
                            )
                    break

            self.write_new_episode_file(new_datas, episode_idx)

    def get_modified_feature_names(self) -> dict[str, list[str]]:
        eef_names = [
            "left_eef_pos_x",
            "left_eef_pos_y",
            "left_eef_pos_z",
            "left_eef_ori_x",
            "left_eef_ori_y",
            "left_eef_ori_z",
            "right_eef_pos_x",
            "right_eef_pos_y",
            "right_eef_pos_z",
            "right_eef_ori_x",
            "right_eef_ori_y",
            "right_eef_ori_z",
        ]
        
        result = {
            "eef_sim_state": eef_names,
            "eef_sim_action": eef_names,
        }
        
        if self.has_gripper:
            gripper_names = ["left_gripper_open", "right_gripper_open"]
            result["gripper_state"] = gripper_names
            result["gripper_action"] = gripper_names
        
        return result
    
    def write_new_info_file(self) -> None:
        """重写 write_new_info_file 方法，添加 has_gripper 信息"""
        import json
        
        json_dict = {}
        json_dict["has_gripper"] = self.has_gripper
        json_dict["features"] = {}
        
        for feature_key, names in self.get_modified_feature_names().items():
            if names is not None:
                if len(names) != len(set(names)):
                    raise ValueError(f"given feature names contain duplicated names: {names}")
            json_dict["features"][feature_key] = {}
            json_dict["features"][feature_key]["names"] = names

        with open(self.new_info_file_path, "w") as f:
            json.dump(json_dict, f, indent=2)


    def prepare_processing(self) -> None:
        # 可由子类实现具体准备逻辑；此处保留空实现
        pass

    # 该方法将ori_state_data进行后处理，返回结果为后处理后的数据
    def process_episode_state_data(self, ori_state_data: np.ndarray) -> np.ndarray:
        episode_idx = getattr(self, 'current_episode_idx', 0)
        results = self.simulator.replay_episode_background(episode_index=episode_idx, is_state=True)

        eef_data = np.array(results)

        # 计算EEF位姿数据的列数（每个site 6维：pos(3) + ori(3)）
        num_sites = len(self.sim_replay_config.mjcf_site_names)
        num_eef_cols = num_sites * 6
        
        # 如果没有夹爪，只返回EEF位姿数据
        if not self.has_gripper:
            return eef_data[:, :num_eef_cols]
        
        # 有夹爪：归一化夹爪数据后返回完整数据（EEF + 夹爪）
        if eef_data.shape[1] > num_eef_cols:
            # 提取夹爪数据（EEF位姿之后的列）
            gripper_data = eef_data[:, num_eef_cols:]
            
            # 归一化到 [0, 1] 范围
            # 使用公式: (value - min) / (max - min)
            if self.gripper_value_open != self.gripper_value_close:
                gripper_normalized = (gripper_data - self.gripper_value_close) / (
                    self.gripper_value_open - self.gripper_value_close
                )
                # 限制在 [0, 1] 范围内
                gripper_normalized = np.clip(gripper_normalized, 0.0, 1.0)
                
                # 替换原始夹爪数据
                eef_data[:, num_eef_cols:] = gripper_normalized
            
        return eef_data

    # 该方法将ori_action_data进行后处理，返回结果为后处理后的数据
    def process_episode_action_data(self, ori_action_data: np.ndarray) -> np.ndarray:
        episode_idx = getattr(self, 'current_episode_idx', 0)
        results = self.simulator.replay_episode_background(episode_index=episode_idx, is_state=False)
        
        eef_data = np.array(results)
        
        # 计算EEF位姿数据的列数（每个site 6维：pos(3) + ori(3)）
        num_sites = len(self.sim_replay_config.mjcf_site_names)
        num_eef_cols = num_sites * 6
        
        # 如果没有夹爪，只返回EEF位姿数据
        if not self.has_gripper:
            return eef_data[:, :num_eef_cols]
        
        # 有夹爪：归一化夹爪数据后返回完整数据（EEF + 夹爪）
        if eef_data.shape[1] > num_eef_cols:
            # 提取夹爪数据（EEF位姿之后的列）
            gripper_data = eef_data[:, num_eef_cols:]
            
            # 归一化到 [0, 1] 范围
            if self.gripper_value_open != self.gripper_value_close:
                gripper_normalized = (gripper_data - self.gripper_value_close) / (
                    self.gripper_value_open - self.gripper_value_close
                )
                # 限制在 [0, 1] 范围内
                gripper_normalized = np.clip(gripper_normalized, 0.0, 1.0)
                
                # 替换原始夹爪数据
                eef_data[:, num_eef_cols:] = gripper_normalized
            
            # print(f"  [ACTION] Episode {episode_idx}: Normalized gripper from range [{self.gripper_value_close}, {self.gripper_value_open}]")
            # print(f"  [ACTION] EEF cols: {num_eef_cols}, Total cols: {eef_data.shape[1]}, Gripper cols: {eef_data.shape[1] - num_eef_cols}")
            # print(f"  [ACTION] Sample normalized gripper values: {eef_data[0, num_eef_cols:]}")
        
        # 返回完整数据（EEF + 归一化后的夹爪），在 process_episode_data 中会分离
        return eef_data
