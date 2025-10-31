from pathlib import Path

from .bad_frame_detection_config import BadFrameDetectionConfig


class BadFrameDetection:
    def __init__(self, convert_path: str | Path, detection_config: BadFrameDetectionConfig) -> None:
        self.convert_path: Path = Path(convert_path).expanduser().absolute()
        self.detection_config = detection_config

    def detect_bad_frame(self) -> dict[int, dict[str, int]]:
        results = {}
        if self.detection_config.jump_frame:
            self.detect_jump_frame()

        if self.detection_config.stationary_motion:
            return self.detect_stationary_motion()
