#!/usr/bin/env bash
# Downloads S-Bank's synthetic Junction 2026 dataset into data/raw/ (never committed).
# Source: https://github.com/hackjunction/Junction-2026-S-pankki
# Usage (from the repo root): bash scripts/get_data.sh
set -euo pipefail

REPO="hackjunction/Junction-2026-S-pankki"
BRANCH="main"
DEST="$(cd "$(dirname "$0")/.." && pwd)/data/raw"
mkdir -p "$DEST"

# Small files: normal raw URLs.
for f in tx_customers_junction.csv mtg_negotiation_history.csv mtg_tx_customer_link_and_final_mtg_infio.csv; do
  echo "Downloading $f"
  curl -fL --retry 3 -o "$DEST/$f" "https://raw.githubusercontent.com/$REPO/$BRANCH/$f"
done

# The big transactions file is stored with Git LFS: use the LFS media URL.
f=tx_junction_transactions.csv
echo "Downloading $f (~346 MB)"
curl -fL --retry 3 -o "$DEST/$f" "https://media.githubusercontent.com/media/$REPO/$BRANCH/$f"

# Check that we got real data, not an LFS pointer file.
if head -c 40 "$DEST/$f" | grep -q "git-lfs"; then
  echo "ERROR: got an LFS pointer instead of data. Download it manually: open the file on GitHub and click 'Download raw file'." >&2
  exit 1
fi

echo "Done. Files in $DEST:"
ls -lh "$DEST"
