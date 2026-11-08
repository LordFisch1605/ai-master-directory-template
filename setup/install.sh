#!/usr/bin/env bash
# Linux/macOS bootstrap: installs Python 3 if it is missing, then runs the interactive setup.
#   bash setup/install.sh
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  read -r -p "Python 3 is missing. Install it with your package manager? [Y/n] " answer
  case "$answer" in [nN]*) echo "Install Python 3, then run this again."; exit 1 ;; esac
  if [ "$(uname)" = "Darwin" ]; then
    command -v brew >/dev/null 2>&1 || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
    brew install python
  elif command -v apt-get >/dev/null 2>&1; then sudo apt-get update && sudo apt-get install -y python3 python3-pip
  elif command -v dnf >/dev/null 2>&1; then sudo dnf install -y python3 python3-pip
  elif command -v pacman >/dev/null 2>&1; then sudo pacman -S --noconfirm python python-pip
  else echo "No known package manager. Install Python 3, then run this again."; exit 1
  fi
fi
python3 "$here/setup.py"
