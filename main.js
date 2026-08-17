const {
    app,
    BrowserWindow,
    session
} = require("electron");

const {
    spawn,
    execSync
} = require("child_process");

const path = require("path");

let mainWindow = null;
let pythonProcess = null;


// ============================================================
// CREATE WINDOW
// ============================================================

function createWindow() {

    mainWindow = new BrowserWindow({

        width: 900,
        height: 700,

        minWidth: 700,
        minHeight: 600,

        webPreferences: {

            nodeIntegration: true,

            contextIsolation: false,

            // Required for microphone access
            webSecurity: false

        }

    });


    mainWindow.loadFile(
        path.join(__dirname, "index.html")
    );


    mainWindow.webContents.openDevTools();


    mainWindow.on("closed", () => {

        mainWindow = null;

    });

}


// ============================================================
// PYTHON DETECTION
// ============================================================

function findPython() {

    const candidates =
        process.platform === "win32"

            ? [
                "python",
                "py",
                "python3"
            ]

            : [
                "python3",
                "python"
            ];


    for (const command of candidates) {

        try {

            execSync(
                `${command} --version`,
                {
                    stdio: "ignore"
                }
            );

            return command;

        }

        catch (error) {

            // Try next Python command

        }

    }


    return null;

}


// ============================================================
// START PYTHON BACKEND
// ============================================================

function startPythonBackend() {

    const pythonPath = findPython();


    if (!pythonPath) {

        console.error(
            "[ERROR] Python was not found."
        );

        return;

    }


    const agentPath =
        path.join(
            __dirname,
            "agent.py"
        );


    console.log(
        `[INFO] Starting Wolf backend using ${pythonPath}`
    );


    pythonProcess = spawn(

        pythonPath,

        [
            "-u",
            agentPath
        ],

        {

            cwd: __dirname,

            env: {
                ...process.env,

                PYTHONUNBUFFERED: "1"

            },

            windowsHide: false

        }

    );


    // --------------------------------------------------------
    // PYTHON OUTPUT
    // --------------------------------------------------------

    pythonProcess.stdout.on(
        "data",
        (data) => {

            const text =
                data.toString();

            console.log(
                "[Python]",
                text.trim()
            );


            if (
                text.includes(
                    "Starting Flask server"
                )
            ) {

                if (mainWindow) {

                    mainWindow.webContents.send(
                        "backend-starting"
                    );

                }

            }


            if (
                text.includes(
                    "WOLF VOICE AGENT READY"
                )
            ) {

                if (mainWindow) {

                    mainWindow.webContents.send(
                        "voice-agent-ready"
                    );

                }

            }

        }
    );


    // --------------------------------------------------------
    // PYTHON ERRORS
    // --------------------------------------------------------

    pythonProcess.stderr.on(
        "data",
        (data) => {

            console.error(
                "[Python Error]",
                data.toString()
            );

        }
    );


    // --------------------------------------------------------
    // PYTHON ERROR
    // --------------------------------------------------------

    pythonProcess.on(
        "error",
        (error) => {

            console.error(
                "[ERROR] Failed to start Python:",
                error
            );

        }
    );


    // --------------------------------------------------------
    // PYTHON EXIT
    // --------------------------------------------------------

    pythonProcess.on(
        "close",
        (code) => {

            console.log(
                `[INFO] Python backend exited with code ${code}`
            );

            pythonProcess = null;

        }
    );

}


// ============================================================
// ELECTRON READY
// ============================================================

app.whenReady().then(() => {

    // --------------------------------------------------------
    // MICROPHONE PERMISSION
    // --------------------------------------------------------

    session.defaultSession.setPermissionRequestHandler(
        (
            webContents,
            permission,
            callback
        ) => {

            if (
                permission === "media"
            ) {

                callback(true);

            }

            else {

                callback(false);

            }

        }
    );


    // --------------------------------------------------------
    // CREATE WINDOW
    // --------------------------------------------------------

    createWindow();


    // --------------------------------------------------------
    // START PYTHON
    // --------------------------------------------------------

    startPythonBackend();

});


// ============================================================
// WINDOWS / MAC
// ============================================================

app.on(
    "window-all-closed",
    () => {

        if (pythonProcess) {

            console.log(
                "[INFO] Stopping Python backend..."
            );


            try {

                pythonProcess.kill();

            }

            catch (error) {

                console.error(
                    error
                );

            }

            pythonProcess = null;

        }


        if (
            process.platform !== "darwin"
        ) {

            app.quit();

        }

    }
);


app.on(
    "activate",
    () => {

        if (
            BrowserWindow.getAllWindows()
                .length === 0
        ) {

            createWindow();

        }

    }
);


