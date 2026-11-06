# Video and subtitles

Distilled from Agent-Reach `references/video.md` at the pin in
`resources.toml`. Read-only: metadata, subtitles, and best-effort comments; no
downloads of paid or DRM content, no posting, and no login automation.

## YouTube

```bash
# Metadata
yt-dlp --dump-json "URL"

# Subtitles, without downloading the video
yt-dlp --write-sub --write-auto-sub --sub-lang "zh-Hans,zh,en" --skip-download -o "/tmp/%(id)s" "URL"
cat /tmp/VIDEO_ID.*.vtt

# Best-effort comments
yt-dlp --write-comments --skip-download --write-info-json \
  --extractor-args "youtube:max_comments=20" \
  -o "/tmp/%(id)s" "URL"

# Search
yt-dlp --dump-json "ytsearch5:query"
```

Manual captions are reliable. Auto-generated captions may repeat lines and
need cleanup. Comment extraction is best-effort (web scrape, not the Data
API); do not claim completeness.

### Subtitle retry chain

Stop as soon as real subtitle content exists.

1. Run the `--write-sub --write-auto-sub` command above.
2. On a bot check, an empty response, or no subtitle file, and if OpenCLI is
   connected, run `opencli youtube transcript "URL" -f yaml`.
3. If OpenCLI returns `Caption URL returned empty response`, retry at most
   three times; the signed caption URL expires.
4. If the video genuinely has no captions, report that. A transcription step is
   a separate owner decision: one named provider, no silent second provider.

## Bilibili

Never use `yt-dlp` for Bilibili; upstream reports a blanket 412. Use
`bili-cli` or OpenCLI.

```bash
# Video detail, search, hot, rank (bili-cli, read-only, no login)
bili video BVxxx
bili search "query" --type video -n 5
bili hot -n 10
bili rank -n 10

# Audio download and ASR-ready WAV
bili audio BVxxx

# Subtitles through OpenCLI (desktop Chrome session)
opencli bilibili subtitle BVxxx

# OpenCLI alternatives
opencli bilibili search "query" -f yaml
opencli bilibili video BVxxx -f yaml
```

Zero-config search fallback:

```bash
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
curl -s -c /tmp/bili_ck.txt -o /dev/null -A "$UA" "https://www.bilibili.com/"
curl -s -b /tmp/bili_ck.txt -A "$UA" -e "https://www.bilibili.com/" \
  "https://api.bilibili.com/x/web-interface/search/all/v2?keyword=QUERY&page=1"
```

`bili audio` writes media; keep it in `/tmp`. Transcription is not adopted as a
bundled route. If the owner asks for it, choose one named provider and record
the choice in the issue; never send the same audio to a second provider
without consent.

Success means a non-empty title, subtitle, comment body, or result list. An
exit code alone is not evidence.
