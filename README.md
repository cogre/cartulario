# cartulario

Send a video link to your own Telegram bot. Find the file on your PC.

A *cartulary* is the book where a household copied and kept its documents.

One file. It talks to Telegram with the standard library and downloads with
[yt-dlp](https://github.com/yt-dlp/yt-dlp). No server, no account with us, nothing in the cloud:
the bot is yours and the videos land on your disk.

## Why

Saving a video from a phone used to take me four steps: copy the link, paste it into an online
converter, save to the phone, send it to the PC. Now it is one: share the link to a chat.

Telegram keeps messages for a bot for about a day, so the PC does not need to be on when you send
the link. Next time you run the script, it picks up everything you sent.

## Setup (once, about five minutes)

Requires Python 3.9 or newer. [FFmpeg](https://ffmpeg.org) is needed for sites that deliver video
and audio separately.

```
pip install yt-dlp
```

1. In Telegram, open **@BotFather**, send `/newbot` and follow it. You get a token.
2. Copy `.env.example` to `.env` and paste the token after `CARTULARIO_BOT_TOKEN=`.
3. Find your own Telegram id:

   ```
   python cartulario.py --whoami
   ```

   Send any message to your new bot; the script prints your id. Put it after `CARTULARIO_OWNER_ID=`.

The token is a password for your bot. It stays in `.env`, which git ignores. Do not paste it
anywhere else.

## Use

Send a link to your bot, in the private chat. Add a line of your own if you want to remember why
you kept it.

Then, on the PC:

```
python cartulario.py            # fetch what you sent, download, exit
python cartulario.py --watch    # keep listening
```

On Windows you can double-click `cartulario.bat` instead.

The bot answers in the chat: saved, or why not.

Without Telegram:

```
python cartulario.py https://example.com/some-video "why I kept it"
```

## Where things go

```
videos/
  2026-10/
    2026-10-11 Author - Title of the video [id].mp4
  INDEX.txt
```

`INDEX.txt` is plain text, one block per video: when it was saved, where from, title, file, link
and your note. Years from now it still says where each file came from, even if the link is dead.

Set `CARTULARIO_FOLDER` in `.env` to use another folder.

## Who the bot obeys

Only the id in `CARTULARIO_OWNER_ID`, and only in a private chat. Messages from anyone else, and
links posted in groups, are ignored without an answer. With no owner configured, it obeys nobody.

The link is handed to yt-dlp as a plain argument after `--`. It never passes through a shell and
cannot be read as an option.

## When a download fails

- **"asked for a login, or the post is private"**: the site only shows it to logged-in users.
  Public posts usually work. This script never handles your password; see yt-dlp's documentation
  on cookies if you need it.
- **"yt-dlp does not know this address"**: the site is not supported.
- **A site that worked yesterday stops working**: sites change constantly. Update yt-dlp:
  `pip install -U yt-dlp`.
- **Larger than 800 MB**: the limit is a constant at the top of the script.

## What it does not do

- Run by itself. Nothing is installed as a service; it works when you run it.
- Send the video back to your phone.
- Download playlists or whole profiles. One link, one video.
- Retry failed links on its own. Send the link again.

## A note on use

This is for keeping things you want to study or remember. Reposting other people's videos is a
matter of copyright and of each platform's rules, and this tool does not change that.

## Tests

```
python -m unittest discover -s tests
```

They run offline, with a fake Telegram and a fake downloader.

## License

MIT
