# gmail_demo_3_pal_plan.py

import os
import json
from dotenv import load_dotenv

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from openai import OpenAI

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


# ============================================================
# ##1 Gmail auth
# ============================================================
def get_gmail_service():
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        with open("token.json", "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


# ============================================================
# ##2 Gmail helpers
# ============================================================
def get_header(headers, name):
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def read_emails(service, query="newer_than:7d", max_results=10):
    res = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )

    msgs = res.get("messages", [])
    out = []

    for m in msgs:
        msg = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=m["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            )
            .execute()
        )

        headers = msg.get("payload", {}).get("headers", [])

        out.append(
            {
                "subject": get_header(headers, "Subject"),
                "from": get_header(headers, "From"),
                "date": get_header(headers, "Date"),
                "snippet": msg.get("snippet", ""),
            }
        )

    return out


# ============================================================
# ##3 OpenAI client
# ============================================================
def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found in .env")
    return OpenAI(api_key=api_key)


# ============================================================
# ##4 Planner
# user prompt -> JSON plan
# ============================================================
def make_plan(client, user_prompt):
    system = """
You are a planner for a Gmail read-only agent.

Return ONLY valid JSON.
No markdown. No explanation.

Allowed schema:
{
  "action": "read_emails",
  "query": "<gmail search query>",
  "limit": <integer 1..20>
}

Examples:
User: get emails
{"action":"read_emails","query":"newer_than:7d","limit":10}

User: get unread emails
{"action":"read_emails","query":"is:unread newer_than:7d","limit":10}

User: get emails from amazon
{"action":"read_emails","query":"from:amazon newer_than:30d","limit":10}

User: summarize latest promotional emails
{"action":"read_emails","query":"category:promotions newer_than:14d","limit":10}
""".strip()

    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )

    text = resp.choices[0].message.content.strip()
    plan = json.loads(text)

    if plan.get("action") != "read_emails":
        raise ValueError("Only action=read_emails is allowed")

    limit = int(plan.get("limit", 10))
    if limit < 1 or limit > 20:
        raise ValueError("limit must be between 1 and 20")

    query = str(plan.get("query", "newer_than:7d")).strip()
    if not query:
        query = "newer_than:7d"

    return {"action": "read_emails", "query": query, "limit": limit}


# ============================================================
# ##5 Summarizer
# emails -> natural language answer
# ============================================================
def summarize_emails(client, user_prompt, emails):
    text = "\n\n".join(
        [
            f"From: {e['from']}\nSubject: {e['subject']}\nDate: {e['date']}\nSnippet: {e['snippet']}"
            for e in emails
        ]
    )

    prompt = f"""
User request:
{user_prompt}

Emails:
{text}

Give a brief helpful answer.
""".strip()

    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    return resp.choices[0].message.content


# ============================================================
# ##6 Main
# ============================================================
def main():
    user_prompt = input("PROMPT: ").strip()
    if not user_prompt:
        user_prompt = "get emails"

    client = get_openai_client()
    service = get_gmail_service()

    plan = make_plan(client, user_prompt)

    print("\n--- PLAN ---")
    print(json.dumps(plan, indent=2))

    emails = read_emails(
        service,
        query=plan["query"],
        max_results=plan["limit"],
    )

    print(f"\n--- RAW EMAILS ({len(emails)}) ---")
    for i, e in enumerate(emails, start=1):
        print(f"[{i}] {e['subject']} | {e['from']}")

    answer = summarize_emails(client, user_prompt, emails)

    print("\n--- AI RESPONSE ---")
    print(answer)


if __name__ == "__main__":
    main()
