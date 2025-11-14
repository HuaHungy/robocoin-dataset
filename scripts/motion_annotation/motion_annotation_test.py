from pathlib import Path

from robocoin_dataset.annotation.motion_annotation.processors.motion_annotation_data_post_processor import (
    MotionAnnotationDataPostProcessor,
)
from robocoin_dataset.sim_replay.configs.agilex_cobot_magic_config import (
    AgilexCobotMagicLerobotH5Mp4NewSimReplayConfig,
)

if __name__ == "__main__":
    repo_path: Path = Path(
        "/mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_put_the_pen_into_the_pen_holder"
    )
    processor: MotionAnnotationDataPostProcessor = MotionAnnotationDataPostProcessor(
        convert_path=repo_path, sim_replay_config=AgilexCobotMagicLerobotH5Mp4NewSimReplayConfig()
    )
    processor.process()
