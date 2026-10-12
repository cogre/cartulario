# -*- coding: utf-8 -*-
"""
cartulario - send a video link to your own Telegram bot, find the file on your PC.
(A cartulary is the book where a household copied and kept its documents.)

  python cartulario.py              fetch the links you sent since last time, download them, exit
  python cartulario.py --watch      keep listening (leave the window open)
  python cartulario.py LINK [note]  download one link directly, without Telegram
  python cartulario.py --whoami     print the Telegram id of whoever messages the bot next (for setup)

Setup, once: create a bot with @BotFather, then put its token and your own Telegram id in a file
named .env next to this script (see .env.example). Only that id is obeyed, and only in a private chat.

Videos go to  videos/YYYY-MM/  and every one gets an entry in  videos/INDEX.txt :
when, where from, title, file, link and the note you typed with it.

Downloading is done by yt-dlp. This script never asks for or stores any site password.
Keep what you save for yourself: reposting other people's videos is a copyright and platform-rules matter.
"""
import json, os, re, subprocess, sys, time, urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_MB = 800                      # larger than this is probably not the short clip you meant to keep
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
URL = re.compile(r"https?://[^\s<>\"']+", re.I)


# ------------------------------------------------------------------ config
def load_env(path=None):
    out = {}
    try:
        with open(path or os.path.join(HERE, ".env"), encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def config():
    env = dict(load_env(), **{k: v for k, v in os.environ.items() if k.startswith("CARTULARIO_")})
    return {"token": env.get("CARTULARIO_BOT_TOKEN", ""), "owner": env.get("CARTULARIO_OWNER_ID", "").strip(),
            "folder": os.path.abspath(os.path.expanduser(env.get("CARTULARIO_FOLDER") or os.path.join(HERE, "videos")))}


# ------------------------------------------------------------------ text helpers
def links(text):
    """The http(s) addresses in a message, without trailing punctuation."""
    return [u.rstrip(").,;!?") for u in URL.findall(text or "")]


def note_of(text):
    return re.sub(r"\s+", " ", URL.sub(" ", text or "")).strip()[:300]


def origin(url):
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    host = re.sub(r"^(www|m|mobile|vm|vt)\.", "", host)
    return {"youtu.be": "youtube.com", "twitter.com": "x.com"}.get(host, host)


def short_error(text):
    """The last error line from yt-dlp, with the usual cases said plainly."""
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    last = next((l for l in reversed(lines) if "ERROR" in l), lines[-1] if lines else "yt-dlp gave no reason")
    last = re.sub(r"^ERROR:\s*", "", last)
    low = last.lower()
    if any(w in low for w in ("login", "log in", "sign in", "cookies", "private")):
        return "the site asked for a login, or the post is private: " + last[:160]
    if "unsupported url" in low:
        return "yt-dlp does not know this address: " + last[:160]
    if "max-filesize" in low:
        return "the video is larger than %d MB" % MAX_MB
    if "no video" in low:
        return "this post has no video: " + last[:160]
    return last[:220]


# ------------------------------------------------------------------ download
def download(url, folder, when=None):
    """Downloads one link. Returns (ok, title, path relative to folder, error)."""
    if not re.match(r"^https?://", url, re.I):
        return False, "", "", "not an http address"
    dest = os.path.join(folder, time.strftime("%Y-%m", time.localtime(when or time.time())))
    os.makedirs(dest, exist_ok=True)
    template = os.path.join(dest, "%(upload_date>%Y-%m-%d|undated)s %(uploader,channel|unknown).40s - %(title).70s [%(id)s].%(ext)s")
    cmd = [sys.executable, "-m", "yt_dlp", "--no-playlist", "--no-progress", "--windows-filenames", "--no-overwrites",
           "--max-filesize", "%dM" % MAX_MB, "--socket-timeout", "30", "--retries", "3",
           "-S", "res:1080,ext:mp4:m4a", "--merge-output-format", "mp4",
           "--print", "after_move:FILE=%(filepath)s", "--print", "after_move:TITLE=%(title)s", "--no-simulate",
           "-o", template, "--", url]                # a list and "--": the link never goes through a shell or reads as an option
    # Without this, on Windows yt-dlp answers in the system code page: a title with an accent comes back mangled
    # and the file "does not exist" under the name we were told.
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
                           creationflags=NO_WINDOW, env=env)
    except subprocess.TimeoutExpired:
        return False, "", "", "still downloading after 15 minutes"
    path = next((l[5:] for l in r.stdout.splitlines() if l.startswith("FILE=")), "")
    title = next((l[6:] for l in r.stdout.splitlines() if l.startswith("TITLE=")), "")
    if r.returncode == 0 and path and not os.path.exists(path):
        return False, title, "", "downloaded, but the file is not under the name yt-dlp reported; look in the month folder"
    if r.returncode != 0 or not path:
        return False, title, "", short_error(r.stderr)
    return True, title or os.path.basename(path), os.path.relpath(path, folder), ""


def record(folder, url, title, rel, note):
    index = os.path.join(folder, "INDEX.txt")
    new = not os.path.exists(index)
    with open(index, "a", encoding="utf-8", newline="\n") as f:
        if new:
            f.write("CARTULARIO - saved videos\nOne block each: when it was saved | where from | title, then the file, the link and your note.\n\n")
        f.write("%s | %s | %s\n  file: %s\n  link: %s\n%s\n" % (
            time.strftime("%Y-%m-%d %H:%M"), origin(url) or "-", title, rel, url, ("  note: %s\n" % note) if note else ""))


def save(url, note, folder, dl=download):
    """Download + record. Returns the line to tell the user."""
    ok, title, rel, err = dl(url, folder)
    if ok:
        record(folder, url, title, rel, note)
        return True, "Saved: %s\n%s" % (title, rel)
    return False, "Could not download (%s).\n%s\nSend the link again to retry." % (origin(url), err)


# ------------------------------------------------------------------ telegram
def api(token, method, **params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request("https://api.telegram.org/bot%s/%s" % (token, method), data=data)
    with urllib.request.urlopen(req, timeout=int(params.get("timeout", 0)) + 20) as r:
        out = json.loads(r.read().decode())
    if not out.get("ok"):
        raise RuntimeError(out.get("description") or "telegram said no")
    return out["result"]


def allowed(msg, owner):
    """Only the owner, and only in a private chat. Links posted in groups are ignored."""
    return bool(owner) and (msg.get("chat") or {}).get("type") == "private" and str((msg.get("from") or {}).get("id")) == str(owner)


def handle(msg, cfg, send, dl=download):
    """One incoming message. `send(text)` replies in the same chat."""
    if not allowed(msg, cfg["owner"]):
        return "ignored"
    text = msg.get("text") or msg.get("caption") or ""
    found = links(text)
    if not found:
        send("Send me a video link, with a line of your own if you like. It will be on your PC.")
        return "help"
    send("Downloading from %s..." % origin(found[0]))
    ok, reply = save(found[0], note_of(text), cfg["folder"], dl)
    send(reply)
    return "saved" if ok else "failed"


def _offset_file(folder):
    return os.path.join(folder, ".offset")


def poll_once(cfg, wait=0, call=api, dl=download, log=print):
    """Reads the messages Telegram kept for us, handles each, remembers where it stopped."""
    os.makedirs(cfg["folder"], exist_ok=True)
    try:
        with open(_offset_file(cfg["folder"])) as f:
            offset = int(f.read().strip() or 0)
    except (OSError, ValueError):
        offset = 0
    updates = call(cfg["token"], "getUpdates", offset=offset, timeout=wait, allowed_updates='["message"]')
    done = 0
    for u in updates:
        msg = u.get("message") or {}
        chat = (msg.get("chat") or {}).get("id")
        # the offset is written BEFORE the download: a link that crashes the script is not retried forever
        with open(_offset_file(cfg["folder"]), "w") as f:
            f.write(str(u["update_id"] + 1))
        result = handle(msg, cfg, lambda t: call(cfg["token"], "sendMessage", chat_id=chat, text=t, disable_web_page_preview="true"), dl)
        if result != "ignored":
            log("  %s  %s" % (time.strftime("%H:%M"), result))
            done += 1
    return done


def whoami(cfg, call=api):
    print("Send any message to your bot now. Waiting up to 60 seconds...")
    for u in call(cfg["token"], "getUpdates", timeout=60, allowed_updates='["message"]'):
        m = u.get("message") or {}
        print("  id %s  (%s)  chat type: %s" % ((m.get("from") or {}).get("id"), (m.get("from") or {}).get("first_name", ""), (m.get("chat") or {}).get("type")))
    print("Put your id in .env as CARTULARIO_OWNER_ID.")


def main(a):
    cfg = config()
    if a and a[0] in ("-h", "--help"):
        return print(__doc__)
    if a and re.match(r"^https?://", a[0], re.I):
        return print(save(a[0], " ".join(a[1:]), cfg["folder"])[1])
    if not cfg["token"]:
        return print("No bot token. Copy .env.example to .env and fill it in (see README).")
    if a and a[0] == "--whoami":
        return whoami(cfg)
    if not cfg["owner"]:
        return print("No owner id. Run:  python cartulario.py --whoami   and put the id in .env")
    if a and a[0] == "--watch":
        print("Listening. Videos go to %s\nCtrl+C to stop." % cfg["folder"])
        while True:
            try:
                poll_once(cfg, wait=50)
            except (urllib.error.URLError, RuntimeError, OSError) as e:
                print("  telegram unreachable (%s); trying again in 30 s" % type(e).__name__)
                time.sleep(30)
    n = poll_once(cfg)
    print("nothing new" if not n else "%d message(s) handled" % n)


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        print("\nstopped")
