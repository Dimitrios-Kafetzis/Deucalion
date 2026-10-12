# `deucalion rebuild`

Rebuilds this computer from a full backup, in eight steps (see
[What a rebuild restores](../concepts/rebuild.md)). For each step it shows the plan, then asks.
Nothing changes until you press ++enter++ on a step.

```text
--8<-- "snippets/cli/help-rebuild.txt"
```

| Option | What it does |
|---|---|
| *(none)* | Go through the steps that aren't done yet, asking at each one. |
| `--step NAME` | Run only this step (again, even if it was done): `check`, `repositories`, `packages`, `home`, `paths`, `desktop`, `system-config` or `services`. |
| `--dry-run` | Show every step's plan and change nothing. |
| `-y`, `--yes` | Apply the pre-selected items of every step without asking. |
| `--target NAME` | Which backup drive. |

`rebuild` needs a terminal to ask its questions; without one, use `--dry-run` or `--yes`.

## Answering a step

Each step shows its notes, then its items with a number: `[x]` items are selected, `[ ]` items are
not, and lines with `-` are for information only. For example, step 3 of the run below:

```text
--8<-- "snippets/cli/rebuild-cli.txt:22:32"
```

Then it waits at the `>` prompt:

| You type | What happens |
|---|---|
| ++enter++ (or `y`) | Apply the selected items. |
| `n` (or `s`, `skip`) | Skip this step. |
| numbers, e.g. `2` or `2 5-7` | Select or unselect those items (the list is shown again). |
| `all` / `none` | Select all / none of the items. |
| `d N`, e.g. `d 2` | Show the changes for item N (step 7: what is different in that `/etc` file; `+` lines come from the backup, `-` lines from this computer). |
| `q` | Stop here. Run `deucalion rebuild` again later to continue. |

Step 1 (the check) asks **Continue? [y/N]** instead: answer `y` once you have read it.

## A dry run

`--dry-run` shows what every step would do, and changes nothing:

??? example "The dry run on Alex's new laptop (click to open)"

    ```text
    --8<-- "snippets/cli/new-rebuild-dry-run.txt"
    ```

## A complete run

On a new laptop with Ubuntu 26.04 and the user name `alexk`, from a backup of `alex` on Ubuntu 24.04
(run from the backup drive's `Deucalion-Tool` folder):

```text
--8<-- "snippets/cli/rebuild-cli.txt"
```

## Running it again

Finished steps are skipped (with how to run them again); a second run changes nothing that is
already right:

```text
--8<-- "snippets/cli/rebuild-again.txt"
```

Progress is kept in `~/.local/state/deucalion/rebuild.json`, for the backup drive in use. To redo one
step, use `--step`:

```text
--8<-- "snippets/cli/rebuild-step-again.txt"
```

## Exit codes

`0` done, stopped with `q`, or `--dry-run`; `1` you didn't continue after step 1, or an error;
`130` stopped with ++ctrl+c++.

A step that fails is reported (`failed`) and the rebuild moves on to the next step; run that step
again with `--step` once the problem is fixed. At the end a **Summary** lists each step (`done`,
`skipped` or `failed`, with its number of warnings) and reminds you to **log out and back in**.

## Related

- [Rebuild your computer](../tutorials/rebuild.md) (the full walk-through)
- The app's [Rebuild](../app/rebuild.md) page
