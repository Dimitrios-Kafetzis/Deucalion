#!/bin/bash
# Install Deucalion for the current user (no administrator rights needed):
#   ~/.local/share/deucalion        the program
#   ~/.local/bin/deucalion          the command
#   app menu entry and icon
#
#   ./install.sh                    check and install what is needed, then install Deucalion
#   ./install.sh --system-helper    also install the administrator helper system-wide (asks for
#                                   your password): a root-owned copy, so code that runs as root
#                                   can't be changed by other programs, and a clearer password prompt
#   ./install.sh --uninstall        remove it (your backups and settings are kept)
# Extra options: --veracrypt / --no-veracrypt (install VeraCrypt or not, without asking), --yes
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ID=io.github.DimitriosKafetzis.Deucalion
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
DEST="$DATA/deucalion"
BIN="$HOME/.local/bin"
HELPER_DIR=/usr/local/libexec/deucalion
POLICY=/usr/share/polkit-1/actions/$APP_ID.policy

SYSTEM_HELPER=0; UNINSTALL=0; DEPS_ARGS=()
for arg in "$@"; do
    case "$arg" in
        --system-helper) SYSTEM_HELPER=1 ;;
        --uninstall) UNINSTALL=1 ;;
        --veracrypt|--no-veracrypt|--yes|-y) DEPS_ARGS+=("$arg") ;;
        *) echo "Unknown option: $arg"; exit 2 ;;
    esac
done
as_admin() { if [[ -t 0 ]]; then sudo "$@"; else pkexec "$@"; fi; }

if [[ $UNINSTALL == 1 ]]; then
    rm -rf "$DEST" "$BIN/deucalion" "$DATA/applications/$APP_ID.desktop" \
           "$DATA/icons/hicolor/scalable/apps/$APP_ID.svg" "$DATA/icons/hicolor/symbolic/apps/$APP_ID-symbolic.svg"
    if [[ -e "$HELPER_DIR" || -e "$POLICY" ]]; then
        echo "Removing the system helper (asks for your password)…"
        as_admin rm -rf "$HELPER_DIR" "$POLICY"
    fi
    echo "Deucalion was removed. Your backups and ~/.config/deucalion are kept."
    exit 0
fi

python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || { echo "Python 3.10 or newer is needed."; exit 1; }

echo "Checking what Deucalion needs…"
python3 "$SRC/bin/deucalion" deps --install "${DEPS_ARGS[@]}" || echo "Continuing; see above for what is missing."
echo

echo "Installing Deucalion into $DEST"
rm -rf "$DEST.new"
mkdir -p "$DEST.new"
cp -r "$SRC/deucalion" "$SRC/bin" "$SRC/data" "$SRC/README.md" "$DEST.new/"
find "$DEST.new" -name __pycache__ -type d -prune -exec rm -rf {} +
rm -rf "$DEST"
mv "$DEST.new" "$DEST"

mkdir -p "$BIN"
ln -sf "$DEST/bin/deucalion" "$BIN/deucalion"

mkdir -p "$DATA/applications" "$DATA/icons/hicolor/scalable/apps" "$DATA/icons/hicolor/symbolic/apps"
sed "s|^Exec=.*|Exec=$BIN/deucalion|" "$SRC/data/$APP_ID.desktop" > "$DATA/applications/$APP_ID.desktop"
cp "$SRC/data/icons/hicolor/scalable/apps/$APP_ID.svg" "$DATA/icons/hicolor/scalable/apps/"
cp "$SRC/data/icons/hicolor/symbolic/apps/$APP_ID-symbolic.svg" "$DATA/icons/hicolor/symbolic/apps/"
command -v update-desktop-database >/dev/null && update-desktop-database "$DATA/applications" 2>/dev/null || true
command -v gtk4-update-icon-cache >/dev/null && gtk4-update-icon-cache -q -t "$DATA/icons/hicolor" 2>/dev/null || true

if [[ -e "$HELPER_DIR/helper.py" ]] && ! cmp -s "$SRC/deucalion/helper.py" "$HELPER_DIR/helper.py"; then
    echo "The installed administrator helper is from another version; updating it too."
    SYSTEM_HELPER=1
fi
if [[ $SYSTEM_HELPER == 1 ]]; then
    echo "Installing the administrator helper (asks for your password)…"
    as_admin sh -c "install -d -m 0755 -o root -g root '$HELPER_DIR' && \
        install -m 0755 -o root -g root '$SRC/deucalion/helper.py' '$HELPER_DIR/helper.py' && \
        install -m 0644 -o root -g root '$SRC/data/$APP_ID.policy' '$POLICY'"
fi

case ":$PATH:" in
    *":$BIN:"*) ;;
    *) echo "Note: add $BIN to your PATH to run 'deucalion' from a terminal." ;;
esac
echo "Done. Open Deucalion from the app menu, or run: deucalion"
