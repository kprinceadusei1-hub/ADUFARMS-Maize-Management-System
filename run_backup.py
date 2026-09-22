"""Create and verify a scheduled ADUFARMS database backup."""
import os
import shutil
from pathlib import Path

import backup_service


BASE_DIR = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "adufarms.db"))
OFFSITE_DIR = os.environ.get("ADUFARMS_OFFSITE_BACKUP_DIR")


def main() -> None:
    backup = backup_service.create_backup(DATABASE)
    print(f"Created verified backup: {backup}")

    if not OFFSITE_DIR:
        print("Warning: ADUFARMS_OFFSITE_BACKUP_DIR is not configured; backup is local only.")
        return

    destination = Path(OFFSITE_DIR)
    destination.mkdir(parents=True, exist_ok=True)
    for source in (backup, backup.with_suffix(".json")):
        temporary = destination / f"{source.name}.tmp"
        shutil.copy2(source, temporary)
        os.replace(temporary, destination / source.name)
    backup_service.verify_backup(destination / backup.name)
    print(f"Verified off-site copy: {destination / backup.name}")


if __name__ == "__main__":
    main()
