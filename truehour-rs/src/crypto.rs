use base64::engine::general_purpose::URL_SAFE;
use base64::Engine;
use fernet::Fernet;
use hmac::{Hmac, Mac};
use sha2::{Digest, Sha256};

pub const DEFAULT_SALT: &[u8] = b"TrueHour_Fixed_Salt_1337";
pub const DEFAULT_PASSWORD_SALT: &[u8] = b"TrueHour_Password_Salt_Fixed";
pub const PBKDF2_ITERATIONS_V2: u32 = 600_000;
pub const PBKDF2_ITERATIONS_LEGACY: u32 = 100_000;
pub const BANK_FIELDS: &[&str] = &[
    "bank_holder",
    "bank_account",
    "bank_routing",
    "bank_swift",
    "bank_name",
    "bank_address",
];

type HmacSha256 = Hmac<Sha256>;

pub fn get_machine_id() -> String {
    std::env::var("COMPUTERNAME")
        .ok()
        .filter(|s| !s.is_empty())
        .or_else(|| std::env::var("HOSTNAME").ok().filter(|s| !s.is_empty()))
        .unwrap_or_else(|| "default_host".to_string())
}

/// Mirrors `crypto._get_secure_key(seed)` from Python v4.2.
pub fn get_secure_key(seed: &str) -> String {
    if seed.is_empty() {
        return "default_key_seed".to_string();
    }
    let machine_id = get_machine_id();
    let combined = format!("{seed}:{machine_id}");
    let mut hasher = Sha256::new();
    hasher.update(combined.as_bytes());
    hex::encode(hasher.finalize())
}

/// Mirrors `crypto._get_portable_key(seed)` from Python v4.2.
pub fn get_portable_key(seed: &str) -> String {
    if seed.is_empty() {
        return "default_portable_seed".to_string();
    }
    let combined = format!("TrueHourPortable:{seed}");
    let mut hasher = Sha256::new();
    hasher.update(combined.as_bytes());
    hex::encode(hasher.finalize())
}

/// RFC 2898 PBKDF2-HMAC-SHA256 generating a 32-byte key (single block, exact match to Python hashlib.pbkdf2_hmac).
pub fn pbkdf2_hmac_sha256_32(password: &[u8], salt: &[u8], iterations: u32) -> [u8; 32] {
    let mut u = [0u8; 32];
    let mut t = [0u8; 32];

    let base_mac = HmacSha256::new_from_slice(password).expect("HMAC accepts any key size");
    let mut mac = base_mac.clone();
    mac.update(salt);
    mac.update(&1u32.to_be_bytes());
    let first = mac.finalize().into_bytes();
    u.copy_from_slice(&first);
    t.copy_from_slice(&first);

    for _ in 1..iterations {
        let mut mac = base_mac.clone();
        mac.update(&u);
        let next = mac.finalize().into_bytes();
        u.copy_from_slice(&next);
        for (tb, ub) in t.iter_mut().zip(u.iter()) {
            *tb ^= *ub;
        }
    }

    t
}

/// Mirrors `crypto._get_password_key(password, salt, iterations)` from Python v4.2.
pub fn get_password_key(password: &str, salt: Option<&[u8]>, iterations: u32) -> String {
    if password.is_empty() {
        return "default_password_seed".to_string();
    }
    let effective_salt = salt.unwrap_or(DEFAULT_PASSWORD_SALT);
    let dk = pbkdf2_hmac_sha256_32(password.as_bytes(), effective_salt, iterations);
    hex::encode(dk)
}

/// Mirrors `crypto._get_password_key_legacy(password)` from Python v4.2.
pub fn get_password_key_legacy(password: &str) -> String {
    if password.is_empty() {
        return "default_password_seed".to_string();
    }
    let mut hasher = Sha256::new();
    hasher.update(password.as_bytes());
    hex::encode(hasher.finalize())
}

/// Mirrors `crypto._derive_fernet_key(key_seed, salt, iterations)`.
pub fn derive_fernet_key(key_seed: &str, salt: Option<&[u8]>, iterations: u32) -> String {
    let salt_bytes = salt.unwrap_or(DEFAULT_SALT);
    let dk = pbkdf2_hmac_sha256_32(key_seed.as_bytes(), salt_bytes, iterations);
    URL_SAFE.encode(dk)
}

/// Mirrors `crypto._encrypt_string(text, key_seed, salt)` returning `"v2:<fernet_token>"`.
pub fn encrypt_string_with_salt(text: &str, key_seed: &str, salt: Option<&[u8]>) -> String {
    if text.is_empty() {
        return String::new();
    }
    let key = derive_fernet_key(key_seed, salt, PBKDF2_ITERATIONS_V2);
    let Some(fernet) = Fernet::new(&key) else {
        return String::new();
    };
    let token = fernet.encrypt(text.as_bytes());
    format!("v2:{token}")
}

/// Mirrors `crypto._encrypt_string(text, key_seed)` returning `"v2:<fernet_token>"`.
pub fn encrypt_string(text: &str, key_seed: &str) -> String {
    encrypt_string_with_salt(text, key_seed, None)
}

/// Mirrors `crypto._decrypt_string(encrypted_text, key_seed, salt)` with 600k -> 100k fallback.
pub fn decrypt_string_with_salt(
    encrypted_text: &str,
    key_seed: &str,
    salt: Option<&[u8]>,
) -> String {
    if encrypted_text.is_empty() {
        return String::new();
    }
    let clean = encrypted_text
        .strip_prefix("v2:")
        .unwrap_or(encrypted_text);

    for iters in [PBKDF2_ITERATIONS_V2, PBKDF2_ITERATIONS_LEGACY] {
        let key = derive_fernet_key(key_seed, salt, iters);
        if let Some(fernet) = Fernet::new(&key) {
            if let Ok(plain) = fernet.decrypt(clean) {
                if let Ok(s) = String::from_utf8(plain) {
                    return s;
                }
            }
        }
    }

    String::new()
}

/// Mirrors `crypto._decrypt_string(encrypted_text, key_seed)` with 600k -> 100k fallback.
pub fn decrypt_string(encrypted_text: &str, key_seed: &str) -> String {
    decrypt_string_with_salt(encrypted_text, key_seed, None)
}

/// Reusable lazy Fernet codec for batching multiple fields under the same key seed & salt.
pub struct CachedSeedCipher {
    key_seed: String,
    salt: Option<Vec<u8>>,
    v2: Option<Fernet>,
    legacy: Option<Fernet>,
}

impl CachedSeedCipher {
    pub fn new(key_seed: String, salt: Option<&[u8]>) -> Self {
        Self {
            key_seed,
            salt: salt.map(|s| s.to_vec()),
            v2: None,
            legacy: None,
        }
    }

    fn ensure_v2(&mut self) -> Option<&Fernet> {
        if self.v2.is_none() {
            let key = derive_fernet_key(&self.key_seed, self.salt.as_deref(), PBKDF2_ITERATIONS_V2);
            self.v2 = Fernet::new(&key);
        }
        self.v2.as_ref()
    }

    fn ensure_legacy(&mut self) -> Option<&Fernet> {
        if self.legacy.is_none() {
            let key =
                derive_fernet_key(&self.key_seed, self.salt.as_deref(), PBKDF2_ITERATIONS_LEGACY);
            self.legacy = Fernet::new(&key);
        }
        self.legacy.as_ref()
    }

    pub fn encrypt(&mut self, text: &str) -> String {
        if text.is_empty() {
            return String::new();
        }
        let Some(fernet) = self.ensure_v2() else {
            return String::new();
        };
        format!("v2:{}", fernet.encrypt(text.as_bytes()))
    }

    pub fn decrypt(&mut self, encrypted_text: &str) -> String {
        if encrypted_text.is_empty() {
            return String::new();
        }
        let clean = encrypted_text.strip_prefix("v2:").unwrap_or(encrypted_text);
        if let Some(fernet) = self.ensure_v2() {
            if let Ok(plain) = fernet.decrypt(clean) {
                if let Ok(s) = String::from_utf8(plain) {
                    return s;
                }
            }
        }
        if let Some(fernet) = self.ensure_legacy() {
            if let Ok(plain) = fernet.decrypt(clean) {
                if let Ok(s) = String::from_utf8(plain) {
                    return s;
                }
            }
        }
        String::new()
    }
}

pub fn encrypt_bank_field(plain_text: &str, anonymous_user_id: &str) -> String {
    if plain_text.is_empty() {
        return String::new();
    }
    let key_seed = get_secure_key(anonymous_user_id);
    encrypt_string(plain_text, &key_seed)
}

/// Helper for decrypting profile bank settings where `key_seed` comes from `get_secure_key(anonymous_user_id)`
/// (with fallback to empty/default seed or portable key).
pub fn decrypt_bank_field(encrypted_text: &str, anonymous_user_id: &str) -> String {
    if encrypted_text.is_empty() {
        return String::new();
    }
    let candidates = [
        get_secure_key(anonymous_user_id),
        get_secure_key(""),
        get_portable_key(anonymous_user_id),
    ];
    for key_seed in &candidates {
        let decoded = decrypt_string(encrypted_text, key_seed);
        if !decoded.is_empty() {
            return decoded;
        }
    }
    String::new()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pbkdf2_known_vector() {
        // RFC 7914 / Test vector: password="password", salt="salt", c=1 -> 32 bytes SHA256
        // Verified: hashlib.pbkdf2_hmac('sha256', b'password', b'salt', 1, 32).hex()
        // == 120fb6cffcf8b32c43e7225256c4f837a86548c92ccc35480805987cb70be17b
        let out = pbkdf2_hmac_sha256_32(b"password", b"salt", 1);
        assert_eq!(
            hex::encode(out),
            "120fb6cffcf8b32c43e7225256c4f837a86548c92ccc35480805987cb70be17b"
        );

        // c=4096: hashlib.pbkdf2_hmac('sha256', b'password', b'salt', 4096, 32).hex()
        // == c5e478d59288c841aa530db6845c4c8d962893a001ce4e11a4963873aa98134a
        let out_4096 = pbkdf2_hmac_sha256_32(b"password", b"salt", 4096);
        assert_eq!(
            hex::encode(out_4096),
            "c5e478d59288c841aa530db6845c4c8d962893a001ce4e11a4963873aa98134a"
        );
    }

    #[test]
    fn test_encrypt_decrypt_roundtrip_and_legacy_fallback() {
        let seed = get_secure_key("test-user-seed-123");
        let encrypted = encrypt_string("IBAN-SECRET-9988", &seed);
        assert!(encrypted.starts_with("v2:"));
        assert_eq!(decrypt_string(&encrypted, &seed), "IBAN-SECRET-9988");
        assert_eq!(decrypt_string(&encrypted, &get_secure_key("wrong-seed")), "");

        // Legacy 100k token without "v2:" prefix
        let legacy_key = derive_fernet_key(&seed, None, PBKDF2_ITERATIONS_LEGACY);
        let f = Fernet::new(&legacy_key).unwrap();
        let legacy_token = f.encrypt(b"LegacyBankInfo");
        assert_eq!(decrypt_string(&legacy_token, &seed), "LegacyBankInfo");

        // Empty roundtrip
        assert_eq!(encrypt_string("", &seed), "");
        assert_eq!(decrypt_string("", &seed), "");
    }
}
