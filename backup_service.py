"""Admin-only SQLite backup/restore helpers. Never exposed directly via static routes."""
from __future__ import annotations
import shutil
import sqlite3
import os
import hashlib
import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
BACKUP_DIR = Path(os.environ.get("ADUFARMS_BACKUP_DIR", BASE_DIR / "backups"))
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_KEEP_COUNT = max(int(os.environ.get("ADUFARMS_BACKUP_KEEP_COUNT", "90")), 3)


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def list_backups():
    return sorted(BACKUP_DIR.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)


def checksum(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(path: Path) -> None:
    manifest = path.with_suffix(".json")
    manifest.write_text(json.dumps({
        "backup": path.name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "size": path.stat().st_size,
        "sha256": checksum(path),
    }, indent=2), encoding="utf-8")


def verify_backup(path: str | Path) -> None:
    """Verify both SQLite integrity and the optional local checksum manifest."""
    backup = Path(path)
    verify_database(backup)
    manifest = backup.with_suffix(".json")
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("sha256") != checksum(backup):
            raise ValueError(f"Backup checksum failed: {backup.name}")


def prune_backups() -> None:
    """Keep a rolling set of verified snapshots; never delete the newest three."""
    backups = list_backups()
    for old in backups[BACKUP_KEEP_COUNT:]:
        try:
            verify_backup(old)
        except Exception:
            continue
        old.unlink(missing_ok=True)
        old.with_suffix(".json").unlink(missing_ok=True)


def verify_database(db_path: str | Path) -> None:
    """Raise when a SQLite database is missing or fails its integrity check."""
    path = Path(db_path)
    if not path.exists() or path.stat().st_size == 0:
        raise ValueError("Database file is unavailable or empty.")
    conn = sqlite3.connect(str(path))
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise ValueError(f"Database integrity check failed: {result}")
    finally:
        conn.close()


def create_backup(db_path: str | Path) -> Path:
    """Create timestamped backup. Never overwrites existing file (timestamp is unique;
    if collision, append counter). Returns backup path."""
    src = Path(db_path)
    verify_database(src)
    base = f"adufarms_{timestamp()}.db"
    dst = BACKUP_DIR / base
    counter = 1
    while dst.exists():
        dst = BACKUP_DIR / f"adufarms_{timestamp()}_{counter}.db"
        counter += 1
    # Use SQLite backup API for a consistent snapshot, fallback to copy.
    try:
        src_conn = sqlite3.connect(str(src))
        dst_conn = sqlite3.connect(str(dst))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
            src_conn.close()
    except Exception:
        if dst.exists():
            dst.unlink()
        shutil.copy2(src, dst)
    try:
        verify_database(dst)
        _write_manifest(dst)
        verify_backup(dst)
    except Exception:
        if dst.exists():
            dst.unlink()
        dst.with_suffix(".json").unlink(missing_ok=True)
        raise
    prune_backups()
    return dst


def safe_restore(db_path: str | Path, backup_name: str) -> Path:
    """Restore from a backup inside BACKUP_DIR only (prevents path traversal).
    Creates a pre-restore safety backup first. Returns pre-restore backup path."""
    safe = Path(backup_name).name
    src = BACKUP_DIR / safe
    if not src.exists() or src.suffix != ".db":
        raise ValueError("Selected backup is unavailable.")
    if src.resolve().parent != BACKUP_DIR.resolve():
        raise ValueError("Invalid backup selection.")
    verify_backup(src)
    dst = Path(db_path)
    # Safety backup before restore (never silently overwrite the only backup)
    pre = create_backup(dst)
    temporary = dst.with_suffix(dst.suffix + ".restore.tmp")
    try:
        shutil.copy2(src, temporary)
        verify_database(temporary)
        os.replace(temporary, dst)
    finally:
        if temporary.exists():
            temporary.unlink()
    return pre