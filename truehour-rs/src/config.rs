use chrono::Local;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::thread;
use std::time::Duration;

#[cfg(windows)]
use std::os::windows::fs::OpenOptionsExt;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProfilesConfig {
    pub active_profile: String,
    pub profiles: Vec<String>,
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}

impl Default for ProfilesConfig {
    fn default() -> Self {
        Self {
            active_profile: "Default".to_string(),
            profiles: vec!["Default".to_string()],
            extra: Map::new(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct ProfilePaths {
    pub app_data_root: PathBuf,
    pub profile_name: String,
    pub profile_dir: PathBuf,
    pub sessions_dir: PathBuf,
    pub autosave_dir: PathBuf,
    pub trash_dir: PathBuf,
    pub reports_dir: PathBuf,
    pub invoices_dir: PathBuf,
    pub qr_codes_dir: PathBuf,
    pub settings_file: PathBuf,
    pub app_settings_file: PathBuf,
    pub tags_file: PathBuf,
    pub active_session_file: PathBuf,
    pub auto_excluded_file: PathBuf,
    pub name_overrides_file: PathBuf,
    pub db_file: PathBuf,
    pub time_chain_file: PathBuf,
    pub security_log_file: PathBuf,
    pub lock_file: PathBuf,
    pub safety_backups_dir: PathBuf,
}

impl ProfilePaths {
    pub fn from_root_and_profile(app_data_root: PathBuf, profile_name: String) -> Self {
        let profile_dir = app_data_root.join("profiles").join(&profile_name);
        Self {
            sessions_dir: profile_dir.join("sessions"),
            autosave_dir: profile_dir.join("autosave"),
            trash_dir: profile_dir.join("trash"),
            reports_dir: profile_dir.join("reports"),
            invoices_dir: profile_dir.join("invoices"),
            qr_codes_dir: profile_dir.join("qr_codes"),
            settings_file: profile_dir.join("settings.json"),
            app_settings_file: profile_dir.join("app_settings.json"),
            tags_file: profile_dir.join("tags.json"),
            active_session_file: profile_dir.join("active_session.json"),
            auto_excluded_file: profile_dir.join("auto_excluded_apps.txt"),
            name_overrides_file: profile_dir.join("name_overrides.txt"),
            db_file: profile_dir.join("truehour.db"),
            time_chain_file: profile_dir.join("time_chain.json"),
            security_log_file: profile_dir.join("security_log.json"),
            lock_file: app_data_root.join("truehour.lock"),
            safety_backups_dir: app_data_root.join("rust_safety_backups"),
            app_data_root,
            profile_name,
            profile_dir,
        }
    }

    pub fn ensure_dirs(&self) -> io::Result<()> {
        fs::create_dir_all(&self.app_data_root)?;
        fs::create_dir_all(&self.profile_dir)?;
        fs::create_dir_all(&self.sessions_dir)?;
        fs::create_dir_all(&self.autosave_dir)?;
        fs::create_dir_all(&self.trash_dir)?;
        fs::create_dir_all(&self.reports_dir)?;
        fs::create_dir_all(&self.invoices_dir)?;
        fs::create_dir_all(&self.qr_codes_dir)?;
        Ok(())
    }
}

pub fn get_app_data_root() -> PathBuf {
    if let Ok(override_dir) = std::env::var("TRUEHOUR_DATA_ROOT") {
        let trimmed = override_dir.trim();
        if !trimmed.is_empty() {
            return PathBuf::from(trimmed);
        }
    }
    if let Ok(local_app_data) = std::env::var("LOCALAPPDATA") {
        let trimmed = local_app_data.trim();
        if !trimmed.is_empty() {
            return PathBuf::from(trimmed).join("TrueHour");
        }
    }
    if let Ok(profile) = std::env::var("USERPROFILE") {
        let trimmed = profile.trim();
        if !trimmed.is_empty() {
            return PathBuf::from(trimmed)
                .join("AppData")
                .join("Local")
                .join("TrueHour");
        }
    }
    PathBuf::from(".").join("TrueHourData")
}

pub fn atomic_write_bytes(path: &Path, data: &[u8]) -> io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let pid = std::process::id();
    let tmp_name = match path.file_name().and_then(|n| n.to_str()) {
        Some(name) => format!("{name}.tmp.{pid}"),
        None => format!("file.tmp.{pid}"),
    };
    let tmp_path = path.with_file_name(tmp_name);

    {
        let mut f = File::create(&tmp_path)?;
        f.write_all(data)?;
        f.sync_all()?;
    }

    let mut last_err = None;
    for attempt in 0..4 {
        match fs::rename(&tmp_path, path) {
            Ok(()) => return Ok(()),
            Err(e) => {
                last_err = Some(e);
                if attempt < 3 {
                    thread::sleep(Duration::from_millis(20));
                }
            }
        }
    }

    let _ = fs::remove_file(&tmp_path);
    Err(last_err.unwrap_or_else(|| io::Error::other("atomic rename failed")))
}

pub fn atomic_write_str(path: &Path, content: &str) -> io::Result<()> {
    atomic_write_bytes(path, content.as_bytes())
}

pub fn load_or_init_profiles(app_data_root: &Path) -> io::Result<ProfilesConfig> {
    fs::create_dir_all(app_data_root)?;
    let profiles_file = app_data_root.join("profiles.json");
    if profiles_file.exists() {
        let raw = fs::read_to_string(&profiles_file)?;
        let clean = raw.trim_start_matches('\u{feff}');
        if let Ok(mut cfg) = serde_json::from_str::<ProfilesConfig>(clean) {
            if cfg.active_profile.trim().is_empty() {
                cfg.active_profile = "Default".to_string();
            }
            if !cfg.profiles.iter().any(|p| p == &cfg.active_profile) {
                cfg.profiles.push(cfg.active_profile.clone());
            }
            return Ok(cfg);
        }
    }
    let cfg = ProfilesConfig::default();
    let json = serde_json::to_string_pretty(&cfg).map_err(io::Error::other)?;
    atomic_write_str(&profiles_file, &json)?;
    Ok(cfg)
}

pub fn resolve_active_profile() -> io::Result<ProfilePaths> {
    let root = get_app_data_root();
    let cfg = load_or_init_profiles(&root)?;
    let paths = ProfilePaths::from_root_and_profile(root, cfg.active_profile);
    Ok(paths)
}

pub fn save_profiles_config(app_data_root: &Path, cfg: &ProfilesConfig) -> io::Result<()> {
    fs::create_dir_all(app_data_root)?;
    let profiles_file = app_data_root.join("profiles.json");
    let json = serde_json::to_string_pretty(cfg).map_err(io::Error::other)?;
    atomic_write_str(&profiles_file, &json)
}

pub fn validate_profile_name(name: &str) -> Result<String, String> {
    let trimmed = name.trim();
    if trimmed.is_empty() {
        return Err("Profile name cannot be empty.".to_string());
    }
    if trimmed == "." || trimmed == ".." || trimmed.contains("..") {
        return Err("Invalid profile name.".to_string());
    }
    const FORBIDDEN: &[char] = &['/', '\\', ':', '*', '?', '"', '<', '>', '|', '\0'];
    if trimmed.chars().any(|c| FORBIDDEN.contains(&c) || c.is_control()) {
        return Err("Profile name contains unsupported path characters.".to_string());
    }
    Ok(trimmed.to_string())
}

pub fn create_profile(app_data_root: &Path, name: &str) -> Result<ProfilesConfig, String> {
    let clean = validate_profile_name(name)?;
    let mut cfg = load_or_init_profiles(app_data_root).map_err(|e| e.to_string())?;
    if cfg.profiles.iter().any(|p| p.eq_ignore_ascii_case(&clean)) {
        return Err(format!("Profile '{clean}' already exists."));
    }
    let paths = ProfilePaths::from_root_and_profile(app_data_root.to_path_buf(), clean.clone());
    paths.ensure_dirs().map_err(|e| e.to_string())?;
    cfg.profiles.push(clean);
    save_profiles_config(app_data_root, &cfg).map_err(|e| e.to_string())?;
    Ok(cfg)
}

pub fn switch_profile(app_data_root: &Path, name: &str) -> Result<ProfilesConfig, String> {
    let clean = validate_profile_name(name)?;
    let mut cfg = load_or_init_profiles(app_data_root).map_err(|e| e.to_string())?;
    let matched = cfg
        .profiles
        .iter()
        .find(|p| p.eq_ignore_ascii_case(&clean))
        .cloned()
        .ok_or_else(|| format!("Profile '{clean}' not found."))?;
    let paths = ProfilePaths::from_root_and_profile(app_data_root.to_path_buf(), matched.clone());
    paths.ensure_dirs().map_err(|e| e.to_string())?;
    cfg.active_profile = matched;
    save_profiles_config(app_data_root, &cfg).map_err(|e| e.to_string())?;
    Ok(cfg)
}

pub fn rename_profile(
    app_data_root: &Path,
    old_name: &str,
    new_name: &str,
) -> Result<ProfilesConfig, String> {
    if old_name == "Default" {
        return Err("The 'Default' profile cannot be renamed.".to_string());
    }
    let clean_new = validate_profile_name(new_name)?;
    let mut cfg = load_or_init_profiles(app_data_root).map_err(|e| e.to_string())?;
    if cfg
        .profiles
        .iter()
        .any(|p| p != old_name && p.eq_ignore_ascii_case(&clean_new))
    {
        return Err(format!("Profile '{clean_new}' already exists."));
    }
    let old_dir = app_data_root.join("profiles").join(old_name);
    let new_dir = app_data_root.join("profiles").join(&clean_new);
    if old_dir.exists() {
        if new_dir.exists() {
            return Err(format!("Target directory for '{clean_new}' already exists."));
        }
        if fs::rename(&old_dir, &new_dir).is_err() {
            copy_dir_recursive(&old_dir, &new_dir).map_err(|e| e.to_string())?;
            fs::remove_dir_all(&old_dir).map_err(|e| e.to_string())?;
        }
    } else {
        fs::create_dir_all(&new_dir).map_err(|e| e.to_string())?;
    }

    // Update logo path inside app_settings.json if it referenced old profile dir
    let new_settings_path = new_dir.join("app_settings.json");
    if new_settings_path.exists() {
        if let Ok(raw) = fs::read_to_string(&new_settings_path) {
            if let Ok(mut val) = serde_json::from_str::<Value>(raw.trim_start_matches('\u{feff}')) {
                if let Some(obj) = val.as_object_mut() {
                    if let Some(logo) = obj.get("business_logo_path").and_then(|v| v.as_str()) {
                        let old_prefix = old_dir.to_string_lossy().to_string();
                        if logo.starts_with(&old_prefix) {
                            let updated = logo.replacen(
                                &old_prefix,
                                &new_dir.to_string_lossy(),
                                1,
                            );
                            obj.insert("business_logo_path".into(), Value::String(updated));
                            if let Ok(s) = serde_json::to_string_pretty(&val) {
                                let _ = atomic_write_str(&new_settings_path, &s);
                            }
                        }
                    }
                }
            }
        }
    }

    for p in &mut cfg.profiles {
        if p == old_name {
            *p = clean_new.clone();
        }
    }
    if cfg.active_profile == old_name {
        cfg.active_profile = clean_new;
    }
    save_profiles_config(app_data_root, &cfg).map_err(|e| e.to_string())?;
    Ok(cfg)
}

pub fn delete_profile(app_data_root: &Path, name: &str) -> Result<ProfilesConfig, String> {
    if name == "Default" {
        return Err("The 'Default' profile cannot be deleted.".to_string());
    }
    let mut cfg = load_or_init_profiles(app_data_root).map_err(|e| e.to_string())?;
    let p_dir = app_data_root.join("profiles").join(name);
    if p_dir.exists() {
        fs::remove_dir_all(&p_dir).map_err(|e| format!("Failed to delete profile directory: {e}"))?;
    }
    cfg.profiles.retain(|p| p != name);
    if !cfg.profiles.iter().any(|p| p == "Default") {
        cfg.profiles.insert(0, "Default".to_string());
    }
    if cfg.active_profile == name {
        cfg.active_profile = cfg.profiles.first().cloned().unwrap_or_else(|| "Default".to_string());
    }
    save_profiles_config(app_data_root, &cfg).map_err(|e| e.to_string())?;
    Ok(cfg)
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SafetyBackupRecord {
    pub profile: String,
    pub backup_dir: String,
    pub created_at: String,
    pub files_copied: usize,
    pub bytes_copied: u64,
}

fn has_meaningful_profile_data(profile_dir: &Path) -> bool {
    if !profile_dir.exists() {
        return false;
    }
    let markers = [
        "truehour.db",
        "app_settings.json",
        "settings.json",
        "tags.json",
        "time_chain.json",
        "active_session.json",
    ];
    if markers.iter().any(|m| profile_dir.join(m).exists()) {
        return true;
    }
    let sessions = profile_dir.join("sessions");
    if let Ok(entries) = fs::read_dir(sessions) {
        for entry in entries.flatten() {
            if entry.path().is_file() {
                return true;
            }
        }
    }
    false
}

fn copy_dir_recursive(src: &Path, dst: &Path) -> io::Result<(usize, u64)> {
    fs::create_dir_all(dst)?;
    let mut files_copied = 0usize;
    let mut bytes_copied = 0u64;

    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let src_path = entry.path();
        let file_name = entry.file_name();
        let name_str = file_name.to_string_lossy();

        if name_str.ends_with(".tmp")
            || name_str.contains(".tmp.")
            || name_str.ends_with(".lock")
        {
            continue;
        }

        let dst_path = dst.join(&file_name);
        let file_type = entry.file_type()?;
        if file_type.is_dir() {
            let (sub_files, sub_bytes) = copy_dir_recursive(&src_path, &dst_path)?;
            files_copied += sub_files;
            bytes_copied += sub_bytes;
        } else if file_type.is_file() {
            let bytes = fs::copy(&src_path, &dst_path)?;
            files_copied += 1;
            bytes_copied += bytes;
        }
    }

    Ok((files_copied, bytes_copied))
}

fn sanitize_path_component(name: &str) -> String {
    name.chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '-' || c == '_' {
                c
            } else {
                '_'
            }
        })
        .collect()
}

/// Performs an automatic one-time safety backup of the active profile BEFORE any live data
/// is opened or mutated by Rust v5. Returns `Ok(Some(record))` if a backup was created on
/// this launch, or `Ok(None)` if already backed up previously or the profile has no prior data.
pub fn ensure_first_launch_safety_backup(
    paths: &ProfilePaths,
) -> io::Result<Option<SafetyBackupRecord>> {
    let safe_name = sanitize_path_component(&paths.profile_name);
    let done_marker = paths.safety_backups_dir.join(format!("{safe_name}.done"));

    if done_marker.exists() {
        return Ok(None);
    }

    if !has_meaningful_profile_data(&paths.profile_dir) {
        return Ok(None);
    }

    fs::create_dir_all(&paths.safety_backups_dir)?;
    let stamp = Local::now().format("%Y%m%d_%H%M%S").to_string();
    let base_name = format!("{safe_name}_pre_v5_{stamp}");
    let tmp_dir = paths.safety_backups_dir.join(format!("{base_name}.tmp"));
    let final_dir = paths.safety_backups_dir.join(&base_name);

    if tmp_dir.exists() {
        let _ = fs::remove_dir_all(&tmp_dir);
    }

    let (files_copied, bytes_copied) = match copy_dir_recursive(&paths.profile_dir, &tmp_dir) {
        Ok(counts) => counts,
        Err(e) => {
            let _ = fs::remove_dir_all(&tmp_dir);
            return Err(e);
        }
    };

    if final_dir.exists() {
        let _ = fs::remove_dir_all(&final_dir);
    }
    fs::rename(&tmp_dir, &final_dir)?;

    let record = SafetyBackupRecord {
        profile: paths.profile_name.clone(),
        backup_dir: final_dir.to_string_lossy().to_string(),
        created_at: Local::now().to_rfc3339(),
        files_copied,
        bytes_copied,
    };
    let marker_json = serde_json::to_string_pretty(&record).map_err(io::Error::other)?;
    atomic_write_str(&done_marker, &marker_json)?;

    Ok(Some(record))
}

#[derive(Debug)]
pub struct SingleInstanceLock {
    lock_path: PathBuf,
    file: std::sync::Mutex<Option<File>>,
}

impl SingleInstanceLock {
    /// Acquires `%LOCALAPPDATA%\TrueHour\truehour.lock` with `FILE_SHARE_READ` (`share_mode(1)`),
    /// matching Qt's `QLockFile` mutual-exclusion behavior on Windows so Python v4.2 and Rust v5.0
    /// can never run simultaneously and double-track.
    pub fn acquire(lock_path: &Path) -> io::Result<Self> {
        if let Some(parent) = lock_path.parent() {
            fs::create_dir_all(parent)?;
        }

        let mut opts = OpenOptions::new();
        opts.create(true).write(true).truncate(true);
        #[cfg(windows)]
        {
            // FILE_SHARE_READ = 1: matches QLockFile on Windows. Second process fails with err 32.
            opts.share_mode(1);
        }

        let mut file = opts.open(lock_path)?;
        let pid = std::process::id();
        let host = std::env::var("COMPUTERNAME")
            .or_else(|_| std::env::var("HOSTNAME"))
            .unwrap_or_else(|_| "localhost".to_string());
        let payload = format!("{pid}\nTrueHour\n{host}\n");
        let _ = file.write_all(payload.as_bytes());
        let _ = file.flush();

        Ok(Self {
            lock_path: lock_path.to_path_buf(),
            file: std::sync::Mutex::new(Some(file)),
        })
    }

    /// Explicitly drops the OS lock handle and deletes `truehour.lock`.
    /// Needed on Windows when an event loop exits abruptly before Drop runs.
    pub fn release(&self) {
        if let Ok(mut guard) = self.file.lock() {
            drop(guard.take());
        }
        let _ = fs::remove_file(&self.lock_path);
    }
}

impl Drop for SingleInstanceLock {
    fn drop(&mut self) {
        self.release();
    }
}

#[cfg(windows)]
pub fn show_native_error_dialog(title: &str, message: &str) {
    use windows::core::PCWSTR;
    use windows::Win32::UI::WindowsAndMessaging::{MessageBoxW, MB_ICONWARNING, MB_OK, MB_TOPMOST};

    let title_w: Vec<u16> = title.encode_utf16().chain(std::iter::once(0)).collect();
    let msg_w: Vec<u16> = message.encode_utf16().chain(std::iter::once(0)).collect();
    unsafe {
        MessageBoxW(
            None,
            PCWSTR(msg_w.as_ptr()),
            PCWSTR(title_w.as_ptr()),
            MB_OK | MB_ICONWARNING | MB_TOPMOST,
        );
    }
}

#[cfg(not(windows))]
pub fn show_native_error_dialog(_title: &str, message: &str) {
    eprintln!("{message}");
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_profiles_load_and_paths() {
        let tmp = TempDir::new().unwrap();
        let root = tmp.path().join("TrueHour");
        fs::create_dir_all(&root).unwrap();
        fs::write(
            root.join("profiles.json"),
            r#"{"active_profile": "Mightyiest", "profiles": ["Default", "Mightyiest"], "custom_meta": 42}"#,
        )
        .unwrap();

        let cfg = load_or_init_profiles(&root).unwrap();
        assert_eq!(cfg.active_profile, "Mightyiest");
        assert_eq!(cfg.profiles, vec!["Default", "Mightyiest"]);
        assert_eq!(cfg.extra.get("custom_meta").and_then(|v| v.as_i64()), Some(42));

        let paths = ProfilePaths::from_root_and_profile(root.clone(), cfg.active_profile);
        assert_eq!(paths.profile_dir, root.join("profiles").join("Mightyiest"));
        assert_eq!(paths.db_file, root.join("profiles").join("Mightyiest").join("truehour.db"));
    }

    #[test]
    fn test_one_time_safety_backup_runs_once_and_skips_tmp_lock() {
        let tmp = TempDir::new().unwrap();
        let root = tmp.path().join("TrueHour");
        let paths = ProfilePaths::from_root_and_profile(root, "Work".to_string());
        paths.ensure_dirs().unwrap();

        fs::write(&paths.app_settings_file, r#"{"hourly_rate": 50}"#).unwrap();
        fs::write(paths.sessions_dir.join("session_2026-01-01_09-00-00.json"), "{}").unwrap();
        fs::write(paths.profile_dir.join("ignore.tmp"), "tmp").unwrap();
        fs::write(paths.profile_dir.join("ignore.lock"), "lock").unwrap();

        let first = ensure_first_launch_safety_backup(&paths).unwrap();
        assert!(first.is_some());
        let record = first.unwrap();
        let bdir = PathBuf::from(&record.backup_dir);
        assert!(bdir.join("app_settings.json").exists());
        assert!(bdir.join("sessions").join("session_2026-01-01_09-00-00.json").exists());
        assert!(!bdir.join("ignore.tmp").exists());
        assert!(!bdir.join("ignore.lock").exists());

        // Second call must be a no-op
        let second = ensure_first_launch_safety_backup(&paths).unwrap();
        assert!(second.is_none());
    }

    #[test]
    fn test_single_instance_lock_mutual_exclusion() {
        let tmp = TempDir::new().unwrap();
        let lock_path = tmp.path().join("truehour.lock");

        let lock1 = SingleInstanceLock::acquire(&lock_path).unwrap();
        let second = SingleInstanceLock::acquire(&lock_path);
        assert!(second.is_err(), "Second acquisition while lock1 is open must fail");
        drop(lock1);

        let lock3 = SingleInstanceLock::acquire(&lock_path);
        assert!(lock3.is_ok(), "Acquisition after drop must succeed");

        let lock3 = lock3.unwrap();
        assert!(lock_path.exists());
        lock3.release();
        assert!(!lock_path.exists());
        let lock4 = SingleInstanceLock::acquire(&lock_path);
        assert!(lock4.is_ok(), "Acquisition after explicit release() must succeed");
    }

    #[test]
    fn test_profile_crud_create_switch_rename_delete() {
        let tmp = TempDir::new().unwrap();
        let root = tmp.path().join("TrueHour");
        fs::create_dir_all(&root).unwrap();

        // Validation errors
        assert!(create_profile(&root, "   ").is_err());
        assert!(create_profile(&root, "../evil").is_err());
        assert!(create_profile(&root, "bad/name").is_err());

        // Create & reject case-insensitive duplicate
        let cfg1 = create_profile(&root, "ClientWork").unwrap();
        assert_eq!(cfg1.profiles, vec!["Default", "ClientWork"]);
        assert!(create_profile(&root, "clientwork").is_err());
        assert!(root.join("profiles").join("ClientWork").join("sessions").exists());

        // Switch active profile & missing error
        let cfg2 = switch_profile(&root, "ClientWork").unwrap();
        assert_eq!(cfg2.active_profile, "ClientWork");
        assert!(switch_profile(&root, "NonExistent").is_err());

        // Seed logo path inside old profile dir to verify rewrite on rename
        let old_pdir = root.join("profiles").join("ClientWork");
        let old_logo = old_pdir.join("logo").join("mark.png").to_string_lossy().to_string();
        fs::write(
            old_pdir.join("app_settings.json"),
            serde_json::to_string_pretty(&serde_json::json!({
                "business_logo_path": old_logo
            }))
            .unwrap(),
        )
        .unwrap();

        // Block Default rename, rename ClientWork -> StudioA
        assert!(rename_profile(&root, "Default", "Custom").is_err());
        let cfg3 = rename_profile(&root, "ClientWork", "StudioA").unwrap();
        assert_eq!(cfg3.active_profile, "StudioA");
        assert!(cfg3.profiles.contains(&"StudioA".to_string()));
        assert!(!cfg3.profiles.contains(&"ClientWork".to_string()));
        assert!(!old_pdir.exists());
        let new_settings_raw =
            fs::read_to_string(root.join("profiles").join("StudioA").join("app_settings.json"))
                .unwrap();
        assert!(new_settings_raw.contains("StudioA"));

        // Block Default delete, delete StudioA falls back to Default
        assert!(delete_profile(&root, "Default").is_err());
        let cfg4 = delete_profile(&root, "StudioA").unwrap();
        assert_eq!(cfg4.active_profile, "Default");
        assert_eq!(cfg4.profiles, vec!["Default"]);
        assert!(!root.join("profiles").join("StudioA").exists());
    }
}
