#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
APPDIR="$BUILD_DIR/AppDir"
OUTPUT_APPIMAGE="$SCRIPT_DIR/Fallen-Lobo-Wireless-x86_64.AppImage"

rm -rf "$BUILD_DIR"
mkdir -p "$APPDIR/usr/share/fallen-lobo-driver"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$APPDIR/usr/share/applications"

# Copia código, regras e assets originais
cp "$SCRIPT_DIR/lobo_driver.py" "$APPDIR/usr/share/fallen-lobo-driver/"
cp "$SCRIPT_DIR/lobo_gui.py" "$APPDIR/usr/share/fallen-lobo-driver/"
cp "$SCRIPT_DIR/lobo-ctl" "$APPDIR/usr/share/fallen-lobo-driver/"
cp "$SCRIPT_DIR/70-fallen-lobo-wireless.rules" "$APPDIR/usr/share/fallen-lobo-driver/"
cp "$SCRIPT_DIR/install.sh" "$APPDIR/usr/share/fallen-lobo-driver/"
cp "$SCRIPT_DIR/LICENSE" "$APPDIR/usr/share/fallen-lobo-driver/"
cp "$SCRIPT_DIR/COPYRIGHT" "$APPDIR/usr/share/fallen-lobo-driver/"
cp -r "$SCRIPT_DIR/assets" "$APPDIR/usr/share/fallen-lobo-driver/"

# Ícone oficial 256x256 e .desktop do AppImage
cp "$SCRIPT_DIR/assets/app_icon.png" "$APPDIR/fallen-lobo-wireless.png"
cp "$SCRIPT_DIR/assets/app_icon.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/fallen-lobo-wireless.png"
ln -sf "fallen-lobo-wireless.png" "$APPDIR/.DirIcon"

cat > "$APPDIR/fallen-lobo-wireless.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=Fallen Lobo Wireless
GenericName=Mouse Configuration Software
Comment=Software de configuração e driver para o Mouse Gamer Fallen Lobo Wireless
Icon=fallen-lobo-wireless
Exec=AppRun
Terminal=false
Categories=Utility;Settings;HardwareSettings;
StartupWMClass=fallen-lobo-wireless
X-AppImage-Version=1.0.1.3
X-AppImage-Name=Fallen Lobo Wireless
EOF
cp "$APPDIR/fallen-lobo-wireless.desktop" "$APPDIR/usr/share/applications/"

cat > "$APPDIR/AppRun" << 'EOF'
#!/usr/bin/env bash
set -e
HERE="$(dirname "$(readlink -f "${0}")")"
APP_SHARE="$HERE/usr/share/fallen-lobo-driver"
export PYTHONPATH="$APP_SHARE:${PYTHONPATH:-}"

if [[ "${1:-}" == "--cli" ]]; then
    shift
    exec -a fallen-lobo-ctl /usr/bin/python3 "$APP_SHARE/lobo-ctl" "$@"
elif [[ "${1:-}" == "--install-udev" ]]; then
    exec "$APP_SHARE/install.sh"
else
    exec -a fallen-lobo-wireless /usr/bin/python3 "$APP_SHARE/lobo_gui.py" "$@"
fi
EOF
chmod +x "$APPDIR/AppRun" "$APPDIR/usr/share/fallen-lobo-driver/lobo_gui.py" "$APPDIR/usr/share/fallen-lobo-driver/lobo-ctl"

# Obtém o runtime AppImage Type-2 padrão (x86_64) e empacota SquashFS
RUNTIME_BIN="$BUILD_DIR/runtime-x86_64"
SQUASHFS_IMG="$BUILD_DIR/payload.squashfs"

if [[ -n "${APPIMAGE_RUNTIME:-}" && -f "$APPIMAGE_RUNTIME" ]]; then
    cp "$APPIMAGE_RUNTIME" "$RUNTIME_BIN"
elif [[ -f "$SCRIPT_DIR/runtime-x86_64" ]]; then
    cp "$SCRIPT_DIR/runtime-x86_64" "$RUNTIME_BIN"
elif [[ -f "$HOME/AppImages/openrgb.appimage" ]]; then
    head -c 193728 "$HOME/AppImages/openrgb.appimage" > "$RUNTIME_BIN"
elif command -v curl >/dev/null 2>&1; then
    curl -fsSL "https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64" -o "$RUNTIME_BIN"
elif command -v wget >/dev/null 2>&1; then
    wget -qO "$RUNTIME_BIN" "https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64"
else
    echo "Erro: runtime-x86_64 não encontrado e curl/wget indisponíveis." >&2
    echo "Defina APPIMAGE_RUNTIME=/caminho/para/runtime-x86_64 e tente novamente." >&2
    exit 1
fi
mksquashfs "$APPDIR" "$SQUASHFS_IMG" -root-owned -noappend -comp gzip >/dev/null

rm -f "$OUTPUT_APPIMAGE"
cat "$RUNTIME_BIN" "$SQUASHFS_IMG" > "$OUTPUT_APPIMAGE"
chmod +x "$OUTPUT_APPIMAGE"
rm -rf "$BUILD_DIR"

echo "AppImage gerado com sucesso: $OUTPUT_APPIMAGE"
