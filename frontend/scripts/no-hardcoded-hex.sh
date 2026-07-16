#!/bin/bash
# Pre-commit hook: block new hardcoded hex in *.jsx
# Exceptions: #fff/#FFFFFF (white text), lines with "zodiac data-color" comment,
#             files: tailwind.config.js, index.css

ERRORS=0

for file in $(git diff --cached --name-only --diff-filter=ACM | grep '\.jsx$'); do
  # Skip non-frontend files
  [[ "$file" != frontend/src/* ]] && continue

  # Get only added/changed lines (+ lines in diff)
  LINES=$(git diff --cached -U0 "$file" | grep '^+' | grep -v '^+++' | grep -oE '#[0-9A-Fa-f]{3,8}')

  for hex in $LINES; do
    hex_lower=$(echo "$hex" | tr '[:upper:]' '[:lower:]')
    # Allow #fff and #ffffff (white text on buttons)
    [[ "$hex_lower" == "#fff" || "$hex_lower" == "#ffffff" ]] && continue

    # Check if the line has "data-color" comment
    LINE_CONTENT=$(git diff --cached -U0 "$file" | grep '^+' | grep -v '^+++' | grep "$hex" | head -1)
    echo "$LINE_CONTENT" | grep -q "data-color" && continue

    echo "ERROR: Hardcoded hex $hex in $file"
    echo "  → Use CSS var (var(--accent), var(--text-primary), etc.) or mark as /* zodiac data-color, intentional */"
    ERRORS=$((ERRORS + 1))
  done
done

if [ $ERRORS -gt 0 ]; then
  echo ""
  echo "Found $ERRORS hardcoded hex value(s). Use CSS tokens from index.css instead."
  echo "If this is a data-visualization color, add comment: /* zodiac data-color, intentional */"
  exit 1
fi

exit 0
