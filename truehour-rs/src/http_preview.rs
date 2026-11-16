use std::io::{BufRead, BufReader, Write};
use std::net::TcpListener;
use std::path::Path;
use std::sync::Arc;
use std::time::Duration;

pub fn open_target_externally(target: &str) -> Result<(), String> {
    #[cfg(windows)]
    {
        use windows::core::PCWSTR;
        use windows::Win32::UI::Shell::ShellExecuteW;
        use windows::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;

        let op: Vec<u16> = "open\0".encode_utf16().collect();
        let file: Vec<u16> = target.encode_utf16().chain(std::iter::once(0)).collect();
        let hinst = unsafe {
            ShellExecuteW(
                None,
                PCWSTR(op.as_ptr()),
                PCWSTR(file.as_ptr()),
                PCWSTR::null(),
                PCWSTR::null(),
                SW_SHOWNORMAL,
            )
        };
        if (hinst.0 as isize) <= 32 {
            return Err(format!("Windows shell failed to open target: {target}"));
        }
        Ok(())
    }
    #[cfg(not(windows))]
    {
        let _ = target;
        Err("Opening URLs/files is only supported on Windows".to_string())
    }
}

pub fn write_temp_html_and_open(prefix: &str, html: &str) -> Result<std::path::PathBuf, String> {
    let fname = format!(
        "{prefix}_{}.html",
        chrono::Local::now().format("%Y%m%d_%H%M%S_%3f")
    );
    let path = std::env::temp_dir().join(fname);
    std::fs::write(&path, html.as_bytes())
        .map_err(|e| format!("Failed to write temporary HTML file: {e}"))?;
    let target = path.to_string_lossy().to_string();
    open_target_externally(&target)?;
    Ok(path)
}

pub fn open_folder_or_file(path: &Path) -> Result<(), String> {
    let target = path.to_string_lossy().to_string();
    open_target_externally(&target)
}

/// Starts a single-invoice localhost preview HTTP server on `127.0.0.1:<ephemeral_port>`
/// matching Python `InvoiceHTTPServer` (`GET /` serves invoice HTML, `POST /save` commits
/// draft -> unpaid in SQLite). Automatically shuts down after 30 minutes of inactivity.
pub fn start_invoice_preview_server<F>(html: String, on_save: F) -> Result<String, String>
where
    F: Fn() -> Result<&'static str, String> + Send + Sync + 'static,
{
    let listener = TcpListener::bind("127.0.0.1:0")
        .map_err(|e| format!("Failed to bind localhost preview port: {e}"))?;
    let port = listener
        .local_addr()
        .map_err(|e| format!("Failed to query preview port: {e}"))?
        .port();
    let _ = listener.set_nonblocking(true);

    let html_arc = Arc::new(html);
    let save_cb = Arc::new(on_save);

    std::thread::spawn(move || {
        let idle_limit = Duration::from_secs(30 * 60);
        let mut last_activity = std::time::Instant::now();

        loop {
            match listener.accept() {
                Ok((mut stream, _)) => {
                    last_activity = std::time::Instant::now();
                    let _ = stream.set_read_timeout(Some(Duration::from_secs(5)));
                    let mut reader = BufReader::new(stream.try_clone().unwrap_or_else(|_| {
                        panic!("clone tcp stream failed");
                    }));
                    let mut request_line = String::new();
                    if reader.read_line(&mut request_line).is_err() || request_line.is_empty() {
                        continue;
                    }
                    // Drain headers quickly
                    loop {
                        let mut hdr = String::new();
                        match reader.read_line(&mut hdr) {
                            Ok(0) | Err(_) => break,
                            Ok(_) if hdr == "\r\n" || hdr == "\n" => break,
                            _ => {}
                        }
                    }

                    let mut parts = request_line.split_whitespace();
                    let method = parts.next().unwrap_or("GET");
                    let raw_target = parts.next().unwrap_or("/");
                    let path = raw_target.split('?').next().unwrap_or("/");

                    if method == "OPTIONS" {
                        let resp = concat!(
                            "HTTP/1.1 204 No Content\r\n",
                            "Access-Control-Allow-Origin: *\r\n",
                            "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n",
                            "Access-Control-Allow-Headers: Content-Type\r\n",
                            "Content-Length: 0\r\nConnection: close\r\n\r\n"
                        );
                        let _ = stream.write_all(resp.as_bytes());
                        let _ = stream.flush();
                    } else if method == "POST" && path == "/save" {
                        let body = match save_cb() {
                            Ok(status_str) => format!(r#"{{"status":"{status_str}"}}"#),
                            Err(err) => {
                                let escaped = err.replace('"', "'");
                                format!(r#"{{"status":"error","message":"{escaped}"}}"#)
                            }
                        };
                        let resp = format!(
                            "HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\nAccess-Control-Allow-Origin: *\r\nCache-Control: no-store\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                            body.len(),
                            body
                        );
                        let _ = stream.write_all(resp.as_bytes());
                        let _ = stream.flush();
                    } else if method == "GET" && (path == "/" || path.is_empty()) {
                        let bytes = html_arc.as_bytes();
                        let header = format!(
                            "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nCache-Control: no-store, no-cache, must-revalidate\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                            bytes.len()
                        );
                        let _ = stream.write_all(header.as_bytes());
                        let _ = stream.write_all(bytes);
                        let _ = stream.flush();
                    } else {
                        let resp = "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
                        let _ = stream.write_all(resp.as_bytes());
                        let _ = stream.flush();
                    }
                }
                Err(ref e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                    if last_activity.elapsed() >= idle_limit {
                        break;
                    }
                    std::thread::sleep(Duration::from_millis(50));
                }
                Err(_) => break,
            }
        }
    });

    Ok(format!("http://127.0.0.1:{port}/?preview=1"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Read;
    use std::net::TcpStream;
    use std::sync::atomic::{AtomicUsize, Ordering};

    #[test]
    fn test_invoice_preview_http_server_get_and_save() {
        let saves = Arc::new(AtomicUsize::new(0));
        let saves_cb = Arc::clone(&saves);
        let url = start_invoice_preview_server("<html>Hello Invoice</html>".into(), move || {
            let prev = saves_cb.fetch_add(1, Ordering::SeqCst);
            Ok(if prev == 0 { "success" } else { "already_saved" })
        })
        .unwrap();

        let host_port = url
            .strip_prefix("http://")
            .unwrap()
            .split('/')
            .next()
            .unwrap();

        // 1. GET /?preview=1
        {
            let mut stream = TcpStream::connect(host_port).unwrap();
            stream
                .write_all(b"GET /?preview=1 HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
                .unwrap();
            let mut buf = String::new();
            stream.read_to_string(&mut buf).unwrap();
            assert!(buf.contains("200 OK"));
            assert!(buf.contains("<html>Hello Invoice</html>"));
        }

        // 2. First POST /save -> success
        {
            let mut stream = TcpStream::connect(host_port).unwrap();
            stream
                .write_all(b"POST /save HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 0\r\n\r\n")
                .unwrap();
            let mut buf = String::new();
            stream.read_to_string(&mut buf).unwrap();
            assert!(buf.contains(r#"{"status":"success"}"#));
        }

        // 3. Second POST /save -> already_saved (idempotent)
        {
            let mut stream = TcpStream::connect(host_port).unwrap();
            stream
                .write_all(b"POST /save HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 0\r\n\r\n")
                .unwrap();
            let mut buf = String::new();
            stream.read_to_string(&mut buf).unwrap();
            assert!(buf.contains(r#"{"status":"already_saved"}"#));
        }
        assert_eq!(saves.load(Ordering::SeqCst), 2);
    }
}
