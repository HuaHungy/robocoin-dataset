# 为后续的yaml文件生成和README生成，以及网页的元信息收集做准备。
# 将所有的字段和名称记录下来之后，进行最终的更新和修改
# 1. 首先根据yaml文件记录字段和对应的值，如果值为空则一样赋值为空但是记录有这样一个字段，保存为字典
# 2. 然后分为三部分：
#   1. 基础信息：dataset_name根据文件夹的名字给出, dataset_uuid根据数据库中的信息给出, device_model根据文件名的前半段给出, end_effector_type根据数据库的字段给出,
#              operation_platform_height根据数据库中的信息给出，如果没有则赋值null
#   2. 多对多信息：scene_type, task_descriptions, atomic_actions, objects
#   3. 单对单信息：yaml_file_path, data_path, convert_path
# 3. 然后根据数据库中的信息，进行最终的更新和修改
# 4. 最后生成yaml文件和README文件


def collect_correct_metadata(yaml_path: str, database_file_path: str) -> None:
    # 1. 首先根据yaml文件记录字段和对应的值，如果值为空则一样赋值为空但是记录有这样一个字段，保存为字典
    # 2. 然后分为三部分：
    #   1. 基础信息：dataset_name, dataset_uuid, device_model, end_effector_type, operation_platform_height
    #   2. 多对多信息：scene_type, task_descriptions, atomic_actions, objects
    pass
