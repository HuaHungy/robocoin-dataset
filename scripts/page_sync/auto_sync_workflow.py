#!/usr/bin/env python3
"""
本脚本是进行网页同步的自动化工作流。

一个标准的执行命令是(示例):
python scripts/page_sync/auto_sync_workflow.py \
  --db-path /mnt/db/datasets_new.db \
  --target-dir /home/rogerspyke/projects \
  --git-dir /home/rogerspyke/projects/DataManager \
  --log-level INFO \
  --update-videos \
  --crf 30 \
  --run-once

脚本的流程是:
1. 每隔固定时间(默认 2 小时)执行一次完整的同步流程:
   1) 调用页面同步逻辑,在 target-dir 中生成网页项目所需的 YAML 和视频资源
   2) 将生成的 assets 文件夹复制到 git-dir 的 docs/assets 目录（强制覆写）
   3) 在命令完成之后,对指定挂载路径执行挂载
   4) 在 git-dir 中执行 git add、git commit 和 git push
      - 只添加 docs/assets 目录的变更
      - commit 信息默认为: "automatic sync assets for page project (X datasets)"
      - push 到指定分支(默认 main),以触发 GitHub Actions 刷新网页资源

2. 你可以通过 --interval-hours 参数修改同步间隔,也可以使用 --run-once 先调试单次流程。

注意:
- 挂载操作默认执行: mount <mount-path>
  - 默认 mount-path 为 /home/rogerspyke/projects
  - 如果你的环境不同,可以通过 --mount-path 参数进行修改
  - 挂载前,请确保 /etc/fstab 或权限配置正确,否则 mount 可能需要 sudo 或失败
- git push 默认使用远端 origin 和分支 main,可通过 --git-remote 和 --git-branch 参数调整

cd /home/rogerspyke/projects/robocoin-dataset

python scripts/page_sync/auto_sync_workflow.py \
  --db-path /mnt/db/datasets_new.db \
  --target-dir /home/rogerspyke/projects \
  --git-dir /home/rogerspyke/projects/DataManager \
  --log-level INFO \
  --update-videos \
  --crf 30 \
  --run-once

python scripts/page_sync/auto_sync_workflow.py \
  --db-path /mnt/db/datasets_new.db \
  --target-dir /home/rogerspyke/projects \
  --git-dir /home/rogerspyke/projects/DataManager \
  --log-level INFO \
  --update-videos \
  --crf 30

nohup python scripts/page_sync/auto_sync_workflow.py \
  --db-path /mnt/db/datasets_new.db \
  --target-dir /home/rogerspyke/projects \
  --git-dir /home/rogerspyke/projects/DataManager \
  --log-level INFO \
  --update-videos \
  --crf 30 \
  > auto_sync.log 2>&1 &
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SyncConfig:
    db_path: Path
    target_dir: Path
    git_dir: Path
    crf: int
    update_videos: bool
    log_level: str
    interval_hours: float
    mount_path: Path
    git_remote: str
    git_branch: str
    git_commit_message: str
    git_username: str | None
    git_token: str | None
    run_once: bool


def _run_subprocess(
    cmd: list[str] | str,
    *,
    cwd: Path | None = None,
    check: bool = True,
    shell: bool | None = None,
) -> subprocess.CompletedProcess:
    """
    Helper to run a subprocess with logging.

    Args:
        cmd: Command to run (list or string when shell=True)
        cwd: Working directory
        check: Whether to raise on non-zero exit
        shell: Whether to run through shell (defaults to False when cmd is list)
    """
    if isinstance(cmd, list):
        cmd_display = " ".join(cmd)
    else:
        cmd_display = cmd

    logger.debug("Running command: %s (cwd=%s)", cmd_display, cwd or ".")

    if shell is None:
        shell = isinstance(cmd, str)

    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd is not None else None,
        check=False,  # we'll handle check manually
        shell=shell,
        capture_output=True,
        text=True,
    )

    if result.stdout:
        logger.debug("Command stdout:\n%s", result.stdout)
    if result.stderr:
        logger.debug("Command stderr:\n%s", result.stderr)

    if check and result.returncode != 0:
        logger.error("Command failed with exit code %s: %s", result.returncode, cmd_display)
        raise subprocess.CalledProcessError(
            result.returncode,
            cmd_display,
            output=result.stdout,
            stderr=result.stderr,
        )

    return result


def _run_page_sync(config: SyncConfig) -> None:
    """调用页面同步逻辑,生成/更新页面项目所需资源。"""
    logger.info("Starting page sync...")
    logger.info("  Database: %s", config.db_path)
    logger.info("  Target dir: %s", config.target_dir)
    logger.info("  CRF: %s", config.crf)
    logger.info("  Update videos: %s", config.update_videos)

    # 复用与 prepare_page_sync_files.py 相同的入口
    from robocoin_dataset.page_sync.page_sync import main as page_sync_main

    page_sync_main(
        db_path=str(config.db_path),
        target_dir=str(config.target_dir),
        crf=config.crf,
        update_videos=config.update_videos,
        log_level=config.log_level,
    )

    logger.info("Page sync completed successfully.")


def _run_mount(config: SyncConfig) -> None:
    """对指定路径执行挂载操作(如果需要)。"""
    if not config.mount_path:
        logger.debug("No mount path specified, skipping mount step.")
        return

    logger.info("Mounting path: %s", config.mount_path)

    try:
        _run_subprocess(["mount", str(config.mount_path)], check=True)
        logger.info("Mount completed: %s", config.mount_path)
    except subprocess.CalledProcessError as exc:
        logger.error(
            "Mount command failed for %s (exit=%s). Please check fstab/permissions.",
            config.mount_path,
            exc.returncode,
        )
        # 挂载失败不阻塞后续 git 步骤,但记录错误


def _copy_assets_to_git_dir(config: SyncConfig) -> None:
    """复制 assets 文件夹到 git 目录的 docs/assets 目录（强制覆写）。"""
    source_assets = config.target_dir / "docs" / "assets"
    target_assets = config.git_dir / "docs" / "assets"

    if not source_assets.exists():
        logger.warning("Source assets directory does not exist: %s", source_assets)
        return

    logger.info("Copying assets from %s to %s (force overwrite)", source_assets, target_assets)

    try:
        # 确保目标目录存在
        target_assets.parent.mkdir(parents=True, exist_ok=True)

        # 强制覆写：如果目标目录存在，先删除再复制
        if target_assets.exists():
            import shutil
            shutil.rmtree(target_assets)

        # 使用 rsync 进行复制，如果 rsync 不可用则使用 cp
        try:
            _run_subprocess(["rsync", "-av", "--delete", str(source_assets) + "/", str(target_assets)], check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            # rsync 不可用，使用 shutil
            import shutil
            shutil.copytree(source_assets, target_assets)

        logger.info("Assets copy completed successfully to %s", target_assets)

    except Exception as exc:
        logger.error("Failed to copy assets to git directory: %s", exc)
        raise


def _count_datasets(db_path: Path) -> int:
    """统计数据库中已同步完成 (COMPLETED) 的数据集数量。

    这个计数代表了数据库中标记为已完成页面同步的数据集总数。
    """
    try:
        from robocoin_dataset.database.database import DatasetDatabase
        from robocoin_dataset.database.models import DatasetDB, TaskStatus

        db = DatasetDatabase(str(db_path))
        with db.with_session() as session:
            completed_count = session.query(DatasetDB).filter(
                DatasetDB.dataset_info_sync_status == TaskStatus.COMPLETED
            ).count()

        logger.info("Database shows %d datasets marked as COMPLETED", completed_count)
        return completed_count
    except Exception as e:
        logger.warning("Failed to query database for completed datasets: %s", e)
        return 0


def _setup_git_auth(config: SyncConfig) -> None:
    """设置 git 认证信息，避免交互式输入。"""
    if not config.git_username or not config.git_token:
        logger.debug("No git credentials provided, using default authentication (SSH or stored credentials)")
        return

    # 设置 git credential helper 来存储 token
    import os
    os.environ['GIT_USERNAME'] = config.git_username
    os.environ['GIT_TOKEN'] = config.git_token

    # 创建一个简单的 credential helper 脚本
    credential_script = """#!/bin/bash
echo "username=$GIT_USERNAME"
echo "password=$GIT_TOKEN"
"""
    credential_path = Path.home() / ".git_credential_helper.sh"
    credential_path.write_text(credential_script)
    credential_path.chmod(0o755)

    logger.info("Git credentials configured for user: %s", config.git_username)


def _run_git_sync(config: SyncConfig) -> None:
    """在目标目录执行 git add/commit/push,用于触发 GitHub Actions。

    只添加 assets 目录下的文件，确保不会修改 README 或其他文件。
    """
    target_dir = config.target_dir

    logger.info("Running git sync in %s", target_dir)

    # 0) 设置认证（如果提供了凭据）
    _setup_git_auth(config)

    # 1) 只添加 docs/assets 目录，确保不会修改 README 或其他文件
    assets_path = target_dir / "docs" / "assets"
    if not assets_path.exists():
        logger.warning("Assets directory does not exist at %s. Skipping git add.", assets_path)
        return

    logger.info("Adding docs/assets directory to git")
    # 使用相对路径，相对于 target_dir
    _run_subprocess(["git", "add", "docs/assets/"], cwd=target_dir, check=True)

    # 2) 检查是否有 staged 变更,没有则跳过 commit/push
    diff_result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=str(target_dir),
    )

    if diff_result.returncode == 0:
        logger.info("No changes to commit. Skipping git commit and push.")
        return
    if diff_result.returncode not in (0, 1):
        logger.warning(
            "Unexpected return code from 'git diff --cached --quiet': %s. "
            "Will still attempt to commit/push.",
            diff_result.returncode,
        )

    # 3) 计算数据集数量并更新提交信息
    dataset_count = _count_datasets(config.db_path)
    commit_message = f"{config.git_commit_message} ({dataset_count} datasets)"

    # 4) git commit
    _run_subprocess(
        ["git", "commit", "-m", commit_message],
        cwd=target_dir,
        check=True,
    )
    logger.info("Git commit created with message: %s", commit_message)

    # 5) git push
    push_cmd = ["git", "push", config.git_remote, config.git_branch]

    # 如果提供了凭据，使用 credential helper
    if config.git_username and config.git_token:
        env = os.environ.copy()
        env['GIT_ASKPASS'] = str(Path.home() / ".git_credential_helper.sh")
        result = subprocess.run(
            push_cmd,
            cwd=str(target_dir),
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error("Git push failed: %s", result.stderr)
            raise subprocess.CalledProcessError(result.returncode, push_cmd, result.stdout, result.stderr)
    else:
        _run_subprocess(push_cmd, cwd=target_dir, check=True)

    logger.info(
        "Git push completed to %s/%s. GitHub Actions (if configured) should be triggered.",
        config.git_remote,
        config.git_branch,
    )


def _run_git_sync_in_git_dir(config: SyncConfig) -> None:
    """在 git 目录执行 git add/commit/push,用于触发 GitHub Actions。

    只添加 docs/assets 目录下的文件，确保不会修改 README 或其他文件。
    """
    git_dir = config.git_dir

    logger.info("Running git sync in git directory: %s", git_dir)

    # 0) 设置认证（如果提供了凭据）
    _setup_git_auth(config)

    # 1) 只添加 docs/assets 目录，确保不会修改 README 或其他文件
    assets_path = git_dir / "docs" / "assets"
    if not assets_path.exists():
        logger.warning("Assets directory does not exist in git dir at %s. Skipping git add.", assets_path)
        return

    logger.info("Adding docs/assets directory to git")
    # 使用相对路径，相对于 git_dir
    _run_subprocess(["git", "add", "docs/assets/"], cwd=git_dir, check=True)

    # 2) 检查是否有 staged 变更,没有则跳过 commit/push
    diff_result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=str(git_dir),
    )

    if diff_result.returncode == 0:
        logger.info("No changes to commit in git directory. Skipping git commit and push.")
        return
    if diff_result.returncode not in (0, 1):
        logger.warning(
            "Unexpected return code from 'git diff --cached --quiet': %s. "
            "Will still attempt to commit/push.",
            diff_result.returncode,
        )

    # 3) 计算数据集数量并更新提交信息
    dataset_count = _count_datasets(config.db_path)
    commit_message = f"{config.git_commit_message} ({dataset_count} datasets)"

    # 4) git commit
    _run_subprocess(
        ["git", "commit", "-m", commit_message],
        cwd=git_dir,
        check=True,
    )
    logger.info("Git commit created with message: %s", commit_message)

    # 5) git push
    push_cmd = ["git", "push", config.git_remote, config.git_branch]

    # 如果提供了凭据，使用 credential helper
    if config.git_username and config.git_token:
        env = os.environ.copy()
        env['GIT_ASKPASS'] = str(Path.home() / ".git_credential_helper.sh")
        result = subprocess.run(
            push_cmd,
            cwd=str(git_dir),
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error("Git push failed: %s", result.stderr)
            raise subprocess.CalledProcessError(result.returncode, push_cmd, result.stdout, result.stderr)
    else:
        _run_subprocess(push_cmd, cwd=git_dir, check=True)

    logger.info(
        "Git push completed to %s/%s. GitHub Actions (if configured) should be triggered.",
        config.git_remote,
        config.git_branch,
    )


def _run_single_cycle(config: SyncConfig) -> None:
    """执行一次完整的同步 + 挂载 + 复制到git目录 + git 流程。"""
    start_time = datetime.now()
    logger.info("===== Starting auto sync cycle at %s =====", start_time.isoformat(timespec="seconds"))

    try:
        _run_page_sync(config)
    except Exception:  # noqa: BLE001
        logger.exception("Page sync step failed.")
        # 失败时仍然尝试继续执行后续步骤,以便挂载/推送其他变更(如果需要)

    try:
        _copy_assets_to_git_dir(config)
    except Exception:  # noqa: BLE001
        logger.exception("Assets copy to git directory step failed.")

    try:
        _run_mount(config)
    except Exception:  # noqa: BLE001
        logger.exception("Mount step failed.")

    try:
        _run_git_sync_in_git_dir(config)
    except subprocess.CalledProcessError:
        logger.exception("Git sync step failed.")
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected error during git sync step.")

    end_time = datetime.now()
    logger.info(
        "===== Auto sync cycle finished at %s (duration: %s) =====",
        end_time.isoformat(timespec="seconds"),
        end_time - start_time,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Auto workflow for syncing dataset info to page project and pushing changes to GitHub.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 每 2 小时自动同步一次,在 target-dir 生成文件,复制到 git-dir 并推送
  python scripts/page_sync/auto_sync_workflow.py \\
    --db-path /mnt/db/datasets_new.db \\
    --target-dir /home/rogerspyke/projects \\
    --git-dir /home/rogerspyke/projects/DataManager \\
    --log-level INFO \\
    --update-videos \\
    --crf 30

  # 只运行一次,用于调试
  python scripts/page_sync/auto_sync_workflow.py \\
    --db-path /mnt/db/datasets_new.db \\
    --target-dir /home/rogerspyke/projects \\
    --git-dir /home/rogerspyke/projects/DataManager \\
    --run-once

  # 修改同步间隔为每 3 小时,并显式指定挂载路径
  python scripts/page_sync/auto_sync_workflow.py \\
    --db-path /mnt/db/datasets_new.db \\
    --target-dir /home/rogerspyke/projects \\
    --git-dir /home/rogerspyke/projects/page-repo \\
    --mount-path /home/rogerspyke/projects \\
    --interval-hours 3

  # 如果需要使用 HTTPS 认证而非 SSH,可以提供 GitHub token
  python scripts/page_sync/auto_sync_workflow.py \\
    --db-path /mnt/db/datasets_new.db \\
    --target-dir /home/rogerspyke/projects \\
    --git-dir /home/rogerspyke/projects/page-repo \\
    --git-username your-github-username \\
    --git-token your-personal-access-token
        """,
    )

    parser.add_argument(
        "--db-path",
        type=str,
        required=True,
        help="Path to the SQLite database file (e.g., /mnt/db/datasets_new.db)",
    )
    parser.add_argument(
        "--target-dir",
        type=str,
        required=True,
        help="Root directory of the page project where assets are located and git operations run",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=23,
        help="CRF value for video compression (default: 23, range: 0-51, lower = better quality)",
    )
    parser.add_argument(
        "--update-videos",
        action="store_true",
        help="Force regenerate videos and thumbnails even if they exist (default: False)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--interval-hours",
        type=float,
        default=2.0,
        help="Interval between sync cycles in hours (default: 2.0)",
    )
    parser.add_argument(
        "--mount-path",
        type=str,
        default="/home/rogerspyke/projects",
        help="Path to mount before git sync (default: /home/rogerspyke/projects). "
        "If this path is not needed in your environment, you can still leave it and rely on /etc/fstab, "
        "or set it to the same as --target-dir.",
    )
    parser.add_argument(
        "--git-remote",
        type=str,
        default="origin",
        help="Git remote name to push to (default: origin)",
    )
    parser.add_argument(
        "--git-branch",
        type=str,
        default="main",
        help="Git branch to push to (default: main)",
    )
    parser.add_argument(
        "--git-commit-message",
        type=str,
        default="automatic sync assets for page project",
        help='Commit message used for automatic sync (default: "automatic sync assets for page project")',
    )
    parser.add_argument(
        "--git-username",
        type=str,
        help="GitHub username for authentication (optional, uses SSH if not provided)",
    )
    parser.add_argument(
        "--git-token",
        type=str,
        help="GitHub personal access token for authentication (optional, uses SSH if not provided)",
    )
    parser.add_argument(
        "--git-dir",
        type=str,
        required=True,
        help="Directory where git operations (add/commit/push) will be performed",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run a single sync cycle and exit (useful for debugging).",
    )

    return parser.parse_args(argv)


def _build_config(args: argparse.Namespace) -> SyncConfig:
    db_path = Path(args.db_path).expanduser().absolute()
    target_dir = Path(args.target_dir).expanduser().absolute()
    git_dir = Path(args.git_dir).expanduser().absolute()
    mount_path = Path(args.mount_path).expanduser().absolute()

    # 基本路径校验
    if not db_path.exists():
        print(f"Error: Database file not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    if not target_dir.exists():
        print(f"Error: Target directory not found: {target_dir}", file=sys.stderr)
        print("Please create the directory first or check the path.", file=sys.stderr)
        sys.exit(1)

    if not target_dir.is_dir():
        print(f"Error: Target path is not a directory: {target_dir}", file=sys.stderr)
        sys.exit(1)

    if not git_dir.exists():
        print(f"Error: Git directory not found: {git_dir}", file=sys.stderr)
        print("Please create the directory first or check the path.", file=sys.stderr)
        sys.exit(1)

    if not git_dir.is_dir():
        print(f"Error: Git path is not a directory: {git_dir}", file=sys.stderr)
        sys.exit(1)

    if args.interval_hours <= 0:
        print("Error: --interval-hours must be positive.", file=sys.stderr)
        sys.exit(1)

    return SyncConfig(
        db_path=db_path,
        target_dir=target_dir,
        git_dir=git_dir,
        crf=args.crf,
        update_videos=args.update_videos,
        log_level=args.log_level,
        interval_hours=args.interval_hours,
        mount_path=mount_path,
        git_remote=args.git_remote,
        git_branch=args.git_branch,
        git_commit_message=args.git_commit_message,
        git_username=args.git_username,
        git_token=args.git_token,
        run_once=args.run_once,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    # Setup logging
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = _build_config(args)

    logger.info("Auto sync workflow starting with configuration:")
    logger.info("  db_path: %s", config.db_path)
    logger.info("  target_dir: %s", config.target_dir)
    logger.info("  git_dir: %s", config.git_dir)
    logger.info("  crf: %s", config.crf)
    logger.info("  update_videos: %s", config.update_videos)
    logger.info("  interval_hours: %s", config.interval_hours)
    logger.info("  mount_path: %s", config.mount_path)
    logger.info("  git_remote: %s", config.git_remote)
    logger.info("  git_branch: %s", config.git_branch)
    logger.info("  git_commit_message: %s", config.git_commit_message)
    logger.info("  git_username: %s", config.git_username or "Not set (using SSH)")
    logger.info("  git_token: %s", "***" if config.git_token else "Not set (using SSH)")

    if config.run_once:
        logger.info("Running in single-cycle mode (--run-once).")
        _run_single_cycle(config)
        return 0

    logger.info("Entering loop mode. Sync will run every %.2f hours.", config.interval_hours)

    interval_seconds = config.interval_hours * 3600

    try:
        while True:
            _run_single_cycle(config)
            logger.info("Sleeping for %.2f hours before next cycle.", config.interval_hours)
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt, exiting auto sync workflow.")
        return 0
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected fatal error in auto sync workflow.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
