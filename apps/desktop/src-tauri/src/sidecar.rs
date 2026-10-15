//! Owns the Python backend lifecycle: spawn on launch unless one is already serving,
//! kill on exit. Best-effort — if no venv python is found we log and continue so a
//! developer can run `./dev.ps1` manually.

use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

static SIDECAR: Mutex<Option<Child>> = Mutex::new(None);

const PORT: &str = "8765";

/// True if something already answers on 127.0.0.1:8765 (a dev backend, say).
fn backend_running() -> bool {
    TcpStream::connect_timeout(
        &"127.0.0.1:8765".parse().unwrap(),
        Duration::from_millis(250),
    )
    .is_ok()
}

/// Repo root relative to the src-tauri working dir during `tauri dev`
/// (apps/desktop/src-tauri -> ../../..).
fn repo_root() -> PathBuf {
    if let Ok(explicit) = std::env::var("GLASSVIEW_ROOT") {
        return PathBuf::from(explicit);
    }
    PathBuf::from("../../..")
}

fn python_candidates(root: &PathBuf) -> Vec<PathBuf> {
    if let Ok(p) = std::env::var("GLASSVIEW_PYTHON") {
        return vec![PathBuf::from(p)];
    }
    vec![
        root.join(".venv/Scripts/python.exe"), // Windows
        root.join(".venv/bin/python"),         // Unix
    ]
}

/// Start the FastAPI service as a child process if not already running.
pub fn start() {
    let mut guard = SIDECAR.lock().unwrap();
    if guard.is_some() {
        return;
    }
    if backend_running() {
        println!("[sidecar] backend already serving on {PORT}; not spawning");
        return;
    }

    let root = repo_root();
    let python = python_candidates(&root).into_iter().find(|p| p.exists());
    let Some(python) = python else {
        eprintln!(
            "[sidecar] no venv python found; start the backend manually \
             (./dev.ps1 or uvicorn glassview_ai.main:app --port {PORT})"
        );
        return;
    };

    match Command::new(&python)
        .current_dir(&root)
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
            watch_readiness();
        }
        Err(e) => eprintln!("[sidecar] failed to start backend: {e}"),
    }
}

/// How long to wait for a freshly spawned backend to bind the port. Cold imports
/// (sqlite-vec, Pillow) are slow the first time, and slower still if the repo lives
/// on cloud-synced storage that has to hydrate the files first.
const READY_TIMEOUT: Duration = Duration::from_secs(90);

/// Poll the port after spawning so a backend that starts but never listens is
/// visible in the log instead of silently leaving the UI on its error panel.
fn watch_readiness() {
    thread::spawn(|| {
        let start = Instant::now();
        while start.elapsed() < READY_TIMEOUT {
            if backend_running() {
                println!(
                    "[sidecar] backend ready after {:.1}s",
                    start.elapsed().as_secs_f32()
                );
                return;
            }
            thread::sleep(Duration::from_millis(500));
        }
        eprintln!(
            "[sidecar] backend spawned but never bound {PORT} within {}s.              The process may be stuck importing. Check it with:              .venv/Scripts/python.exe -m uvicorn glassview_ai.main:app --port {PORT}",
            READY_TIMEOUT.as_secs()
        );
    });
}

/// Kill the backend child if we started one.
pub fn stop() {
    if let Some(mut child) = SIDECAR.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
        println!("[sidecar] backend stopped");
    }
}
