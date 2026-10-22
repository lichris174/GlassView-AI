#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! GlassView native shell: a content-sized transparent always-on-top overlay window,
//! a global toggle hotkey, a system tray, ownership of the Python backend sidecar, and
//! the region-snip capture flow (a temporary fullscreen window).

mod capture;
mod sidecar;

use tauri::{
    menu::{MenuBuilder, MenuItemBuilder},
    tray::TrayIconBuilder,
    Emitter, Manager, RunEvent,
};
use std::sync::Mutex;

use tauri_plugin_global_shortcut::{
    Builder as GlobalShortcutBuilder, GlobalShortcutExt, Shortcut, ShortcutState,
};

const DEFAULT_SHORTCUT: &str = "Ctrl+Shift+Space";

/// The accelerator currently bound to the overlay toggle. Tracked so a rebind can drop
/// exactly this one and leave other shortcuts (the region-mode Escape) alone.
static TOGGLE_SHORTCUT: Mutex<Option<Shortcut>> = Mutex::new(None);

fn main() {
    tauri::Builder::default()
        .plugin(GlobalShortcutBuilder::new().build())
        // Opens Markdown links in the system browser (scoped to http/https in capabilities).
        .plugin(tauri_plugin_opener::init())
        // Launch-on-login. The frontend toggles it through the plugin's own
        // commands; MacosLauncher is irrelevant on Windows but required by the API.
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .invoke_handler(tauri::generate_handler![
            capture::capture_screen,
            capture::arm_region_escape,
            capture::disarm_region_escape,
            register_shortcut,
        ])
        .setup(|app| {
            // Off the main thread: the /health probe can take seconds (it waits on
            // Ollama), and the window must not stall behind it.
            std::thread::spawn(sidecar::start);
            let default = parse_shortcut(DEFAULT_SHORTCUT)?;
            if let Err(err) = register_hotkey(app.handle(), default) {
                eprintln!("[setup] default hotkey unavailable: {err}");
            }
            build_tray(app.handle())?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|_app, event| {
            if let RunEvent::Exit = event {
                sidecar::stop();
            }
        });
}

fn parse_shortcut(accelerator: &str) -> Result<Shortcut, String> {
    accelerator
        .parse::<Shortcut>()
        .map_err(|err| format!("invalid shortcut \"{accelerator}\": {err}"))
}

/// Re-register the global hotkey to a new accelerator (called from Settings).
/// The new binding is validated and registered before the old one is dropped, so an
/// invalid or taken accelerator returns an error and leaves the current hotkey working.
#[tauri::command]
fn register_shortcut(app: tauri::AppHandle, accelerator: String) -> Result<(), String> {
    let next = parse_shortcut(&accelerator)?;
    let previous = *TOGGLE_SHORTCUT.lock().unwrap();
    if previous == Some(next) {
        return Ok(());
    }
    register_hotkey(&app, next)?;
    if let Some(previous) = previous {
        let _ = app.global_shortcut().unregister(previous);
    }
    Ok(())
}

/// Bind `shortcut` to toggle the overlay: surface the window and emit `toggle-overlay`
/// so the frontend expands/collapses the toolbar.
fn register_hotkey(app: &tauri::AppHandle, shortcut: Shortcut) -> Result<(), String> {
    let handle = app.clone();
    app.global_shortcut()
        .on_shortcut(shortcut, move |_app, _sc, event| {
            if event.state != ShortcutState::Pressed {
                return;
            }
            if let Some(main) = handle.get_webview_window("main") {
                let _ = main.show();
                let _ = main.set_focus();
                let _ = main.emit("toggle-overlay", ());
            }
        })
        .map_err(|err| {
            eprintln!("[hotkey] failed to register {shortcut}: {err}");
            format!("{err}")
        })?;
    *TOGGLE_SHORTCUT.lock().unwrap() = Some(shortcut);
    Ok(())
}

/// System tray with Show / Quit.
fn build_tray(app: &tauri::AppHandle) -> tauri::Result<()> {
    let show = MenuItemBuilder::with_id("show", "Show GlassView").build(app)?;
    let quit = MenuItemBuilder::with_id("quit", "Quit").build(app)?;
    let menu = MenuBuilder::new(app).items(&[&show, &quit]).build()?;

    TrayIconBuilder::new()
        .icon(app.default_window_icon().unwrap().clone())
        .tooltip("GlassView")
        .menu(&menu)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "show" => {
                if let Some(main) = app.get_webview_window("main") {
                    let _ = main.show();
                    let _ = main.set_focus();
                }
            }
            "quit" => app.exit(0),
            _ => {}
        })
        .build(app)?;
    Ok(())
}
