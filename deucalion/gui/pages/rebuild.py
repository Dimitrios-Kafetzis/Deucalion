"""Rebuild: the new-machine wizard, one page per step, each with a review before applying."""

from __future__ import annotations

from ..common import (Adw, GLib, Gtk, Pango, alert, button, clamp, clear, group_add, hbox, label, on_main,
                      page_with_header, row, run_async, scrolled, toast, vbox, when)
from ... import rebuild
from ...logs import close_run_log, open_run_log
from ...util import human_size

STATUS = {"done": ("emblem-ok-symbolic", "status-ok", "Done"),
          "skipped": ("media-skip-forward-symbolic", "dim-label", "Skipped"),
          "failed": ("dialog-error-symbolic", "status-error", "Failed")}


class RebuildPage:
    def __init__(self, win):
        self.win = win
        self.state = win.state
        self.ctx: rebuild.Context | None = None
        self.log = None
        self.nav = Adw.NavigationView()

        self.steps_group = Adw.PreferencesGroup(title="Steps")
        self.intro = Adw.PreferencesGroup()
        self.continue_btn = button("Start", self._continue, ("suggested-action", "pill", "pill-big"))
        self.continue_btn.set_halign(Gtk.Align.CENTER)
        self.continue_btn.set_margin_top(12)
        prefs = Adw.PreferencesPage()
        prefs.add(self.intro)
        prefs.add(self.steps_group)
        g = Adw.PreferencesGroup()
        g.add(self.continue_btn)
        prefs.add(g)
        self.empty = Adw.StatusPage(icon_name="system-software-install-symbolic", title="Rebuild this machine",
                                    description="Connect (and unlock) the backup drive of the machine you want to "
                                                "recreate here.")
        self.root_stack = Gtk.Stack()
        self.root_stack.add_named(prefs, "steps")
        self.root_stack.add_named(self.empty, "empty")
        root = Adw.NavigationPage(title="Rebuild", tag="root",
                                  child=page_with_header("Rebuild", self.root_stack))
        self.nav.add(root)
        self.widget = self.nav
        self.state.connect("changed", lambda *_: self.on_show() if self.nav.get_visible_page().get_tag() == "root" else None)

    # -- the list of steps --------------------------------------------------------------------------
    def on_show(self):
        t = self.state.target
        if t is None:
            self._close_ctx()
            self.empty.set_child(button("Unlock", lambda: self.win.unlock_drive(), ("pill", "suggested-action"))
                                 if self.state.status == "locked" else None)
            self.root_stack.set_visible_child_name("empty")
            return
        if self.ctx is None or str(self.ctx.t.root) != str(t.root):
            self._close_ctx()
            self.log, _ = open_run_log(t, "rebuild")
            self.ctx = rebuild.Context(self.state.cfg, t, t.manifest(), self.log)
        self.root_stack.set_visible_child_name("steps")
        self._fill_steps()

    def _close_ctx(self):
        if self.ctx is not None:
            self.ctx.close()
            self.ctx.m.close()
            self.ctx = None
        if self.log is not None:
            close_run_log(self.log)
            self.log = None

    def _fill_steps(self):
        ctx = self.ctx
        clear(self.intro)
        info = ctx.info
        old = (info.get("machine") or {}).get("hostname", "?")
        osname = (info.get("os") or {}).get("pretty", "")
        self.intro.set_title(f"Rebuild from {ctx.old_user or '?'}@{old}")
        self.intro.set_description(
            (f"{osname} · " if osname else "") + f"backup from {when(ctx.t.read_summary().get('last_run', {}).get('finished'))}. "
            "Each step shows what it will do before it changes anything; you can skip any step.")
        clear(self.steps_group)
        state = rebuild.load_state(ctx.t)["steps"]
        for n, step in enumerate(rebuild.STEPS, 1):
            st = state.get(step.name, {})
            r = row(step.title, STATUS.get(st.get("status"), (None, None, "Not done yet"))[2]
                    + (f" · {when(st.get('when'))}" if st.get("when") else ""), activatable=True)
            num = label(f"{n}", ("step-number",), wrap=False)
            r.add_prefix(num)
            if st.get("status") in STATUS:
                icon, css, _ = STATUS[st["status"]]
                img = Gtk.Image(icon_name=icon)
                img.add_css_class(css)
                r.add_suffix(img)
            r.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
            r.connect("activated", lambda _r, s=step: self.open_step(s))
            group_add(self.steps_group, r)
        pending = [s for s in rebuild.STEPS if state.get(s.name, {}).get("status") not in ("done", "skipped")]
        self.continue_btn.set_label("Start" if len(pending) == len(rebuild.STEPS) else
                                    "Continue" if pending else "All Steps Done")
        self.continue_btn.set_sensitive(bool(pending) and not self.state.busy)

    def _continue(self):
        state = rebuild.load_state(self.ctx.t)["steps"]
        for s in rebuild.STEPS:
            if state.get(s.name, {}).get("status") not in ("done", "skipped"):
                self.open_step(s)
                return

    def open_step(self, step: rebuild.Step):
        page = StepPage(self, step)
        self.current_step = page
        self.nav.push(page.page)
        page.load()

    def next_after(self, step: rebuild.Step):
        idx = rebuild.STEPS.index(step)
        self.nav.pop_to_tag("root")
        self._fill_steps()
        if idx + 1 < len(rebuild.STEPS):
            self.open_step(rebuild.STEPS[idx + 1])

    # Screenshot mode only (the documentation): each one does what a click would do.
    def screenshot_step(self, number: str = "7"):
        """Open step N (1-8) and show its plan."""
        if self.ctx:
            self.nav.pop_to_tag("root")
            self.open_step(rebuild.STEPS[int(number) - 1])

    def screenshot_root(self):
        self.nav.pop_to_tag("root")
        if self.ctx:
            self._fill_steps()

    def screenshot_diff(self, n: str = "1"):
        """'Show Changes' for the Nth selectable item of the open /etc step."""
        page = self.current_step
        page._diff(page.plan.actionable[int(n) - 1])

    def screenshot_tick(self, keys: str):
        """Select only these items (keys separated by '|', or 'all'/'none') on the open step."""
        page = self.current_step
        wanted = set(keys.split("|"))
        for it in page.plan.actionable:
            it.selected = keys == "all" or (keys != "none" and (it.key in wanted or it.label in wanted))
        page._show_plan(page.plan)

    def screenshot_apply(self):
        self.current_step._apply()

    def screenshot_applied(self):
        """Wait until the open step has finished applying (returns 'wait' while it runs)."""
        page = self.current_step
        if page.plan is None:
            return "wait"            # still planning
        if not page.plan.actionable:
            return None              # nothing to apply: it moved on by itself
        return "wait" if self.state.busy or not page.next_btn.get_visible() else None

    def screenshot_next(self):
        """'Next Step' on the open step."""
        self.next_after(self.current_step.step)

    def screenshot_skip(self):
        self.current_step._skip()

    def screenshot_scrolllog(self):
        page = self.current_step
        buf = page.logview.get_buffer()
        page.logview.scroll_to_iter(buf.get_end_iter(), 0, False, 0, 0)


class StepPage:
    def __init__(self, owner: RebuildPage, step: rebuild.Step):
        self.owner = owner
        self.step = step
        self.ctx = owner.ctx
        self.plan: rebuild.StepPlan | None = None

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        spinner = Gtk.Spinner(width_request=48, height_request=48, spinning=True, halign=Gtk.Align.CENTER)
        self.stack.add_named(Adw.StatusPage(title="Looking at the backup and this machine…", child=spinner), "loading")

        self.prefs = Adw.PreferencesPage()
        self.notes = Adw.PreferencesGroup()
        self.items = Adw.PreferencesGroup()
        self.prefs.add(self.notes)
        self.prefs.add(self.items)
        self.stack.add_named(self.prefs, "plan")

        self.logview = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                    top_margin=12, bottom_margin=12, left_margin=12, right_margin=12)
        self.logview.add_css_class("card")
        self.apply_bar = Gtk.ProgressBar(visible=False)
        self.apply_spinner = Gtk.Spinner(spinning=True)
        self.apply_title = label("Working…", ("title-2",))
        apply_box = vbox(12, margin=24, children=[hbox(12, [self.apply_spinner, self.apply_title]),
                                                  self.apply_bar, scrolled(self.logview)])
        self.stack.add_named(clamp(apply_box, 900), "apply")

        self.skip_btn = button("Skip This Step", self._skip, ("pill",))
        self.apply_btn = button("Apply", self._apply, ("suggested-action", "pill"))
        self.next_btn = button("Next Step", lambda: owner.next_after(step), ("suggested-action", "pill"))
        self.next_btn.set_visible(False)
        self.count = label("", ("dim-label",), wrap=False)
        bar = hbox(12, [self.count, Gtk.Box(hexpand=True), self.skip_btn, self.apply_btn, self.next_btn])
        for side in ("top", "bottom", "start", "end"):
            getattr(bar, f"set_margin_{side}")(10)
        self.bar = bar
        n = rebuild.STEPS.index(step) + 1
        self.page = Adw.NavigationPage(title=step.title,
                                       child=page_with_header(f"Step {n} of {len(rebuild.STEPS)}: {step.title}",
                                                              self.stack, bottom=bar))

    def load(self):
        self.bar.set_sensitive(False)
        run_async(lambda: self.step.plan(self.ctx), self._show_plan,
                  lambda msg: (alert(self.owner.win, "Could not prepare this step", msg),
                               self.owner.nav.pop_to_tag("root")))

    def _show_plan(self, plan: rebuild.StepPlan):
        self.plan = plan
        self.bar.set_sensitive(True)
        clear(self.notes)
        clear(self.items)
        self.notes.set_visible(bool(plan.notes))
        for n in plan.notes:
            group_add(self.notes, row(n, icon="dialog-information-symbolic"))
        self.items.set_visible(bool(plan.items))
        if self.step.needs_admin and plan.actionable:
            self.items.set_description("Applying asks for your administrator password.")
        for it in plan.items:
            r = row(it.label, it.detail)
            if it.selectable:
                check = Gtk.CheckButton(active=it.selected, valign=Gtk.Align.CENTER)
                check.connect("toggled", lambda c, it=it: (setattr(it, "selected", c.get_active()), self._count()))
                r.add_prefix(check)
                r.set_activatable_widget(check)
                if isinstance(self.step, rebuild.SystemConfigStep):
                    r.add_suffix(button("Show Changes", lambda it=it: self._diff(it), ("flat",)))
            else:
                r.add_css_class("dim-label")
            group_add(self.items, r)
        if plan.actionable and len(plan.actionable) > 3:
            sel = hbox(6, [button("All", lambda: self._select(True), ("flat",)),
                           button("None", lambda: self._select(False), ("flat",))])
            self.items.set_header_suffix(sel)
        self.apply_btn.set_label("Apply" if plan.actionable else "Continue")
        self._count()
        self.stack.set_visible_child_name("plan")

    def _select(self, on: bool):
        for it in self.plan.actionable:
            it.selected = on
        self._show_plan(self.plan)

    def _count(self):
        if not self.plan or not self.plan.actionable:
            self.count.set_label("")
            return
        n = sum(1 for i in self.plan.actionable if i.selected)
        self.count.set_label(f"{n} of {len(self.plan.actionable)} selected")

    def _diff(self, item):
        text = rebuild.SystemConfigStep.diff(item) or "(binary file or no readable difference)"
        tv = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.NONE)
        tv.get_buffer().set_text(text)
        sw = Gtk.ScrolledWindow(min_content_height=360, min_content_width=640, child=tv)
        alert(self.owner.win, item.key, "Lines starting with + come from the backup, - from this machine.",
              (("close", "Close"),), extra=sw)

    def _out(self, line: str):
        def add():
            buf = self.logview.get_buffer()
            buf.insert(buf.get_end_iter(), line + "\n")
            self.logview.scroll_to_mark(buf.get_insert(), 0, False, 0, 0)
        on_main(add)

    def _skip(self):
        rebuild.save_state(rebuild.load_state(self.ctx.t), self.step.name, "skipped", [])
        self.owner.next_after(self.step)

    def _apply(self):
        selected = [i for i in self.plan.actionable if i.selected]
        if not self.plan.actionable:
            rebuild.save_state(rebuild.load_state(self.ctx.t), self.step.name, "done", [])
            self.owner.next_after(self.step)
            return
        self.stack.set_visible_child_name("apply")
        self.skip_btn.set_visible(False)
        self.apply_btn.set_visible(False)
        self.count.set_label("")
        self.owner.state.set_busy(True)
        kwargs = {}
        if self.step.name == "home":
            self.apply_bar.set_visible(True)

            def progress(p):
                frac = p.bytes_done / p.bytes_total if p.bytes_total else 1.0
                on_main(lambda: (self.apply_bar.set_fraction(min(frac, 1.0)),
                                 self.apply_bar.set_text(f"{human_size(p.bytes_done)} of {human_size(p.bytes_total)}"),
                                 self.apply_bar.set_show_text(True)))
            kwargs["on_progress"] = progress
        run_async(lambda: self.step.apply(self.ctx, selected, self._out, **kwargs), self._applied, self._apply_failed)

    def _applied(self, warnings):
        self.owner.state.set_busy(False)
        rebuild.save_state(rebuild.load_state(self.ctx.t), self.step.name, "done", warnings)
        self.apply_spinner.set_spinning(False)
        self.apply_title.set_label("Done" if not warnings else f"Done, with {len(warnings)} warnings")
        for w in warnings:
            self._out(f"⚠ {w}")
        self.next_btn.set_visible(True)
        toast(self.page.get_child(), f"{self.step.title}: done")

    def _apply_failed(self, msg):
        self.owner.state.set_busy(False)
        rebuild.save_state(rebuild.load_state(self.ctx.t), self.step.name, "failed", [msg])
        self.apply_spinner.set_spinning(False)
        self.apply_title.set_label("This step failed")
        self._out(msg)
        self.next_btn.set_visible(True)
