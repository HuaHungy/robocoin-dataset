#!/usr/bin/env python3
import argparse
from pathlib import Path
from importlib import import_module

from robocoin_dataset.sim_replay.sim_replay import _sim_replay_dataset

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo_path", required=True, help="Path to the converted dataset (leformat)")
    p.add_argument("--config_module", required=True, help="Python module path for replay config, e.g. mypkg.configs.my_cfg_module")
    p.add_argument("--config_class", required=True, help="Class name inside module, e.g. MySimReplayConfig")
    args = p.parse_args()

    repo = Path(args.repo_path).expanduser().absolute()
    mod = import_module(args.config_module)
    cfg_cls = getattr(mod, args.config_class)
    cfg = cfg_cls()
    _sim_replay_dataset(repo, cfg)

if __name__ == '__main__':
    main()