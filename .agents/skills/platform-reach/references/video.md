# Video: YouTube, Bilibili

## YouTube (yt-dlp)

```bash
yt-dlp --dump-json "URL"                       # metadata
yt-dlp --dump-json "ytsearch5:query"           # search, 5 results

# Subtitles only, no video download
yt-dlp --write-sub --write-auto-sub --sub-lang "en,zh-Hans,zh" \
  --skip-download -o "/tmp/%(id)s" "URL"
cat /tmp/VIDEO_ID.*.vtt

# Comments, best effort (scraped, not the Data API; some go missing)
yt-dlp --write-comments --skip-download --write-info-json \
  --extractor-args "youtube:max_comments=20" -o "/tmp/%(id)s" "URL"
# They land in the .info.json "comments" field.
```

Uploaded subtitles are reliable. Auto-generated ones repeat lines, so remove
the duplicates before quoting them.

**Subtitle fallback chain.** Stop at the first non-empty transcript:

1. Run the `yt-dlp` subtitle command above.
2. If you get a bot check, an empty response or no subtitle file, and OpenCLI
   is connected: `opencli youtube transcript "URL" -f yaml`.
3. If OpenCLI says `Caption URL returned empty response`, retry up to 3
   times. Caption URLs expire, and an empty response does not mean the
   video has no captions.
4. If there are still no captions, transcribe the audio
   (see [Transcription](#transcription)).

## Bilibili

**Do not use yt-dlp on Bilibili.** The site blocks it with HTTP 412.

```bash
# bili-cli (pipx package bilibili-cli): read-only, no login
bili video BVxxx                  # title, uploader, duration, stats, subtitle availability
bili search "query" --type video -n 5
bili hot -n 10
bili rank -n 10
bili audio BVxxx                  # audio as ASR-ready WAV, for transcription

# Subtitles with timestamps (OpenCLI, desktop Chrome)
opencli bilibili subtitle BVxxx
```

Zero-install search, used when neither CLI is available:

```bash
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
curl -s -c /tmp/bili_ck.txt -o /dev/null -A "$UA" "https://www.bilibili.com/"
curl -s -b /tmp/bili_ck.txt -A "$UA" -e "https://www.bilibili.com/" \
  "https://api.bilibili.com/x/web-interface/search/all/v2?keyword=QUERY&page=1"
```

That cookie jar is an anonymous visitor cookie for this one request. Delete
it afterwards.

## Transcription

Use this when a video or podcast has no subtitles. Transcribe only a public
URL or a local audio file.

```bash
# 1. Audio only (yt-dlp -x needs ffmpeg); for Bilibili use `bili audio BVxxx`
yt-dlp -x --audio-format mp3 -o "/tmp/%(id)s.%(ext)s" "URL"

# 2. Whisper-compatible API (Groq shown; OpenAI uses api.openai.com/v1 and whisper-1).
#    Files over the provider's size limit must be split first (ffmpeg -f segment).
curl -s https://api.groq.com/openai/v1/audio/transcriptions \
  -H "Authorization: Bearer $GROQ_API_KEY" \
  -F model=whisper-large-v3 -F file=@/tmp/VIDEO_ID.mp3
```

The key comes from the user's environment and is never echoed.

This uploads the audio to that provider. Tell the user which provider gets
it. Never fall back to a second provider without their consent, because it
can cost money and shares the content again.
