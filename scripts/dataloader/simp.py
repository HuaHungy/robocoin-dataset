import argparse
import random
import sys
from collections.abc import Iterator
from pathlib import Path

import torch
import torch.utils.data
import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "third_parties" / "robocoin-lerobot" / "src"))

from lerobot.datasets.lerobot_dataset import LeRobotDataset  # type: ignore


class EpisodeSampler(torch.utils.data.Sampler):
    def __init__(self, dataset: LeRobotDataset, sample_rate: float = 0.1) -> None:
        self.frame_ids = random.sample(
            range(dataset.num_frames), k=int(dataset.num_frames * sample_rate)
        )
        self.frame_ids = self.frame_ids[:: int(1 / sample_rate)]

    def __iter__(self) -> Iterator:
        return iter(self.frame_ids)

    def __len__(self) -> int:
        return len(self.frame_ids)


parser = argparse.ArgumentParser()
parser.add_argument("repo_path", type=str, default="")
parser.add_argument("--num-workers", type=int, default=8)
args = parser.parse_args()
dataset = LeRobotDataset(
    repo_id="test/dataloader_check",
    root=args.repo_path,
    video_backend="pyav", # torchcodec is not supported.(2.0)
)

sampler = EpisodeSampler(dataset)


dataloader = torch.utils.data.DataLoader(
    dataset,
    num_workers=args.num_workers,
    batch_size=32,
    sampler=sampler,
)

for batch in tqdm.tqdm(dataloader, total=len(dataloader)):
    pass
