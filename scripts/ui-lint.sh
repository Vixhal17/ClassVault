#!/usr/bin/env bash
set -euo pipefail

echo "Running UI Design System Linter..."

TARGET_DIR="frontend"
FAIL=0

# Check for banned Tailwind classes
BANNED_CLASSES=(
  "gradient"
  "backdrop-blur"
  "shadow-lg"
  "shadow-xl"
  "shadow-2xl"
  "rounded-xl"
  "rounded-2xl"
  "rounded-3xl"
  "animate-bounce"
  "animate-ping"
  "animate-pulse"
)

for pattern in "${BANNED_CLASSES[@]}"; do
  matches=$(grep -rn "$pattern" "$TARGET_DIR/app" "$TARGET_DIR/components" 2>/dev/null || true)
  if [ -n "$matches" ]; then
    echo "ERROR: Banned design pattern '$pattern' found:"
    echo "$matches"
    FAIL=1
  fi
done

# Check for raw hex colors outside globals.css
hex_matches=$(grep -rnE "#[0-9a-fA-F]{3,6}" "$TARGET_DIR/app" "$TARGET_DIR/components" 2>/dev/null | grep -v "globals.css" | grep -v "styleguide" || true)
if [ -n "$hex_matches" ]; then
  echo "ERROR: Hex colors found outside globals.css:"
  echo "$hex_matches"
  FAIL=1
fi

# Check for emojis
emoji_matches=$(grep -rnP '[\x{1F600}-\x{1F64F}\x{1F300}-\x{1F5FF}\x{1F680}-\x{1F6FF}\x{2600}-\x{26FF}\x{2700}-\x{27BF}]' "$TARGET_DIR/app" "$TARGET_DIR/components" 2>/dev/null || true)
if [ -n "$emoji_matches" ]; then
  echo "ERROR: Emoji characters found in UI source:"
  echo "$emoji_matches"
  FAIL=1
fi

if [ $FAIL -ne 0 ]; then
  echo "UI Lint Failed: UI violates section 11 design system constraints."
  exit 1
fi

echo "UI Lint Passed cleanly. Zero forbidden design elements found."
