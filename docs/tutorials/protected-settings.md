# Include protected settings

**What you'll do:** decide whether full backups also save the settings that only the administrator
can read.<br>
**What you need:** your administrator password, at each full backup.<br>
**How long it takes:** 1 minute.

Some parts of the [system recipe](../concepts/system-recipe.md) can only be read by the administrator:

- your saved **Wi-Fi and VPN connections**, with their passwords;
- some system settings files in `/etc`;
- the administrator's scheduled tasks (root's crontab).

With **protected settings** on (the default), Ubuntu asks for your administrator password at the
start of each full backup, and these are saved too. A [rebuild](rebuild.md) can then put your Wi-Fi
networks back on a new computer.

!!! warning "Passwords on the drive"
    Saved connections contain their passwords. On a drive that isn't encrypted, anyone with the drive
    can read them. Use an [encrypted drive](../choosing-a-drive.md), or turn protected settings off.

=== "App"

    - **On the Back Up page**: with **Everything** chosen, the switch **Include protected settings**.
    - **On the Settings page**: **Include protected system settings** (the same setting).

    ![The Back Up page's options: Save system settings, and Include protected settings ("Wi-Fi
    passwords and settings only the administrator can read. You will be asked for your password.").](../assets/screenshots/app/backup-choose.png){ .shot }

    Turn it off to never be asked. It is remembered for the next backups.

=== "Command line"

    It is on unless you turn it off in the [configuration file](../reference/configuration.md)
    (`"system_admin": false`) or the app. For one backup, `--no-admin` skips it:

    ```text
    --8<-- "snippets/cli/backup-no-admin.txt"
    ```

    The warning means: the protected settings saved by an **earlier** backup are kept as they were;
    they are just not updated this time.

When the administrator password isn't given (you cancel the password window, or turn the option off),
everything else is still backed up, and a copy of the protected settings from an earlier backup is
kept, never deleted.

**What you have now:** you know when Deucalion asks for your administrator password, and why.

**Next steps:** [Administrator access](../concepts/administrator-access.md) explains how that password
is used.
