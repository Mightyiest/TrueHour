use crate::config::{load_or_init_profiles, save_profiles_config, ProfilePaths, ProfilesConfig};
use crate::crypto::{self, BANK_FIELDS};
use crate::db;
use chrono::Local;
use crc32fast::Hasher;
use flate2::read::DeflateDecoder;
use flate2::write::DeflateEncoder;
use flate2::Compression;
use rusqlite::backup::Backup;
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use std::collections::HashMap;
use std::fs::{self, File};
use std::io::{self, Read, Write};
use std::path::{Component, Path, PathBuf};
use tempfile::TempDir;

const EXCLUDED_FILENAMES: &[&str] = &["token.json", "token.pickle", "client_secret.json"];
const EXCLUDED_EXTENSIONS: &[&str] = &["-wal", "-shm", ".tmp", ".lock"];

fn should_skip_file(name: &str) -> bool {
    let base = Path::new(name)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or(name);
    if EXCLUDED_FILENAMES.contains(&base) {
        return true;
    }
    EXCLUDED_EXTENSIONS.iter().any(|ext| name.ends_with(ext)) || name.contains(".tmp.")
}

// ---------------------------------------------------------------------------
// Minimal Standard ZIP Reader / Writer (Store = 0 & Deflate = 8) using flate2 + crc32fast
// ---------------------------------------------------------------------------

struct ZipEntryInput {
    name: String,
    data: Vec<u8>,
}

fn write_zip_deflate(dest: &Path, entries: &[ZipEntryInput]) -> io::Result<()> {
    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut out = File::create(dest)?;
    let mut central_records: Vec<(u32, u32, u32, u32, String)> = Vec::with_capacity(entries.len());
    let mut offset: u32 = 0;

    for entry in entries {
        let name_bytes = entry.name.as_bytes();
        let mut crc_hasher = Hasher::new();
        crc_hasher.update(&entry.data);
        let crc = crc_hasher.finalize();

        let mut encoder = DeflateEncoder::new(Vec::new(), Compression::default());
        encoder.write_all(&entry.data)?;
        let compressed = encoder.finish()?;

        let uncomp_len = entry.data.len() as u32;
        let comp_len = compressed.len() as u32;

        // Local file header (30 bytes + name)
        out.write_all(&0x0403_4b50u32.to_le_bytes())?; // signature
        out.write_all(&20u16.to_le_bytes())?; // version needed (2.0)
        out.write_all(&0x0800u16.to_le_bytes())?; // UTF-8 filename flag
        out.write_all(&8u16.to_le_bytes())?; // compression: Deflate (8)
        out.write_all(&0u16.to_le_bytes())?; // mod time
        out.write_all(&0x5421u16.to_le_bytes())?; // mod date
        out.write_all(&crc.to_le_bytes())?;
        out.write_all(&comp_len.to_le_bytes())?;
        out.write_all(&uncomp_len.to_le_bytes())?;
        out.write_all(&(name_bytes.len() as u16).to_le_bytes())?;
        out.write_all(&0u16.to_le_bytes())?; // extra len
        out.write_all(name_bytes)?;
        out.write_all(&compressed)?;

        central_records.push((crc, comp_len, uncomp_len, offset, entry.name.clone()));
        offset = offset
            .checked_add(30 + name_bytes.len() as u32 + comp_len)
            .ok_or_else(|| io::Error::other("Archive exceeds 4GB ZIP limit"))?;
    }

    let cd_offset = offset;
    let mut cd_size: u32 = 0;
    for (crc, comp_len, uncomp_len, local_off, name) in &central_records {
        let name_bytes = name.as_bytes();
        out.write_all(&0x0201_4b50u32.to_le_bytes())?; // central header sig
        out.write_all(&20u16.to_le_bytes())?; // version made by
        out.write_all(&20u16.to_le_bytes())?; // version needed
        out.write_all(&0x0800u16.to_le_bytes())?; // UTF-8 flag
        out.write_all(&8u16.to_le_bytes())?; // deflate
        out.write_all(&0u16.to_le_bytes())?;
        out.write_all(&0x5421u16.to_le_bytes())?;
        out.write_all(&crc.to_le_bytes())?;
        out.write_all(&comp_len.to_le_bytes())?;
        out.write_all(&uncomp_len.to_le_bytes())?;
        out.write_all(&(name_bytes.len() as u16).to_le_bytes())?;
        out.write_all(&0u16.to_le_bytes())?; // extra
        out.write_all(&0u16.to_le_bytes())?; // comment
        out.write_all(&0u16.to_le_bytes())?; // disk start
        out.write_all(&0u16.to_le_bytes())?; // int attr
        out.write_all(&0u32.to_le_bytes())?; // ext attr
        out.write_all(&local_off.to_le_bytes())?;
        out.write_all(name_bytes)?;
        cd_size += 46 + name_bytes.len() as u32;
    }

    let count = central_records.len() as u16;
    out.write_all(&0x0605_4b50u32.to_le_bytes())?; // EOCD sig
    out.write_all(&0u16.to_le_bytes())?;
    out.write_all(&0u16.to_le_bytes())?;
    out.write_all(&count.to_le_bytes())?;
    out.write_all(&count.to_le_bytes())?;
    out.write_all(&cd_size.to_le_bytes())?;
    out.write_all(&cd_offset.to_le_bytes())?;
    out.write_all(&0u16.to_le_bytes())?;
    out.flush()?;
    Ok(())
}

fn read_u16_le(buf: &[u8], pos: usize) -> Option<u16> {
    let slice: [u8; 2] = buf.get(pos..pos + 2)?.try_into().ok()?;
    Some(u16::from_le_bytes(slice))
}

fn read_u32_le(buf: &[u8], pos: usize) -> Option<u32> {
    let slice: [u8; 4] = buf.get(pos..pos + 4)?.try_into().ok()?;
    Some(u32::from_le_bytes(slice))
}

fn read_zip_entries(src: &Path) -> Result<Vec<(String, Vec<u8>)>, String> {
    let bytes = fs::read(src).map_err(|e| format!("Failed to read archive: {e}"))?;
    if bytes.len() < 22 {
        return Err("Not a valid ZIP archive.".to_string());
    }

    // Locate End of Central Directory (scan backwards from end up to 65KB comment range)
    let search_start = bytes.len().saturating_sub(65_558);
    let mut eocd_pos = None;
    let mut i = bytes.len() - 22;
    loop {
        if read_u32_le(&bytes, i) == Some(0x0605_4b50) {
            eocd_pos = Some(i);
            break;
        }
        if i <= search_start {
            break;
        }
        i -= 1;
    }
    let eocd = eocd_pos.ok_or_else(|| "Not a valid ZIP archive (missing EOCD).".to_string())?;
    let total_entries = read_u16_le(&bytes, eocd + 10).unwrap_or(0) as usize;
    let cd_offset = read_u32_le(&bytes, eocd + 16).unwrap_or(0) as usize;

    let mut cursor = cd_offset;
    let mut out = Vec::with_capacity(total_entries);
    for _ in 0..total_entries {
        if read_u32_le(&bytes, cursor) != Some(0x0201_4b50) {
            return Err("Corrupt ZIP central directory.".to_string());
        }
        let method = read_u16_le(&bytes, cursor + 10).unwrap_or(0);
        let crc_expected = read_u32_le(&bytes, cursor + 16).unwrap_or(0);
        let comp_size = read_u32_le(&bytes, cursor + 20).unwrap_or(0) as usize;
        let _uncomp_size = read_u32_le(&bytes, cursor + 24).unwrap_or(0) as usize;
        let name_len = read_u16_le(&bytes, cursor + 28).unwrap_or(0) as usize;
        let extra_len = read_u16_le(&bytes, cursor + 30).unwrap_or(0) as usize;
        let comment_len = read_u16_le(&bytes, cursor + 32).unwrap_or(0) as usize;
        let local_offset = read_u32_le(&bytes, cursor + 42).unwrap_or(0) as usize;

        let name_slice = bytes
            .get(cursor + 46..cursor + 46 + name_len)
            .ok_or_else(|| "Corrupt ZIP entry name.".to_string())?;
        let name = String::from_utf8_lossy(name_slice).to_string();
        cursor += 46 + name_len + extra_len + comment_len;

        // Read local header
        if read_u32_le(&bytes, local_offset) != Some(0x0403_4b50) {
            return Err("Corrupt ZIP local file header.".to_string());
        }
        let l_name_len = read_u16_le(&bytes, local_offset + 26).unwrap_or(0) as usize;
        let l_extra_len = read_u16_le(&bytes, local_offset + 28).unwrap_or(0) as usize;
        let data_start = local_offset + 30 + l_name_len + l_extra_len;
        let payload = bytes
            .get(data_start..data_start + comp_size)
            .ok_or_else(|| "Corrupt ZIP entry payload.".to_string())?;

        if name.ends_with('/') {
            continue;
        }

        let plain = match method {
            0 => payload.to_vec(),
            8 => {
                let mut dec = DeflateDecoder::new(payload);
                let mut buf = Vec::new();
                dec.read_to_end(&mut buf)
                    .map_err(|e| format!("Failed to decompress entry '{name}': {e}"))?;
                buf
            }
            other => {
                return Err(format!("Unsupported ZIP compression method {other} for '{name}'"));
            }
        };

        let mut crc_hasher = Hasher::new();
        crc_hasher.update(&plain);
        if crc_hasher.finalize() != crc_expected {
            return Err(format!("CRC mismatch in backup entry '{name}'."));
        }

        out.push((name, plain));
    }

    Ok(out)
}

fn is_safe_archive_rel_path(rel: &str) -> bool {
    if rel.is_empty() {
        return false;
    }
    let normalized = rel.replace('\\', "/");
    let p = Path::new(&normalized);
    if p.is_absolute() {
        return false;
    }
    for comp in p.components() {
        match comp {
            Component::ParentDir | Component::RootDir | Component::Prefix(_) => return false,
            _ => {}
        }
    }
    true
}

// ---------------------------------------------------------------------------
// Backup Logic (Python core/backup_manager.py v2 & v3 compatible)
// ---------------------------------------------------------------------------

fn snapshot_sqlite_bytes(db_path: &Path) -> io::Result<Vec<u8>> {
    let tmp = TempDir::new()?;
    let dest_db = tmp.path().join("clean_backup.db");
    {
        let src_conn = db::open_connection(db_path).map_err(io::Error::other)?;
        let _ = src_conn.pragma_update(None, "wal_checkpoint", "TRUNCATE");
        let mut dst_conn = rusqlite::Connection::open(&dest_db).map_err(io::Error::other)?;
        let bkp = Backup::new(&src_conn, &mut dst_conn).map_err(io::Error::other)?;
        bkp.run_to_completion(100, std::time::Duration::from_millis(5), None)
            .map_err(io::Error::other)?;
    }
    fs::read(&dest_db)
}

fn sanitize_settings_for_backup(
    raw_bytes: &[u8],
    mut pwd_cipher: Option<&mut crypto::CachedSeedCipher>,
) -> Vec<u8> {
    let Ok(mut val) = serde_json::from_slice::<Value>(raw_bytes) else {
        return raw_bytes.to_vec();
    };
    let Some(obj) = val.as_object_mut() else {
        return raw_bytes.to_vec();
    };

    let anon_id = obj
        .get("anonymous_user_id")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let local_key = crypto::get_secure_key(&anon_id);
    let portable_key = if anon_id.is_empty() {
        local_key.clone()
    } else {
        crypto::get_portable_key(&anon_id)
    };
    let mut local_cipher = crypto::CachedSeedCipher::new(local_key, None);
    let mut portable_cipher = crypto::CachedSeedCipher::new(portable_key, None);

    for &plain_fld in BANK_FIELDS {
        let enc_fld = format!("{plain_fld}_enc");
        let existing_enc = obj
            .get(&enc_fld)
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let existing_plain = obj
            .get(plain_fld)
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        let mut decrypted = String::new();
        if !existing_enc.is_empty() {
            decrypted = local_cipher.decrypt(&existing_enc);
            if decrypted.is_empty() {
                decrypted = portable_cipher.decrypt(&existing_enc);
            }
        }
        if decrypted.is_empty() && !existing_plain.is_empty() {
            decrypted = existing_plain;
        }

        if let Some(ref mut pc) = pwd_cipher {
            let new_enc = pc.encrypt(&decrypted);
            obj.insert(enc_fld, json!(new_enc));
        } else if !decrypted.is_empty() {
            let new_enc = portable_cipher.encrypt(&decrypted);
            obj.insert(enc_fld, json!(new_enc));
        }
        obj.remove(plain_fld);
    }

    serde_json::to_vec_pretty(&val).unwrap_or_else(|_| raw_bytes.to_vec())
}

fn restore_settings_from_backup(
    raw_bytes: &[u8],
    is_encrypted: bool,
    mut pwd_cipher: Option<&mut crypto::CachedSeedCipher>,
    password_present: bool,
) -> Vec<u8> {
    let Ok(mut val) = serde_json::from_slice::<Value>(raw_bytes) else {
        return raw_bytes.to_vec();
    };
    let Some(obj) = val.as_object_mut() else {
        return raw_bytes.to_vec();
    };

    let anon_id = obj
        .get("anonymous_user_id")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let target_local_key = crypto::get_secure_key(&anon_id);
    let portable_key = if anon_id.is_empty() {
        target_local_key.clone()
    } else {
        crypto::get_portable_key(&anon_id)
    };
    let mut local_cipher = crypto::CachedSeedCipher::new(target_local_key, None);
    let mut portable_cipher = crypto::CachedSeedCipher::new(portable_key, None);

    for &plain_fld in BANK_FIELDS {
        let enc_fld = format!("{plain_fld}_enc");
        let enc_val = obj
            .get(&enc_fld)
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let plain_val = obj
            .get(plain_fld)
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        let decrypted = if is_encrypted {
            if let Some(ref mut pc) = pwd_cipher {
                pc.decrypt(&enc_val)
            } else {
                String::new()
            }
        } else if !enc_val.is_empty() {
            let d = portable_cipher.decrypt(&enc_val);
            if d.is_empty() {
                local_cipher.decrypt(&enc_val)
            } else {
                d
            }
        } else {
            plain_val
        };

        if !decrypted.is_empty() {
            let re_enc = local_cipher.encrypt(&decrypted);
            obj.insert(enc_fld, json!(re_enc));
            obj.insert(plain_fld.to_string(), json!(""));
        } else if is_encrypted && !password_present {
            // Banking stripped
            obj.insert(enc_fld, json!(""));
            obj.insert(plain_fld.to_string(), json!(""));
        }
    }

    serde_json::to_vec_pretty(&val).unwrap_or_else(|_| raw_bytes.to_vec())
}

fn collect_profile_entries(
    profile_dir: &Path,
    archive_prefix: &str,
    mut pwd_cipher: Option<&mut crypto::CachedSeedCipher>,
    entries: &mut Vec<ZipEntryInput>,
) -> io::Result<usize> {
    let mut stack = vec![profile_dir.to_path_buf()];
    let mut session_count = 0usize;

    while let Some(dir) = stack.pop() {
        for item in fs::read_dir(&dir)? {
            let item = item?;
            let path = item.path();
            let ft = item.file_type()?;
            if ft.is_dir() {
                stack.push(path);
                continue;
            }
            if !ft.is_file() {
                continue;
            }
            let rel = path
                .strip_prefix(profile_dir)
                .map_err(io::Error::other)?
                .to_string_lossy()
                .replace('\\', "/");
            if should_skip_file(&rel) {
                continue;
            }
            if rel.starts_with("sessions/") && rel.ends_with(".json") {
                session_count += 1;
            }

            let arcname = if archive_prefix.is_empty() {
                rel.clone()
            } else {
                format!("{archive_prefix}/{rel}")
            };

            let data = if rel == "app_settings.json" {
                let raw = fs::read(&path)?;
                sanitize_settings_for_backup(&raw, pwd_cipher.as_deref_mut())
            } else if rel == "truehour.db" {
                snapshot_sqlite_bytes(&path).unwrap_or_else(|_| fs::read(&path).unwrap_or_default())
            } else {
                fs::read(&path)?
            };

            entries.push(ZipEntryInput {
                name: arcname,
                data,
            });
        }
    }

    Ok(session_count)
}

pub fn backup_workspace(
    app_data_root: &Path,
    dest_zip_path: &Path,
    password: Option<&str>,
) -> Result<(), String> {
    let clean_pwd = password.map(str::trim).filter(|s| !s.is_empty());
    let cfg = load_or_init_profiles(app_data_root).map_err(|e| e.to_string())?;
    let mut profiles = cfg.profiles.clone();

    let profiles_base = app_data_root.join("profiles");
    if profiles_base.exists() {
        if let Ok(read_dirs) = fs::read_dir(&profiles_base) {
            for ent in read_dirs.flatten() {
                if ent.path().is_dir() {
                    if let Some(name) = ent.file_name().to_str() {
                        if !profiles.iter().any(|p| p == name) {
                            profiles.push(name.to_string());
                        }
                    }
                }
            }
        }
    }

    let salt_vec = if clean_pwd.is_some() {
        let mut s = [0u8; 16];
        getrandom::getrandom(&mut s).map_err(|e| format!("Random salt generation failed: {e}"))?;
        Some(s.to_vec())
    } else {
        None
    };
    let salt_slice = salt_vec.as_deref();

    let mut pwd_cipher = if let (Some(pwd), Some(salt)) = (clean_pwd, salt_slice) {
        let pwd_key = crypto::get_password_key(pwd, Some(salt), crypto::PBKDF2_ITERATIONS_V2);
        Some(crypto::CachedSeedCipher::new(pwd_key, Some(salt)))
    } else {
        None
    };

    let mut entries = Vec::new();
    let mut sessions_by_profile: HashMap<String, usize> = HashMap::new();
    let mut total_sessions = 0usize;

    for prof in &profiles {
        let p_dir = profiles_base.join(prof);
        if p_dir.exists() {
            let cnt = collect_profile_entries(
                &p_dir,
                &format!("profiles/{prof}"),
                pwd_cipher.as_mut(),
                &mut entries,
            )
            .map_err(|e| format!("Failed collecting profile '{prof}': {e}"))?;
            sessions_by_profile.insert(prof.clone(), cnt);
            total_sessions += cnt;
        }
    }

    let host = std::env::var("COMPUTERNAME")
        .or_else(|_| std::env::var("HOSTNAME"))
        .unwrap_or_else(|_| "unknown".to_string());

    let mut meta = Map::new();
    meta.insert("version".into(), json!(3));
    meta.insert("type".into(), json!("full_workspace"));
    meta.insert("key_derivation".into(), json!("pbkdf2"));
    meta.insert("encrypted".into(), json!(clean_pwd.is_some()));
    meta.insert(
        "created_at".into(),
        json!(Local::now().format("%Y-%m-%dT%H:%M:%S%.6f").to_string()),
    );
    meta.insert("source_machine".into(), json!(host));
    meta.insert("active_profile".into(), json!(cfg.active_profile));
    meta.insert("profiles".into(), json!(profiles));
    meta.insert("total_sessions".into(), json!(total_sessions));
    meta.insert("sessions_by_profile".into(), json!(sessions_by_profile));

    if let (Some(ref mut pc), Some(salt)) = (pwd_cipher.as_mut(), salt_slice) {
        meta.insert("salt_hex".into(), json!(hex::encode(salt)));
        let verify_enc = pc.encrypt("truehour_backup_verify");
        meta.insert("verification_enc".into(), json!(verify_enc));
    }

    let meta_bytes = serde_json::to_vec_pretty(&Value::Object(meta)).map_err(|e| e.to_string())?;
    entries.insert(
        0,
        ZipEntryInput {
            name: "__backup_meta__.json".to_string(),
            data: meta_bytes,
        },
    );

    let profiles_json_path = app_data_root.join("profiles.json");
    let profiles_bytes = fs::read(&profiles_json_path).unwrap_or_else(|_| {
        serde_json::to_vec_pretty(&json!({
            "active_profile": cfg.active_profile,
            "profiles": profiles,
        }))
        .unwrap_or_default()
    });
    entries.insert(
        1,
        ZipEntryInput {
            name: "profiles.json".to_string(),
            data: profiles_bytes,
        },
    );

    write_zip_deflate(dest_zip_path, &entries)
        .map_err(|e| format!("Failed writing backup archive: {e}"))?;
    Ok(())
}

pub fn backup_profile(
    app_data_root: &Path,
    profile_name: &str,
    dest_zip_path: &Path,
    password: Option<&str>,
) -> Result<(), String> {
    let trimmed = profile_name.trim();
    if trimmed.is_empty() {
        return Err("Profile name is empty.".to_string());
    }
    let p_dir = app_data_root.join("profiles").join(trimmed);
    if !p_dir.exists() {
        return Err(format!("Profile directory does not exist: {trimmed}"));
    }

    let clean_pwd = password.map(str::trim).filter(|s| !s.is_empty());
    let salt_vec = if clean_pwd.is_some() {
        let mut s = [0u8; 16];
        getrandom::getrandom(&mut s).map_err(|e| format!("Random salt generation failed: {e}"))?;
        Some(s.to_vec())
    } else {
        None
    };
    let salt_slice = salt_vec.as_deref();

    let mut pwd_cipher = if let (Some(pwd), Some(salt)) = (clean_pwd, salt_slice) {
        let pwd_key = crypto::get_password_key(pwd, Some(salt), crypto::PBKDF2_ITERATIONS_V2);
        Some(crypto::CachedSeedCipher::new(pwd_key, Some(salt)))
    } else {
        None
    };

    let mut entries = Vec::new();
    let total_sessions = collect_profile_entries(&p_dir, "", pwd_cipher.as_mut(), &mut entries)
        .map_err(|e| format!("Failed collecting profile '{trimmed}': {e}"))?;

    let host = std::env::var("COMPUTERNAME")
        .or_else(|_| std::env::var("HOSTNAME"))
        .unwrap_or_else(|_| "unknown".to_string());

    let mut meta = Map::new();
    meta.insert("version".into(), json!(3));
    meta.insert("type".into(), json!("single_profile"));
    meta.insert("profile_name".into(), json!(trimmed));
    meta.insert("key_derivation".into(), json!("pbkdf2"));
    meta.insert("encrypted".into(), json!(clean_pwd.is_some()));
    meta.insert(
        "created_at".into(),
        json!(Local::now().format("%Y-%m-%dT%H:%M:%S%.6f").to_string()),
    );
    meta.insert("source_machine".into(), json!(host));
    meta.insert("total_sessions".into(), json!(total_sessions));

    if let (Some(ref mut pc), Some(salt)) = (pwd_cipher.as_mut(), salt_slice) {
        meta.insert("salt_hex".into(), json!(hex::encode(salt)));
        let verify_enc = pc.encrypt("truehour_backup_verify");
        meta.insert("verification_enc".into(), json!(verify_enc));
    }

    let meta_bytes = serde_json::to_vec_pretty(&Value::Object(meta)).map_err(|e| e.to_string())?;
    entries.insert(
        0,
        ZipEntryInput {
            name: "__backup_meta__.json".to_string(),
            data: meta_bytes,
        },
    );

    write_zip_deflate(dest_zip_path, &entries)
        .map_err(|e| format!("Failed writing profile backup archive: {e}"))?;
    Ok(())
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImportBackupResult {
    pub status: String, // "success" | "banking_stripped" | "password_required" | "wrong_password" | "error"
    pub backup_type: String,
    pub restored_profiles: Vec<String>,
    pub active_profile: String,
    pub total_sessions: usize,
    pub message: String,
}

pub fn import_backup(
    app_data_root: &Path,
    src_zip_path: &Path,
    password: Option<&str>,
    strip_if_encrypted: bool,
    fallback_target_profile: &str,
) -> ImportBackupResult {
    let err_res = |msg: String| ImportBackupResult {
        status: "error".into(),
        backup_type: "unknown".into(),
        restored_profiles: vec![],
        active_profile: fallback_target_profile.into(),
        total_sessions: 0,
        message: msg,
    };

    let entries = match read_zip_entries(src_zip_path) {
        Ok(e) => e,
        Err(msg) => return err_res(msg),
    };

    for (name, _) in &entries {
        if !is_safe_archive_rel_path(name) {
            return err_res(format!("Unsafe archive entry path prevented: {name}"));
        }
    }

    let mut entry_map: HashMap<String, Vec<u8>> = HashMap::new();
    for (name, data) in entries {
        entry_map.insert(name.replace('\\', "/"), data);
    }

    let mut is_encrypted = false;
    let mut verification_token = String::new();
    let mut key_derivation = "pbkdf2".to_string();
    let mut salt_bytes: Option<Vec<u8>> = None;
    let mut archive_type = "single_profile".to_string();
    let mut meta_active_profile = fallback_target_profile.to_string();
    let mut meta_profile_name = fallback_target_profile.to_string();

    if let Some(meta_raw) = entry_map.get("__backup_meta__.json") {
        if let Ok(meta) = serde_json::from_slice::<Value>(meta_raw) {
            is_encrypted = meta.get("encrypted").and_then(|v| v.as_bool()).unwrap_or(false);
            verification_token = meta
                .get("verification_enc")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            key_derivation = meta
                .get("key_derivation")
                .and_then(|v| v.as_str())
                .unwrap_or("legacy")
                .to_string();
            archive_type = meta
                .get("type")
                .and_then(|v| v.as_str())
                .unwrap_or("single_profile")
                .to_string();
            if let Some(ap) = meta.get("active_profile").and_then(|v| v.as_str()) {
                if !ap.is_empty() {
                    meta_active_profile = ap.to_string();
                }
            }
            if let Some(pn) = meta.get("profile_name").and_then(|v| v.as_str()) {
                if !pn.is_empty() {
                    meta_profile_name = pn.to_string();
                }
            }
            if let Some(hex_s) = meta.get("salt_hex").and_then(|v| v.as_str()) {
                if let Ok(b) = hex::decode(hex_s) {
                    salt_bytes = Some(b);
                }
            }
        }
    }

    let has_profiles_prefix = entry_map.keys().any(|k| k.starts_with("profiles/"));
    if has_profiles_prefix {
        archive_type = "full_workspace".to_string();
    }

    let clean_pwd = password.map(str::trim).filter(|s| !s.is_empty());
    let mut effective_encrypted = is_encrypted;
    let mut status = "success".to_string();
    let mut pwd_cipher: Option<crypto::CachedSeedCipher> = None;

    if is_encrypted {
        if let Some(pwd) = clean_pwd {
            let pwd_key = if key_derivation == "pbkdf2" {
                crypto::get_password_key(pwd, salt_bytes.as_deref(), crypto::PBKDF2_ITERATIONS_V2)
            } else {
                crypto::get_password_key_legacy(pwd)
            };
            let mut cipher = crypto::CachedSeedCipher::new(pwd_key, salt_bytes.as_deref());
            let verified = cipher.decrypt(&verification_token);
            if verified != "truehour_backup_verify" {
                return ImportBackupResult {
                    status: "wrong_password".into(),
                    backup_type: archive_type,
                    restored_profiles: vec![],
                    active_profile: meta_active_profile,
                    total_sessions: 0,
                    message: "Incorrect backup password.".into(),
                };
            }
            pwd_cipher = Some(cipher);
        } else if strip_if_encrypted {
            effective_encrypted = false;
            status = "banking_stripped".to_string();
        } else {
            return ImportBackupResult {
                status: "password_required".into(),
                backup_type: archive_type,
                restored_profiles: vec![],
                active_profile: meta_active_profile,
                total_sessions: 0,
                message: "This backup is password-encrypted.".into(),
            };
        }
    }

    if archive_type == "full_workspace" {
        let mut restored_profiles: Vec<String> = Vec::new();
        let mut total_sessions = 0usize;
        let mut logo_by_profile: HashMap<String, PathBuf> = HashMap::new();

        // Discover logo files first
        for rel in entry_map.keys() {
            if let Some(rest) = rel.strip_prefix("profiles/") {
                let mut parts = rest.splitn(2, '/');
                if let (Some(prof), Some(sub)) = (parts.next(), parts.next()) {
                    if sub.starts_with("logo/") && !sub.ends_with('/') {
                        let fname = Path::new(sub).file_name().unwrap_or_default();
                        logo_by_profile.insert(
                            prof.to_string(),
                            app_data_root
                                .join("profiles")
                                .join(prof)
                                .join("logo")
                                .join(fname),
                        );
                    }
                }
            }
        }

        for (rel, data) in &entry_map {
            let Some(rest) = rel.strip_prefix("profiles/") else {
                continue;
            };
            let mut parts = rest.splitn(2, '/');
            let (Some(prof), Some(in_prof)) = (parts.next(), parts.next()) else {
                continue;
            };
            if prof.is_empty() || should_skip_file(in_prof) {
                continue;
            }
            if !restored_profiles.iter().any(|p| p == prof) {
                restored_profiles.push(prof.to_string());
            }

            let dest_prof_dir = app_data_root.join("profiles").join(prof);
            let dst_file = dest_prof_dir.join(in_prof);
            if let Some(parent) = dst_file.parent() {
                let _ = fs::create_dir_all(parent);
            }

            if in_prof == "truehour.db" {
                let _ = fs::remove_file(dest_prof_dir.join("truehour.db-wal"));
                let _ = fs::remove_file(dest_prof_dir.join("truehour.db-shm"));
            }
            if in_prof.starts_with("sessions/") && in_prof.ends_with(".json") {
                total_sessions += 1;
            }

            let written_bytes = if in_prof == "app_settings.json" {
                let mut restored = restore_settings_from_backup(
                    data,
                    effective_encrypted,
                    pwd_cipher.as_mut(),
                    clean_pwd.is_some(),
                );
                if let Some(logo_path) = logo_by_profile.get(prof) {
                    if let Ok(mut v) = serde_json::from_slice::<Value>(&restored) {
                        if let Some(obj) = v.as_object_mut() {
                            obj.insert(
                                "business_logo_path".into(),
                                json!(logo_path.to_string_lossy()),
                            );
                            if let Ok(b) = serde_json::to_vec_pretty(&v) {
                                restored = b;
                            }
                        }
                    }
                }
                restored
            } else {
                data.clone()
            };

            let _ = fs::write(&dst_file, written_bytes);
        }

        let mut cfg = load_or_init_profiles(app_data_root).unwrap_or_else(|_| ProfilesConfig::default());
        for p in &restored_profiles {
            if !cfg.profiles.iter().any(|e| e == p) {
                cfg.profiles.push(p.clone());
            }
        }
        if !meta_active_profile.is_empty() && cfg.profiles.iter().any(|e| e == &meta_active_profile) {
            cfg.active_profile = meta_active_profile.clone();
        }
        let _ = save_profiles_config(app_data_root, &cfg);

        for prof in &restored_profiles {
            let p_paths = ProfilePaths::from_root_and_profile(app_data_root.to_path_buf(), prof.clone());
            let _ = db::init_database(&p_paths);
            let _ = db::rebuild_all_summaries(&p_paths, false);
        }

        return ImportBackupResult {
            status,
            backup_type: "full_workspace".into(),
            restored_profiles,
            active_profile: cfg.active_profile,
            total_sessions,
            message: "Workspace restored successfully.".into(),
        };
    }

    // Single profile archive (v1 / v2)
    let target_name = if meta_profile_name.trim().is_empty() {
        fallback_target_profile.to_string()
    } else {
        meta_profile_name
    };
    let dest_prof_dir = app_data_root.join("profiles").join(&target_name);
    let _ = fs::create_dir_all(&dest_prof_dir);
    let mut total_sessions = 0usize;
    let mut extracted_logo: Option<PathBuf> = None;

    for rel in entry_map.keys() {
        if rel.starts_with("logo/") && !rel.ends_with('/') {
            let fname = Path::new(rel).file_name().unwrap_or_default();
            extracted_logo = Some(dest_prof_dir.join("logo").join(fname));
            break;
        }
    }

    for (rel, data) in &entry_map {
        if rel == "__backup_meta__.json" || should_skip_file(rel) {
            continue;
        }
        let dst_file = dest_prof_dir.join(rel);
        if let Some(parent) = dst_file.parent() {
            let _ = fs::create_dir_all(parent);
        }
        if rel == "truehour.db" {
            let _ = fs::remove_file(dest_prof_dir.join("truehour.db-wal"));
            let _ = fs::remove_file(dest_prof_dir.join("truehour.db-shm"));
        }
        if rel.starts_with("sessions/") && rel.ends_with(".json") {
            total_sessions += 1;
        }
        let written_bytes = if rel == "app_settings.json" {
            let mut restored = restore_settings_from_backup(
                data,
                effective_encrypted,
                pwd_cipher.as_mut(),
                clean_pwd.is_some(),
            );
            if let Some(ref lp) = extracted_logo {
                if let Ok(mut v) = serde_json::from_slice::<Value>(&restored) {
                    if let Some(obj) = v.as_object_mut() {
                        obj.insert("business_logo_path".into(), json!(lp.to_string_lossy()));
                        if let Ok(b) = serde_json::to_vec_pretty(&v) {
                            restored = b;
                        }
                    }
                }
            }
            restored
        } else {
            data.clone()
        };
        let _ = fs::write(&dst_file, written_bytes);
    }

    let mut cfg = load_or_init_profiles(app_data_root).unwrap_or_else(|_| ProfilesConfig::default());
    if !cfg.profiles.iter().any(|p| p == &target_name) {
        cfg.profiles.push(target_name.clone());
    }
    let _ = save_profiles_config(app_data_root, &cfg);
    let p_paths = ProfilePaths::from_root_and_profile(app_data_root.to_path_buf(), target_name.clone());
    let _ = db::init_database(&p_paths);
    let _ = db::rebuild_all_summaries(&p_paths, false);

    ImportBackupResult {
        status,
        backup_type: "single_profile".into(),
        restored_profiles: vec![target_name],
        active_profile: cfg.active_profile,
        total_sessions,
        message: "Profile backup imported successfully.".into(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::settings::{load_full_settings, save_full_settings, FullSettingsDto};
    use tempfile::TempDir;

    fn sample_settings_with_bank() -> FullSettingsDto {
        FullSettingsDto {
            confirm_on_close: true,
            developer_mode: false,
            theme_style: "modern-dark".into(),
            dark_mode: true,
            min_track_seconds: 2,
            auto_save_seconds: 10,
            idle_threshold_seconds_total: 120,
            currency_symbol_raw: "$ (USD)".into(),
            currency_symbol: "$".into(),
            hourly_rate: 75.0,
            enable_distraction_auto_pause: true,
            distraction_apps: vec!["discord.exe".into()],
            weekly_goal_hours: 40.0,
            business_name: "Acme".into(),
            business_address: "1 Main".into(),
            business_emails: vec!["me@acme.com".into()],
            business_phone: "555-0100".into(),
            business_payment: "Net 14".into(),
            enable_bank_details: true,
            bank_holder: "Acme Owner".into(),
            bank_account: "123456789".into(),
            bank_routing: "021000021".into(),
            bank_swift: "CHASUS33".into(),
            bank_name: "Chase".into(),
            bank_address: "NY".into(),
            client_name: "Bob".into(),
            client_address: "2 Oak".into(),
            client_emails: vec!["bob@client.com".into()],
            enable_business_logo: true,
            business_logo_path: "".into(),
            qr_code_paths: vec![],
            qr_code_links: HashMap::new(),
            qr_code_items: vec![],
            mask_business_emails: false,
            mask_business_phone: false,
            mask_client_emails: false,
        }
    }

    #[test]
    fn test_encrypted_workspace_backup_and_restore_roundtrip() {
        let src_tmp = TempDir::new().unwrap();
        let src_root = src_tmp.path().join("TrueHourSrc");
        let paths = ProfilePaths::from_root_and_profile(src_root.clone(), "Default".into());
        paths.ensure_dirs().unwrap();
        db::init_database(&paths).unwrap();

        let dto = sample_settings_with_bank();
        save_full_settings(&paths, &dto).unwrap();
        fs::write(
            paths.sessions_dir.join("session_2026-11-10_09-00-00.json"),
            r#"{"date":"2026-11-10","start":"09:00:00","total_seconds":60,"counted_seconds":60,"apps":[]}"#,
        )
        .unwrap();
        // OAuth token files must never enter backups (strictly local-only)
        fs::write(paths.profile_dir.join("token.json"), r#"{"secret":"nope"}"#).unwrap();

        let archive = src_tmp.path().join("backup.truehour");
        backup_workspace(&src_root, &archive, Some("TopSecret!99")).unwrap();
        assert!(archive.exists());

        let dst_tmp = TempDir::new().unwrap();
        let dst_root = dst_tmp.path().join("TrueHourDst");
        fs::create_dir_all(&dst_root).unwrap();

        // 1. No password -> password_required
        let r_req = import_backup(&dst_root, &archive, None, false, "Default");
        assert_eq!(r_req.status, "password_required");

        // 2. Wrong password -> wrong_password
        let r_bad = import_backup(&dst_root, &archive, Some("WrongPwd"), false, "Default");
        assert_eq!(r_bad.status, "wrong_password");

        // 3. Correct password -> success + bank decrypted
        let r_ok = import_backup(&dst_root, &archive, Some("TopSecret!99"), false, "Default");
        assert_eq!(r_ok.status, "success");
        assert_eq!(r_ok.total_sessions, 1);

        let restored_paths = ProfilePaths::from_root_and_profile(dst_root.clone(), "Default".into());
        assert!(!restored_paths.profile_dir.join("token.json").exists());
        let loaded = load_full_settings(&restored_paths);
        assert_eq!(loaded.bank_account, "123456789");
        assert_eq!(loaded.bank_routing, "021000021");

        // 4. Strip banking when password omitted + strip_if_encrypted=true
        let dst_strip = dst_tmp.path().join("TrueHourStrip");
        fs::create_dir_all(&dst_strip).unwrap();
        let r_strip = import_backup(&dst_strip, &archive, None, true, "Default");
        assert_eq!(r_strip.status, "banking_stripped");
        let strip_paths = ProfilePaths::from_root_and_profile(dst_strip, "Default".into());
        let loaded_strip = load_full_settings(&strip_paths);
        assert_eq!(loaded_strip.bank_account, "");
        assert_eq!(loaded_strip.hourly_rate, 75.0);
    }

    #[test]
    fn test_zip_slip_traversal_rejected() {
        let tmp = TempDir::new().unwrap();
        let malicious = tmp.path().join("evil.truehour");
        write_zip_deflate(
            &malicious,
            &[ZipEntryInput {
                name: "../escaped.txt".into(),
                data: b"pwn".to_vec(),
            }],
        )
        .unwrap();

        let root = tmp.path().join("TrueHour");
        fs::create_dir_all(&root).unwrap();
        let res = import_backup(&root, &malicious, None, false, "Default");
        assert_eq!(res.status, "error");
        assert!(res.message.contains("Unsafe"));
        assert!(!tmp.path().join("escaped.txt").exists());
    }

    #[test]
    fn test_single_profile_backup_and_restore_roundtrip() {
        let src_tmp = TempDir::new().unwrap();
        let src_root = src_tmp.path().join("TrueHourSrc");
        let work_paths = ProfilePaths::from_root_and_profile(src_root.clone(), "Work".into());
        work_paths.ensure_dirs().unwrap();
        db::init_database(&work_paths).unwrap();
        let dto = sample_settings_with_bank();
        save_full_settings(&work_paths, &dto).unwrap();
        fs::write(
            work_paths.sessions_dir.join("session_2026-11-12_10-00-00.json"),
            r#"{"date":"2026-11-12","start":"10:00:00","total_seconds":120,"counted_seconds":120,"apps":[]}"#,
        )
        .unwrap();

        let archive = src_tmp.path().join("work_profile.truehour");
        backup_profile(&src_root, "Work", &archive, Some("WorkSecret#1")).unwrap();
        assert!(archive.exists());

        let dst_tmp = TempDir::new().unwrap();
        let dst_root = dst_tmp.path().join("TrueHourDst");
        fs::create_dir_all(&dst_root).unwrap();
        let res = import_backup(&dst_root, &archive, Some("WorkSecret#1"), false, "Default");
        assert_eq!(res.status, "success");
        assert_eq!(res.backup_type, "single_profile");
        assert_eq!(res.restored_profiles, vec!["Work".to_string()]);
        assert_eq!(res.total_sessions, 1);

        let restored_work = ProfilePaths::from_root_and_profile(dst_root, "Work".into());
        let loaded = load_full_settings(&restored_work);
        assert_eq!(loaded.bank_account, "123456789");
    }
}
