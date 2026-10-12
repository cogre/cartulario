# -*- coding: utf-8 -*-
"""
cartulario - send a video link to your own Telegram bot, find the file on your PC.
(A cartulary is the book where a household copied and kept its documents.)

  python cartulario.py              fetch the links you sent since last time, download them, exit
  python cartulario.py --watch      keep listening (leave the window open)
  python cartulario.py LINK [note]  download one link directly, without Telegram
  python cartulario.py --whoami     print the Telegram id of whoever messages the bot next (for setup)
  python cartulario.py --page       rebuild videos/index.html from INDEX.txt

Setup, once: create a bot with @BotFather, then put its token and your own Telegram id in a file
named .env next to this script (see .env.example). Only that id is obeyed, and only in a private chat.

Videos go to  videos/YYYY-MM/  and every one gets an entry in  videos/INDEX.txt :
when, where from, title, file, link and the note you typed with it.
videos/index.html is rebuilt after every download: open it in a browser to search and watch what you saved.

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
        page(folder)
        return True, "Saved: %s\n%s" % (title, rel)
    return False, "Could not download (%s).\n%s\nSend the link again to retry." % (origin(url), err)



# ------------------------------------------------------------------ page
PAGE = r'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>cartulario</title>
<!-- Generated by cartulario.py from INDEX.txt. Do not edit: it is rewritten after every download.
     One self-contained file. It plays the videos straight from this folder; nothing is loaded from the internet. -->
<style>
:root{--bg:#f6f4ef;--card:#fbfaf7;--line:#e2ddd2;--txt:#1d1b17;--txt2:#5d584e;--txt3:#8c8678;--ac:#1f6f4a;--acbg:#e3efe7}
@media (prefers-color-scheme: dark){:root{--bg:#101210;--card:#161916;--line:#262b27;--txt:#e9ebe6;--txt2:#a3aaa1;--txt3:#6d756c;--ac:#5fd39a;--acbg:#1b2a22}}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);font:15px/1.55 "Segoe UI",system-ui,-apple-system,Roboto,sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:24px 16px 80px}
h1{font-size:20px;display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
h1 small{font-weight:400;font-size:12.5px;color:var(--txt3)}
#q{width:100%;margin-top:14px;padding:10px 12px;background:var(--card);border:1px solid var(--line);border-radius:8px;font:inherit;color:inherit}
#q:focus{outline:none;border-color:var(--ac)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 4px}
.chips button{background:none;border:1px solid var(--line);border-radius:999px;padding:2px 10px;font:inherit;font-size:12.5px;color:var(--txt2);cursor:pointer}
.chips button b{font-weight:400;color:var(--txt3);margin-left:4px}
.chips button.on{background:var(--acbg);border-color:var(--ac);color:var(--txt)}
.count{font-size:12px;color:var(--txt3);margin:8px 0 12px}
.item{background:var(--card);border:1px solid var(--line);border-radius:10px;margin-bottom:10px;overflow:hidden}
.head{display:block;width:100%;text-align:left;background:none;border:0;padding:12px 14px;cursor:pointer;font:inherit;color:inherit}
.head .t{font-weight:600;line-height:1.35}
.head .m{font-size:12px;color:var(--txt3);margin-top:3px}
.head .n{font-size:13.5px;color:var(--txt2);margin-top:5px}
.body{padding:0 14px 14px}
video{display:block;width:100%;max-height:72vh;background:#000;border-radius:8px}
.body .f{font-size:12px;color:var(--txt3);margin-top:8px;word-break:break-all}
.body a{color:var(--ac);word-break:break-all}
.empty{color:var(--txt3);padding:40px 0}
</style></head><body><div class="wrap">
<h1>cartulario <small id="when"></small></h1>
<input id="q" type="search" placeholder="search title, note or site" autocomplete="off">
<div class="chips" id="chips"></div>
<div class="count" id="count"></div>
<div id="list"></div>
</div>
<script>
const D = /*__DATA__*/{"items":[],"made":""};
const $ = i => document.getElementById(i);
const esc = t => String(t == null ? "" : t).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
const plain = t => t.normalize("NFD").replace(/[^\x00-\x7f]/g, c => c.charCodeAt(0) >= 0x300 && c.charCodeAt(0) <= 0x36f ? "" : c).toLowerCase();
const src = f => f.split(/[\\/]/).map(encodeURIComponent).join("/");          // path relative to this page, safe for any file name
const N = D.items.map((x, i) => Object.assign({i: i, find: plain([x.title, x.note, x.origin, x.file].join(" "))}, x));
let site = "", terms = [], open = -1;
function shown(){ return N.filter(x => (!site || x.origin === site) && terms.every(t => x.find.indexOf(t) >= 0)); }
function draw(){
  const per = {}; N.filter(x => terms.every(t => x.find.indexOf(t) >= 0)).forEach(x => per[x.origin] = (per[x.origin] || 0) + 1);
  const sites = [...new Set(N.map(x => x.origin))].sort();
  $("chips").innerHTML = sites.length < 2 ? "" : '<button data-s="" class="' + (site ? "" : "on") + '">all</button>' +
    sites.map(s => '<button data-s="' + esc(s) + '" class="' + (site === s ? "on" : "") + '">' + esc(s) + '<b>' + (per[s] || 0) + '</b></button>').join("");
  const f = shown();
  $("count").textContent = f.length + (f.length === 1 ? " video" : " videos") + (f.length < N.length ? " of " + N.length : "");
  $("list").innerHTML = f.map(x => '<div class="item"><button class="head" data-i="' + x.i + '"><div class="t">' + esc(x.title) + '</div><div class="m">' +
      esc(x.when) + " · " + esc(x.origin) + '</div>' + (x.note ? '<div class="n">' + esc(x.note) + '</div>' : '') + '</button>' +
      (x.i === open ? '<div class="body"><video controls preload="metadata" src="' + esc(src(x.file)) + '"></video><div class="f">' + esc(x.file) +
        '</div><div class="f"><a href="' + esc(x.link) + '" target="_blank" rel="noopener noreferrer">' + esc(x.link) + '</a></div></div>' : '') + '</div>').join("")
    || '<div class="empty">' + (N.length ? "Nothing matches." : "Nothing saved yet. Send a link to your bot and run cartulario.") + '</div>';
}
$("list").addEventListener("click", ev => { const b = ev.target.closest(".head"); if(b){ const i = +b.dataset.i; open = open === i ? -1 : i; draw(); } });
$("chips").addEventListener("click", ev => { const b = ev.target.closest("button"); if(b){ site = b.dataset.s; draw(); } });
$("q").addEventListener("input", function(){ terms = plain(this.value).split(/\s+/).filter(t => t.length > 1); draw(); });
$("when").textContent = "updated " + D.made;
draw();
</script></body></html>
'''


def entries(folder):
    """INDEX.txt read back: [{when, origin, title, file, link, note}], newest first."""
    out, cur = [], None
    try:
        with open(os.path.join(folder, "INDEX.txt"), encoding="utf-8") as f:
            linhas = f.read().split("\n")
    except OSError:
        return []
    for l in linhas:
        m = re.match(r"^(\d{4}-\d\d-\d\d \d\d:\d\d) \| (.*?) \| (.*)$", l)
        if m:
            cur = {"when": m.group(1), "origin": m.group(2), "title": m.group(3), "file": "", "link": "", "note": ""}
            out.append(cur)
        elif cur is not None:
            for chave, rotulo in (("file", "file"), ("link", "link"), ("note", "note")):
                if l.startswith("  " + rotulo + ": "):
                    cur[chave] = l[len(rotulo) + 4:]
    return [e for e in reversed(out) if e["file"]]


def page(folder):
    """Rewrites index.html: every saved video in one page, with search and a player. Returns how many."""
    items = entries(folder)
    dados = json.dumps({"items": items, "made": time.strftime("%Y-%m-%d %H:%M")}, ensure_ascii=False).replace("</", "<\\/")
    with open(os.path.join(folder, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(PAGE.replace('/*__DATA__*/{"items":[],"made":""}', dados))
    return len(items)


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
    if a and a[0] == "--page":
        os.makedirs(cfg["folder"], exist_ok=True)
        return print("%d video(s) -> %s" % (page(cfg["folder"]), os.path.join(cfg["folder"], "index.html")))
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
