#!/usr/bin/env bash
# Fresh-box installer for 脆脆的AI早咖啡 (Debian/Ubuntu). Idempotent: safe to re-run.
#   git clone https://github.com/YUECHENCUI/crispy-ai-coffee.git && cd crispy-ai-coffee && ./setup.sh
set -euo pipefail
cd "$(dirname "$0")"
SUDO=""; [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null && SUDO="sudo"

echo "▶ apt packages (ffmpeg, CJK fonts, curl, fontconfig, python venv)"
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq ffmpeg fonts-noto-cjk fonts-noto-cjk-extra fontconfig curl python3-venv python3-pip >/dev/null

echo "▶ Latin fonts (SIL OFL, from github.com/google/fonts) -> ~/.local/share/fonts/crispy"
FD="$HOME/.local/share/fonts/crispy"; mkdir -p "$FD"
G="https://github.com/google/fonts/raw/main/ofl"
for f in "intertight/InterTight%5Bwght%5D.ttf" "jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf" \
         "instrumentserif/InstrumentSerif-Regular.ttf" "instrumentserif/InstrumentSerif-Italic.ttf"; do
  out="$FD/$(basename "$f" | sed 's/%5B/[/; s/%5D/]/')"
  [ -s "$out" ] || curl -fsSL -o "$out" "$G/$f"
done
fc-cache -f >/dev/null

echo "▶ Python venv + packages"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python -m playwright install --with-deps chromium >/dev/null

echo "▶ Theme music (deterministic re-synthesis if the WAVs are missing)"
[ -s assets/music/bed_loop.wav ] || .venv/bin/python assets/music/compose.py

echo "▶ Self-check"
for fam in "Noto Sans CJK SC" "Noto Serif CJK SC" "Inter Tight" "JetBrains Mono" "Instrument Serif"; do
  got=$(fc-match -f '%{family}' "$fam"); case "$got" in *"$fam"*) echo "  font ok: $fam";; *) echo "  ✗ font missing: $fam (got $got)"; exit 1;; esac
done
.venv/bin/python -c "import edge_tts, playwright, numpy, scipy, jsonschema; print('  python deps ok')"
ffmpeg -version | head -1
echo "✅ setup done. Daily: .venv/bin/python run.py --init --date YYYY-MM-DD, fill brief.json, then .venv/bin/python run.py --date YYYY-MM-DD"
