# Video downloader app mockup
_Exported on 7/29/2026 at 23:47:17 GMT+3 from Cursor (3.13.25)_

---

**User**

Create a mockup for this video downloader app. The flow is like this: user pastes a URL, we get metadata for this URL and available formats. The UI should present options to download audio, video-only or video with audio; select format, quality, show a thumbnail. It should communicate the status clearly (downloading, errors, warnings, etc). Advanced options could include downloading a playlist and downloading from file (batch). Also, an option to select output directory. Sane defaults.

---

**Cursor**

Reviewing the app and canvas skill, then building an interactive UI mockup for the downloader flow.


Checking the canvas SDK for available components and any existing canvases.


Creating an interactive canvas mockup you can open beside the chat to explore the full download flow and UI states.


I've built an interactive UI mockup as a **Cursor Canvas** — a live React panel you can open beside this chat to click through the flow. Open it here: [ytdl-ui mockup](C:\Users\zaych\.cursor\projects\c-Users-zaych-Source-ytdl-ui\canvases\ytdl-ui-mockup.canvas.tsx).

## Flow (3 steps)

1. **Source URL** — Paste URL → **Fetch info** (disabled while busy; Enter supported in the real app)
2. **Media** — Thumbnail + title/channel/duration; pick **Video+audio** (default), **Video only**, or **Audio only**; **Quality** and **Container/codec** update per type
3. **Output** — Folder path with **Browse** (default: `Downloads`)

## Status & feedback

- **Fetching** — info callout while metadata loads
- **Ready** — neutral callout + monospace format list (sample `-F` output)
- **Downloading** — progress bar with size readout and destination line
- **Done** — success callout
- **Error** — danger callout (toggle **Demo: simulate 429 error** under Advanced to preview rate-limit handling)

## Advanced options (collapsed by default)

- Download entire **playlist**
- **Batch from file** (.txt, one URL per line)
- **Subtitles** toggle
- 429 error demo toggle for design review

## Sane defaults

| Setting | Default |
|---|---|
| Media type | Video + audio |
| Quality | Best available |
| Format | MP4 |
| Output | User Downloads folder |
| Filename | yt-dlp `%(title)s.%(ext)s` |

## How to try it

1. Open the canvas link above
2. Click **Fetch info** (URL is pre-filled)
3. Switch media types and quality/format
4. Click **Download** to simulate progress
5. Expand **Advanced options** and toggle the 429 demo, then **Reset** and fetch again

This is design-only — no yt-dlp calls. It maps to your P2–P4 tasks: format selection, output folder, thumbnails, status panel, playlist/batch.

If you want next steps, I can implement this layout in Tkinter (`main.py`) or refine the mockup (e.g. playlist queue UI, format table instead of dropdowns).

---

**User**

Get rid of "Step X" labels. Add ability to edit raw cmd paramers in advanced section. Status is collapsible (collapsed by default).

---

**Cursor**

Updating the canvas mockup: removing step labels, adding editable raw command arguments in Advanced, and making Status collapsible by default.


Updated the mockup: [ytdl-ui mockup](C:\Users\zaych\.cursor\projects\c-Users-zaych-Source-ytdl-ui\canvases\ytdl-ui-mockup.canvas.tsx)

**Removed** — "Step 1/2/3" labels from card headers.

**Advanced → yt-dlp arguments** — Editable monospace textarea for raw flags (before the URL). **Sync from UI** rebuilds args from current media type, quality, format, output path, playlist, and subtitle settings. A preview line shows the full command: `yt-dlp <args> <url>`.

**Status** — Collapsible card, collapsed by default. The header shows a trailing hint when something is active (`Working…`, `Error`, `Complete`) so you can spot state without expanding.

---

**User**

Now how about we save this as a detailed spec in a requirement style in an .md file?

