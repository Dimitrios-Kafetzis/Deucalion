"""Command-line interface: `deucalion <command>`."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
from pathlib import Path

from . import __version__
from .backup import BackupJob, Plan, Progress
from .config import DEFAULT_HOME_EXCLUDES, Config
from .drives import list_drives
from .logs import close_run_log, open_run_log
from .restore import Restorer
from .target import Target
from .util import DeucalionError, fs_type, human_duration, human_size, is_encrypted
from .verify import verify

# --------------------------------------------------------------------------------------------
# Output helpers


def _color(code: str):
    def wrap(text: str) -> str:
        if sys.stdout.isatty() and not os.environ.get("NO_COLOR"):
            return f"\x1b[{code}m{text}\x1b[0m"
        return text
    return wrap


bold, green, yellow, red, dim = _color("1"), _color("32"), _color("33"), _color("31"), _color("2")


def _shorten(text: str, width: int) -> str:
    return text if len(text) <= width else "…" + text[-(width - 1):]


class ProgressPrinter:
    """One self-updating line on the terminal."""

    def __init__(self, stream=sys.stderr):
        self.stream = stream
        self.tty = stream.isatty()

    def __call__(self, p: Progress) -> None:
        if not self.tty:
            return
        width = shutil.get_terminal_size((100, 20)).columns - 1
        if p.phase == "scan":
            line = f"Scanning… {p.files_total:,} files  "
        elif p.phase == "done":
            self.clear()
            return
        else:
            total = p.bytes_total or 1
            frac = min(p.bytes_done / total, 1.0) if p.bytes_total else (
                p.files_done / p.files_total if p.files_total else 1.0)
            bar = "█" * int(frac * 20) + "░" * (20 - int(frac * 20))
            line = f"{bar} {frac * 100:3.0f}%  "
            if p.bytes_total:
                line += f"{human_size(p.bytes_done)} / {human_size(p.bytes_total)}  "
            else:
                line += f"{p.files_done:,} / {p.files_total:,} files  "
            if p.rate:
                line += f"{human_size(p.rate)}/s  "
            if p.eta is not None:
                line += f"{human_duration(p.eta)} left  "
        room = width - len(line)
        if room > 10:
            line += _shorten(p.current, room)
        self.stream.write("\r" + line[:width] + "\x1b[K")
        self.stream.flush()

    def clear(self) -> None:
        if self.tty:
            self.stream.write("\r\x1b[K")
            self.stream.flush()


class GracefulCancel:
    """First Ctrl+C asks the running task to stop safely; a second one aborts."""

    def __init__(self):
        self.event = threading.Event()
        self._old = None

    def __enter__(self):
        def handler(signum, frame):
            if self.event.is_set():
                raise KeyboardInterrupt
            self.event.set()
            sys.stderr.write("\n" + yellow("Stopping safely… (press Ctrl+C again to abort immediately)") + "\n")
        self._old = signal.signal(signal.SIGINT, handler)
        return self.event

    def __exit__(self, *exc):
        signal.signal(signal.SIGINT, self._old)
        return False


def confirm(question: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print("Not confirmed (no terminal to ask). Use --yes to confirm.")
        return False
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def _print_list(title: str, items: list[str], limit: int) -> None:
    if not items:
        return
    print(f"  {title}:")
    for i in items[:limit]:
        print(f"    {i}")
    if len(items) > limit:
        print(dim(f"    … and {len(items) - limit:,} more"))


# --------------------------------------------------------------------------------------------
# Commands


def cmd_drives(cfg: Config, args) -> int:
    drives = list_drives()
    shown = 0
    for d in drives:
        if d.system:
            continue
        shown += 1
        kind = "external" if d.external else "internal"
        print(bold(f"{d.path}  {d.model or 'Drive'}  {human_size(d.size)}  ({kind}, {d.transport or '?'})"))
        if not d.volumes:
            print("    no filesystems (empty or unformatted)")
        for v in d.volumes:
            state = ", ".join(v.mountpoints) if v.mountpoints else "not mounted"
            tags = []
            if v.encrypted:
                tags.append("encrypted")
            if v.has_backup:
                tags.append(green("Deucalion backup"))
            label = f" “{v.label}”" if v.label else ""
            print(f"    {v.path}{label}  {v.fstype or '-'}  {human_size(v.size)}  {state}"
                  + (f"  [{', '.join(tags)}]" if tags else ""))
    if not shown:
        print("No external drives found. (Your system disk is never listed.)")
    return 0


def cmd_register(cfg: Config, args) -> int:
    target = Target.create(Path(args.path), name=args.name, allow_internal=args.allow_internal)
    target.register(cfg, allow_internal=args.allow_internal, make_default=args.default)
    fs = fs_type(target.root)
    print(green(f"Registered backup drive '{target.name}'."))
    print(f"  Backup folder: {target.root}")
    print(f"  Filesystem:    {fs}  (names stored {'as-is' if target.policy.kind == 'posix' else 'exFAT-safe'})")
    print(f"  Encrypted:     {'yes' if is_encrypted(target.root) else 'no'}")
    print(f"  Free space:    {human_size(target.free_bytes())}")
    return 0


def cmd_targets(cfg: Config, args) -> int:
    targets = cfg.get("targets", {})
    if not targets:
        print("No backup drives registered. Use: deucalion register <drive folder>")
        return 0
    for tid, t in targets.items():
        connected = (Path(t["path"]) / ".deucalion" / "drive-id").exists()
        default = " (default)" if cfg.get("default_target") == tid else ""
        state = green("connected") if connected else dim("not connected")
        print(f"{bold(t['name'])}{default}  {state}\n    {t['path']}\n    id {tid}")
    return 0


def _print_plan(plan: Plan, details: bool, show_folders: bool = False) -> None:
    print(bold(f"Backup plan ({plan.kind}: {plan.scope_text})"))
    print(f"  New files:      {plan.new_files:>10,}   {human_size(plan.new_bytes)}")
    print(f"  Changed files:  {plan.changed_files:>10,}   {human_size(plan.changed_bytes)} (previous versions go to _removed/)")
    print(f"  Gone/excluded:  {plan.removed_items:>10,}   {human_size(plan.removed_bytes)} (moved to _removed/)")
    print(f"  Unchanged:      {plan.unchanged_files:>10,}   {human_size(plan.unchanged_bytes)}")
    if show_folders and plan.folders:
        print("  Largest folders in this backup:")
        for folder, files, size in plan.largest_folders(12):
            print(f"    {human_size(size):>10}  {files:>10,} files  {folder}")
    if details:
        limit = 10**9
        _print_list("Will copy", [a.entry.path for a in plan.actions if a.op == "copy"], limit)
        _print_list("Will move to _removed/", [a.entry.path for a in plan.removals], limit)
    _print_warnings(plan.warnings, plan.skipped, details)


def _print_warnings(warnings: list[str], skipped: list[tuple[str, str]], details: bool) -> None:
    limit = 10**9 if details else 8
    if warnings:
        print(yellow(f"  Warnings ({len(warnings)}):"))
        for w in warnings[:limit]:
            print(f"    {w}")
        if len(warnings) > limit:
            print(dim(f"    … and {len(warnings) - limit:,} more (see the log)"))
    if skipped:
        print(dim(f"  Skipped ({len(skipped)}):"))
        for path, why in skipped[:limit]:
            print(dim(f"    {path}: {why}"))
        if len(skipped) > limit:
            print(dim(f"    … and {len(skipped) - limit:,} more (see the log)"))


def _only_from_args(cfg: Config, args) -> list[str]:
    only = list(args.only or [])
    if args.profile:
        profiles = cfg.get("profiles", {})
        if args.profile not in profiles:
            raise DeucalionError(f"No profile called '{args.profile}'. See: deucalion profile list")
        only += profiles[args.profile]
    return only


def cmd_backup(cfg: Config, args) -> int:
    target = Target.find(cfg, args.target)
    printer = ProgressPrinter()
    with target.lock(), GracefulCancel() as cancel:
        log, log_paths = open_run_log(target, "backup" if not args.dry_run else "dry-run")
        job = BackupJob(cfg, target, _only_from_args(cfg, args), printer, cancel, log,
                        check_drive=args.check_drive)
        try:
            print(f"Backing up to {bold(target.name)}  {dim(str(target.root))}")
            identity = job.identity_problem()
            if identity:
                print(yellow(identity))
                if not args.dry_run and not confirm("Continue anyway?", args.yes):
                    print("Nothing was changed.")
                    return 1
            if not is_encrypted(target.root):
                found = job.sensitive_found()
                if found:
                    print(yellow("Note: this drive is not encrypted, and your backup includes keys or "
                                 "logged-in sessions (" + ", ".join(found[:4]) + ")."))
            try:
                plan = job.scan()
            except Exception:
                printer.clear()
                raise
            printer.clear()
            if cancel.is_set():
                print("Cancelled before anything was copied.")
                return 130
            _print_plan(plan, args.details, show_folders=args.dry_run)
            if args.dry_run:
                print(dim("Dry run: nothing was copied. Add --details to list every file."))
                return 0
            problem = job.space_problem(plan)
            if problem:
                print(red(problem))
                return 1
            if plan.nothing_to_do:
                print(green("Everything is already up to date."))
            result = job.execute(plan)
            printer.clear()
            log.info("finished with status %s", result.status)
            if result.status == "cancelled":
                print(yellow(f"Stopped. {result.copied_files:,} files were copied; "
                             "the next backup continues from here."))
                return 130
            if result.status == "failed":
                print(red(f"Backup failed: {result.error}"))
                return 1
            _print_warnings(result.warnings[len(plan.warnings):], [], args.details)
            msg = (f"Backup finished in {human_duration(result.duration)}: copied {result.copied_files:,} "
                   f"files ({human_size(result.copied_bytes)}), moved {result.removed_items:,} items to _removed/.")
            print(green(msg) if result.status == "completed" else yellow(msg + " Some warnings above."))
            if log_paths:
                print(dim(f"Log: {log_paths[0]}"))
            return 0
        finally:
            job.close()
            close_run_log(log)


def cmd_status(cfg: Config, args) -> int:
    target = Target.find(cfg, args.target)
    s = target.read_summary()
    m = target.manifest()
    try:
        size, files = m.tree_totals()
        runs = m.last_runs(5)
    finally:
        m.close()
    removed = target.removed_batches()
    print(bold(f"Backup drive '{target.name}'"))
    print(f"  Folder:        {target.root}")
    print(f"  Filesystem:    {fs_type(target.root)}   Encrypted: {'yes' if is_encrypted(target.root) else 'no'}")
    print(f"  Backed up:     {files:,} files, {human_size(size)}")
    print(f"  Free space:    {human_size(target.free_bytes())}")
    print(f"  _removed/:     {human_size(sum(r[1] for r in removed))} in {len(removed)} batch(es)")
    if s.get("machine"):
        print(f"  From machine:  {s['machine'].get('hostname')} ({s['machine'].get('os')}), "
              f"user {s.get('user', {}).get('name')}")
    if s.get("last_full_backup"):
        print(f"  Last full:     {s['last_full_backup']}")
    if runs:
        print("  Recent runs:")
        for rid, kind, started, finished, status, scope, stats in runs:
            st = json.loads(stats) if stats else {}
            colour = green if status == "completed" else yellow if status in ("completed_with_warnings", "cancelled") else red
            print(f"    {started}  {kind:<8} {colour(status):<24} "
                  f"{st.get('copied_files', 0):,} copied, {human_size(st.get('copied_bytes', 0))}"
                  + (f"  [{scope}]" if kind == "partial" else ""))
    return 0


def cmd_ls(cfg: Config, args) -> int:
    target = Target.find(cfg, args.target)
    m = target.manifest()
    try:
        r = Restorer(cfg, target, m)
        if not args.path:
            for name, (origin, here) in r.sources.items():
                size, files = m.tree_totals(name)
                print(f"{bold(name + '/')}  from {origin}  ({files:,} files, {human_size(size)})")
            return 0
        logical, _ = r.resolve(args.path)
        entry = m.get(logical)
        children = m.children(logical) if entry.kind == "d" else {entry.name: entry}
        for name in sorted(children, key=str.lower):
            e = children[name]
            if e.kind == "d":
                size, files = m.tree_totals(e.path)
                print(f"  {bold(name + '/')}  {dim(f'{files:,} files, {human_size(size)}')}")
            elif e.kind == "l":
                print(f"  {name} -> {e.link}")
            else:
                print(f"  {name}  {dim(human_size(e.size))}")
        return 0
    finally:
        m.close()


def cmd_restore(cfg: Config, args) -> int:
    target = Target.find(cfg, args.target)
    printer = ProgressPrinter()
    with target.lock(), GracefulCancel() as cancel:
        m = target.manifest()
        log, log_paths = open_run_log(target, "restore")
        try:
            r = Restorer(cfg, target, m, printer, cancel, log)
            plan = r.plan(args.items, Path(args.to) if args.to else None)
            print(bold("Restore plan"))
            for logical, dest in plan.roots:
                print(f"  {logical}  →  {dest}")
            print(f"  New:              {plan.count('create') + plan.count('mkdir'):>8,}")
            print(f"  Overwrite:        {plan.count('overwrite'):>8,}   (current versions are moved aside first)")
            print(f"  Already the same: {plan.count('same'):>8,}")
            print(f"  To copy:          {plan.copy_files:>8,}   {human_size(plan.copy_bytes)}")
            if plan.count("missing"):
                print(red(f"  Missing on drive: {plan.count('missing'):>8,}"))
            _print_list("Will overwrite", [str(i.dest) for i in plan.of("overwrite")], 10**9 if args.details else 15)
            if args.dry_run:
                print(dim("Dry run: nothing was changed."))
                return 0
            if plan.copy_files == 0 and plan.count("overwrite") == 0 and plan.count("mkdir") == 0 \
                    and plan.count("create") == 0:
                print(green("Nothing to restore: everything is already the same."))
                return 0
            if not confirm("Restore now?", args.yes):
                print("Nothing was changed.")
                return 1
            res = r.execute(plan)
            printer.clear()
            for w in res.warnings[:20]:
                print(yellow(f"  {w}"))
            if res.status == "cancelled":
                print(yellow(f"Stopped after restoring {res.restored_files:,} files."))
            else:
                print(green(f"Restored {res.restored_files:,} files ({human_size(res.restored_bytes)})."))
            if res.undo_dir:
                print(f"Files that were replaced are kept in {res.undo_dir}")
            return 130 if res.status == "cancelled" else 0
        finally:
            m.close()
            close_run_log(log)


def cmd_verify(cfg: Config, args) -> int:
    target = Target.find(cfg, args.target)
    printer = ProgressPrinter()
    with target.lock(), GracefulCancel() as cancel:
        m = target.manifest()
        try:
            res = verify(target, m, full=args.full, on_progress=printer, cancel=cancel)
        finally:
            m.close()
    printer.clear()
    mode = "full (checksums)" if args.full else "quick (sizes)"
    print(f"Verified {res.checked_files:,} files, {human_size(res.checked_bytes)} — {mode}")
    _print_list(red("Missing on drive"), res.missing, 20)
    _print_list(red("Wrong size"), res.wrong_size, 20)
    _print_list(red("Damaged (checksum mismatch)"), res.damaged, 20)
    if res.cancelled:
        print(yellow("Stopped before the end."))
        return 130
    if res.ok:
        print(green("The backup is intact."))
        return 0
    print(red("Problems found. The next backup will copy these files again."))
    return 1


def cmd_removed(cfg: Config, args) -> int:
    target = Target.find(cfg, args.target)
    batches = target.removed_batches()
    if args.action == "list" or args.action is None:
        if not batches:
            print("_removed/ is empty.")
            return 0
        for name, size, files in batches:
            print(f"  {name}   {files:>8,} files   {human_size(size)}")
        print(f"  Total: {human_size(sum(b[1] for b in batches))}   ({target.removed_root})")
        return 0
    # empty
    names = args.names or None
    chosen = [b for b in batches if names is None or b[0] in names]
    if names:
        unknown = set(names) - {b[0] for b in batches}
        if unknown:
            raise DeucalionError(f"Not found in _removed/: {', '.join(sorted(unknown))}")
    if not chosen:
        print("_removed/ is already empty.")
        return 0
    total = sum(b[1] for b in chosen)
    print(f"This permanently deletes {len(chosen)} batch(es), {human_size(total)}, from the drive:")
    for name, size, files in chosen:
        print(f"  {name}   {files:,} files   {human_size(size)}")
    if not confirm("Delete them permanently?", args.yes):
        print("Nothing was deleted.")
        return 1
    with target.lock():
        freed = target.empty_removed([b[0] for b in chosen])
    print(green(f"Freed {human_size(freed)}."))
    return 0


def cmd_exclude(cfg: Config, args) -> int:
    ex = cfg.setdefault("home_excludes", list(DEFAULT_HOME_EXCLUDES))
    if args.action == "add":
        for p in args.patterns:
            if p not in ex:
                ex.append(p)
        cfg.save()
    elif args.action == "remove":
        missing = [p for p in args.patterns if p not in ex]
        if missing:
            raise DeucalionError(f"Not in the exclusion list: {', '.join(missing)}")
        cfg["home_excludes"] = [p for p in ex if p not in args.patterns]
        cfg.save()
    elif args.action == "reset":
        cfg["home_excludes"] = list(DEFAULT_HOME_EXCLUDES)
        cfg.save()
    for p in cfg["home_excludes"]:
        print(f"  {p}")
    return 0


def cmd_folder(cfg: Config, args) -> int:
    folders = cfg.setdefault("extra_folders", [])
    if args.action == "add":
        path = Path(args.path).expanduser().absolute()
        if not path.is_dir():
            raise DeucalionError(f"{path} is not a folder.")
        if path == cfg.home or cfg.home in path.parents:
            raise DeucalionError("That folder is inside your home folder, which is already backed up.")
        name = args.name or path.name or "root"
        if not all(c.isalnum() or c in "._-" for c in name):
            raise DeucalionError("Use only letters, digits, '.', '_' and '-' in the name (--name).")
        if any(f["name"] == name for f in folders):
            raise DeucalionError(f"There is already an extra folder called '{name}'.")
        folders.append({"name": name, "path": str(path), "excludes": []})
        cfg.save()
    elif args.action == "remove":
        if not any(f["name"] == args.path for f in folders):
            raise DeucalionError(f"No extra folder called '{args.path}'.")
        cfg["extra_folders"] = [f for f in folders if f["name"] != args.path]
        cfg.save()
    print(f"  home: {cfg.home}  (always included)")
    for f in cfg.get("extra_folders", []):
        print(f"  {f['name']}: {f['path']}")
    return 0


def cmd_profile(cfg: Config, args) -> int:
    profiles = cfg.setdefault("profiles", {})
    if args.action == "add":
        if not args.paths:
            raise DeucalionError("Give the folders/files for the profile.")
        profiles[args.name] = [str(Path(p).expanduser().absolute()) for p in args.paths]
        cfg.save()
    elif args.action == "remove":
        if profiles.pop(args.name, None) is None:
            raise DeucalionError(f"No profile called '{args.name}'.")
        cfg.save()
    if not profiles:
        print("No profiles. Create one with: deucalion profile add NAME PATH...")
    for name, paths in profiles.items():
        print(f"  {bold(name)}: {', '.join(paths)}")
    return 0


def cmd_config(cfg: Config, args) -> int:
    if args.action == "path":
        print(cfg.path)
    elif args.action == "edit":
        if not cfg.path.exists():
            cfg.save()
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "nano"
        subprocess.call([editor, str(cfg.path)])
        Config.load(cfg.path)  # validate
    else:
        print(json.dumps(dict(cfg), indent=2, ensure_ascii=False))
    return 0


# --------------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="deucalion",
        description="Back up your Ubuntu machine to an external drive, and restore or rebuild from it.")
    p.add_argument("--version", action="version", version=f"Deucalion {__version__}")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    def add(name, func, help_):
        sp = sub.add_parser(name, help=help_, description=help_)
        sp.set_defaults(func=func)
        return sp

    def target_opt(sp):
        sp.add_argument("--target", metavar="NAME", help="which registered drive to use")

    add("drives", cmd_drives, "list connected drives")

    sp = add("register", cmd_register, "use a drive (or a folder on it) for backups")
    sp.add_argument("path", help="where the drive is mounted, e.g. /media/you/MyDrive")
    sp.add_argument("--name", help="a friendly name for this backup drive")
    sp.add_argument("--default", action="store_true", help="make it the default drive")
    sp.add_argument("--allow-internal", action="store_true", help=argparse.SUPPRESS)

    add("targets", cmd_targets, "list registered backup drives")

    sp = add("backup", cmd_backup, "back up everything, or only some folders")
    sp.add_argument("--only", nargs="+", metavar="PATH", help="back up only these folders/files")
    sp.add_argument("--profile", help="back up the folders saved in a profile")
    sp.add_argument("--dry-run", action="store_true", help="show what would be copied, change nothing")
    sp.add_argument("--details", action="store_true", help="list every file and warning")
    sp.add_argument("--check-drive", action="store_true",
                    help="also check that every file is really on the drive (slower)")
    sp.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")
    target_opt(sp)

    sp = add("status", cmd_status, "show the state of the backup")
    target_opt(sp)

    sp = add("ls", cmd_ls, "list what is in the backup (with original names)")
    sp.add_argument("path", nargs="?", help="e.g. ~/Documents or home/Documents")
    target_opt(sp)

    sp = add("restore", cmd_restore, "restore files or folders from the backup")
    sp.add_argument("items", nargs="+", metavar="PATH", help="e.g. ~/Documents/report.pdf")
    sp.add_argument("--to", metavar="DIR", help="restore into this folder instead of the original place")
    sp.add_argument("--dry-run", action="store_true", help="show what would happen, change nothing")
    sp.add_argument("--details", action="store_true", help="list every file that would be overwritten")
    sp.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")
    target_opt(sp)

    sp = add("verify", cmd_verify, "check the backup on the drive is complete and undamaged")
    sp.add_argument("--full", action="store_true", help="also re-read every file and compare checksums")
    target_opt(sp)

    sp = add("removed", cmd_removed, "list or empty _removed/ (old versions and deleted files)")
    sp.add_argument("action", nargs="?", choices=["list", "empty"], default="list")
    sp.add_argument("names", nargs="*", help="batches to empty (default: all)")
    sp.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")
    target_opt(sp)

    sp = add("exclude", cmd_exclude, "manage what is left out of your home backup")
    sp.add_argument("action", nargs="?", choices=["list", "add", "remove", "reset"], default="list")
    sp.add_argument("patterns", nargs="*")

    sp = add("folder", cmd_folder, "manage extra folders outside your home (e.g. /srv)")
    sp.add_argument("action", nargs="?", choices=["list", "add", "remove"], default="list")
    sp.add_argument("path", nargs="?", help="folder to add, or name to remove")
    sp.add_argument("--name", help="short name for the folder on the drive")

    sp = add("profile", cmd_profile, "manage saved selections for partial backups")
    sp.add_argument("action", nargs="?", choices=["list", "add", "remove"], default="list")
    sp.add_argument("name", nargs="?")
    sp.add_argument("paths", nargs="*")

    sp = add("config", cmd_config, "show or edit the configuration")
    sp.add_argument("action", nargs="?", choices=["show", "edit", "path"], default="show")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    if os.geteuid() == 0 and not os.environ.get("DEUCALION_ALLOW_ROOT"):
        print(red("Please run Deucalion as your normal user (not with sudo). "
                  "It asks for the admin password itself when a step needs it."), file=sys.stderr)
        return 1
    try:
        cfg = Config.load()
        return args.func(cfg, args)
    except DeucalionError as e:
        print(red(str(e)), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(red("\nAborted."), file=sys.stderr)
        return 130
    except Exception as e:
        if os.environ.get("DEUCALION_DEBUG"):
            raise
        print(red(f"Unexpected error: {type(e).__name__}: {e}"), file=sys.stderr)
        print("Nothing on your machine was changed by a backup. Run again with DEUCALION_DEBUG=1 "
              "for details, and please report it.", file=sys.stderr)
        return 1
