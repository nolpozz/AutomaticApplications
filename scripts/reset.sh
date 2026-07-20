#!/usr/bin/env bash
# Delete all generated runtime state (database, documents, workbook, logs).
# user_data/ and config are never touched.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "This will delete the data/ directory (database, documents, workbook, logs)."
read -r -p "Continue? [y/N] " reply
if [[ "$reply" =~ ^[Yy]$ ]]; then
  rm -rf data
  mkdir -p data && touch data/.gitkeep
  echo "Reset complete."
else
  echo "Aborted."
fi
