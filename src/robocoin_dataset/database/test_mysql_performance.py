from pathlib import Path
import time
import random
import string
from contextlib import contextmanager
import sys

# 导入你的数据库类（适配PostgreSQL）
sys.path.append(str(Path(__file__).parent))  # 加入项目根目录
from robocoin_dataset.database.database import DatasetDatabase  # 已改为PostgreSQL版本
from robocoin_dataset.database.models import AtomicActionDB

# ===================== 工具函数 =====================
@contextmanager
def timer(operation_name: str):
    """计时上下文管理器，输出操作耗时"""
    start = time.perf_counter()
    yield
    end = time.perf_counter()
    print(f"✅ {operation_name} 耗时: {end - start:.4f} 秒")

def generate_random_action_name(length: int = 10) -> str:
    """生成随机action_name，用于测试插入（确保唯一）"""
    return 'pg_test_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

# ===================== 核心测试函数 =====================
def test_postgresql_performance(config_path: str):
    """
    测试PostgreSQL读写性能（针对atomic_actions表）
    :param config_path: postgresql_config.yaml的路径
    """
    # 1. 初始化数据库连接
    print("===== 初始化数据库连接 =====")
    with timer("数据库连接初始化"):
        db = DatasetDatabase(db_file=config_path)  # 关键：适配PostgreSQL类的db_file参数

    # 测试数据（随机生成，带pg_test前缀，避免污染真实数据）
    test_action_names = [generate_random_action_name() for _ in range(100)]
    test_action_name = test_action_names[0]

    # 2. 测试查询性能（分3类查询）
    print("\n===== 测试查询性能 =====")
    # 2.1 全表查询
    with timer("全表查询（所有action_name）"):
        with db.with_session() as session:
            all_actions = session.query(AtomicActionDB).all()
            print(f"  - 全表数据量: {len(all_actions)}")

    # 2.2 单条精准查询（按action_name）
    if all_actions:
        target_name = all_actions[0].action_name
        with timer(f"单条精准查询（action_name='{target_name}'）"):
            with db.with_session() as session:
                action = session.query(AtomicActionDB).filter_by(action_name=target_name).first()
                print(f"  - 查询结果: {action.action_name if action else '无'}")

    # 2.3 批量查询（IN条件）
    if len(all_actions) >= 10:
        batch_names = [a.action_name for a in all_actions[:10]]
        with timer(f"批量查询（10个action_name IN条件）"):
            with db.with_session() as session:
                actions = session.query(AtomicActionDB).filter(AtomicActionDB.action_name.in_(batch_names)).all()
                print(f"  - 批量查询结果数: {len(actions)}")

    # 3. 测试插入性能（分2类插入）
    print("\n===== 测试插入性能 =====")
    # 3.1 单条插入
    with timer("单条插入（1个action_name）"):
        with db.with_session() as session:
            new_action = AtomicActionDB(action_name=test_action_name)
            session.add(new_action)
            # 无需手动commit：DatasetDatabase的with_session已自动commit

    # 3.2 批量插入（100条）- PostgreSQL批量插入优化
    with timer("批量插入（100个action_name）"):
        with db.with_session() as session:
            new_actions = [AtomicActionDB(action_name=name) for name in test_action_names[1:]]
            session.add_all(new_actions)
            # 无需手动commit：with_session自动处理

    # 4. 测试更新性能
    print("\n===== 测试更新性能 =====")
    with timer(f"单条更新（action_name='{test_action_name}'）"):
        with db.with_session() as session:
            action = session.query(AtomicActionDB).filter_by(action_name=test_action_name).first()
            if action:
                action.action_name = f"{test_action_name}_updated"
                print(f"  - 更新后名称: {action.action_name}")

    # 5. 测试删除性能
    print("\n===== 测试删除性能 =====")
    # 5.1 单条删除
    updated_name = f"{test_action_name}_updated"
    with timer(f"单条删除（action_name='{updated_name}'）"):
        with db.with_session() as session:
            action = session.query(AtomicActionDB).filter_by(action_name=updated_name).first()
            if action:
                session.delete(action)
                print(f"  - 成功删除单条记录")

    # 5.2 批量删除（清理测试数据）- PostgreSQL适配synchronize_session参数
    with timer("批量删除（100条测试数据）"):
        with db.with_session() as session:
            # 匹配测试生成的随机名称（带pg_test前缀）
            test_names = test_action_names[1:]
            # PostgreSQL推荐使用synchronize_session='fetch'或False
            session.query(AtomicActionDB).filter(AtomicActionDB.action_name.in_(test_names)).delete(
                synchronize_session='fetch'  # 适配PostgreSQL的参数
            )
            print(f"  - 成功清理测试数据")

    # 6. 总结性能数据（适配PostgreSQL的性能基准）
    print("\n===== 性能测试总结 =====")
    print("📌 PostgreSQL操作耗时参考（本地/局域网正常范围）：")
    print("   - 连接初始化: < 0.1 秒（超过0.3秒说明配置/服务问题）")
    print("   - 单条查询: < 0.01 秒（PostgreSQL查询性能优于MySQL）")
    print("   - 单条插入: < 0.02 秒（事务提交效率更高）")
    print("   - 批量插入100条: < 0.2 秒（PostgreSQL批量写入优化更好）")

if __name__ == "__main__":
    # 配置文件路径（替换为你的PostgreSQL配置文件路径）
    CONFIG_PATH = "/home/liuyou/Documents/robocoin-dataset/db/postgresql_config.yaml"
    
    # 运行性能测试
    try:
        test_postgresql_performance(CONFIG_PATH)
    except Exception as e:
        print(f"❌ 性能测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
