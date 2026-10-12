# FAQ

## Why do some file names look odd on my drive?

On an exFAT or NTFS drive, characters that those formats don't allow (`: * ? " < > | \`) are stored as
look-alike characters (`report： final？.txt`), and a name that differs from another only by upper or
lower case gets a number (`notes (2).txt`). **Deucalion always restores the original names**; it keeps
them in the [manifest](../concepts/manifest.md). See [File names on exFAT](../concepts/file-names.md).

## `verify --full` is very slow. Is something wrong?

No. The full check reads every byte of the backup from the drive to compare checksums, so it takes as
long as reading the whole backup: about 15 minutes per 100 GB at 120 MB per second (a typical USB hard
disk), longer on slow drives. The quick check (`deucalion verify`) only checks that every file is there
with the right size and takes seconds. Run the full check now and then, not every time. You can stop it
with ++ctrl+c++; problems found until then are still marked for the next backup.

## The power went off (or I unplugged the drive) during a backup

Plug the drive in again and **run the backup again**. That's all. The manifest is written so that it
survives a sudden stop; files half-copied are thrown away and copied again; leftovers on the drive are
moved to Removed Files. The **Overview** page may show the last backup as *Interrupted* until the next
one finishes. Your computer's files are never changed by a backup.

If the drive was encrypted and is now "busy" or can't be locked, unplug and plug it in again, or
restart the computer.

## The power went off during a restore or a rebuild

Run it again. A restore puts back what it was replacing if it is stopped; files already restored stay.
A rebuild remembers which steps are done; run `deucalion rebuild` again (or open **Rebuild** in the app)
and it continues. A step stopped in the middle can be run again safely.

## I forgot my backup password

**It can't be recovered.** Not by you, not by Deucalion, not by anyone: that is what encryption
means. Deucalion never stores the password.

- If your computer still works, set the drive up again with a new password (this erases it) and make a
  new full backup. Your files are still on your computer.
- If your computer is lost and you don't remember the password, the backup can't be opened.

Write the password down and keep it somewhere safe, away from the computer and the drive.

## Can I use the drive for other files too?

Yes, with the **Encrypted part + normal part** layout (use the normal part), the **Encrypted folder**
layout, or a drive used **as it is**. Don't put your own files inside `Deucalion-Backup`, and don't
rename or move that folder (or `Deucalion-Backup.hc` / `.luks`).

## Can I back up two computers to the same drive?

Not to the same backup folder: each backup mirrors one computer and user, and Deucalion warns if the
drive holds another computer's backup. Use one drive per computer, or give each computer its own folder
on the drive with [`deucalion register`](../cli/register.md) (for example `register /media/alex/Big/laptop`
and `register /media/alex/Big/desktop`).

## Can I keep several copies, for example a drive at home and one at the office?

Yes. Set up both; each is a separate backup drive. Choose which one to back up to on the **Drives** page
(the star button) or with `--target NAME`.

## Does Deucalion back up automatically?

Not in version 0.2: it runs when you start it. Automatic backups are planned.

## Does it keep older versions of my files?

The backup holds the latest version. When a file changes, the previous version is moved to
[Removed Files](../concepts/mirror-and-removed.md), dated by backup. That is not a full history of every
day, but it does keep every version that a backup replaced, until you empty it.

## How do I restore onto Windows or a Mac?

Deucalion restores onto Ubuntu only. On Windows or macOS you can open the backup and copy files (see
[Open your backup without Deucalion](../tutorials/open-without-deucalion.md)).

## Does it back up Docker containers or virtual machines?

Not in version 0.2. Files of virtual machines in your home folder (for example `~/VirtualBox VMs`) are
backed up like any files; Docker's own storage is not. The system recipe only lists Docker images and
volumes and libvirt machines, by name. Large virtual disk files may change on every use: consider
[leaving them out](../tutorials/leave-out.md) and backing them up separately.

## Is my backup password or my data sent anywhere?

No. Deucalion runs on your computer and talks only to your drive. The only internet use: downloading
VeraCrypt (when you ask), and, during a rebuild, checking that your software sources exist for the new
Ubuntu version and installing packages.

## Which Ubuntu versions does it work on?

The app needs **Ubuntu 24.04 or newer**. The command line works on **Ubuntu 22.04 or newer** (Python
3.10 or newer), so on 22.04 you can do everything with [commands](../cli/index.md). It was tested by
hand on Ubuntu 24.04 and 26.04, and its automated tests run on 22.04 and 24.04. A rebuild works
from an older Ubuntu version to a newer one (for example 24.04 → 26.04); it also works onto the same
version.
