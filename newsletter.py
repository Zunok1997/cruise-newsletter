import os
import re
import smtplib
import feedparser
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta
from groq import Groq

# ── RSS Sources ───────────────────────────────────────────────────────────────

RSS_FEEDS = [
    ("Seatrade Cruise",      "https://www.seatrade-cruise.com/rss/all"),
    ("Cruise Industry News", "https://cruiseindustrynews.com/feed/"),
    ("Skift",                "https://skift.com/feed/"),
    ("TradeWinds",           "https://www.tradewindsnews.com/feed/"),
    ("ShippingWatch",        "https://en.shippingwatch.com/rss"),
]

CATEGORY_COLORS = {
    "New Ships":             "#0066cc",
    "Ports & Destinations":  "#0f9d58",
    "Business & Finance":    "#e67e00",
    "People & Appointments": "#7b1fa2",
    "Events & Trade Shows":  "#c62828",
    "Operations":            "#00838f",
    "Sustainability":        "#2e7d32",
    "Technology":            "#e65100",
}

# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch_news():
    articles = []
    for source, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            count = 0
            for entry in feed.entries[:12]:
                summary = re.sub(r"<[^>]+>", "", entry.get("summary", ""))[:600].strip()
                articles.append({
                    "source":    source,
                    "title":     entry.get("title", "").strip(),
                    "summary":   summary,
                    "link":      entry.get("link", ""),
                    "published": entry.get("published", ""),
                })
                count += 1
            print(f"  {source}: {count} articles")
        except Exception as e:
            print(f"  {source}: ERROR — {e}")
    return articles

# ── AI Generation ─────────────────────────────────────────────────────────────

def generate_analysis(articles):
    client = Groq(api_key=os.environ["GROQ_API_KEY"])

    articles_text = "\n\n".join([
        f"[{i+1}] SOURCE: {a['source']}\nTITLE: {a['title']}\nSUMMARY: {a['summary']}\nURL: {a['link']}"
        for i, a in enumerate(articles)
    ])

    today = datetime.now(timezone(timedelta(hours=-3))).strftime("%B %d, %Y")

    prompt = f"""You are a senior analyst covering the global cruise and maritime travel industry. Today is {today}.

Below are the latest articles from major industry publications. Read them carefully.

{articles_text}

Select the 8 most newsworthy and relevant articles. For each one, produce a structured analysis block.

Return ONLY the following format — no intro text, no commentary outside the delimiters:

##STORIES##
ARTICLE_INDEX|CATEGORY|HEADLINE|ANALYSIS|KEY_PLAYERS|IMPLICATIONS|URL
---
ARTICLE_INDEX|CATEGORY|HEADLINE|ANALYSIS|KEY_PLAYERS|IMPLICATIONS|URL
---
(repeat for all 8 stories)
##END##

Field rules:
- ARTICLE_INDEX: the number [N] from the list above
- CATEGORY: exactly one of: New Ships | Ports & Destinations | Business & Finance | People & Appointments | Events & Trade Shows | Operations | Sustainability | Technology
- HEADLINE: a clear, concise rewrite of the headline (max 14 words)
- ANALYSIS: 3-4 sentence expert analysis explaining what happened and why it matters to the cruise industry
- KEY_PLAYERS: comma-separated list of cruise lines, companies, ports, shipyards, or executives mentioned
- IMPLICATIONS: 2 sentences on what this means for the industry going forward
- URL: the article's URL exactly as provided

Do not use pipe characters | inside any field text. Separate story blocks with a line containing only ---."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=8000,
        temperature=0.3,
    )
    return response.choices[0].message.content


def parse_stories(ai_output, articles):
    stories = []
    try:
        body = ai_output.split("##STORIES##")[1].split("##END##")[0].strip()
        for block in body.split("---"):
            block = block.strip()
            if not block:
                continue
            parts = [p.strip() for p in block.split("|")]
            if len(parts) < 7:
                print(f"  Skipping malformed block: {block[:80]}")
                continue
            idx_str = parts[0].strip()
            url = parts[6].strip()
            # fall back to original article URL if AI mangled it
            try:
                orig_idx = int(re.sub(r"\D", "", idx_str)) - 1
                if not url.startswith("http") and 0 <= orig_idx < len(articles):
                    url = articles[orig_idx]["link"]
            except ValueError:
                pass
            stories.append({
                "category":    parts[1],
                "headline":    parts[2],
                "analysis":    parts[3],
                "key_players": parts[4],
                "implications":parts[5],
                "url":         url,
            })
    except Exception as e:
        print(f"  Parse error: {e}")
    return stories

# ── HTML ──────────────────────────────────────────────────────────────────────

def _badge(category):
    color = CATEGORY_COLORS.get(category, "#546e7a")
    return (
        f'<span style="background:{color};color:#fff;padding:2px 9px;border-radius:12px;'
        f'font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.6px;'
        f'white-space:nowrap">{category}</span>'
    )


def _story_block(i, s):
    badge = _badge(s["category"])
    return f"""
    <details style="margin-bottom:10px;border:1px solid #dde3ea;border-radius:10px;overflow:hidden">
      <summary style="padding:15px 18px;cursor:pointer;background:#f8fafc;list-style:none;
                      display:flex;align-items:flex-start;gap:14px;user-select:none">
        <span style="color:#0066cc;font-weight:800;font-size:15px;min-width:26px;
                     padding-top:1px">{i:02d}</span>
        <div style="flex:1">
          <div style="margin-bottom:6px">{badge}</div>
          <p style="margin:0;font-weight:600;font-size:14px;color:#1a1f2e;line-height:1.45">
            {s['headline']}
          </p>
        </div>
        <span style="color:#9aa8b8;font-size:18px;padding-top:2px;flex-shrink:0">›</span>
      </summary>
      <div style="padding:16px 20px 18px;background:#ffffff;border-top:1px solid #dde3ea">
        <p style="margin:0 0 14px;color:#374151;font-size:13.5px;line-height:1.65">
          {s['analysis']}
        </p>
        <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px">
          <div style="flex:1;min-width:200px;background:#f0f4f8;border-radius:7px;padding:11px 14px">
            <p style="margin:0 0 4px;font-size:11px;font-weight:700;color:#64748b;
                      text-transform:uppercase;letter-spacing:0.7px">Key Players</p>
            <p style="margin:0;font-size:13px;color:#1e293b">{s['key_players']}</p>
          </div>
          <div style="flex:1;min-width:200px;background:#eff6ff;border-radius:7px;padding:11px 14px;
                      border-left:3px solid #0066cc">
            <p style="margin:0 0 4px;font-size:11px;font-weight:700;color:#0066cc;
                      text-transform:uppercase;letter-spacing:0.7px">Implications</p>
            <p style="margin:0;font-size:13px;color:#1e293b">{s['implications']}</p>
          </div>
        </div>
        <a href="{s['url']}" target="_blank"
           style="display:inline-block;background:#0066cc;color:#fff;text-decoration:none;
                  padding:8px 18px;border-radius:7px;font-size:12.5px;font-weight:600">
          Read Full Article &rarr;
        </a>
      </div>
    </details>"""


def build_html(stories):
    tz_ar = timezone(timedelta(hours=-3))
    date_str = datetime.now(tz_ar).strftime("%B %d, %Y")
    pages_url = os.environ.get("PAGES_URL", "#")

    stories_html = "".join(_story_block(i + 1, s) for i, s in enumerate(stories))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Cruise & Maritime Daily &mdash; {date_str}</title>
  <style>
    details summary::-webkit-details-marker {{ display:none }}
    details[open] summary span:last-child {{ transform:rotate(90deg);display:inline-block }}
    @media (max-width:600px) {{ .two-col {{ flex-direction:column }} }}
  </style>
</head>
<body style="margin:0;padding:0;background:#eef2f7;font-family:-apple-system,BlinkMacSystemFont,
             'Segoe UI',Roboto,Arial,sans-serif">
  <div style="max-width:700px;margin:0 auto;padding:20px 16px">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#00204a 0%,#003d7a 50%,#0066cc 100%);
                border-radius:14px;padding:36px 32px;margin-bottom:20px;text-align:center">
      <p style="margin:0 0 8px;font-size:11px;color:rgba(255,255,255,0.6);
                text-transform:uppercase;letter-spacing:3px">Daily Briefing</p>
      <h1 style="margin:0 0 6px;color:#ffffff;font-size:24px;font-weight:800;
                 letter-spacing:-0.3px">Cruise &amp; Maritime Intelligence</h1>
      <p style="margin:0;color:rgba(255,255,255,0.75);font-size:13px">{date_str}</p>
    </div>

    <!-- Subtitle -->
    <p style="text-align:center;color:#64748b;font-size:12.5px;margin:0 0 18px">
      {len(stories)} top stories &nbsp;&middot;&nbsp; Click any headline to expand
    </p>

    <!-- Stories -->
    {stories_html}

    <!-- Footer -->
    <div style="border-top:1px solid #dde3ea;margin-top:28px;padding-top:20px;text-align:center">
      <a href="{pages_url}" style="color:#0066cc;text-decoration:none;font-size:12.5px;
                                   font-weight:600">View online version</a>
      <p style="color:#9aa8b8;font-size:11px;margin:10px 0 0;line-height:1.6">
        Sources: Seatrade Cruise &nbsp;&middot;&nbsp; Cruise Industry News &nbsp;&middot;&nbsp;
        Skift &nbsp;&middot;&nbsp; TradeWinds &nbsp;&middot;&nbsp; ShippingWatch<br>
        Analysis generated by AI &mdash; verify before acting on any information.
      </p>
    </div>

  </div>
</body>
</html>"""

# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(html_content):
    gmail_user     = os.environ["GMAIL_USER"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]
    recipients     = [r.strip() for r in os.environ["RECIPIENT_EMAIL"].split(",")]
    pages_url      = os.environ.get("PAGES_URL", "")

    tz_ar    = timezone(timedelta(hours=-3))
    date_str = datetime.now(tz_ar).strftime("%B %d, %Y")
    subject  = f"Cruise & Maritime Daily — {date_str}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = gmail_user
    msg["To"]      = ", ".join(recipients)

    email_html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
  <div style="max-width:500px;margin:0 auto;padding:40px 24px;text-align:center">
    <p style="font-size:16px;color:#1a1f2e;margin:0 0 32px;text-align:left">Buenos dias,</p>
    <a href="{pages_url}" target="_blank"
       style="display:inline-block;background:linear-gradient(135deg,#00204a,#0066cc);
              color:#ffffff;text-decoration:none;padding:16px 40px;border-radius:10px;
              font-size:15px;font-weight:700;letter-spacing:0.3px">
      ⚓ Ver Cruise &amp; Maritime Daily
    </a>
    <p style="font-size:16px;color:#1a1f2e;margin:32px 0 0;text-align:left">Saludos,</p>
  </div>
</body>
</html>"""

    plain = f"Buenos dias,\n\nCruise & Maritime Daily — {date_str}\n{pages_url}\n\nSaludos,"
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(email_html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, recipients, msg.as_string())

    print(f"  Email sent to: {', '.join(recipients)}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("1. Fetching news...")
    articles = fetch_news()
    print(f"   Total: {len(articles)} articles\n")

    if not articles:
        print("No articles fetched — aborting.")
        return

    print("2. Generating AI analysis...")
    ai_output = generate_analysis(articles)
    print(ai_output[:1500], "\n")

    print("3. Parsing stories...")
    stories = parse_stories(ai_output, articles)
    print(f"   {len(stories)} stories parsed\n")

    if not stories:
        print("No stories parsed — aborting.")
        return

    print("4. Building HTML...")
    html = build_html(stories)
    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("   Saved to docs/index.html\n")

    print("5. Sending email...")
    send_email(html)
    print("\nDone.")


if __name__ == "__main__":
    main()
