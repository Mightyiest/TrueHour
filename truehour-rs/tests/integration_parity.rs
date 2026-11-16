use serde_json::json;
use std::fs;
use std::sync::Arc;
use tempfile::TempDir;
use truehour_lib::appinfo::{AppResolver, ForegroundApp};
use truehour_lib::config::{
    ensure_first_launch_safety_backup, load_or_init_profiles, ProfilePaths, SingleInstanceLock,
};
use truehour_lib::crypto;
use truehour_lib::db;
use truehour_lib::report::{move_session_to_trash, rename_saved_session, save_to_history};
use truehour_lib::secure_time::{hash_chain_entry_fields, to_python_canonical_json};
use truehour_lib::settings::AppSettings;
use truehour_lib::tags::TagManager;
use truehour_lib::tracker::{AppTracker, SystemProbe};

struct DummyProbe;
impl SystemProbe for DummyProbe {
    fn get_foreground_app(&self) -> ForegroundApp {
        ForegroundApp {
            friendly_name: "Visual Studio Code".into(),
            exe_path: r"C:\Apps\Code.exe".into(),
        }
    }
    fn get_idle_seconds(&self) -> f64 {
        0.0
    }
}

#[test]
fn test_python_fernet_v2_and_sha256_chain_interop() {
    // Generated verbatim from Python v4.2 crypto.py & secure_time.py:
    let py_seed = "127b59c783ac35fd62509f74fe365d9d8261627109ca413a4d1dde02f268edd0";
    let py_token = "v2:gAAAAABq-WTECZTLB80ohHFQf6n7YdmWtTONIQrA_KeuX3_OcZ-ZcPdbmkdoqTX4bXW8YtpsKzvRtY7rh6Oqsbr51NZ8vBfHnr2q1ySkcBGkg74DcGcWw9Y=";
    assert_eq!(crypto::decrypt_string(py_token, py_seed), "Account-987654321");

    let entry = json!({
        "event_type": "TRACKING_ENTRY",
        "data": {
            "app": "Code \u{2014} Work",
            "duration": 2.5,
            "monotonic_time": 12.25,
            "integrity_status": "VALID"
        },
        "previous_hash": "GENESIS",
        "timestamp": "2026-11-15T15:00:00.123456"
    });
    assert_eq!(
        to_python_canonical_json(&entry),
        r#"{"data": {"app": "Code \u2014 Work", "duration": 2.5, "integrity_status": "VALID", "monotonic_time": 12.25}, "event_type": "TRACKING_ENTRY", "previous_hash": "GENESIS", "timestamp": "2026-11-15T15:00:00.123456"}"#
    );
    assert_eq!(
        hash_chain_entry_fields(&entry),
        "1eba2bd6f0d87adbbe5600163a0c49771aecb6a61908e06efeb50bc443e0cb03"
    );
}

#[test]
fn test_full_isolated_v4_migration_and_stop_save_trash_flow() {
    let tmp = TempDir::new().unwrap();
    let root = tmp.path().join("TrueHour");
    fs::create_dir_all(&root).unwrap();

    // Seed Python v4.2 root + active profile
    fs::write(
        root.join("profiles.json"),
        r#"{"active_profile": "Mightyiest", "profiles": ["Default", "Mightyiest"]}"#,
    )
    .unwrap();
    let cfg = load_or_init_profiles(&root).unwrap();
    assert_eq!(cfg.active_profile, "Mightyiest");
    let paths = ProfilePaths::from_root_and_profile(root.clone(), cfg.active_profile);
    paths.ensure_dirs().unwrap();

    // Populate Python v4.2 settings + session + chain + wal stubs
    let v4_settings = json!({
        "confirm_on_close": true,
        "hourly_rate": 40.0,
        "currency_symbol": "$",
        "idle_threshold_seconds_total": 180,
        "theme_style": "modern-dark",
        "dark_mode": true,
        "bank_routing_enc": "v2:encrypted_blob_here",
        "client_email": "billing@example.com"
    });
    fs::write(
        &paths.app_settings_file,
        serde_json::to_string_pretty(&v4_settings).unwrap(),
    )
    .unwrap();
    fs::write(
        &paths.settings_file,
        r#"{"excluded_apps": ["Spotify"]}"#,
    )
    .unwrap();
    fs::write(
        paths.sessions_dir.join("session_2026-11-10_09-00-00.json"),
        serde_json::to_string_pretty(&json!({
            "session_name": "Prior Python Session",
            "date": "2026-11-10",
            "start": "09:00:00",
            "end": "10:00:00",
            "total_seconds": 3600,
            "counted_seconds": 3600,
            "apps": [{"name": "VS Code", "seconds": 3600, "excluded": false, "tag": "Development"}]
        }))
        .unwrap(),
    )
    .unwrap();

    // 1. Lock + one-time safety backup BEFORE DB initialization
    let _lock = SingleInstanceLock::acquire(&paths.lock_file).unwrap();
    let backup = ensure_first_launch_safety_backup(&paths).unwrap().unwrap();
    assert!(std::path::Path::new(&backup.backup_dir)
        .join("app_settings.json")
        .exists());
    assert!(ensure_first_launch_safety_backup(&paths).unwrap().is_none());

    // 2. Initialize SQLite WAL & rebuild daily_summary from Python history
    db::init_database(&paths).unwrap();
    db::rebuild_all_summaries(&paths, false).unwrap();
    let prior_row = db::get_daily_summary(&paths, "2026-11-10").unwrap().unwrap();
    assert_eq!(prior_row.total_seconds, 3600);
    assert_eq!(prior_row.session_count, 1);

    // 3. Inline quick-settings update preserves all Phase 2/3 encrypted fields
    let resolver = AppResolver::new(paths.name_overrides_file.clone());
    let tag_mgr = TagManager::new(paths.tags_file.clone(), Arc::clone(&resolver));
    let tracker = AppTracker::new(
        paths.clone(),
        resolver,
        tag_mgr,
        Arc::new(DummyProbe),
    );
    tracker.update_inline_settings(85.0, 240);
    let updated_settings = AppSettings::load(&paths.app_settings_file);
    assert_eq!(updated_settings.hourly_rate(), 85.0);
    assert_eq!(updated_settings.idle_threshold_seconds_total(), 240);
    assert_eq!(
        updated_settings
            .raw
            .get("bank_routing_enc")
            .and_then(|v| v.as_str()),
        Some("v2:encrypted_blob_here")
    );
    assert_eq!(
        updated_settings
            .raw
            .get("client_email")
            .and_then(|v| v.as_str()),
        Some("billing@example.com")
    );

    // 4. Start, accumulate a poll tick, stop & auto-save -> rename -> trash
    assert!(tracker.start(""));
    tracker.process_poll_tick(
        ForegroundApp {
            friendly_name: "Visual Studio Code".into(),
            exe_path: r"C:\Apps\Code.exe".into(),
        },
        0.0,
        truehour_lib::tracker::unix_now_f64(),
    );
    let (mut rep, _) = tracker.stop_and_build_report().unwrap();
    let saved_file = save_to_history(&paths, &mut rep).unwrap();
    assert!(saved_file.exists());

    let new_name = rename_saved_session(&saved_file, "Architecture Refactor").unwrap();
    assert_eq!(new_name, "Architecture Refactor");

    let trashed = move_session_to_trash(&paths, &saved_file).unwrap();
    assert!(trashed.exists());
    assert!(!saved_file.exists());
}
