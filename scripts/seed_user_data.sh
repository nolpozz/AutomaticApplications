#!/usr/bin/env bash
# Seed your private user_data/ from the committed example template.
# user_data/ is gitignored, so your real background is never pushed to GitHub.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -n "$(find user_data -type f ! -name '.gitkeep' 2>/dev/null)" ]; then
  echo "user_data/ already has content — not overwriting. Edit those files directly."
  exit 0
fi

cp -r user_data.example/. user_data/
echo "Seeded user_data/ from user_data.example/. Now edit user_data/profile.yaml and folders."
echo "Reminder: user_data/ is gitignored and will NOT be committed."
