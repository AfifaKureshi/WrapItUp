#!/usr/bin/env bash
set -euo pipefail

# Creates platform runner files while preserving the PackWise Dart source.
flutter create --project-name packwise --org com.packwise .
flutter pub get
