#[derive(Debug, Clone)]
pub struct HttpResponse {
    pub status: u16,
    pub date_header: Option<String>,
    pub body: String,
}

#[cfg(windows)]
pub fn http_request(method: &str, url: &str, timeout_ms: i32) -> Result<HttpResponse, String> {
    use std::ffi::c_void;
    use windows::core::PCWSTR;
    use windows::Win32::Networking::WinHttp::*;

    struct HInternetGuard(*mut c_void);
    impl Drop for HInternetGuard {
        fn drop(&mut self) {
            if !self.0.is_null() {
                unsafe {
                    let _ = WinHttpCloseHandle(self.0);
                }
            }
        }
    }

    let (is_https, rest) = if let Some(r) = url.strip_prefix("https://") {
        (true, r)
    } else if let Some(r) = url.strip_prefix("http://") {
        (false, r)
    } else {
        return Err(format!("Unsupported URL scheme: {url}"));
    };

    let (host_port, path) = match rest.find('/') {
        Some(idx) => (&rest[..idx], &rest[idx..]),
        None => (rest, "/"),
    };

    let (host, port) = match host_port.split_once(':') {
        Some((h, p)) => (
            h,
            p.parse::<u16>()
                .unwrap_or(if is_https { 443 } else { 80 }),
        ),
        None => (host_port, if is_https { 443 } else { 80 }),
    };

    let to_wide = |s: &str| -> Vec<u16> { s.encode_utf16().chain(std::iter::once(0)).collect() };

    let agent_w = to_wide("TrueHour/1.0");
    let host_w = to_wide(host);
    let path_w = to_wide(path);
    let method_w = to_wide(method);

    unsafe {
        let h_session = WinHttpOpen(
            PCWSTR(agent_w.as_ptr()),
            WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY,
            PCWSTR::null(),
            PCWSTR::null(),
            0,
        );
        if h_session.is_null() {
            return Err("WinHttpOpen failed".to_string());
        }
        let _g_session = HInternetGuard(h_session);

        let _ = WinHttpSetTimeouts(h_session, timeout_ms, timeout_ms, timeout_ms, timeout_ms);

        let h_connect = WinHttpConnect(h_session, PCWSTR(host_w.as_ptr()), port, 0);
        if h_connect.is_null() {
            return Err("WinHttpConnect failed".to_string());
        }
        let _g_connect = HInternetGuard(h_connect);

        let flags = if is_https {
            WINHTTP_FLAG_SECURE
        } else {
            WINHTTP_OPEN_REQUEST_FLAGS(0)
        };
        let h_request = WinHttpOpenRequest(
            h_connect,
            PCWSTR(method_w.as_ptr()),
            PCWSTR(path_w.as_ptr()),
            PCWSTR::null(),
            PCWSTR::null(),
            std::ptr::null(),
            flags,
        );
        if h_request.is_null() {
            return Err("WinHttpOpenRequest failed".to_string());
        }
        let _g_request = HInternetGuard(h_request);

        WinHttpSendRequest(
            h_request,
            None,
            None,
            0,
            0,
            0,
        )
        .map_err(|e| format!("WinHttpSendRequest failed: {e}"))?;

        WinHttpReceiveResponse(h_request, std::ptr::null_mut())
            .map_err(|e| format!("WinHttpReceiveResponse failed: {e}"))?;

        let mut status_code: u32 = 0;
        let mut status_size: u32 = std::mem::size_of::<u32>() as u32;
        let _ = WinHttpQueryHeaders(
            h_request,
            WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
            PCWSTR::null(),
            Some(&mut status_code as *mut u32 as *mut c_void),
            &mut status_size,
            std::ptr::null_mut(),
        );

        let mut date_header = None;
        let mut date_size: u32 = 0;
        let _ = WinHttpQueryHeaders(
            h_request,
            WINHTTP_QUERY_DATE,
            PCWSTR::null(),
            None,
            &mut date_size,
            std::ptr::null_mut(),
        );
        if date_size > 0 && date_size < 4096 {
            let mut buf = vec![0u16; (date_size as usize / 2) + 2];
            let mut actual_bytes = (buf.len() * 2) as u32;
            if WinHttpQueryHeaders(
                h_request,
                WINHTTP_QUERY_DATE,
                PCWSTR::null(),
                Some(buf.as_mut_ptr() as *mut c_void),
                &mut actual_bytes,
                std::ptr::null_mut(),
            )
            .is_ok()
            {
                let char_len = (actual_bytes as usize) / 2;
                let trimmed = buf[..char_len.min(buf.len())]
                    .iter()
                    .take_while(|&&c| c != 0)
                    .copied()
                    .collect::<Vec<u16>>();
                let parsed = String::from_utf16_lossy(&trimmed);
                if !parsed.trim().is_empty() {
                    date_header = Some(parsed.trim().to_string());
                }
            }
        }

        let mut body_bytes = Vec::new();
        if !method.eq_ignore_ascii_case("HEAD") {
            loop {
                let mut avail: u32 = 0;
                if WinHttpQueryDataAvailable(h_request, &mut avail).is_err() || avail == 0 {
                    break;
                }
                let to_read = avail.min(65536);
                let mut chunk = vec![0u8; to_read as usize];
                let mut read: u32 = 0;
                if WinHttpReadData(
                    h_request,
                    chunk.as_mut_ptr() as *mut c_void,
                    to_read,
                    &mut read,
                )
                .is_err()
                    || read == 0
                {
                    break;
                }
                body_bytes.extend_from_slice(&chunk[..read as usize]);
                if body_bytes.len() >= 1024 * 1024 {
                    break;
                }
            }
        }

        Ok(HttpResponse {
            status: status_code as u16,
            date_header,
            body: String::from_utf8_lossy(&body_bytes).to_string(),
        })
    }
}

#[cfg(not(windows))]
pub fn http_request(_method: &str, _url: &str, _timeout_ms: i32) -> Result<HttpResponse, String> {
    Err("HTTP client only implemented for Windows".to_string())
}
