# Security policy

Deucalion handles people's files, backup passwords and encrypted drives. Part of it runs as root (the
administrator helper, `deucalion/helper.py`). Security reports are very welcome and are taken
seriously.

## Supported versions

Security fixes are made for the latest release only. Please update before reporting.

| Version | Supported |
|---|---|
| 0.2.x (latest) | Yes |
| older | No |

## Reporting a vulnerability

**Please don't open a public issue.** Report it privately through GitHub instead:

1. Go to the [Security tab](https://github.com/Dimitrios-Kafetzis/Deucalion/security) of the repository.
2. Click **Report a vulnerability**
   ([direct link](https://github.com/Dimitrios-Kafetzis/Deucalion/security/advisories/new)).
3. Describe the problem, how to reproduce it, and what an attacker could do with it.

Only the maintainer can see the report. You can expect:

- a reply within **7 days**;
- a fix, or a plan for one, as soon as the problem is confirmed;
- credit in the release notes and the security advisory, if you want it.

## What counts

Examples of what is in scope:

- the administrator helper doing anything outside its fixed list of operations, or accepting
  arguments it should refuse (for example touching the system disk or files outside its scope);
- ways for another local user or program to make Deucalion run code as root;
- backup or VeraCrypt passwords being written to disk, logs or process arguments;
- the VeraCrypt installer accepting a package without a valid signature from VeraCrypt's key;
- a backup or restore that can be tricked into reading or writing outside the intended folders
  (for example through symbolic links on the backup drive).

Not in scope: someone who already has your administrator password or root access, and files on an
**unencrypted** backup drive being readable by whoever holds the drive (that is by design; choose an
encrypted layout to prevent it).

## How Deucalion limits risk

The design is described in
[Administrator access](https://dimitrios-kafetzis.github.io/Deucalion/concepts/administrator-access/)
and [Choosing a drive](https://dimitrios-kafetzis.github.io/Deucalion/choosing-a-drive/) (encryption).
