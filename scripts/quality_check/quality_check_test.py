from robocoin_dataset.quality_check.dataset_quality_check import (
    get_checker_config,
    quality_check_pipeline,
)

if __name__ == "__main__":
    repo_path = "/mnt/nas/synnas/docker2/robocoin-datasets/G1edu-u3_bowl_storage_grape_multitry"
    device_model = "unitree_g1"
    device_model_version = "default_version"
    device_version_config_file = "scripts/quality_check/configs/device_version_checker_config.yaml"
    checker_config = get_checker_config(
        device_model=device_model,
        device_model_version=device_model_version,
        device_verison_config_file=device_version_config_file,
    )
    res, detail_res = quality_check_pipeline(
        repo_path=repo_path, configs=checker_config, data_feature="merged"
    )
    for k, v in detail_res.items():
        print(k)
        for k1, v1 in v.items():
            print(k1, v1)
