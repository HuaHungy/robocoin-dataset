from pathlib import Path

import numpy as np
import pandas as pd

from .state_action_data_processor_base import StateActionDataPostProcessorBase


class LejuRobotProcessor(StateActionDataPostProcessorBase):
    def __init__(self, convert_path: str | Path) -> None:
        super().__init__(convert_path)

    def prepare_processing(self) -> None:
        pass

    def _smooth_data(self, data: np.ndarray, window_size: int = 2) -> np.ndarray:
        """
        对数据进行平滑滤波
        
        Args:
            data: 输入数据，shape 为 (n_frames, n_features)
            window_size: 滑动窗口大小
            
        Returns:
            平滑后的数据
        """
        if data.shape[0] < window_size:
            # 如果数据长度小于窗口大小，直接返回原数据
            return data
        
        smoothed_data = np.zeros_like(data)
        for i in range(data.shape[1]):
            series = pd.Series(data[:, i])
            smoothed_series = series.rolling(window=window_size, min_periods=1, center=True).mean()
            smoothed_data[:, i] = smoothed_series.values
        
        return smoothed_data

    # 该方法将ori_state_data进行后处理，返回结果为后处理后的数据
    def process_episode_state_data(self, ori_state_data: np.ndarray) -> np.ndarray:
        new_state_data = ori_state_data.copy()
        # 应用平滑滤波
        new_state_data = self._smooth_data(new_state_data, window_size=4)
        return new_state_data

    # 该方法将ori_action_data进行后处理，返回结果为后处理后的数据
    def process_episode_action_data(self, ori_action_data: np.ndarray) -> np.ndarray:
        new_action_data = ori_action_data.copy()
        # 应用平滑滤波
        new_action_data = self._smooth_data(new_action_data, window_size=4)
        return new_action_data
    def get_modified_feature_names(self):
        return super().get_modified_feature_names()

    def get_modified_info_state_names(self) -> dict[str, str]:
        return {}

    # 该方法返回处理后的action数据名称
    def get_modified_info_action_names(self) -> dict[str, str]:
        return {}
