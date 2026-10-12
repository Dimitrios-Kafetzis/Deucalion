# Save and use a profile

**What you'll do:** save a list of folders under a name, then back them up with one short
command.<br>
**What you need:** a terminal (profiles are only available on the command line).<br>
**How long it takes:** 2 minutes.

=== "App"

    The app has no profiles. Use **Back Up → Only some folders** and add the folders each time (see
    [Back up only some folders](some-folders.md)), or use the command line for this.

=== "Command line"

    1. Save a profile called `work` with two folders:

        ```text
        --8<-- "snippets/cli/profile-add.txt"
        ```

    2. Back up with it:

        ```text
        --8<-- "snippets/cli/backup-profile.txt"
        ```

        Here nothing had changed, so nothing was copied.

    3. See your profiles with `deucalion profile`; change one by saving it again with the same name;
       delete one with `deucalion profile remove work`.

**What you have now:** a profile you can back up with `deucalion backup --profile work`.

**Next steps:** see [`deucalion profile`](../cli/profile.md) for all options.
