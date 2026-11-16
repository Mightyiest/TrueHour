use crate::config::{atomic_write_str, ProfilePaths};
use crate::crypto;
use base64::engine::general_purpose::STANDARD as B64;
use base64::Engine;
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::Path;

pub const DEFAULT_AUTO_EXCLUDED_WINDOWS: &str = r#"# ══════════════════════════════════════════════════════════════════
# TrueHour — Auto-Excluded Apps
# ══════════════════════════════════════════════════════════════════
# Apps listed here are completely invisible to TrueHour.
# They will not appear in the app list, report, timeline, or CSV.
#
# Rules:
#   - One executable name per line (e.g. explorer.exe)
#   - Lines starting with # are comments and are ignored
#   - Names are case-insensitive
#   - .exe extension is optional
#
# To stop excluding an app, delete its line or add # in front.
# To exclude a new app, add its .exe name on a new line.
# Changes take effect on the next session start.
# ══════════════════════════════════════════════════════════════════

# ── TrueHour Self-Exclusion ───────────────────────────────────────
truehour.exe
truehour

# ── Windows Shell & Desktop ────────────────────────────────────────
explorer.exe
dwm.exe
shellexperiencehost.exe
applicationframehost.exe
startmenuexperiencehost.exe
searchhost.exe
searchindexer.exe
searchapp.exe
widgets.exe
textinputhost.exe

# ── Snipping & Screenshot Tools ───────────────────────────────────
snipping.exe
snippingtool.exe
screensketch.exe

# ── System Services & Background ──────────────────────────────────
svchost.exe
csrss.exe
wininit.exe
winlogon.exe
lsass.exe
services.exe
rundll32.exe
taskhostw.exe
spoolsv.exe
fontdriverhost.exe
sihost.exe
ctfmon.exe

# ── Windows Updates & Maintenance ─────────────────────────────────
tiworker.exe
trustedinstaller.exe
mrt.exe
wuauclt.exe
usoclient.exe

# ── Windows Defender & Security ───────────────────────────────────
msmpeng.exe
nissrv.exe
securityhealthsystray.exe
securityhealthservice.exe
smartscreen.exe

# ── Audio & Volume ────────────────────────────────────────────────
sndvol.exe
audiodg.exe
realtek.exe

# ── Input & Language ──────────────────────────────────────────────
TabTip.exe
InputMethod.exe

# ── System Utilities (brief use, not real work) ───────────────────
taskmgr.exe
dxdiag.exe
msinfo32.exe
msiexec.exe
consent.exe

# ── Quick Calculators & Clocks (optional) ─────────────────────────
# Uncomment below if you want to exclude these:
# calculator.exe
# calc.exe
# clock.exe
"#;

/// Full `app_settings.json` holder that keeps EVERY unknown/Phase-2/3 key untouched in `raw`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppSettings {
    pub raw: Map<String, Value>,
}

impl Default for AppSettings {
    fn default() -> Self {
        let mut raw = Map::new();
        raw.insert("confirm_on_close".into(), json!(true));
        raw.insert("min_track_seconds".into(), json!(2));
        raw.insert("auto_save_seconds".into(), json!(10));
        raw.insert("currency_symbol".into(), json!("$"));
        raw.insert("hourly_rate".into(), json!(0.0));
        raw.insert("idle_threshold_seconds_total".into(), json!(120));
        raw.insert("enable_distraction_auto_pause".into(), json!(false));
        raw.insert("distraction_apps".into(), json!([]));
        raw.insert("developer_mode".into(), json!(false));
        raw.insert("dark_mode".into(), json!(false));
        raw.insert("theme_style".into(), json!("light"));
        Self { raw }
    }
}

impl AppSettings {
    pub fn load(path: &Path) -> Self {
        let mut defaults = Self::default();
        if !path.exists() {
            let _ = defaults.save(path);
            return defaults;
        }
        if let Ok(raw_str) = fs::read_to_string(path) {
            let clean = raw_str.trim_start_matches('\u{feff}');
            if let Ok(Value::Object(loaded)) = serde_json::from_str::<Value>(clean) {
                for (k, v) in loaded {
                    defaults.raw.insert(k, v);
                }
                // Respect legacy dark_mode if theme_style was missing or default while dark_mode=true
                if !defaults.raw.contains_key("theme_style") {
                    let dm = defaults.dark_mode();
                    defaults.raw.insert(
                        "theme_style".into(),
                        json!(if dm { "modern-dark" } else { "light" }),
                    );
                }
            }
        }
        defaults
    }

    pub fn save(&self, path: &Path) -> std::io::Result<()> {
        let json_str =
            serde_json::to_string_pretty(&self.raw).map_err(std::io::Error::other)?;
        atomic_write_str(path, &json_str)
    }

    pub fn confirm_on_close(&self) -> bool {
        self.raw
            .get("confirm_on_close")
            .and_then(|v| v.as_bool())
            .unwrap_or(true)
    }

    pub fn min_track_seconds(&self) -> i64 {
        self.raw
            .get("min_track_seconds")
            .and_then(|v| v.as_i64())
            .unwrap_or(0)
            .max(0)
    }

    pub fn auto_save_seconds(&self) -> u64 {
        self.raw
            .get("auto_save_seconds")
            .and_then(|v| v.as_u64())
            .unwrap_or(60)
    }

    pub fn currency_symbol(&self) -> String {
        let raw = self
            .raw
            .get("currency_symbol")
            .and_then(|v| v.as_str())
            .unwrap_or("$");
        // Match Python v4.2 app.py: `str(raw_curr).split()[0].split("(")[0].strip() or "$"`
        let first_ws = raw.split_whitespace().next().unwrap_or("");
        let stripped = first_ws.split('(').next().unwrap_or("").trim();
        if stripped.is_empty() {
            "$".to_string()
        } else {
            stripped.to_string()
        }
    }

    pub fn hourly_rate(&self) -> f64 {
        self.raw
            .get("hourly_rate")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.0)
            .max(0.0)
    }

    pub fn set_hourly_rate(&mut self, rate: f64) {
        let clamped = if rate.is_finite() { rate.max(0.0) } else { 0.0 };
        let rounded = (clamped * 100.0).round() / 100.0;
        self.raw.insert("hourly_rate".into(), json!(rounded));
    }

    pub fn idle_threshold_seconds_total(&self) -> u64 {
        if let Some(total) = self
            .raw
            .get("idle_threshold_seconds_total")
            .and_then(|v| v.as_u64())
        {
            return total;
        }
        let mins = self
            .raw
            .get("idle_threshold_minutes")
            .and_then(|v| v.as_u64())
            .unwrap_or(5);
        mins * 60
    }

    pub fn set_idle_threshold_seconds_total(&mut self, seconds: u64) {
        self.raw
            .insert("idle_threshold_seconds_total".into(), json!(seconds));
    }

    pub fn enable_distraction_auto_pause(&self) -> bool {
        self.raw
            .get("enable_distraction_auto_pause")
            .and_then(|v| v.as_bool())
            .unwrap_or(true)
    }

    pub fn distraction_apps(&self) -> Vec<String> {
        self.raw
            .get("distraction_apps")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|v| v.as_str().map(|s| s.to_string()))
                    .collect()
            })
            .unwrap_or_default()
    }

    pub fn set_distraction_apps(&mut self, apps: Vec<String>) {
        self.raw.insert("distraction_apps".into(), json!(apps));
    }

    pub fn dark_mode(&self) -> bool {
        self.raw
            .get("dark_mode")
            .and_then(|v| v.as_bool())
            .unwrap_or(false)
    }

    pub fn theme_style(&self) -> String {
        let style = self
            .raw
            .get("theme_style")
            .and_then(|v| v.as_str())
            .unwrap_or("light");
        match style {
            "light" | "modern-dark" | "classic-dark" => style.to_string(),
            _ => "light".to_string(),
        }
    }

    pub fn set_theme_style(&mut self, style: &str) {
        let normalized = match style {
            "light" | "modern-dark" | "classic-dark" => style,
            _ => "light",
        };
        self.raw.insert("theme_style".into(), json!(normalized));
        self.raw
            .insert("dark_mode".into(), json!(normalized != "light"));
    }

    pub fn developer_mode(&self) -> bool {
        self.raw
            .get("developer_mode")
            .and_then(|v| v.as_bool())
            .unwrap_or(false)
    }

    pub fn set_developer_mode(&mut self, enabled: bool) {
        self.raw.insert("developer_mode".into(), json!(enabled));
    }

    pub fn weekly_goal_hours(&self) -> f64 {
        self.raw
            .get("weekly_goal_hours")
            .and_then(|v| v.as_f64())
            .unwrap_or(40.0)
            .max(0.0)
    }

    pub fn set_weekly_goal_hours(&mut self, hours: f64) {
        let clamped = if hours.is_finite() { hours.max(0.0) } else { 40.0 };
        self.raw.insert("weekly_goal_hours".into(), json!(clamped));
    }
}

pub fn generate_uuid_v4() -> String {
    let mut bytes = [0u8; 16];
    let _ = getrandom::getrandom(&mut bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    format!(
        "{:02x}{:02x}{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}",
        bytes[0], bytes[1], bytes[2], bytes[3],
        bytes[4], bytes[5],
        bytes[6], bytes[7],
        bytes[8], bytes[9],
        bytes[10], bytes[11], bytes[12], bytes[13], bytes[14], bytes[15]
    )
}

pub fn image_file_to_data_uri(path: &Path) -> Option<String> {
    if !path.exists() {
        return None;
    }
    let ext = path
        .extension()
        .and_then(|e| e.to_str())
        .map(|s| s.to_ascii_lowercase())?;
    let mime = match ext.as_str() {
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        _ => return None,
    };
    let bytes = fs::read(path).ok()?;
    Some(format!("data:{mime};base64,{}", B64.encode(&bytes)))
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QrCodeItemDto {
    pub filename: String,
    pub link: String,
    pub data_uri: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FullSettingsDto {
    pub confirm_on_close: bool,
    pub developer_mode: bool,
    pub theme_style: String,
    pub dark_mode: bool,
    pub min_track_seconds: i64,
    pub auto_save_seconds: u64,
    pub idle_threshold_seconds_total: u64,
    pub currency_symbol_raw: String,
    pub currency_symbol: String,
    pub hourly_rate: f64,
    pub enable_distraction_auto_pause: bool,
    pub distraction_apps: Vec<String>,
    pub weekly_goal_hours: f64,

    // Business Profile
    pub business_name: String,
    pub business_address: String,
    pub business_emails: Vec<String>,
    pub business_phone: String,
    pub business_payment: String,

    // Bank Transfer Details (plaintext in DTO for UI editing; encrypted on disk)
    pub enable_bank_details: bool,
    pub bank_holder: String,
    pub bank_account: String,
    pub bank_routing: String,
    pub bank_swift: String,
    pub bank_name: String,
    pub bank_address: String,

    // Default Client Profile
    pub client_name: String,
    pub client_address: String,
    pub client_emails: Vec<String>,

    // Business Logo
    pub enable_business_logo: bool,
    pub business_logo_path: String,

    // Payment QR Codes (up to 4)
    pub qr_code_paths: Vec<String>,
    pub qr_code_links: HashMap<String, String>,
    pub qr_code_items: Vec<QrCodeItemDto>,

    // Privacy Masking
    pub mask_business_emails: bool,
    pub mask_business_phone: bool,
    pub mask_client_emails: bool,
}

fn get_str(raw: &Map<String, Value>, key: &str, default: &str) -> String {
    raw.get(key)
        .and_then(|v| v.as_str())
        .unwrap_or(default)
        .to_string()
}

fn get_bool(raw: &Map<String, Value>, key: &str, default: bool) -> bool {
    raw.get(key).and_then(|v| v.as_bool()).unwrap_or(default)
}

fn get_str_vec(raw: &Map<String, Value>, key: &str) -> Vec<String> {
    raw.get(key)
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(|s| s.trim().to_string()))
                .filter(|s| !s.is_empty())
                .collect()
        })
        .unwrap_or_default()
}

pub fn load_full_settings(paths: &ProfilePaths) -> FullSettingsDto {
    let settings = AppSettings::load(&paths.app_settings_file);
    let raw = &settings.raw;
    let anon_id = get_str(raw, "anonymous_user_id", "");

    let mut business_emails = get_str_vec(raw, "business_emails");
    if business_emails.is_empty() {
        let legacy = get_str(raw, "business_email", "");
        if !legacy.trim().is_empty() {
            business_emails = legacy
                .split(',')
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .collect();
        }
    }

    let mut c_primary = crypto::CachedSeedCipher::new(crypto::get_secure_key(&anon_id), None);
    let mut c_default = crypto::CachedSeedCipher::new(crypto::get_secure_key(""), None);
    let mut c_portable = crypto::CachedSeedCipher::new(crypto::get_portable_key(&anon_id), None);

    let mut decrypt_bank = |plain_key: &str, enc_key: &str| -> String {
        let enc_val = get_str(raw, enc_key, "");
        if !enc_val.is_empty() {
            for cipher in [&mut c_primary, &mut c_default, &mut c_portable] {
                let decoded = cipher.decrypt(&enc_val);
                if !decoded.is_empty() {
                    return decoded;
                }
            }
        }
        get_str(raw, plain_key, "")
    };

    let qr_code_paths = get_str_vec(raw, "qr_code_paths");
    let qr_code_links: HashMap<String, String> = raw
        .get("qr_code_links")
        .and_then(|v| v.as_object())
        .map(|obj| {
            obj.iter()
                .filter_map(|(k, v)| v.as_str().map(|s| (k.clone(), s.to_string())))
                .collect()
        })
        .unwrap_or_default();

    let qr_code_items: Vec<QrCodeItemDto> = qr_code_paths
        .iter()
        .take(4)
        .map(|fname| {
            let link = qr_code_links.get(fname).cloned().unwrap_or_default();
            let full_path = paths.qr_codes_dir.join(fname);
            let data_uri = image_file_to_data_uri(&full_path);
            QrCodeItemDto {
                filename: fname.clone(),
                link,
                data_uri,
            }
        })
        .collect();

    let theme_style = settings.theme_style();
    let legacy_mask = get_bool(raw, "mask_sensitive_data", false);

    FullSettingsDto {
        confirm_on_close: settings.confirm_on_close(),
        developer_mode: settings.developer_mode(),
        dark_mode: theme_style != "light",
        theme_style,
        min_track_seconds: settings.min_track_seconds(),
        auto_save_seconds: settings.auto_save_seconds(),
        idle_threshold_seconds_total: settings.idle_threshold_seconds_total(),
        currency_symbol_raw: get_str(raw, "currency_symbol", "$ (USD)"),
        currency_symbol: settings.currency_symbol(),
        hourly_rate: settings.hourly_rate(),
        enable_distraction_auto_pause: settings.enable_distraction_auto_pause(),
        distraction_apps: settings.distraction_apps(),
        weekly_goal_hours: settings.weekly_goal_hours(),

        business_name: get_str(raw, "business_name", ""),
        business_address: get_str(raw, "business_address", ""),
        business_emails,
        business_phone: get_str(raw, "business_phone", ""),
        business_payment: get_str(raw, "business_payment", ""),

        enable_bank_details: get_bool(raw, "enable_bank_details", true),
        bank_holder: decrypt_bank("bank_holder", "bank_holder_enc"),
        bank_account: decrypt_bank("bank_account", "bank_account_enc"),
        bank_routing: decrypt_bank("bank_routing", "bank_routing_enc"),
        bank_swift: decrypt_bank("bank_swift", "bank_swift_enc"),
        bank_name: decrypt_bank("bank_name", "bank_name_enc"),
        bank_address: decrypt_bank("bank_address", "bank_address_enc"),

        client_name: get_str(raw, "client_name", ""),
        client_address: get_str(raw, "client_address", ""),
        client_emails: get_str_vec(raw, "client_emails"),

        enable_business_logo: get_bool(raw, "enable_business_logo", true),
        business_logo_path: get_str(raw, "business_logo_path", ""),

        qr_code_paths,
        qr_code_links,
        qr_code_items,

        mask_business_emails: get_bool(raw, "mask_business_emails", legacy_mask),
        mask_business_phone: get_bool(raw, "mask_business_phone", legacy_mask),
        mask_client_emails: get_bool(raw, "mask_client_emails", legacy_mask),
    }
}

pub fn save_full_settings(
    paths: &ProfilePaths,
    dto: &FullSettingsDto,
) -> Result<AppSettings, String> {
    let mut settings = AppSettings::load(&paths.app_settings_file);
    let mut anon_id = get_str(&settings.raw, "anonymous_user_id", "");
    if anon_id.is_empty() {
        anon_id = generate_uuid_v4();
        settings
            .raw
            .insert("anonymous_user_id".into(), json!(anon_id));
    }

    settings.raw.insert("confirm_on_close".into(), json!(dto.confirm_on_close));
    settings.set_developer_mode(dto.developer_mode);
    settings.set_theme_style(&dto.theme_style);
    settings.raw.insert("min_track_seconds".into(), json!(dto.min_track_seconds.max(0)));
    settings.raw.insert("auto_save_seconds".into(), json!(dto.auto_save_seconds.max(1)));
    settings.set_idle_threshold_seconds_total(dto.idle_threshold_seconds_total);
    let curr_raw = if dto.currency_symbol_raw.trim().is_empty() {
        dto.currency_symbol.trim()
    } else {
        dto.currency_symbol_raw.trim()
    };
    settings.raw.insert(
        "currency_symbol".into(),
        json!(if curr_raw.is_empty() { "$" } else { curr_raw }),
    );
    settings.set_hourly_rate(dto.hourly_rate);
    settings.raw.insert(
        "enable_distraction_auto_pause".into(),
        json!(dto.enable_distraction_auto_pause),
    );
    settings.set_distraction_apps(dto.distraction_apps.clone());
    settings.set_weekly_goal_hours(dto.weekly_goal_hours);

    // Business Profile
    settings.raw.insert("business_name".into(), json!(dto.business_name.trim()));
    settings.raw.insert("business_address".into(), json!(dto.business_address.trim()));
    settings.raw.insert("business_emails".into(), json!(dto.business_emails));
    settings.raw.insert(
        "business_email".into(),
        json!(dto.business_emails.join(", ")),
    );
    settings.raw.insert("business_phone".into(), json!(dto.business_phone.trim()));
    settings.raw.insert("business_payment".into(), json!(dto.business_payment.trim()));

    // Bank Transfer Details (Fernet v2 encrypted, clear plaintext keys matching Python v4.2)
    settings.raw.insert("enable_bank_details".into(), json!(dto.enable_bank_details));
    let bank_pairs = [
        ("bank_holder", "bank_holder_enc", dto.bank_holder.trim()),
        ("bank_account", "bank_account_enc", dto.bank_account.trim()),
        ("bank_routing", "bank_routing_enc", dto.bank_routing.trim()),
        ("bank_swift", "bank_swift_enc", dto.bank_swift.trim()),
        ("bank_name", "bank_name_enc", dto.bank_name.trim()),
        ("bank_address", "bank_address_enc", dto.bank_address.trim()),
    ];
    let mut bank_cipher = crypto::CachedSeedCipher::new(crypto::get_secure_key(&anon_id), None);
    for (plain_k, enc_k, val) in bank_pairs {
        settings.raw.insert(plain_k.into(), json!(""));
        let encrypted = if val.is_empty() {
            String::new()
        } else {
            bank_cipher.encrypt(val)
        };
        settings.raw.insert(enc_k.into(), json!(encrypted));
    }

    // Client Profile
    settings.raw.insert("client_name".into(), json!(dto.client_name.trim()));
    settings.raw.insert("client_address".into(), json!(dto.client_address.trim()));
    settings.raw.insert("client_emails".into(), json!(dto.client_emails));

    // Logo
    settings.raw.insert("enable_business_logo".into(), json!(dto.enable_business_logo));
    settings.raw.insert("business_logo_path".into(), json!(dto.business_logo_path.trim()));

    // QR Codes (cap at 4)
    let capped_qrs: Vec<String> = dto.qr_code_paths.iter().take(4).cloned().collect();
    settings.raw.insert("qr_code_paths".into(), json!(capped_qrs));
    settings.raw.insert("qr_code_links".into(), json!(dto.qr_code_links));

    // Privacy
    settings.raw.insert("mask_business_emails".into(), json!(dto.mask_business_emails));
    settings.raw.insert("mask_business_phone".into(), json!(dto.mask_business_phone));
    settings.raw.insert("mask_client_emails".into(), json!(dto.mask_client_emails));

    settings
        .save(&paths.app_settings_file)
        .map_err(|e| format!("Failed to save settings: {e}"))?;
    Ok(settings)
}

pub fn import_qr_code_image(paths: &ProfilePaths, src_path: &Path) -> Result<QrCodeItemDto, String> {
    if !src_path.exists() {
        return Err("Selected QR code image does not exist.".to_string());
    }
    let ext = src_path
        .extension()
        .and_then(|e| e.to_str())
        .map(|s| s.to_ascii_lowercase())
        .filter(|e| matches!(e.as_str(), "png" | "jpg" | "jpeg"))
        .ok_or_else(|| "QR code must be a PNG or JPG image.".to_string())?;
    fs::create_dir_all(&paths.qr_codes_dir).map_err(|e| e.to_string())?;
    let stamp = chrono::Local::now().format("%Y%m%d_%H%M%S_%3f");
    let fname = format!("qr_{stamp}.{ext}");
    let dst = paths.qr_codes_dir.join(&fname);
    fs::copy(src_path, &dst).map_err(|e| format!("Failed to copy QR image: {e}"))?;
    let data_uri = image_file_to_data_uri(&dst);
    Ok(QrCodeItemDto {
        filename: fname,
        link: String::new(),
        data_uri,
    })
}

pub fn delete_qr_code_image(paths: &ProfilePaths, filename: &str) {
    let clean = Path::new(filename).file_name().and_then(|n| n.to_str());
    if let Some(name) = clean {
        let p = paths.qr_codes_dir.join(name);
        let _ = fs::remove_file(p);
    }
}

/// Manages `settings.json` (`excluded_apps`) matching Python v4.2 schema.
#[derive(Debug, Clone)]
pub struct ExcludedSettings {
    pub raw: Map<String, Value>,
    pub excluded_apps: HashSet<String>,
}

impl ExcludedSettings {
    pub fn load(path: &Path) -> Self {
        let mut raw = Map::new();
        let mut excluded_apps = HashSet::new();
        if path.exists() {
            if let Ok(raw_str) = fs::read_to_string(path) {
                let clean = raw_str.trim_start_matches('\u{feff}');
                if let Ok(Value::Object(obj)) = serde_json::from_str::<Value>(clean) {
                    if let Some(arr) = obj.get("excluded_apps").and_then(|v| v.as_array()) {
                        for item in arr {
                            if let Some(name) = item.as_str() {
                                excluded_apps.insert(name.to_string());
                            }
                        }
                    }
                    raw = obj;
                }
            }
        }
        Self { raw, excluded_apps }
    }

    pub fn save(&mut self, path: &Path) -> std::io::Result<()> {
        let mut list: Vec<String> = self.excluded_apps.iter().cloned().collect();
        list.sort_by_key(|s| s.to_lowercase());
        self.raw.insert("excluded_apps".into(), json!(list));
        let json_str =
            serde_json::to_string_pretty(&self.raw).map_err(std::io::Error::other)?;
        atomic_write_str(path, &json_str)
    }

    pub fn is_excluded(&self, app_name: &str) -> bool {
        self.excluded_apps.contains(app_name)
    }

    pub fn set_excluded(&mut self, app_name: &str, excluded: bool) {
        if excluded {
            self.excluded_apps.insert(app_name.to_string());
        } else {
            self.excluded_apps.remove(app_name);
        }
    }
}

pub fn create_auto_excluded_if_missing(path: &Path) {
    if path.exists() {
        if let Ok(existing) = fs::read_to_string(path) {
            let lower = existing.to_lowercase();
            let missing: Vec<&str> = DEFAULT_AUTO_EXCLUDED_WINDOWS
                .lines()
                .map(|l| l.trim())
                .filter(|l| {
                    !l.is_empty()
                        && !l.starts_with('#')
                        && l.chars().next().is_some_and(|c| c.is_alphanumeric())
                })
                .filter(|raw| {
                    let exe = raw.to_lowercase();
                    let base = exe.strip_suffix(".exe").unwrap_or(&exe);
                    !lower.contains(base)
                })
                .collect();
            if !missing.is_empty() {
                let mut appended = existing;
                if !appended.ends_with('\n') {
                    appended.push('\n');
                }
                appended.push_str("\n# ── Automatically Excluded Apps (Added via update) ──\n");
                for m in missing {
                    appended.push_str(m);
                    appended.push('\n');
                }
                let _ = atomic_write_str(path, &appended);
            }
        }
        return;
    }

    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let _ = atomic_write_str(path, DEFAULT_AUTO_EXCLUDED_WINDOWS);
}

pub fn load_auto_excluded_exes(path: &Path) -> HashSet<String> {
    create_auto_excluded_if_missing(path);
    let mut set = HashSet::new();
    set.insert("truehour.exe".to_string());
    set.insert("truehour".to_string());

    if let Ok(raw) = fs::read_to_string(path) {
        for line in raw.lines() {
            let mut trimmed = line.trim().to_lowercase();
            if !trimmed.is_empty()
                && !trimmed.starts_with('#')
                && trimmed.chars().next().is_some_and(|c| c.is_alphanumeric())
            {
                if cfg!(windows) && !trimmed.ends_with(".exe") {
                    trimmed.push_str(".exe");
                }
                set.insert(trimmed);
            }
        }
    }
    set
}

pub fn is_auto_excluded_exe(exe_path: &str, auto_excluded: &HashSet<String>) -> bool {
    if exe_path.is_empty() {
        return false;
    }
    let exe_name = Path::new(exe_path)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or(exe_path)
        .to_lowercase();
    if exe_name == "truehour.exe" || exe_name == "truehour" {
        return true;
    }
    auto_excluded.contains(&exe_name)
}

pub fn ensure_profile_bootstrap_files(paths: &ProfilePaths) -> std::io::Result<()> {
    paths.ensure_dirs()?;
    create_auto_excluded_if_missing(&paths.auto_excluded_file);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_app_settings_preserves_phase2_and_encrypted_fields() {
        let tmp = TempDir::new().unwrap();
        let file = tmp.path().join("app_settings.json");

        let original = json!({
            "hourly_rate": 45.0,
            "idle_threshold_seconds_total": 180,
            "currency_symbol": "€",
            "theme_style": "modern-dark",
            "dark_mode": true,
            "bank_account_enc": "v2:gAAAAABsecret",
            "client_name": "Acme Corp",
            "anonymous_user_id": "user-uuid-123"
        });
        fs::write(&file, serde_json::to_string_pretty(&original).unwrap()).unwrap();

        let mut loaded = AppSettings::load(&file);
        assert_eq!(loaded.hourly_rate(), 45.0);
        assert_eq!(loaded.idle_threshold_seconds_total(), 180);
        assert_eq!(loaded.currency_symbol(), "€");
        assert_eq!(loaded.theme_style(), "modern-dark");

        // Update inline hourly rate & idle threshold from Phase 1 UI
        loaded.set_hourly_rate(75.5);
        loaded.set_idle_threshold_seconds_total(300);
        loaded.save(&file).unwrap();

        let reloaded = AppSettings::load(&file);
        assert_eq!(reloaded.hourly_rate(), 75.5);
        assert_eq!(reloaded.idle_threshold_seconds_total(), 300);
        assert_eq!(
            reloaded.raw.get("bank_account_enc").and_then(|v| v.as_str()),
            Some("v2:gAAAAABsecret")
        );
        assert_eq!(
            reloaded.raw.get("client_name").and_then(|v| v.as_str()),
            Some("Acme Corp")
        );
        assert_eq!(
            reloaded.raw.get("anonymous_user_id").and_then(|v| v.as_str()),
            Some("user-uuid-123")
        );
    }

    #[test]
    fn test_auto_excluded_loading_and_custom_preservation() {
        let tmp = TempDir::new().unwrap();
        let file = tmp.path().join("auto_excluded_apps.txt");
        let set = load_auto_excluded_exes(&file);
        assert!(is_auto_excluded_exe(r"C:\Windows\explorer.exe", &set));
        assert!(is_auto_excluded_exe("truehour.exe", &set));
        assert!(!is_auto_excluded_exe(r"C:\Tools\code.exe", &set));

        // Append custom app and verify missing defaults didn't erase custom entry
        let mut contents = fs::read_to_string(&file).unwrap();
        contents.push_str("\nspotify.exe\n");
        fs::write(&file, contents).unwrap();

        let reloaded = load_auto_excluded_exes(&file);
        assert!(is_auto_excluded_exe("C:\\Apps\\Spotify.exe", &reloaded));
    }

    #[test]
    fn test_python_v4_defaults_and_currency_stripping() {
        let defaults = AppSettings::default();
        assert_eq!(defaults.min_track_seconds(), 2);
        assert_eq!(defaults.auto_save_seconds(), 10);
        assert_eq!(defaults.idle_threshold_seconds_total(), 120);
        assert!(!defaults.enable_distraction_auto_pause());

        let tmp = TempDir::new().unwrap();
        let file = tmp.path().join("app_settings.json");
        fs::write(&file, r#"{"currency_symbol": "$ (USD)", "hourly_rate": 10.0}"#).unwrap();
        let mut loaded = AppSettings::load(&file);
        assert_eq!(loaded.currency_symbol(), "$");
        loaded.set_hourly_rate(12.0);
        loaded.save(&file).unwrap();

        let reloaded_raw = fs::read_to_string(&file).unwrap();
        assert!(reloaded_raw.contains("$ (USD)"));
    }

    #[test]
    fn test_zero_thresholds_preserved_on_full_settings_save() {
        let tmp = TempDir::new().unwrap();
        let paths = ProfilePaths::from_root_and_profile(tmp.path().to_path_buf(), "Default".into());
        paths.ensure_dirs().unwrap();
        let mut dto = load_full_settings(&paths);
        dto.min_track_seconds = 0;
        dto.auto_save_seconds = 1;
        dto.idle_threshold_seconds_total = 0;
        save_full_settings(&paths, &dto).unwrap();

        let reloaded = load_full_settings(&paths);
        assert_eq!(reloaded.min_track_seconds, 0);
        assert_eq!(reloaded.auto_save_seconds, 1);
        assert_eq!(reloaded.idle_threshold_seconds_total, 0);
    }
}
