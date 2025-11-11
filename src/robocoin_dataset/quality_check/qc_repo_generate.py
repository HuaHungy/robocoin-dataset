import json
from pathlib import Path

import numpy as np
import pandas as pd
import tqdm

from robocoin_dataset.quality_check.hardlink.make_hardlink import (
    RepoHardLinkCorresp,
    create_hardlinks_from_correspondence,
)
from robocoin_dataset.utils.parquet_paths import get_parquet_paths
from robocoin_dataset.utils.path_utils import (
    get_dataset_video_paths,
    get_episodes_jsonl_file_paths,
    get_episodes_stats_jsonl_file_paths,
    get_meta_info_file_path,
)


def gen_qc_repo_files(
    repo_path: str | Path,
    bad_episodes: set[int],
    input_feature: str,
    output_feature: str,
) -> dict[str | Path, str | Path]:
    """Remove bad episodes from the dataset repository.

    Args:
        repo_path (str|Path): Path to the dataset repository.
        bad_episodes (set[int]): Set of episode indices to be removed.
        feature_type (str): Type of feature (e.g., 'state', 'action', 'video').
    """
    repo_path = Path(repo_path)
    if not repo_path.exists():
        raise ValueError(f"Repository path does not exist: {repo_path}")

    if repo_path.is_file():
        raise ValueError(f"Repository path is a file: {repo_path}")

    if input_feature == output_feature:
        raise ValueError("Input feature cannot be the same as output feature.")

    _, input_info_file_path = get_meta_info_file_path(repo_path, input_feature)
    _, out_info_file_path = get_meta_info_file_path(repo_path, output_feature)

    input_episodes_jsonl_path, _ = get_episodes_jsonl_file_paths(repo_path, input_feature)
    _, out_episodes_jsonl_path = get_episodes_jsonl_file_paths(repo_path, output_feature)

    _, input_episodes_stats_jsonl_path = get_episodes_stats_jsonl_file_paths(
        repo_path, input_feature
    )
    _, out_episodes_stats_jsonl_path = get_episodes_stats_jsonl_file_paths(
        repo_path, output_feature
    )

    _, input_parquet_paths = get_parquet_paths(repo_path, input_feature)

    episodes_frame_nums = {}
    with open(input_episodes_jsonl_path) as f:
        for line in f:
            data = json.loads(line)
            episode_id = data["episode_index"]
            frame_count = data["length"]
            episodes_frame_nums[episode_id] = frame_count

    sorted_episodes_frame_nums = sorted(episodes_frame_nums.items(), key=lambda x: x[0])
    episodes_frame_nums_list = [frame_num for _, frame_num in sorted_episodes_frame_nums]

    qc_episodes_start_frame_indices = [0]
    for episode_id in range(len(episodes_frame_nums_list)):
        if episode_id in bad_episodes:
            continue
        qc_episodes_start_frame_indices.append(
            qc_episodes_start_frame_indices[-1] + episodes_frame_nums_list[episode_id]
        )

    out_total_frames = sum(
        frame_num
        for ep_idx, frame_num in enumerate(episodes_frame_nums_list)
        if ep_idx not in bad_episodes
    )
    out_total_episodes = len(episodes_frame_nums_list) - len(bad_episodes)

    _gen_output_meta_info_file(
        input_info_file_path, out_info_file_path, out_total_frames, out_total_episodes
    )

    _gen_output_episodes_jsonl_file(
        input_episodes_jsonl_path, out_episodes_jsonl_path, bad_episodes
    )
    _gen_output_episodes_stats_jsonl_file(
        input_episodes_stats_jsonl_path, out_episodes_stats_jsonl_path, bad_episodes
    )

    with open(input_info_file_path) as f:
        data = json.load(f)
        chunks_size = data.get("chunks_size")

    _gen_output_parquet_files(
        repo_path=repo_path,
        input_parquet_paths=input_parquet_paths,
        bad_episodes=bad_episodes,
        qc_episodes_start_frame_indices=qc_episodes_start_frame_indices,
        chunk_size=chunks_size,
        output_feature=output_feature,
    )
    return _gen_video_path_matching_dict(
        input_video_paths=get_dataset_video_paths(repo_path),
        repo_path=repo_path,
        bad_episodes=bad_episodes,
        chunk_size=chunks_size,
    )


def _gen_output_meta_info_file(
    input_info_file_path: Path,
    output_info_file_path: Path,
    total_frames: int,
    total_episodes: int,
) -> None:
    with open(input_info_file_path) as f:
        with open(output_info_file_path, "w") as out_f:
            data = json.load(f)
            input_total_videos = data.get("total_videos")
            input_total_episodes = data.get("total_episodes")
            chunks_size = data.get("chunks_size")
            videos_per_episode = input_total_videos // input_total_episodes

            data["total_frames"] = total_frames
            data["total_episodes"] = total_episodes
            data["total_videos"] = total_episodes * videos_per_episode
            data["total_chunks"] = (total_episodes + chunks_size - 1) // chunks_size
            json.dump(data, out_f)


def _gen_output_episodes_jsonl_file(
    input_episodes_jsonl_path: Path,
    output_episodes_jsonl_path: Path,
    bad_episodes: set[int],
) -> None:
    out_ep_idx = 0
    with open(
        input_episodes_jsonl_path,
    ) as f:
        with open(output_episodes_jsonl_path, "w") as out_f:
            for line in f:
                data = json.loads(line)
                episode_id = data["episode_index"]
                if episode_id in bad_episodes:
                    continue
                data["episode_index"] = out_ep_idx
                out_f.write(json.dumps(data) + "\n")
                out_ep_idx += 1


def _gen_output_episodes_stats_jsonl_file(
    input_episodes_stats_jsonl_path: Path,
    output_episodes_stats_jsonl_path: Path,
    bad_episodes: set[int],
) -> None:
    out_ep_idx = 0
    with open(
        input_episodes_stats_jsonl_path,
    ) as f:
        with open(output_episodes_stats_jsonl_path, "w") as out_f:
            for line in f:
                data = json.loads(line)
                episode_id = data["episode_index"]
                if episode_id in bad_episodes:
                    continue
                data["episode_index"] = out_ep_idx
                out_f.write(json.dumps(data) + "\n")
                out_ep_idx += 1


def _gen_output_parquet_files(
    repo_path: str | Path,
    input_parquet_paths: list[Path],
    bad_episodes: set[int],
    qc_episodes_start_frame_indices: list[int],
    chunk_size: int,
    output_feature: str,
) -> None:
    out_episode_idx = 0
    repo_path = Path(repo_path).expanduser().absolute()

    def get_output_parquet_path(out_ep_idx: int) -> Path:
        chunk_idx = ep_idx // chunk_size
        output_parquet_path = (
            repo_path
            / f"{output_feature}_data"
            / f"chunk-{chunk_idx:03d}"
            / f"episode_{out_ep_idx:06d}.parquet"
        )
        output_parquet_path.parent.mkdir(parents=True, exist_ok=True)
        return output_parquet_path

    for ep_idx, input_parquet_path in tqdm.tqdm(
        enumerate(input_parquet_paths),
        total=len(input_parquet_paths),
        desc="Generating output parquet files",
        unit="episode",
    ):
        if ep_idx in bad_episodes:
            continue
        df = pd.read_parquet(input_parquet_path)
        indices_data = np.array(df["index"].to_list(), dtype=int)
        indices_data = (
            indices_data - indices_data[0] + qc_episodes_start_frame_indices[out_episode_idx]
        )
        df["index"] = indices_data.tolist()
        df["episode_index"] = out_episode_idx
        output_parquet_path = get_output_parquet_path(out_episode_idx)
        df.to_parquet(output_parquet_path, engine="pyarrow")
        out_episode_idx += 1


def _gen_video_path_matching_dict(
    input_video_paths: list[list[Path]],
    repo_path: str | Path,
    bad_episodes: set[int],
    chunk_size: int,
) -> dict[int, list[Path]]:
    repo_path = Path(repo_path).expanduser().absolute()

    def get_video_new_path(ep_video_paths: list[Path], output_ep_idx: int) -> dict[str, str]:
        chunk_idx = output_ep_idx // chunk_size
        results = {}
        for video_path in ep_video_paths:
            new_video_path = (
                repo_path
                / "videos"
                / f"chunk-{chunk_idx:03d}"
                / video_path.parent.name
                / f"episode_{output_ep_idx:06d}.mp4"
            )
            results[str(video_path)] = str(new_video_path)
        return results

    matching_dict = {}

    out_episode_idx = 0
    for ep_idx, video_paths in enumerate(input_video_paths):
        if ep_idx in bad_episodes:
            continue

        matching_dict.update(get_video_new_path(video_paths, out_episode_idx))
        out_episode_idx += 1

    return matching_dict


def gen_qc_repo(
    repo_path: str | Path,
    bad_episodes: set[int],
    input_feature: str = "quality_checked",
    hl_suffix: str = "hardlink",
) -> None:
    repo_path = Path(repo_path).expanduser().absolute()

    video_path_corresp = gen_qc_repo_files(
        repo_path=repo_path,
        bad_episodes=bad_episodes,
        input_feature=input_feature,
        output_feature=hl_suffix,
    )
    file_corresp, dir_corresp = RepoHardLinkCorresp(
        input_feature=input_feature,
        repo_path=repo_path,
        hard_link_repo_path=repo_path.parent / f"{str(repo_path.name)}_{hl_suffix}",
        video_path_corresp=video_path_corresp,
    ).get_hard_link_corresp()
    create_hardlinks_from_correspondence(file_corresp=file_corresp, dir_corresp=dir_corresp)
