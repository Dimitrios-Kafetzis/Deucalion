# Rebuild

The **Rebuild** page sets up this computer from a full backup, in eight steps. For the full
walk-through, see [Rebuild your computer](../tutorials/rebuild.md); for what each step does and
doesn't do, see [What a rebuild restores](../concepts/rebuild.md).

![The Rebuild page: "Rebuild from alex@alex-laptop", Ubuntu 24.04.5 LTS, the eight steps and a Start
button.](../assets/screenshots/rebuild/rebuild-start.png){ .shot }

## The list of steps

- The title says which computer and user the backup comes from, its Ubuntu version and when it was
  made.
- Each step shows **Not done yet**, **Done**, **Skipped** or **Failed**, with when. Click a step to
  open it (also to run it again).
- **Start** opens the first step; later it reads **Continue** (the first step not done or skipped), or
  **All Steps Done**.

If the drive isn't connected the page says so; if it is locked it has an **Unlock** button:

![The Rebuild page when the drive is locked: "Rebuild this machine" and an Unlock button.](../assets/screenshots/app/rebuild-locked.png){ .shot }

## A step

![Step 8 of 8: the items with tick boxes, "3 of 3 selected", and the buttons Skip This Step and
Apply.](../assets/screenshots/rebuild/rebuild-services.png){ .shot }

- While the step looks at the backup and this computer, it says *Looking at the backup and this
  machine…*. Nothing is changed.
- **Notes** (with an ⓘ) explain things worth knowing.
- **Items** have tick boxes; greyed-out items are for information only. The count at the bottom left
  says how many are selected. With more than three, **All** and **None** buttons appear.
- In step 7, **Show Changes** next to each file shows the difference between this computer's file and
  the backup's (`+` lines from the backup, `-` from this computer).
- *Applying asks for your administrator password* appears on steps that need it.

Buttons:

| Button | What it does |
|---|---|
| **Skip This Step** | Marks the step **Skipped** and opens the next one. |
| **Apply** | Applies the ticked items. A log shows what happens; step 4 also shows a progress bar. |
| **Continue** | (Instead of **Apply**, when the step has nothing to do.) Marks it done and opens the next one. |
| **Next Step** | After applying: opens the next step. |
| ‹ (top left) | Back to the list. |

![Step 2 applied: "Done", the log, and Next Step.](../assets/screenshots/rebuild/rebuild-repos-done.png){ .shot }

When a step fails, it says **This step failed** with the reason in the log. Fix the cause and open the
step again from the list.

## Related

- [`deucalion rebuild`](../cli/rebuild.md)
