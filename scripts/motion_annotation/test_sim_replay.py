import argparse

from robocoin_dataset.annotation.motion_annotation.configs.realman_rmc_aidal_config import (
    RealmanRmcAidalLerobotSimReplayConfig,
)
from robocoin_dataset.annotation.motion_annotation.lerobot_sim_replay import (
    LerobotSimReplay,
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("repo_path", type=str)

    parser.add_argument("frequency", type=int)

    args = parser.parse_args()

    realman_config = RealmanRmcAidalLerobotSimReplayConfig()
    config = realman_config

    simulator = LerobotSimReplay(config, args.repo_path)
    simulator.start_viewer()
    simulator.load_dataset()
    simulator.replay_episode(0, is_state=True, sleep_time_ms=1000 // args.frequency)
    input("press enter to close")
    simulator.close_viewer()

"""usage:
python scripts/motion_annotation/test_sim_replay.py /mnt/nas/synnas/docker2/robocoin-datasets/agilex_cobot_decoupled_magic_wipe_table/ 30
"""
