#!/bin/bash
# Pre-commit hook: block new hardcoded hex in *.jsx
# Exceptions:
#   - #fff / #ffffff (white text on colored elements)
#   - a line containing "data-color" (per-line opt-out)
#   - a file whose FIRST 3 lines contain "data-color" (file-level opt-out,
#     e.g. NebulaBackground WebGL shader, LandingPage fixed-light design)

ERRORS=0

for file in $(git diff --cached --name-only --diff-filter=ACM | grep '\.jsx$'); do
  [[ "$file" != frontend/src/* ]] && continue

  # File-level opt-out: marker in first 3 lines
  if head -3 "$file" 2>/dev/null | grep -q "data-color"; then
    continue
  fi

  # Walk added lines; check each line individually
  while IFS= read -r line; do
    [[ "$line" == +++* ]] && continue
    [[ "$line" != +* ]] && continue
    echo "$line" | grep -q "data-color" && continue

    for hex in $(echo "$line" | grep -oE '#[0-9A-Fa-f]{3,8}'); do
      hl=$(echo "$hex" | tr '[:upper:]' '[:lower:]')
      [[ "$hl" == "#fff" || "$hl" == "#ffffff" ]] && continue
      echo "ERROR: Hardcoded hex $hex in $file"
      ERRORS=$((ERRORS + 1))
    done
  done < <(git diff --cached -U0 "$file")
done

if [ $ERRORS -gt 0 ]; then
  echo ""
  echo "Found $ERRORS hardcoded hex value(s). Use CSS tokens from index.css (var(--*))."
  echo "Data-viz color? Add /* zodiac data-color, intentional */ on the line,"
  echo "or put the marker in the file's first 3 lines for a whole-file exception."
  exit 1
fi

exit 0
