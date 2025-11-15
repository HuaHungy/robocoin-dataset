from pathlib import Path

from robocoin_dataset.annotation.motion_annotation.processors.motion_annotation_data_post_processor import (
    MotionAnnotationDataPostProcessor,
)
from robocoin_dataset.sim_replay.configs.unitree_g1_config import (
    UnitreeG1Dof29ThreeFingerHandConfig,
)

if __name__ == "__main__":
    repo_path: Path = Path(
        "/mnt/nas/synnas/docker2/robocoin-datasets/unitree_g1_plate_storage_bread"
    )
    processor: MotionAnnotationDataPostProcessor = MotionAnnotationDataPostProcessor(
        convert_path=repo_path, sim_replay_config=UnitreeG1Dof29ThreeFingerHandConfig()
    )
    processor.process()
