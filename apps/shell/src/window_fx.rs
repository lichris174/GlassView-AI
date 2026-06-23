//! Native window effects (Windows acrylic/dark-mode) for the glass look.

#[cfg(target_os = "windows")]
use tauri::Manager;

#[cfg(target_os = "windows")]
/// Apply acrylic-style backdrop + dark mode so CSS glass blends with the OS.
pub fn apply_acrylic(app: &tauri::AppHandle) {
    let Some(window) = app.get_webview_window("main") else {
        return;
    };
    let Ok(handle) = window.hwnd() else {
        return;
    };
    unsafe {
        use windows::Win32::Foundation::HWND;
        use windows::Win32::Graphics::Dwm::{DwmSetWindowAttribute, DWMWINDOWATTRIBUTE};

        const DWMWA_USE_IMMERSIVE_DARK_MODE: DWMWINDOWATTRIBUTE = DWMWINDOWATTRIBUTE(20);
        const DWMWA_SYSTEMBACKDROP_TYPE: DWMWINDOWATTRIBUTE = DWMWINDOWATTRIBUTE(38);
        const DWMSBT_TRANSIENTWINDOW: u32 = 3; // acrylic on Win11+

        let hwnd = HWND(handle.0);
        let enable_dark: u32 = 1;
        let backdrop: u32 = DWMSBT_TRANSIENTWINDOW;

        DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            &enable_dark as *const _ as _,
            std::mem::size_of::<u32>() as u32,
        )
        .ok();
        DwmSetWindowAttribute(
            hwnd,
            DWMWA_SYSTEMBACKDROP_TYPE,
            &backdrop as *const _ as _,
            std::mem::size_of::<u32>() as u32,
        )
        .ok();
    }
}

#[cfg(not(target_os = "windows"))]
pub fn apply_acrylic(_app: &tauri::AppHandle) {}
