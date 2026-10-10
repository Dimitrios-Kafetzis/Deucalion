"""Command-line interface: `deucalion <command>`."""

from __future__ import annotations

import argparse
import getpass
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
from . import rebuild
from . import drivesetup
from .drives import list_drives
from .privileged import Privileged
from .logs import close_run_log, open_run_log
from .restore import Restorer
from .target import Target
from .util import DeucalionError, fs_type, human_duration, human_size, is_encrypted, run
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
# Finding (and if needed unlocking) the backup drive


def _ask_password(prompt: str, confirm_it: bool = False) -> str:
    if os.environ.get("DEUCALION_PASSWORD_STDIN"):
        return sys.stdin.readline().rstrip("\n")
    if not sys.stdin.isatty():
        raise DeucalionError("A password is needed but there is no terminal to ask for it.")
    while True:
        pw = getpass.getpass(prompt)
        if not confirm_it:
            return pw
        if len(pw) < 8:
            print(red("  Use at least 8 characters (a few words make a strong, memorable password)."))
            continue
        if len(pw) < 12:
            print(yellow("  Tip: 12 or more characters is much safer."))
        if getpass.getpass("  Type it again: ") == pw:
            return pw
        print(red("  The two passwords are different. Try again."))


def find_target(cfg: Config, wanted: str | None) -> Target:
    """Target.find, but offers to unlock an encrypted backup drive first."""
    try:
        return Target.find(cfg, wanted)
    except DeucalionError:
        tid = Target.select(cfg, wanted)
        access = cfg["targets"][tid].get("access") or {}
        if access.get("method", "none") == "none":
            raise
    name = cfg["targets"][tid]["name"]
    ds = drivesetup.DriveSetup(cfg, out=lambda s: print(dim(f"  {s}")))
    try:
        ds.locate(access)  # raises if the drive is not plugged in
        print(f"The backup drive '{name}' is locked.")
        ds.open(access, _ask_password("  Backup password: "))
    finally:
        ds.close()
    return Target.find(cfg, wanted)


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
    target = find_target(cfg, args.target)
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
            if job.kind == "full" and cfg.get("system_recipe", True) and not args.no_system:
                use_admin = cfg.get("system_admin", True) and not args.no_admin and not args.dry_run
                print("Saving the system recipe (packages, settings, services)"
                      + (" — you may be asked for your administrator password…" if use_admin else "…"))
                priv = Privileged() if use_admin else None
                try:
                    job.prepare_system(priv)
                finally:
                    if priv:
                        priv.close()
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
            _refresh_tool_copy(cfg, target)
            return 0
        finally:
            job.close()
            close_run_log(log)


def _refresh_tool_copy(cfg: Config, target: Target) -> None:
    """Keep the copy of Deucalion on the drive's unencrypted part up to date."""
    try:
        root = drivesetup.plain_root_of(cfg, target)
        if root is not None and os.access(root, os.W_OK):
            access = cfg["targets"].get(target.id, {}).get("access", {"method": "none"})
            drivesetup.install_tool_copy(root, target, access)
    except (OSError, DeucalionError) as e:
        print(dim(f"(Could not update the copy of Deucalion on the drive: {e})"))


def cmd_status(cfg: Config, args) -> int:
    target = find_target(cfg, args.target)
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
    target = find_target(cfg, args.target)
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
    target = find_target(cfg, args.target)
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


def _show_items(plan: "rebuild.StepPlan") -> None:
    for n, it in enumerate(plan.items, 1):
        if it.selectable:
            box = green("[x]") if it.selected else "[ ]"
            print(f"  {box} {n:>3}  {it.label}" + (dim(f"  — {it.detail}") if it.detail else ""))
        else:
            print(dim(f"   -  {n:>3}  {it.label}" + (f"  — {it.detail}" if it.detail else "")))


def _parse_numbers(text: str, limit: int) -> list[int]:
    out = []
    for part in text.replace(",", " ").split():
        if "-" in part:
            a, _, b = part.partition("-")
            if a.isdigit() and b.isdigit():
                out += range(int(a), int(b) + 1)
        elif part.isdigit():
            out.append(int(part))
    return [n for n in out if 1 <= n <= limit]


def _ask_step(step: "rebuild.Step", plan: "rebuild.StepPlan") -> str:
    """Interactive review. Returns 'apply', 'skip' or 'quit'."""
    help_ = ("  Enter = apply the checked items · n = skip this step · numbers (2 5-7) = check/uncheck · "
             "all / none · d N = show the change for item N · q = stop here")
    print(dim(help_))
    while True:
        try:
            ans = input(bold("  > ")).strip().lower()
        except EOFError:
            return "quit"
        if ans in ("", "y", "yes"):
            return "apply"
        if ans in ("n", "no", "s", "skip"):
            return "skip"
        if ans in ("q", "quit"):
            return "quit"
        if ans in ("all", "none"):
            for it in plan.actionable:
                it.selected = ans == "all"
        elif ans.startswith("d"):
            for n in _parse_numbers(ans[1:], len(plan.items)):
                it = plan.items[n - 1]
                diff = rebuild.SystemConfigStep.diff(it) if isinstance(step, rebuild.SystemConfigStep) and it.data else ""
                print(diff or dim("  (no details to show)"))
            continue
        else:
            for n in _parse_numbers(ans, len(plan.items)):
                it = plan.items[n - 1]
                if it.selectable:
                    it.selected = not it.selected
        _show_items(plan)


def cmd_rebuild(cfg: Config, args) -> int:
    target = find_target(cfg, args.target)
    interactive = sys.stdin.isatty() and not args.yes
    if not interactive and not args.yes and not args.dry_run:
        raise DeucalionError("rebuild needs a terminal to ask you questions (or use --dry-run / --yes).")
    printer = ProgressPrinter()
    with target.lock():
        m = target.manifest()
        log, log_paths = open_run_log(target, "rebuild")
        ctx = rebuild.Context(cfg, target, m, log)
        state = rebuild.load_state(target)
        steps = [s for s in rebuild.STEPS if not args.step or s.name == args.step]
        report: list[tuple[str, str, list[str]]] = []
        try:
            print(bold(f"Rebuild from backup '{target.name}'"))
            for n, step in enumerate(steps, 1):
                done = state["steps"].get(step.name, {})
                if done.get("status") == "done" and not args.step and not args.dry_run:
                    print(dim(f"\n✓ {step.title}: done {done.get('when')} (run again with --step {step.name})"))
                    continue
                print(bold(f"\nStep {n}/{len(steps)}: {step.title}"))
                plan = step.plan(ctx)
                for note in plan.notes:
                    print(f"  {note}")
                _show_items(plan)
                if args.dry_run:
                    continue
                if not plan.actionable:
                    if step.name == "check" and interactive and not confirm("  Continue?", False):
                        return 1
                    rebuild.save_state(state, step.name, "done", [])
                    continue
                choice = _ask_step(step, plan) if interactive else "apply"
                if choice == "quit":
                    print("Stopped. Run 'deucalion rebuild' again to continue from here.")
                    break
                if choice == "skip":
                    rebuild.save_state(state, step.name, "skipped", [])
                    report.append((step.title, "skipped", []))
                    continue
                selected = [i for i in plan.actionable if i.selected]
                kwargs = {"on_progress": printer} if step.name == "home" else {}
                try:
                    warnings = step.apply(ctx, selected, lambda line: (printer.clear(), print(f"    {line}")), **kwargs)
                except DeucalionError as e:
                    printer.clear()
                    print(red(f"  {e}"))
                    rebuild.save_state(state, step.name, "failed", [str(e)])
                    report.append((step.title, "failed", [str(e)]))
                    continue
                printer.clear()
                for w in warnings:
                    print(yellow(f"    {w}"))
                rebuild.save_state(state, step.name, "done", warnings)
                report.append((step.title, "done", warnings))
        finally:
            ctx.close()
            m.close()
            close_run_log(log)
        if args.dry_run:
            print(dim("\nDry run: nothing was changed."))
        elif report:
            print(bold("\nSummary"))
            for title, status, warnings in report:
                colour = green if status == "done" and not warnings else yellow if status != "failed" else red
                print(f"  {colour(status):<10} {title}" + (f"  ({len(warnings)} warnings)" if warnings else ""))
            print("Log out and back in to finish (new groups and desktop settings take effect then).")
        return 0


def cmd_verify(cfg: Config, args) -> int:
    target = find_target(cfg, args.target)
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
    target = find_target(cfg, args.target)
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


def _choose(title: str, options: list[tuple[str, str]], default: int = 1) -> str:
    """Numbered menu; returns the key of the chosen option."""
    print(bold(title))
    for n, (_, text) in enumerate(options, 1):
        print(f"  {n}) {text}")
    while True:
        try:
            ans = input(f"  Choose [1-{len(options)}] (default {default}): ").strip()
        except EOFError:
            raise DeucalionError("Cancelled.") from None
        if not ans:
            return options[default - 1][0]
        if ans.isdigit() and 1 <= int(ans) <= len(options):
            return options[int(ans) - 1][0]


def _ask_size_gb(question: str, default_gb: int, max_gb: int) -> int:
    while True:
        try:
            ans = input(f"  {question} [default {default_gb} GB, max {max_gb} GB]: ").strip()
        except EOFError:
            raise DeucalionError("Cancelled.") from None
        gb = default_gb if not ans else int(ans) if ans.isdigit() else -1
        if 1 <= gb <= max_gb:
            return gb * 1024 ** 3
        print(red(f"  Enter a number between 1 and {max_gb}."))


def cmd_setup_drive(cfg: Config, args) -> int:
    interactive = sys.stdin.isatty() and not os.environ.get("DEUCALION_PASSWORD_STDIN")
    drives = [d for d in list_drives(include_loops=args.allow_internal) if not d.system and (d.external or args.allow_internal)]
    if args.device:
        matches = [d for d in drives if d.path == args.device]
        if not matches:
            raise DeucalionError(f"{args.device} is not an external drive (your system disk is never offered).")
        drive = matches[0]
    else:
        if not drives:
            raise DeucalionError("No external drive found. Plug one in and try again.")
        if not interactive:
            raise DeucalionError("Give the drive, e.g. deucalion setup-drive /dev/sdb")
        key = _choose("Which drive?", [(d.path, f"{d.path}  {d.model or 'Drive'}  {human_size(d.size)}")
                                      for d in drives])
        drive = next(d for d in drives if d.path == key)
    print(bold(f"\n{drive.path}  {drive.model or 'Drive'}  {human_size(drive.size)}"))
    mounted = [v for v in drive.volumes if v.mountpoints and not v.encrypted]
    for v in drive.volumes:
        used = ""
        if v.mountpoints:
            du = shutil.disk_usage(v.mountpoints[0])
            used = f", {human_size(du.used)} used"
        print(f"  {v.path}  {v.fstype or 'unknown'}  {human_size(v.size)}{used}"
              + (f"  “{v.label}”" if v.label else "") + (f"  at {', '.join(v.mountpoints)}" if v.mountpoints else ""))
    if not drive.volumes:
        print("  (empty)")

    layout = args.layout
    if not layout:
        if not interactive:
            raise DeucalionError("Give --layout.")
        opts = [(k, v) for k, v in drivesetup.LAYOUTS.items() if k in drivesetup.ERASING or mounted]
        layout = _choose("\nHow should the backup be stored?", opts)
    method = args.method or ""
    if layout.startswith("encrypt") and not method:
        if not interactive:
            raise DeucalionError("Give --method veracrypt or --method luks.")
        vc = "" if drivesetup.veracrypt_binary() else " (install VeraCrypt first)"
        method = _choose("\nWhich encryption?", [
            ("veracrypt", f"VeraCrypt: open it on Linux, macOS and Windows (with VeraCrypt){vc}"),
            ("luks", "LUKS: built into Ubuntu, no extra software, Linux only")])
    folder = ""
    if layout in ("encrypt-folder", "as-is"):
        if not mounted:
            raise DeucalionError("This drive has no usable filesystem; choose a layout that formats it.")
        folder = mounted[0].mountpoints[0] if len(mounted) == 1 or not interactive else _choose(
            "\nWhich part of the drive?", [(v.mountpoints[0], f"{v.mountpoints[0]} ({v.fstype})") for v in mounted])
    size = int(args.size * 1024 ** 3) if args.size else 0
    if layout == "encrypt-part" and not size:
        max_gb = max(int(drive.size / 1024 ** 3) - 1, 1)
        size = _ask_size_gb("Size of the encrypted part for backups?", int(max_gb * 0.8), max_gb) if interactive \
            else int(drive.size * 0.8)
    if layout == "encrypt-folder" and not size:
        max_gb = max(int(shutil.disk_usage(folder).free * 0.95 / 1024 ** 3), 1)
        size = _ask_size_gb("Size of the encrypted folder? (it cannot grow later)", int(max_gb * 0.8), max_gb) \
            if interactive else int(max_gb * 0.8) * 1024 ** 3
    name = args.name or (input(f"  A name for this backup drive [Deucalion]: ").strip() if interactive else "") or "Deucalion"
    req = drivesetup.SetupRequest(layout, device=drive.path, folder=folder, method=method, name=name, size=size,
                                  allow_internal=args.allow_internal)

    missing = drivesetup.missing_requirements(req)
    if any(code == "exfatprogs" for code, _ in missing):
        print(yellow("\nThe 'exfatprogs' package is needed to create exFAT filesystems."))
        if confirm("  Install it now? (asks for your administrator password)", args.yes):
            with Privileged() as priv:
                if priv.call("apt_install", packages=["exfatprogs"], on_progress=lambda l: print(dim(f"    {l}"))).get("code"):
                    raise DeucalionError("exfatprogs could not be installed.")
    for code, msg in drivesetup.missing_requirements(req):
        if code not in ("password",):
            raise DeucalionError(msg)

    print(bold("\nSummary"))
    print(f"  Drive:  {drive.path}  {drive.model}  {human_size(drive.size)}")
    print(f"  Layout: {drivesetup.LAYOUTS[layout]}" + (f" ({method})" if method else ""))
    if size:
        print(f"  Encrypted size: {human_size(size)}")
    if layout in drivesetup.ERASING:
        print(red(f"  EVERYTHING on {drive.path} will be erased."))
        if args.yes_erase != os.path.basename(drive.path):
            if not interactive:
                raise DeucalionError(f"To erase the drive non-interactively, pass --yes-erase {os.path.basename(drive.path)}")
            typed = input(f"  To confirm, type the drive name ({os.path.basename(drive.path)}): ").strip()
            if typed != os.path.basename(drive.path):
                print("Nothing was changed.")
                return 1
    elif not confirm("  Continue?", args.yes):
        print("Nothing was changed.")
        return 1
    if layout.startswith("encrypt"):
        print("\nChoose the password for the backup. It cannot be recovered if you forget it: write it down "
              "and keep it somewhere safe.")
        req.passphrase = _ask_password("  Backup password: ", confirm_it=True)
    ds = drivesetup.DriveSetup(cfg, out=lambda line: print(f"  {line}"))
    try:
        target = ds.run(req)
    finally:
        ds.close()
    print(green(f"\nDone. Back up with: deucalion backup") + (f"  (drive '{target.name}')" if target else ""))
    return 0


def cmd_open(cfg: Config, args) -> int:
    ds = drivesetup.DriveSetup(cfg, out=lambda s: print(dim(f"  {s}")))
    try:
        if args.source:
            src = os.path.abspath(args.source)
            if src.startswith("/dev/"):
                fstype = fs_type_of_device(src)
                method = "luks" if fstype == "crypto_LUKS" else "veracrypt"
                access = {"method": method, "kind": "partition", "source": src, "mount_name": "Deucalion"}
            else:
                method = "luks" if src.endswith(".luks") else "veracrypt"
                access = {"method": method, "kind": "file", "source": src, "file": os.path.basename(src),
                          "plain_path": os.path.dirname(src), "mount_name": "Deucalion"}
        else:
            access = None
            try:
                tid = Target.select(cfg, args.target)
                access = cfg["targets"][tid].get("access")
            except DeucalionError:
                pass
            if not access or access.get("method", "none") == "none":
                found = drivesetup.discover()
                if not found:
                    raise DeucalionError("No encrypted Deucalion backup found. Plug in the drive, or give the "
                                         "encrypted partition or file: deucalion open /dev/sdb2")
                root, access = found[0]
                if access.get("kind") == "file":
                    access = dict(access, plain_path=str(root))
        mp = ds.open(access, _ask_password("Backup password: "))
    finally:
        ds.close()
    root = drivesetup.target_root_for(mp)
    if root is None:
        print(yellow(f"Unlocked at {mp}, but there is no Deucalion backup in it."))
        return 1
    target = Target(root)
    entry = cfg.get("targets", {}).get(target.id)
    if entry is None:
        target.register(cfg)
        print(f"Registered backup drive '{target.name}' on this machine.")
    stored = {k: v for k, v in access.items() if k != "source"}
    if access.get("kind") == "partition" and "partuuid" not in stored and access.get("source"):
        stored["partuuid"] = run(["lsblk", "-no", "PARTUUID", access["source"]]).stdout.strip()
    cfg["targets"][target.id]["access"] = stored
    cfg["targets"][target.id]["path"] = str(root)
    cfg.save()
    print(green(f"Backup drive '{target.name}' is open: {root}"))
    return 0


def fs_type_of_device(dev: str) -> str:
    return run(["blkid", "-s", "TYPE", "-o", "value", dev]).stdout.strip()


def cmd_close(cfg: Config, args) -> int:
    tid = Target.select(cfg, args.target)
    entry = cfg["targets"][tid]
    access = entry.get("access") or {"method": "none"}
    ds = drivesetup.DriveSetup(cfg, out=lambda s: print(dim(f"  {s}")))
    try:
        if access.get("method", "none") == "none":
            root = Path(entry["path"])
            mp = run(["findmnt", "-rno", "TARGET", "--target", str(root)]).stdout.strip()
            if not mp or not mp.startswith(("/media/", "/run/media/", "/mnt/")):
                print("The backup drive is not mounted.")
                return 0
            src = run(["findmnt", "-rno", "SOURCE", mp]).stdout.strip()
            ds.u.unmount(ds.u.resolve(src))
        else:
            ds.close_access(access)
    finally:
        ds.close()
    print(green(f"Backup drive '{entry['name']}' is closed. You can unplug it."))
    return 0


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

    sp = add("setup-drive", cmd_setup_drive, "prepare a drive for backups (format, encrypt)")
    sp.add_argument("device", nargs="?", help="the drive, e.g. /dev/sdb (asked if not given)")
    sp.add_argument("--layout", choices=list(drivesetup.LAYOUTS))
    sp.add_argument("--method", choices=["veracrypt", "luks"], help="encryption method")
    sp.add_argument("--size", type=float, metavar="GB", help="size of the encrypted part or folder")
    sp.add_argument("--name", help="a name for the backup drive")
    sp.add_argument("--yes-erase", metavar="DRIVE", default="", help="confirm erasing, e.g. --yes-erase sdb")
    sp.add_argument("-y", "--yes", action="store_true", help="don't ask for other confirmations")
    sp.add_argument("--allow-internal", action="store_true", help=argparse.SUPPRESS)

    sp = add("open", cmd_open, "unlock an encrypted backup drive")
    sp.add_argument("source", nargs="?", help="encrypted partition or file (only needed the first time)")
    target_opt(sp)

    sp = add("close", cmd_close, "lock/unmount the backup drive so it can be unplugged")
    target_opt(sp)

    sp = add("backup", cmd_backup, "back up everything, or only some folders")
    sp.add_argument("--only", nargs="+", metavar="PATH", help="back up only these folders/files")
    sp.add_argument("--profile", help="back up the folders saved in a profile")
    sp.add_argument("--dry-run", action="store_true", help="show what would be copied, change nothing")
    sp.add_argument("--details", action="store_true", help="list every file and warning")
    sp.add_argument("--check-drive", action="store_true",
                    help="also check that every file is really on the drive (slower)")
    sp.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")
    sp.add_argument("--no-system", action="store_true", help="don't save the system recipe")
    sp.add_argument("--no-admin", action="store_true",
                    help="don't ask for the administrator password (some system settings are then not saved)")
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

    sp = add("rebuild", cmd_rebuild, "rebuild this machine from a backup (new machine or new Ubuntu)")
    sp.add_argument("--step", choices=[st.name for st in rebuild.STEPS], help="run only this step (again)")
    sp.add_argument("--dry-run", action="store_true", help="show every step's plan, change nothing")
    sp.add_argument("-y", "--yes", action="store_true", help="apply the pre-selected items without asking")
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
