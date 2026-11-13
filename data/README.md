# Data

Nothing in `raw/`, `processed/` or `cache/` is committed (see `.gitignore`).

## S-Bank synthetic dataset
Source: https://github.com/hackjunction/Junction-2026-S-pankki (provided for Junction 2026).

**Quickest:** from the repo root run `bash scripts/get_data.sh` (downloads all four CSVs into `data/raw/`).

Or manually: put the four CSVs in `data/raw/`. `tx_junction_transactions.csv` (~346 MB) is stored with Git LFS:
- Easiest: open the file on GitHub and click **Download raw file**. "Download ZIP" may give you only a pointer file.
- Or install git-lfs (`git lfs install`), clone the repo, then run `git lfs pull`.
- Check: `head -c 200 data/raw/tx_junction_transactions.csv` must show CSV data, not `version https://git-lfs...`.

Then run: `cd backend && python -m kukkaro.data.prepare`

## Open data
List every downloaded open-data file here with its source URL and licence.
