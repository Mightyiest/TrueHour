use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use image::codecs::png::PngEncoder;
use image::{ColorType, ImageEncoder};
use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::Path;
use std::sync::{Arc, Mutex};

const DEFAULT_OVERRIDES_CONTENT: &str = "# Add your custom app name overrides here. Format: exename=Friendly Name\n# Example: chrome=Google Chrome\n";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ForegroundApp {
    pub friendly_name: String,
    pub exe_path: String,
}

#[derive(Debug, Clone, Default)]
pub struct ExeVersionInfo {
    pub file_description: Option<String>,
    pub company_name: Option<String>,
    pub product_name: Option<String>,
}

pub struct AppResolver {
    overrides_file: Mutex<std::path::PathBuf>,
    overrides: Mutex<HashMap<String, String>>,
    name_cache: Mutex<HashMap<(String, String), String>>,
    version_cache: Mutex<HashMap<String, ExeVersionInfo>>,
    icon_cache: Mutex<HashMap<(String, u32), Option<String>>>,
    raw_icon_cache: Mutex<HashMap<(String, u32), Option<Arc<[u8]>>>>,
}

impl AppResolver {
    pub fn new(overrides_file: std::path::PathBuf) -> Arc<Self> {
        let resolver = Arc::new(Self {
            overrides_file: Mutex::new(overrides_file),
            overrides: Mutex::new(HashMap::new()),
            name_cache: Mutex::new(HashMap::new()),
            version_cache: Mutex::new(HashMap::new()),
            icon_cache: Mutex::new(HashMap::new()),
            raw_icon_cache: Mutex::new(HashMap::new()),
        });
        resolver.reload_name_overrides();
        resolver
    }

    pub fn set_overrides_file_and_reload(&self, new_path: std::path::PathBuf) {
        *self.overrides_file.lock().unwrap() = new_path;
        self.reload_name_overrides();
    }

    pub fn reload_name_overrides(&self) {
        let path = self.overrides_file.lock().unwrap().clone();
        if !path.exists() {
            if let Some(parent) = path.parent() {
                let _ = fs::create_dir_all(parent);
            }
            let _ = fs::write(&path, DEFAULT_OVERRIDES_CONTENT);
        }

        let mut map = HashMap::new();
        if let Ok(raw) = fs::read_to_string(&path) {
            for line in raw.lines() {
                let trimmed = line.trim();
                if !trimmed.is_empty() && !trimmed.starts_with('#') {
                    if let Some((k, v)) = trimmed.split_once('=') {
                        let key = k.trim().to_lowercase();
                        let val = v.trim().to_string();
                        if !key.is_empty() && !val.is_empty() {
                            map.insert(key, val);
                        }
                    }
                }
            }
        }
        *self.overrides.lock().unwrap() = map;
        self.name_cache.lock().unwrap().clear();
    }

    pub fn resolve_name(&self, exe_path: &str, base_name: &str) -> String {
        let key_pair = (exe_path.to_string(), base_name.to_string());
        if let Some(cached) = self.name_cache.lock().unwrap().get(&key_pair) {
            return cached.clone();
        }

        let lower_base = base_name.trim().to_lowercase();
        let mut resolved = self.overrides.lock().unwrap().get(&lower_base).cloned();

        if resolved.is_none() && !exe_path.is_empty() {
            resolved = self.get_version_info(exe_path).file_description;
        }

        let final_name = resolved.unwrap_or_else(|| title_case_app_name(base_name));

        let mut cache = self.name_cache.lock().unwrap();
        if cache.len() >= 512 {
            cache.clear();
        }
        cache.insert(key_pair, final_name.clone());
        final_name
    }

    pub fn get_version_info(&self, exe_path: &str) -> ExeVersionInfo {
        if exe_path.is_empty() {
            return ExeVersionInfo::default();
        }
        if let Some(cached) = self.version_cache.lock().unwrap().get(exe_path) {
            return cached.clone();
        }
        let info = query_pe_version_info(exe_path);
        let mut cache = self.version_cache.lock().unwrap();
        if cache.len() >= 512 {
            cache.clear();
        }
        cache.insert(exe_path.to_string(), info.clone());
        info
    }

    pub fn get_foreground_app_info(&self) -> ForegroundApp {
        #[cfg(windows)]
        {
            match win32::get_foreground_pid() {
                None => ForegroundApp {
                    friendly_name: "[Idle]".to_string(),
                    exe_path: String::new(),
                },
                Some(pid) if pid == std::process::id() => ForegroundApp {
                    friendly_name: "TrueHour".to_string(),
                    exe_path: "truehour.exe".to_string(),
                },
                Some(pid) => {
                    let exe_path = win32::get_process_image_path(pid).unwrap_or_default();
                    let base_from_path = if !exe_path.is_empty() {
                        Path::new(&exe_path)
                            .file_stem()
                            .and_then(|s| s.to_str())
                            .unwrap_or("")
                            .to_string()
                    } else {
                        String::new()
                    };

                    let base = if !base_from_path.is_empty() {
                        base_from_path
                    } else {
                        win32::get_process_name_via_snapshot(pid).unwrap_or_default()
                    };

                    if !exe_path.is_empty() {
                        ForegroundApp {
                            friendly_name: self.resolve_name(&exe_path, &base),
                            exe_path,
                        }
                    } else if !base.is_empty() {
                        ForegroundApp {
                            friendly_name: self.resolve_name("", &base),
                            exe_path: String::new(),
                        }
                    } else {
                        ForegroundApp {
                            friendly_name: "[Protected System App]".to_string(),
                            exe_path: String::new(),
                        }
                    }
                }
            }
        }
        #[cfg(not(windows))]
        {
            ForegroundApp {
                friendly_name: "[Idle]".to_string(),
                exe_path: String::new(),
            }
        }
    }

    /// Extracts transparent RGBA PNG icon data URL (`data:image/png;base64,...`) cached by path.
    pub fn get_icon_data_url(&self, exe_path: &str, size: u32) -> Option<String> {
        if exe_path.is_empty() || exe_path.eq_ignore_ascii_case("truehour.exe") {
            return None;
        }
        let key = (exe_path.to_string(), size);
        if let Some(cached) = self.icon_cache.lock().unwrap().get(&key) {
            return cached.clone();
        }

        let data_url = extract_icon_png_data_url(exe_path, size);
        let mut cache = self.icon_cache.lock().unwrap();
        if cache.len() >= 512 {
            cache.clear();
        }
        cache.insert(key, data_url.clone());
        data_url
    }

    /// Extracts transparent `size x size` RGBA pixel bytes directly (zero PNG/base64 overhead).
    pub fn get_icon_rgba(&self, exe_path: &str, size: u32) -> Option<Arc<[u8]>> {
        if exe_path.is_empty() || exe_path.eq_ignore_ascii_case("truehour.exe") {
            return None;
        }
        let key = (exe_path.to_string(), size);
        if let Some(cached) = self.raw_icon_cache.lock().unwrap().get(&key) {
            return cached.clone();
        }

        #[cfg(windows)]
        let raw_opt: Option<Arc<[u8]>> = win32::extract_icon_rgba(exe_path, size).map(Arc::from);
        #[cfg(not(windows))]
        let raw_opt: Option<Arc<[u8]>> = None;

        let mut cache = self.raw_icon_cache.lock().unwrap();
        if cache.len() >= 512 {
            cache.clear();
        }
        cache.insert(key, raw_opt.clone());
        raw_opt
    }
}

#[cfg_attr(not(test), allow(dead_code))]
pub(crate) fn is_descendant_in_process_map(
    pid: u32,
    ancestor_pid: u32,
    parent_by_pid: &HashMap<u32, u32>,
) -> bool {
    if pid == 0 || ancestor_pid == 0 || pid == ancestor_pid {
        return false;
    }
    let mut visited = HashSet::new();
    let mut curr = pid;
    while visited.insert(curr) {
        let Some(&ppid) = parent_by_pid.get(&curr) else {
            return false;
        };
        if ppid == ancestor_pid {
            return true;
        }
        if ppid == 0 || ppid == curr {
            return false;
        }
        curr = ppid;
    }
    false
}

pub fn title_case_app_name(base_name: &str) -> String {
    let cleaned = base_name.replace(['_', '-'], " ");
    cleaned
        .split_whitespace()
        .map(|word| {
            let mut chars = word.chars();
            match chars.next() {
                None => String::new(),
                Some(first) => {
                    let up: String = first.to_uppercase().collect();
                    let rest: String = chars.as_str().to_lowercase();
                    format!("{up}{rest}")
                }
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

#[cfg(windows)]
fn query_pe_version_info(exe_path: &str) -> ExeVersionInfo {
    win32::read_pe_version_info(exe_path)
}

#[cfg(not(windows))]
fn query_pe_version_info(_exe_path: &str) -> ExeVersionInfo {
    ExeVersionInfo::default()
}

pub fn extract_icon_png_data_url(exe_path: &str, size: u32) -> Option<String> {
    #[cfg(windows)]
    {
        let rgba = win32::extract_icon_rgba(exe_path, size)?;
        let mut png_bytes = Vec::new();
        let encoder = PngEncoder::new(&mut png_bytes);
        encoder
            .write_image(&rgba, size, size, ColorType::Rgba8.into())
            .ok()?;
        let b64 = STANDARD.encode(png_bytes);
        Some(format!("data:image/png;base64,{b64}"))
    }
    #[cfg(not(windows))]
    {
        let _ = (exe_path, size);
        None
    }
}

#[cfg(windows)]
pub mod win32 {
    use super::ExeVersionInfo;
    use std::ffi::c_void;
    use std::mem;
    use windows::core::{BOOL, PCWSTR, PWSTR};
    use windows::Win32::Foundation::{CloseHandle, HANDLE, HWND};
    use windows::Win32::Graphics::Gdi::*;
    use windows::Win32::Storage::FileSystem::{
        GetFileVersionInfoSizeW, GetFileVersionInfoW, VerQueryValueW,
    };
    use windows::Win32::System::Diagnostics::ToolHelp::{
        CreateToolhelp32Snapshot, Process32FirstW, Process32NextW, PROCESSENTRY32W,
        TH32CS_SNAPPROCESS,
    };
    use windows::Win32::System::Threading::{
        OpenProcess, QueryFullProcessImageNameW, PROCESS_NAME_FORMAT,
        PROCESS_QUERY_LIMITED_INFORMATION,
    };
    use windows::Win32::UI::Shell::ExtractIconExW;
    use windows::Win32::UI::WindowsAndMessaging::{
        DestroyIcon, DrawIconEx, GetForegroundWindow, GetWindowThreadProcessId, DI_MASK,
        DI_NORMAL, HICON,
    };

    struct HandleGuard(HANDLE);
    impl Drop for HandleGuard {
        fn drop(&mut self) {
            if !self.0.is_invalid() {
                unsafe {
                    let _ = CloseHandle(self.0);
                }
            }
        }
    }

    struct IconGuard(HICON);
    impl Drop for IconGuard {
        fn drop(&mut self) {
            if !self.0.is_invalid() {
                unsafe {
                    let _ = DestroyIcon(self.0);
                }
            }
        }
    }

    struct ScreenDcGuard(HWND, HDC);
    impl Drop for ScreenDcGuard {
        fn drop(&mut self) {
            if !self.1.is_invalid() {
                unsafe {
                    ReleaseDC(Some(self.0), self.1);
                }
            }
        }
    }

    struct MemDcGuard(HDC);
    impl Drop for MemDcGuard {
        fn drop(&mut self) {
            if !self.0.is_invalid() {
                unsafe {
                    let _ = DeleteDC(self.0);
                }
            }
        }
    }

    struct BitmapGuard(HBITMAP);
    impl Drop for BitmapGuard {
        fn drop(&mut self) {
            if !self.0.is_invalid() {
                unsafe {
                    let _ = DeleteObject(self.0.into());
                }
            }
        }
    }

    struct SelectGuard(HDC, HGDIOBJ);
    impl Drop for SelectGuard {
        fn drop(&mut self) {
            if !self.0.is_invalid() && !self.1.is_invalid() {
                unsafe {
                    SelectObject(self.0, self.1);
                }
            }
        }
    }

    pub fn get_foreground_pid() -> Option<u32> {
        unsafe {
            let hwnd = GetForegroundWindow();
            if hwnd.0.is_null() {
                return None;
            }
            let mut pid: u32 = 0;
            GetWindowThreadProcessId(hwnd, Some(&mut pid));
            if pid == 0 {
                None
            } else {
                Some(pid)
            }
        }
    }

    pub fn get_process_image_path(pid: u32) -> Option<String> {
        unsafe {
            let handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid).ok()?;
            let _guard = HandleGuard(handle);
            let mut buf = vec![0u16; 1024];
            let mut size = buf.len() as u32;
            QueryFullProcessImageNameW(
                handle,
                PROCESS_NAME_FORMAT(0),
                PWSTR(buf.as_mut_ptr()),
                &mut size,
            )
            .ok()?;
            let path = String::from_utf16_lossy(&buf[..size as usize]);
            if path.is_empty() {
                None
            } else {
                Some(path)
            }
        }
    }

    pub fn get_process_name_via_snapshot(pid: u32) -> Option<String> {
        unsafe {
            let snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0).ok()?;
            let _guard = HandleGuard(snap);
            let mut entry: PROCESSENTRY32W = mem::zeroed();
            entry.dwSize = mem::size_of::<PROCESSENTRY32W>() as u32;
            if Process32FirstW(snap, &mut entry).is_ok() {
                loop {
                    if entry.th32ProcessID == pid {
                        let len = entry
                            .szExeFile
                            .iter()
                            .position(|&c| c == 0)
                            .unwrap_or(entry.szExeFile.len());
                        let name = String::from_utf16_lossy(&entry.szExeFile[..len]);
                        let base = if name.to_lowercase().ends_with(".exe") {
                            name[..name.len() - 4].to_string()
                        } else {
                            name
                        };
                        return if base.is_empty() { None } else { Some(base) };
                    }
                    if Process32NextW(snap, &mut entry).is_err() {
                        break;
                    }
                }
            }
            None
        }
    }

    #[cfg_attr(not(test), allow(dead_code))]
    pub fn collect_process_parent_map() -> Option<std::collections::HashMap<u32, u32>> {
        unsafe {
            let snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0).ok()?;
            let _guard = HandleGuard(snap);
            let mut entry: PROCESSENTRY32W = mem::zeroed();
            entry.dwSize = mem::size_of::<PROCESSENTRY32W>() as u32;
            let mut parent_by_pid = std::collections::HashMap::new();
            if Process32FirstW(snap, &mut entry).is_ok() {
                loop {
                    parent_by_pid.insert(entry.th32ProcessID, entry.th32ParentProcessID);
                    if Process32NextW(snap, &mut entry).is_err() {
                        break;
                    }
                }
            }
            Some(parent_by_pid)
        }
    }

    #[cfg_attr(not(test), allow(dead_code))]
    pub fn is_child_of_current_process(pid: u32) -> bool {
        let my_pid = std::process::id();
        if pid == 0 || pid == my_pid {
            return false;
        }
        let Some(parent_by_pid) = collect_process_parent_map() else {
            return false;
        };
        super::is_descendant_in_process_map(pid, my_pid, &parent_by_pid)
    }

    pub fn read_pe_version_info(exe_path: &str) -> ExeVersionInfo {
        let mut info = ExeVersionInfo::default();
        let path_w: Vec<u16> = exe_path.encode_utf16().chain(std::iter::once(0)).collect();

        unsafe {
            let size = GetFileVersionInfoSizeW(PCWSTR(path_w.as_ptr()), None);
            if size == 0 {
                return info;
            }
            let mut data = vec![0u8; size as usize];
            if GetFileVersionInfoW(
                PCWSTR(path_w.as_ptr()),
                Some(0),
                size,
                data.as_mut_ptr() as *mut c_void,
            )
            .is_err()
            {
                return info;
            }

            let mut codepages: Vec<String> = Vec::new();
            let trans_q: Vec<u16> = "\\VarFileInfo\\Translation\0".encode_utf16().collect();
            let mut trans_ptr: *mut c_void = std::ptr::null_mut();
            let mut trans_len: u32 = 0;
            if VerQueryValueW(
                data.as_ptr() as *const c_void,
                PCWSTR(trans_q.as_ptr()),
                &mut trans_ptr,
                &mut trans_len,
            ) == BOOL(1)
                && !trans_ptr.is_null()
                && trans_len >= 4
            {
                let pairs = (trans_len as usize) / 4;
                let words = std::slice::from_raw_parts(trans_ptr as *const u16, pairs * 2);
                for chunk in words.chunks_exact(2) {
                    codepages.push(format!("{:04X}{:04X}", chunk[0], chunk[1]));
                }
            }
            for fallback in ["040904B0", "040904E4", "000004B0"] {
                if !codepages.iter().any(|c| c == fallback) {
                    codepages.push(fallback.to_string());
                }
            }

            let query_field = |field: &str| -> Option<String> {
                for cp in &codepages {
                    let sub_w: Vec<u16> = format!("\\StringFileInfo\\{cp}\\{field}\0")
                        .encode_utf16()
                        .collect();
                    let mut val_ptr: *mut c_void = std::ptr::null_mut();
                    let mut val_len: u32 = 0;
                    if VerQueryValueW(
                        data.as_ptr() as *const c_void,
                        PCWSTR(sub_w.as_ptr()),
                        &mut val_ptr,
                        &mut val_len,
                    ) == BOOL(1)
                        && !val_ptr.is_null()
                        && val_len > 0
                    {
                        let slice =
                            std::slice::from_raw_parts(val_ptr as *const u16, val_len as usize);
                        let trimmed_len = slice.iter().position(|&c| c == 0).unwrap_or(slice.len());
                        let s = String::from_utf16_lossy(&slice[..trimmed_len])
                            .trim()
                            .to_string();
                        if !s.is_empty() {
                            return Some(s);
                        }
                    }
                }
                None
            };

            info.file_description = query_field("FileDescription");
            info.company_name = query_field("CompanyName");
            info.product_name = query_field("ProductName");
        }
        info
    }

    pub fn extract_icon_rgba(exe_path: &str, size: u32) -> Option<Vec<u8>> {
        if size == 0 {
            return None;
        }
        let path_w: Vec<u16> = exe_path.encode_utf16().chain(std::iter::once(0)).collect();
        unsafe {
            let mut large = HICON::default();
            let mut small = HICON::default();
            let count = ExtractIconExW(
                PCWSTR(path_w.as_ptr()),
                0,
                Some(&mut large),
                Some(&mut small),
                1,
            );
            let _g_large = IconGuard(large);
            let _g_small = IconGuard(small);
            if count == 0 {
                return None;
            }

            let hicon = if size <= 16 && !small.is_invalid() {
                small
            } else if !large.is_invalid() {
                large
            } else {
                small
            };
            if hicon.is_invalid() {
                return None;
            }

            let screen_dc = GetDC(None);
            if screen_dc.is_invalid() {
                return None;
            }
            let _g_screen = ScreenDcGuard(HWND::default(), screen_dc);

            let mem_dc = CreateCompatibleDC(Some(screen_dc));
            if mem_dc.is_invalid() {
                return None;
            }
            let _g_mem = MemDcGuard(mem_dc);

            let mut bmi: BITMAPINFO = mem::zeroed();
            bmi.bmiHeader.biSize = mem::size_of::<BITMAPINFOHEADER>() as u32;
            bmi.bmiHeader.biWidth = size as i32;
            bmi.bmiHeader.biHeight = -(size as i32); // top-down DIB
            bmi.bmiHeader.biPlanes = 1;
            bmi.bmiHeader.biBitCount = 32;
            bmi.bmiHeader.biCompression = BI_RGB.0;

            let mut bits_ptr: *mut c_void = std::ptr::null_mut();
            let bmp = CreateDIBSection(
                Some(screen_dc),
                &bmi,
                DIB_RGB_COLORS,
                &mut bits_ptr,
                None,
                0,
            )
            .ok()?;
            let _g_bmp = BitmapGuard(bmp);
            if bits_ptr.is_null() {
                return None;
            }

            let byte_len = (size * size * 4) as usize;
            std::ptr::write_bytes(bits_ptr as *mut u8, 0, byte_len);

            let old_obj = SelectObject(mem_dc, bmp.into());
            let _g_select = SelectGuard(mem_dc, old_obj);

            if DrawIconEx(
                mem_dc,
                0,
                0,
                hicon,
                size as i32,
                size as i32,
                0,
                None,
                DI_NORMAL,
            )
            .is_err()
            {
                return None;
            }
            let _ = GdiFlush();

            let src_slice = std::slice::from_raw_parts(bits_ptr as *const u8, byte_len);
            let mut rgba = vec![0u8; byte_len];
            let mut has_non_zero_alpha = false;
            let mut has_non_zero_rgb = false;

            for (src, dst) in src_slice.chunks_exact(4).zip(rgba.chunks_exact_mut(4)) {
                let b = src[0];
                let g = src[1];
                let r = src[2];
                let a = src[3];
                if a > 0 {
                    has_non_zero_alpha = true;
                }
                if b > 0 || g > 0 || r > 0 {
                    has_non_zero_rgb = true;
                }
                dst[0] = r;
                dst[1] = g;
                dst[2] = b;
                dst[3] = a;
            }

            // Legacy non-alpha mask icons leave alpha bytes at 0: recover transparency from DI_MASK.
            if !has_non_zero_alpha && has_non_zero_rgb {
                let mut mask_bits_ptr: *mut c_void = std::ptr::null_mut();
                if let Ok(mask_bmp) = CreateDIBSection(
                    Some(screen_dc),
                    &bmi,
                    DIB_RGB_COLORS,
                    &mut mask_bits_ptr,
                    None,
                    0,
                ) {
                    let _g_mask_bmp = BitmapGuard(mask_bmp);
                    if !mask_bits_ptr.is_null() {
                        std::ptr::write_bytes(mask_bits_ptr as *mut u8, 0xFF, byte_len);
                        let prev = SelectObject(mem_dc, mask_bmp.into());
                        let _g_mask_sel = SelectGuard(mem_dc, prev);
                        if DrawIconEx(
                            mem_dc,
                            0,
                            0,
                            hicon,
                            size as i32,
                            size as i32,
                            0,
                            None,
                            DI_MASK,
                        )
                        .is_ok()
                        {
                            let _ = GdiFlush();
                            let mask_slice =
                                std::slice::from_raw_parts(mask_bits_ptr as *const u8, byte_len);
                            for (m_px, dst_px) in
                                mask_slice.chunks_exact(4).zip(rgba.chunks_exact_mut(4))
                            {
                                // In DI_MASK onto white background: opaque=0x00, transparent=0xFF.
                                dst_px[3] = if m_px[0] < 128 { 255 } else { 0 };
                            }
                        }
                    }
                }
            }

            Some(rgba)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_name_overrides_and_title_case() {
        let tmp = TempDir::new().unwrap();
        let overrides_path = tmp.path().join("name_overrides.txt");
        fs::write(
            &overrides_path,
            "# Comment line\nmy_custom_cli = Super Custom CLI\n",
        )
        .unwrap();

        let resolver = AppResolver::new(overrides_path);
        assert_eq!(resolver.resolve_name("", "my_custom_cli"), "Super Custom CLI");
        assert_eq!(resolver.resolve_name("", "hello-world_app"), "Hello World App");
    }

    #[cfg(windows)]
    #[test]
    fn test_icon_extraction_no_gdi_handle_leak() {
        use windows::Win32::System::Threading::{GetCurrentProcess, GetGuiResources, GR_GDIOBJECTS};

        let sys_dir = std::env::var("SystemRoot").unwrap_or_else(|_| "C:\\Windows".to_string());
        let explorer = format!("{sys_dir}\\explorer.exe");
        if !Path::new(&explorer).exists() {
            return;
        }

        // Warm once to initialize GDI/image allocations
        let first = extract_icon_png_data_url(&explorer, 32);
        assert!(first.is_some());

        let proc = unsafe { GetCurrentProcess() };
        let before = unsafe { GetGuiResources(proc, GR_GDIOBJECTS) };

        for _ in 0..50 {
            let out = extract_icon_png_data_url(&explorer, 16);
            assert!(out.is_some());
        }

        let after = unsafe { GetGuiResources(proc, GR_GDIOBJECTS) };
        assert!(
            after <= before + 2,
            "GDI handles leaked during icon extraction: before={before}, after={after}"
        );
    }

    #[test]
    fn test_is_descendant_in_process_map_multihop_and_edge_cases() {
        let my_pid = 1000;
        let mut parent_by_pid = HashMap::new();
        // 1-hop WebView2 browser process under truehour.exe
        parent_by_pid.insert(2000, my_pid);
        // 2-hop WebView2 renderer process under browser process
        parent_by_pid.insert(3000, 2000);
        // 3-hop WebView2 child process under renderer
        parent_by_pid.insert(4000, 3000);

        // Unrelated tree
        parent_by_pid.insert(500, 4);
        parent_by_pid.insert(5000, 500);

        // Cycle & self-loop
        parent_by_pid.insert(6000, 6001);
        parent_by_pid.insert(6001, 6000);
        parent_by_pid.insert(7000, 7000);

        assert!(is_descendant_in_process_map(2000, my_pid, &parent_by_pid));
        assert!(is_descendant_in_process_map(3000, my_pid, &parent_by_pid));
        assert!(is_descendant_in_process_map(4000, my_pid, &parent_by_pid));

        assert!(!is_descendant_in_process_map(my_pid, my_pid, &parent_by_pid));
        assert!(!is_descendant_in_process_map(0, my_pid, &parent_by_pid));
        assert!(!is_descendant_in_process_map(5000, my_pid, &parent_by_pid));
        assert!(!is_descendant_in_process_map(6000, my_pid, &parent_by_pid));
        assert!(!is_descendant_in_process_map(7000, my_pid, &parent_by_pid));
        assert!(!is_descendant_in_process_map(9999, my_pid, &parent_by_pid));
    }

    #[cfg(windows)]
    #[test]
    fn test_win32_is_child_of_current_process_multilevel_real_processes() {
        use std::os::windows::process::CommandExt;
        use std::process::Command;
        use windows::Win32::Foundation::CloseHandle;
        use windows::Win32::System::Threading::{OpenProcess, TerminateProcess, PROCESS_TERMINATE};

        const CREATE_NO_WINDOW: u32 = 0x0800_0000;

        assert!(!win32::is_child_of_current_process(0));
        assert!(!win32::is_child_of_current_process(std::process::id()));

        struct TreeGuard {
            child: Option<std::process::Child>,
            grandchild_pid: Option<u32>,
        }
        impl Drop for TreeGuard {
            fn drop(&mut self) {
                if let Some(gc_pid) = self.grandchild_pid {
                    unsafe {
                        if let Ok(h) = OpenProcess(PROCESS_TERMINATE, false, gc_pid) {
                            let _ = TerminateProcess(h, 1);
                            let _ = CloseHandle(h);
                        }
                    }
                }
                if let Some(ref mut ch) = self.child {
                    let _ = ch.kill();
                    let _ = ch.wait();
                }
            }
        }

        let child = Command::new("cmd.exe")
            .args(["/d", "/c", "ping -n 30 127.0.0.1 >nul & rem"])
            .creation_flags(CREATE_NO_WINDOW)
            .spawn()
            .expect("failed to spawn cmd.exe test process");

        let child_pid = child.id();
        let mut guard = TreeGuard {
            child: Some(child),
            grandchild_pid: None,
        };

        assert!(
            win32::is_child_of_current_process(child_pid),
            "1-hop child process {child_pid} should be detected"
        );

        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(3);
        let mut found_grandchild = None;
        while std::time::Instant::now() < deadline {
            if let Some(map) = win32::collect_process_parent_map() {
                if let Some((&gc_pid, _)) = map.iter().find(|&(&pid, &ppid)| ppid == child_pid && pid != child_pid) {
                    found_grandchild = Some(gc_pid);
                    break;
                }
            }
            std::thread::sleep(std::time::Duration::from_millis(25));
        }

        let gc_pid = found_grandchild.expect("expected 2-hop grandchild process under cmd.exe");
        guard.grandchild_pid = Some(gc_pid);

        assert!(
            win32::is_child_of_current_process(gc_pid),
            "2-hop grandchild process {gc_pid} (parent {child_pid}) should be detected as self-owned"
        );
    }
}
