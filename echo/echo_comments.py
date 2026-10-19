#!/usr/bin/env python3
"""Echo: Kommentare unter Noels Instagram-Beiträgen abholen und per privater Antwort eine DM schicken.

Instagram erlaubt genau eine private Antwort (DM) pro Kommentar, bis 7 Tage nach dem Kommentar.
Antwortet die Person, landet das Gespräch bei Leni (scout/scout_dm.py).
Der Zugangsschlüssel kommt als Netzwerk-Secret (vom Proxy eingesetzt) oder aus IG_ACCESS_TOKEN.

  python3 echo_comments.py fetch [--days 7]         # neue Kommentare als JSON
  python3 echo_comments.py reply --comment ID --text-file dm.txt
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://graph.instagram.com/v25.0"
REPLY_DAYS = 7  # Private Antworten nur bis 7 Tage nach dem Kommentar


def call(method, path, params=None, body=None):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    t = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if t:
        req.add_header("Authorization", "Bearer " + t)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            err = json.load(e).get("error", {})
        except Exception:
            err = {}
        sys.exit(f"Instagram-Fehler {e.code}: {err.get('message', e.reason)}")


def parse_time(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")


def fetch(days):
    me = call("GET", "/me", {"fields": "user_id,username"})
    now = dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(days=days)
    media = call("GET", "/me/media", {"fields": "id,caption,timestamp,permalink,comments_count", "limit": 25}).get("data", [])
    out = []
    for m in media:
        if not m.get("comments_count"):
            continue
        res = call("GET", f"/{m['id']}/comments", {"fields": "id,text,timestamp,username,from", "limit": 50})
        for c in res.get("data", []):
            at = parse_time(c["timestamp"])
            if at < since or c.get("username") == me.get("username"):
                continue
            out.append({
                "commentId": c["id"],
                "handle": c.get("username", ""),
                "text": c.get("text", ""),
                "at": at.isoformat(),
                "mediaId": m["id"],
                "permalink": m.get("permalink", ""),
                "caption": (m.get("caption") or "")[:200],
                "canReply": now - at < dt.timedelta(days=REPLY_DAYS),
            })
    json.dump({"account": me.get("username"), "fetchedAt": now.isoformat(), "comments": out},
              sys.stdout, ensure_ascii=False, indent=1)
    print()


def reply(comment_id, text):
    text = text.strip()
    if not text:
        sys.exit("Leere Nachricht, nichts gesendet.")
    res = call("POST", "/me/messages", body={"recipient": {"comment_id": comment_id}, "message": {"text": text}})
    print(json.dumps({"sent": True, "message_id": res.get("message_id")}))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--days", type=int, default=REPLY_DAYS)
    r = sub.add_parser("reply")
    r.add_argument("--comment", required=True)
    r.add_argument("--text-file", required=True)
    a = ap.parse_args()
    if a.cmd == "fetch":
        fetch(a.days)
    else:
        with open(a.text_file, encoding="utf-8") as fh:
            reply(a.comment, fh.read())


if __name__ == "__main__":
    main()
