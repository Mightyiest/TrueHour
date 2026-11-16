use crate::appinfo::AppResolver;
use crate::config::atomic_write_str;
use crate::net::http_request;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

pub const DEFAULT_PROJECTS: &[&str] = &[
    "Development",
    "Design",
    "Research",
    "Documentation",
    "Communication",
    "Management",
    "Unassigned",
];

pub const PRIORITY_CATEGORIES: &[&str] = &[
    "Development",
    "Design",
    "Documentation",
    "Communication",
    "Research",
    "Management",
];

pub fn category_keywords() -> &'static [(&'static str, &'static [&'static str])] {
    &[
        (
            "Development",
            &[
                "code",
                "studio",
                "compiler",
                "ide",
                "git",
                "docker",
                "sublime",
                "debugger",
                "terminal",
                "powershell",
                "python",
                "node",
                "npm",
                "cargo",
                "msbuild",
                "visual studio",
                "pycharm",
                "intellij",
                "vscode",
            ],
        ),
        (
            "Design",
            &[
                "photoshop",
                "illustrator",
                "design",
                "draw",
                "cad",
                "paint",
                "premiere",
                "blend",
                "creative",
                "maya",
                "blender",
                "canvas",
                "figma",
                "sketch",
                "invision",
                "rendering",
                "image editor",
            ],
        ),
        (
            "Documentation",
            &[
                "word",
                "excel",
                "pdf",
                "document",
                "notion",
                "obsidian",
                "writer",
                "spreadsheet",
                "powerpoint",
                "slides",
                "notes",
                "acrobat",
                "typora",
                "logseq",
            ],
        ),
        (
            "Communication",
            &[
                "slack",
                "teams",
                "discord",
                "zoom",
                "outlook",
                "whatsapp",
                "messenger",
                "skype",
                "telegram",
                "thunderbird",
                "mail",
                "chat",
                "meeting",
            ],
        ),
        (
            "Research",
            &[
                "chrome",
                "firefox",
                "edge",
                "safari",
                "browser",
                "google",
                "search",
                "wikipedia",
                "navigator",
                "opera",
                "brave",
            ],
        ),
        (
            "Management",
            &[
                "project",
                "jira",
                "trello",
                "asana",
                "clickup",
                "monday.com",
                "board",
                "gantt",
                "backlog",
            ],
        ),
    ]
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct TagsFileSchema {
    #[serde(default)]
    projects: Vec<String>,
    #[serde(default)]
    mappings: HashMap<String, String>,
    #[serde(default)]
    display_names: HashMap<String, String>,
}

struct TagState {
    tags_file: PathBuf,
    projects: Vec<String>,
    mappings: HashMap<String, String>,
    display_names: HashMap<String, String>,
    dirty: bool,
    enable_online_lookup: bool,
}

pub struct TagManager {
    inner: Arc<Mutex<TagState>>,
    resolver: Arc<AppResolver>,
}

impl TagManager {
    pub fn new(tags_file: PathBuf, resolver: Arc<AppResolver>) -> Arc<Self> {
        let mut state = TagState {
            tags_file,
            projects: DEFAULT_PROJECTS.iter().map(|s| s.to_string()).collect(),
            mappings: HashMap::new(),
            display_names: HashMap::new(),
            dirty: false,
            enable_online_lookup: true,
        };
        Self::load_locked(&mut state);
        Arc::new(Self {
            inner: Arc::new(Mutex::new(state)),
            resolver,
        })
    }

    pub fn reload_from_file(&self, new_tags_file: PathBuf) {
        let mut state = self.inner.lock().unwrap();
        state.tags_file = new_tags_file;
        Self::load_locked(&mut state);
    }

    fn load_locked(state: &mut TagState) {
        state.projects = DEFAULT_PROJECTS.iter().map(|s| s.to_string()).collect();
        state.mappings.clear();
        state.display_names.clear();
        state.dirty = false;

        if !state.tags_file.exists() {
            Self::save_locked(state, true);
            return;
        }

        let raw = match fs::read_to_string(&state.tags_file) {
            Ok(s) => s,
            Err(_) => return,
        };
        let clean_raw = raw.trim_start_matches('\u{feff}');

        match serde_json::from_str::<TagsFileSchema>(clean_raw) {
            Ok(parsed) => {
                let mut projs: Vec<String> = parsed
                    .projects
                    .into_iter()
                    .filter(|p| !p.trim().is_empty())
                    .collect();
                for &def_proj in DEFAULT_PROJECTS {
                    if !projs.iter().any(|p| p == def_proj) {
                        projs.push(def_proj.to_string());
                    }
                }
                state.projects = projs;
                state.display_names.clear();
                for (orig_key, disp) in parsed.display_names {
                    let norm = orig_key.trim().to_lowercase();
                    if !norm.is_empty() && !disp.trim().is_empty() {
                        state.display_names.insert(norm, disp);
                    }
                }
                state.mappings.clear();
                for (orig_key, tag) in parsed.mappings {
                    let trimmed = orig_key.trim();
                    let norm = trimmed.to_lowercase();
                    if !norm.is_empty() {
                        state
                            .display_names
                            .entry(norm.clone())
                            .or_insert_with(|| trimmed.to_string());
                        state.mappings.insert(norm, tag);
                    }
                }
            }
            Err(_) => {
                let corrupt_bak = format!("{}.corrupt.bak", state.tags_file.to_string_lossy());
                let _ = fs::copy(&state.tags_file, corrupt_bak);
                state.projects = DEFAULT_PROJECTS.iter().map(|s| s.to_string()).collect();
                state.mappings.clear();
                state.display_names.clear();
            }
        }
    }

    fn save_locked(state: &mut TagState, force: bool) {
        if !force {
            state.dirty = true;
            return;
        }
        let payload = json!({
            "projects": state.projects,
            "mappings": state.mappings,
            "display_names": state.display_names,
        });
        if let Ok(json_str) = serde_json::to_string_pretty(&payload) {
            if state.tags_file.exists() {
                let bak = format!("{}.bak", state.tags_file.to_string_lossy());
                let _ = fs::copy(&state.tags_file, bak);
            }
            if atomic_write_str(&state.tags_file, &json_str).is_ok() {
                state.dirty = false;
            }
        }
    }

    pub fn save_if_dirty(&self) {
        let mut state = self.inner.lock().unwrap();
        if state.dirty {
            Self::save_locked(&mut state, true);
        }
    }

    pub fn projects(&self) -> Vec<String> {
        self.inner.lock().unwrap().projects.clone()
    }

    /// Reads tag without spawning background categorization when already mapped,
    /// matching `Tracker.get_app_tag` read behavior.
    pub fn get_mapped_tag(&self, app_name: &str) -> String {
        let key = app_name.trim().to_lowercase();
        let state = self.inner.lock().unwrap();
        state
            .mappings
            .get(&key)
            .cloned()
            .unwrap_or_else(|| "Unassigned".to_string())
    }

    pub fn get_tag(&self, app_name: &str, exe_path: &str) -> String {
        let clean = app_name.trim();
        if clean.is_empty() {
            return "Unassigned".to_string();
        }
        let key = clean.to_lowercase();
        let enable_online = {
            let mut state = self.inner.lock().unwrap();
            if let Some(existing) = state.mappings.get(&key) {
                return existing.clone();
            }
            state.mappings.insert(key.clone(), "Unassigned".to_string());
            state.display_names.insert(key.clone(), clean.to_string());
            state.dirty = true;
            state.enable_online_lookup
        };

        let inner = Arc::clone(&self.inner);
        let resolver = Arc::clone(&self.resolver);
        let app_owned = clean.to_string();
        let exe_owned = exe_path.to_string();

        std::thread::spawn(move || {
            if let Some(matched) = Self::match_offline(&resolver, &app_owned, &exe_owned) {
                let mut state = inner.lock().unwrap();
                state.mappings.insert(key.clone(), matched);
                state.display_names.insert(key, app_owned);
                state.dirty = true;
                Self::save_locked(&mut state, true);
                return;
            }
            if enable_online {
                if let Some(matched) = Self::fetch_online_tag(&resolver, &app_owned, &exe_owned) {
                    let mut state = inner.lock().unwrap();
                    state.mappings.insert(key.clone(), matched);
                    state.display_names.insert(key, app_owned);
                    Self::save_locked(&mut state, true);
                }
            }
        });

        "Unassigned".to_string()
    }

    pub fn set_tag(&self, app_name: &str, tag: &str) -> bool {
        let clean_name = app_name.trim();
        let clean_tag = tag.trim();
        if clean_name.is_empty() || clean_tag.is_empty() {
            return false;
        }
        let key = clean_name.to_lowercase();
        let mut state = self.inner.lock().unwrap();
        if !state.projects.iter().any(|p| p == clean_tag) && clean_tag != "Unassigned" {
            return false;
        }
        state.mappings.insert(key.clone(), clean_tag.to_string());
        state.display_names.insert(key, clean_name.to_string());
        Self::save_locked(&mut state, true);
        true
    }

    pub fn add_project(&self, project: &str) -> bool {
        let trimmed = project.trim();
        if trimmed.is_empty() {
            return false;
        }
        let mut state = self.inner.lock().unwrap();
        if state.projects.iter().any(|p| p.eq_ignore_ascii_case(trimmed)) {
            return false;
        }
        state.projects.push(trimmed.to_string());
        Self::save_locked(&mut state, true);
        true
    }

    pub fn remove_app_tag(&self, app_name: &str) -> bool {
        let clean_name = app_name.trim();
        let key = clean_name.to_lowercase();
        let mut state = self.inner.lock().unwrap();
        if state.mappings.contains_key(&key) {
            state.mappings.insert(key.clone(), "Unassigned".to_string());
            state.display_names.insert(key, clean_name.to_string());
            Self::save_locked(&mut state, true);
            return true;
        }
        false
    }

    pub fn delete_project(&self, project: &str) -> Result<Vec<String>, String> {
        let trimmed = project.trim();
        if DEFAULT_PROJECTS.iter().any(|&p| p.eq_ignore_ascii_case(trimmed)) {
            return Err("Built-in project categories cannot be deleted.".to_string());
        }
        let mut state = self.inner.lock().unwrap();
        let before = state.projects.len();
        state.projects.retain(|p| !p.eq_ignore_ascii_case(trimmed));
        if state.projects.len() == before {
            return Err(format!("Category '{trimmed}' was not found."));
        }
        for val in state.mappings.values_mut() {
            if val.eq_ignore_ascii_case(trimmed) {
                *val = "Unassigned".to_string();
            }
        }
        Self::save_locked(&mut state, true);
        Ok(state.projects.clone())
    }

    pub fn get_all_mappings_snapshot(&self) -> (Vec<String>, Vec<(String, String)>) {
        let state = self.inner.lock().unwrap();
        let mut entries: Vec<(String, String)> = state
            .mappings
            .iter()
            .map(|(k, tag)| {
                let display = state
                    .display_names
                    .get(k)
                    .cloned()
                    .unwrap_or_else(|| k.clone());
                (display, tag.clone())
            })
            .collect();
        entries.sort_by(|a, b| a.0.to_lowercase().cmp(&b.0.to_lowercase()));
        (state.projects.clone(), entries)
    }

    pub fn match_offline(resolver: &AppResolver, app_name: &str, exe_path: &str) -> Option<String> {
        let app_lower = app_name.trim().to_lowercase();
        let mut exe_name = String::new();
        let mut desc_lower = String::new();
        let mut company_lower = String::new();
        let mut product_lower = String::new();

        if !exe_path.is_empty() {
            let fname = Path::new(exe_path)
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("")
                .to_lowercase();
            exe_name = fname.strip_suffix(".exe").unwrap_or(&fname).to_string();

            let ver = resolver.get_version_info(exe_path);
            if let Some(d) = ver.file_description {
                desc_lower = d.trim().to_lowercase();
            }
            if let Some(c) = ver.company_name {
                company_lower = c.trim().to_lowercase();
            }
            if let Some(p) = ver.product_name {
                product_lower = p.trim().to_lowercase();
            }
        }

        let mut scores: HashMap<&str, f64> = PRIORITY_CATEGORIES
            .iter()
            .map(|&cat| (cat, 0.0))
            .collect();

        // 1. High-priority company / brand mappings
        if company_lower.contains("adobe")
            || product_lower.contains("adobe")
            || app_lower.contains("photoshop")
            || app_lower.contains("illustrator")
        {
            *scores.get_mut("Design").unwrap() += 5.0;
        }
        if company_lower.contains("jetbrains")
            || product_lower.contains("intellij")
            || product_lower.contains("pycharm")
            || product_lower.contains("webstorm")
        {
            *scores.get_mut("Development").unwrap() += 5.0;
        }
        if company_lower.contains("autodesk") || product_lower.contains("autocad") {
            *scores.get_mut("Design").unwrap() += 5.0;
        }
        if app_lower.contains("slack") || exe_name.contains("slack") {
            *scores.get_mut("Communication").unwrap() += 5.0;
        }
        if app_lower.contains("discord") || exe_name.contains("discord") {
            *scores.get_mut("Communication").unwrap() += 5.0;
        }
        if app_lower.contains("zoom") || exe_name.contains("zoom") {
            *scores.get_mut("Communication").unwrap() += 5.0;
        }
        if app_lower.contains("figma") || exe_name.contains("figma") {
            *scores.get_mut("Design").unwrap() += 5.0;
        }
        if company_lower.contains("github")
            || product_lower.contains("github")
            || exe_name.contains("git")
        {
            *scores.get_mut("Development").unwrap() += 5.0;
        }

        // 2. Tokenize all strings
        let mut all_tokens: HashSet<String> = HashSet::new();
        for text in [&app_lower, &exe_name, &desc_lower, &product_lower, &company_lower] {
            if text.is_empty() {
                continue;
            }
            let cleaned: String = text
                .chars()
                .map(|c| if c.is_alphanumeric() { c } else { ' ' })
                .collect();
            for tok in cleaned.split_whitespace() {
                all_tokens.insert(tok.to_string());
            }
        }

        // 3. Score keywords (exact token +3.0, else substring inside longer token +1.0)
        for &(category, words) in category_keywords() {
            for &word in words {
                if all_tokens.contains(word) {
                    *scores.get_mut(category).unwrap() += 3.0;
                } else if all_tokens
                    .iter()
                    .any(|tok| tok.len() > word.len() && tok.contains(word))
                {
                    *scores.get_mut(category).unwrap() += 1.0;
                }
            }
        }

        // 4. Priority-ordered max score selection
        let mut max_score = 0.0;
        let mut best_cat: Option<&str> = None;
        for &cat in PRIORITY_CATEGORIES {
            let s = *scores.get(cat).unwrap_or(&0.0);
            if s > max_score {
                max_score = s;
                best_cat = Some(cat);
            }
        }

        best_cat.map(|c| c.to_string())
    }

    fn fetch_online_tag(resolver: &AppResolver, app_name: &str, exe_path: &str) -> Option<String> {
        if app_name.is_empty() || app_name.starts_with('[') {
            return None;
        }
        let mut query = app_name.to_string();
        if !exe_path.is_empty() {
            if let Some(desc) = resolver.get_version_info(exe_path).file_description {
                if desc.len() > 3 {
                    query = desc;
                }
            }
        }
        let encoded_q = url_encode_component(&query);
        let url = format!(
            "https://api.duckduckgo.com/?q={encoded_q}&format=json&no_html=1&skip_disambig=1"
        );
        let resp = http_request("GET", &url, 3000).ok()?;
        if resp.status != 200 {
            return None;
        }
        let val: Value = serde_json::from_str(&resp.body).ok()?;
        let abstract_text = val
            .get("AbstractText")
            .and_then(|v| v.as_str())
            .filter(|s| !s.is_empty())
            .or_else(|| val.get("Abstract").and_then(|v| v.as_str()))?;
        if abstract_text.is_empty() {
            return None;
        }

        let words_in_abstract: HashSet<String> = abstract_text
            .to_lowercase()
            .split(|c: char| !c.is_alphanumeric())
            .filter(|w| !w.is_empty())
            .map(|w| w.to_string())
            .collect();

        for &(cat, kws) in category_keywords() {
            for &kw in kws {
                if kw.contains(' ') {
                    if abstract_text.to_lowercase().contains(kw) {
                        return Some(cat.to_string());
                    }
                } else if words_in_abstract.contains(kw) {
                    return Some(cat.to_string());
                }
            }
        }
        None
    }

    #[cfg(test)]
    pub fn disable_online_lookup_for_test(&self) {
        self.inner.lock().unwrap().enable_online_lookup = false;
    }
}

fn url_encode_component(input: &str) -> String {
    let mut out = String::new();
    for b in input.as_bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(*b as char)
            }
            b' ' => out.push_str("%20"),
            _ => out.push_str(&format!("%{:02X}", b)),
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_offline_heuristics_and_tags_persistence() {
        let tmp = TempDir::new().unwrap();
        let tags_path = tmp.path().join("tags.json");
        let overrides = tmp.path().join("name_overrides.txt");
        let resolver = AppResolver::new(overrides);
        let mgr = TagManager::new(tags_path.clone(), Arc::clone(&resolver));
        mgr.disable_online_lookup_for_test();

        assert_eq!(
            TagManager::match_offline(&resolver, "Visual Studio Code", r"C:\Apps\Code.exe"),
            Some("Development".to_string())
        );
        assert_eq!(
            TagManager::match_offline(&resolver, "Figma", r"C:\Apps\Figma.exe"),
            Some("Design".to_string())
        );
        assert_eq!(
            TagManager::match_offline(&resolver, "Google Chrome", r"C:\Apps\chrome.exe"),
            Some("Research".to_string())
        );
        assert_eq!(
            TagManager::match_offline(&resolver, "Discord", r"C:\Apps\discord.exe"),
            Some("Communication".to_string())
        );

        assert!(mgr.add_project("Client Alpha"));
        assert!(mgr.set_tag("CustomTool", "Client Alpha"));
        assert_eq!(mgr.get_mapped_tag("CustomTool"), "Client Alpha");

        // Reload from disk and verify persistence
        let mgr2 = TagManager::new(tags_path, resolver);
        assert_eq!(mgr2.get_mapped_tag("customtool"), "Client Alpha");
        assert!(mgr2.projects().contains(&"Client Alpha".to_string()));

        // Snapshot returns projects and sorted display mappings
        let (projs, mappings) = mgr2.get_all_mappings_snapshot();
        assert!(projs.contains(&"Client Alpha".to_string()));
        assert!(mappings
            .iter()
            .any(|(app, tag)| app == "CustomTool" && tag == "Client Alpha"));

        // Built-in & missing categories cannot be deleted
        assert!(mgr2.delete_project("Development").is_err());
        assert!(mgr2.delete_project("DoesNotExist").is_err());

        // Deleting Client Alpha reassigns CustomTool to Unassigned
        let after = mgr2.delete_project("Client Alpha").unwrap();
        assert!(!after.contains(&"Client Alpha".to_string()));
        assert_eq!(mgr2.get_mapped_tag("CustomTool"), "Unassigned");
    }
}
