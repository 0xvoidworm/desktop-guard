"""User-requested desktop appearance guard. No network, deletion, or elevation."""

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import msvcrt
import os
from pathlib import Path
import stat
import time
import uuid
import winreg


HIDDEN = stat.FILE_ATTRIBUTE_HIDDEN
REPARSE = stat.FILE_ATTRIBUTE_REPARSE_POINT
KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
KERNEL32.SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
KERNEL32.SetFileAttributesW.restype = wintypes.BOOL
NATIVE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\HideDesktopIcons\NewStartPanel"


def hide_path(path, attributes):
    if not KERNEL32.SetFileAttributesW(str(path), attributes | HIDDEN):
        raise ctypes.WinError(ctypes.get_last_error())


class DesktopGuard:
    def __init__(self, config, logger=None):
        self.personal = Path(config["personal_desktop"]).absolute()
        self.public = Path(config["public_desktop"]).absolute()
        self.allowed = {name.casefold() for name in config["allowed_names"]}
        self.output = Path(config["output_dir"]).absolute()
        self.native_ids = config.get("hidden_native_ids", []) if config.get("enforce_native_icons") else []
        self.logger = logger or logging.getLogger("desktop-guard")
        self.pending = {}
        self.last_errors = {}
        self.last_native_check = -100.0
        self.last_status = -100.0
        self.counts = {"hidden": 0, "archived": 0, "errors": 0}
        if self.personal == self.public or self.output in (self.personal, self.public):
            raise ValueError("Unsafe configured roots")
        self.output.mkdir(parents=True, exist_ok=True)

    def record(self, action, path, **fields):
        self.logger.info(json.dumps({"time": datetime.now(timezone.utc).isoformat(), "action": action, "path": str(path), **fields}))

    def error(self, path, message):
        key = str(path)
        now = time.monotonic()
        if now - self.last_errors.get(key, -1000) >= 300:
            self.record("error", path, message=message)
            self.last_errors[key] = now
            self.counts["errors"] += 1

    def archive_public_shortcut(self, path, info):
        # Never relocate folders, user documents, links to folders, or reparse points.
        # A .lnk/.url is moved as a file; its target is never opened or executed.
        if path.parent != self.public or path.suffix.casefold() not in (".lnk", ".url"):
            return False
        if info.st_file_attributes & (stat.FILE_ATTRIBUTE_DIRECTORY | REPARSE):
            return False
        signature = (info.st_size, info.st_mtime_ns)
        previous = self.pending.get(str(path))
        now = time.monotonic()
        if previous is None or previous[0] != signature:
            self.pending[str(path)] = (signature, now)
            return True
        if now - previous[1] < 2:
            return True
        archive = self.output / "PublicDesktop"
        archive.mkdir(exist_ok=True)
        destination = archive / f"{path.stem}-{uuid.uuid4().hex}{path.suffix}"
        if destination.parent != archive or archive.resolve() != self.output.resolve() / "PublicDesktop":
            raise RuntimeError("Unexpected archive target")
        source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        self.record("archive-planned", path, destination=str(destination), sha256=source_hash)
        # Same-volume rename is recoverable and Windows refuses existing targets.
        os.rename(path, destination)
        if hashlib.sha256(destination.read_bytes()).hexdigest() != source_hash:
            raise RuntimeError(f"Archived shortcut changed; preserved at {destination}")
        self.pending.pop(str(path), None)
        self.record("archived", path, destination=str(destination), sha256=source_hash)
        self.counts["archived"] += 1
        return True

    def scan_root(self, root):
        if root.is_symlink() or root.is_junction():
            self.error(root, "Root is a reparse point; skipped")
            return
        try:
            entries = list(root.iterdir())
        except OSError as exc:
            self.error(root, str(exc))
            return
        for path in entries:
            if root == self.personal and path.name.casefold() in self.allowed:
                continue
            try:
                info = path.lstat()
                attributes = info.st_file_attributes
                if attributes & HIDDEN:
                    continue
                if attributes & REPARSE:
                    self.error(path, "Reparse point skipped to preserve its target")
                    continue
                try:
                    hide_path(path, attributes)
                except OSError:
                    if root == self.public and self.archive_public_shortcut(path, info):
                        continue
                    raise
                self.record("hidden", path, previous_attributes=attributes)
                self.counts["hidden"] += 1
            except FileNotFoundError:
                self.pending.pop(str(path), None)
            except (OSError, RuntimeError) as exc:
                self.error(path, str(exc))

    def maintain_native_icons(self):
        if not self.native_ids:
            return
        try:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, NATIVE_KEY, 0, winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
                for identifier in self.native_ids:
                    try:
                        previous, value_type = winreg.QueryValueEx(key, identifier)
                    except FileNotFoundError:
                        previous, value_type = None, None
                    if previous != 1 or value_type != winreg.REG_DWORD:
                        winreg.SetValueEx(key, identifier, 0, winreg.REG_DWORD, 1)
                        self.record("native-icon-hidden", identifier, previous_value=previous)
        except OSError as exc:
            self.error(NATIVE_KEY, str(exc))

    def scan(self):
        self.scan_root(self.personal)
        self.scan_root(self.public)
        now = time.monotonic()
        if now - self.last_native_check >= 30:
            self.maintain_native_icons()
            self.last_native_check = now
        if now - self.last_status >= 30:
            data = {"pid": os.getpid(), "last_scan_utc": datetime.now(timezone.utc).isoformat(), "counts": self.counts, "allowed": sorted(self.allowed)}
            temporary = self.output / "status.tmp"
            temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
            temporary.replace(self.output / "status.json")
            self.last_status = now


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    output = Path(config["output_dir"])
    output.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("desktop-guard")
    logger.setLevel(logging.INFO)
    logger.addHandler(RotatingFileHandler(output / "events.jsonl", maxBytes=1048576, backupCount=2, encoding="utf-8"))
    # A held file lock prevents duplicate processes, including repeated startup.
    with (output / "instance.lock").open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return
        guard = DesktopGuard(config, logger)
        guard.record("started", args.config, pid=os.getpid())
        try:
            while not (Path(__file__).parent / "STOP").exists():
                try:
                    guard.scan()
                except Exception as exc:
                    guard.error("scan", repr(exc))
                if args.once:
                    break
                time.sleep(max(0.5, float(config.get("interval_seconds", 1))))
        finally:
            guard.record("stopped", args.config, pid=os.getpid())


if __name__ == "__main__":
    main()
