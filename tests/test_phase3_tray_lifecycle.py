"""Unit and integration tests for Wolf AI Phase 3 Background & Tray Architecture."""
import os
import sys
import json
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


class Phase3ArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.main_js_path = BASE_DIR / "main.js"
        self.assets_dir = BASE_DIR / "assets"
        self.renderer_js_path = BASE_DIR / "renderer.js"

    def test_main_js_exists_and_contains_phase3_components(self):
        """Verify main.js contains spawn lifecycle, tray menu, global shortcut, and IPC handlers."""
        self.assertTrue(self.main_js_path.exists(), "main.js must exist")
        content = self.main_js_path.read_text(encoding="utf-8")

        # 1. Child process spawn & lifecycle
        self.assertIn("spawn", content, "main.js must use child_process.spawn")
        self.assertIn("getPythonExecutable", content, "main.js must resolve Python executable")
        self.assertIn("startBackend", content, "main.js must have startBackend lifecycle method")
        self.assertIn("stopBackend", content, "main.js must have stopBackend lifecycle method")
        self.assertIn("restartBackend", content, "main.js must have restartBackend lifecycle method")

        # 2. System tray & context menu
        self.assertIn("Tray", content, "main.js must import Electron Tray")
        self.assertIn("createTray", content, "main.js must implement createTray")
        self.assertIn("updateTrayMenu", content, "main.js must implement updateTrayMenu")
        self.assertIn("Wake Wolf", content, "Tray context menu must include Wake Wolf")
        self.assertIn("Restart Backend", content, "Tray context menu must include Restart Backend")
        self.assertIn("Quit Wolf AI", content, "Tray context menu must include Quit Wolf AI")

        # 3. Global hotkey
        self.assertIn("globalShortcut", content, "main.js must import globalShortcut")
        self.assertIn("CommandOrControl+Shift+Space", content, "Global hotkey must be Ctrl+Shift+Space")
        self.assertIn("registerGlobalHotkeys", content, "main.js must register hotkeys")

        # 4. IPC handlers
        self.assertIn("backend-status", content, "main.js must broadcast backend-status")
        self.assertIn("restart-backend", content, "main.js must handle restart-backend IPC")
        self.assertIn("wake-wolf", content, "main.js must handle wake-wolf IPC")

    def test_assets_exist(self):
        """Verify tray icon and app icons are generated in assets directory."""
        self.assertTrue(self.assets_dir.exists(), "assets directory must exist")
        icon_png = self.assets_dir / "icon.png"
        tray_png = self.assets_dir / "tray.png"
        self.assertTrue(icon_png.exists() or tray_png.exists(), "icon.png or tray.png must exist in assets")

    def test_renderer_listens_to_phase3_ipc_events(self):
        """Verify renderer.js has listeners for wake-wolf and backend-status."""
        self.assertTrue(self.renderer_js_path.exists(), "renderer.js must exist")
        content = self.renderer_js_path.read_text(encoding="utf-8")
        self.assertIn('ipcRenderer.on("wake-wolf"', content, "renderer must listen for wake-wolf event")
        self.assertIn('ipcRenderer.on("backend-status"', content, "renderer must listen for backend-status event")

    @patch("google.genai.Client")
    def test_health_endpoint_response_structure(self, mock_genai_client):
        """Verify /health endpoint returns valid JSON with ok=True."""
        with patch.dict(os.environ, {"GEMINI_TEXT_MODEL": "gemini-3.8-flash"}):
            from agent import app
            with app.test_client() as client:
                response = client.get("/health")
                self.assertEqual(response.status_code, 200)
                data = json.loads(response.data)
                self.assertTrue(data.get("ok"))
                self.assertIn("ai_ready", data)


if __name__ == "__main__":
    unittest.main()
