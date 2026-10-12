#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Dimitrios Kafetzis
# Runs INSIDE the documentation VM ("Alex's laptop", Ubuntu 24.04) before the first full backup:
# gives the machine a few things a real desktop has, so the system recipe and the rebuild steps
# have something to show. Everything here is fictional demo setup.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# A real Ubuntu Desktop records its installation in /var/log/installer; a cloud image doesn't. Deucalion
# uses that date to tell the installer's own /etc files from later changes, so mark "installed now".
sudo mkdir -p /var/log/installer && sudo touch /var/log/installer

# A third-party apt repository with its key (Google Chrome's, without installing Chrome) and a PPA
curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | sudo gpg --batch --yes --dearmor -o /etc/apt/keyrings/google-chrome.gpg
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main" \
    | sudo tee /etc/apt/sources.list.d/google-chrome.list >/dev/null
sudo add-apt-repository -y -n ppa:git-core/ppa >/dev/null 2>&1
sudo apt-get update -q >/dev/null

# Some apps: apt packages, a snap, and a package from a downloaded .deb file
sudo apt-get install -y -q --no-install-recommends htop tree git >/dev/null
sudo snap install hello-world >/dev/null
mkdir -p /tmp/hello-tool/DEBIAN /tmp/hello-tool/usr/local/bin
cat > /tmp/hello-tool/DEBIAN/control <<'EOF'
Package: hello-tool
Version: 1.2.0
Architecture: all
Maintainer: Demo <demo@example.com>
Description: A small demo tool installed from a downloaded .deb file
EOF
printf '#!/bin/sh\necho hello\n' > /tmp/hello-tool/usr/local/bin/hello-tool
chmod 755 /tmp/hello-tool/usr/local/bin/hello-tool
mkdir -p ~/Downloads
dpkg-deb --build --root-owner-group /tmp/hello-tool ~/Downloads/hello-tool_1.2.0_all.deb >/dev/null
sudo apt-get install -y -q ~/Downloads/hello-tool_1.2.0_all.deb >/dev/null

# Scheduled task, a user service, groups
{ crontab -l 2>/dev/null || true; echo "0 9 * * 1 $HOME/Projects/scripts/backup-photos.sh"; } | crontab -
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/notes-sync.service <<EOF
[Unit]
Description=Sync my notes (demo)
[Service]
ExecStart=/bin/true
[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload && systemctl --user enable notes-sync.service >/dev/null 2>&1 || true
sudo usermod -aG dialout "$USER"

# System settings in /etc: a udev rule, a kernel setting, a changed config file, a hosts entry
echo 'SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", MODE="0666"' | sudo tee /etc/udev/rules.d/99-usb-serial.rules >/dev/null
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swappiness.conf >/dev/null
sudo sed -i 's/^# set linenumbers/set linenumbers/' /etc/nanorc
echo '192.168.1.20  nas' | sudo tee -a /etc/hosts >/dev/null
# ...made "later" than the installation (on a real laptop: days or months later)
sudo touch -d '+2 hours' /etc/udev/rules.d/99-usb-serial.rules /etc/sysctl.d/99-swappiness.conf /etc/hosts

# A saved Wi-Fi connection (NetworkManager), with its password
sudo nmcli connection add type wifi con-name "Home Wi-Fi" ifname '*' ssid "HomeNet" \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk "demo-password-123" >/dev/null

# Desktop settings
dbus-run-session -- bash -c "dconf write /org/gnome/desktop/interface/color-scheme \"'prefer-dark'\";
  dconf write /org/gnome/desktop/interface/clock-show-weekday true;
  dconf write /org/gnome/shell/favorite-apps \"['org.gnome.Nautilus.desktop', 'firefox_firefox.desktop']\""

# An extra folder outside the home folder
sudo mkdir -p /srv/shared && sudo chown "$USER:$USER" /srv/shared
printf 'Family recipes, shared with the NAS.\n' > /srv/shared/README.txt
mkdir -p /srv/shared/scans && head -c 300000 /dev/urandom > /srv/shared/scans/passport.pdf
echo "old machine ready"
