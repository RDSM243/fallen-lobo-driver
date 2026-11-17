"""Complete Linux userspace HID driver for the Fallen Lobo Wireless (Compx 3554:F53C / 3554:F511)."""

from __future__ import annotations

import glob
import json
import os
import select
from dataclasses import asdict, dataclass, field
from typing import Optional

VENDOR_ID = 0x3554
PIDS = {
    0xF53C: "2.4GHz Wireless",
    0xF511: "USB-C Com Fio",
}

REPORT_ID = 0x08
PACKET_SIZE = 17
FLASH_CHUNK_SIZE = 10

CMD_IS_ONLINE = 0x03
CMD_BATTERY = 0x04
CMD_WRITE_FLASH = 0x07
CMD_READ_FLASH = 0x08
CMD_CLEAR_SETTING = 0x09
CMD_VERSION = 0x12
CMD_SET_4K_RGB = 0x14
CMD_GET_4K_RGB = 0x15
CMD_SET_LONG_RANGE = 0x16
CMD_GET_LONG_RANGE = 0x17
CMD_SET_DONGLE_RGB_MODE = 0x18
CMD_SLAVE_VERSION = 0xB3

POLLING_RATE_TO_CODE = {
    125: 0x08,
    250: 0x04,
    500: 0x02,
    1000: 0x01,
    2000: 0x10,
    4000: 0x20,
    8000: 0x40,
}
CODE_TO_POLLING_RATE = {v: k for k, v in POLLING_RATE_TO_CODE.items()}

SLEEP_TIME_OPTIONS: list[tuple[int, str, str]] = [
    (1, "10 segundos", "10 seconds"),
    (3, "30 segundos", "30 seconds"),
    (6, "1 minuto", "1 minute"),
    (30, "5 minutos", "5 minutes"),
    (60, "10 minutos", "10 minutes"),
    (90, "15 minutos", "15 minutes"),
    (120, "20 minutos", "20 minutes"),
    (150, "25 minutos", "25 minutes"),
    (180, "30 minutos", "30 minutes"),
    (210, "35 minutos", "35 minutes"),
    (240, "40 minutos", "40 minutes"),
]

PERFORMANCE_TIME_OPTIONS: list[tuple[int, str, str]] = [
    (3, "30 Segundos", "30 Seconds"),
    (6, "1 Minuto", "1 Minute"),
    (12, "2 Minutos", "2 Minutes"),
    (30, "5 Minutos", "5 Minutes"),
    (60, "10 Minutos", "10 Minutes"),
    (90, "15 Minutos", "15 Minutes"),
]

# Fallen Lobo Wireless voltage curve in mV (0% to 100% in 5% steps, from Config.ini)
BATTERY_MV_CURVE = [
    3050, 3170, 3230, 3300, 3600, 3660, 3720, 3760, 3800, 3840, 3880,
    3920, 3940, 3960, 3980, 4000, 4020, 4040, 4060, 4080, 4110,
]

DEFAULT_DPI_STAGES = [
    (400, 400, (255, 0, 0)),
    (800, 800, (0, 0, 255)),
    (1600, 1600, (0, 255, 0)),
    (3200, 3200, (255, 255, 0)),
    (6400, 6400, (0, 255, 255)),
    (26000, 26000, (170, 255, 255)),
    (6000, 6000, (0, 255, 255)),
    (8000, 8000, (255, 255, 255)),
]

# Default 6 button mappings on Fallen Lobo Wireless:
# 1: Left Click, 2: Right Click, 3: Middle Click, 4: Forward, 5: Back, 6: DPI Loop
DEFAULT_BUTTONS = [
    (0x01, 0x01, 0x00, "Clique esquerdo"),
    (0x01, 0x02, 0x00, "Clique Direito"),
    (0x01, 0x04, 0x00, "Clique do Scroll"),
    (0x01, 0x10, 0x00, "Avançar"),
    (0x01, 0x08, 0x00, "Recuar"),
    (0x02, 0x01, 0x00, "Loop de DPI"),
]

# Multimedia / Consumer Control codes from HIDUsb.dll & Software Mouse Lobo.exe
MULTIMEDIA_ACTIONS: dict[str, tuple[str, str, int]] = {
    "media_player": ("Media Player", "Media Player", 0x0183),
    "play_pause": ("Tocar/Pausar", "Play/Pause", 0x00CD),
    "next_track": ("Próxima Música", "Next Track", 0x00B5),
    "prev_track": ("Música Anterior", "Previous Track", 0x00B6),
    "stop": ("Parar", "Stop", 0x00B7),
    "mute": ("Silenciar", "Mute", 0x00E2),
    "vol_up": ("Aumentar o volume", "Volume Up", 0x00E9),
    "vol_down": ("Diminuir o volume", "Volume Down", 0x00EA),
    "email": ("E-mail", "Email", 0x018A),
    "calculator": ("Calculadora", "Calculator", 0x0192),
    "my_computer": ("Meu computador", "My Computer", 0x0194),
    "search": ("Pesquisa", "Search", 0x0221),
    "home": ("Página Inicial", "Browser Home", 0x0223),
    "browser_back": ("Voltar página", "Browser Back", 0x0224),
    "browser_forward": ("Avançar página", "Browser Forward", 0x0225),
    "browser_stop": ("Parar carregamento", "Browser Stop", 0x0226),
    "browser_refresh": ("Atualizar página", "Browser Refresh", 0x0227),
    "favorites": ("Favoritos", "Favorites", 0x022A),
}

# Standard USB HID Keyboard scan codes
HID_KEYCODES: dict[str, int] = {
    "A": 0x04, "B": 0x05, "C": 0x06, "D": 0x07, "E": 0x08, "F": 0x09,
    "G": 0x0A, "H": 0x0B, "I": 0x0C, "J": 0x0D, "K": 0x0E, "L": 0x0F,
    "M": 0x10, "N": 0x11, "O": 0x12, "P": 0x13, "Q": 0x14, "R": 0x15,
    "S": 0x16, "T": 0x17, "U": 0x18, "V": 0x19, "W": 0x1A, "X": 0x1B,
    "Y": 0x1C, "Z": 0x1D,
    "1": 0x1E, "2": 0x1F, "3": 0x20, "4": 0x21, "5": 0x22,
    "6": 0x23, "7": 0x24, "8": 0x25, "9": 0x26, "0": 0x27,
    "Enter": 0x28, "Esc": 0x29, "Backspace": 0x2A, "Tab": 0x2B, "Space": 0x2C,
    "-": 0x2D, "=": 0x2E, "[": 0x2F, "]": 0x30, "\\": 0x31, ";": 0x33,
    "'": 0x34, "`": 0x35, ",": 0x36, ".": 0x37, "/": 0x38, "CapsLock": 0x39,
    "F1": 0x3A, "F2": 0x3B, "F3": 0x3C, "F4": 0x3D, "F5": 0x3E, "F6": 0x3F,
    "F7": 0x40, "F8": 0x41, "F9": 0x42, "F10": 0x43, "F11": 0x44, "F12": 0x45,
    "PrintScreen": 0x46, "ScrollLock": 0x47, "Pause": 0x48,
    "Insert": 0x49, "Home": 0x4A, "PageUp": 0x4B, "Delete": 0x4C, "End": 0x4D, "PageDown": 0x4E,
    "Right": 0x4F, "Left": 0x50, "Down": 0x51, "Up": 0x52,
    "Ctrl": 0xE0, "Shift": 0xE1, "Alt": 0xE2, "Win": 0xE3,
}
CODE_TO_HID_KEY = {v: k for k, v in HID_KEYCODES.items()}

# Vendor HID descriptor signature: Usage Page 0xFF02, Usage 0x02, Report ID 0x08
_VENDOR_DESC_MARKER = bytes.fromhex("0602ff0902a1018508")


class LoboDriverError(RuntimeError):
    """Raised when communication with the mouse fails."""


@dataclass
class DeviceInfo:
    hidraw_path: str
    pid: int
    mode: str
    name: str
    accessible: bool = True


@dataclass
class BatteryInfo:
    raw_level: int
    charging: bool
    voltage_mv: int
    percent: int


@dataclass
class DpiStage:
    index: int
    dpi_x: int
    dpi_y: int
    color: tuple[int, int, int]


@dataclass
class ButtonMapping:
    index: int
    action_type: int
    param1: int
    param2: int
    label: str = ""


@dataclass
class LightConfig:
    mode: int = 1        # 0=Off, 1=Rainbow Flow, 2=Single Breath, 3=Steady Rainbow, 4=Neon, 5=Multi Breath, 6=Steady
    r: int = 255
    g: int = 224
    b: int = 0
    speed: int = 8       # 1..10
    brightness: int = 9  # 1..10
    enable: int = 1
    moving_off: bool = False


@dataclass
class MacroStep:
    action: str          # "press", "release"
    key: str             # Key name from HID_KEYCODES
    delay_ms: int = 10


@dataclass
class MacroDefinition:
    name: str
    repeat_mode: int = 1   # 1=N times, 0xFE=Until release, 0xFF=Until click
    repeat_count: int = 1
    steps: list[MacroStep] = field(default_factory=list)


@dataclass
class MouseConfig:
    polling_rate_hz: int = 1000
    max_dpi_stages: int = 5
    active_dpi_stage: int = 1
    lod_mm: int = 1
    debounce_ms: int = 8
    motion_sync: bool = True
    sleep_code: int = 6
    ripple_control: bool = False
    angle_snapping: bool = False
    sensor_mode: int = 0         # 0=LP, 1=HP, 2=Corded/Full Performance
    performance_time: int = 6    # in 10s units
    dpi_led_mode: int = 2        # 0=Off, 1=Steady, 2=Breathing
    dpi_led_brightness: int = 128
    dpi_led_speed: int = 3
    dpi_stages: list[DpiStage] = field(default_factory=list)
    buttons: list[ButtonMapping] = field(default_factory=list)
    light: LightConfig = field(default_factory=LightConfig)

    @classmethod
    def default(cls) -> "MouseConfig":
        stages = [
            DpiStage(index=i, dpi_x=dx, dpi_y=dy, color=col)
            for i, (dx, dy, col) in enumerate(DEFAULT_DPI_STAGES)
        ]
        buttons = [
            ButtonMapping(index=i, action_type=t, param1=p1, param2=p2, label=lbl)
            for i, (t, p1, p2, lbl) in enumerate(DEFAULT_BUTTONS)
        ]
        return cls(dpi_stages=stages, buttons=buttons)


def compx_checksum(data: bytes | bytearray) -> int:
    """Compute Compx 8-bit checksum: (0x55 - sum(bytes)) & 0xFF."""
    return (0x55 - (sum(data) & 0xFF)) & 0xFF


def _valid_field(buf: bytes, offset: int, length: int) -> bool:
    """Return True if buf[offset:offset+length] matches its trailing checksum byte."""
    if offset + length >= len(buf):
        return False
    return compx_checksum(buf[offset : offset + length]) == buf[offset + length]


def _pack_field(data: bytes) -> bytes:
    """Append the Compx checksum byte to a Flash field payload."""
    return data + bytes([compx_checksum(data)])


def encode_dpi_3395(dpi_x: int, dpi_y: int) -> bytes:
    """Encode PAW3395 X/Y DPI (50..26000, step 50) into 3 payload bytes."""
    dpi_x = max(50, min(26000, (dpi_x // 50) * 50))
    dpi_y = max(50, min(26000, (dpi_y // 50) * 50))
    rx = (dpi_x // 50) - 1
    ry = (dpi_y // 50) - 1
    hi = ((rx >> 8) & 0x03) << 2 | ((ry >> 8) & 0x03) << 6
    return bytes([rx & 0xFF, ry & 0xFF, hi])


def decode_dpi_3395(b0: int, b1: int, b2: int) -> tuple[int, int]:
    """Decode 3 Flash bytes into PAW3395 (dpi_x, dpi_y)."""
    rx = b0 | (((b2 >> 2) & 0x03) << 8)
    ry = b1 | (((b2 >> 6) & 0x03) << 8)
    dx = max(50, min(26000, (rx + 1) * 50))
    dy = max(50, min(26000, (ry + 1) * 50))
    return dx, dy


def encode_multimedia_buffer(consumer_code: int) -> bytes:
    """Format a 32-byte ShortcutKey Flash block for a 16-bit Consumer Control usage."""
    lo = consumer_code & 0xFF
    hi = (consumer_code >> 8) & 0xFF
    payload = bytes([
        0x02,               # 2 events (press + release)
        0x82, lo, hi,       # Press Consumer Control
        0x42, lo, hi,       # Release Consumer Control
    ])
    buf = bytearray(32)
    buf[:len(payload)] = payload
    buf[len(payload)] = compx_checksum(payload)
    return bytes(buf)


def encode_shortcut_buffer(modifiers: list[str], key: str) -> bytes:
    """Format a 32-byte ShortcutKey Flash block for up to 2 modifiers + 1 key."""
    keys = [m for m in modifiers if m in HID_KEYCODES][:2]
    if key in HID_KEYCODES and key not in keys:
        keys.append(key)
    if not keys:
        keys = ["A"]

    events = bytearray([len(keys) * 2])
    for k in keys:
        code = HID_KEYCODES[k]
        events.extend([0x81, code, 0x00])
    for k in reversed(keys):
        code = HID_KEYCODES[k]
        events.extend([0x41, code, 0x00])

    buf = bytearray(32)
    buf[:len(events)] = events
    buf[len(events)] = compx_checksum(events)
    return bytes(buf)


def encode_macro_buffer(macro: MacroDefinition) -> bytes:
    """Format a 384-byte (0x180) MacroKey Flash block matching MacroKeyToBuffer in HIDUsb.dll."""
    buf = bytearray(0x180)
    name_bytes = macro.name.encode("utf-8")[:30]
    buf[0] = len(name_bytes)
    buf[1 : 1 + len(name_bytes)] = name_bytes

    steps = macro.steps[:70]
    count = len(steps)
    buf[0x1F] = count

    pos = 0x20
    for step in steps:
        flag = 0x80 if step.action == "press" else 0x40
        code = HID_KEYCODES.get(step.key, 0x04)
        delay = max(1, min(65535, step.delay_ms))
        buf[pos] = flag | 0x01
        buf[pos + 1] = code & 0xFF
        buf[pos + 2] = 0x00
        buf[pos + 3] = (delay >> 8) & 0xFF
        buf[pos + 4] = delay & 0xFF
        pos += 5

    # Checksum from 0x1F to 0x20 + count * 5
    csum_end = 0x20 + count * 5
    buf[csum_end] = compx_checksum(buf[0x1F:csum_end])
    return bytes(buf)


def describe_button_mapping(action_type: int, p1: int, p2: int, lang: str = "pt") -> str:
    """Return a human-readable label for a 3-byte KeyFunMap entry."""
    pt = lang == "pt"
    if action_type == 0x00:
        return "Desabilitar" if pt else "Disable"
    if action_type == 0x01:
        names_pt = {
            0x01: "Clique esquerdo",
            0x02: "Clique Direito",
            0x04: "Clique do Scroll",
            0x08: "Recuar",
            0x10: "Avançar",
        }
        names_en = {
            0x01: "Left Click",
            0x02: "Right Click",
            0x04: "Middle Click",
            0x08: "Back",
            0x10: "Forward",
        }
        return (names_pt if pt else names_en).get(p1, f"Mouse (0x{p1:02x})")
    if action_type == 0x02:
        if p1 == 0x01:
            return "Loop de DPI" if pt else "DPI Loop"
        if p1 == 0x02:
            return "DPI+"
        if p1 == 0x03:
            return "DPI-"
        return "Troca de DPI" if pt else "DPI Switch"
    if action_type == 0x03:
        if p1 == 0x01:
            return "Rolar para cima" if pt else "Scroll Up"
        if p1 == 0x02:
            return "Rolar para baixo" if pt else "Scroll Down"
        return "Scroll"
    if action_type == 0x04:
        return f"{'Tecla de disparo' if pt else 'Fire Key'} ({p1}ms x{p2})"
    if action_type == 0x05:
        return "Atalho / Multimídia" if pt else "Shortcut / Multimedia"
    if action_type == 0x06:
        return f"Macro #{p1 + 1}"
    if action_type == 0x07:
        return "Troca da Taxa de Atualização" if pt else "Polling Rate Switch"
    if action_type == 0x08:
        return "Luz ON/OFF" if pt else "Light ON/OFF"
    if action_type == 0x0A:
        dpi = ((p1 | (p2 << 8)) + 1) * 50
        return f"{'Trava de DPI' if pt else 'DPI Lock'} ({dpi})"
    return f"Custom (0x{action_type:02x}, 0x{p1:02x}, 0x{p2:02x})"


def voltage_to_percent(voltage_mv: int) -> int:
    """Interpolate battery percentage (0..100) from mV using Fallen's curve."""
    if voltage_mv <= BATTERY_MV_CURVE[0]:
        return 0
    if voltage_mv >= BATTERY_MV_CURVE[-1]:
        return 100
    for idx in range(len(BATTERY_MV_CURVE) - 1):
        lo, hi = BATTERY_MV_CURVE[idx], BATTERY_MV_CURVE[idx + 1]
        if lo <= voltage_mv <= hi:
            frac = (voltage_mv - lo) / (hi - lo)
            return round((idx + frac) * 5)
    return 100


def find_devices() -> list[DeviceInfo]:
    """Discover connected Fallen Lobo Wireless vendor hidraw interfaces."""
    devices: list[DeviceInfo] = []
    for sys_path in sorted(glob.glob("/sys/bus/hid/devices/0003:3554:*")):
        uevent_path = os.path.join(sys_path, "uevent")
        desc_path = os.path.join(sys_path, "report_descriptor")
        hidraw_glob = glob.glob(os.path.join(sys_path, "hidraw", "hidraw*"))
        if not hidraw_glob or not os.path.exists(desc_path):
            continue

        try:
            with open(desc_path, "rb") as f:
                desc = f.read()
        except OSError:
            continue
        if _VENDOR_DESC_MARKER not in desc:
            continue

        pid = 0
        name = "Compx Mouse Lobo Wireless"
        with open(uevent_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("HID_ID="):
                    parts = line.strip().split(":")
                    if len(parts) == 3:
                        pid = int(parts[2], 16)
                elif line.startswith("HID_NAME="):
                    name = line.strip().split("=", 1)[1]

        if pid not in PIDS:
            continue

        hidraw_path = f"/dev/{os.path.basename(hidraw_glob[0])}"
        accessible = os.access(hidraw_path, os.R_OK | os.W_OK)
        devices.append(
            DeviceInfo(
                hidraw_path=hidraw_path,
                pid=pid,
                mode=PIDS[pid],
                name=name,
                accessible=accessible,
            )
        )
    # Prefer wired mode if both dongle and USB-C cable are connected
    devices.sort(key=lambda d: (0 if d.pid == 0xF511 else 1))
    return devices


class LoboMouse:
    """HID interface to the Fallen Lobo Wireless mouse / 2.4GHz dongle."""

    def __init__(self, device: Optional[DeviceInfo] = None, timeout_s: float = 0.8):
        if device is None:
            found = find_devices()
            if not found:
                raise LoboDriverError(
                    "Fallen Lobo Wireless não encontrado (VID 3554, PID F53C/F511)."
                )
            device = found[0]
        self.device = device
        self.timeout_s = timeout_s
        try:
            self._fd = os.open(device.hidraw_path, os.O_RDWR | os.O_NONBLOCK)
        except PermissionError as exc:
            raise LoboDriverError(
                f"Sem permissão para abrir {device.hidraw_path}. "
                "Clique em 'Liberar Permissão USB (udev)' ou rode ./install.sh."
            ) from exc
        except OSError as exc:
            raise LoboDriverError(f"Falha ao abrir {device.hidraw_path}: {exc}") from exc

    def close(self) -> None:
        if getattr(self, "_fd", -1) >= 0:
            os.close(self._fd)
            self._fd = -1

    def __enter__(self) -> "LoboMouse":
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def _drain(self) -> None:
        """Discard any stale unread input reports before issuing a command."""
        while True:
            r, _, _ = select.select([self._fd], [], [], 0)
            if not r:
                break
            try:
                os.read(self._fd, 64)
            except BlockingIOError:
                break

    def _xfer(self, cmd: int, addr: int = 0, length: int = 0, payload: bytes = b"") -> bytes:
        """Send a 17-byte Compx command frame and wait for the matching 17-byte reply."""
        self._drain()
        buf = bytearray(PACKET_SIZE)
        buf[0] = REPORT_ID
        buf[1] = cmd & 0xFF
        buf[2] = 0x00
        buf[3] = (addr >> 8) & 0xFF
        buf[4] = addr & 0xFF
        buf[5] = length & 0xFF
        if payload:
            buf[6 : 6 + len(payload)] = payload[:10]
        buf[16] = compx_checksum(buf[:16])

        for _attempt in range(3):
            self._drain()
            os.write(self._fd, bytes(buf))

            ready, _, _ = select.select([self._fd], [], [], self.timeout_s)
            while ready:
                try:
                    resp = os.read(self._fd, PACKET_SIZE)
                except BlockingIOError:
                    break
                if len(resp) == PACKET_SIZE and resp[0] == REPORT_ID and resp[1] == (cmd & 0xFF):
                    return resp
                ready, _, _ = select.select([self._fd], [], [], self.timeout_s)

        raise LoboDriverError(f"Timeout aguardando resposta HID (cmd 0x{cmd:02x})")

    def is_online(self) -> bool:
        """Return True if the mouse is awake and reachable."""
        resp = self._xfer(CMD_IS_ONLINE)
        return resp[6] > 0

    def get_version(self) -> tuple[int, int]:
        """Return receiver/device firmware (major, minor) version tuple."""
        resp = self._xfer(CMD_VERSION)
        return resp[6], resp[7]

    def get_slave_version(self) -> tuple[int, int]:
        """Return mouse slave firmware (major, minor) version tuple."""
        try:
            resp = self._xfer(CMD_SLAVE_VERSION)
            return resp[6], resp[7]
        except LoboDriverError:
            return (1, 0)

    def get_battery(self) -> BatteryInfo:
        """Query battery level, charging state, and voltage in mV."""
        self.is_online()
        resp = self._xfer(CMD_BATTERY)
        raw_level = resp[6]
        charging = resp[7] != 0
        voltage_mv = (resp[8] << 8) | resp[9]
        if 1 <= raw_level <= 100:
            percent = raw_level
        elif 2800 <= voltage_mv <= 4400:
            percent = voltage_to_percent(voltage_mv)
        else:
            percent = 0
        return BatteryInfo(
            raw_level=raw_level,
            charging=charging,
            voltage_mv=voltage_mv,
            percent=percent,
        )

    def get_long_range_mode(self) -> bool:
        """Return True if long-range wireless mode is enabled."""
        try:
            resp = self._xfer(CMD_GET_LONG_RANGE)
            return resp[6] != 0
        except LoboDriverError:
            return False

    def set_long_range_mode(self, enabled: bool) -> None:
        """Enable or disable long-range wireless mode."""
        self._xfer(CMD_SET_LONG_RANGE, length=0x0A, payload=bytes([1 if enabled else 0]))

    def set_dongle_rgb_mode(self, mode: int) -> None:
        """Set receiver LED indicator mode (0=Polling Rate, 1=Battery State, 2=Low Battery Warning)."""
        payload = bytes([0x00, mode & 0xFF, 0x00, 0x00, 0x00, 0x00])
        self._xfer(CMD_SET_DONGLE_RGB_MODE, length=0x0A, payload=payload)

    def factory_reset(self) -> None:
        """Send hardware factory reset command (0x09) and restore default Flash settings."""
        self._xfer(CMD_CLEAR_SETTING)

    def read_flash(self, addr: int, length: int) -> bytes:
        """Read `length` bytes from mouse Flash starting at `addr`."""
        out = bytearray()
        offset = 0
        while offset < length:
            chunk = min(FLASH_CHUNK_SIZE, length - offset)
            resp = self._xfer(CMD_READ_FLASH, addr=addr + offset, length=chunk)
            out.extend(resp[6 : 6 + chunk])
            offset += chunk
        return bytes(out)

    def write_flash(self, addr: int, data: bytes) -> None:
        """Write `data` bytes to mouse Flash starting at `addr`."""
        offset = 0
        while offset < len(data):
            chunk = data[offset : offset + FLASH_CHUNK_SIZE]
            self._xfer(
                CMD_WRITE_FLASH,
                addr=addr + offset,
                length=len(chunk),
                payload=chunk,
            )
            offset += len(chunk)

    def get_config(self) -> MouseConfig:
        """Read and parse the complete mouse configuration block from Flash (0x00..0xBA)."""
        flash = self.read_flash(0x0000, 0xBC)
        cfg = MouseConfig.default()

        if _valid_field(flash, 0x00, 1):
            cfg.polling_rate_hz = CODE_TO_POLLING_RATE.get(flash[0x00], 1000)
        if _valid_field(flash, 0x02, 1) and 1 <= flash[0x02] <= 8:
            cfg.max_dpi_stages = flash[0x02]
        if _valid_field(flash, 0x04, 1) and 0 <= flash[0x04] < cfg.max_dpi_stages:
            cfg.active_dpi_stage = flash[0x04]
        if _valid_field(flash, 0x08, 1):
            cfg.lod_mm = 2 if flash[0x08] else 1

        if _valid_field(flash, 0x4C, 1):
            cfg.dpi_led_mode = flash[0x4C]
        if _valid_field(flash, 0x4E, 1):
            cfg.dpi_led_brightness = flash[0x4E]
        if _valid_field(flash, 0x50, 1):
            cfg.dpi_led_speed = flash[0x50]

        if _valid_field(flash, 0xA0, 6):
            cfg.light.mode = flash[0xA0]
            cfg.light.r = flash[0xA1]
            cfg.light.g = flash[0xA2]
            cfg.light.b = flash[0xA3]
            cfg.light.speed = flash[0xA4]
            cfg.light.brightness = flash[0xA5]
        if _valid_field(flash, 0xA7, 1):
            cfg.light.enable = flash[0xA7]

        if _valid_field(flash, 0xA9, 1):
            cfg.debounce_ms = flash[0xA9]
        if _valid_field(flash, 0xAB, 1):
            cfg.motion_sync = flash[0xAB] != 0
        if _valid_field(flash, 0xAD, 1):
            cfg.sleep_code = flash[0xAD]
        if _valid_field(flash, 0xAF, 1):
            cfg.ripple_control = flash[0xAF] != 0
        if _valid_field(flash, 0xB1, 1):
            cfg.angle_snapping = flash[0xB1] != 0
        if _valid_field(flash, 0xB5, 1):
            cfg.light.moving_off = flash[0xB5] != 0
        if _valid_field(flash, 0xB7, 1):
            cfg.performance_time = flash[0xB7]
        if _valid_field(flash, 0xB9, 1):
            cfg.sensor_mode = flash[0xB9]

        stages: list[DpiStage] = []
        for idx in range(8):
            dpi_off = 0x0C + idx * 4
            col_off = 0x2C + idx * 4
            default_dx, default_dy, default_col = DEFAULT_DPI_STAGES[idx]
            if _valid_field(flash, dpi_off, 3):
                dx, dy = decode_dpi_3395(flash[dpi_off], flash[dpi_off + 1], flash[dpi_off + 2])
            else:
                dx, dy = default_dx, default_dy
            if _valid_field(flash, col_off, 3):
                color = (flash[col_off], flash[col_off + 1], flash[col_off + 2])
            else:
                color = default_col
            stages.append(DpiStage(index=idx, dpi_x=dx, dpi_y=dy, color=color))
        cfg.dpi_stages = stages

        buttons: list[ButtonMapping] = []
        for idx in range(6):
            btn_off = 0x60 + idx * 4
            def_t, def_p1, def_p2, _ = DEFAULT_BUTTONS[idx]
            if _valid_field(flash, btn_off, 3):
                t, p1, p2 = flash[btn_off], flash[btn_off + 1], flash[btn_off + 2]
            else:
                t, p1, p2 = def_t, def_p1, def_p2
            buttons.append(
                ButtonMapping(
                    index=idx,
                    action_type=t,
                    param1=p1,
                    param2=p2,
                    label=describe_button_mapping(t, p1, p2),
                )
            )
        cfg.buttons = buttons
        return cfg

    def set_polling_rate(self, hz: int) -> None:
        if hz not in POLLING_RATE_TO_CODE:
            valid = ", ".join(str(k) for k in sorted(POLLING_RATE_TO_CODE))
            raise ValueError(f"Polling rate inválido ({hz}). Válidos: {valid}")
        self.write_flash(0x00, _pack_field(bytes([POLLING_RATE_TO_CODE[hz]])))

    def set_active_dpi_stage(self, stage: int) -> None:
        if not 0 <= stage <= 7:
            raise ValueError("Stage deve ser entre 0 e 7")
        self.write_flash(0x04, _pack_field(bytes([stage])))

    def set_max_dpi_stages(self, count: int) -> None:
        if not 1 <= count <= 8:
            raise ValueError("Quantidade de estágios DPI deve ser entre 1 e 8")
        self.write_flash(0x02, _pack_field(bytes([count])))

    def set_dpi(
        self,
        stage: int,
        dpi_x: int,
        dpi_y: Optional[int] = None,
        color: Optional[tuple[int, int, int]] = None,
    ) -> None:
        if not 0 <= stage <= 7:
            raise ValueError("Stage deve ser entre 0 e 7")
        if dpi_y is None:
            dpi_y = dpi_x
        self.write_flash(0x0C + stage * 4, _pack_field(encode_dpi_3395(dpi_x, dpi_y)))
        if color is not None:
            r, g, b = color
            self.write_flash(0x2C + stage * 4, _pack_field(bytes([r & 0xFF, g & 0xFF, b & 0xFF])))

    def set_dpi_led(self, mode: int, brightness: int = 128, speed: int = 3) -> None:
        self.write_flash(0x4C, _pack_field(bytes([mode & 0xFF])))
        self.write_flash(0x4E, _pack_field(bytes([brightness & 0xFF])))
        self.write_flash(0x50, _pack_field(bytes([speed & 0xFF])))
        self.write_flash(0x52, _pack_field(bytes([0 if mode == 0 else 1])))

    def set_button_mapping(
        self,
        button_index: int,
        action_type: int,
        param1: int = 0,
        param2: int = 0,
        shortcut_buf: Optional[bytes] = None,
    ) -> None:
        if not 0 <= button_index <= 15:
            raise ValueError("Índice de botão inválido")
        self.write_flash(
            0x60 + button_index * 4,
            _pack_field(bytes([action_type & 0xFF, param1 & 0xFF, param2 & 0xFF])),
        )
        if shortcut_buf is not None:
            self.write_flash(0x0100 + button_index * 0x20, shortcut_buf[:0x20])

    def write_macro(self, macro_index: int, macro: MacroDefinition) -> None:
        if not 0 <= macro_index <= 15:
            raise ValueError("Índice de macro deve ser entre 0 e 15")
        buf = encode_macro_buffer(macro)
        # Only need to write the active portion (header + steps + checksum)
        active_len = min(0x180, 0x20 + len(macro.steps[:70]) * 5 + 2)
        self.write_flash(0x0300 + macro_index * 0x180, buf[:active_len])

    def set_light(self, light: LightConfig) -> None:
        payload = bytes([
            light.mode & 0xFF,
            light.r & 0xFF,
            light.g & 0xFF,
            light.b & 0xFF,
            max(1, min(10, light.speed)) & 0xFF,
            max(1, min(10, light.brightness)) & 0xFF,
        ])
        self.write_flash(0xA0, _pack_field(payload))
        self.write_flash(0xA7, _pack_field(bytes([0 if light.mode == 0 else 1])))
        self.write_flash(0xB5, _pack_field(bytes([1 if light.moving_off else 0])))

    def set_lod(self, mm: int) -> None:
        if mm not in (1, 2):
            raise ValueError("LOD deve ser 1 ou 2 (mm)")
        self.write_flash(0x08, _pack_field(bytes([0 if mm == 1 else 1])))

    def set_debounce(self, ms: int) -> None:
        if not 0 <= ms <= 30:
            raise ValueError("Debounce deve ser entre 0 e 30 ms")
        self.write_flash(0xA9, _pack_field(bytes([ms])))

    def set_motion_sync(self, enabled: bool) -> None:
        self.write_flash(0xAB, _pack_field(bytes([1 if enabled else 0])))

    def set_sleep_time(self, code: int) -> None:
        self.write_flash(0xAD, _pack_field(bytes([code & 0xFF])))

    def set_ripple_control(self, enabled: bool) -> None:
        self.write_flash(0xAF, _pack_field(bytes([1 if enabled else 0])))

    def set_angle_snapping(self, enabled: bool) -> None:
        self.write_flash(0xB1, _pack_field(bytes([1 if enabled else 0])))

    def set_sensor_mode(self, mode: int, perf_time: int = 6) -> None:
        self.write_flash(0xB3, _pack_field(bytes([1 if mode == 2 else 0])))
        self.write_flash(0xB7, _pack_field(bytes([perf_time & 0xFF])))
        self.write_flash(0xB9, _pack_field(bytes([mode & 0xFF])))

    def apply_full_config(self, cfg: MouseConfig) -> None:
        """Write an entire MouseConfig profile to hardware Flash."""
        self.set_polling_rate(cfg.polling_rate_hz)
        self.set_max_dpi_stages(cfg.max_dpi_stages)
        self.set_active_dpi_stage(cfg.active_dpi_stage)
        self.set_lod(cfg.lod_mm)
        for s in cfg.dpi_stages:
            self.set_dpi(s.index, s.dpi_x, s.dpi_y, s.color)
        self.set_dpi_led(cfg.dpi_led_mode, cfg.dpi_led_brightness, cfg.dpi_led_speed)
        for b in cfg.buttons:
            self.set_button_mapping(b.index, b.action_type, b.param1, b.param2)
        self.set_light(cfg.light)
        self.set_debounce(cfg.debounce_ms)
        self.set_motion_sync(cfg.motion_sync)
        self.set_sleep_time(cfg.sleep_code)
        self.set_ripple_control(cfg.ripple_control)
        self.set_angle_snapping(cfg.angle_snapping)
        self.set_sensor_mode(cfg.sensor_mode, cfg.performance_time)


class ProfileStore:
    """Manage local profiles (1..4) and macro library in ~/.config/fallen-lobo-wireless/."""

    def __init__(self) -> None:
        cfg_dir = os.path.expanduser("~/.config/fallen-lobo-wireless")
        os.makedirs(cfg_dir, exist_ok=True)
        self.path = os.path.join(cfg_dir, "state.json")
        self.active_profile: int = 0
        self.language: str = "pt"
        self.profiles: list[MouseConfig] = [MouseConfig.default() for _ in range(4)]
        self.macros: list[MacroDefinition] = []
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self.active_profile = int(raw.get("active_profile", 0)) % 4
            self.language = raw.get("language", "pt")
            if "profiles" in raw and len(raw["profiles"]) == 4:
                self.profiles = [self._dict_to_cfg(d) for d in raw["profiles"]]
            if "macros" in raw:
                self.macros = [
                    MacroDefinition(
                        name=m["name"],
                        repeat_mode=m.get("repeat_mode", 1),
                        repeat_count=m.get("repeat_count", 1),
                        steps=[MacroStep(**s) for s in m.get("steps", [])],
                    )
                    for m in raw["macros"]
                ]
        except Exception:
            pass

    def save(self) -> None:
        data = {
            "active_profile": self.active_profile,
            "language": self.language,
            "profiles": [asdict(p) for p in self.profiles],
            "macros": [asdict(m) for m in self.macros],
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def export_profile(self, index: int, filepath: str) -> None:
        data = {
            "device": "Fallen Lobo Wireless",
            "profile": asdict(self.profiles[index]),
            "macros": [asdict(m) for m in self.macros],
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def import_profile(self, index: int, filepath: str) -> MouseConfig:
        with open(filepath, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if raw.get("device") != "Fallen Lobo Wireless" and "profile" not in raw:
            raise ValueError("Arquivo de configuração incompatível.")
        cfg = self._dict_to_cfg(raw["profile"])
        self.profiles[index] = cfg
        if "macros" in raw:
            self.macros = [
                MacroDefinition(
                    name=m["name"],
                    repeat_mode=m.get("repeat_mode", 1),
                    repeat_count=m.get("repeat_count", 1),
                    steps=[MacroStep(**s) for s in m.get("steps", [])],
                )
                for m in raw["macros"]
            ]
        self.save()
        return cfg

    @staticmethod
    def _dict_to_cfg(d: dict) -> MouseConfig:
        cfg = MouseConfig.default()
        for k in (
            "polling_rate_hz", "max_dpi_stages", "active_dpi_stage", "lod_mm",
            "debounce_ms", "motion_sync", "sleep_code", "ripple_control",
            "angle_snapping", "sensor_mode", "performance_time",
            "dpi_led_mode", "dpi_led_brightness", "dpi_led_speed",
        ):
            if k in d:
                setattr(cfg, k, d[k])
        if "dpi_stages" in d:
            cfg.dpi_stages = [
                DpiStage(
                    index=s["index"],
                    dpi_x=s["dpi_x"],
                    dpi_y=s["dpi_y"],
                    color=tuple(s["color"]),
                )
                for s in d["dpi_stages"]
            ]
        if "buttons" in d:
            cfg.buttons = [ButtonMapping(**b) for b in d["buttons"]]
        if "light" in d:
            cfg.light = LightConfig(**d["light"])
        return cfg
