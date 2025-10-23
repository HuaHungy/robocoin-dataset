import argparse
from pathlib import Path

from sqlalchemy import text

from robocoin_dataset.database.database import DatasetDatabase

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db_file_path",
        type=str,
        default="",
        help="Path to the database file",
    )

    args = parser.parse_args()
    db_file_path = Path(args.db_file_path).expanduser().absolute()

    db = DatasetDatabase(db_file_path)
    with db.with_session() as session:
        session.execute(
            text("ALTER TABLE lerobot_format_convert ADD COLUMN convert_version_uuid VARCHAR")
        )
        session.commit()


"""usage:
# agilex_cobot_decoupled_magic
python scripts/post_process_parquet/add_lerobot_convert_version_uuid_column.py \
    --db_file_path ./db/datasets.db \

# realman_rmc_aidal
python scripts/post_process_parquet/post_process_parquet.py \
    --db_file_path ./db/datasets.db \
    --parquet_post_processing_factory_config_path ./scripts/post_process_parquet/configs/parquet_post_processing_factory_config.yaml \
    --device_model realman_rmc_aidal \
    --log_dir ./logs/sim_replay

"""
