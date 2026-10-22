//! Screen capture for the region feature. Capture happens here; the selection + crop
//! run inside the MAIN window's React app (no second window — a blank second window was
//! trapping the user). A global-Escape failsafe force-restores the window even if the
//! webview ever freezes, so region mode can never lock the desktop.

use std::sync::atomic::{AtomicU64, Ordering};

use base64::Engine;
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

fn encode_png(buffer: &[u8], width: u32, height: u32) -> Result<String, String> {
    let mut png_data = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut png_data, width, height);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        let mut writer = encoder.write_header().map_err(|e| e.to_string())?;
        writer.write_image_data(buffer).map_err(|e| e.to_string())?;
    }
    let b64 = base64::engine::general_purpose::STANDARD.encode(&png_data);
    Ok(format!("data:image/png;base64,{b64}"))
}

#[tauri::command]
/// Capture the primary screen and return it as a PNG data URL (physical pixels).
pub fn capture_screen() -> Result<String, String> {
    let screen = screenshots::Screen::from_point(0, 0).map_err(|e| e.to_string())?;
    let image = screen.capture().map_err(|e| e.to_string())?;
    encode_png(image.rgba(), image.width(), image.height())
}

/// Restore the main window out of region mode (drop fullscreen, show, focus).
fn restore_main(app: &AppHandle) {
    if let Some(main) = app.get_webview_window("main") {
        let _ = main.set_fullscreen(false);
        let _ = main.set_always_on_top(true);
        let _ = main.show();
        let _ = main.set_focus();
    }
}

/// Bumped on every arm, so a delayed self-unregister from an earlier region session
/// cannot drop the Escape a newer session has armed.
static ESCAPE_ARM: AtomicU64 = AtomicU64::new(0);

#[tauri::command]
/// Arm a global Escape that cancels region mode even if the webview is unresponsive.
pub fn arm_region_escape(app: AppHandle) -> Result<(), String> {
    let arm = ESCAPE_ARM.fetch_add(1, Ordering::SeqCst) + 1;
    let handle = app.clone();
    app.global_shortcut()
        .on_shortcut("Escape", move |_app, _sc, event| {
            if event.state != ShortcutState::Pressed {
                return;
            }
            restore_main(&handle);
            if let Some(main) = handle.get_webview_window("main") {
                let _ = main.emit("region-cancel", ());
            }
            // Release Escape here rather than trusting the webview's disarm call, which
            // never arrives if the webview is dead. Off-thread: the plugin holds its
            // shortcut lock while running this handler, so unregistering inline deadlocks.
            let handle = handle.clone();
            std::thread::spawn(move || {
                if ESCAPE_ARM.load(Ordering::SeqCst) == arm {
                    let _ = handle.global_shortcut().unregister("Escape");
                }
            });
        })
        .map_err(|e| e.to_string())
}

#[tauri::command]
/// Disarm the global Escape failsafe when leaving region mode.
pub fn disarm_region_escape(app: AppHandle) -> Result<(), String> {
    let _ = app.global_shortcut().unregister("Escape");
    Ok(())
}
