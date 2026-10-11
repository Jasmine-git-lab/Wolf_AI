"""Unit and integration tests for Wolf AI Phase 4 Desktop Overlay Window."""
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


class Phase4OverlayTests(unittest.TestCase):
    def setUp(self):
        self.main_js_path = BASE_DIR / "main.js"
        self.index_html_path = BASE_DIR / "index.html"
        self.style_css_path = BASE_DIR / "style.css"
        self.renderer_js_path = BASE_DIR / "renderer.js"

    def test_main_js_frameless_overlay_configuration(self):
        """Verify main.js configures frameless transparent HUD overlay anchored top-center."""
        self.assertTrue(self.main_js_path.exists())
        content = self.main_js_path.read_text(encoding="utf-8")

        # 1. Overlay window properties
        self.assertIn("frame: false", content, "Window must be frameless")
        self.assertIn("transparent: true", content, "Window must be transparent")
        self.assertIn("hasShadow: false", content, "Window must disable shadow to prevent Windows border artifacts")
        self.assertIn("setAlwaysOnTop", content, "Window must configure alwaysOnTop")
        self.assertIn("getTopCenterPosition", content, "Window must calculate top-center positioning")
        self.assertIn("screen.getPrimaryDisplay", content, "Must use screen.getPrimaryDisplay for bounds")

        # 2. IPC handlers for overlay management
        self.assertIn("resize-window", content, "main.js must handle resize-window")
        self.assertIn("toggle-pin", content, "main.js must handle toggle-pin")
        self.assertIn("start-auto-dismiss", content, "main.js must handle start-auto-dismiss")
        self.assertIn("cancel-auto-dismiss", content, "main.js must handle cancel-auto-dismiss")
        self.assertIn("overlay-animation-finished", content, "main.js must handle animation finish")

    def test_index_html_contains_hud_capsule_and_controls(self):
        """Verify index.html contains modern HUD structure and controls."""
        self.assertTrue(self.index_html_path.exists())
        content = self.index_html_path.read_text(encoding="utf-8")

        self.assertIn("hudCapsule", content, "HTML must contain hudCapsule container")
        self.assertIn("pinBtn", content, "HTML must contain pin button")
        self.assertIn("minBtn", content, "HTML must contain minimize button")
        self.assertIn("closeBtn", content, "HTML must contain close button")
        self.assertIn("drag-region", content, "HTML must contain drag region for overlay dragging")
        self.assertIn("no-drag", content, "HTML must mark interactive controls as no-drag")

    def test_style_css_contains_overlay_animations(self):
        """Verify style.css includes transparent background, glassmorphism, and slide animations."""
        self.assertTrue(self.style_css_path.exists())
        content = self.style_css_path.read_text(encoding="utf-8")

        self.assertIn("background: transparent", content, "CSS must ensure transparent background")
        self.assertIn("hudSlideDown", content, "CSS must define hudSlideDown animation")
        self.assertIn("hudSlideUp", content, "CSS must define hudSlideUp animation")
        self.assertIn("-webkit-app-region: drag", content, "CSS must define drag region")
        self.assertIn("-webkit-app-region: no-drag", content, "CSS must define no-drag region")

    def test_renderer_js_overlay_event_bindings(self):
        """Verify renderer.js handles HUD animations, auto-dismiss, and controls."""
        self.assertTrue(self.renderer_js_path.exists())
        content = self.renderer_js_path.read_text(encoding="utf-8")

        self.assertIn("trigger-dismiss-animation", content, "Renderer must handle trigger-dismiss-animation")
        self.assertIn("trigger-show-animation", content, "Renderer must handle trigger-show-animation")
        self.assertIn("pin-status-changed", content, "Renderer must handle pin-status-changed")
        self.assertIn("start-auto-dismiss", content, "Renderer must trigger start-auto-dismiss")
        self.assertIn("cancel-auto-dismiss", content, "Renderer must trigger cancel-auto-dismiss")


if __name__ == "__main__":
    unittest.main()
