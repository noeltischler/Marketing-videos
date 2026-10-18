#!/usr/bin/env python3
"""Scout: Instagram-DMs abholen und freigegebene Antworten senden.

Nutzt die Instagram API mit Instagram-Login (graph.instagram.com).
Der Zugangsschlüssel kommt aus der Umgebungsvariable IG_ACCESS_TOKEN
und wird nie ausgegeben oder gespeichert.

  python3 scout_dm.py check                       # Konto prüfen
  python3 scout_dm.py fetch [--limit 20]          # Gespräche als JSON
  python3 scout_dm.py send --to IGSID --text-file antwort.txt
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
WINDOW_HOURS = 24  # Automatische Antworten nur bis 24 h nach der letzten Nachricht der Person


def token():
    t = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not t:
        sys.exit("IG_ACCESS_TOKEN fehlt in der Umgebung.")
    return t


def call(method, path, params=None, body=None):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token())
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
    # Instagram liefert z. B. 2026-10-18T16:54:54+0000
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")


def me():
    return call("GET", "/me", {"fields": "user_id,username"})


def fetch(limit):
    account = me()
    my_id = str(account.get("user_id") or account.get("id"))
    res = call("GET", "/me/conversations", {
        "platform": "instagram",
        "limit": limit,
        "fields": "id,updated_time,participants,messages.limit(15){id,created_time,from,to,message}",
    })
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for c in res.get("data", []):
        other = next((p for p in c.get("participants", {}).get("data", []) if str(p.get("id")) != my_id), None)
        if not other:
            continue
        msgs = []
        for m in reversed(c.get("messages", {}).get("data", [])):  # API liefert neueste zuerst
            msgs.append({
                "id": m["id"],
                "from_me": str(m.get("from", {}).get("id")) == my_id,
                "text": m.get("message", ""),
                "at": parse_time(m["created_time"]).isoformat(),
            })
        last_in = next((m for m in reversed(msgs) if not m["from_me"]), None)
        out.append({
            "convId": c["id"],
            "userId": str(other.get("id")),
            "handle": other.get("username", ""),
            "messages": msgs,
            "lastInAt": last_in["at"] if last_in else None,
            "lastInId": last_in["id"] if last_in else None,
            "waitingForUs": bool(msgs) and not msgs[-1]["from_me"],
            "windowOpen": bool(last_in) and now - dt.datetime.fromisoformat(last_in["at"]) < dt.timedelta(hours=WINDOW_HOURS),
        })
    json.dump({"account": account.get("username"), "fetchedAt": now.isoformat(), "conversations": out},
              sys.stdout, ensure_ascii=False, indent=1)
    print()


def send(to, text):
    text = text.strip()
    if not text:
        sys.exit("Leere Nachricht, nichts gesendet.")
    res = call("POST", "/me/messages", body={"recipient": {"id": to}, "message": {"text": text}})
    print(json.dumps({"sent": True, "message_id": res.get("message_id")}))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    f = sub.add_parser("fetch")
    f.add_argument("--limit", type=int, default=20)
    s = sub.add_parser("send")
    s.add_argument("--to", required=True)
    s.add_argument("--text-file", required=True)
    a = ap.parse_args()
    if a.cmd == "check":
        print(json.dumps(me(), ensure_ascii=False))
    elif a.cmd == "fetch":
        fetch(a.limit)
    else:
        with open(a.text_file, encoding="utf-8") as fh:
            send(a.to, fh.read())


if __name__ == "__main__":
    main()
