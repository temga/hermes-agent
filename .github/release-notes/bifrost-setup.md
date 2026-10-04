## Hermes Setup — Bifrost Edition (Tauri installer, ~5MB)

Lightweight Tauri installer that downloads and installs Hermes Agent + Bifrost Gateway plugins on first launch.
One key (sk-bf-*) powers LLM, image gen, web search, STT & TTS.

### macOS
1. Download `Hermes-Setup-Bifrost.dmg`
2. Open, drag Hermes to Applications
3. Launch — installer will download Hermes Agent + Bifrost plugins automatically
4. On first launch of the desktop app, enter your Bifrost key (sk-bf-*)
5. No Gatekeeper warnings — signed with Developer ID + notarized by Apple

### Windows
1. Download `Hermes-Setup-Bifrost.exe`
2. Run — SmartScreen may warn (unsigned installer); click "More info" → "Run anyway"
3. Installer will download Hermes Agent + Bifrost plugins automatically
4. On first launch of the desktop app, enter your Bifrost key (sk-bf-*)

### What it does
- macOS: downloads `install.sh` from `temga/hermes-agent`
- Windows: runs `install.ps1` (bundled in the installer)
- Installs the `main` branch of `temga/hermes-agent`, pinned to this release's commit
- Stages: prerequisites → repository → venv → python-deps → config → products → **bifrost-plugins** → setup → gateway → complete
- `products` stage: builds the `hermes` command, TUI/web and the desktop app
- `bifrost-plugins` stage: routes all service providers → the Bifrost plugins bundled in the tree (`plugins/<category>/bifrost/`)
