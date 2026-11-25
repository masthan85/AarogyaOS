#!/usr/bin/env bash
# Runs each Maestro flow on its own and, when one fails, prints what was on screen at that moment,
# so a failure can be read from the CI log. Used by the android-maestro job in CI.
set -u
failed=0
for flow in .maestro/*.yaml; do
  [ "$(basename "$flow")" = "config.yaml" ] && continue
  if ! maestro test "$flow"; then
    failed=1
    echo "Screen when $(basename "$flow") failed:"
    adb shell uiautomator dump /sdcard/ui.xml >/dev/null
    adb shell cat /sdcard/ui.xml | grep -o 'text="[^"]*"\|content-desc="[^"]*"\|resource-id="[^"]*"' | grep -v '=""'
  fi
done
exit "$failed"
