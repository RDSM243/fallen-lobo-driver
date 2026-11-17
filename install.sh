#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "1. Instalando regra udev para Fallen Lobo Wireless (3554:F53C / 3554:F511)..."
sudo cp "$SCRIPT_DIR/70-fallen-lobo-wireless.rules" /etc/udev/rules.d/70-fallen-lobo-wireless.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw
sudo chmod 0666 /dev/hidraw* 2>/dev/null || true

echo "2. Instalando AppImage em ~/AppImages/fallen_lobo_wireless.appimage e ícone no sistema..."
APPIMAGE_SRC="$SCRIPT_DIR/Fallen-Lobo-Wireless-x86_64.AppImage"
if [[ ! -f "$APPIMAGE_SRC" ]]; then
    echo "Erro: '$APPIMAGE_SRC' não encontrado." >&2
    echo "Baixe o AppImage na página de Releases do GitHub ou gere com ./build_appimage.sh" >&2
    exit 1
fi

mkdir -p "$HOME/AppImages/.icons" \
         "$HOME/.local/share/applications" \
         "$HOME/.local/share/icons/hicolor/256x256/apps" \
         "$HOME/.local/share/pixmaps" \
         "$HOME/.icons" \
         "$HOME/.local/bin"

cp "$APPIMAGE_SRC" "$HOME/AppImages/fallen_lobo_wireless.appimage"
chmod +x "$HOME/AppImages/fallen_lobo_wireless.appimage"

cp "$SCRIPT_DIR/assets/app_icon.png" "$HOME/AppImages/.icons/fallen_lobo_wireless"
cp "$SCRIPT_DIR/assets/app_icon.png" "$HOME/.local/share/icons/hicolor/256x256/apps/fallen-lobo-wireless.png"
cp "$SCRIPT_DIR/assets/app_icon.png" "$HOME/.local/share/pixmaps/fallen-lobo-wireless.png"
cp "$SCRIPT_DIR/assets/app_icon.png" "$HOME/.icons/fallen-lobo-wireless.png"

cat > "$HOME/.local/share/applications/fallen-lobo-wireless.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Fallen Lobo Wireless
Comment=Software de configuração e driver para o Mouse Gamer Fallen Lobo Wireless
Icon=fallen-lobo-wireless
TryExec=$HOME/AppImages/fallen_lobo_wireless.appimage
Exec=env DESKTOPINTEGRATION=1 $HOME/AppImages/fallen_lobo_wireless.appimage
Terminal=false
Categories=Utility;Settings;HardwareSettings;
StartupNotify=true
StartupWMClass=fallen-lobo-wireless
X-AppImage-Version=1.0.1.3
X-AppImage-Name=Fallen Lobo Wireless
EOF

ln -sf "$SCRIPT_DIR/lobo-ctl" "$HOME/.local/bin/lobo-ctl"

echo "Pronto! Você já pode abrir 'Fallen Lobo Wireless' pelo menu de aplicativos ou rodando:"
echo "  ~/AppImages/fallen_lobo_wireless.appimage"
