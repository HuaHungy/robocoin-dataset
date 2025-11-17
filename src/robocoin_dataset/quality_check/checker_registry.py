DATASET_DATA_CHECKERS: dict[str, callable] = {}
EPISODE_DATA_CHECKERS: dict[str, callable] = {}
EPISODE_VIDEO_CHECKERS: dict[str, callable] = {}
EPISODE_VIDEO_DATA_CONSISTENCY_CHECKERS: dict[str, callable] = {}


def dataset_data_checker_registry(name: str) -> any:
    def decorator(func: callable) -> callable:
        DATASET_DATA_CHECKERS[name] = func
        return func

    return decorator


def episode_data_checker_registry(name: str) -> any:
    def decorator(func: callable) -> callable:
        EPISODE_DATA_CHECKERS[name] = func
        return func

    return decorator


def episode_video_checker_registry(name: str) -> any:
    def decorator(func: callable) -> callable:
        EPISODE_VIDEO_CHECKERS[name] = func
        return func

    return decorator


def data_video_consistency_checker_registry(name: str) -> any:
    def decorator(func: callable) -> callable:
        EPISODE_VIDEO_DATA_CONSISTENCY_CHECKERS[name] = func
        return func

    return decorator
