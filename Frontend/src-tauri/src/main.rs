#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{Manager, Emitter};
use base64::Engine;
use std::sync::Mutex;
use tauri::{AppHandle, WebviewWindowBuilder, WebviewUrl};

#[tauri::command]
fn log_frontend(message: String) {
    println!("[frontend] {message}");
}

#[tauri::command]
fn capture_fullscreen() -> Result<String, String> {
    // Capture the primary screen and return a data URL.
    let screen = screenshots::Screen::from_point(0, 0).map_err(|e| e.to_string())?;
    let image = screen.capture().map_err(|e| e.to_string())?;

    let width = image.width() as u32;
    let height = image.height() as u32;
    let buffer = image.rgba().clone();

    let mut png_data = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut png_data, width, height);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        let mut writer = encoder.write_header().map_err(|e| e.to_string())?;
        writer
            .write_image_data(&buffer)
            .map_err(|e| e.to_string())?;
    }

    let b64 = base64::engine::general_purpose::STANDARD.encode(&png_data);
    Ok(format!("data:image/png;base64,{}", b64))
}

struct SnipState {
    image: Vec<u8>,
    width: u32,
    height: u32,
}

static SNIP_STATE: Mutex<Option<SnipState>> = Mutex::new(None);

#[tauri::command]
fn start_snip(app: AppHandle) -> Result<(), String> {
    println!("[snip] start_snip invoked");
    // Hide main window to avoid capturing it in the screenshot.
    if let Some(main) = app.get_webview_window("main") {
        if let Err(e) = main.hide() {
            println!("[snip] failed to hide main window: {e}");
        }
    }

    let screen = screenshots::Screen::from_point(0, 0)
        .map_err(|e| {
            println!("[snip] Screen::from_point error: {e}");
            e.to_string()
        })?;
    let image = screen.capture().map_err(|e| {
        println!("[snip] screen.capture error: {e}");
        e.to_string()
    })?;
    let width = image.width() as u32;
    let height = image.height() as u32;
    let buffer = image.rgba().clone();

    {
        let mut state = SNIP_STATE.lock().map_err(|e| e.to_string())?;
        *state = Some(SnipState {
            image: buffer.clone(),
            width,
            height,
        });
    }

    // Note: overlay will pull the image via get_snip_image()

    // Create overlay window if not exists
    if app.get_webview_window("snip-overlay").is_none() {
        println!("[snip] creating overlay window");
        if let Err(e) = WebviewWindowBuilder::new(
            &app,
            "snip-overlay",
            WebviewUrl::App("overlay.html".into()),
        )
        .transparent(false)
        .decorations(false)
        .focused(true)
        .fullscreen(true)
        .always_on_top(true)
        .visible(true)
        .resizable(false)
        .build() {
            println!("[snip] overlay build error: {e}");
            return Err(e.to_string());
        }
    }

    if let Some(win) = app.get_webview_window("snip-overlay") {
        println!("[snip] showing overlay window");
        if let Err(e) = win.show() {
            println!("[snip] overlay show error: {e}");
            if let Some(main) = app.get_webview_window("main") {
                let _ = main.show();
                let _ = main.set_focus();
            }
            return Err(e.to_string());
        }
        if let Err(e) = win.set_focus() {
            println!("[snip] overlay focus error: {e}");
        }
    } else {
        println!("[snip] overlay window not found after build");
        if let Some(main) = app.get_webview_window("main") {
            let _ = main.show();
            let _ = main.set_focus();
        }
        return Err("Overlay window missing".into());
    }

    Ok(())
}

#[tauri::command]
fn get_snip_image() -> Result<String, String> {
    println!("[snip] get_snip_image requested");
    let state = SNIP_STATE.lock().map_err(|e| e.to_string())?;
    let Some(snip) = state.as_ref() else {
        return Err("No snip state".into());
    };

    let mut png_data = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut png_data, snip.width, snip.height);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        let mut writer = encoder.write_header().map_err(|e| e.to_string())?;
        writer
            .write_image_data(&snip.image)
            .map_err(|e| e.to_string())?;
    }
    let b64 = base64::engine::general_purpose::STANDARD.encode(&png_data);
    Ok(format!("data:image/png;base64,{}", b64))
}

#[tauri::command]
fn finish_snip(
    app: AppHandle,
    x: f32,
    y: f32,
    width: f32,
    height: f32,
    viewport_w: f32,
    viewport_h: f32,
) -> Result<(), String> {
    println!("[snip] finish_snip received selection x={x} y={y} w={width} h={height}");
    let mut state = SNIP_STATE.lock().map_err(|e| e.to_string())?;
    let Some(snip) = state.take() else {
        return Err("No snip state".into());
    };

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

    let mut png_data = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut png_data, sw, sh);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        let mut writer = encoder.write_header().map_err(|e| e.to_string())?;

        let mut cropped = Vec::with_capacity((sw * sh * 4) as usize);
        for row in sy..sy + sh {
            let start = (row * snip.width * 4 + sx * 4) as usize;
            let end = start + (sw * 4) as usize;
            cropped.extend_from_slice(&snip.image[start..end]);
        }

        writer
            .write_image_data(&cropped)
            .map_err(|e| e.to_string())?;
    }

    let b64 = base64::engine::general_purpose::STANDARD.encode(&png_data);
    let data_url = format!("data:image/png;base64,{}", b64);

    if let Some(main) = app.get_webview_window("main") {
        main.emit("snip-complete", data_url)
            .map_err(|e| e.to_string())?;
        let _ = main.show();
        let _ = main.set_focus();
    }

    if let Some(win) = app.get_webview_window("snip-overlay") {
        let _ = win.close();
    }

    Ok(())
}

#[tauri::command]
fn cancel_snip(app: AppHandle) -> Result<(), String> {
    println!("[snip] cancel_snip invoked");
    {
        let mut state = SNIP_STATE.lock().map_err(|e| e.to_string())?;
        *state = None;
    }

    if let Some(win) = app.get_webview_window("snip-overlay") {
        let _ = win.close();
    }

    if let Some(main) = app.get_webview_window("main") {
        main
            .emit("snip-cancel", ())
            .map_err(|e| e.to_string())?;
        let _ = main.show();
        let _ = main.set_focus();
    }

    Ok(())
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            log_frontend,
            capture_fullscreen,
            start_snip,
            get_snip_image,
            finish_snip,
            cancel_snip
        ])
        .setup(|app| {
            #[cfg(target_os = "windows")]
            {
                if let Some(window) = app.get_webview_window("main") {
                    if let Ok(handle) = window.hwnd() {
                        // Enable acrylic-style blur and dark mode so CSS backdrop-filter
                        // can blend with the OS background instead of a flat color.
                        unsafe {
                            use windows::Win32::Foundation::HWND;
                            use windows::Win32::Graphics::Dwm::{
                                DwmSetWindowAttribute, DWMWINDOWATTRIBUTE,
                            };

                            const DWMWA_USE_IMMERSIVE_DARK_MODE: DWMWINDOWATTRIBUTE =
                                DWMWINDOWATTRIBUTE(20);
                            const DWMWA_SYSTEMBACKDROP_TYPE: DWMWINDOWATTRIBUTE =
                                DWMWINDOWATTRIBUTE(38);
                            // 3 = DWMSBT_TRANSIENTWINDOW (acrylic) on Win11+
                            const DWMSBT_TRANSIENTWINDOW: u32 = 3;

                            let hwnd = HWND(handle.0);
                            let enable_dark: u32 = 1;
                            let backdrop: u32 = DWMSBT_TRANSIENTWINDOW;

                            // Dark mode helps the glass look consistent with the chrome.
                            DwmSetWindowAttribute(
                                hwnd,
                                DWMWA_USE_IMMERSIVE_DARK_MODE,
                                &enable_dark as *const _ as _,
                                std::mem::size_of::<u32>() as u32,
                            )
                            .ok();

                            // Acrylic-style blur behind the transparent window.
                            DwmSetWindowAttribute(
                                hwnd,
                                DWMWA_SYSTEMBACKDROP_TYPE,
                                &backdrop as *const _ as _,
                                std::mem::size_of::<u32>() as u32,
                            )
                            .ok();
                        }
                    }
                }
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
