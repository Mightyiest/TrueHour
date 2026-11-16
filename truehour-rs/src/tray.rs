#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TrayAction {
    OpenMain,
    TogglePause,
    Exit,
}

#[cfg(windows)]
mod win_impl {
    use super::TrayAction;
    use std::cell::RefCell;
    use std::ffi::c_void;
    use std::mem;
    use std::sync::atomic::{AtomicBool, AtomicU8, AtomicUsize, Ordering};
    use std::sync::mpsc::Sender;
    use std::sync::Arc;
    use windows::core::{w, BOOL, PCWSTR};
    use windows::Win32::Foundation::{HWND, LPARAM, LRESULT, POINT, WPARAM};
    use windows::Win32::Graphics::Gdi::*;
    use windows::Win32::System::LibraryLoader::GetModuleHandleW;
    use windows::Win32::UI::Shell::{
        Shell_NotifyIconW, NIF_ICON, NIF_MESSAGE, NIF_TIP, NIM_ADD, NIM_DELETE, NOTIFYICONDATAW,
    };
    use windows::Win32::UI::WindowsAndMessaging::*;

    const TRAY_CLASS_W: PCWSTR = w!("TrueHourTrayHost_v5");
    const TRAY_WINDOW_W: PCWSTR = w!("TrueHourSingleInstanceMsgWindow");
    const TRAY_UID: u32 = 1;
    const WM_TRAY_CALLBACK: u32 = WM_APP + 1;
    const WM_TRUEHOUR_SHOW_MAIN: u32 = WM_APP + 42;
    const WM_TRAY_SHUTDOWN: u32 = WM_APP + 43;

    const CMD_OPEN: usize = 1001;
    const CMD_TOGGLE_PAUSE: usize = 1002;
    const CMD_EXIT: usize = 1003;

    const TRAY_PNG_BYTES: &[u8] = include_bytes!("../icons/32x32.png");

    struct TrayThreadState {
        hicon: HICON,
        wm_taskbar_created: u32,
        tx: Sender<TrayAction>,
        egui_ctx: egui::Context,
        running_paused: Arc<AtomicU8>,
        alive: Arc<AtomicBool>,
    }

    thread_local! {
        static TRAY_STATE: RefCell<Option<TrayThreadState>> = const { RefCell::new(None) };
    }

    fn add_tray_icon(hwnd: HWND, hicon: HICON) {
        let mut nid: NOTIFYICONDATAW = unsafe { mem::zeroed() };
        nid.cbSize = mem::size_of::<NOTIFYICONDATAW>() as u32;
        nid.hWnd = hwnd;
        nid.uID = TRAY_UID;
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP;
        nid.uCallbackMessage = WM_TRAY_CALLBACK;
        nid.hIcon = hicon;

        let tip_w: Vec<u16> = "TrueHour - Time Tracker".encode_utf16().collect();
        let copy_len = tip_w.len().min(nid.szTip.len() - 1);
        nid.szTip[..copy_len].copy_from_slice(&tip_w[..copy_len]);

        unsafe {
            let _ = Shell_NotifyIconW(NIM_ADD, &nid);
        }
    }

    fn remove_tray_icon(hwnd: HWND) {
        let mut nid: NOTIFYICONDATAW = unsafe { mem::zeroed() };
        nid.cbSize = mem::size_of::<NOTIFYICONDATAW>() as u32;
        nid.hWnd = hwnd;
        nid.uID = TRAY_UID;
        unsafe {
            let _ = Shell_NotifyIconW(NIM_DELETE, &nid);
        }
    }

    fn create_hicon_from_png() -> HICON {
        let Ok(img) = image::load_from_memory(TRAY_PNG_BYTES) else {
            return HICON::default();
        };
        let rgba_img = img.to_rgba8();
        let (w, h) = rgba_img.dimensions();
        if w == 0 || h == 0 {
            return HICON::default();
        }
        let rgba = rgba_img.into_raw();

        unsafe {
            let screen_dc = GetDC(None);
            if screen_dc.is_invalid() {
                return HICON::default();
            }

            let mut bmi: BITMAPINFO = mem::zeroed();
            bmi.bmiHeader.biSize = mem::size_of::<BITMAPINFOHEADER>() as u32;
            bmi.bmiHeader.biWidth = w as i32;
            bmi.bmiHeader.biHeight = -(h as i32);
            bmi.bmiHeader.biPlanes = 1;
            bmi.bmiHeader.biBitCount = 32;
            bmi.bmiHeader.biCompression = BI_RGB.0;

            let mut bits_ptr: *mut c_void = std::ptr::null_mut();
            let Ok(hbm_color) = CreateDIBSection(
                Some(screen_dc),
                &bmi,
                DIB_RGB_COLORS,
                &mut bits_ptr,
                None,
                0,
            ) else {
                ReleaseDC(None, screen_dc);
                return HICON::default();
            };

            if !bits_ptr.is_null() {
                let px_count = (w * h) as usize;
                let dst = std::slice::from_raw_parts_mut(bits_ptr as *mut u8, px_count * 4);
                for (s, d) in rgba.chunks_exact(4).zip(dst.chunks_exact_mut(4)) {
                    d[0] = s[2]; // B
                    d[1] = s[1]; // G
                    d[2] = s[0]; // R
                    d[3] = s[3]; // A
                }
            }

            let mask_stride = ((w as usize + 15) / 16) * 2;
            let mask_bytes = vec![0u8; mask_stride * (h as usize)];
            let hbm_mask = CreateBitmap(
                w as i32,
                h as i32,
                1,
                1,
                Some(mask_bytes.as_ptr() as *const c_void),
            );

            let icon_info = ICONINFO {
                fIcon: BOOL(1),
                xHotspot: 0,
                yHotspot: 0,
                hbmMask: hbm_mask,
                hbmColor: hbm_color,
            };
            let hicon = CreateIconIndirect(&icon_info).unwrap_or_default();

            if !hbm_color.is_invalid() {
                let _ = DeleteObject(hbm_color.into());
            }
            if !hbm_mask.is_invalid() {
                let _ = DeleteObject(hbm_mask.into());
            }
            ReleaseDC(None, screen_dc);
            hicon
        }
    }

    fn emit_action(action: TrayAction) {
        TRAY_STATE.with(|cell| {
            if let Some(st) = cell.borrow().as_ref() {
                let _ = st.tx.send(action);
                st.egui_ctx.request_repaint();
            }
        });
    }

    fn show_context_menu(hwnd: HWND) {
        let state_bits = TRAY_STATE.with(|cell| {
            cell.borrow()
                .as_ref()
                .map(|s| s.running_paused.load(Ordering::SeqCst))
                .unwrap_or(0)
        });
        let running = (state_bits & 0b10) != 0;
        let paused = (state_bits & 0b01) != 0;

        unsafe {
            let Ok(hmenu) = CreatePopupMenu() else {
                return;
            };

            let _ = AppendMenuW(hmenu, MF_STRING, CMD_OPEN, w!("Open TrueHour"));
            let _ = SetMenuDefaultItem(hmenu, CMD_OPEN as u32, 0);

            let pause_flags = if running {
                MF_STRING
            } else {
                MF_STRING | MF_GRAYED
            };
            let pause_label = if paused {
                w!("Resume Tracking")
            } else {
                w!("Pause Tracking")
            };
            let _ = AppendMenuW(hmenu, pause_flags, CMD_TOGGLE_PAUSE, pause_label);
            let _ = AppendMenuW(hmenu, MF_SEPARATOR, 0, PCWSTR::null());
            let _ = AppendMenuW(hmenu, MF_STRING, CMD_EXIT, w!("Exit"));

            let mut pt = POINT::default();
            let _ = GetCursorPos(&mut pt);
            let _ = SetForegroundWindow(hwnd);
            let cmd = TrackPopupMenu(
                hmenu,
                TPM_RETURNCMD | TPM_NONOTIFY | TPM_RIGHTBUTTON,
                pt.x,
                pt.y,
                None,
                hwnd,
                None,
            );
            let _ = PostMessageW(Some(hwnd), WM_NULL, WPARAM(0), LPARAM(0));
            let _ = DestroyMenu(hmenu);

            match cmd.0 as usize {
                CMD_OPEN => emit_action(TrayAction::OpenMain),
                CMD_TOGGLE_PAUSE => emit_action(TrayAction::TogglePause),
                CMD_EXIT => emit_action(TrayAction::Exit),
                _ => {}
            }
        }
    }

    unsafe extern "system" fn tray_wnd_proc(
        hwnd: HWND,
        msg: u32,
        wparam: WPARAM,
        lparam: LPARAM,
    ) -> LRESULT {
        let taskbar_msg = TRAY_STATE.with(|cell| {
            cell.borrow()
                .as_ref()
                .map(|s| s.wm_taskbar_created)
                .unwrap_or(0)
        });

        if taskbar_msg != 0 && msg == taskbar_msg {
            let hicon = TRAY_STATE.with(|cell| {
                cell.borrow()
                    .as_ref()
                    .map(|s| s.hicon)
                    .unwrap_or_default()
            });
            add_tray_icon(hwnd, hicon);
            return LRESULT(0);
        }

        match msg {
            WM_TRAY_CALLBACK => {
                let mouse_msg = (lparam.0 & 0xFFFF) as u32;
                match mouse_msg {
                    WM_LBUTTONUP | WM_LBUTTONDBLCLK => {
                        emit_action(TrayAction::OpenMain);
                    }
                    WM_RBUTTONUP | WM_CONTEXTMENU => {
                        show_context_menu(hwnd);
                    }
                    _ => {}
                }
                LRESULT(0)
            }
            WM_TRUEHOUR_SHOW_MAIN => {
                emit_action(TrayAction::OpenMain);
                LRESULT(0)
            }
            WM_TRAY_SHUTDOWN => {
                let _ = DestroyWindow(hwnd);
                LRESULT(0)
            }
            WM_DESTROY => {
                remove_tray_icon(hwnd);
                TRAY_STATE.with(|cell| {
                    if let Some(st) = cell.borrow_mut().take() {
                        st.alive.store(false, Ordering::SeqCst);
                        if !st.hicon.is_invalid() {
                            let _ = DestroyIcon(st.hicon);
                        }
                    }
                });
                PostQuitMessage(0);
                LRESULT(0)
            }
            _ => DefWindowProcW(hwnd, msg, wparam, lparam),
        }
    }

    pub struct SystemTray {
        hwnd_raw: Arc<AtomicUsize>,
        running_paused: Arc<AtomicU8>,
        alive: Arc<AtomicBool>,
    }

    impl SystemTray {
        pub fn start(
            egui_ctx: egui::Context,
            tx: Sender<TrayAction>,
            running: bool,
            paused: bool,
        ) -> Self {
            let init_bits = ((running as u8) << 1) | (paused as u8);
            let running_paused = Arc::new(AtomicU8::new(init_bits));
            let alive = Arc::new(AtomicBool::new(true));
            let hwnd_raw = Arc::new(AtomicUsize::new(0));

            let rp_thread = Arc::clone(&running_paused);
            let alive_thread = Arc::clone(&alive);
            let hwnd_thread = Arc::clone(&hwnd_raw);

            std::thread::Builder::new()
                .name("truehour-tray".to_string())
                .spawn(move || unsafe {
                    let hinst = GetModuleHandleW(PCWSTR::null()).unwrap_or_default();
                    let wc = WNDCLASSEXW {
                        cbSize: mem::size_of::<WNDCLASSEXW>() as u32,
                        style: WNDCLASS_STYLES(0),
                        lpfnWndProc: Some(tray_wnd_proc),
                        cbClsExtra: 0,
                        cbWndExtra: 0,
                        hInstance: hinst.into(),
                        hIcon: HICON::default(),
                        hCursor: LoadCursorW(None, IDC_ARROW).unwrap_or_default(),
                        hbrBackground: HBRUSH::default(),
                        lpszMenuName: PCWSTR::null(),
                        lpszClassName: TRAY_CLASS_W,
                        hIconSm: HICON::default(),
                    };
                    let _ = RegisterClassExW(&wc);

                    let Ok(hwnd) = CreateWindowExW(
                        WINDOW_EX_STYLE(0),
                        TRAY_CLASS_W,
                        TRAY_WINDOW_W,
                        WINDOW_STYLE(0),
                        0,
                        0,
                        0,
                        0,
                        None,
                        None,
                        Some(hinst.into()),
                        None,
                    ) else {
                        alive_thread.store(false, Ordering::SeqCst);
                        return;
                    };

                    hwnd_thread.store(hwnd.0 as usize, Ordering::SeqCst);
                    let hicon = create_hicon_from_png();
                    let wm_taskbar_created = RegisterWindowMessageW(w!("TaskbarCreated"));

                    add_tray_icon(hwnd, hicon);

                    TRAY_STATE.with(|cell| {
                        *cell.borrow_mut() = Some(TrayThreadState {
                            hicon,
                            wm_taskbar_created,
                            tx,
                            egui_ctx,
                            running_paused: rp_thread,
                            alive: Arc::clone(&alive_thread),
                        });
                    });

                    let mut msg = MSG::default();
                    while GetMessageW(&mut msg, None, 0, 0).0 > 0 {
                        let _ = TranslateMessage(&msg);
                        DispatchMessageW(&msg);
                    }
                    alive_thread.store(false, Ordering::SeqCst);
                    hwnd_thread.store(0, Ordering::SeqCst);
                })
                .ok();

            Self {
                hwnd_raw,
                running_paused,
                alive,
            }
        }

        pub fn set_tracking_state(&self, running: bool, paused: bool) {
            let bits = ((running as u8) << 1) | (paused as u8);
            self.running_paused.store(bits, Ordering::SeqCst);
        }

        pub fn is_alive(&self) -> bool {
            self.alive.load(Ordering::SeqCst)
        }

        pub fn shutdown(&self) {
            let raw = self.hwnd_raw.swap(0, Ordering::SeqCst);
            if raw != 0 {
                let hwnd = HWND(raw as *mut c_void);
                unsafe {
                    let _ = PostMessageW(Some(hwnd), WM_TRAY_SHUTDOWN, WPARAM(0), LPARAM(0));
                }
            }
        }
    }

    impl Drop for SystemTray {
        fn drop(&mut self) {
            self.shutdown();
        }
    }

    pub fn try_signal_existing_instance() -> bool {
        unsafe {
            match FindWindowW(TRAY_CLASS_W, TRAY_WINDOW_W) {
                Ok(hwnd) if !hwnd.0.is_null() => {
                    PostMessageW(Some(hwnd), WM_TRUEHOUR_SHOW_MAIN, WPARAM(0), LPARAM(0)).is_ok()
                }
                _ => false,
            }
        }
    }
}

#[cfg(not(windows))]
mod win_impl {
    use super::TrayAction;
    use std::sync::mpsc::Sender;

    pub struct SystemTray;

    impl SystemTray {
        pub fn start(
            _egui_ctx: egui::Context,
            _tx: Sender<TrayAction>,
            _running: bool,
            _paused: bool,
        ) -> Self {
            Self
        }

        pub fn set_tracking_state(&self, _running: bool, _paused: bool) {}

        pub fn is_alive(&self) -> bool {
            false
        }

        pub fn shutdown(&self) {}
    }

    pub fn try_signal_existing_instance() -> bool {
        false
    }
}

pub use win_impl::{try_signal_existing_instance, SystemTray};
