use std::path::PathBuf;

#[cfg(windows)]
mod win_dlg {
    use std::ffi::c_void;
    use std::path::PathBuf;

    #[repr(C)]
    struct OpenFileNameW {
        l_struct_size: u32,
        hwnd_owner: *mut c_void,
        h_instance: *mut c_void,
        lpstr_filter: *const u16,
        lpstr_custom_filter: *mut u16,
        n_max_cust_filter: u32,
        n_filter_index: u32,
        lpstr_file: *mut u16,
        n_max_file: u32,
        lpstr_file_title: *mut u16,
        n_max_file_title: u32,
        lpstr_initial_dir: *const u16,
        lpstr_title: *const u16,
        flags: u32,
        n_file_offset: u16,
        n_file_extension: u16,
        lpstr_def_ext: *const u16,
        l_cust_data: usize,
        lpfn_hook: usize,
        lp_template_name: *const u16,
        pv_reserved: *mut c_void,
        dw_reserved: u32,
        flags_ex: u32,
    }

    #[link(name = "comdlg32")]
    extern "system" {
        fn GetOpenFileNameW(lpofn: *mut OpenFileNameW) -> i32;
        fn GetSaveFileNameW(lpofn: *mut OpenFileNameW) -> i32;
    }

    const OFN_OVERWRITEPROMPT: u32 = 0x0000_0002;
    const OFN_NOCHANGEDIR: u32 = 0x0000_0008;
    const OFN_PATHMUSTEXIST: u32 = 0x0000_0800;
    const OFN_FILEMUSTEXIST: u32 = 0x0000_1000;
    const OFN_EXPLORER: u32 = 0x0008_0000;

    fn build_filter_utf16(pairs: &[(&str, &str)]) -> Vec<u16> {
        let mut out = Vec::new();
        for (label, pattern) in pairs {
            out.extend(label.encode_utf16());
            out.push(0);
            out.extend(pattern.encode_utf16());
            out.push(0);
        }
        out.push(0);
        out
    }

    pub fn open_file(title: &str, filters: &[(&str, &str)], def_ext: &str) -> Option<PathBuf> {
        let mut file_buf = vec![0u16; 32768];
        let filter_w = build_filter_utf16(filters);
        let title_w: Vec<u16> = title.encode_utf16().chain(std::iter::once(0)).collect();
        let def_ext_w: Vec<u16> = def_ext.encode_utf16().chain(std::iter::once(0)).collect();

        let mut ofn = OpenFileNameW {
            l_struct_size: std::mem::size_of::<OpenFileNameW>() as u32,
            hwnd_owner: std::ptr::null_mut(),
            h_instance: std::ptr::null_mut(),
            lpstr_filter: filter_w.as_ptr(),
            lpstr_custom_filter: std::ptr::null_mut(),
            n_max_cust_filter: 0,
            n_filter_index: 1,
            lpstr_file: file_buf.as_mut_ptr(),
            n_max_file: file_buf.len() as u32,
            lpstr_file_title: std::ptr::null_mut(),
            n_max_file_title: 0,
            lpstr_initial_dir: std::ptr::null(),
            lpstr_title: title_w.as_ptr(),
            flags: OFN_EXPLORER | OFN_PATHMUSTEXIST | OFN_FILEMUSTEXIST | OFN_NOCHANGEDIR,
            n_file_offset: 0,
            n_file_extension: 0,
            lpstr_def_ext: if def_ext.is_empty() {
                std::ptr::null()
            } else {
                def_ext_w.as_ptr()
            },
            l_cust_data: 0,
            lpfn_hook: 0,
            lp_template_name: std::ptr::null(),
            pv_reserved: std::ptr::null_mut(),
            dw_reserved: 0,
            flags_ex: 0,
        };

        let ok = unsafe { GetOpenFileNameW(&mut ofn) };
        if ok == 0 {
            return None;
        }
        let end = file_buf.iter().position(|&c| c == 0).unwrap_or(file_buf.len());
        let selected = String::from_utf16_lossy(&file_buf[..end]);
        if selected.is_empty() {
            None
        } else {
            Some(PathBuf::from(selected))
        }
    }

    pub fn save_file(
        title: &str,
        default_filename: &str,
        filters: &[(&str, &str)],
        def_ext: &str,
    ) -> Option<PathBuf> {
        let mut file_buf = vec![0u16; 32768];
        let def_u16: Vec<u16> = default_filename.encode_utf16().collect();
        let copy_len = def_u16.len().min(file_buf.len() - 1);
        file_buf[..copy_len].copy_from_slice(&def_u16[..copy_len]);

        let filter_w = build_filter_utf16(filters);
        let title_w: Vec<u16> = title.encode_utf16().chain(std::iter::once(0)).collect();
        let def_ext_w: Vec<u16> = def_ext.encode_utf16().chain(std::iter::once(0)).collect();

        let mut ofn = OpenFileNameW {
            l_struct_size: std::mem::size_of::<OpenFileNameW>() as u32,
            hwnd_owner: std::ptr::null_mut(),
            h_instance: std::ptr::null_mut(),
            lpstr_filter: filter_w.as_ptr(),
            lpstr_custom_filter: std::ptr::null_mut(),
            n_max_cust_filter: 0,
            n_filter_index: 1,
            lpstr_file: file_buf.as_mut_ptr(),
            n_max_file: file_buf.len() as u32,
            lpstr_file_title: std::ptr::null_mut(),
            n_max_file_title: 0,
            lpstr_initial_dir: std::ptr::null(),
            lpstr_title: title_w.as_ptr(),
            flags: OFN_EXPLORER | OFN_PATHMUSTEXIST | OFN_OVERWRITEPROMPT | OFN_NOCHANGEDIR,
            n_file_offset: 0,
            n_file_extension: 0,
            lpstr_def_ext: if def_ext.is_empty() {
                std::ptr::null()
            } else {
                def_ext_w.as_ptr()
            },
            l_cust_data: 0,
            lpfn_hook: 0,
            lp_template_name: std::ptr::null(),
            pv_reserved: std::ptr::null_mut(),
            dw_reserved: 0,
            flags_ex: 0,
        };

        let ok = unsafe { GetSaveFileNameW(&mut ofn) };
        if ok == 0 {
            return None;
        }
        let end = file_buf.iter().position(|&c| c == 0).unwrap_or(file_buf.len());
        let selected = String::from_utf16_lossy(&file_buf[..end]);
        if selected.is_empty() {
            None
        } else {
            Some(PathBuf::from(selected))
        }
    }
}

pub fn pick_open_file(title: &str, filters: &[(&str, &str)], def_ext: &str) -> Option<PathBuf> {
    #[cfg(windows)]
    {
        win_dlg::open_file(title, filters, def_ext)
    }
    #[cfg(not(windows))]
    {
        let _ = (title, filters, def_ext);
        None
    }
}

pub fn pick_save_file(
    title: &str,
    default_filename: &str,
    filters: &[(&str, &str)],
    def_ext: &str,
) -> Option<PathBuf> {
    #[cfg(windows)]
    {
        win_dlg::save_file(title, default_filename, filters, def_ext)
    }
    #[cfg(not(windows))]
    {
        let _ = (title, default_filename, filters, def_ext);
        None
    }
}
