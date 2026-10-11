#!/usr/bin/env python3
"""Publish an episode to the Miami-Dade Vibe Check podcast feed on GitHub.

Usage (run in shell with credentials [{"provider":"github"}]):
  python3 publish.py --mp3 PATH --title "..." --description "..." [--date YYYY-MM-DD]
  python3 publish.py --init   # upload cover.jpg + empty feed if missing

Stateless: reads current feed.xml from the repo, adds the episode, keeps newest 60,
deletes MP3s that fall off, writes feed.xml back. Uses `apicall github`.
"""
import argparse, base64, datetime, email.utils, html, json, os, re, subprocess, sys

OWNER, REPO, BRANCH = "juanky-mdd-digest", "mdd-digest-feed", "main"
RAW = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}"
KEEP = 60
TITLE = "Miami-Dade Vibe Check"
DESC = ("A weekday rundown of west-central Miami-Dade (Westchester, Sweetwater, Kendall, Doral) "
        "and County Hall, with balanced coverage across outlets.")


def api(endpoint, **params):
    argv = ["github", endpoint] + [f"{k}={v}" for k, v in params.items() if v is not None]
    helper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "apicall_stdin.py")
    out = subprocess.run([sys.executable, helper], input=json.dumps(argv), capture_output=True, text=True)
    try:
        d = json.loads(out.stdout)
    except Exception:
        raise SystemExit(f"apicall {endpoint} bad output: {out.stdout[:500]} {out.stderr[:500]}")
    if isinstance(d, dict) and d.get("error"):
        return None, d
    return d, None


def get_file(path):
    d, err = api("contents_get", owner=OWNER, repo=REPO, path=path, ref=BRANCH)
    if err or not d:
        return None, None
    content = base64.b64decode(d.get("content", "")) if d.get("content") else b""
    return content, d.get("sha")


def put_file(path, data: bytes, message):
    _, sha = get_file(path)
    d, err = api("contents_put", owner=OWNER, repo=REPO, path=path, message=message,
                 content=base64.b64encode(data).decode(), sha=sha, branch=BRANCH)
    if err:
        raise SystemExit(f"upload {path} failed: {json.dumps(err)[:400]}")


def del_file(path, message):
    _, sha = get_file(path)
    if sha:
        api("contents_delete", owner=OWNER, repo=REPO, path=path, message=message, sha=sha, branch=BRANCH)


def duration(mp3):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp3],
                         capture_output=True, text=True).stdout.strip()
    s = int(float(out or 0))
    return f"{s//3600:02d}:{s%3600//60:02d}:{s%60:02d}"


def build_feed(items):
    now = email.utils.format_datetime(datetime.datetime.now(datetime.timezone.utc))
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">',
        '<channel>',
        f'<title>{TITLE}</title>', f'<link>https://github.com/{OWNER}/{REPO}</link>',
        f'<description>{html.escape(DESC)}</description>', '<language>en-us</language>',
        f'<lastBuildDate>{now}</lastBuildDate>',
        f'<itunes:author>Hark</itunes:author>', f'<itunes:image href="{RAW}/cover.jpg"/>',
        f'<image><url>{RAW}/cover.jpg</url><title>{TITLE}</title><link>https://github.com/{OWNER}/{REPO}</link></image>',
        '<itunes:explicit>false</itunes:explicit>', '<itunes:block>Yes</itunes:block>',
        '<itunes:category text="News"/>',
    ]
    parts += items
    parts += ['</channel>', '</rss>']
    return "\n".join(parts).encode()


def existing_items():
    data, _ = get_file("feed.xml")
    if not data:
        return []
    return re.findall(r"<item>.*?</item>", data.decode(), flags=re.S)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mp3"); ap.add_argument("--title"); ap.add_argument("--description", default="")
    ap.add_argument("--date"); ap.add_argument("--init", action="store_true")
    a = ap.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    if a.init:
        cover = os.path.join(here, "cover.jpg")
        if os.path.exists(cover) and not get_file("cover.jpg")[1]:
            put_file("cover.jpg", open(cover, "rb").read(), "Add cover art")
        if not get_file("feed.xml")[1]:
            put_file("feed.xml", build_feed([]), "Create feed")
        if not a.mp3:
            print(f"{RAW}/feed.xml"); return
    date = a.date or datetime.date.today().isoformat()
    name = os.path.basename(a.mp3)
    rpath = f"episodes/{name}"
    put_file(rpath, open(a.mp3, "rb").read(), f"Episode {date}")
    url = f"{RAW}/{rpath}"
    pub = email.utils.format_datetime(datetime.datetime.fromisoformat(date + "T08:00:00-04:00"))
    item = (f"<item><title>{html.escape(a.title)}</title>"
            f"<description>{html.escape(a.description)}</description>"
            f'<enclosure url="{url}" length="{os.path.getsize(a.mp3)}" type="audio/mpeg"/>'
            f'<guid isPermaLink="false">{rpath}</guid><pubDate>{pub}</pubDate>'
            f"<itunes:duration>{duration(a.mp3)}</itunes:duration></item>")
    items = [i for i in existing_items() if f">{rpath}</guid>" not in i]
    items = [item] + items
    keep, drop = items[:KEEP], items[KEEP:]
    put_file("feed.xml", build_feed(keep), f"Feed: add {date}")
    for d in drop:
        m = re.search(r"<guid[^>]*>(episodes/[^<]+)</guid>", d)
        if m:
            del_file(m.group(1), "Prune old episode")
    print(f"{RAW}/feed.xml")


if __name__ == "__main__":
    main()
