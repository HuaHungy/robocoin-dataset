#!/usr/bin/env python

# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
""" Visualize data of **all** frames of any episode of a dataset of type LeRobotDataset.

Note: The last frame of the episode doesn't always correspond to a final state.
That's because our datasets are composed of transition from state to state up to
the antepenultimate state associated to the ultimate action to arrive in the final state.
However, there might not be a transition from a final state to another state.

Note: This script aims to visualize the data used to train the neural networks.
~What you see is what you get~. When visualizing image modality, it is often expected to observe
lossy compression artifacts since these images have been decoded from compressed mp4 videos to
save disk space. The compression factor applied has been tuned to not affect success rate.

Examples:

- Visualize data stored on a local machine:
```
local$ python -m lerobot.scripts.visualize_dataset \
    --repo-id lerobot/pusht \
    --episode-index 0
```

- Visualize data stored on a distant machine with a local viewer:
```
distant$ python -m lerobot.scripts.visualize_dataset \
    --repo-id lerobot/pusht \
    --episode-index 0 \
    --save 1 \
    --output-dir path/to/directory

local$ scp distant:path/to/directory/lerobot_pusht_episode_0.rrd .
local$ rerun lerobot_pusht_episode_0.rrd
```

- Visualize data stored on a distant machine through streaming:
(You need to forward the websocket port to the distant machine, with
`ssh -L 9087:localhost:9087 username@remote-host`)
```
distant$ python -m lerobot.scripts.visualize_dataset \
    --repo-id lerobot/pusht \
    --episode-index 0 \
    --mode distant \
    --ws-port 9087

local$ rerun ws://localhost:9087
```

"""

import gc
import logging
import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import rerun as rr
import torch
import torch.utils.data
import tqdm
from lerobot.datasets.lerobot_dataset import LeRobotDataset  # type: ignore


class EpisodeSampler(torch.utils.data.Sampler):
    def __init__(self, dataset: LeRobotDataset, episode_index: int) -> None:
        from_idx = dataset.episode_data_index["from"][episode_index].item()
        to_idx = dataset.episode_data_index["to"][episode_index].item()
        self.frame_ids = range(from_idx, to_idx)

    def __iter__(self) -> Iterator:
        return iter(self.frame_ids)

    def __len__(self) -> int:
        return len(self.frame_ids)


def to_hwc_uint8_numpy(chw_float32_torch: torch.Tensor) -> np.ndarray:
    assert chw_float32_torch.dtype == torch.float32
    assert chw_float32_torch.ndim == 3
    c, h, w = chw_float32_torch.shape
    assert c < h and c < w, f"expect channel first images, but instead {chw_float32_torch.shape}"
    return (chw_float32_torch * 255).type(torch.uint8).permute(1, 2, 0).numpy()


def get_annotation_text(batch: dict, idx: int) -> str:
    annotation_text = ""
    # tasks
    if "tasks" in batch:
        annotation_text += f"Tasks: {batch['tasks'][idx]};"
    # subtasks
    if "subtasks" in batch:
        print(batch["subtasks"])
        print(type(batch["subtasks"][0]))
        annotation_text += f"Subtasks: {batch['subtasks'][idx]};"
    # left arm state annotations
    # EEF acceleration magnitude
    if "left_eef_acc_mag_state" in batch:
        annotation_text += f"Left EEF acc mag state: {batch['left_eef_acc_mag_state'][idx]}\n"
    # EEF direction
    if "left_eef_direction_state" in batch:
        annotation_text += f"Left EEF direction state: {batch['left_eef_direction_state'][idx]}\n"
    # EEF velocity
    if "left_eef_velocity_state" in batch:
        annotation_text += f"Left EEF velocity state: {batch['left_eef_velocity_state'][idx]}\n"
    # Gripper mode
    if "left_gripper_mode_state" in batch:
        annotation_text += f"Left gripper mode state: {batch['left_gripper_mode_state'][idx]}\n"
    # Gripper activity
    if "left_gripper_activity_state" in batch:
        annotation_text += (
            f"Left gripper activity state: {batch['left_gripper_activity_state'][idx]}\n"
        )

    annotation_text += "\n"

    # left arm action annotations
    if "left_eef_acc_mag_action" in batch:
        annotation_text += f"Left EEF acc mag action: {batch['left_eef_acc_mag_action'][idx]}\n"
    if "left_eef_direction_action" in batch:
        annotation_text += f"Left EEF direction action: {batch['left_eef_direction_action'][idx]}\n"
    if "left_eef_velocity_action" in batch:
        annotation_text += f"Left EEF velocity action: {batch['left_eef_velocity_action'][idx]}\n"
    if "left_gripper_mode_action" in batch:
        annotation_text += f"Left gripper mode action: {batch['left_gripper_mode_action'][idx]}\n"
    if "left_gripper_activity_action" in batch:
        annotation_text += (
            f"Left gripper activity action: {batch['left_gripper_activity_action'][idx]}\n"
        )

    annotation_text += "\n"

    # right arm state annotations
    if "right_eef_acc_mag_state" in batch:
        annotation_text += f"Right EEF acc mag state: {batch['right_eef_acc_mag_state'][idx]}\n"
    if "right_eef_direction_state" in batch:
        annotation_text += f"Right EEF direction state: {batch['right_eef_direction_state'][idx]}\n"
    if "right_eef_velocity_state" in batch:
        annotation_text += f"Right EEF velocity state: {batch['right_eef_velocity_state'][idx]}\n"
    if "right_gripper_mode_state" in batch:
        annotation_text += f"Right gripper mode state: {batch['right_gripper_mode_state'][idx]}\n"
    if "right_gripper_activity_state" in batch:
        annotation_text += (
            f"Right gripper activity state: {batch['right_gripper_activity_state'][idx]}\n"
        )

    annotation_text += "\n"

    # right arm action annotations
    if "right_eef_acc_mag_action" in batch:
        annotation_text += f"Right EEF acc mag action: {batch['right_eef_acc_mag_action'][idx]}\n"
    if "right_eef_direction_action" in batch:
        annotation_text += (
            f"Right EEF direction action: {batch['right_eef_direction_action'][idx]}\n"
        )
    if "right_eef_velocity_action" in batch:
        annotation_text += f"Right EEF velocity action: {batch['right_eef_velocity_action'][idx]}\n"
    if "right_gripper_mode_action" in batch:
        annotation_text += f"Right gripper mode action: {batch['right_gripper_mode_action'][idx]}\n"
    if "right_gripper_activity_action" in batch:
        annotation_text += (
            f"Right gripper activity action: {batch['right_gripper_activity_action'][idx]}\n"
        )

    return annotation_text


def visualize_dataset(
    dataset: LeRobotDataset,
    episode_index: int,
    batch_size: int = 32,
    num_workers: int = 0,
    mode: str = "local",
    web_port: int = 9090,
    ws_port: int = 9087,
    save: bool = False,
    output_dir: Path | None = None,
) -> Path | None:
    if save:
        assert output_dir is not None, (
            "Set an output directory where to write .rrd files with `--output-dir path/to/directory`."
        )

    repo_id = dataset.repo_id

    logging.info("Loading dataloader")
    episode_sampler = EpisodeSampler(dataset, episode_index)
    dataloader = torch.utils.data.DataLoader(
        dataset,
        num_workers=num_workers,
        batch_size=batch_size,
        sampler=episode_sampler,
    )

    logging.info("Starting Rerun")

    if mode not in ["local", "distant"]:
        raise ValueError(mode)

    spawn_local_viewer = mode == "local" and not save
    rr.init(f"{repo_id}/episode_{episode_index}", spawn=spawn_local_viewer)

    # Manually call python garbage collector after `rr.init` to avoid hanging in a blocking flush
    # when iterating on a dataloader with `num_workers` > 0
    # TODO(rcadene): remove `gc.collect` when rerun version 0.16 is out, which includes a fix
    gc.collect()

    if mode == "distant":
        rr.serve(open_browser=False, web_port=web_port, ws_port=ws_port)

    logging.info("Logging to Rerun")

    for batch in tqdm.tqdm(dataloader, total=len(dataloader)):
        # iterate over the batch
        for i in range(len(batch["index"])):
            rr.set_time_sequence("frame_index", batch["frame_index"][i].item())
            rr.set_time_seconds("timestamp", batch["timestamp"][i].item())

            # display each camera image
            for key in dataset.meta.camera_keys:
                # TODO(rcadene): add `.compress()`? is it lossless?
                rr.log(key, rr.Image(to_hwc_uint8_numpy(batch[key][i])))

            # display each dimension of action space (e.g. actuators command)
            if "action" in batch:
                for dim_idx, val in enumerate(batch["action"][i]):
                    rr.log(f"action/{dim_idx}", rr.Scalar(val.item()))

            # display each dimension of observed state space (e.g. agent position in joint space)
            if "observation.state" in batch:
                for dim_idx, val in enumerate(batch["observation.state"][i]):
                    rr.log(f"state/{dim_idx}", rr.Scalar(val.item()))

            if "next.done" in batch:
                rr.log("next.done", rr.Scalar(batch["next.done"][i].item()))

            if "next.reward" in batch:
                rr.log("next.reward", rr.Scalar(batch["next.reward"][i].item()))

            if "next.success" in batch:
                rr.log("next.success", rr.Scalar(batch["next.success"][i].item()))

            annotation_text = get_annotation_text(batch, i)
            if annotation_text:
                rr.log("annotations", rr.TextLog(annotation_text))

    if mode == "local" and save:
        # save .rrd locally
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        repo_id_str = repo_id.replace("/", "_")
        rrd_path = output_dir / f"{repo_id_str}_episode_{episode_index}.rrd"
        rr.save(rrd_path)
        return rrd_path

    if mode == "distant":
        # stop the process from exiting since it is serving the websocket connection
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Ctrl-C received. Exiting.")

    return None
