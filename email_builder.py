"""Email automation (Phase 1).

Turns the analysis results into one email per rep (fuel regions) and one per TTC manager, generates each
brief with Claude, and packages the result as JSON files that a Power Automate flow sends from Outlook.

This module deliberately has no Streamlit dependency so it can be tested on its own.
"""
import csv
import html
import io
import json
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

from alignment import (
    region_key, first_name, make_email, is_open_seat, inside_region_codes,
)
from config import (
    EMAIL_EXCLUDED_REGIONS, EMAIL_SIGNOFF, EMAIL_MAX_WORKERS, EMAIL_MAX_TOKENS,
    EMAIL_MODEL, PRICE_INPUT_PER_MTOK, PRICE_OUTPUT_PER_MTOK,
    TTC_KNOWN_MANAGERS, TTC_EMAIL_LABELS,
)
from fuel_prompt import build_claude_prompt
from ttc_prompt import build_ttc_prompt


# ═══════════════════════════════════════════════════════════════════════════════
# Planning: who gets which email
# ═══════════════════════════════════════════════════════════════════════════════
def filter_results_for_region(results, code):
    """Every account whose region rolls up to this region number (30, 30.1, 30.2 -> '30')."""
    def match(a):
        return region_key(a.get("region")) == code
    return {
        "report_date": results["report_date"],
        "region_summary": [],
        "fuel_main_alerts": [a for a in results["fuel_main_alerts"] if match(a)],
        "fuel_secondary": [a for a in results["fuel_secondary"] if match(a)],
        "fuel_newly_dark": [a for a in results["fuel_newly_dark"] if match(a)],
        "fuel_increases": [a for a in results["fuel_increases"] if match(a)],
        "non_fuel_alerts": {
            metric: [a for a in alerts if match(a)]
            for metric, alerts in results["non_fuel_alerts"].items()
        },
        "errors": [],
    }


def _count_flagged(filtered):
    n = (len(filtered["fuel_main_alerts"]) + len(filtered["fuel_secondary"])
         + len(filtered["fuel_newly_dark"]) + len(filtered["fuel_increases"]))
    n += sum(len(v) for v in filtered["non_fuel_alerts"].values())
    return n


def _region_sort_key(code):
    try:
        return (0, int(code))
    except ValueError:
        return (1, code)


def build_fuel_items(results, alignment):
    """Returns (items, skipped). Each item is one email to generate."""
    items, skipped = [], []
    inside_codes = inside_region_codes(alignment)
    report_date = results.get("report_date") or "Unknown"

    for code in sorted(alignment["regions"], key=_region_sort_key):
        entry = alignment["regions"][code]
        label = f"Region {code}"

        if code in EMAIL_EXCLUDED_REGIONS:
            skipped.append({"email": label, "reason": "Excluded region"})
            continue
        if not entry["rep"] or is_open_seat(entry["rep"]):
            skipped.append({"email": label, "reason": "No rep (OPEN seat)"})
            continue

        warnings = []
        to_addr = make_email(entry["rep"])
        if not to_addr:
            skipped.append({"email": label, "reason": f"Can't build an address from rep name '{entry['rep']}'"})
            continue

        cc_addrs = []
        for am in entry["area_managers"]:
            addr = make_email(am)
            if addr:
                cc_addrs.append(addr)
            else:
                warnings.append(f"Can't build an address for Area Manager '{am}' -- not CC'd")

        filtered = filter_results_for_region(results, code)
        flagged = _count_flagged(filtered)
        if flagged == 0:
            warnings.append("No flagged accounts this period")

        prompt, table_map = build_claude_prompt(
            filtered, email_mode=True, region_label=label, inside_regions=inside_codes
        )
        items.append({
            "id": f"region-{code}",
            "kind": "fuel",
            "label": label,
            "to_name": entry["rep"],
            "greeting_name": first_name(entry["rep"]),
            "to": to_addr,
            "cc": cc_addrs,
            "subject": f"{label} Summary Period Ending {report_date}",
            "prompt": prompt,
            "table_map": table_map,
            "flagged": flagged,
            "warnings": warnings,
            "file_stem": f"Region_{code}_Summary",
        })

    # Regions that have accounts in the report but no alignment row are never emailed -- surface them.
    report_codes = set()
    for a in (results["fuel_main_alerts"] + results["fuel_secondary"]
              + results["fuel_newly_dark"] + results["fuel_increases"]):
        report_codes.add(region_key(a.get("region")))
    for alerts in results["non_fuel_alerts"].values():
        for a in alerts:
            report_codes.add(region_key(a.get("region")))
    for code in sorted(report_codes - set(alignment["regions"]), key=_region_sort_key):
        skipped.append({"email": f"Region {code}", "reason": "In the report but not in the alignment file -- not emailed"})
    return items, skipped


def build_ttc_items(ttc_results, report_date):
    items = []
    for manager in TTC_KNOWN_MANAGERS:
        label = TTC_EMAIL_LABELS.get(manager, manager)
        to_addr = make_email(manager)
        prompt, table_map = build_ttc_prompt(manager, ttc_results)
        flagged = sum(len(v) for v in ttc_results.get("flagged_customers", {}).get(manager, {}).values())
        warnings = [] if to_addr else [f"Can't build an address for '{manager}'"]
        items.append({
            "id": f"ttc-{manager.split()[0].lower()}",
            "kind": "ttc",
            "label": label,
            "to_name": manager,
            "greeting_name": first_name(manager),
            "to": to_addr or "",
            "cc": [],
            "subject": f"{label} Summary Period Ending {report_date}",
            "prompt": prompt,
            "table_map": table_map,
            "flagged": flagged,
            "warnings": warnings,
            "file_stem": label.replace(" ", "_") + "_Summary",
        })
    return items


# ═══════════════════════════════════════════════════════════════════════════════
# Cost estimate (shown BEFORE any Claude call)
# ═══════════════════════════════════════════════════════════════════════════════
def estimate_cost(items):
    """Rough range. Input tokens ~ chars/3 (conservative for table-heavy text);
    output tokens: typical 1,500 (fuel) / 2,500 (TTC), high 4,000 / 6,000."""
    in_tok = sum(len(i["prompt"]) / 3.0 for i in items)
    typical_out = sum(1500 if i["kind"] == "fuel" else 2500 for i in items)
    high_out = sum(4000 if i["kind"] == "fuel" else 6000 for i in items)

    def cost(i_tok, o_tok):
        return i_tok / 1e6 * PRICE_INPUT_PER_MTOK + o_tok / 1e6 * PRICE_OUTPUT_PER_MTOK

    return {"typical": cost(in_tok, typical_out), "high": cost(in_tok, high_out), "input_tokens": int(in_tok)}


def actual_cost(in_tokens, out_tokens):
    return in_tokens / 1e6 * PRICE_INPUT_PER_MTOK + out_tokens / 1e6 * PRICE_OUTPUT_PER_MTOK


# ═══════════════════════════════════════════════════════════════════════════════
# Generating the briefs
# ═══════════════════════════════════════════════════════════════════════════════
def call_claude(client, prompt, model=EMAIL_MODEL, max_tokens=EMAIL_MAX_TOKENS, retries=3):
    last = None
    for attempt in range(retries):
        try:
            msg = client.messages.create(
                model=model, max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            usage = getattr(msg, "usage", None)
            return (
                msg.content[0].text,
                getattr(usage, "input_tokens", 0) or 0,
                getattr(usage, "output_tokens", 0) or 0,
            )
        except Exception as e:  # network / rate limit / overloaded -- retry with backoff
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def _generate_one(client, item):
    raw, in_tok, out_tok = call_claude(client, item["prompt"])
    raw = raw.replace(chr(96), "")  # same backtick strip the portal already applies
    warnings = []
    missing = [t for t in item["table_map"] if t not in raw]
    if missing:
        warnings.append("Claude left out table(s): " + ", ".join(missing))
    body_md = raw
    for token, table_text in item["table_map"].items():
        body_md = body_md.replace(token, table_text)
    leftover = re.findall(r"%%[A-Z0-9_]+%%", body_md)
    if leftover:
        warnings.append("Unreplaced placeholder(s): " + ", ".join(sorted(set(leftover))))
        body_md = re.sub(r"%%[A-Z0-9_]+%%", "", body_md)
    return {
        "status": "ok", "markdown": body_md, "warnings": warnings,
        "in_tokens": in_tok, "out_tokens": out_tok,
    }


def generate_all(items, client, progress_cb=None, max_workers=EMAIL_MAX_WORKERS):
    """Generate every brief (several at a time). Returns {item_id: output dict}.
    progress_cb(done, total, item_label) is called from the calling thread only."""
    outputs = {}
    total = len(items)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_generate_one, client, it): it for it in items}
        done = 0
        for fut in as_completed(futures):
            it = futures[fut]
            try:
                outputs[it["id"]] = fut.result()
            except Exception as e:
                outputs[it["id"]] = {
                    "status": "error", "markdown": "", "warnings": [f"Claude call failed: {e}"],
                    "in_tokens": 0, "out_tokens": 0,
                }
            done += 1
            if progress_cb:
                progress_cb(done, total, it["label"])
    return outputs


# ═══════════════════════════════════════════════════════════════════════════════
# Markdown -> Outlook-friendly HTML
# ═══════════════════════════════════════════════════════════════════════════════
FONT = "Calibri, Arial, sans-serif"
_NUMERIC_CELL = re.compile(r"^[+\-]?\$?[\d,]*\.?\d+(\s?(GAL|EA|Hrs|%))?$")


def _inline(text):
    """Escape, then apply **bold**."""
    out = html.escape(text, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)


def _split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_separator(line):
    cells = _split_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c) for c in cells)


def _table_html(table_lines):
    header = _split_row(table_lines[0])
    body = [_split_row(l) for l in table_lines[2:]] if len(table_lines) > 2 else []
    th_style = (f"font-family:{FONT};font-size:12px;font-weight:bold;color:#ffffff;background-color:#d90d0d;"
                "border:1px solid #bbbbbb;padding:4px 8px;text-align:left;")
    out = ['<table cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin:6px 0 10px 0;">',
           "<tr>" + "".join(f'<th bgcolor="#d90d0d" style="{th_style}">{_inline(h)}</th>' for h in header) + "</tr>"]
    for r_i, row in enumerate(body):
        bg = "#f7f7f7" if r_i % 2 else "#ffffff"
        cells = []
        for c in row:
            align = "right" if _NUMERIC_CELL.match(c) else "left"
            td_style = (f"font-family:{FONT};font-size:12px;color:#222222;border:1px solid #cccccc;"
                        f"padding:4px 8px;text-align:{align};")
            cells.append(f'<td bgcolor="{bg}" style="{td_style}">{_inline(c)}</td>')
        out.append("<tr>" + "".join(cells) + "</tr>")
    out.append("</table>")
    return "\n".join(out)


def md_to_html(md):
    """Converts the brief's markdown subset (headings, bullets, tables, bold, paragraphs) to inline-styled HTML."""
    lines = md.replace("\r\n", "\n").split("\n")
    out, i = [], 0
    bullets = []

    def flush_bullets():
        if bullets:
            li = "".join(f'<li style="margin:2px 0;">{_inline(b)}</li>' for b in bullets)
            out.append(f'<ul style="font-family:{FONT};font-size:14px;color:#222222;margin:4px 0 8px 0;padding-left:22px;">{li}</ul>')
            bullets.clear()

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()

        if not stripped:
            flush_bullets()
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < len(lines) and _is_separator(lines[i + 1]):
            flush_bullets()
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            out.append(_table_html([l.strip() for l in lines[i:j]]))
            i = j
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            flush_bullets()
            level, text = len(m.group(1)), m.group(2)
            if level <= 2:
                style = (f"font-family:{FONT};font-size:17px;font-weight:bold;color:#1a1a1a;margin:16px 0 6px 0;"
                         "padding-bottom:3px;border-bottom:2px solid #d90d0d;")
                tag = "h2"
            elif level == 3:
                style = f"font-family:{FONT};font-size:15px;font-weight:bold;color:#1a1a1a;margin:12px 0 4px 0;"
                tag = "h3"
            else:
                style = f"font-family:{FONT};font-size:14px;font-weight:bold;color:#444444;margin:10px 0 2px 0;"
                tag = "h4"
            out.append(f'<{tag} style="{style}">{_inline(text)}</{tag}>')
            i += 1
            continue

        m = re.match(r"^[-*•]\s+(.*)$", stripped)
        if m:
            bullets.append(m.group(1))
            i += 1
            continue

        flush_bullets()
        out.append(f'<p style="font-family:{FONT};font-size:14px;color:#222222;margin:4px 0;">{_inline(stripped)}</p>')
        i += 1

    flush_bullets()
    return "\n".join(out)


SIGNATURE_NAME = "John Mark Martinez"
SIGNATURE_LINES = [
    "Fleet Sales Analyst I",
    "Love\u2019s Travel Stops & Country Stores",
    "682-597-7011",
]
SIGNATURE_LINK = ("Loves.com", "https://www.loves.com/")
SIGNATURE_SOCIAL = [
    ("Facebook", "https://www.facebook.com/lovestravelstops/"),
    ("X", "https://x.com/LovesTravelStop"),
    ("LinkedIn", "https://www.linkedin.com/company/love's-travel-stops"),
    ("Instagram", "https://www.instagram.com/lovestravelstops/"),
]


def _link(label, url):
    return (f'<a href="{html.escape(url, quote=True)}" '
            f'style="color:#0563C1;text-decoration:underline;">{html.escape(label, quote=False)}</a>')


def build_signature_html():
    """Sign-off plus signature block. Same font and size as the email body."""
    line = f'font-family:{FONT};font-size:14px;color:#222222;margin:0;'
    social = " | ".join(_link(label, url) for label, url in SIGNATURE_SOCIAL)
    rows = [
        f'<p style="{line}margin-top:16px;">{html.escape(EMAIL_SIGNOFF, quote=False)}</p>',
        f'<p style="{line}">&nbsp;</p>',
        f'<p style="{line}"><b>{html.escape(SIGNATURE_NAME, quote=False)}</b></p>',
    ]
    rows += [f'<p style="{line}">{html.escape(t, quote=False)}</p>' for t in SIGNATURE_LINES]
    rows.append(f'<p style="{line}">{_link(*SIGNATURE_LINK)}</p>')
    rows.append(f'<p style="{line}">{social}</p>')
    return "\n".join(rows)


def build_email_html(greeting_name, brief_md):
    """The full email body: greeting, the brief, then the sign-off and signature."""
    p = f'font-family:{FONT};font-size:14px;color:#222222;margin:0 0 10px 0;'
    return (
        f'<div style="font-family:{FONT};font-size:14px;color:#222222;">\n'
        f'<p style="{p}">Hello {html.escape(greeting_name, quote=False)},</p>\n'
        f"{md_to_html(brief_md)}\n"
        f"{build_signature_html()}\n"
        "</div>"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Packaging for Power Automate
# ═══════════════════════════════════════════════════════════════════════════════
def _safe_date(report_date):
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", str(report_date))
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return re.sub(r"[^0-9A-Za-z\-]+", "-", str(report_date)).strip("-") or "unknown"


def _preview_page(item, to, cc, subject, body_html, test_note=""):
    head = (
        f'<div style="font-family:{FONT};font-size:12px;color:#555;background:#f2f2f2;padding:8px 12px;'
        f'border-bottom:1px solid #ccc;margin-bottom:12px;">'
        f"<b>To:</b> {html.escape(to)}<br><b>CC:</b> {html.escape(cc)}<br><b>Subject:</b> {html.escape(subject)}"
        f"{test_note}</div>"
    )
    return f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>{html.escape(subject)}</title></head><body>{head}{body_html}</body></html>'


def finalize_item(item, output, report_date, test_address=None):
    """The exact payload one Power Automate run will send for this item."""
    body_html = build_email_html(item["greeting_name"], output["markdown"])
    real_to, real_cc = item["to"], "; ".join(item["cc"])
    test_note = ""
    if test_address:
        to, cc, subject = test_address, "", f"[TEST] {item['subject']}"
        test_note = f"<br><b>TEST MODE</b> -- real recipients would be To: {html.escape(real_to)} | CC: {html.escape(real_cc)}"
    else:
        to, cc, subject = real_to, real_cc, item["subject"]
    return {
        "to": to, "cc": cc, "subject": subject, "body": body_html,
        "region": item["label"], "period": str(report_date),
        "_preview": _preview_page(item, to, cc, subject, body_html, test_note),
        "_file": f"{item['file_stem']}_{_safe_date(report_date)}",
    }


def package_zip(items, outputs, skipped, report_date, test_address=None):
    """ZIP layout:  send/*.json  (what Power Automate picks up)
                    preview/*.html  (open in a browser to review -- do NOT upload)
                    recipients.csv  (every email, its status, and anything skipped)"""
    buf = io.BytesIO()
    rows = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for item in items:
            out = outputs.get(item["id"])
            if not out or out["status"] != "ok":
                rows.append([item["label"], item["to"], "; ".join(item["cc"]), item["subject"], "NOT GENERATED",
                             "; ".join((out or {}).get("warnings", []) or item["warnings"])])
                continue
            if not item["to"] and not test_address:
                rows.append([item["label"], "", "", item["subject"], "NOT PACKAGED", "No recipient address"])
                continue
            payload = finalize_item(item, out, report_date, test_address)
            name = payload.pop("_file")
            preview = payload.pop("_preview")
            z.writestr(f"send/{name}.json", json.dumps(payload, indent=2, ensure_ascii=False))
            z.writestr(f"preview/{name}.html", preview)
            rows.append([item["label"], payload["to"], payload["cc"], payload["subject"], "READY",
                         "; ".join(item["warnings"] + out["warnings"])])
        for s in skipped:
            rows.append([s["email"], "", "", "", "SKIPPED", s["reason"]])

        csv_buf = io.StringIO()
        w = csv.writer(csv_buf)
        w.writerow(["Email", "To", "CC", "Subject", "Status", "Notes"])
        w.writerows(rows)
        z.writestr("recipients.csv", csv_buf.getvalue())
    return buf.getvalue()
