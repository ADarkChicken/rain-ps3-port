# Compact view of lift packets + skeleton declaration for the given types (M5), stubs-only once work/recon/<Type>.cs exists.
# Usage: bash tools/recon_view.sh [--all] Type [...]   (wrapper around recon_view.py)
cd "$(dirname "$0")/.." && exec tools/.venv/Scripts/python -I tools/recon_view.py "$@"
