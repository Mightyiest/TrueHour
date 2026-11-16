#[cfg(windows)]
fn to_short_path_if_needed(path: &str) -> String {
    if !path.contains(' ') {
        return path.to_string();
    }
    use std::ffi::OsString;
    use std::os::windows::ffi::{OsStrExt, OsStringExt};

    #[link(name = "kernel32")]
    extern "system" {
        fn GetShortPathNameW(
            lpszlongpath: *const u16,
            lpszshortpath: *mut u16,
            cchbuffer: u32,
        ) -> u32;
    }

    let wide: Vec<u16> = std::ffi::OsStr::new(path)
        .encode_wide()
        .chain(std::iter::once(0))
        .collect();
    let needed = unsafe { GetShortPathNameW(wide.as_ptr(), std::ptr::null_mut(), 0) };
    if needed == 0 {
        return path.to_string();
    }
    let mut buf = vec![0u16; needed as usize];
    let written = unsafe { GetShortPathNameW(wide.as_ptr(), buf.as_mut_ptr(), needed) };
    if written > 0 && (written as usize) < buf.len() {
        let os = OsString::from_wide(&buf[..written as usize]);
        if let Some(s) = os.to_str() {
            return s.to_string();
        }
    }
    path.to_string()
}

fn main() {
    println!("cargo:rerun-if-changed=icons/icon.ico");

    #[cfg(windows)]
    {
        let target_os = std::env::var("CARGO_CFG_TARGET_OS").unwrap_or_default();
        if target_os != "windows" {
            return;
        }
        let target_env = std::env::var("CARGO_CFG_TARGET_ENV").unwrap_or_default();
        let Ok(out_dir_raw) = std::env::var("OUT_DIR") else {
            return;
        };
        let short_out = to_short_path_if_needed(&out_dir_raw);
        let out_path = std::path::Path::new(&short_out);

        let manifest_dir = std::env::var("CARGO_MANIFEST_DIR").unwrap_or_else(|_| ".".to_string());
        let icon_src = std::path::Path::new(&manifest_dir)
            .join("icons")
            .join("icon.ico");
        if !icon_src.exists() {
            println!("cargo:warning=Missing icons/icon.ico; skipping Windows exe icon embed");
            return;
        }

        let icon_dst = out_path.join("icon.ico");
        if std::fs::copy(&icon_src, &icon_dst).is_err() {
            println!("cargo:warning=Failed copying icon.ico to OUT_DIR");
            return;
        }

        let rc_content = r#"1 ICON "icon.ico"

1 VERSIONINFO
FILEVERSION     5,0,0,0
PRODUCTVERSION  5,0,0,0
FILEFLAGSMASK   0x3fL
FILEFLAGS       0x0L
FILEOS          0x40004L
FILETYPE        0x1L
FILESUBTYPE     0x0L
BEGIN
    BLOCK "StringFileInfo"
    BEGIN
        BLOCK "040904B0"
        BEGIN
            VALUE "CompanyName",      "TrueHour"
            VALUE "FileDescription",  "TrueHour Focus & Time Tracker"
            VALUE "FileVersion",      "5.0.0.0"
            VALUE "InternalName",     "truehour"
            VALUE "LegalCopyright",   "TrueHour"
            VALUE "OriginalFilename", "truehour.exe"
            VALUE "ProductName",      "TrueHour"
            VALUE "ProductVersion",   "5.0.0"
        END
    END
    BLOCK "VarFileInfo"
    BEGIN
        VALUE "Translation", 0x0409, 1200
    END
END
"#;
        let rc_path = out_path.join("app_icon.rc");
        if std::fs::write(&rc_path, rc_content).is_err() {
            println!("cargo:warning=Failed writing app_icon.rc");
            return;
        }

        if target_env == "gnu" {
            let res_obj = out_path.join("icon_res.o");
            let status = std::process::Command::new("windres")
                .args(["--use-temp-file", "-I"])
                .arg(&short_out)
                .arg(&rc_path)
                .args(["-O", "coff", "-o"])
                .arg(&res_obj)
                .status();
            match status {
                Ok(st) if st.success() && res_obj.exists() => {
                    let arg = res_obj.to_string_lossy().replace('\\', "/");
                    println!("cargo:rustc-link-arg-bins={arg}");
                }
                Ok(st) => {
                    println!("cargo:warning=windres exited with {st}; exe will lack embedded icon");
                }
                Err(e) => {
                    println!("cargo:warning=windres not available ({e}); exe will lack embedded icon");
                }
            }
        } else if target_env == "msvc" {
            let res_file = out_path.join("icon_res.res");
            let status = std::process::Command::new("rc.exe")
                .args(["/nologo", "/fo"])
                .arg(&res_file)
                .arg(&rc_path)
                .status();
            if matches!(status, Ok(st) if st.success()) && res_file.exists() {
                let arg = res_file.to_string_lossy().replace('\\', "/");
                println!("cargo:rustc-link-arg-bins={arg}");
            }
        }
    }
}
