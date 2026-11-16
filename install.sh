#!/usr/bin/env bash
# Prism installer for macOS.
# Installs what is missing (Python 3.9+, Git, GitHub CLI, Node.js), then runs install.py.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OS="$(uname -s)"

have() { command -v "$1" >/dev/null 2>&1; }

python_ok() {
  for p in python3 python; do
    if have "$p" && "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
      PY="$(command -v "$p")"; return 0
    fi
  done
  return 1
}

install_mac() {
  if ! have brew; then
    echo "Installing Homebrew (it may ask for your password)..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"; fi
    if [ -x /usr/local/bin/brew ]; then eval "$(/usr/local/bin/brew shellenv)"; fi
  fi
  python_ok || brew install python@3.12
  have git || brew install git
  have gh || brew install gh
  have node || brew install node
}


case "$OS" in
  Darwin) install_mac ;;
  *) echo "Prism supports macOS. Windows and Linux support are in Prism Pro."; exit 1 ;;
esac

python_ok || { echo "Python 3.9+ is still missing. Install it and run: python3 install.py"; exit 1; }
exec "$PY" "$HERE/install.py" "$@"
