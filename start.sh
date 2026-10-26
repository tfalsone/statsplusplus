#!/usr/bin/env bash
set -e

echo ""
echo "  Stats++ Launcher"
echo "  ================="
echo ""

# Find Python
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        if "$cmd" -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "  [ERROR] Python 3.10+ not found."
    echo ""
    echo "  Install Python:"
    echo "    macOS:  brew install python3"
    echo "    Ubuntu: sudo apt install python3-full"
    echo "    Other:  https://www.python.org/downloads/"
    echo ""
    exit 1
fi

# Guard the most common mis-extract: the unzip tool created a nested
# statsplusplus-vX.Y.Z/ folder, so the real files sit one level down and the
# launcher is running in the wrong place. Detect it and give a clear fix
# instead of a cryptic "No module named statsplusplus" later.
if [ ! -f "pyproject.toml" ] || [ ! -f "web/app.py" ]; then
    NESTED="$(find . -maxdepth 2 -name pyproject.toml -path '*/pyproject.toml' 2>/dev/null | head -n1)"
    echo ""
    echo "  [ERROR] Stats++ files aren't where the launcher expects them."
    if [ -n "$NESTED" ]; then
        echo "          It looks like the zip extracted into a subfolder:"
        echo "            $(dirname "$NESTED")"
        echo "          Move everything from that subfolder up into THIS folder"
        echo "          (so start.sh / start.bat sit next to pyproject.toml), then re-run."
    else
        echo "          Re-extract the release zip into this folder so start.sh sits"
        echo "          next to pyproject.toml and the web/ folder."
    fi
    echo ""
    exit 1
fi

# Create virtual environment if needed
if [ ! -d ".venv" ]; then
    echo "  Creating virtual environment..."
    "$PYTHON" -m venv .venv
fi

# Install/update the package (editable). This installs Flask (from pyproject)
# AND puts the statsplusplus package (src/ layout) on the path — required, or
# the app fails with "No module named 'statsplusplus'".
#
# Version-aware: pip skips reinstalling an editable package it thinks is already
# satisfied, so after extracting a new zip the registered metadata can lag the
# shipped code. We compare the version pip last registered against the version
# in the freshly-extracted pyproject.toml and force a clean reinstall when they
# differ, then report the result so the user KNOWS the update landed.
INSTALLED_VER="$(.venv/bin/python -c 'from importlib.metadata import version; print(version("statsplusplus"))' 2>/dev/null || echo "none")"
SHIPPED_VER="$(grep -m1 -E '^\s*version\s*=' pyproject.toml | sed -E 's/.*"([^"]+)".*/\1/')"

echo "  Checking dependencies..."
if [ "$INSTALLED_VER" != "$SHIPPED_VER" ]; then
    # New version (or first install) — force a clean reinstall of the metadata.
    if ! .venv/bin/pip install -e . >/tmp/spp_install.log 2>&1; then
        echo ""
        echo "  [ERROR] Update install failed. The extracted files may be incomplete."
        echo "          Try re-extracting the release zip over this folder, then re-run."
        echo "          Details: /tmp/spp_install.log"
        echo ""
        exit 1
    fi
    if [ "$INSTALLED_VER" = "none" ]; then
        echo "  Installed Stats++ v${SHIPPED_VER}."
    else
        echo "  Updated: v${INSTALLED_VER} -> v${SHIPPED_VER}"
    fi
else
    # Same version — a quiet, fast satisfied-check keeps startup snappy.
    .venv/bin/pip install -q -e . >/dev/null 2>&1 || .venv/bin/pip install -e .
    echo "  Already up to date: v${SHIPPED_VER}"
fi

# Prune stale files left over from a previous version (manifest-based; no-op in
# dev checkouts that lack MANIFEST.txt). See prune_stale.py.
.venv/bin/python3 prune_stale.py 2>/dev/null || true

echo ""
echo "  Starting Stats++..."
echo "  Open your browser to: http://localhost:5001"
echo ""
echo "  Press Ctrl+C to stop the server."
echo ""

# Open browser after a short delay (background)
(sleep 2 && {
    if command -v xdg-open &>/dev/null; then
        xdg-open "http://localhost:5001" 2>/dev/null
    elif command -v open &>/dev/null; then
        open "http://localhost:5001"
    fi
}) &

# Run the server
.venv/bin/python3 web/app.py
