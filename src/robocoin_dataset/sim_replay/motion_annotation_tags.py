class MotionAnnotationBaseTags:
    parquet_column_name: str | None = None
    tag_list: list[str] | None = None
    def operator(self, other: str) -> bool:


class EEFMovementDirectionTags(MotionAnnotationBaseTags):
    parquet_column_name = "eef_movement_direction_type"
    tag_list = [
        "stationary",
        "left",
        "right",
        "up",
        "down",
        "forward",
        "backward",
    ]


class EEFMovementVelocityTags(MotionAnnotationBaseTags):
    parquet_column_name = "eef_movement_velocity_type"
    tag_list = [
        "slow",
        "fast",
        "stationary",
    ]


class EEFMovementAccelerationTags(MotionAnnotationBaseTags):
    parquet_column_name = "eef_movement_acceleration_type"
    tag_list = [
        "constant",
        "accelerating",
        "decelerating",
    ]


class GripperActionTags(MotionAnnotationBaseTags):
    parquet_column_name = "gripper_state_type"
    tag_list = [
        "opening",
        "closing",
        "holding",
    ]


class GripperStateTags(MotionAnnotationBaseTags):
    parquet_column_name = "gripper_state_type"
    tag_list = [
        "open",
        "closed",
    ]
