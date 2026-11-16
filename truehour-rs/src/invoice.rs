use crate::config::ProfilePaths;
use crate::report::{
    format_currency, format_duration, html_escape, project_color, ProjectBreakdownEntry,
};
use crate::settings::{image_file_to_data_uri, FullSettingsDto};
use crate::tags::TagManager;
use chrono::Local;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::PathBuf;

const INVOICE_HTML_TEMPLATE: &str = include_str!("../../templates/invoice.html");
const RECEIPT_HTML_TEMPLATE: &str = include_str!("../../templates/receipt.html");

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ManualLineItem {
    pub description: String,
    pub amount: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InvoicePrivacyOverrides {
    pub mask_business_emails: bool,
    pub mask_business_phone: bool,
    pub mask_client_emails: bool,
    #[serde(default)]
    pub invoice_no: Option<String>,
    #[serde(default)]
    pub additional_items: Vec<ManualLineItem>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BillingData {
    pub total_seconds: i64,
    pub total_formatted: String,
    pub counted_seconds: i64,
    pub counted_formatted: String,
    pub total_earned: f64,
    pub total_earned_display: String,
    pub project_breakdown: Vec<ProjectBreakdownEntry>,
    pub session_count: usize,
    #[serde(default)]
    pub additional_items: Vec<ManualLineItem>,
}

pub fn mask_email(email: &str) -> String {
    if email.is_empty() || !email.contains('@') {
        return email.to_string();
    }
    let Some((local, domain)) = email.split_once('@') else {
        return email.to_string();
    };
    let masked_local = if local.chars().count() <= 2 {
        format!("{local}**")
    } else {
        let prefix: String = local.chars().take(2).collect();
        format!("{prefix}**")
    };
    let masked_domain = if let Some((_, tld)) = domain.rsplit_once('.') {
        format!("*****.{tld}")
    } else {
        "*****".to_string()
    };
    format!("{masked_local}@{masked_domain}")
}

pub fn mask_phone(phone: &str) -> String {
    if phone.is_empty() {
        return String::new();
    }
    let mut masked_rev: Vec<char> = Vec::with_capacity(phone.len());
    let mut mask_count = 0usize;
    for ch in phone.chars().rev() {
        if ch.is_ascii_digit() && mask_count < 7 {
            masked_rev.push('*');
            mask_count += 1;
        } else {
            masked_rev.push(ch);
        }
    }
    masked_rev.into_iter().rev().collect()
}

pub fn merge_sessions_for_invoice(
    tag_manager: &TagManager,
    filepaths: &[PathBuf],
    hourly_rate: f64,
    currency_symbol: &str,
) -> Result<BillingData, String> {
    if filepaths.is_empty() {
        return Err("Select at least one session to generate an invoice.".to_string());
    }

    let mut seen_keys: HashSet<(String, String, String)> = HashSet::new();
    let mut sessions: Vec<Value> = Vec::new();

    for path in filepaths {
        let Ok(raw) = fs::read_to_string(path) else {
            continue;
        };
        let Ok(data) = serde_json::from_str::<Value>(raw.trim_start_matches('\u{feff}')) else {
            continue;
        };
        let d = data.get("date").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let s = data.get("start").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let key = (d, s, path.to_string_lossy().to_string());
        if seen_keys.insert(key) {
            sessions.push(data);
        }
    }

    if sessions.is_empty() {
        return Err("No valid session files found for invoicing.".to_string());
    }

    let mut total_seconds = 0i64;
    let mut counted_seconds = 0i64;
    let mut project_times: HashMap<String, i64> = HashMap::new();

    for session in &sessions {
        total_seconds += session
            .get("total_seconds")
            .and_then(|v| v.as_i64())
            .unwrap_or(0);
        if let Some(apps) = session.get("apps").and_then(|v| v.as_array()) {
            for app in apps {
                let name = app.get("name").and_then(|v| v.as_str()).unwrap_or("");
                let secs = app.get("seconds").and_then(|v| v.as_i64()).unwrap_or(0);
                let excluded = app.get("excluded").and_then(|v| v.as_bool()).unwrap_or(false);
                let active_tag = tag_manager.get_mapped_tag(name);
                let tag = if !active_tag.is_empty() && active_tag != "Unassigned" {
                    active_tag
                } else {
                    app.get("tag")
                        .and_then(|v| v.as_str())
                        .unwrap_or("Unassigned")
                        .to_string()
                };
                if !excluded {
                    counted_seconds += secs;
                    *project_times.entry(tag).or_insert(0) += secs;
                }
            }
        }
    }

    let total_proj: i64 = project_times.values().sum();
    let mut breakdown: Vec<ProjectBreakdownEntry> = project_times
        .into_iter()
        .map(|(proj, secs)| {
            let pct = if total_proj > 0 {
                ((secs as f64 / total_proj as f64) * 1000.0).round() / 10.0
            } else {
                0.0
            };
            let earned = (((secs as f64 / 3600.0) * hourly_rate) * 100.0).round() / 100.0;
            ProjectBreakdownEntry {
                color: project_color(&proj).to_string(),
                project: proj,
                seconds: secs,
                formatted: format_duration(secs),
                percent: pct,
                earned,
                earned_display: format_currency(currency_symbol, earned),
            }
        })
        .collect();
    breakdown.sort_by(|a, b| b.seconds.cmp(&a.seconds));

    let total_earned = if hourly_rate > 0.0 {
        (breakdown.iter().map(|b| b.earned).sum::<f64>() * 100.0).round() / 100.0
    } else {
        0.0
    };

    Ok(BillingData {
        total_seconds,
        total_formatted: format_duration(total_seconds),
        counted_seconds,
        counted_formatted: format_duration(counted_seconds),
        total_earned,
        total_earned_display: format_currency(currency_symbol, total_earned),
        project_breakdown: breakdown,
        session_count: sessions.len(),
        additional_items: Vec::new(),
    })
}

fn default_logo_svg(class_name: &str) -> String {
    format!(
        r#"<svg class="{class_name}" width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" style="margin-bottom: 12px; display: block;">
      <rect width="40" height="40" rx="10" fill="url(#logo-grad)"/>
      <path d="M20 11V29" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M13 18L20 11L27 18" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M10 29H30" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
      <defs>
        <linearGradient id="logo-grad" x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
          <stop stop-color="var(--accent-gradient-start, #6366F1)"/>
          <stop offset="1" stop-color="var(--accent-gradient-end, #4F46E5)"/>
        </linearGradient>
      </defs>
    </svg>"#
    )
}

fn build_contact_parts(settings: &FullSettingsDto) -> (String, String) {
    let biz_emails: Vec<String> = settings
        .business_emails
        .iter()
        .map(|e| {
            if settings.mask_business_emails {
                html_escape(&mask_email(e))
            } else {
                html_escape(e)
            }
        })
        .collect();
    let biz_email_str = biz_emails.join(", ");

    let biz_phone = if settings.business_phone.trim().is_empty() {
        String::new()
    } else if settings.mask_business_phone {
        html_escape(&mask_phone(settings.business_phone.trim()))
    } else {
        html_escape(settings.business_phone.trim())
    };

    let mut contact_parts = Vec::new();
    if !biz_email_str.is_empty() {
        contact_parts.push(biz_email_str);
    }
    if !biz_phone.is_empty() {
        contact_parts.push(biz_phone);
    }
    let biz_contact_html = contact_parts.join(" &nbsp;&bull;&nbsp; ");

    let client_emails: Vec<String> = settings
        .client_emails
        .iter()
        .map(|e| {
            if settings.mask_client_emails {
                html_escape(&mask_email(e))
            } else {
                html_escape(e)
            }
        })
        .collect();

    (biz_contact_html, client_emails.join(", "))
}

pub fn generate_receipt_html(
    billing_data: &BillingData,
    settings: &FullSettingsDto,
    invoice_no: Option<&str>,
    additional_items: &[ManualLineItem],
) -> String {
    let logo_html = if settings.enable_business_logo {
        let lp = settings.business_logo_path.trim();
        if !lp.is_empty() {
            if let Some(uri) = image_file_to_data_uri(&PathBuf::from(lp)) {
                format!(r#"<img src="{uri}" class="receipt-logo" />"#)
            } else {
                default_logo_svg("receipt-logo")
            }
        } else {
            default_logo_svg("receipt-logo")
        }
    } else {
        String::new()
    };

    let hours_counted = billing_data.counted_seconds as f64 / 3600.0;
    let hourly_rate = settings.hourly_rate;
    let curr_sym = if settings.currency_symbol.is_empty() {
        "$"
    } else {
        settings.currency_symbol.as_str()
    };

    let (biz_contact_html, client_emails_joined) = build_contact_parts(settings);
    let client_emails_html = if client_emails_joined.is_empty() {
        String::new()
    } else {
        format!(r#"<div class="party-address">{client_emails_joined}</div>"#)
    };

    let effective_items = if additional_items.is_empty() {
        &billing_data.additional_items
    } else {
        additional_items
    };
    let add_total: f64 = effective_items.iter().map(|it| it.amount).sum();
    let total_paid = billing_data.total_earned + add_total;
    let total_paid_display = format_currency(curr_sym, total_paid);

    let final_receipt_no = invoice_no
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_string)
        .unwrap_or_else(|| format!("REC-{}", Local::now().format("%Y%m%d%H%M")));

    let biz_name = if settings.business_name.trim().is_empty() {
        "TrueHour Business"
    } else {
        settings.business_name.trim()
    };
    let client_name = if settings.client_name.trim().is_empty() {
        "Valued Client"
    } else {
        settings.client_name.trim()
    };

    let mut html = RECEIPT_HTML_TEMPLATE.to_string();
    if settings.dark_mode {
        html = html.replace(
            "<body>",
            &format!(r#"<body class="dark {}">"#, settings.theme_style),
        );
    }

    html.replace("{{LOGO_HTML}}", &logo_html)
        .replace("{{BUSINESS_NAME}}", &html_escape(biz_name))
        .replace("{{BUSINESS_ADDRESS}}", &html_escape(&settings.business_address))
        .replace("{{BUSINESS_CONTACT}}", &biz_contact_html)
        .replace("{{RECEIPT_NO}}", &html_escape(&final_receipt_no))
        .replace("{{DATE}}", &Local::now().format("%B %d, %Y").to_string())
        .replace("{{CLIENT_NAME}}", &html_escape(client_name))
        .replace("{{CLIENT_ADDRESS}}", &html_escape(&settings.client_address))
        .replace("{{CLIENT_EMAILS_HTML}}", &client_emails_html)
        .replace("{{HOURS_COUNTED}}", &format!("{hours_counted:.2}"))
        .replace("{{HOURLY_RATE}}", &format!("{curr_sym}{hourly_rate:.2}/hr"))
        .replace("{{TOTAL_AMOUNT_PAID}}", &html_escape(&total_paid_display))
}

pub fn generate_invoice_html(
    paths: &ProfilePaths,
    billing_data: &BillingData,
    settings: &FullSettingsDto,
    status: &str,
    invoice_no: Option<&str>,
    additional_items: &[ManualLineItem],
) -> String {
    if status.eq_ignore_ascii_case("paid") {
        return generate_receipt_html(billing_data, settings, invoice_no, additional_items);
    }

    let logo_html = if settings.enable_business_logo {
        let lp = settings.business_logo_path.trim();
        if !lp.is_empty() {
            if let Some(uri) = image_file_to_data_uri(&PathBuf::from(lp)) {
                format!(r#"<img src="{uri}" class="invoice-logo" />"#)
            } else {
                default_logo_svg("invoice-logo")
            }
        } else {
            default_logo_svg("invoice-logo")
        }
    } else {
        String::new()
    };

    let hours_counted = billing_data.counted_seconds as f64 / 3600.0;
    let hourly_rate = settings.hourly_rate;
    let curr_sym = if settings.currency_symbol.is_empty() {
        "$"
    } else {
        settings.currency_symbol.as_str()
    };

    let (biz_contact_html, client_emails_joined) = build_contact_parts(settings);
    let client_emails_html = if client_emails_joined.is_empty() {
        String::new()
    } else {
        format!(r#"<div class="client-email">{client_emails_joined}</div>"#)
    };

    let mut qr_items = Vec::new();
    let mut has_any_link = false;
    for fname in settings.qr_code_paths.iter().take(4) {
        let full_path = paths.qr_codes_dir.join(fname);
        if let Some(qr_uri) = image_file_to_data_uri(&full_path) {
            let link_url = settings
                .qr_code_links
                .get(fname)
                .map(|s| s.trim())
                .unwrap_or("");
            let img_html = if !link_url.is_empty() {
                has_any_link = true;
                format!(
                    r#"<a href="{}" target="_blank" style="cursor: pointer; display: block; text-decoration: none; text-align: center;">
                        <img src="{qr_uri}" class="qr-code-image" alt="Payment QR Code" />
                        <div style="font-size: 10px; color: var(--accent); margin-top: 6px; font-weight: 700; font-family: 'Inter', sans-serif;">🔗 Click to Pay</div>
                    </a>"#,
                    html_escape(link_url)
                )
            } else {
                format!(r#"<img src="{qr_uri}" class="qr-code-image" alt="Payment QR Code" />"#)
            };
            qr_items.push(format!(
                r#"<div class="qr-code-item">{img_html}</div>"#
            ));
        }
    }

    let qr_html = if qr_items.is_empty() {
        String::new()
    } else {
        let hint_html = if has_any_link {
            "\n            <div style=\"font-size: 11px; color: var(--text-muted); margin-top: 8px; font-weight: 500; font-family: 'Inter', sans-serif;\">💡 Click on a QR code to open its payment link.</div>"
        } else {
            ""
        };
        format!(
            r#"<div style="margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--border); display: flex; flex-direction: column; align-items: flex-start; justify-content: flex-start; width: 100%;">
                <div class="qr-codes-container">{}</div>{}
                <div class="trust-banner" style="margin-top: 8px; max-width: 320px;">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                        <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                    </svg>
                    <span>Secure Settlement</span>
                </div>
            </div>"#,
            qr_items.join(""),
            hint_html
        )
    };

    let bank_details_html = if settings.enable_bank_details
        && (!settings.bank_holder.is_empty()
            || !settings.bank_account.is_empty()
            || !settings.bank_routing.is_empty()
            || !settings.bank_swift.is_empty()
            || !settings.bank_name.is_empty()
            || !settings.bank_address.is_empty())
    {
        let mut items = Vec::new();
        let push_item = |items: &mut Vec<String>, label: &str, val: &str, span2: bool| {
            if !val.trim().is_empty() {
                let col_style = if span2 {
                    r#" style="grid-column: span 2;""#
                } else {
                    ""
                };
                items.push(format!(
                    r#"<div class="bank-detail-item"{col_style}>
                        <div style="font-size: 10px; font-weight: 700; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.05em;">{label}</div>
                        <div style="font-size: 13px; font-weight: 600; color: var(--text-main); margin-top: 3px; line-height: 1.4;">{}</div>
                    </div>"#,
                    html_escape(val.trim())
                ));
            }
        };
        push_item(&mut items, "Account Holder", &settings.bank_holder, false);
        push_item(&mut items, "Account Number", &settings.bank_account, false);
        push_item(&mut items, "Routing Number", &settings.bank_routing, false);
        push_item(&mut items, "SWIFT / BIC", &settings.bank_swift, false);
        let bank_info = [settings.bank_name.trim(), settings.bank_address.trim()]
            .into_iter()
            .filter(|s| !s.is_empty())
            .collect::<Vec<_>>()
            .join(", ");
        push_item(&mut items, "Bank Name &amp; Address", &bank_info, true);
        format!(
            r#"<div class="bank-details-box" style="margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--border);">
                <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--accent); letter-spacing: 0.05em; margin-bottom: 8px;">Bank Transfer Details</div>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px 16px;">
                    {}
                </div>
            </div>"#,
            items.join("")
        )
    } else {
        String::new()
    };

    let effective_items = if additional_items.is_empty() {
        &billing_data.additional_items
    } else {
        additional_items
    };
    let add_total: f64 = effective_items.iter().map(|it| it.amount).sum();
    let total_due = billing_data.total_earned + add_total;
    let total_due_display = format_currency(curr_sym, total_due);

    let mut items_html = String::new();
    for pb in &billing_data.project_breakdown {
        let cat_hours = pb.seconds as f64 / 3600.0;
        let pill_style = if pb.color != "#64748B" {
            format!("background-color: {}1a; color: {};", pb.color, pb.color)
        } else {
            String::new()
        };
        items_html.push_str(&format!(
            r#"
                <tr>
                    <td style="font-weight: 600;"><span class="tag-pill" style="{pill_style}">{}</span></td>
                    <td>{}</td>
                    <td>{cat_hours:.2}</td>
                    <td>{curr_sym}{hourly_rate:.2}/hr</td>
                    <td>{}</td>
                </tr>
            "#,
            html_escape(&pb.project),
            pb.formatted,
            html_escape(&pb.earned_display)
        ));
    }

    for item in effective_items {
        let desc = if item.description.trim().is_empty() {
            "Additional Payment"
        } else {
            item.description.trim()
        };
        let amt_disp = format_currency(curr_sym, item.amount);
        items_html.push_str(&format!(
            r#"
                <tr>
                    <td style="font-weight: 600;"><span class="tag-pill" style="background-color: rgba(37, 99, 235, 0.12); color: #2563EB;">➕ {}</span></td>
                    <td>Manual Line Item</td>
                    <td>1.00</td>
                    <td>{amt_disp}</td>
                    <td>{amt_disp}</td>
                </tr>
            "#,
            html_escape(desc)
        ));
    }

    let final_invoice_no = invoice_no
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_string)
        .unwrap_or_else(|| format!("INV-{}", Local::now().format("%Y%m%d%H%M")));

    let biz_name = if settings.business_name.trim().is_empty() {
        "TrueHour Invoice"
    } else {
        settings.business_name.trim()
    };
    let client_name = if settings.client_name.trim().is_empty() {
        "Valued Client"
    } else {
        settings.client_name.trim()
    };
    let pay_instr = if settings.business_payment.trim().is_empty() {
        "Payment is due within 14 days of invoice date."
    } else {
        settings.business_payment.trim()
    };

    let mut html = INVOICE_HTML_TEMPLATE.to_string();
    if settings.dark_mode {
        html = html.replace(
            "<body>",
            &format!(r#"<body class="dark {}">"#, settings.theme_style),
        );
    }

    html.replace("{{LOGO_HTML}}", &logo_html)
        .replace("{{BUSINESS_NAME}}", &html_escape(biz_name))
        .replace("{{BUSINESS_ADDRESS}}", &html_escape(&settings.business_address))
        .replace("{{BUSINESS_CONTACT}}", &biz_contact_html)
        .replace("{{INVOICE_NO}}", &html_escape(&final_invoice_no))
        .replace("{{INVOICE_BADGE}}", "INVOICE")
        .replace("{{TOTAL_DUE_LABEL}}", "Total Amount Due")
        .replace("{{PAYMENT_CONFIRMATION_STAMP}}", "")
        .replace("{{DATE}}", &Local::now().format("%B %d, %Y").to_string())
        .replace("{{SESSIONS_COMPILED}}", &billing_data.session_count.to_string())
        .replace("{{CLIENT_NAME}}", &html_escape(client_name))
        .replace("{{CLIENT_ADDRESS}}", &html_escape(&settings.client_address))
        .replace("{{CLIENT_EMAILS_HTML}}", &client_emails_html)
        .replace("{{HOURS_COUNTED}}", &format!("{hours_counted:.2}"))
        .replace("{{TOTAL_AMOUNT_DUE}}", &html_escape(&total_due_display))
        .replace("{{GRAND_TOTAL}}", &html_escape(&total_due_display))
        .replace("{{PAYMENT_INSTRUCTIONS}}", &html_escape(pay_instr))
        .replace("{{QR_HTML}}", &qr_html)
        .replace("{{BANK_DETAILS_HTML}}", &bank_details_html)
        .replace("<!-- {{ITEMS}} -->", &items_html)
        .replace("{{ITEMS}}", &items_html)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::appinfo::AppResolver;
    use serde_json::json;
    use tempfile::TempDir;

    #[test]
    fn test_mask_email_and_phone_parity() {
        assert_eq!(mask_email("neil@gmail.com"), "ne**@*****.com");
        assert_eq!(mask_email("ab@test.io"), "ab**@*****.io");
        assert_eq!(mask_email("invalid"), "invalid");
        assert_eq!(mask_phone("+1 (555) 123-4567"), "+1 (555) ***-****");
    }

    #[test]
    fn test_merge_sessions_and_generate_invoice_and_receipt_html() {
        let tmp = TempDir::new().unwrap();
        let paths = ProfilePaths::from_root_and_profile(tmp.path().to_path_buf(), "Test".into());
        paths.ensure_dirs().unwrap();
        let resolver = AppResolver::new(paths.name_overrides_file.clone());
        let tag_mgr = TagManager::new(paths.tags_file.clone(), resolver);
        tag_mgr.set_tag("VS Code", "Development");

        let s1 = paths.sessions_dir.join("session_2026-11-01_09-00-00.json");
        let s2 = paths.sessions_dir.join("session_2026-11-02_09-00-00.json");
        fs::write(
            &s1,
            serde_json::to_string_pretty(&json!({
                "date": "2026-11-01",
                "start": "09:00:00",
                "total_seconds": 3600,
                "counted_seconds": 3600,
                "apps": [
                    {"name": "VS Code", "seconds": 3600, "excluded": false, "tag": "Unassigned"},
                    {"name": "Spotify", "seconds": 600, "excluded": true, "tag": "Unassigned"}
                ]
            }))
            .unwrap(),
        )
        .unwrap();
        fs::write(
            &s2,
            serde_json::to_string_pretty(&json!({
                "date": "2026-11-02",
                "start": "09:00:00",
                "total_seconds": 1800,
                "counted_seconds": 1800,
                "apps": [{"name": "Figma", "seconds": 1800, "excluded": false, "tag": "Design"}]
            }))
            .unwrap(),
        )
        .unwrap();

        let billing = merge_sessions_for_invoice(&tag_mgr, &[s1, s2], 50.0, "$").unwrap();
        assert_eq!(billing.session_count, 2);
        assert_eq!(billing.counted_seconds, 5400);
        assert_eq!(billing.total_earned, 75.0);
        assert!(billing
            .project_breakdown
            .iter()
            .any(|p| p.project == "Development" && p.seconds == 3600));

        let settings = FullSettingsDto {
            confirm_on_close: true,
            developer_mode: false,
            theme_style: "modern-dark".into(),
            dark_mode: true,
            min_track_seconds: 2,
            auto_save_seconds: 10,
            idle_threshold_seconds_total: 120,
            currency_symbol_raw: "$ (USD)".into(),
            currency_symbol: "$".into(),
            hourly_rate: 50.0,
            enable_distraction_auto_pause: false,
            distraction_apps: vec![],
            weekly_goal_hours: 40.0,
            business_name: "Studio Labs".into(),
            business_address: "123 Market St".into(),
            business_emails: vec!["billing@studiolabs.com".into()],
            business_phone: "+1 555 123 4567".into(),
            business_payment: "Net 14".into(),
            enable_bank_details: true,
            bank_holder: "Studio Labs LLC".into(),
            bank_account: "99998888".into(),
            bank_routing: "111000222".into(),
            bank_swift: "".into(),
            bank_name: "First Bank".into(),
            bank_address: "".into(),
            client_name: "Client Co".into(),
            client_address: "456 Oak".into(),
            client_emails: vec!["ap@client.co".into()],
            enable_business_logo: true,
            business_logo_path: "".into(),
            qr_code_paths: vec![],
            qr_code_links: HashMap::new(),
            qr_code_items: vec![],
            mask_business_emails: true,
            mask_business_phone: true,
            mask_client_emails: true,
        };

        let items = vec![ManualLineItem {
            description: "Rush Fee".into(),
            amount: 25.0,
        }];
        let inv_html = generate_invoice_html(&paths, &billing, &settings, "unpaid", Some("INV-100"), &items);
        assert!(inv_html.contains("INV-100"));
        assert!(inv_html.contains("$100.00"));
        assert!(inv_html.contains("bi**@*****.com"));
        assert!(inv_html.contains("ap**@*****.co"));
        assert!(inv_html.contains("Studio Labs LLC"));
        assert!(inv_html.contains("Rush Fee"));

        let rec_html = generate_invoice_html(&paths, &billing, &settings, "paid", Some("INV-100"), &items);
        assert!(rec_html.contains("PAID RECEIPT"));
        assert!(rec_html.contains("INV-100"));
        assert!(rec_html.contains("$100.00"));
    }
}
