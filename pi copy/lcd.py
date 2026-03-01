"""
pi/lcd.py — Grove LCD RGB Backlight V2.0 display driver.

Wraps the Grove LCD library into a clean, simple API so the rest of
the Pi code never thinks about I2C, cursors, or character limits.

The LCD is 16 characters wide × 2 lines tall.
Line 1: Coaching message    e.g. "SPEED IT UP!"
Line 2: Score bar           e.g. "████████░░  81%"

Hardware:
  Grove LCD RGB Backlight V2.0
  Connected to any I2C port on the Grove Base HAT.
  I2C addresses: 0x3E (LCD controller) and 0x62 (RGB backlight)
  Verify with: sudo i2cdetect -y 1

The backlight color changes with the coaching event:
  GOOD         → Green   (0, 255, 80)
  SPEED_UP     → Red     (255, 30, 0)
  VIBE_CHECK   → Orange  (255, 120, 0)
  RAISE_ENERGY → Red     (255, 30, 0)
  VISUAL_RESET → Blue    (0, 150, 255)
  IDLE / error → White   (255, 255, 255)
"""

import logging
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

LCD_WIDTH = 16  # Characters per line
LCD_LINES = 2   # Number of lines


# ─────────────────────────────────────────────
# BACKLIGHT COLOR MAP
# RGB tuples (0-255 each) for each event type.
# ─────────────────────────────────────────────

BACKLIGHT_COLORS: dict[str, Tuple[int, int, int]] = {
    "GOOD":         (0,   220, 80),    # Green
    "SPEED_UP":     (255, 30,  0),     # Red
    "VIBE_CHECK":   (255, 120, 0),     # Orange
    "RAISE_ENERGY": (255, 30,  0),     # Red
    "VISUAL_RESET": (0,   150, 255),   # Blue
    "IDLE":         (80,  80,  80),    # Dim white
    "ERROR":        (255, 0,   200),   # Magenta — something went wrong
    "STARTUP":      (0,   100, 255),   # Blue — booting up
}


# ─────────────────────────────────────────────
# GROVE LCD IMPORT WITH MOCK FALLBACK
# On the Pi: uses the real grove.display library.
# On a laptop: prints to terminal so you can test without hardware.
# ─────────────────────────────────────────────

try:
    from grove.display.jhd1802 import JHD1802
    _grove_available = True
    logger.info("Grove LCD library loaded.")
except ImportError:
    logger.warning("grove library not found — LCD output will print to terminal.")
    _grove_available = False


class MockLCD:
    """
    Prints LCD output to the terminal when running on a laptop.
    Simulates the 16x2 display in ASCII so you can see exactly
    what would appear on the physical screen.
    """
    def __init__(self):
        self._line1 = ""
        self._line2 = ""
        self._color = (80, 80, 80)

    def clear(self):
        self._line1 = ""
        self._line2 = ""

    def setCursor(self, row: int, col: int):
        pass  # State tracked via write calls

    def write(self, text: str):
        pass  # Handled by show() directly

    def setRGB(self, r: int, g: int, b: int):
        self._color = (r, g, b)

    def display(self, line1: str, line2: str):
        """Print the current display state to terminal."""
        self._line1 = line1.ljust(LCD_WIDTH)[:LCD_WIDTH]
        self._line2 = line2.ljust(LCD_WIDTH)[:LCD_WIDTH]
        r, g, b = self._color
        print(f"\n  ┌──────────────────┐")
        print(f"  │ {self._line1} │  RGB({r},{g},{b})")
        print(f"  │ {self._line2} │")
        print(f"  └──────────────────┘")


# ─────────────────────────────────────────────
# LCD MANAGER
# ─────────────────────────────────────────────

class LCDManager:
    """
    Manages the Grove LCD RGB display.

    Handles:
    - Lazy initialization (opens I2C on first use)
    - Auto-clearing before writes (prevents ghost characters)
    - Backlight color changes per event type
    - Error recovery if the display stops responding
    - Mock mode for laptop testing
    """

    def __init__(self):
        self._lcd = None
        self._is_mock = not _grove_available
        self._last_line1 = ""
        self._last_line2 = ""

    def _init_display(self):
        """Initialize the LCD hardware. Called once on first use."""
        if self._is_mock:
            self._lcd = MockLCD()
            logger.info("LCD initialized in mock mode (terminal output).")
            return

        try:
            self._lcd = JHD1802()
            self._lcd.clear()
            logger.info("Grove LCD initialized successfully.")
        except Exception as e:
            logger.error(f"LCD init failed: {e} — switching to mock mode.")
            self._is_mock = True
            self._lcd = MockLCD()

    def _get_lcd(self):
        if self._lcd is None:
            self._init_display()
        return self._lcd

    def _set_backlight(self, event_type: str):
        """Sets the RGB backlight color for the given event type."""
        color = BACKLIGHT_COLORS.get(event_type, BACKLIGHT_COLORS["IDLE"])
        r, g, b = color

        if self._is_mock:
            self._lcd.setRGB(r, g, b)
            return

        try:
            self._lcd.setRGB(r, g, b)
        except Exception as e:
            logger.warning(f"Failed to set backlight: {e}")

    def show(self, line1: str, line2: str = "", event_type: str = "IDLE"):
        """
        Main display method. Call this from anywhere in the Pi code.

        Args:
            line1:      Top line — max 16 chars. Longer strings are truncated.
            line2:      Bottom line — max 16 chars. Score bar goes here.
            event_type: Used to set the backlight color. Pass the event string
                        from the CoachingEvent e.g. "GOOD", "SPEED_UP", etc.
        
        Avoids unnecessary I2C writes if the content hasn't changed —
        flickering the LCD on every loop iteration looks bad during demos.
        """
        # Pad/truncate to exactly LCD_WIDTH
        l1 = line1.ljust(LCD_WIDTH)[:LCD_WIDTH]
        l2 = line2.ljust(LCD_WIDTH)[:LCD_WIDTH]

        # Skip write if nothing changed (avoids I2C overhead + flicker)
        if l1 == self._last_line1 and l2 == self._last_line2:
            return

        lcd = self._get_lcd()

        if self._is_mock:
            lcd.setRGB(*BACKLIGHT_COLORS.get(event_type, BACKLIGHT_COLORS["IDLE"]))
            lcd.display(l1, l2)
        else:
            try:
                lcd.clear()
                lcd.setCursor(0, 0)
                lcd.write(l1)
                lcd.setCursor(1, 0)
                lcd.write(l2)
                self._set_backlight(event_type)
            except Exception as e:
                logger.error(f"LCD write failed: {e} — attempting reinit.")
                self._lcd = None  # Force reinit on next call
                return

        self._last_line1 = l1
        self._last_line2 = l2

    def clear(self):
        """Clears the display and resets to idle backlight color."""
        lcd = self._get_lcd()
        self._last_line1 = ""
        self._last_line2 = ""

        if self._is_mock:
            print("  [LCD cleared]")
            return

        try:
            lcd.clear()
            self._set_backlight("IDLE")
        except Exception as e:
            logger.warning(f"LCD clear failed: {e}")

    def startup_animation(self):
        """
        Plays a short startup sequence on the LCD.
        Called once when pi/main.py starts.
        Shows the project name, then "Ready..." before entering the loop.
        """
        self._set_backlight("STARTUP")

        frames = [
            ("NEURO-SYNC",     "  initializing  "),
            ("NEURO-SYNC",     "  loading AI... "),
            ("NEURO-SYNC",     "  ready!        "),
        ]

        for line1, line2 in frames:
            self.show(line1, line2, "STARTUP")
            self._last_line1 = ""  # Force re-draw on next call
            self._last_line2 = ""
            time.sleep(0.7)

        self.clear()

    def show_error(self, message: str):
        """Display an error state. Magenta backlight."""
        short = message[:LCD_WIDTH]
        self.show("  ERROR", short, "ERROR")


# ─────────────────────────────────────────────
# MODULE-LEVEL SINGLETON
# ─────────────────────────────────────────────

_manager: Optional[LCDManager] = None

def get_manager() -> LCDManager:
    global _manager
    if _manager is None:
        _manager = LCDManager()
    return _manager

def show(line1: str, line2: str = "", event_type: str = "IDLE"):
    """Public API — write two lines to the LCD."""
    get_manager().show(line1, line2, event_type)

def clear():
    """Public API — clear the LCD."""
    get_manager().clear()

def startup_animation():
    """Public API — play startup sequence."""
    get_manager().startup_animation()

def show_error(message: str):
    """Public API — show error state."""
    get_manager().show_error(message)


# ─────────────────────────────────────────────
# QUICK TEST
# Run directly to test all backlight colors + display:
#   python3 lcd.py
# ─────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    print("Testing LCD display...\n")

    startup_animation()
    time.sleep(0.5)

    test_cases = [
        ("GREAT ENERGY!",  "██████████ 100%", "GOOD"),
        (">> SPEED UP <<",  "████░░░░░░  43%", "SPEED_UP"),
        ("SHOW ENERGY!",   "█████░░░░░  52%", "VIBE_CHECK"),
        ("RAISE ENERGY!",  "████░░░░░░  41%", "RAISE_ENERGY"),
        ("MOVE AROUND!",   "██████░░░░  63%", "VISUAL_RESET"),
    ]

    for line1, line2, event in test_cases:
        print(f"\nEvent: {event}")
        show(line1, line2, event)
        time.sleep(1.2)

    clear()
    print("\n✓ LCD test complete.")
