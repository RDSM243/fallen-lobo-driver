#!/usr/bin/env python3
"""Interface Gráfica (PyQt6) idêntica ao software Windows para o Mouse Fallen Lobo Wireless."""

from __future__ import annotations

import math
import os
import subprocess
import sys
import time
from typing import Callable, Optional

from PyQt6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QKeyEvent,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lobo_driver import (
    HID_KEYCODES,
    MULTIMEDIA_ACTIONS,
    PERFORMANCE_TIME_OPTIONS,
    SLEEP_TIME_OPTIONS,
    ButtonMapping,
    DeviceInfo,
    DpiStage,
    LoboDriverError,
    LoboMouse,
    MacroDefinition,
    MacroStep,
    MouseConfig,
    ProfileStore,
    describe_button_mapping,
    encode_dpi_3395,
    encode_multimedia_buffer,
    encode_shortcut_buffer,
    find_devices,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_ICON_PATH = os.path.join(BASE_DIR, "assets", "app_icon.png")
MOUSE_RENDER_PATH = os.path.join(BASE_DIR, "assets", "mouse_render.png")
APP_ID = "fallen-lobo-wireless"


def ensure_desktop_integration() -> None:
    """Garante que o ícone e o .desktop estejam registrados no Linux atual (mesmo rodando só o AppImage)."""
    if not os.path.exists(APP_ICON_PATH):
        return
    try:
        home = os.path.expanduser("~")
        icon_dirs = [
            os.path.join(home, ".local", "share", "icons", "hicolor", "256x256", "apps"),
            os.path.join(home, ".local", "share", "icons", "hicolor", "128x128", "apps"),
            os.path.join(home, ".local", "share", "pixmaps"),
            os.path.join(home, ".icons"),
        ]
        with open(APP_ICON_PATH, "rb") as src_f:
            icon_bytes = src_f.read()

        for d in icon_dirs:
            os.makedirs(d, exist_ok=True)
            dst = os.path.join(d, f"{APP_ID}.png")
            if not os.path.exists(dst) or os.path.getsize(dst) != len(icon_bytes):
                with open(dst, "wb") as out_f:
                    out_f.write(icon_bytes)

        app_dir = os.path.join(home, ".local", "share", "applications")
        os.makedirs(app_dir, exist_ok=True)
        desktop_path = os.path.join(app_dir, f"{APP_ID}.desktop")
        exec_target = os.environ.get("APPIMAGE") or os.path.abspath(__file__)
        icon_target = os.path.join(
            home, ".local", "share", "icons", "hicolor", "256x256", "apps", f"{APP_ID}.png"
        )
        desktop_content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Fallen Lobo Wireless\n"
            "Comment=Software de configuração e driver para o Mouse Gamer Fallen Lobo Wireless\n"
            f"Icon={icon_target}\n"
            f"TryExec={exec_target}\n"
            f"Exec=env DESKTOPINTEGRATION=1 {exec_target}\n"
            "Terminal=false\n"
            "Categories=Utility;Settings;HardwareSettings;\n"
            "StartupNotify=true\n"
            f"StartupWMClass={APP_ID}\n"
            "X-AppImage-Name=Fallen Lobo Wireless\n"
        )
        with open(desktop_path, "w", encoding="utf-8") as df:
            df.write(desktop_content)
    except OSError:
        pass

# Paleta de 14 cores rápidas do software original
PRESET_COLORS = [
    (255, 0, 0),
    (255, 128, 0),
    (255, 224, 0),
    (128, 255, 0),
    (0, 255, 0),
    (0, 255, 128),
    (0, 255, 255),
    (0, 128, 255),
    (0, 0, 255),
    (128, 0, 255),
    (255, 0, 255),
    (255, 0, 128),
    (255, 255, 255),
    (170, 255, 255),
]

QT_KEY_TO_HID_NAME: dict[int, str] = {
    Qt.Key.Key_Return: "Enter",
    Qt.Key.Key_Enter: "Enter",
    Qt.Key.Key_Escape: "Esc",
    Qt.Key.Key_Backspace: "Backspace",
    Qt.Key.Key_Tab: "Tab",
    Qt.Key.Key_Space: "Space",
    Qt.Key.Key_Minus: "-",
    Qt.Key.Key_Equal: "=",
    Qt.Key.Key_BracketLeft: "[",
    Qt.Key.Key_BracketRight: "]",
    Qt.Key.Key_Backslash: "\\",
    Qt.Key.Key_Semicolon: ";",
    Qt.Key.Key_Apostrophe: "'",
    Qt.Key.Key_QuoteLeft: "`",
    Qt.Key.Key_Comma: ",",
    Qt.Key.Key_Period: ".",
    Qt.Key.Key_Slash: "/",
    Qt.Key.Key_CapsLock: "CapsLock",
    Qt.Key.Key_Insert: "Insert",
    Qt.Key.Key_Home: "Home",
    Qt.Key.Key_PageUp: "PageUp",
    Qt.Key.Key_Delete: "Delete",
    Qt.Key.Key_End: "End",
    Qt.Key.Key_PageDown: "PageDown",
    Qt.Key.Key_Right: "Right",
    Qt.Key.Key_Left: "Left",
    Qt.Key.Key_Down: "Down",
    Qt.Key.Key_Up: "Up",
    Qt.Key.Key_Control: "Ctrl",
    Qt.Key.Key_Shift: "Shift",
    Qt.Key.Key_Alt: "Alt",
    Qt.Key.Key_Meta: "Win",
}
for _i in range(1, 13):
    QT_KEY_TO_HID_NAME[getattr(Qt.Key, f"Key_F{_i}")] = f"F{_i}"
for _ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
    QT_KEY_TO_HID_NAME[getattr(Qt.Key, f"Key_{_ch}")] = _ch


def make_nav_icon(kind: str, active: bool) -> QIcon:
    """Desenha ícones vetoriais próprios para a barra lateral."""
    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    col = QColor("#ffe000") if active else QColor("#d0d5e0")
    pen = QPen(col, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)

    if kind == "buttons":
        p.drawRoundedRect(QRectF(8, 4, 16, 24), 8, 8)
        p.drawLine(8, 14, 24, 14)
        p.drawLine(16, 4, 16, 14)
    elif kind == "sensor":
        p.drawEllipse(QRectF(6, 6, 20, 20))
        p.drawEllipse(QRectF(13, 13, 6, 6))
        p.drawLine(16, 2, 16, 8)
        p.drawLine(16, 24, 16, 30)
        p.drawLine(2, 16, 8, 16)
        p.drawLine(24, 16, 30, 16)
    elif kind == "macro":
        p.drawEllipse(QRectF(4, 4, 24, 24))
        f = p.font()
        f.setBold(True)
        f.setPixelSize(14)
        p.setFont(f)
        p.drawText(QRect(4, 4, 24, 24), Qt.AlignmentFlag.AlignCenter, "M")
    elif kind == "light":
        p.drawEllipse(QRectF(10, 10, 12, 12))
        for deg in range(0, 360, 45):
            rad = math.radians(deg)
            p.drawLine(
                QPoint(round(16 + 9 * math.cos(rad)), round(16 + 9 * math.sin(rad))),
                QPoint(round(16 + 13 * math.cos(rad)), round(16 + 13 * math.sin(rad))),
            )
    elif kind == "settings":
        p.drawEllipse(QRectF(11, 11, 10, 10))
        p.drawEllipse(QRectF(6, 6, 20, 20))
        for deg in range(0, 360, 45):
            rad = math.radians(deg)
            p.drawLine(
                QPoint(round(16 + 10 * math.cos(rad)), round(16 + 10 * math.sin(rad))),
                QPoint(round(16 + 14 * math.cos(rad)), round(16 + 14 * math.sin(rad))),
            )
    p.end()
    return QIcon(pix)


GLOBAL_QSS = """
QMainWindow, QDialog {
    background-color: #0d0e11;
    color: #f0f0f0;
    font-family: "Sans Serif";
    font-size: 13px;
}
QToolTip {
    background-color: #1c2029;
    color: #f0f0f0;
    border: 1px solid #ffe000;
    padding: 4px 8px;
}
QWidget {
    color: #eaeaea;
}
QFrame#Card {
    background-color: #16181e;
    border: 1px solid #262934;
    border-radius: 8px;
}
QFrame#CardActive {
    background-color: #1c2029;
    border: 1px solid #ffe000;
    border-radius: 8px;
}
QPushButton {
    background-color: #21242d;
    border: 1px solid #323746;
    border-radius: 6px;
    padding: 6px 12px;
    color: #ffffff;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #2c313d;
    border-color: #ffe000;
}
QPushButton:pressed {
    background-color: #ffe000;
    color: #0d0e11;
}
QPushButton#AccentBtn {
    background-color: #ffe000;
    border: 1px solid #ffe000;
    color: #0d0e11;
    font-weight: 700;
}
QPushButton#AccentBtn:hover {
    background-color: #ffea4c;
}
QPushButton#RateBtn[active="true"] {
    background-color: #ffe000;
    border: 1px solid #ffe000;
    color: #0d0e11;
    font-weight: 700;
}
QPushButton#DangerBtn {
    background-color: #3a181c;
    border: 1px solid #6e2830;
    color: #ff9ea6;
}
QPushButton#DangerBtn:hover {
    background-color: #542027;
    border-color: #ff5566;
}
QPushButton#WinCtrlBtn {
    background-color: #1b1e26;
    border: 1px solid #2e3342;
    border-radius: 6px;
    padding: 0px;
    color: #dcdfe6;
    font-size: 14px;
    font-weight: 700;
}
QPushButton#WinCtrlBtn:hover {
    background-color: #2c3240;
    border-color: #ffe000;
    color: #ffe000;
}
QPushButton#WinCloseBtn {
    background-color: #1b1e26;
    border: 1px solid #2e3342;
    border-radius: 6px;
    padding: 0px;
    color: #dcdfe6;
    font-size: 14px;
    font-weight: 700;
}
QPushButton#WinCloseBtn:hover {
    background-color: #e81123;
    border-color: #ff4455;
    color: #ffffff;
}
QComboBox, QSpinBox {
    background-color: #21242d;
    border: 1px solid #353947;
    border-radius: 5px;
    padding: 4px 8px;
    color: #f0f0f0;
    min-height: 24px;
}
QComboBox:hover, QSpinBox:hover {
    border-color: #ffe000;
}
QComboBox QAbstractItemView {
    background-color: #1a1d24;
    color: #f0f0f0;
    selection-background-color: #ffe000;
    selection-color: #0d0e11;
    border: 1px solid #353947;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #2b2f3b;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: #ffe000;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #ffffff;
    border: 2px solid #ffe000;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 8px;
}
QListWidget {
    background-color: #13151a;
    border: 1px solid #282c37;
    border-radius: 6px;
    padding: 4px;
}
QListWidget::item {
    padding: 6px 8px;
    border-radius: 4px;
}
QListWidget::item:selected {
    background-color: #ffe000;
    color: #0d0e11;
    font-weight: 700;
}
QCheckBox {
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #454a5c;
    background: #1d2028;
}
QCheckBox::indicator:checked {
    background: #ffe000;
    border-color: #ffe000;
}
"""


class MouseDiagramWidget(QWidget):
    """Renderiza o modelo 3D próprio do mouse com os 6 pontos numerados interativos."""

    # Posições (x, y) sobre cada botão físico no render 3D e posição do badge numerado
    CALLOUTS = [
        (1, (195, 220), (54, 272)),   # 1: Clique Esquerdo (pá inferior / lado do polegar)
        (2, (134, 146), (48, 88)),    # 2: Clique Direito (pá superior)
        (3, (158, 174), (48, 184)),   # 3: Clique do Scroll (roda branca)
        (4, (306, 154), (372, 166)),  # 4: Recuar (botão lateral traseiro)
        (5, (264, 182), (366, 256)),  # 5: Avançar (botão lateral frontal)
        (6, (202, 114), (356, 76)),   # 6: Loop de DPI (botão central)
    ]

    def __init__(self, on_select_button: Callable[[int], None], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.on_select_button = on_select_button
        self.setFixedSize(420, 350)
        self.mouse_pix = QPixmap(MOUSE_RENDER_PATH)
        self.hovered_idx: int = -1
        self.selected_idx: int = 0
        self.setMouseTracking(True)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        if not self.mouse_pix.isNull():
            scaled = self.mouse_pix.scaled(
                320, 225, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            px = (self.width() - scaled.width()) // 2
            py = (self.height() - scaled.height()) // 2 + 10
            p.drawPixmap(px, py, scaled)

        for num, pt_mouse, pt_badge in self.CALLOUTS:
            idx = num - 1
            active = idx == self.selected_idx or idx == self.hovered_idx
            line_col = QColor("#ffe000") if active else QColor("#00d4ff")

            pen = QPen(line_col, 2 if active else 1.5)
            p.setPen(pen)
            p.drawLine(QPoint(*pt_mouse), QPoint(*pt_badge))

            # Ponto sobre o botão físico no mouse
            p.setBrush(line_col)
            p.drawEllipse(QPoint(*pt_mouse), 4, 4)

            # Círculo numerado
            bg_col = QColor("#ffe000") if active else QColor("#1e222b")
            fg_col = QColor("#0d0e11") if active else QColor("#ffffff")
            p.setBrush(bg_col)
            p.setPen(QPen(line_col, 2))
            p.drawEllipse(QPoint(*pt_badge), 15, 15)

            p.setPen(fg_col)
            f = p.font()
            f.setBold(True)
            f.setPointSize(10)
            p.setFont(f)
            rect = QRect(pt_badge[0] - 15, pt_badge[1] - 15, 30, 30)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(num))

    def mouseMoveEvent(self, event) -> None:
        pos = event.pos()
        hov = -1
        for num, _pm, pb in self.CALLOUTS:
            if (pos.x() - pb[0]) ** 2 + (pos.y() - pb[1]) ** 2 <= 18 ** 2:
                hov = num - 1
                break
        if hov != self.hovered_idx:
            self.hovered_idx = hov
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if hov >= 0 else Qt.CursorShape.ArrowCursor
            )
            self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.hovered_idx >= 0:
            self.selected_idx = self.hovered_idx
            self.update()
            self.on_select_button(self.hovered_idx)


class ButtonConfigDialog(QDialog):
    """Diálogo completo para atribuir função a um dos 6 botões do Fallen Lobo Wireless."""

    def __init__(
        self,
        button_index: int,
        current: ButtonMapping,
        macros: list[MacroDefinition],
        lang: str = "pt",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.button_index = button_index
        self.macros = macros
        self.lang = lang
        self.result_mapping: Optional[tuple[int, int, int, Optional[bytes], str]] = None

        pt = lang == "pt"
        self.setWindowTitle(
            f"{'Configurar Botão' if pt else 'Configure Button'} #{button_index + 1}"
        )
        self.setFixedSize(460, 380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        lbl_cat = QLabel("Categoria da Função:" if pt else "Function Category:")
        lbl_cat.setStyleSheet("font-weight: 700; color: #ffe000;")
        layout.addWidget(lbl_cat)

        self.combo_category = QComboBox()
        self.categories = [
            ("mouse", "Botões Padrão do Mouse" if pt else "Standard Mouse Buttons"),
            ("dpi", "Controle de DPI" if pt else "DPI Control"),
            ("fire", "Tecla de Disparo (Fire Key)" if pt else "Fire Key"),
            ("shortcut", "Combinação de Teclas (Atalho)" if pt else "Keyboard Shortcut"),
            ("multimedia", "Multimídia & Sistema" if pt else "Multimedia & System"),
            ("macro", "Macro" if pt else "Macro"),
            ("rate", "Troca da Taxa de Atualização" if pt else "Polling Rate Switch"),
            ("light", "Luz ON/OFF" if pt else "Light ON/OFF"),
            ("scroll", "Rolagem (Scroll)" if pt else "Scroll Up/Down"),
            ("disable", "Desabilitar Botão" if pt else "Disable Button"),
        ]
        for _k, text in self.categories:
            self.combo_category.addItem(text)
        layout.addWidget(self.combo_category)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        # 0: Mouse
        w_mouse = QWidget()
        l_mouse = QVBoxLayout(w_mouse)
        self.combo_mouse = QComboBox()
        self.mouse_opts = [
            (0x01, "Clique esquerdo" if pt else "Left Click"),
            (0x02, "Clique Direito" if pt else "Right Click"),
            (0x04, "Clique do Scroll" if pt else "Middle Click"),
            (0x10, "Avançar" if pt else "Forward"),
            (0x08, "Recuar" if pt else "Back"),
        ]
        for _code, txt in self.mouse_opts:
            self.combo_mouse.addItem(txt)
        l_mouse.addWidget(QLabel("Selecione o clique:" if pt else "Select click:"))
        l_mouse.addWidget(self.combo_mouse)
        l_mouse.addStretch()
        self.stack.addWidget(w_mouse)

        # 1: DPI
        w_dpi = QWidget()
        l_dpi = QVBoxLayout(w_dpi)
        self.combo_dpi = QComboBox()
        self.dpi_opts = [
            (0x02, 0x01, "Loop de DPI" if pt else "DPI Loop"),
            (0x02, 0x02, "DPI+"),
            (0x02, 0x03, "DPI-"),
            (0x0A, 0x00, "Trava de DPI (Sniper)" if pt else "DPI Lock (Sniper)"),
        ]
        for _t, _p, txt in self.dpi_opts:
            self.combo_dpi.addItem(txt)
        l_dpi.addWidget(QLabel("Modo de DPI:" if pt else "DPI action:"))
        l_dpi.addWidget(self.combo_dpi)
        self.spin_sniper_dpi = QSpinBox()
        self.spin_sniper_dpi.setRange(50, 26000)
        self.spin_sniper_dpi.setSingleStep(50)
        self.spin_sniper_dpi.setValue(400)
        l_dpi.addWidget(QLabel("Valor da Trava de DPI (50..26000):" if pt else "Sniper DPI:"))
        l_dpi.addWidget(self.spin_sniper_dpi)
        l_dpi.addStretch()
        self.stack.addWidget(w_dpi)

        # 2: Fire Key
        w_fire = QWidget()
        l_fire = QVBoxLayout(w_fire)
        l_fire.addWidget(QLabel("Intervalo entre disparos (10–255 ms):" if pt else "Interval (10–255 ms):"))
        self.spin_fire_interval = QSpinBox()
        self.spin_fire_interval.setRange(10, 255)
        self.spin_fire_interval.setValue(20)
        l_fire.addWidget(self.spin_fire_interval)
        l_fire.addWidget(QLabel("Repetições (0 = repetir enquanto segurar, 1–3):" if pt else "Repeats (0–3):"))
        self.spin_fire_count = QSpinBox()
        self.spin_fire_count.setRange(0, 3)
        self.spin_fire_count.setValue(3)
        l_fire.addWidget(self.spin_fire_count)
        l_fire.addStretch()
        self.stack.addWidget(w_fire)

        # 3: Shortcut
        w_sc = QWidget()
        l_sc = QVBoxLayout(w_sc)
        l_sc.addWidget(QLabel("Modificadores (máximo 2):" if pt else "Modifiers (max 2):"))
        mod_row = QHBoxLayout()
        self.chk_ctrl = QCheckBox("Ctrl")
        self.chk_shift = QCheckBox("Shift")
        self.chk_alt = QCheckBox("Alt")
        self.chk_win = QCheckBox("Win/Super")
        for c in (self.chk_ctrl, self.chk_shift, self.chk_alt, self.chk_win):
            mod_row.addWidget(c)
        l_sc.addLayout(mod_row)
        l_sc.addWidget(QLabel("Tecla Principal:" if pt else "Main Key:"))
        self.combo_sc_key = QComboBox()
        for k in HID_KEYCODES:
            if k not in ("Ctrl", "Shift", "Alt", "Win"):
                self.combo_sc_key.addItem(k)
        l_sc.addWidget(self.combo_sc_key)
        l_sc.addStretch()
        self.stack.addWidget(w_sc)

        # 4: Multimedia
        w_mm = QWidget()
        l_mm = QVBoxLayout(w_mm)
        l_mm.addWidget(QLabel("Ação Multimídia / Sistema:" if pt else "Multimedia / System Action:"))
        self.combo_mm = QComboBox()
        self.mm_keys = list(MULTIMEDIA_ACTIONS.keys())
        for mk in self.mm_keys:
            pt_lbl, en_lbl, _code = MULTIMEDIA_ACTIONS[mk]
            self.combo_mm.addItem(pt_lbl if pt else en_lbl)
        l_mm.addWidget(self.combo_mm)
        l_mm.addStretch()
        self.stack.addWidget(w_mm)

        # 5: Macro
        w_mac = QWidget()
        l_mac = QVBoxLayout(w_mac)
        l_mac.addWidget(QLabel("Selecione a Macro:" if pt else "Select Macro:"))
        self.combo_macro = QComboBox()
        for idx, m in enumerate(self.macros):
            self.combo_macro.addItem(f"[{idx + 1}] {m.name}")
        l_mac.addWidget(self.combo_macro)
        l_mac.addWidget(QLabel("Modo de Execução:" if pt else "Trigger Mode:"))
        self.combo_macro_mode = QComboBox()
        self.combo_macro_mode.addItem("Repetir número definido de vezes" if pt else "Repeat N times")
        self.combo_macro_mode.addItem("Repetir até soltar a tecla" if pt else "Repeat while held")
        self.combo_macro_mode.addItem("Repetir até clicar novamente" if pt else "Repeat until clicked again")
        l_mac.addWidget(self.combo_macro_mode)
        l_mac.addStretch()
        self.stack.addWidget(w_mac)

        # 6: Rate
        w_rate = QWidget()
        l_rate = QVBoxLayout(w_rate)
        l_rate.addWidget(QLabel("Alterna ciclicamente entre as taxas de atualização (Polling Rate)."))
        l_rate.addStretch()
        self.stack.addWidget(w_rate)

        # 7: Light
        w_light = QWidget()
        l_light = QVBoxLayout(w_light)
        l_light.addWidget(QLabel("Liga ou desliga a iluminação RGB do mouse."))
        l_light.addStretch()
        self.stack.addWidget(w_light)

        # 8: Scroll
        w_scroll = QWidget()
        l_scroll = QVBoxLayout(w_scroll)
        self.combo_scroll = QComboBox()
        self.combo_scroll.addItem("Rolar para cima" if pt else "Scroll Up")
        self.combo_scroll.addItem("Rolar para baixo" if pt else "Scroll Down")
        l_scroll.addWidget(self.combo_scroll)
        l_scroll.addStretch()
        self.stack.addWidget(w_scroll)

        # 9: Disable
        w_dis = QWidget()
        l_dis = QVBoxLayout(w_dis)
        l_dis.addWidget(QLabel("Desativa este botão (Nota: é obrigatório manter ao menos 1 Clique Esquerdo)."))
        l_dis.addStretch()
        self.stack.addWidget(w_dis)

        self.combo_category.currentIndexChanged.connect(self.stack.setCurrentIndex)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Cancelar" if pt else "Cancel")
        btn_ok = QPushButton("Confirmar" if pt else "Confirm")
        btn_ok.setObjectName("AccentBtn")
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._on_confirm)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _on_confirm(self) -> None:
        cat_key = self.categories[self.combo_category.currentIndex()][0]
        pt = self.lang == "pt"
        if cat_key == "mouse":
            code, lbl = self.mouse_opts[self.combo_mouse.currentIndex()]
            self.result_mapping = (0x01, code, 0x00, None, lbl)
        elif cat_key == "dpi":
            t, p1, lbl = self.dpi_opts[self.combo_dpi.currentIndex()]
            if t == 0x0A:
                dpi = (self.spin_sniper_dpi.value() // 50) * 50
                raw = (dpi // 50) - 1
                self.result_mapping = (0x0A, raw & 0xFF, (raw >> 8) & 0xFF, None, f"{lbl} ({dpi})")
            else:
                self.result_mapping = (t, p1, 0x00, None, lbl)
        elif cat_key == "fire":
            interval = self.spin_fire_interval.value()
            cnt = self.spin_fire_count.value()
            lbl = f"{'Tecla de disparo' if pt else 'Fire Key'} ({interval}ms x{cnt})"
            self.result_mapping = (0x04, interval, cnt, None, lbl)
        elif cat_key == "shortcut":
            mods = []
            if self.chk_ctrl.isChecked():
                mods.append("Ctrl")
            if self.chk_shift.isChecked():
                mods.append("Shift")
            if self.chk_alt.isChecked():
                mods.append("Alt")
            if self.chk_win.isChecked():
                mods.append("Win")
            mods = mods[:2]
            key = self.combo_sc_key.currentText()
            sc_buf = encode_shortcut_buffer(mods, key)
            combo_txt = "+".join(mods + [key])
            self.result_mapping = (0x05, 0x00, self.button_index, sc_buf, combo_txt)
        elif cat_key == "multimedia":
            mk = self.mm_keys[self.combo_mm.currentIndex()]
            pt_lbl, en_lbl, code = MULTIMEDIA_ACTIONS[mk]
            mm_buf = encode_multimedia_buffer(code)
            self.result_mapping = (0x05, 0x00, self.button_index, mm_buf, pt_lbl if pt else en_lbl)
        elif cat_key == "macro":
            if not self.macros:
                QMessageBox.warning(
                    self,
                    "Aviso",
                    "Por favor, primeiro crie uma nova Macro na aba Macros."
                    if pt
                    else "Please create a Macro first.",
                )
                return
            m_idx = self.combo_macro.currentIndex()
            mode_idx = self.combo_macro_mode.currentIndex()
            rep_byte = 0x01 if mode_idx == 0 else (0xFE if mode_idx == 1 else 0xFF)
            lbl = f"Macro-{self.macros[m_idx].name}"
            self.result_mapping = (0x06, m_idx, rep_byte, None, lbl)
        elif cat_key == "rate":
            self.result_mapping = (
                0x07,
                0x01,
                0x00,
                None,
                "Troca da Taxa de Atualização" if pt else "Polling Rate Switch",
            )
        elif cat_key == "light":
            self.result_mapping = (0x08, 0x01, 0x00, None, "Luz ON/OFF" if pt else "Light ON/OFF")
        elif cat_key == "scroll":
            idx = self.combo_scroll.currentIndex()
            self.result_mapping = (
                0x03,
                0x01 if idx == 0 else 0x02,
                0x00,
                None,
                self.combo_scroll.currentText(),
            )
        elif cat_key == "disable":
            self.result_mapping = (0x00, 0x00, 0x00, None, "Desabilitar" if pt else "Disable")

        self.accept()


class FallenLoboMainWindow(QMainWindow):
    """Janela principal do software Fallen Lobo Wireless para Linux."""

    def __init__(self) -> None:
        super().__init__()
        self.store = ProfileStore()
        self.cfg: MouseConfig = self.store.profiles[self.store.active_profile]
        self.device_info: Optional[DeviceInfo] = None
        self.online: bool = False
        self.dongle_fw: str = "--"
        self.mouse_fw: str = "--"
        self.battery_percent: int = 100
        self.battery_mv: int = 0
        self.battery_charging: bool = False
        self.selected_dpi_stage: int = self.cfg.active_dpi_stage
        self.recording_macro: bool = False
        self.last_record_ts: float = 0.0

        self.setWindowTitle("Fallen Lobo Wireless — Linux Driver")
        self.setMinimumSize(1020, 700)
        self.resize(1020, 700)
        self.brand_pix = QPixmap(APP_ICON_PATH)
        if not self.brand_pix.isNull():
            self.setWindowIcon(QIcon(self.brand_pix))

        self._build_ui()
        self.refresh_device_status(sync_from_hw=True)

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(lambda: self.refresh_device_status(sync_from_hw=False))
        self.poll_timer.start(4000)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Fundo escuro principal
        p.fillRect(self.rect(), QColor("#07080b"))

        # Barra lateral esquerda própria
        sb_rect = QRectF(8, 8, 102, self.height() - 16)
        sb_path = QPainterPath()
        sb_path.addRoundedRect(sb_rect, 10, 10)
        p.fillPath(sb_path, QColor("#2b303a"))
        p.setPen(QPen(QColor("#3a404e"), 1))
        p.drawPath(sb_path)

        # Emblema do app no topo da barra lateral
        if not self.brand_pix.isNull():
            p.drawPixmap(QRect(27, 26, 64, 64), self.brand_pix)
        p.setPen(QPen(QColor("#1a1d24"), 2))
        p.drawLine(22, 114, 96, 114)

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
            self.btn_win_max.setText("□")
        else:
            self.showMaximized()
            self.btn_win_max.setText("❐")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 56:
            wh = self.windowHandle()
            if wh is not None:
                wh.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 56:
            self._toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    # ------------------------------------------------------------------
    # Construção da Interface
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)
        main_h = QHBoxLayout(root)
        main_h.setContentsMargins(0, 0, 0, 0)
        main_h.setSpacing(0)

        # Barra lateral esquerda
        sidebar = QWidget()
        sidebar.setFixedWidth(112)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(14, 132, 14, 24)
        sb_layout.setSpacing(12)

        self.nav_buttons: list[QToolButton] = []
        nav_specs = [
            ("buttons", "Botões"),
            ("sensor", "Sensor"),
            ("macro", "Macros"),
            ("light", "Luzes"),
            ("settings", "Ajustes"),
        ]
        for idx, (kind, label) in enumerate(nav_specs):
            btn = QToolButton()
            btn.setFixedSize(84, 68)
            btn.setText(label)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("icon_kind", kind)
            btn.setIconSize(QSize(26, 26))
            btn.clicked.connect(lambda _checked=False, i=idx: self._switch_tab(i))
            sb_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        sb_layout.addStretch()
        main_h.addWidget(sidebar)

        # Área direita: Cabeçalho superior + Páginas
        right_area = QWidget()
        right_v = QVBoxLayout(right_area)
        right_v.setContentsMargins(22, 12, 16, 16)
        right_v.setSpacing(8)

        # Top Bar (Status à esquerda + Controles de Janela Minimizar/Maximizar/Fechar no canto superior direito)
        top_bar = QVBoxLayout()
        top_bar.setContentsMargins(0, 2, 0, 4)
        top_bar.setSpacing(6)

        top_row1 = QHBoxLayout()
        top_row1.setSpacing(8)

        self.lbl_conn_badge = QLabel("● Procurando mouse...")
        self.lbl_conn_badge.setStyleSheet(
            "background-color: #1c2029; border: 1px solid #303646; "
            "border-radius: 6px; padding: 5px 10px; font-weight: 700; color: #00d4ff;"
        )
        top_row1.addWidget(self.lbl_conn_badge)

        self.lbl_battery = QLabel("Bateria: --%")
        self.lbl_battery.setStyleSheet(
            "background-color: #1c2029; border: 1px solid #303646; "
            "border-radius: 6px; padding: 5px 10px; font-weight: 700; color: #ffe000;"
        )
        top_row1.addWidget(self.lbl_battery)

        self.combo_profile = QComboBox()
        for i in range(4):
            self.combo_profile.addItem(f"Perfil {i + 1}")
        self.combo_profile.setCurrentIndex(self.store.active_profile)
        self.combo_profile.currentIndexChanged.connect(self._on_profile_changed)
        top_row1.addWidget(self.combo_profile)
        top_row1.addStretch()

        # Botões de controle da janela (Minimizar, Maximizar/Restaurar, Fechar) no canto superior direito
        win_ctrl_row = QHBoxLayout()
        win_ctrl_row.setSpacing(6)

        self.btn_win_min = QPushButton("—")
        self.btn_win_min.setObjectName("WinCtrlBtn")
        self.btn_win_min.setFixedSize(32, 28)
        self.btn_win_min.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_win_min.clicked.connect(self.showMinimized)

        self.btn_win_max = QPushButton("□")
        self.btn_win_max.setObjectName("WinCtrlBtn")
        self.btn_win_max.setFixedSize(32, 28)
        self.btn_win_max.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_win_max.clicked.connect(self._toggle_maximize)

        self.btn_win_close = QPushButton("✕")
        self.btn_win_close.setObjectName("WinCloseBtn")
        self.btn_win_close.setFixedSize(32, 28)
        self.btn_win_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_win_close.clicked.connect(self.close)

        win_ctrl_row.addWidget(self.btn_win_min)
        win_ctrl_row.addWidget(self.btn_win_max)
        win_ctrl_row.addWidget(self.btn_win_close)
        top_row1.addLayout(win_ctrl_row)

        top_bar.addLayout(top_row1)

        top_row2 = QHBoxLayout()
        self.btn_fix_udev = QPushButton("⚡ Liberar Permissão USB (udev)")
        self.btn_fix_udev.setObjectName("AccentBtn")
        self.btn_fix_udev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fix_udev.clicked.connect(self._install_udev_pkexec)
        self.btn_fix_udev.setVisible(False)
        top_row2.addWidget(self.btn_fix_udev)
        top_row2.addStretch()
        top_bar.addLayout(top_row2)

        right_v.addLayout(top_bar)
        right_v.addSpacing(12)

        # Stacked Pages
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_page_buttons())
        self.pages.addWidget(self._build_page_sensor())
        self.pages.addWidget(self._build_page_macro())
        self.pages.addWidget(self._build_page_light())
        self.pages.addWidget(self._build_page_settings())
        right_v.addWidget(self.pages, 1)

        # Rodapé de status rápido
        self.lbl_status_footer = QLabel("Pronto.")
        self.lbl_status_footer.setStyleSheet("color: #9aa0b0; font-size: 12px;")
        right_v.addWidget(self.lbl_status_footer)

        main_h.addWidget(right_area, 1)
        self._switch_tab(0)

    def _switch_tab(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            active = i == index
            btn.setIcon(make_nav_icon(btn.property("icon_kind"), active))
            if active:
                btn.setStyleSheet(
                    "QToolButton { background-color: #1e222b; border: 2px solid #ffe000; "
                    "border-radius: 10px; color: #ffe000; font-size: 11px; font-weight: 700; padding-top: 6px; }"
                )
            else:
                btn.setStyleSheet(
                    "QToolButton { background-color: transparent; border: 1px solid transparent; "
                    "border-radius: 10px; color: #c8cdd8; font-size: 11px; font-weight: 600; padding-top: 6px; }"
                    "QToolButton:hover { background-color: #343946; color: #ffffff; }"
                )

    # ------------------------------------------------------------------
    # ABA 1: Botões (Home / Buttoninterface)
    # ------------------------------------------------------------------
    def _build_page_buttons(self) -> QWidget:
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(18)

        # Coluna esquerda: 6 botões + Debounce + Import/Export/Reset
        left_card = QFrame()
        left_card.setObjectName("Card")
        left_v = QVBoxLayout(left_card)
        left_v.setContentsMargins(16, 16, 16, 16)
        left_v.setSpacing(10)

        title = QLabel("Mapeamento de Botões (6 Teclas)")
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #ffe000;")
        left_v.addWidget(title)

        self.btn_slot_widgets: list[QPushButton] = []
        for idx in range(6):
            row = QHBoxLayout()
            badge = QLabel(str(idx + 1))
            badge.setFixedSize(26, 26)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(
                "background-color: #ffe000; color: #0d0e11; font-weight: 800; border-radius: 13px;"
            )
            row.addWidget(badge)

            slot_btn = QPushButton()
            slot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            slot_btn.setMinimumHeight(34)
            slot_btn.setStyleSheet("text-align: left; padding-left: 12px;")
            slot_btn.clicked.connect(lambda _c=False, b=idx: self._open_button_dialog(b))
            row.addWidget(slot_btn, 1)
            self.btn_slot_widgets.append(slot_btn)
            left_v.addLayout(row)

        left_v.addSpacing(8)

        # Debounce Time
        deb_frame = QFrame()
        deb_frame.setStyleSheet("background-color: #1e222c; border-radius: 6px; padding: 6px;")
        deb_h = QHBoxLayout(deb_frame)
        deb_lbl = QLabel("⚡ Atraso de Debounce:")
        deb_lbl.setStyleSheet("font-weight: 700;")
        deb_h.addWidget(deb_lbl)
        self.spin_debounce = QSpinBox()
        self.spin_debounce.setRange(0, 30)
        self.spin_debounce.setSuffix(" ms")
        self.spin_debounce.setValue(self.cfg.debounce_ms)
        self.spin_debounce.valueChanged.connect(self._on_debounce_changed)
        deb_h.addWidget(self.spin_debounce)
        left_v.addWidget(deb_frame)

        left_v.addStretch()

        # Importar / Exportar / Restaurar
        act_row = QHBoxLayout()
        btn_import = QPushButton("Importar")
        btn_export = QPushButton("Exportar")
        btn_reset = QPushButton("Restaurar")
        btn_reset.setObjectName("DangerBtn")
        btn_import.clicked.connect(self._import_profile_dialog)
        btn_export.clicked.connect(self._export_profile_dialog)
        btn_reset.clicked.connect(self._reset_current_profile)
        act_row.addWidget(btn_import)
        act_row.addWidget(btn_export)
        act_row.addWidget(btn_reset)
        left_v.addLayout(act_row)

        h.addWidget(left_card, 1)

        # Coluna direita: Diagrama interativo do Fallen Lobo Wireless
        right_card = QFrame()
        right_card.setObjectName("Card")
        right_v = QVBoxLayout(right_card)
        right_v.setContentsMargins(14, 14, 14, 14)
        lbl_hint = QLabel("Clique no número na imagem ou na lista ao lado para configurar o botão:")
        lbl_hint.setWordWrap(True)
        lbl_hint.setStyleSheet("color: #b0b6c6; font-size: 12px;")
        lbl_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_v.addWidget(lbl_hint)

        self.mouse_diagram = MouseDiagramWidget(on_select_button=self._open_button_dialog)
        right_v.addWidget(self.mouse_diagram, 0, Qt.AlignmentFlag.AlignCenter)

        h.addWidget(right_card, 1)
        return page

    # ------------------------------------------------------------------
    # ABA 2: Sensor & DPI (PixArt PAW3395)
    # ------------------------------------------------------------------
    def _build_page_sensor(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)

        # Bloco Superior: Estágios de DPI
        dpi_card = QFrame()
        dpi_card.setObjectName("Card")
        dpi_v = QVBoxLayout(dpi_card)
        dpi_v.setContentsMargins(14, 12, 14, 12)
        dpi_v.setSpacing(10)

        hdr_row = QHBoxLayout()
        lbl_dpi_title = QLabel("★ Estágios de DPI (Sensor PixArt PAW3395 — 50 a 26.000 DPI)")
        lbl_dpi_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #ffe000;")
        hdr_row.addWidget(lbl_dpi_title)
        hdr_row.addStretch()
        hdr_row.addWidget(QLabel("Estágios ativos:"))
        self.spin_max_stages = QSpinBox()
        self.spin_max_stages.setRange(1, 8)
        self.spin_max_stages.setValue(self.cfg.max_dpi_stages)
        self.spin_max_stages.valueChanged.connect(self._on_max_stages_changed)
        hdr_row.addWidget(self.spin_max_stages)
        dpi_v.addLayout(hdr_row)

        # Grid de 8 cards de estágio DPI
        stages_h = QHBoxLayout()
        stages_h.setSpacing(8)
        self.stage_cards: list[QPushButton] = []
        for idx in range(8):
            btn = QPushButton()
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(64)
            btn.clicked.connect(lambda _c=False, s=idx: self._on_select_dpi_stage(s))
            stages_h.addWidget(btn, 1)
            self.stage_cards.append(btn)
        dpi_v.addLayout(stages_h)

        # Ajuste fino do estágio selecionado + Cor do estágio
        tune_row = QHBoxLayout()
        self.lbl_editing_stage = QLabel("Estágio #1:")
        self.lbl_editing_stage.setStyleSheet("font-weight: 700; color: #00d4ff;")
        tune_row.addWidget(self.lbl_editing_stage)

        self.slider_dpi = QSlider(Qt.Orientation.Horizontal)
        self.slider_dpi.setRange(1, 520)  # 50..26000 em passos de 50
        self.slider_dpi.valueChanged.connect(self._on_dpi_slider_moved)
        self.slider_dpi.sliderReleased.connect(self._commit_current_dpi_stage)
        tune_row.addWidget(self.slider_dpi, 1)

        self.spin_dpi_val = QSpinBox()
        self.spin_dpi_val.setRange(50, 26000)
        self.spin_dpi_val.setSingleStep(50)
        self.spin_dpi_val.setSuffix(" DPI")
        self.spin_dpi_val.valueChanged.connect(self._on_dpi_spin_changed)
        tune_row.addWidget(self.spin_dpi_val)

        self.btn_stage_color = QPushButton("Cor do Estágio")
        self.btn_stage_color.clicked.connect(self._pick_stage_color)
        tune_row.addWidget(self.btn_stage_color)

        dpi_v.addLayout(tune_row)
        v.addWidget(dpi_card)

        # Bloco do Meio: Taxa de Atualização (Polling Rate) + Iluminação DPI
        mid_h = QHBoxLayout()
        mid_h.setSpacing(12)

        rate_card = QFrame()
        rate_card.setObjectName("Card")
        rate_v = QVBoxLayout(rate_card)
        rate_v.setContentsMargins(14, 12, 14, 12)
        lbl_rate = QLabel("⚡ Taxa de Atualização (Polling Rate)")
        lbl_rate.setStyleSheet("font-size: 14px; font-weight: 700; color: #ffe000;")
        rate_v.addWidget(lbl_rate)

        rate_grid = QGridLayout()
        self.rate_buttons: dict[int, QPushButton] = {}
        for idx, hz in enumerate([125, 250, 500, 1000, 2000, 4000]):
            b = QPushButton(f"{hz} Hz")
            b.setObjectName("RateBtn")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, r=hz: self._on_polling_rate_clicked(r))
            rate_grid.addWidget(b, idx // 3, idx % 3)
            self.rate_buttons[hz] = b
        rate_v.addLayout(rate_grid)
        mid_h.addWidget(rate_card, 1)

        # Iluminação do Indicador de DPI
        dpiled_card = QFrame()
        dpiled_card.setObjectName("Card")
        dpiled_v = QVBoxLayout(dpiled_card)
        dpiled_v.setContentsMargins(14, 12, 14, 12)
        lbl_dpiled = QLabel("● Efeitos de Iluminação DPI")
        lbl_dpiled.setStyleSheet("font-size: 14px; font-weight: 700; color: #ffe000;")
        dpiled_v.addWidget(lbl_dpiled)

        row_dl_mode = QHBoxLayout()
        row_dl_mode.addWidget(QLabel("Modo:"))
        self.combo_dpi_led_mode = QComboBox()
        self.combo_dpi_led_mode.addItems(["Desligado", "Estático", "Respiração"])
        self.combo_dpi_led_mode.currentIndexChanged.connect(self._on_dpi_led_changed)
        row_dl_mode.addWidget(self.combo_dpi_led_mode, 1)
        dpiled_v.addLayout(row_dl_mode)

        row_dl_val = QHBoxLayout()
        row_dl_val.addWidget(QLabel("Brilho:"))
        self.spin_dpi_led_bright = QSpinBox()
        self.spin_dpi_led_bright.setRange(16, 255)
        self.spin_dpi_led_bright.setSingleStep(16)
        self.spin_dpi_led_bright.valueChanged.connect(self._on_dpi_led_changed)
        row_dl_val.addWidget(self.spin_dpi_led_bright)

        row_dl_val.addWidget(QLabel("Velocidade:"))
        self.spin_dpi_led_speed = QSpinBox()
        self.spin_dpi_led_speed.setRange(1, 5)
        self.spin_dpi_led_speed.valueChanged.connect(self._on_dpi_led_changed)
        row_dl_val.addWidget(self.spin_dpi_led_speed)
        dpiled_v.addLayout(row_dl_val)

        mid_h.addWidget(dpiled_card, 1)
        v.addLayout(mid_h)

        # Bloco Inferior: Configurações Avançadas do Sensor PAW3395
        sens_card = QFrame()
        sens_card.setObjectName("Card")
        sens_v = QVBoxLayout(sens_card)
        sens_v.setContentsMargins(14, 12, 14, 12)
        lbl_sens = QLabel("⚙ Configurações do Sensor")
        lbl_sens.setStyleSheet("font-size: 14px; font-weight: 700; color: #ffe000;")
        sens_v.addWidget(lbl_sens)

        top_sens_row = QHBoxLayout()
        top_sens_row.addWidget(QLabel("LOD (Descolagem):"))
        self.combo_lod = QComboBox()
        self.combo_lod.addItems(["1 mm", "2 mm"])
        self.combo_lod.currentIndexChanged.connect(self._on_lod_changed)
        top_sens_row.addWidget(self.combo_lod)

        top_sens_row.addSpacing(14)
        top_sens_row.addWidget(QLabel("Modo:"))
        self.combo_sensor_mode = QComboBox()
        self.combo_sensor_mode.addItems([
            "LP (Baixo Consumo)",
            "HP (Alto Desempenho)",
            "Corded (Performance Máxima)",
        ])
        self.combo_sensor_mode.currentIndexChanged.connect(self._on_sensor_mode_changed)
        top_sens_row.addWidget(self.combo_sensor_mode, 1)

        top_sens_row.addWidget(QLabel("Tempo:"))
        self.combo_perf_time = QComboBox()
        for _code, pt_txt, _en in PERFORMANCE_TIME_OPTIONS:
            self.combo_perf_time.addItem(pt_txt)
        self.combo_perf_time.currentIndexChanged.connect(self._on_sensor_mode_changed)
        top_sens_row.addWidget(self.combo_perf_time)
        sens_v.addLayout(top_sens_row)

        toggles_row = QHBoxLayout()
        self.chk_motion_sync = QCheckBox("Motion Sync (Sincronização)")
        self.chk_angle_snap = QCheckBox("Angle Snapping (Correção)")
        self.chk_ripple = QCheckBox("Ripple Control (Suavização)")
        self.chk_motion_sync.toggled.connect(self._on_motion_sync_toggled)
        self.chk_angle_snap.toggled.connect(self._on_angle_snap_toggled)
        self.chk_ripple.toggled.connect(self._on_ripple_toggled)
        toggles_row.addWidget(self.chk_motion_sync)
        toggles_row.addWidget(self.chk_angle_snap)
        toggles_row.addWidget(self.chk_ripple)
        sens_v.addLayout(toggles_row)

        v.addWidget(sens_card)
        return page

    # ------------------------------------------------------------------
    # ABA 3: Editor e Gravador de Macros
    # ------------------------------------------------------------------
    def _build_page_macro(self) -> QWidget:
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(14)

        # Coluna 1: Lista de Macros
        col1 = QFrame()
        col1.setObjectName("Card")
        v1 = QVBoxLayout(col1)
        v1.setContentsMargins(14, 14, 14, 14)
        lbl1 = QLabel("★ Lista de Macros")
        lbl1.setStyleSheet("font-size: 14px; font-weight: 700; color: #ffe000;")
        v1.addWidget(lbl1)

        self.list_macros = QListWidget()
        self.list_macros.currentRowChanged.connect(self._on_macro_selected)
        v1.addWidget(self.list_macros, 1)

        btn_new_m = QPushButton("+ Nova Macro")
        btn_new_m.setObjectName("AccentBtn")
        btn_del_m = QPushButton("Apagar Macro")
        btn_del_m.setObjectName("DangerBtn")
        btn_new_m.clicked.connect(self._create_new_macro)
        btn_del_m.clicked.connect(self._delete_selected_macro)
        v1.addWidget(btn_new_m)
        v1.addWidget(btn_del_m)
        h.addWidget(col1, 1)

        # Coluna 2: Lista de Teclas / Eventos da Macro
        col2 = QFrame()
        col2.setObjectName("Card")
        v2 = QVBoxLayout(col2)
        v2.setContentsMargins(14, 14, 14, 14)
        lbl2 = QLabel("⌨ Sequência de Eventos")
        lbl2.setStyleSheet("font-size: 14px; font-weight: 700; color: #ffe000;")
        v2.addWidget(lbl2)

        self.list_macro_steps = QListWidget()
        v2.addWidget(self.list_macro_steps, 1)

        step_btns = QHBoxLayout()
        btn_edit_delay = QPushButton("Modificar Atraso")
        btn_del_step = QPushButton("Apagar Passo")
        btn_edit_delay.clicked.connect(self._edit_macro_step_delay)
        btn_del_step.clicked.connect(self._delete_macro_step)
        step_btns.addWidget(btn_edit_delay)
        step_btns.addWidget(btn_del_step)
        v2.addLayout(step_btns)
        h.addWidget(col2, 1)

        # Coluna 3: Gravador e Opções de Repetição
        col3 = QFrame()
        col3.setObjectName("Card")
        v3 = QVBoxLayout(col3)
        v3.setContentsMargins(14, 14, 14, 14)
        lbl3 = QLabel("● Gravação & Comandos")
        lbl3.setStyleSheet("font-size: 14px; font-weight: 700; color: #ffe000;")
        v3.addWidget(lbl3)

        self.btn_record_macro = QPushButton("● Começar a Gravar")
        self.btn_record_macro.setObjectName("AccentBtn")
        self.btn_record_macro.clicked.connect(self._toggle_macro_recording)
        v3.addWidget(self.btn_record_macro)

        self.chk_auto_delay = QCheckBox("Inserir Atraso Automaticamente")
        self.chk_auto_delay.setChecked(True)
        v3.addWidget(self.chk_auto_delay)

        d_row = QHBoxLayout()
        d_row.addWidget(QLabel("Atraso Padrão:"))
        self.spin_default_delay = QSpinBox()
        self.spin_default_delay.setRange(1, 5000)
        self.spin_default_delay.setValue(10)
        self.spin_default_delay.setSuffix(" ms")
        d_row.addWidget(self.spin_default_delay)
        v3.addLayout(d_row)

        v3.addSpacing(8)
        v3.addWidget(QLabel("Inserir Tecla Manualmente:"))
        ins_row = QHBoxLayout()
        self.combo_manual_key = QComboBox()
        for k in HID_KEYCODES:
            self.combo_manual_key.addItem(k)
        ins_row.addWidget(self.combo_manual_key, 1)
        btn_add_click = QPushButton("+ Inserir")
        btn_add_click.clicked.connect(self._insert_manual_macro_key)
        ins_row.addWidget(btn_add_click)
        v3.addLayout(ins_row)

        v3.addSpacing(8)
        v3.addWidget(QLabel("Modo de Repetição:"))
        self.rad_rep_loose = QRadioButton("Repetir até liberação da tecla")
        self.rad_rep_click = QRadioButton("Repetir até pressionar a tecla")
        self.rad_rep_num = QRadioButton("Número de Repetições:")
        self.rad_rep_num.setChecked(True)
        v3.addWidget(self.rad_rep_loose)
        v3.addWidget(self.rad_rep_click)
        v3.addWidget(self.rad_rep_num)

        self.spin_macro_repeats = QSpinBox()
        self.spin_macro_repeats.setRange(1, 250)
        self.spin_macro_repeats.setValue(1)
        v3.addWidget(self.spin_macro_repeats)

        v3.addStretch()
        btn_save_macro = QPushButton("✓ Salvar Macro no Mouse")
        btn_save_macro.setObjectName("AccentBtn")
        btn_save_macro.clicked.connect(self._save_current_macro_to_hw)
        v3.addWidget(btn_save_macro)

        h.addWidget(col3, 1)
        return page

    # ------------------------------------------------------------------
    # ABA 4: Iluminação RGB (Light)
    # ------------------------------------------------------------------
    def _build_page_light(self) -> QWidget:
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(16)

        left_card = QFrame()
        left_card.setObjectName("Card")
        lv = QVBoxLayout(left_card)
        lv.setContentsMargins(18, 18, 18, 18)
        lv.setSpacing(14)

        lbl_title = QLabel("★ Efeitos de Iluminação")
        lbl_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #ffe000;")
        lv.addWidget(lbl_title)

        lv.addWidget(QLabel("Modo de Iluminação:"))
        self.combo_light_mode = QComboBox()
        self.combo_light_mode.addItems([
            "Desligado",
            "Fluxo Arco-íris",
            "Respiração (cor única)",
            "Arco-íris constante",
            "Neon",
            "Respiração multicolorida",
            "Cores vibrantes (constante)",
        ])
        lv.addWidget(self.combo_light_mode)

        b_row = QHBoxLayout()
        b_row.addWidget(QLabel("Brilho (1–10):"))
        self.slider_light_bright = QSlider(Qt.Orientation.Horizontal)
        self.slider_light_bright.setRange(1, 10)
        b_row.addWidget(self.slider_light_bright, 1)
        self.spin_light_bright = QSpinBox()
        self.spin_light_bright.setRange(1, 10)
        b_row.addWidget(self.spin_light_bright)
        self.slider_light_bright.valueChanged.connect(self.spin_light_bright.setValue)
        self.spin_light_bright.valueChanged.connect(self.slider_light_bright.setValue)
        lv.addLayout(b_row)

        s_row = QHBoxLayout()
        s_row.addWidget(QLabel("Velocidade (1–10):"))
        self.slider_light_speed = QSlider(Qt.Orientation.Horizontal)
        self.slider_light_speed.setRange(1, 10)
        s_row.addWidget(self.slider_light_speed, 1)
        self.spin_light_speed = QSpinBox()
        self.spin_light_speed.setRange(1, 10)
        s_row.addWidget(self.spin_light_speed)
        self.slider_light_speed.valueChanged.connect(self.spin_light_speed.setValue)
        self.spin_light_speed.valueChanged.connect(self.slider_light_speed.setValue)
        lv.addLayout(s_row)

        self.chk_moving_off = QCheckBox("Desligar luzes ao mover o mouse")
        lv.addWidget(self.chk_moving_off)

        lv.addWidget(QLabel("Tempo para apagar luzes após ficar parado:"))
        self.combo_light_sleep = QComboBox()
        for _code, pt_txt, _en in SLEEP_TIME_OPTIONS:
            self.combo_light_sleep.addItem(pt_txt)
        lv.addWidget(self.combo_light_sleep)

        lv.addStretch()
        btn_apply_light = QPushButton("✓ Aplicar Iluminação")
        btn_apply_light.setObjectName("AccentBtn")
        btn_apply_light.clicked.connect(self._apply_light_settings)
        lv.addWidget(btn_apply_light)
        h.addWidget(left_card, 1)

        # Coluna direita: Cores personalizadas & Pré-visualização
        right_card = QFrame()
        right_card.setObjectName("Card")
        rv = QVBoxLayout(right_card)
        rv.setContentsMargins(18, 18, 18, 18)
        rv.setSpacing(14)

        lbl_col = QLabel("● Cores Personalizadas")
        lbl_col.setStyleSheet("font-size: 15px; font-weight: 700; color: #ffe000;")
        rv.addWidget(lbl_col)

        rgb_row = QHBoxLayout()
        rgb_row.addWidget(QLabel("R:"))
        self.spin_r = QSpinBox()
        self.spin_r.setRange(0, 255)
        rgb_row.addWidget(self.spin_r)
        rgb_row.addWidget(QLabel("G:"))
        self.spin_g = QSpinBox()
        self.spin_g.setRange(0, 255)
        rgb_row.addWidget(self.spin_g)
        rgb_row.addWidget(QLabel("B:"))
        self.spin_b = QSpinBox()
        self.spin_b.setRange(0, 255)
        rgb_row.addWidget(self.spin_b)
        for sp in (self.spin_r, self.spin_g, self.spin_b):
            sp.valueChanged.connect(self._update_light_preview)
        rv.addLayout(rgb_row)

        rv.addWidget(QLabel("Paleta de Cores Padrão:"))
        pal_grid = QGridLayout()
        for i, (r, g, b) in enumerate(PRESET_COLORS):
            sw = QPushButton()
            sw.setFixedSize(36, 28)
            sw.setCursor(Qt.CursorShape.PointingHandCursor)
            sw.setStyleSheet(
                f"background-color: rgb({r},{g},{b}); border: 1px solid #555; border-radius: 4px;"
            )
            sw.clicked.connect(lambda _c=False, rc=(r, g, b): self._set_rgb_spins(*rc))
            pal_grid.addWidget(sw, i // 7, i % 7)
        rv.addLayout(pal_grid)

        btn_wheel = QPushButton("Abrir Roda de Cores...")
        btn_wheel.clicked.connect(self._pick_light_color_dialog)
        rv.addWidget(btn_wheel)

        rv.addWidget(QLabel("Pré-visualização:"))
        self.lbl_color_preview = QLabel()
        self.lbl_color_preview.setFixedHeight(64)
        rv.addWidget(self.lbl_color_preview)
        rv.addStretch()

        h.addWidget(right_card, 1)
        return page

    # ------------------------------------------------------------------
    # ABA 5: Configurações & Dispositivo (FormSetting)
    # ------------------------------------------------------------------
    def _build_page_settings(self) -> QWidget:
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(16)

        # Coluna esquerda: Informações do Dispositivo & Firmware
        info_card = QFrame()
        info_card.setObjectName("Card")
        iv = QVBoxLayout(info_card)
        iv.setContentsMargins(18, 18, 18, 18)
        iv.setSpacing(12)

        lbl_info = QLabel("ℹ Informação do Dispositivo")
        lbl_info.setStyleSheet("font-size: 15px; font-weight: 700; color: #ffe000;")
        iv.addWidget(lbl_info)

        self.lbl_dev_name = QLabel("Dispositivo: Compx Mouse Lobo Wireless")
        self.lbl_dev_mode = QLabel("Modo: --")
        self.lbl_dongle_fw = QLabel("Versão do firmware do Receptor: --")
        self.lbl_mouse_fw = QLabel("Versão do firmware do Mouse: --")
        self.lbl_driver_ver = QLabel("Versão do Driver: v1.0.1.3 (Linux Edition)")
        for w in (
            self.lbl_dev_name,
            self.lbl_dev_mode,
            self.lbl_dongle_fw,
            self.lbl_mouse_fw,
            self.lbl_driver_ver,
        ):
            w.setStyleSheet("font-size: 13px; padding: 2px 0;")
            iv.addWidget(w)

        btn_refresh = QPushButton("↻ Ler Configurações Atuais do Mouse")
        btn_refresh.clicked.connect(lambda: self.refresh_device_status(sync_from_hw=True))
        iv.addWidget(btn_refresh)

        btn_udev = QPushButton("⚡ Instalar / Reparar Regra udev (Permissão USB)")
        btn_udev.clicked.connect(self._install_udev_pkexec)
        iv.addWidget(btn_udev)

        iv.addStretch()

        btn_hw_reset = QPushButton("▲ Restaurar Padrão de Fábrica no Mouse")
        btn_hw_reset.setObjectName("DangerBtn")
        btn_hw_reset.clicked.connect(self._factory_reset_mouse)
        iv.addWidget(btn_hw_reset)
        h.addWidget(info_card, 1)

        # Coluna direita: Modo de Espera, Longa Distância e LED do Receptor
        adv_card = QFrame()
        adv_card.setObjectName("Card")
        av = QVBoxLayout(adv_card)
        av.setContentsMargins(18, 18, 18, 18)
        av.setSpacing(12)

        lbl_adv = QLabel("⚙ Configurações Avançadas & Energia")
        lbl_adv.setStyleSheet("font-size: 15px; font-weight: 700; color: #ffe000;")
        av.addWidget(lbl_adv)

        av.addWidget(QLabel("Tempo para entrar em modo de espera:"))
        self.combo_sleep_setting = QComboBox()
        for _code, pt_txt, _en in SLEEP_TIME_OPTIONS:
            self.combo_sleep_setting.addItem(pt_txt)
        self.combo_sleep_setting.currentIndexChanged.connect(self._on_sleep_setting_changed)
        av.addWidget(self.combo_sleep_setting)

        av.addSpacing(6)
        self.chk_long_range = QCheckBox("Modo de Longa Distância (Long Range Mode)")
        self.chk_long_range.toggled.connect(self._on_long_range_toggled)
        av.addWidget(self.chk_long_range)

        lbl_lr_desc = QLabel(
            "No modo de longa distância, o alcance será maior e a resistência a "
            "interferências mais forte; o consumo aumentará."
        )
        lbl_lr_desc.setWordWrap(True)
        lbl_lr_desc.setStyleSheet("color: #9aa0b0; font-size: 11px;")
        av.addWidget(lbl_lr_desc)

        av.addSpacing(6)
        av.addWidget(QLabel("Informações exibidas pelo LED do receptor:"))
        self.combo_dongle_led = QComboBox()
        self.combo_dongle_led.addItems([
            "Taxa de Atualização (Código de Cores por Hz)",
            "Estado da Bateria (Verde=100%, Amarelo=66%, Vermelho=0%)",
            "Apenas Aviso de Bateria (Pisca em vermelho com bateria baixa)",
        ])
        self.combo_dongle_led.currentIndexChanged.connect(self._on_dongle_led_changed)
        av.addWidget(self.combo_dongle_led)

        av.addStretch()
        h.addWidget(adv_card, 1)
        return page

    # ------------------------------------------------------------------
    # Sincronização da Interface com a Configuração e com o Hardware
    # ------------------------------------------------------------------
    def _sync_ui_from_cfg(self) -> None:
        self._block_signals(True)
        try:
            # Aba 1: Botões
            for i in range(6):
                b = self.cfg.buttons[i]
                lbl = b.label or describe_button_mapping(b.action_type, b.param1, b.param2)
                self.btn_slot_widgets[i].setText(lbl)
            self.spin_debounce.setValue(self.cfg.debounce_ms)

            # Aba 2: Sensor & DPI
            self.spin_max_stages.setValue(self.cfg.max_dpi_stages)
            if self.selected_dpi_stage >= self.cfg.max_dpi_stages:
                self.selected_dpi_stage = self.cfg.active_dpi_stage
            self._refresh_dpi_stage_cards()

            st = self.cfg.dpi_stages[self.selected_dpi_stage]
            self.lbl_editing_stage.setText(f"Estágio #{self.selected_dpi_stage + 1}:")
            self.slider_dpi.setValue(st.dpi_x // 50)
            self.spin_dpi_val.setValue(st.dpi_x)

            for hz, btn in self.rate_buttons.items():
                btn.setProperty("active", "true" if hz == self.cfg.polling_rate_hz else "false")
                btn.style().unpolish(btn)
                btn.style().polish(btn)

            self.combo_dpi_led_mode.setCurrentIndex(min(2, max(0, self.cfg.dpi_led_mode)))
            self.spin_dpi_led_bright.setValue(self.cfg.dpi_led_brightness)
            self.spin_dpi_led_speed.setValue(self.cfg.dpi_led_speed)

            self.combo_lod.setCurrentIndex(1 if self.cfg.lod_mm == 2 else 0)
            self.combo_sensor_mode.setCurrentIndex(min(2, max(0, self.cfg.sensor_mode)))
            perf_codes = [c for c, _, _ in PERFORMANCE_TIME_OPTIONS]
            if self.cfg.performance_time in perf_codes:
                self.combo_perf_time.setCurrentIndex(perf_codes.index(self.cfg.performance_time))

            self.chk_motion_sync.setChecked(self.cfg.motion_sync)
            self.chk_angle_snap.setChecked(self.cfg.angle_snapping)
            self.chk_ripple.setChecked(self.cfg.ripple_control)

            # Aba 3: Macros
            self._refresh_macro_list()

            # Aba 4: Iluminação
            self.combo_light_mode.setCurrentIndex(min(6, max(0, self.cfg.light.mode)))
            self.slider_light_bright.setValue(max(1, min(10, self.cfg.light.brightness)))
            self.spin_light_bright.setValue(max(1, min(10, self.cfg.light.brightness)))
            self.slider_light_speed.setValue(max(1, min(10, self.cfg.light.speed)))
            self.spin_light_speed.setValue(max(1, min(10, self.cfg.light.speed)))
            self.chk_moving_off.setChecked(self.cfg.light.moving_off)
            self.spin_r.setValue(self.cfg.light.r)
            self.spin_g.setValue(self.cfg.light.g)
            self.spin_b.setValue(self.cfg.light.b)
            self._update_light_preview()

            sleep_codes = [c for c, _, _ in SLEEP_TIME_OPTIONS]
            s_idx = sleep_codes.index(self.cfg.sleep_code) if self.cfg.sleep_code in sleep_codes else 2
            self.combo_light_sleep.setCurrentIndex(s_idx)
            self.combo_sleep_setting.setCurrentIndex(s_idx)
        finally:
            self._block_signals(False)

    def _block_signals(self, block: bool) -> None:
        widgets = [
            self.spin_debounce,
            self.spin_max_stages,
            self.slider_dpi,
            self.spin_dpi_val,
            self.combo_dpi_led_mode,
            self.spin_dpi_led_bright,
            self.spin_dpi_led_speed,
            self.combo_lod,
            self.combo_sensor_mode,
            self.combo_perf_time,
            self.chk_motion_sync,
            self.chk_angle_snap,
            self.chk_ripple,
            self.combo_sleep_setting,
        ]
        for w in widgets:
            w.blockSignals(block)

    def _refresh_dpi_stage_cards(self) -> None:
        for idx, btn in enumerate(self.stage_cards):
            enabled = idx < self.cfg.max_dpi_stages
            btn.setVisible(enabled)
            if not enabled:
                continue
            st = self.cfg.dpi_stages[idx]
            r, g, b = st.color
            is_active = idx == self.cfg.active_dpi_stage
            is_sel = idx == self.selected_dpi_stage
            border = "#ffe000" if is_active else ("#00d4ff" if is_sel else "#2d3240")
            bw = "2px" if (is_active or is_sel) else "1px"
            star = "★ " if is_active else ""
            btn.setText(f"{star}Estágio {idx + 1}\n{st.dpi_x} DPI")
            btn.setStyleSheet(
                f"background-color: #1a1d24; border: {bw} solid {border}; "
                f"border-bottom: 5px solid rgb({r},{g},{b}); border-radius: 7px; font-weight: 700;"
            )

    def refresh_device_status(self, sync_from_hw: bool = False) -> None:
        devices = find_devices()
        if not devices:
            self.device_info = None
            self.lbl_conn_badge.setText("● Mouse Desconectado")
            self.lbl_battery.setText("Bateria: --%")
            self.btn_fix_udev.setVisible(False)
            self._sync_ui_from_cfg()
            return

        dev = devices[0]
        self.device_info = dev
        if not dev.accessible:
            self.lbl_conn_badge.setText(f"▲ {dev.mode} (Sem permissão)")
            self.btn_fix_udev.setVisible(True)
            self.lbl_status_footer.setText(
                f"Dispositivo detectado em {dev.hidraw_path}, mas precisa liberar a regra udev."
            )
            self._sync_ui_from_cfg()
            return

        self.btn_fix_udev.setVisible(False)
        try:
            with LoboMouse(dev) as mouse:
                self.online = mouse.is_online()
                if self.online:
                    if self.dongle_fw == "--" or sync_from_hw:
                        ver = mouse.get_version()
                        sver = mouse.get_slave_version()
                        self.dongle_fw = f"v{ver[0]}.{ver[1]:02d}"
                        self.mouse_fw = f"v{sver[0]}.{sver[1]:02d}"
                    bat = mouse.get_battery()
                    self.battery_percent = bat.percent
                    self.battery_mv = bat.voltage_mv
                    self.battery_charging = bat.charging

                    if sync_from_hw:
                        hw_cfg = mouse.get_config()
                        self.cfg = hw_cfg
                        self.store.profiles[self.store.active_profile] = hw_cfg
                        self.store.save()

            state_str = "Online" if self.online else "Em Espera"
            self.lbl_conn_badge.setText(f"● {dev.mode} — {state_str}")
            chg = " ⚡" if self.battery_charging else ""
            mv_txt = f" ({self.battery_mv} mV)" if self.battery_mv > 0 else ""
            self.lbl_battery.setText(f"Bateria: {self.battery_percent}%{mv_txt}{chg}")

            self.lbl_dev_name.setText(f"Dispositivo: {dev.name} ({dev.hidraw_path})")
            self.lbl_dev_mode.setText(f"Modo de Conexão: {dev.mode} ({state_str})")
            self.lbl_dongle_fw.setText(f"Versão do firmware do Receptor: {self.dongle_fw}")
            self.lbl_mouse_fw.setText(f"Versão do firmware do Mouse: {self.mouse_fw}")
            if sync_from_hw and self.online:
                self.lbl_status_footer.setText("Configurações sincronizadas com o mouse.")
            elif not self.online:
                self.lbl_status_footer.setText("Mouse em modo de espera (mova-o para sincronizar).")
        except LoboDriverError as exc:
            if sync_from_hw:
                self.lbl_status_footer.setText(f"Aviso: {exc}")

        self._sync_ui_from_cfg()

    def _hw_apply(self, action: Callable[[LoboMouse], None], msg: str) -> None:
        self.store.save()
        try:
            with LoboMouse() as mouse:
                action(mouse)
            self.lbl_status_footer.setText(f"✓ {msg}")
        except LoboDriverError as exc:
            self.lbl_status_footer.setText(f"Salvo no perfil local ({exc})")

    # ------------------------------------------------------------------
    # Handlers de Eventos da Interface
    # ------------------------------------------------------------------
    def _on_profile_changed(self, idx: int) -> None:
        self.store.active_profile = idx
        self.cfg = self.store.profiles[idx]
        self.selected_dpi_stage = self.cfg.active_dpi_stage
        self._sync_ui_from_cfg()
        self._hw_apply(lambda m: m.apply_full_config(self.cfg), f"Perfil {idx + 1} ativado e enviado ao mouse.")

    def _open_button_dialog(self, btn_idx: int) -> None:
        dlg = ButtonConfigDialog(
            btn_idx,
            self.cfg.buttons[btn_idx],
            self.store.macros,
            lang=self.store.language,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.result_mapping:
            return

        t, p1, p2, sc_buf, lbl = dlg.result_mapping

        # Proteção idêntica ao Windows: obriga manter pelo menos 1 botão com Clique Esquerdo (0x01, 0x01)
        if not (t == 0x01 and p1 == 0x01):
            other_left = any(
                i != btn_idx and b.action_type == 0x01 and b.param1 == 0x01
                for i, b in enumerate(self.cfg.buttons)
            )
            if not other_left:
                QMessageBox.warning(
                    self,
                    "Ação Bloqueada",
                    "É obrigatório manter pelo menos um botão configurado como Clique Esquerdo!",
                )
                return

        self.cfg.buttons[btn_idx] = ButtonMapping(
            index=btn_idx,
            action_type=t,
            param1=p1,
            param2=p2,
            label=lbl,
        )
        self._sync_ui_from_cfg()
        self._hw_apply(
            lambda m: m.set_button_mapping(btn_idx, t, p1, p2, sc_buf),
            f"Botão #{btn_idx + 1} configurado para '{lbl}'.",
        )

    def _on_debounce_changed(self, ms: int) -> None:
        self.cfg.debounce_ms = ms
        self._hw_apply(lambda m: m.set_debounce(ms), f"Debounce ajustado para {ms} ms.")

    def _on_max_stages_changed(self, count: int) -> None:
        self.cfg.max_dpi_stages = count
        if self.cfg.active_dpi_stage >= count:
            self.cfg.active_dpi_stage = count - 1
        if self.selected_dpi_stage >= count:
            self.selected_dpi_stage = count - 1
        self._sync_ui_from_cfg()
        self._hw_apply(lambda m: m.set_max_dpi_stages(count), f"Estágios de DPI ativos: {count}.")

    def _on_select_dpi_stage(self, stage: int) -> None:
        self.selected_dpi_stage = stage
        self.cfg.active_dpi_stage = stage
        self._sync_ui_from_cfg()
        self._hw_apply(
            lambda m: m.set_active_dpi_stage(stage),
            f"Estágio DPI #{stage + 1} ({self.cfg.dpi_stages[stage].dpi_x} DPI) ativado.",
        )

    def _on_dpi_slider_moved(self, step_val: int) -> None:
        dpi = step_val * 50
        self.spin_dpi_val.blockSignals(True)
        self.spin_dpi_val.setValue(dpi)
        self.spin_dpi_val.blockSignals(False)
        st = self.cfg.dpi_stages[self.selected_dpi_stage]
        st.dpi_x = dpi
        st.dpi_y = dpi
        self._refresh_dpi_stage_cards()

    def _on_dpi_spin_changed(self, dpi: int) -> None:
        dpi = max(50, min(26000, (dpi // 50) * 50))
        self.slider_dpi.blockSignals(True)
        self.slider_dpi.setValue(dpi // 50)
        self.slider_dpi.blockSignals(False)
        st = self.cfg.dpi_stages[self.selected_dpi_stage]
        st.dpi_x = dpi
        st.dpi_y = dpi
        self._refresh_dpi_stage_cards()
        self._commit_current_dpi_stage()

    def _commit_current_dpi_stage(self) -> None:
        st = self.cfg.dpi_stages[self.selected_dpi_stage]
        self._hw_apply(
            lambda m: m.set_dpi(st.index, st.dpi_x, st.dpi_y, st.color),
            f"DPI do estágio #{st.index + 1} definido para {st.dpi_x} DPI.",
        )

    def _pick_stage_color(self) -> None:
        st = self.cfg.dpi_stages[self.selected_dpi_stage]
        col = QColorDialog.getColor(QColor(*st.color), self, "Escolher Cor do Estágio DPI")
        if not col.isValid():
            return
        st.color = (col.red(), col.green(), col.blue())
        self._refresh_dpi_stage_cards()
        self._commit_current_dpi_stage()

    def _on_polling_rate_clicked(self, hz: int) -> None:
        self.cfg.polling_rate_hz = hz
        self._sync_ui_from_cfg()
        self._hw_apply(lambda m: m.set_polling_rate(hz), f"Polling Rate definido para {hz} Hz.")

    def _on_dpi_led_changed(self) -> None:
        self.cfg.dpi_led_mode = self.combo_dpi_led_mode.currentIndex()
        self.cfg.dpi_led_brightness = self.spin_dpi_led_bright.value()
        self.cfg.dpi_led_speed = self.spin_dpi_led_speed.value()
        self._hw_apply(
            lambda m: m.set_dpi_led(
                self.cfg.dpi_led_mode, self.cfg.dpi_led_brightness, self.cfg.dpi_led_speed
            ),
            "Iluminação do indicador DPI atualizada.",
        )

    def _on_lod_changed(self, idx: int) -> None:
        mm = 2 if idx == 1 else 1
        self.cfg.lod_mm = mm
        self._hw_apply(lambda m: m.set_lod(mm), f"LOD ajustado para {mm} mm.")

    def _on_sensor_mode_changed(self) -> None:
        mode = self.combo_sensor_mode.currentIndex()
        p_idx = self.combo_perf_time.currentIndex()
        p_code = PERFORMANCE_TIME_OPTIONS[p_idx][0]
        self.cfg.sensor_mode = mode
        self.cfg.performance_time = p_code
        self._hw_apply(
            lambda m: m.set_sensor_mode(mode, p_code),
            "Modo de operação do sensor atualizado.",
        )

    def _on_motion_sync_toggled(self, state: bool) -> None:
        self.cfg.motion_sync = state
        self._hw_apply(
            lambda m: m.set_motion_sync(state),
            f"Motion Sync {'ativado' if state else 'desativado'}.",
        )

    def _on_angle_snap_toggled(self, state: bool) -> None:
        self.cfg.angle_snapping = state
        self._hw_apply(
            lambda m: m.set_angle_snapping(state),
            f"Angle Snapping {'ativado' if state else 'desativado'}.",
        )

    def _on_ripple_toggled(self, state: bool) -> None:
        self.cfg.ripple_control = state
        self._hw_apply(
            lambda m: m.set_ripple_control(state),
            f"Ripple Control {'ativado' if state else 'desativado'}.",
        )

    # ------------------------------------------------------------------
    # Macros
    # ------------------------------------------------------------------
    def _refresh_macro_list(self) -> None:
        cur = self.list_macros.currentRow()
        self.list_macros.blockSignals(True)
        self.list_macros.clear()
        for m in self.store.macros:
            self.list_macros.addItem(m.name)
        if self.store.macros:
            sel = max(0, min(cur, len(self.store.macros) - 1))
            self.list_macros.setCurrentRow(sel)
        self.list_macros.blockSignals(False)
        self._on_macro_selected(self.list_macros.currentRow())

    def _on_macro_selected(self, row: int) -> None:
        self.list_macro_steps.clear()
        if row < 0 or row >= len(self.store.macros):
            return
        m = self.store.macros[row]
        for idx, s in enumerate(m.steps):
            act = "⬇ Apertar" if s.action == "press" else "⬆ Soltar"
            self.list_macro_steps.addItem(f"{idx + 1:02d}. {act} [{s.key}]  (+{s.delay_ms} ms)")

    def _create_new_macro(self) -> None:
        if len(self.store.macros) >= 16:
            QMessageBox.warning(self, "Limite", "Máximo de 16 macros suportado.")
            return
        name, ok = QInputDialog.getText(self, "Nova Macro", "Nome da Macro:")
        if not ok or not name.strip():
            return
        name = name.strip()
        if any(m.name == name for m in self.store.macros):
            QMessageBox.warning(self, "Aviso", "O nome escolhido da macro já está sendo utilizado.")
            return
        self.store.macros.append(MacroDefinition(name=name))
        self.store.save()
        self._refresh_macro_list()
        self.list_macros.setCurrentRow(len(self.store.macros) - 1)

    def _delete_selected_macro(self) -> None:
        row = self.list_macros.currentRow()
        if row < 0 or row >= len(self.store.macros):
            return
        del self.store.macros[row]
        self.store.save()
        self._refresh_macro_list()

    def _toggle_macro_recording(self) -> None:
        row = self.list_macros.currentRow()
        if row < 0 or row >= len(self.store.macros):
            QMessageBox.warning(self, "Aviso", "Por favor, primeiro crie ou selecione uma Macro.")
            return
        self.recording_macro = not self.recording_macro
        if self.recording_macro:
            self.last_record_ts = time.monotonic()
            self.btn_record_macro.setText("⏹ Parar a Gravação (Pressione teclas...)")
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.setFocus()
        else:
            self.btn_record_macro.setText("⏺ Começar a Gravar")
            self.store.save()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.recording_macro and not event.isAutoRepeat():
            self._record_key_event(event.key(), "press")
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if self.recording_macro and not event.isAutoRepeat():
            self._record_key_event(event.key(), "release")
            event.accept()
            return
        super().keyReleaseEvent(event)

    def _record_key_event(self, qt_key: int, action: str) -> None:
        row = self.list_macros.currentRow()
        if row < 0 or row >= len(self.store.macros):
            return
        key_name = QT_KEY_TO_HID_NAME.get(qt_key)
        if not key_name:
            return
        m = self.store.macros[row]
        if len(m.steps) >= 70:
            self._toggle_macro_recording()
            QMessageBox.warning(self, "Limite", "Limite de 70 eventos da macro atingido.")
            return
        now = time.monotonic()
        if self.chk_auto_delay.isChecked():
            delay = max(5, min(5000, int((now - self.last_record_ts) * 1000)))
        else:
            delay = self.spin_default_delay.value()
        self.last_record_ts = now
        m.steps.append(MacroStep(action=action, key=key_name, delay_ms=delay))
        self._on_macro_selected(row)

    def _insert_manual_macro_key(self) -> None:
        row = self.list_macros.currentRow()
        if row < 0 or row >= len(self.store.macros):
            QMessageBox.warning(self, "Aviso", "Por favor, primeiro crie ou selecione uma Macro.")
            return
        m = self.store.macros[row]
        if len(m.steps) + 2 > 70:
            QMessageBox.warning(self, "Limite", "Limite de teclas da macro atingido.")
            return
        key = self.combo_manual_key.currentText()
        d = self.spin_default_delay.value()
        m.steps.append(MacroStep(action="press", key=key, delay_ms=d))
        m.steps.append(MacroStep(action="release", key=key, delay_ms=d))
        self.store.save()
        self._on_macro_selected(row)

    def _edit_macro_step_delay(self) -> None:
        m_row = self.list_macros.currentRow()
        s_row = self.list_macro_steps.currentRow()
        if m_row < 0 or s_row < 0:
            return
        step = self.store.macros[m_row].steps[s_row]
        val, ok = QInputDialog.getInt(
            self, "Atraso (Delay)", "Tempo de atraso (ms):", step.delay_ms, 1, 10000
        )
        if ok:
            step.delay_ms = val
            self.store.save()
            self._on_macro_selected(m_row)

    def _delete_macro_step(self) -> None:
        m_row = self.list_macros.currentRow()
        s_row = self.list_macro_steps.currentRow()
        if m_row < 0 or s_row < 0:
            return
        del self.store.macros[m_row].steps[s_row]
        self.store.save()
        self._on_macro_selected(m_row)

    def _save_current_macro_to_hw(self) -> None:
        row = self.list_macros.currentRow()
        if row < 0 or row >= len(self.store.macros):
            return
        if self.recording_macro:
            self._toggle_macro_recording()
        macro = self.store.macros[row]
        if self.rad_rep_loose.isChecked():
            macro.repeat_mode = 0xFE
        elif self.rad_rep_click.isChecked():
            macro.repeat_mode = 0xFF
        else:
            macro.repeat_mode = max(1, self.spin_macro_repeats.value())
        self._hw_apply(
            lambda m: m.write_macro(row, macro),
            f"Macro '{macro.name}' gravada na memória do mouse.",
        )

    # ------------------------------------------------------------------
    # Iluminação & Configurações
    # ------------------------------------------------------------------
    def _set_rgb_spins(self, r: int, g: int, b: int) -> None:
        self.spin_r.setValue(r)
        self.spin_g.setValue(g)
        self.spin_b.setValue(b)

    def _pick_light_color_dialog(self) -> None:
        col = QColorDialog.getColor(
            QColor(self.spin_r.value(), self.spin_g.value(), self.spin_b.value()),
            self,
            "Selecionar Cor RGB",
        )
        if col.isValid():
            self._set_rgb_spins(col.red(), col.green(), col.blue())

    def _update_light_preview(self) -> None:
        r, g, b = self.spin_r.value(), self.spin_g.value(), self.spin_b.value()
        self.lbl_color_preview.setStyleSheet(
            f"background-color: rgb({r},{g},{b}); border: 2px solid #ffffff; border-radius: 8px;"
        )

    def _apply_light_settings(self) -> None:
        self.cfg.light.mode = self.combo_light_mode.currentIndex()
        self.cfg.light.brightness = self.spin_light_bright.value()
        self.cfg.light.speed = self.spin_light_speed.value()
        self.cfg.light.moving_off = self.chk_moving_off.isChecked()
        self.cfg.light.r = self.spin_r.value()
        self.cfg.light.g = self.spin_g.value()
        self.cfg.light.b = self.spin_b.value()
        s_idx = self.combo_light_sleep.currentIndex()
        self.cfg.sleep_code = SLEEP_TIME_OPTIONS[s_idx][0]
        self.combo_sleep_setting.blockSignals(True)
        self.combo_sleep_setting.setCurrentIndex(s_idx)
        self.combo_sleep_setting.blockSignals(False)

        self._hw_apply(
            lambda m: (m.set_light(self.cfg.light), m.set_sleep_time(self.cfg.sleep_code)),
            "Configurações de iluminação aplicadas ao mouse.",
        )

    def _on_sleep_setting_changed(self, idx: int) -> None:
        code = SLEEP_TIME_OPTIONS[idx][0]
        self.cfg.sleep_code = code
        self.combo_light_sleep.blockSignals(True)
        self.combo_light_sleep.setCurrentIndex(idx)
        self.combo_light_sleep.blockSignals(False)
        self._hw_apply(
            lambda m: m.set_sleep_time(code),
            f"Tempo de espera ajustado para {SLEEP_TIME_OPTIONS[idx][1]}.",
        )

    def _on_long_range_toggled(self, enabled: bool) -> None:
        self._hw_apply(
            lambda m: m.set_long_range_mode(enabled),
            f"Modo de longa distância {'ativado' if enabled else 'desativado'}.",
        )

    def _on_dongle_led_changed(self, mode: int) -> None:
        self._hw_apply(
            lambda m: m.set_dongle_rgb_mode(mode),
            "Modo do LED do receptor atualizado.",
        )

    # ------------------------------------------------------------------
    # Importar / Exportar / Reset / udev
    # ------------------------------------------------------------------
    def _import_profile_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Importar Configuração", "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            self.cfg = self.store.import_profile(self.store.active_profile, path)
            self._sync_ui_from_cfg()
            self._hw_apply(
                lambda m: m.apply_full_config(self.cfg),
                "Configuração importada e aplicada com sucesso.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao Importar", str(exc))

    def _export_profile_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar Configuração",
            f"fallen-lobo-perfil-{self.store.active_profile + 1}.json",
            "JSON (*.json)",
        )
        if not path:
            return
        self.store.export_profile(self.store.active_profile, path)
        self.lbl_status_footer.setText(f"✓ Perfil exportado para {path}")

    def _reset_current_profile(self) -> None:
        ans = QMessageBox.question(
            self,
            "Restaurar Configuração",
            "Tem certeza que deseja restaurar o perfil atual para o padrão de fábrica?",
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.cfg = MouseConfig.default()
        self.store.profiles[self.store.active_profile] = self.cfg
        self.selected_dpi_stage = self.cfg.active_dpi_stage
        self._sync_ui_from_cfg()
        self._hw_apply(
            lambda m: m.apply_full_config(self.cfg),
            "Perfil restaurado para os padrões de fábrica.",
        )

    def _factory_reset_mouse(self) -> None:
        ans = QMessageBox.question(
            self,
            "Restauração de Fábrica",
            "Tem certeza que deseja limpar a memória interna do mouse e restaurar tudo ao padrão?",
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.cfg = MouseConfig.default()
        self.store.profiles[self.store.active_profile] = self.cfg
        self._sync_ui_from_cfg()
        self._hw_apply(
            lambda m: (m.factory_reset(), m.apply_full_config(self.cfg)),
            "Memória interna do mouse restaurada para o padrão de fábrica.",
        )

    def _install_udev_pkexec(self) -> None:
        rule_content = (
            'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="3554", ATTRS{idProduct}=="f53c", MODE="0666", TAG+="uaccess"\n'
            'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="3554", ATTRS{idProduct}=="f511", MODE="0666", TAG+="uaccess"\n'
        )
        cmd = (
            f"printf %s '{rule_content}' > /etc/udev/rules.d/70-fallen-lobo-wireless.rules && "
            "udevadm control --reload-rules && "
            "udevadm trigger --subsystem-match=hidraw && "
            "chmod 0666 /dev/hidraw* 2>/dev/null || true"
        )
        try:
            res = subprocess.run(["pkexec", "bash", "-c", cmd], check=False)
            if res.returncode == 0:
                self.refresh_device_status(sync_from_hw=True)
                QMessageBox.information(
                    self,
                    "Permissão Configurada",
                    "Regra udev instalada com sucesso! O mouse já está acessível.",
                )
        except FileNotFoundError:
            QMessageBox.warning(
                self,
                "pkexec não encontrado",
                "Execute ~/fallen-lobo-driver/install.sh no terminal com sudo.",
            )


def main() -> int:
    ensure_desktop_integration()
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        libc.prctl(15, b"fallen-lobo", 0, 0, 0)
    except Exception:
        pass

    sys.argv[0] = APP_ID
    app = QApplication(sys.argv)
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName("Fallen Lobo Wireless")
    app.setOrganizationName("FallenGear")
    app.setDesktopFileName(APP_ID)
    if os.path.exists(APP_ICON_PATH):
        app.setWindowIcon(QIcon(APP_ICON_PATH))
    app.setStyleSheet(GLOBAL_QSS)
    win = FallenLoboMainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
