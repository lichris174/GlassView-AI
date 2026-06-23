//! Owns the Python AI service lifecycle: spawn on launch, kill on exit.
//!
//! Best-effort in dev: if the venv interpreter isn't found we log and continue,
//! so a developer can also run the backend manually. The shell never hard-fails
//! just because the sidecar path differs.

use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;

static SIDECAR: Mutex<Option<Child>> = Mutex::new(None);

const PORT: &str = "8765";

fn python_candidates() -> Vec<PathBuf> {
    if let Ok(explicit) = std::env::var("GLASSVIEW_PYTHON") {
        return vec![PathBuf::from(explicit)];
    }
    let server = PathBuf::from("../server");
    vec![
        server.join(".venv/Scripts/python.exe"), // Windows
        server.join(".venv/bin/python"),         // Unix
    ]
}

/// Start the FastAPI service as a child process if not already running.
pub fn start() {
    let mut guard = SIDECAR.lock().unwrap();
    if guard.is_some() {
        return;
    }
    let python = python_candidates().into_iter().find(|p| p.exists());
    let Some(python) = python else {
        eprintln!(
            "[sidecar] no venv python found; start the backend manually \
             (cd apps/server && uvicorn glassview_ai.main:app --port {PORT})"
        );
        return;
    };

    match Command::new(&python)
        .current_dir("../server")
        .args([
            "-m",
            "uvicorn",
            "glassview_ai.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            PORT,
        ])
        .spawn()
    {
        Ok(child) => {
            println!("[sidecar] started backend pid={}", child.id());
            *guard = Some(child);
        }
        Err(e) => eprintln!("[sidecar] failed to start backend: {e}"),
    }
}

/// Kill the backend child if we started one.
pub fn stop() {
    if let Some(mut child) = SIDECAR.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
        println!("[sidecar] backend stopped");
    }
}
