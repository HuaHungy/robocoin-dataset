from pathlib import Path

import yaml

from robocoin_dataset.annotation.device_model_annotation.constant import (
    DEVICE_MODEL_ANNOTATION_FILE_NAME,
    DEVICE_MODEL_VERSION,
)
from robocoin_dataset.database.database import DatasetDatabase
from robocoin_dataset.database.models import (
    DatasetDB,
)


def annotate_device_model(db_file_path: Path) -> None:
    if not db_file_path.exists():
        raise FileNotFoundError
    db = DatasetDatabase(db_file=db_file_path)
    with db.with_session() as session:
        items = session.query(DatasetDB).filter(DatasetDB.device_model_version.is_(None)).all()
        items = session.query(DatasetDB).all()

        for item in items:
            dataset_path = Path(item.yaml_file_path).parent
            dmv_annotation_file_path = dataset_path / DEVICE_MODEL_ANNOTATION_FILE_NAME
            if Path(dmv_annotation_file_path).exists():
                with open(dmv_annotation_file_path) as f:
                    data = yaml.safe_load(f)
                    device_model_version = data.get(DEVICE_MODEL_VERSION, "")

            if device_model_version:
                item.device_model_version = device_model_version

        session.commit()
