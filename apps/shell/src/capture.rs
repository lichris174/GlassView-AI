//! Screen capture + region-snip commands (ported from the prototype main.rs).

use base64::Engine;
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager, WebviewUrl, WebviewWindowBuilder};

#[tauri::command]
/// Frontend log sink for debugging.
pub fn log_frontend(message: String) {
    println!("[frontend] {message}");
}

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
/// Capture the primary screen and return a PNG data URL.
pub fn capture_fullscreen() -> Result<String, String> {
    let screen = screenshots::Screen::from_point(0, 0).map_err(|e| e.to_string())?;
    let image = screen.capture().map_err(|e| e.to_string())?;
    encode_png(&image.rgba().clone(), image.width(), image.height())
}

struct SnipState {
    image: Vec<u8>,
    width: u32,
    height: u32,
}

static SNIP_STATE: Mutex<Option<SnipState>> = Mutex::new(None);

#[tauri::command]
/// Capture the screen and show the fullscreen snip overlay.
pub fn start_snip(app: AppHandle) -> Result<(), String> {
    if let Some(main) = app.get_webview_window("main") {
        let _ = main.hide();
    }

    let screen = screenshots::Screen::from_point(0, 0).map_err(|e| e.to_string())?;
    let image = screen.capture().map_err(|e| e.to_string())?;
    let width = image.width();
    let height = image.height();

    {
        let mut state = SNIP_STATE.lock().map_err(|e| e.to_string())?;
        *state = Some(SnipState {
            image: image.rgba().clone(),
            width,
            height,
        });
    }

    if app.get_webview_window("snip-overlay").is_none() {
        WebviewWindowBuilder::new(&app, "snip-overlay", WebviewUrl::App("overlay.html".into()))
            .transparent(false)
            .decorations(false)
            .focused(true)
            .fullscreen(true)
            .always_on_top(true)
            .visible(true)
            .resizable(false)
            .build()
            .map_err(|e| e.to_string())?;
    }

    if let Some(win) = app.get_webview_window("snip-overlay") {
        win.show().map_err(|e| e.to_string())?;
        let _ = win.set_focus();
    } else {
        if let Some(main) = app.get_webview_window("main") {
            let _ = main.show();
        }
        return Err("Overlay window missing".into());
    }
    Ok(())
}

#[tauri::command]
/// Return the captured screen so the overlay can render it.
pub fn get_snip_image() -> Result<String, String> {
    let state = SNIP_STATE.lock().map_err(|e| e.to_string())?;
    let snip = state.as_ref().ok_or("No snip state")?;
    encode_png(&snip.image, snip.width, snip.height)
}

#[tauri::command]
/// Crop the capture to the selected region and emit it to the main window.
#[allow(clippy::too_many_arguments)]
pub fn finish_snip(
    app: AppHandle,
    x: f32,
    y: f32,
    width: f32,
    height: f32,
    viewport_w: f32,
    viewport_h: f32,
) -> Result<(), String> {
    let mut state = SNIP_STATE.lock().map_err(|e| e.to_string())?;
    let snip = state.take().ok_or("No snip state")?;

    if width <= 0.0 || height <= 0.0 {
        return Err("Invalid selection".into());
    }

    let scale_x = snip.width as f32 / viewport_w;
    let scale_y = snip.height as f32 / viewport_h;
    let sx = (x * scale_x).clamp(0.0, snip.width as f32) as u32;
    let sy = (y * scale_y).clamp(0.0, snip.height as f32) as u32;
    let sw = (width * scale_x).clamp(0.0, snip.width as f32 - sx as f32) as u32;
    let sh = (height * scale_y).clamp(0.0, snip.height as f32 - sy as f32) as u32;

    if sw == 0 || sh == 0 {
        return Err("Selection too small".into());
    }

    let mut cropped = Vec::with_capacity((sw * sh * 4) as usize);
    for row in sy..sy + sh {
        let start = (row * snip.width * 4 + sx * 4) as usize;
        let end = start + (sw * 4) as usize;
        cropped.extend_from_slice(&snip.image[start..end]);
    }
    let data_url = encode_png(&cropped, sw, sh)?;

    if let Some(main) = app.get_webview_window("main") {
        main.emit("snip-complete", data_url).map_err(|e| e.to_string())?;
        let _ = main.show();
        let _ = main.set_focus();
    }
    if let Some(win) = app.get_webview_window("snip-overlay") {
        let _ = win.close();
    }
    Ok(())
}

#[tauri::command]
/// Cancel the snip session and restore the main window.
pub fn cancel_snip(app: AppHandle) -> Result<(), String> {
    {
        let mut state = SNIP_STATE.lock().map_err(|e| e.to_string())?;
        *state = None;
    }
    if let Some(win) = app.get_webview_window("snip-overlay") {
        let _ = win.close();
    }
    if let Some(main) = app.get_webview_window("main") {
        main.emit("snip-cancel", ()).map_err(|e| e.to_string())?;
        let _ = main.show();
        let _ = main.set_focus();
    }
    Ok(())
}
