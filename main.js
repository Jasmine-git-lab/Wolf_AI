const {
    app,
    BrowserWindow,
    ipcMain,
    session,
    Tray,
    Menu,
    nativeImage,
    globalShortcut,
    screen
} = require("electron");

const path = require("path");
const fs = require("fs");
const http = require("http");
const { spawn, exec } = require("child_process");

let mainWindow = null;
let tray = null;
let pythonProcess = null;
let backendStatus = "stopped"; // "stopped" | "starting" | "running" | "error"
let isQuitting = false;
let isPinned = true;
let healthCheckTimer = null;
let autoDismissTimer = null;

const BACKEND_PORT = 5000;
const HEALTH_URL = `http://127.0.0.1:${BACKEND_PORT}/health`;
const HOTKEY = "CommandOrControl+Shift+Space";

const OVERLAY_WIDTH = 420;
const OVERLAY_HEIGHT = 280;
const TOP_OFFSET_Y = 24;

// ============================================================
// SCREEN & POSITIONING
// ============================================================

function getTopCenterPosition(width = OVERLAY_WIDTH) {
    const primaryDisplay = screen.getPrimaryDisplay();
    const { width: screenWidth, x: displayX, y: displayY } = primaryDisplay.workArea;
    const x = Math.round(displayX + (screenWidth - width) / 2);
    const y = Math.round(displayY + TOP_OFFSET_Y);
    return { x, y };
}

// ============================================================
// PYTHON EXECUTABLE RESOLVER
// ============================================================

function getPythonExecutable() {
    const candidates = [
        process.env.PYTHON_PATH,
        path.join(__dirname, "..", ".venv", "Scripts", "python.exe"),
        path.join(__dirname, ".venv", "Scripts", "python.exe"),
        path.join(process.cwd(), "..", ".venv", "Scripts", "python.exe"),
        path.join(process.cwd(), ".venv", "Scripts", "python.exe"),
        path.join(__dirname, "..", ".venv", "bin", "python"),
        path.join(__dirname, ".venv", "bin", "python"),
        process.platform === "win32" ? "python.exe" : "python3",
        "python"
    ];

    for (const candidate of candidates) {
        if (candidate && fs.existsSync(candidate)) {
            return candidate;
        }
    }

    return process.platform === "win32" ? "python.exe" : "python3";
}

// ============================================================
// BACKEND LIFECYCLE MANAGEMENT
// ============================================================

function broadcastBackendStatus() {
    if (mainWindow && !mainWindow.isDestroyed() && mainWindow.webContents) {
        mainWindow.webContents.send("backend-status", {
            status: backendStatus,
            port: BACKEND_PORT,
            pid: pythonProcess ? pythonProcess.pid : null
        });
    }
}

function checkBackendHealth(maxRetries = 40, retryIntervalMs = 500) {
    if (healthCheckTimer) {
        clearInterval(healthCheckTimer);
        healthCheckTimer = null;
    }

    let retries = 0;

    healthCheckTimer = setInterval(() => {
        if (backendStatus === "stopped" || !pythonProcess) {
            clearInterval(healthCheckTimer);
            healthCheckTimer = null;
            return;
        }

        retries += 1;

        http.get(HEALTH_URL, (res) => {
            if (res.statusCode === 200) {
                let body = "";
                res.on("data", chunk => { body += chunk; });
                res.on("end", () => {
                    console.log("[Electron] Backend health check PASSED.");
                    backendStatus = "running";
                    clearInterval(healthCheckTimer);
                    healthCheckTimer = null;
                    updateTrayMenu();
                    broadcastBackendStatus();
                });
            }
        }).on("error", () => {
            if (retries >= maxRetries) {
                console.warn("[Electron] Backend health check TIMED OUT.");
                clearInterval(healthCheckTimer);
                healthCheckTimer = null;
                if (backendStatus === "starting") {
                    backendStatus = "error";
                    updateTrayMenu();
                    broadcastBackendStatus();
                }
            }
        });
    }, retryIntervalMs);
}

function startBackend() {
    if (pythonProcess && !pythonProcess.killed) {
        console.log("[Electron] Python backend is already running (PID: " + pythonProcess.pid + ").");
        return;
    }

    const pythonExecutable = getPythonExecutable();
    const scriptPath = path.join(__dirname, "agent.py");

    console.log(`[Electron] Spawning backend: "${pythonExecutable}" "${scriptPath}"`);
    backendStatus = "starting";
    updateTrayMenu();
    broadcastBackendStatus();

    try {
        pythonProcess = spawn(pythonExecutable, [scriptPath, "start"], {
            cwd: __dirname,
            env: {
                ...process.env,
                PYTHONUNBUFFERED: "1"
            },
            stdio: ["ignore", "pipe", "pipe"]
        });

        pythonProcess.stdout.on("data", (data) => {
            const msg = data.toString().trim();
            if (msg) {
                console.log(`[Backend:stdout] ${msg}`);
            }
        });

        pythonProcess.stderr.on("data", (data) => {
            const msg = data.toString().trim();
            if (msg) {
                console.error(`[Backend:stderr] ${msg}`);
            }
        });

        pythonProcess.on("error", (err) => {
            console.error("[Electron] Backend process spawn error:", err);
            backendStatus = "error";
            updateTrayMenu();
            broadcastBackendStatus();
        });

        pythonProcess.on("exit", (code, signal) => {
            console.log(`[Electron] Backend process exited with code ${code}, signal ${signal}.`);
            pythonProcess = null;
            if (!isQuitting) {
                backendStatus = "stopped";
                updateTrayMenu();
                broadcastBackendStatus();
            }
        });

        checkBackendHealth();
    } catch (err) {
        console.error("[Electron] Failed to spawn Python backend:", err);
        backendStatus = "error";
        updateTrayMenu();
        broadcastBackendStatus();
    }
}

function stopBackend() {
    return new Promise((resolve) => {
        if (healthCheckTimer) {
            clearInterval(healthCheckTimer);
            healthCheckTimer = null;
        }

        if (!pythonProcess || pythonProcess.killed) {
            pythonProcess = null;
            backendStatus = "stopped";
            updateTrayMenu();
            broadcastBackendStatus();
            return resolve();
        }

        const pid = pythonProcess.pid;
        console.log(`[Electron] Terminating Python backend (PID: ${pid})...`);

        if (process.platform === "win32") {
            exec(`taskkill /pid ${pid} /T /F`, (err) => {
                if (err) {
                    console.warn(`[Electron] taskkill error: ${err.message}`);
                }
                pythonProcess = null;
                backendStatus = "stopped";
                updateTrayMenu();
                broadcastBackendStatus();
                resolve();
            });
        } else {
            try {
                pythonProcess.kill("SIGTERM");
            } catch (e) {
                // ignore
            }
            setTimeout(() => {
                if (pythonProcess && !pythonProcess.killed) {
                    try { pythonProcess.kill("SIGKILL"); } catch (e) {}
                }
                pythonProcess = null;
                backendStatus = "stopped";
                updateTrayMenu();
                broadcastBackendStatus();
                resolve();
            }, 500);
        }
    });
}

async function restartBackend() {
    console.log("[Electron] Restarting Python backend...");
    await stopBackend();
    setTimeout(() => {
        startBackend();
    }, 600);
}

// ============================================================
// AUTO DISMISS TIMER
// ============================================================

function triggerAutoDismiss(delayMs = 3500) {
    cancelAutoDismiss();
    autoDismissTimer = setTimeout(() => {
        if (mainWindow && !mainWindow.isDestroyed() && mainWindow.isVisible()) {
            mainWindow.webContents.send("trigger-dismiss-animation");
        }
    }, delayMs);
}

function cancelAutoDismiss() {
    if (autoDismissTimer) {
        clearTimeout(autoDismissTimer);
        autoDismissTimer = null;
    }
}

// ============================================================
// WINDOW & TRAY MANAGEMENT
// ============================================================

function showAndFocusWindow() {
    cancelAutoDismiss();
    if (!mainWindow || mainWindow.isDestroyed()) {
        createWindow();
        return;
    }

    const pos = getTopCenterPosition(mainWindow.getBounds().width);
    mainWindow.setPosition(pos.x, pos.y);

    if (mainWindow.isMinimized()) {
        mainWindow.restore();
    }
    if (!mainWindow.isVisible()) {
        mainWindow.show();
    }

    mainWindow.setAlwaysOnTop(isPinned, "screen-saver");
    mainWindow.focus();
    if (mainWindow.webContents) {
        mainWindow.webContents.send("trigger-show-animation");
    }
    updateTrayMenu();
}

function toggleWindow() {
    if (!mainWindow || mainWindow.isDestroyed()) {
        createWindow();
        return;
    }
    if (mainWindow.isVisible()) {
        mainWindow.hide();
    } else {
        showAndFocusWindow();
    }
    updateTrayMenu();
}

function getTrayIcon() {
    const iconPaths = [
        path.join(__dirname, "assets", "tray.png"),
        path.join(__dirname, "assets", "icon.png"),
        path.join(__dirname, "..", "assets", "tray.png"),
        path.join(__dirname, "..", "assets", "icon.png")
    ];

    for (const iconPath of iconPaths) {
        if (fs.existsSync(iconPath)) {
            return nativeImage.createFromPath(iconPath);
        }
    }

    return nativeImage.createEmpty();
}

function updateTrayMenu() {
    if (!tray) return;

    let statusText = "Offline";
    if (backendStatus === "running") statusText = "Online (Port 5000)";
    else if (backendStatus === "starting") statusText = "Starting...";
    else if (backendStatus === "error") statusText = "Error";

    const isWinVisible = mainWindow && !mainWindow.isDestroyed() && mainWindow.isVisible();

    const contextMenu = Menu.buildFromTemplate([
        {
            label: "Wolf AI Desktop HUD",
            enabled: false
        },
        {
            label: `Backend Status: ${statusText}`,
            enabled: false
        },
        { type: "separator" },
        {
            label: "Wake Wolf (Ctrl+Shift+Space)",
            click: () => {
                showAndFocusWindow();
                if (mainWindow && mainWindow.webContents) {
                    mainWindow.webContents.send("wake-wolf");
                }
            }
        },
        {
            label: isWinVisible ? "Hide Overlay" : "Show Overlay",
            click: () => {
                toggleWindow();
            }
        },
        {
            label: "Restart Backend",
            click: () => {
                restartBackend();
            }
        },
        { type: "separator" },
        {
            label: "Settings",
            click: () => {
                showAndFocusWindow();
                if (mainWindow && mainWindow.webContents) {
                    mainWindow.webContents.send("open-settings");
                }
            }
        },
        { type: "separator" },
        {
            label: "Quit Wolf AI",
            click: () => {
                quitApplication();
            }
        }
    ]);

    tray.setContextMenu(contextMenu);
}

function createTray() {
    const icon = getTrayIcon();
    tray = new Tray(icon);
    tray.setToolTip("Wolf AI Desktop Assistant");

    tray.on("click", () => {
        toggleWindow();
    });

    tray.on("double-click", () => {
        showAndFocusWindow();
    });

    updateTrayMenu();
}

// ============================================================
// CREATE OVERLAY WINDOW
// ============================================================

function createWindow() {
    const pos = getTopCenterPosition(OVERLAY_WIDTH);

    mainWindow = new BrowserWindow({
        width: OVERLAY_WIDTH,
        height: OVERLAY_HEIGHT,
        minWidth: 480,
        minHeight: 120,
        x: pos.x,
        y: pos.y,
        frame: false,
        transparent: true,
        hasShadow: false,
        alwaysOnTop: isPinned,
        skipTaskbar: false,
        resizable: true,
        show: false,
        backgroundColor: "#00000000",
        icon: path.join(__dirname, "assets", "icon.png"),
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false,
            webSecurity: true
        }
    });

    mainWindow.setAlwaysOnTop(isPinned, "screen-saver");
    mainWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });

    // Microphone / media permissions
    const allowedPermissions = ["media", "microphone", "audio-capture", "speech"];
    session.defaultSession.setPermissionRequestHandler(
        (webContents, permission, callback) => {
            callback(allowedPermissions.includes(permission));
        }
    );
    session.defaultSession.setPermissionCheckHandler(
        (webContents, permission) => {
            return allowedPermissions.includes(permission);
        }
    );

    mainWindow.loadFile(path.join(__dirname, "index.html"));

    mainWindow.once("ready-to-show", () => {
        showAndFocusWindow();
    });

    // Keep resident in system tray on close instead of exiting
    mainWindow.on("close", (event) => {
        if (!isQuitting) {
            event.preventDefault();
            mainWindow.hide();
            updateTrayMenu();
            return false;
        }
    });

    mainWindow.on("closed", () => {
        mainWindow = null;
    });

    mainWindow.on("show", () => {
        updateTrayMenu();
    });

    mainWindow.on("hide", () => {
        updateTrayMenu();
    });
}

// ============================================================
// GLOBAL HOTKEY REGISTRATION
// ============================================================

function registerGlobalHotkeys() {
    try {
        const registered = globalShortcut.register(HOTKEY, () => {
            console.log(`[Electron] Global hotkey ${HOTKEY} triggered.`);
            showAndFocusWindow();
            if (mainWindow && mainWindow.webContents) {
                mainWindow.webContents.send("wake-wolf");
            }
        });

        if (registered) {
            console.log(`[Electron] Registered global hotkey: ${HOTKEY}`);
        } else {
            console.warn(`[Electron] Failed to register global hotkey: ${HOTKEY}`);
        }
    } catch (err) {
        console.error("[Electron] Error registering global hotkey:", err);
    }
}

// ============================================================
// APPLICATION LIFECYCLE
// ============================================================

async function quitApplication() {
    isQuitting = true;
    cancelAutoDismiss();
    globalShortcut.unregisterAll();
    if (tray) {
        try { tray.destroy(); } catch (e) {}
        tray = null;
    }
    await stopBackend();
    app.quit();
}

app.whenReady().then(() => {
    createWindow();
    createTray();
    registerGlobalHotkeys();
    startBackend();

    app.on("activate", () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        } else {
            showAndFocusWindow();
        }
    });
});

app.on("window-all-closed", () => {
    // Keep app running in system tray on Windows / Linux / macOS
});

app.on("will-quit", () => {
    globalShortcut.unregisterAll();
});

app.on("before-quit", async (event) => {
    if (!isQuitting) {
        event.preventDefault();
        await quitApplication();
    }
});

// ============================================================
// IPC COMMUNICATION
// ============================================================

ipcMain.on("frontend-ready", () => {
    console.log("[Electron] Frontend ready.");
    broadcastBackendStatus();
});

ipcMain.on("restart-backend", () => {
    restartBackend();
});

ipcMain.handle("get-backend-status", () => {
    return {
        status: backendStatus,
        port: BACKEND_PORT,
        pid: pythonProcess ? pythonProcess.pid : null
    };
});

ipcMain.on("wake-wolf", () => {
    showAndFocusWindow();
    if (mainWindow && mainWindow.webContents) {
        mainWindow.webContents.send("wake-wolf");
    }
});

ipcMain.on("hide-window", () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.hide();
        updateTrayMenu();
    }
});

ipcMain.on("minimize-window", () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.minimize();
    }
});

ipcMain.on("toggle-pin", (event, pinState) => {
    if (typeof pinState === "boolean") {
        isPinned = pinState;
    } else {
        isPinned = !isPinned;
    }
    if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.setAlwaysOnTop(isPinned, "screen-saver");
    }
    event.sender.send("pin-status-changed", isPinned);
});

ipcMain.on("resize-window", (event, { width, height }) => {
    if (!mainWindow || mainWindow.isDestroyed()) return;
    const currentBounds = mainWindow.getBounds();
    const newWidth = width || currentBounds.width;
    const newHeight = height || currentBounds.height;
    const pos = getTopCenterPosition(newWidth);
    mainWindow.setBounds({
        x: pos.x,
        y: pos.y,
        width: newWidth,
        height: newHeight
    });
});

ipcMain.on("start-auto-dismiss", (event, { delayMs } = {}) => {
    triggerAutoDismiss(delayMs || 3500);
});

ipcMain.on("cancel-auto-dismiss", () => {
    cancelAutoDismiss();
});

ipcMain.on("overlay-animation-finished", () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.hide();
        updateTrayMenu();
    }
});

ipcMain.on("quit-app", () => {
    quitApplication();
});