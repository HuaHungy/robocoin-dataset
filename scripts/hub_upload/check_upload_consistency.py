#!/usr/bin/env python3
"""
Check upload status consistency with visualize_check_status.

This script verifies that all datasets with COMPLETED upload status:
1. Have visualize_check_status == COMPLETED
2. Have upload_version_ps == visualize_check_version

If all checks pass, returns empty list.
If issues found, returns list of problematic dataset UUIDs.

Usage:
    python scripts/hub_upload/check_upload_consistency.py --db-file-path /path/to/datasets.db

    # Check specific hub
    python scripts/hub_upload/check_upload_consistency.py --db-file-path /path/to/datasets.db --hub huggingface
    python scripts/hub_upload/check_upload_consistency.py --db-file-path /path/to/datasets.db --hub modelscope

    # Check all hubs (default)
    python scripts/hub_upload/check_upload_consistency.py --db-file-path /path/to/datasets.db --hub all
"""

import argparse
import sys
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import inspect  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from robocoin_dataset.database.database import DatasetDatabase  # noqa: E402
from robocoin_dataset.database.models import DatasetDB, TaskStatus  # noqa: E402


class ConsistencyIssue:
    """Represents a data consistency issue."""

    def __init__(
        self,
        dataset_uuid: str,
        dataset_name: str,
        hub: str,
        issue_type: str,
        details: dict[str, Any]
    ) -> None:
        self.dataset_uuid = dataset_uuid
        self.dataset_name = dataset_name
        self.hub = hub
        self.issue_type = issue_type
        self.details = details

    def __str__(self) -> str:
        return (
            f"UUID: {self.dataset_uuid}\n"
            f"  Dataset: {self.dataset_name}\n"
            f"  Hub: {self.hub}\n"
            f"  Issue: {self.issue_type}\n"
            f"  Details: {self.details}"
        )


def check_column_exists(session: Session, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(session.bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def check_single_dataset_consistency(
    session: Session,
    dataset_uuid: str,
    hub_name: str,
    upload_version_ps_field: str
) -> str | None:
    """
    Check consistency for a single dataset (ultra-compact version for inline use).

    Returns:
        Error message if inconsistent, None if consistent
    """
    dataset = session.query(DatasetDB).filter(DatasetDB.dataset_uuid == dataset_uuid).first()
    if not dataset:
        return f"Dataset {dataset_uuid} not found"

    # Check required fields exist
    if not hasattr(dataset, 'visualize_check_status') or not hasattr(dataset, 'visualize_check_version'):
        return None  # Skip check if schema doesn't support it

    # Check visualize_check_status
    if dataset.visualize_check_status != TaskStatus.COMPLETED:
        return f"visualize_check_status={dataset.visualize_check_status}, expected COMPLETED"

    # Check version consistency
    upload_version_ps = getattr(dataset, upload_version_ps_field)
    if upload_version_ps != dataset.visualize_check_version:
        return f"upload_version_ps={upload_version_ps} != visualize_check_version={dataset.visualize_check_version}"

    return None


def check_hub_consistency(
    session: Session,
    hub_name: str,
    upload_status_field: str,
    upload_version_ps_field: str
) -> list[ConsistencyIssue]:
    """
    Check consistency for a specific hub.

    Args:
        session: Database session
        hub_name: Hub name for reporting (e.g., "huggingface", "modelscope")
        upload_status_field: Field name for upload status
        upload_version_ps_field: Field name for upload_version_ps

    Returns:
        List of ConsistencyIssue objects
    """
    issues = []

    print(f"\n{'=' * 80}")
    print(f"Checking {hub_name.upper()} uploads...")
    print(f"{'=' * 80}")

    # Check if required columns exist in the database
    required_columns = [
        upload_status_field,
        upload_version_ps_field,
        'visualize_check_status',
        'visualize_check_version'
    ]

    missing_columns = [col for col in required_columns if not check_column_exists(session, 'datasets', col)]

    if missing_columns:
        print("⚠️  WARNING: The following columns are missing from the database:")
        for col in missing_columns:
            print(f"   - {col}")
        print(f"\n❌ Cannot perform consistency check for {hub_name}.")
        print("   The database schema needs to be updated with these missing columns.")
        print("   This check requires all these fields to exist in the database.\n")
        return issues

    # Query all datasets with COMPLETED upload status for this hub
    upload_status_attr = getattr(DatasetDB, upload_status_field)
    upload_version_ps_attr = getattr(DatasetDB, upload_version_ps_field)

    # Only query the fields we need to avoid schema mismatch issues
    completed_uploads = session.query(
        DatasetDB.dataset_uuid,
        DatasetDB.dataset_name,
        upload_version_ps_attr,
        DatasetDB.visualize_check_status,
        DatasetDB.visualize_check_version
    ).filter(
        upload_status_attr == TaskStatus.COMPLETED
    ).all()

    print(f"Found {len(completed_uploads)} datasets with COMPLETED upload status")

    for row in completed_uploads:
        # Unpack the tuple (dataset_uuid, dataset_name, upload_version_ps, visualize_check_status, visualize_check_version)
        dataset_uuid = row[0]
        dataset_name = row[1]
        upload_version_ps = row[2]
        visualize_check_status = row[3]
        visualize_check_version = row[4]

        # Check 1: visualize_check_status must be COMPLETED
        if visualize_check_status != TaskStatus.COMPLETED:
            issues.append(ConsistencyIssue(
                dataset_uuid=dataset_uuid,
                dataset_name=dataset_name,
                hub=hub_name,
                issue_type="visualize_check_status is not COMPLETED",
                details={
                    "visualize_check_status": visualize_check_status.value if visualize_check_status else "None",
                    "expected": TaskStatus.COMPLETED.value
                }
            ))

        # Check 2: upload_version_ps must equal visualize_check_version
        if upload_version_ps != visualize_check_version:
            issues.append(ConsistencyIssue(
                dataset_uuid=dataset_uuid,
                dataset_name=dataset_name,
                hub=hub_name,
                issue_type="upload_version_ps != visualize_check_version",
                details={
                    "upload_version_ps": upload_version_ps,
                    "visualize_check_version": visualize_check_version,
                    "difference": abs((upload_version_ps or 0) - (visualize_check_version or 0))
                }
            ))

    return issues


def check_all_consistency(db_path: Path, hub_filter: str = "all") -> tuple[list[ConsistencyIssue], bool]:
    """
    Check consistency for all or specific hub(s).

    Args:
        db_path: Path to database file
        hub_filter: Which hub(s) to check ("all", "huggingface", "modelscope")

    Returns:
        Tuple of (list of ConsistencyIssue objects, schema_check_ok)
        schema_check_ok is False if any required columns are missing
    """
    db = DatasetDatabase(db_path)
    all_issues = []
    schema_ok = True

    with db.with_session() as session:
        # First check if visualize_check fields exist
        has_visualize_status = check_column_exists(session, 'datasets', 'visualize_check_status')
        has_visualize_version = check_column_exists(session, 'datasets', 'visualize_check_version')

        if not has_visualize_status or not has_visualize_version:
            schema_ok = False

        hubs_to_check = []

        if hub_filter in ("all", "huggingface"):
            hubs_to_check.append(("huggingface", "huggingface_upload_status", "huggingface_upload_version_ps"))

        if hub_filter in ("all", "modelscope"):
            hubs_to_check.append(("modelscope", "ms_upload_status", "ms_upload_version_ps"))

        for hub_name, status_field, version_ps_field in hubs_to_check:
            issues = check_hub_consistency(session, hub_name, status_field, version_ps_field)
            all_issues.extend(issues)

    return all_issues, schema_ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check upload status consistency with visualize_check_status",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--db-file-path",
        type=str,
        required=True,
        help="Path to the database file"
    )
    parser.add_argument(
        "--hub",
        type=str,
        choices=["all", "huggingface", "modelscope"],
        default="all",
        help="Which hub to check (default: all)"
    )

    args = parser.parse_args()

    # Validate database path
    db_path = Path(args.db_file_path).expanduser().absolute()
    if not db_path.exists():
        print(f"❌ Error: Database file not found: {db_path}", file=sys.stderr)
        return 1
    if not db_path.is_file():
        print(f"❌ Error: Path is not a file: {db_path}", file=sys.stderr)
        return 1

    print(f"\n{'=' * 80}")
    print("UPLOAD CONSISTENCY CHECK")
    print(f"{'=' * 80}")
    print(f"Database: {db_path}")
    print(f"Hub filter: {args.hub}")

    # Run checks
    try:
        issues, schema_ok = check_all_consistency(db_path, args.hub)
    except Exception as e:
        print(f"\n❌ Error during consistency check: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    # Report results
    print(f"\n{'=' * 80}")
    print("RESULTS")
    print(f"{'=' * 80}")

    if not schema_ok:
        print("⚠️  INCOMPLETE CHECK: Database schema is missing required columns.")
        print("    The consistency check could not be performed.")
        print("    Please run database migrations to add the missing columns.")
        print("\n💡 TIP: This means your database is using an older schema.")
        print("    If visualize_check is not part of your workflow, this is expected.")
        return 0

    if not issues:
        print("✅ All checks passed! No consistency issues found.")
        return 0

    print(f"❌ Found {len(issues)} consistency issue(s):\n")

    # Group issues by type
    by_type = {}
    for issue in issues:
        if issue.issue_type not in by_type:
            by_type[issue.issue_type] = []
        by_type[issue.issue_type].append(issue)

    # Print summary
    print("SUMMARY BY ISSUE TYPE:")
    for issue_type, issue_list in by_type.items():
        print(f"  • {issue_type}: {len(issue_list)} dataset(s)")

    # Print detailed issues
    print("\nDETAILED ISSUES:\n")
    for i, issue in enumerate(issues, 1):
        print(f"{i}. {issue}\n")

    # Print UUIDs only (for easy scripting)
    print(f"{'=' * 80}")
    print("PROBLEMATIC DATASET UUIDs:")
    print(f"{'=' * 80}")
    unique_uuids = sorted(set(issue.dataset_uuid for issue in issues))
    for uuid in unique_uuids:
        print(uuid)

    print(f"\nTotal unique datasets with issues: {len(unique_uuids)}")

    return 1


if __name__ == "__main__":
    sys.exit(main())
