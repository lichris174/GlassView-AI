#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! GlassView native shell: window control, screen capture, global hotkey, and
//! ownership of the Python AI sidecar.

mod capture;
mod sidecar;
mod window_fx;

use tauri::{Emitter, Manager, RunEvent};
use tauri_plugin_global_shortcut::{
    Builder as GlobalShortcutBuilder, GlobalShortcutExt, ShortcutState,
};

fn main() {
    let app = tauri::Builder::default()
        .plugin(GlobalShortcutBuilder::new().build())
        .invoke_handler(tauri::generate_handler![
            capture::log_frontend,
            capture::capture_fullscreen,
            capture::start_snip,
            capture::get_snip_image,
            capture::finish_snip,
            capture::cancel_snip,
        ])
        .setup(|app| {
            sidecar::start();
            register_hotkey(app.handle());
            window_fx::apply_acrylic(app.handle());
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|_app, event| {
        if let RunEvent::Exit = event {
            sidecar::stop();
        }
    });
}

/// Global hotkey: summon the main window and trigger the snip flow.
fn register_hotkey(app: &tauri::AppHandle) {
    let shortcut = "Ctrl+Alt+Shift+M";
    let handle = app.clone();
    if let Err(err) = app.global_shortcut().on_shortcut(shortcut, move |_app, _sc, event| {
        if event.state != ShortcutState::Pressed {
            return;
        }
        if let Some(main) = handle.get_webview_window("main") {
            if let Ok(true) = main.is_minimized() {
                let _ = main.unminimize();
            }
            let _ = main.show();
            let _ = main.set_focus();
            let _ = main.emit("snip-hotkey", ());
        }
    }) {
        println!("[hotkey] failed to register {shortcut}: {err}");
    }
}
