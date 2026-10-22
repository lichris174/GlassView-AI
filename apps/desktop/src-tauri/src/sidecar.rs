//! Owns the Python backend lifecycle: spawn on launch unless one is already serving,
//! kill on exit. Best-effort — if no venv python is found we log and continue so a
//! developer can run `./dev.ps1` manually.

use std::io::{Read, Write};
use std::net::TcpStream;
#[cfg(all(windows, not(debug_assertions)))]
use std::os::windows::process::CommandExt;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

static SIDECAR: Mutex<Option<Child>> = Mutex::new(None);
/// Set by stop(). start() runs on its own thread, so an app that quits while it is
/// still probing must not go on to spawn a backend nobody will kill.
static STOPPED: AtomicBool = AtomicBool::new(false);

const PORT: &str = "8765";

/// Upper bound on a /health reply. The route probes Ollama (5 s timeout), so a live
/// backend with a hung daemon can take that long to answer.
const HEALTH_TIMEOUT: Duration = Duration::from_secs(8);

/// Keeps the spawned python.exe (a console program) from opening a console window
/// in release builds, where the shell itself has no console to share. Debug builds
/// keep sharing the terminal so backend logs stay visible.
#[cfg(all(windows, not(debug_assertions)))]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// True if a GlassView backend already answers on 127.0.0.1:8765 (a dev backend, say).
/// Checks /health for the backend's own fields rather than a bare TCP connect, so an
/// unrelated or wedged listener on the port is not mistaken for a working backend.
fn backend_running() -> bool {
    let Ok(mut stream) = TcpStream::connect_timeout(
        &"127.0.0.1:8765".parse().unwrap(),
        Duration::from_millis(250),
    ) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(HEALTH_TIMEOUT));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(500)));
    let request =
        format!("GET /health HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\nConnection: close\r\n\r\n");
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut raw = Vec::new();
    let _ = stream.read_to_end(&mut raw);
    let reply = String::from_utf8_lossy(&raw);
    let status_ok = reply
        .lines()
        .next()
        .is_some_and(|status| status.split_whitespace().nth(1) == Some("200"));
    status_ok && reply.contains("\"ollama_host\"") && reply.contains("\"providers\"")
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
    if guard.is_some() || STOPPED.load(Ordering::SeqCst) {
        return;
    }
    if backend_running() {
        println!("[sidecar] backend already serving on {PORT}; not spawning");
        return;
    }
    if STOPPED.load(Ordering::SeqCst) {
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

    let mut command = Command::new(&python);
    #[cfg(all(windows, not(debug_assertions)))]
    command.creation_flags(CREATE_NO_WINDOW);
    match command
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
    STOPPED.store(true, Ordering::SeqCst);
    if let Some(mut child) = SIDECAR.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
        println!("[sidecar] backend stopped");
    }
}
