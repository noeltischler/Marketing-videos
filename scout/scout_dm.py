#!/usr/bin/env python3
"""Leni (früher Scout): Instagram- und Messenger-DMs abholen und freigegebene Antworten senden.

Instagram: Instagram API mit Instagram-Login (graph.instagram.com), Schlüssel IG_ACCESS_TOKEN.
Messenger: Messenger-Plattform der Facebook-Seite (graph.facebook.com), Seiten-Token FB_PAGE_TOKEN.
Die Schlüssel kommen als Netzwerk-Secret (vom Proxy eingesetzt) oder aus der gleichnamigen
Umgebungsvariable und werden nie ausgegeben oder gespeichert.

  python3 scout_dm.py [--platform messenger] check                 # Konto prüfen
  python3 scout_dm.py [--platform messenger] fetch [--limit 50]    # Gespräche als JSON
  python3 scout_dm.py [--platform messenger] send --to ID --text-file antwort.txt
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

PLATFORMS = {
    "instagram": {"api": "https://graph.instagram.com/v25.0", "env": "IG_ACCESS_TOKEN", "name": "Instagram"},
    "messenger": {"api": "https://graph.facebook.com/v25.0", "env": "FB_PAGE_TOKEN", "name": "Facebook"},
}
PLATFORM = "instagram"
WINDOW_HOURS = 24  # Automatische Antworten nur bis 24 h nach der letzten Nachricht der Person


def token():
    # Leer, wenn der Schlüssel als Netzwerk-Secret hinterlegt ist: dann setzt der Proxy den Header
    return os.environ.get(PLATFORMS[PLATFORM]["env"], "").strip()


def call(method, path, params=None, body=None):
    url = PLATFORMS[PLATFORM]["api"] + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    t = token()
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
        sys.exit(f"{PLATFORMS[PLATFORM]['name']}-Fehler {e.code}: {err.get('message', e.reason)}")


def parse_time(s):
    # Instagram und Facebook liefern z. B. 2026-10-18T16:54:54+0000
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")


def me():
    if PLATFORM == "messenger":
        return call("GET", "/me", {"fields": "id,name"})  # die Facebook-Seite
    return call("GET", "/me", {"fields": "user_id,username"})


def fetch(limit):
    account = me()
    my_id = str(account.get("user_id") or account.get("id"))
    res = call("GET", "/me/conversations", {
        "platform": PLATFORM,
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
                "text": m.get("message") or "[Anhang, Sticker oder Beitrag]",
                "at": parse_time(m["created_time"]).isoformat(),
            })
        last_in = next((m for m in reversed(msgs) if not m["from_me"]), None)
        out.append({
            "convId": c["id"],
            "userId": str(other.get("id")),
            "platform": PLATFORM,
            "handle": other.get("username") or other.get("name", ""),
            "messages": msgs,
            "lastInAt": last_in["at"] if last_in else None,
            "lastInId": last_in["id"] if last_in else None,
            "waitingForUs": bool(msgs) and not msgs[-1]["from_me"],
            "windowOpen": bool(last_in) and now - dt.datetime.fromisoformat(last_in["at"]) < dt.timedelta(hours=WINDOW_HOURS),
        })
    json.dump({"platform": PLATFORM, "account": account.get("username") or account.get("name"), "fetchedAt": now.isoformat(), "conversations": out},
              sys.stdout, ensure_ascii=False, indent=1)
    print()


def send(to, text):
    text = text.strip()
    if not text:
        sys.exit("Leere Nachricht, nichts gesendet.")
    body = {"recipient": {"id": to}, "message": {"text": text}}
    if PLATFORM == "messenger":
        body["messaging_type"] = "RESPONSE"  # Antwort im 24-h-Fenster
    res = call("POST", "/me/messages", body=body)
    print(json.dumps({"sent": True, "message_id": res.get("message_id")}))


def main():
    global PLATFORM
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", choices=sorted(PLATFORMS), default="instagram")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    f = sub.add_parser("fetch")
    f.add_argument("--limit", type=int, default=50)
    s = sub.add_parser("send")
    s.add_argument("--to", required=True)
    s.add_argument("--text-file", required=True)
    a = ap.parse_args()
    PLATFORM = a.platform
    if a.cmd == "check":
        print(json.dumps(me(), ensure_ascii=False))
    elif a.cmd == "fetch":
        fetch(a.limit)
    else:
        with open(a.text_file, encoding="utf-8") as fh:
            send(a.to, fh.read())


if __name__ == "__main__":
    main()
