#!/usr/bin/env bash
set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

ok()   { echo -e "${GREEN}✔ $*${RESET}"; }
warn() { echo -e "${YELLOW}⚠ $*${RESET}"; }
err()  { echo -e "${RED}✖ $*${RESET}"; }
info() { echo -e "${CYAN}▸ $*${RESET}"; }
hdr()  { echo -e "\n${BOLD}$*${RESET}"; }

# ── Defaults ───────────────────────────────────────────────────────────────────
SKIP_IOS=false
SKIP_GUI=false
RUN_CLI=false
BUILD_ONLY=false
IOS_DEVICE="iPhone 17 Pro"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC_CLIENT_DIR="$SCRIPT_DIR/clients/sync-client"
IOS_DIR="$SCRIPT_DIR/clients/ios/MusicPorter"
IOS_BUILD_DIR="/tmp/musicporter-ios-build"
IOS_BUNDLE_ID="com.musicporter.ios"
IOS_SCHEME="MusicPorter"

# ── Usage ──────────────────────────────────────────────────────────────────────
usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Build and run Music Porter client applications.

Options:
  --skip-ios              Skip iOS build and simulator launch
  --skip-gui              Skip Electron GUI build and launch
  --run-cli               Include Sync CLI build (opt-in; no persistent run)
  --build-only            Build everything selected, don't run or launch
  --ios-device <name>     iOS Simulator device name (default: "${IOS_DEVICE}")
  --help                  Show this help

Defaults:
  iOS          build + launch (skipped gracefully if xcodebuild is unavailable)
  Electron GUI build + launch
  Sync CLI     skipped (use --run-cli to include)
EOF
}

# ── Argument parsing ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-ios)   SKIP_IOS=true ;;
    --skip-gui)   SKIP_GUI=true ;;
    --run-cli)    RUN_CLI=true ;;
    --build-only) BUILD_ONLY=true ;;
    --ios-device)
      if [[ -z "${2:-}" ]]; then
        err "--ios-device requires a device name argument"
        exit 1
      fi
      IOS_DEVICE="$2"
      shift
      ;;
    --help|-h) usage; exit 0 ;;
    *)
      err "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
  shift
done

# ── Header ─────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}Music Porter — Client Build & Run${RESET}"
echo "────────────────────────────────────"
echo "  iOS sim:     $([ "$SKIP_IOS" = true ] && echo "skipped" || echo "build + $([ "$BUILD_ONLY" = true ] && echo 'build only' || echo "launch  [device: ${IOS_DEVICE}]")")"
echo "  Electron GUI: $([ "$SKIP_GUI" = true ] && echo "skipped" || echo "build + $([ "$BUILD_ONLY" = true ] && echo 'build only' || echo 'launch')")"
echo "  Sync CLI:    $([ "$RUN_CLI" = true ] && echo "build only" || echo "skipped (use --run-cli)")"
echo ""

# ── Track overall status ───────────────────────────────────────────────────────
IOS_STATUS="skipped"
CLI_STATUS="skipped"
GUI_STATUS="skipped"

# ══════════════════════════════════════════════════════════════════════════════
# iOS Build + Launch
# ══════════════════════════════════════════════════════════════════════════════
if [ "$SKIP_IOS" = false ]; then
  hdr "[iOS] Building for simulator: ${IOS_DEVICE}"
  (
    if ! command -v xcodebuild &>/dev/null; then
      warn "xcodebuild not found — skipping iOS (install Xcode to enable)"
      exit 0
    fi

    if [ ! -d "$IOS_DIR" ]; then
      err "iOS project not found at: $IOS_DIR"
      exit 1
    fi

    cd "$IOS_DIR"

    info "Running xcodebuild..."
    if xcodebuild \
        -project MusicPorter.xcodeproj \
        -scheme "$IOS_SCHEME" \
        -destination "platform=iOS Simulator,name=${IOS_DEVICE}" \
        -configuration Debug \
        -derivedDataPath "$IOS_BUILD_DIR" \
        build \
        2>&1 | grep -E '(error:|warning:|BUILD SUCCEEDED|BUILD FAILED|PhaseScriptExecution|CompileSwift)' | tail -30; then
      ok "iOS build succeeded"
    else
      err "iOS build failed"
      exit 1
    fi

    if [ "$BUILD_ONLY" = false ]; then
      APP_PATH=$(find "$IOS_BUILD_DIR" -name "MusicPorter.app" -maxdepth 6 2>/dev/null | head -1)
      if [ -z "$APP_PATH" ]; then
        err "Could not find MusicPorter.app in build output"
        exit 1
      fi

      info "Booting simulator: ${IOS_DEVICE}"
      xcrun simctl boot "${IOS_DEVICE}" 2>/dev/null || true

      info "Installing app..."
      xcrun simctl install booted "$APP_PATH"

      info "Launching app (bundle: ${IOS_BUNDLE_ID})..."
      xcrun simctl launch booted "$IOS_BUNDLE_ID"

      open -a Simulator
      ok "iOS app launched in simulator"
    fi
  ) && IOS_STATUS="ok" || IOS_STATUS="failed"
fi

# ══════════════════════════════════════════════════════════════════════════════
# Sync CLI Build
# ══════════════════════════════════════════════════════════════════════════════
if [ "$RUN_CLI" = true ]; then
  hdr "[Sync CLI] Building..."
  (
    if ! command -v node &>/dev/null || ! command -v npm &>/dev/null; then
      err "node/npm not found — cannot build Sync CLI"
      exit 1
    fi

    cd "$SYNC_CLIENT_DIR"

    if [ ! -d "node_modules" ]; then
      info "Installing npm dependencies..."
      npm install
    fi

    info "Building core + CLI packages..."
    npm run build --workspace=packages/core --workspace=packages/cli

    ok "Sync CLI built"
    info "Run via: ./clients/sync-client/run-cli.sh <args>"
  ) && CLI_STATUS="ok" || CLI_STATUS="failed"
fi

# ══════════════════════════════════════════════════════════════════════════════
# Electron GUI Build + Launch
# ══════════════════════════════════════════════════════════════════════════════
if [ "$SKIP_GUI" = false ]; then
  hdr "[Electron GUI] Building..."
  (
    if ! command -v node &>/dev/null || ! command -v npm &>/dev/null; then
      err "node/npm not found — cannot build Electron GUI"
      exit 1
    fi

    cd "$SYNC_CLIENT_DIR"

    if [ ! -d "node_modules" ]; then
      info "Installing npm dependencies..."
      npm install
    fi

    info "Building core + GUI packages..."
    npm run build --workspace=packages/core --workspace=packages/gui

    ok "Electron GUI built"

    if [ "$BUILD_ONLY" = false ]; then
      info "Launching Electron GUI (detached)..."
      cd packages/gui
      nohup npm start </dev/null >/tmp/musicporter-gui.log 2>&1 &
      disown
      ok "Electron GUI launched (log: /tmp/musicporter-gui.log)"
    fi
  ) && GUI_STATUS="ok" || GUI_STATUS="failed"
fi

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo "────────────────────────────────────"
echo -e "${BOLD}Summary${RESET}"

_status_line() {
  local label="$1" status="$2"
  case "$status" in
    ok)      echo -e "  ${label}: ${GREEN}done${RESET}" ;;
    failed)  echo -e "  ${label}: ${RED}failed${RESET}" ;;
    skipped) echo -e "  ${label}: ${YELLOW}skipped${RESET}" ;;
  esac
}

_status_line "iOS          " "$IOS_STATUS"
_status_line "Sync CLI     " "$CLI_STATUS"
_status_line "Electron GUI " "$GUI_STATUS"
echo ""

# Exit with failure if any enabled step failed
if [ "$IOS_STATUS" = "failed" ] || [ "$CLI_STATUS" = "failed" ] || [ "$GUI_STATUS" = "failed" ]; then
  exit 1
fi
