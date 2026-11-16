// Windows stand-in for the PS3 native plugin RainPS3Utility.sprx (M7 platform layer, NOT reconstructed code).
// The reconstructed RainPS3Utility.cs P/Invokes these three symbols unchanged.
// Build: rustc --crate-type cdylib -C opt-level=2 -C panic=abort -o RainPS3Utility.dll tools/native/RainPS3Utility.rs
//   -> copy to <Unity project>/Assets/Plugins/x86_64/RainPS3Utility.dll
use std::sync::atomic::{AtomicU32, Ordering};

// CELL_SYSUTIL_LANG_*: 0 Japanese, 1 English (US), 2 French, 3 Spanish, 4 German, 5 Italian, ... Override with the
// environment variable RAIN_PS3_LANG=<number>; default 1 (NPUA80719 is the US release).
#[no_mangle]
pub extern "C" fn GetSystemLanguage() -> i32 {
    std::env::var("RAIN_PS3_LANG").ok().and_then(|v| v.parse().ok()).unwrap_or(1)
}

static GAMMA: AtomicU32 = AtomicU32::new(0x3f80_0000); // 1.0f

#[no_mangle]
pub extern "C" fn GetVideoOutGamma() -> f32 { f32::from_bits(GAMMA.load(Ordering::Relaxed)) }

#[no_mangle]
pub extern "C" fn SetVideoOutGamma(gamma: f32) { GAMMA.store(gamma.to_bits(), Ordering::Relaxed) }
