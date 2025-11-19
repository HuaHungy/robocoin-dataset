#!/usr/bin/env python3
'''
python scripts/sim_replay/sim_replay_local.py \
  --repo_path /home/kemove/Downloads/mcap_to_lerobot/test \
  --config_module robocoin_dataset.sim_replay.configs.realman_RS_01_config \
  --config_class RealmanRS01LerobotSimReplayConfig \
  --replay_source data
'''
import argparse
from pathlib import Path
from importlib import import_module

from robocoin_dataset.sim_replay.sim_replay import _sim_replay_dataset

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo_path", help="Path to the converted dataset (leformat)")
    p.add_argument("--config_module", required=True, help="Python module path for replay config, e.g. mypkg.configs.my_cfg_module")
    p.add_argument("--config_class", required=True, help="Class name inside module, e.g. MySimReplayConfig")
    # p.add_argument("--episode_path", help="Optional path to a single episode parquet file to replay")
    p.add_argument("--replay_source", default="sa_dpp", help="Index of the episode to replay within the dataset")
    p.add_argument("--episode_idx", type=int, default=0, help="Index of the episode to replay within the dataset")
    args = p.parse_args()

    mod = import_module(args.config_module)
    cfg_cls = getattr(mod, args.config_class)
    cfg = cfg_cls()
    if not args.repo_path:
        p.error("--repo_path is required")
    repo = Path(args.repo_path).expanduser().absolute()
    _sim_replay_dataset(repo, cfg,replay_source=args.replay_source,episode_idx=args.episode_idx)

if __name__ == '__main__':
    main()