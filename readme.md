# Sporty100 Stream Scraper

## Setup (do this first)

**1. Make sure Python and Chrome are installed on your computer.**

**2. Install the required packages:**
```
pip install -r requirements.txt
```

That's it — you're ready to run it.

---

## What it does

Visits **sporty100.com**, finds all live sports matches, and collects the video stream links for each one.

**Steps it follows automatically:**
1. Opens sporty100.com and lists all matches
2. Clicks each match to open its page
3. Clicks the "Go to Streamly" button
4. Grabs all stream links from the page (iframes, video URLs, m3u8 links)
5. Saves everything to a JSON file

## Requirements

```
pip install selenium webdriver-manager beautifulsoup4
```

Chrome browser must be installed.

## How to run

**Normal (no browser window):**
```
python3 sporty100_scraper.py
```

**Watch the browser while it runs:**
```
python3 sporty100_scraper.py --visible
```

## Output

Creates a JSON file like `sporty100_streams_20250214_153000.json` with each match name, its page URL, and all stream links found.

> If no matches are found, it saves a `sporty100_debug.html` file you can inspect to fix the issue.
