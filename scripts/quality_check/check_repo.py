import argparse
from pathlib import Path

from robocoin_dataset.quality_check.dataset_quality_check import get_checker_config, quality_check_pipeline


def check_repo(repo_path: str | Path, device_model: str, device_model_version: str) -> dict:
    checker_config = get_checker_config(
        device_model,
        device_model_version,
        Path(__file__).parent / "configs" / "device_version_checker_config.yaml",
    )
    return quality_check_pipeline(repo_path, checker_config)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Quality check for Robocoin dataset repo.")
    parser.add_argument("repo_path", type=str, help="Path to the Robocoin dataset repository.")
    parser.add_argument(
        "--device_model",
        type=str,
        required=False,
        default="",
        help="Device model to check.",
    )
    parser.add_argument(
        "--device_model_version",
        type=str,
        required=False,
        default="",
        help="Device model version to check.",
    )
    args = parser.parse_args()
    score_results, scores_per_checker = check_repo(
        args.repo_path, args.device_model, args.device_model_version
    )
    import json

    print(json.dumps(scores_per_checker))

    jump_frames = scores_per_checker["video_scores_perchecker"]
    print("Jump frame scores per episode:")
    print(json.dumps(jump_frames, indent=2))
