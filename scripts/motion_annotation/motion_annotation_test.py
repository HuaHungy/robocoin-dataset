from pathlib import Path

from robocoin_dataset.annotation.motion_annotation.processors.motion_annotation_data_post_processor import (
    MotionAnnotationDataPostProcessor,
)
from robocoin_dataset.sim_replay.configs.unitree_g1_config import (
    UnitreeG1Dof29ThreeFingerHandConfig,
)

if __name__ == "__main__":
    repo_path: Path = Path(
        "/mnt/nas/synnas/docker2/robocoin-datasets/discover_robotics_aitbot_mmk2_place_the_pliers_and_wallpaper_knife"
    )
    processor: MotionAnnotationDataPostProcessor = MotionAnnotationDataPostProcessor(
        convert_path=repo_path, sim_replay_config=UnitreeG1Dof29ThreeFingerHandConfig()
    )
    processor.process()
