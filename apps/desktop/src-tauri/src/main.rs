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
use tauri_plugin_global_shortcut::{Builder as GlobalShortcutBuilder, GlobalShortcutExt, ShortcutState};

const DEFAULT_SHORTCUT: &str = "Ctrl+Shift+Space";

fn main() {
    tauri::Builder::default()
        .plugin(GlobalShortcutBuilder::new().build())
        .invoke_handler(tauri::generate_handler![
            capture::log_frontend,
            capture::capture_screen,
            capture::arm_region_escape,
            capture::disarm_region_escape,
            register_shortcut,
        ])
        .setup(|app| {
            sidecar::start();
            if let Err(err) = register_hotkey(app.handle(), DEFAULT_SHORTCUT) {
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

/// Re-register the global hotkey to a new accelerator (called from Settings).
/// Returns an error if the accelerator string is invalid so the UI can warn the user.
#[tauri::command]
fn register_shortcut(app: tauri::AppHandle, accelerator: String) -> Result<(), String> {
    app.global_shortcut().unregister_all().ok();
    register_hotkey(&app, &accelerator)
}

/// Bind `accelerator` to toggle the overlay: surface the window and emit `toggle-overlay`
/// so the frontend expands/collapses the toolbar.
fn register_hotkey(app: &tauri::AppHandle, accelerator: &str) -> Result<(), String> {
    let handle = app.clone();
    app.global_shortcut()
        .on_shortcut(accelerator, move |_app, _sc, event| {
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
            eprintln!("[hotkey] failed to register {accelerator}: {err}");
            format!("{err}")
        })
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
