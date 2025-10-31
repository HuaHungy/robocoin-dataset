from 
class BadFrameDetectionConfig:
    jump_frame: bool = False
    stationary_motion: bool = True

    detection_enabled: dict[str, bool] = {
        "jump_frame": False,
        "stationary_motion": False,
    }

    detectors: dict[str, callable] = {
        "jump_frame": ,
        "stationary_motion": ,
    }

    detect_motion_features: set[str] = [
        "observation.state",
        "action",
        "sim_eef_pose",
        "sim_gripper_open",
    ]
    source_data_type: str = "merge"

    max_stationary_frame_num: int = 3
    stationary_phash_threshold: int = 2
    stationary_motion_threshold: float = 0.5
