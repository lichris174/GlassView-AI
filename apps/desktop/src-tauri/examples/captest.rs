//! Standalone check that the `screenshots` crate can grab the screen on this machine.
//! Run: cargo run --example captest   (from apps/desktop/src-tauri)

use std::io::Write;

fn main() {
    match screenshots::Screen::all() {
        Ok(screens) => {
            println!("screens detected: {}", screens.len());
            for s in &screens {
                let d = &s.display_info;
                println!(
                    "  id={} {}x{} scale={} primary={}",
                    d.id, d.width, d.height, d.scale_factor, d.is_primary
                );
            }
        }
        Err(e) => {
            eprintln!("Screen::all ERROR: {e}");
            return;
        }
    }

    let screen = match screenshots::Screen::from_point(0, 0) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("from_point ERROR: {e}");
            return;
        }
    };

    match screen.capture() {
        Ok(img) => {
            println!("CAPTURE OK: {}x{}", img.width(), img.height());
            let mut out = Vec::new();
            {
                let mut enc = png::Encoder::new(&mut out, img.width(), img.height());
                enc.set_color(png::ColorType::Rgba);
                enc.set_depth(png::BitDepth::Eight);
                let mut w = enc.write_header().unwrap();
                w.write_image_data(img.rgba()).unwrap();
            }
            std::fs::File::create("captest.png")
                .unwrap()
                .write_all(&out)
                .unwrap();
            println!("wrote captest.png ({} bytes)", out.len());
        }
        Err(e) => eprintln!("CAPTURE ERROR: {e}"),
    }
}
