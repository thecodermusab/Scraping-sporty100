#!/usr/bin/env python3
"""
Sporty100 Stream Scraper
Flow: sporty100.com matches -> click match -> "Go to Streamly" -> scdn.monster stream links
"""

import json
import time
import logging
from datetime import datetime
from typing import List, Dict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_driver(headless=True):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    try:
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        options = Options()
        if headless:
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        logger.info("Using webdriver-manager ChromeDriver")
        return driver
    except Exception as e:
        logger.warning(f"webdriver-manager failed ({e}), using system ChromeDriver")
        options = Options()
        if headless:
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        return webdriver.Chrome(options=options)


_debug_saved = False

def extract_stream_links(driver) -> List[str]:
    """Extract only stream links from the scdn.monster page"""
    global _debug_saved
    from bs4 import BeautifulSoup
    from selenium.webdriver.common.by import By

    # Save the first scdn.monster page for inspection
    if not _debug_saved:
        with open('debug_scdn_page.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        logger.info("Saved debug_scdn_page.html (first stream page snapshot)")
        _debug_saved = True

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    links = []

    # 1. All iframes — these are almost always the embedded stream players
    for el in driver.find_elements(By.TAG_NAME, 'iframe'):
        try:
            src = el.get_attribute('src') or ''
            if src and src != 'about:blank' and src not in links:
                links.append(src)
        except Exception:
            continue

    for el in soup.find_all('iframe', src=True):
        src = el['src'].strip()
        if src and src != 'about:blank' and src not in links:
            links.append(src)

    # 2. Video / source tags (direct m3u8 or mp4)
    for tag, attr in [('video', 'src'), ('source', 'src')]:
        for el in soup.find_all(tag, **{attr: True}):
            src = el[attr].strip()
            if src and src not in links:
                links.append(src)

    # 3. Any <a> or data attribute containing stream keywords
    stream_keywords = ['m3u8', '.ts', 'stream', 'live', 'play', 'embed', 'player']
    skip_domains = ['sporty100.com', 'google', 'facebook', 'twitter', 'instagram',
                    'about-us', 'privacy', 'contact', 'terms']

    for el in soup.find_all('a', href=True):
        href = el['href'].strip()
        if not href or href.startswith('#') or href.startswith('javascript:'):
            continue
        if any(d in href for d in skip_domains):
            continue
        if any(k in href.lower() for k in stream_keywords):
            if href not in links:
                links.append(href)

    return links


OUTPUT_FILE = f"sporty100_streams_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

def save_results(results):
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved {len(results)} matches to {OUTPUT_FILE}")


def scrape_sporty100(headless=True) -> List[Dict]:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    results = []
    driver = get_driver(headless=headless)
    wait = WebDriverWait(driver, 15)

    try:
        # ── STEP 1: Load sporty100.com and apply Live filter ─────────────────
        logger.info("Loading sporty100.com...")
        driver.get("https://sporty100.com/")
        time.sleep(5)

        # Click the "Live" filter button so only live matches are shown
        live_clicked = False
        for btn in driver.find_elements(By.TAG_NAME, 'button'):
            try:
                if btn.text.strip().lower() in ('live', 'live now'):
                    driver.execute_script("arguments[0].click();", btn)
                    logger.info("Clicked Live filter")
                    time.sleep(3)
                    live_clicked = True
                    break
            except Exception:
                continue

        if not live_clicked:
            # Fallback: look inside any element with role="tab" or similar
            for el in driver.find_elements(By.CSS_SELECTOR, '[role="tab"], [role="button"]'):
                try:
                    if el.text.strip().lower() in ('live', 'live now'):
                        driver.execute_script("arguments[0].click();", el)
                        logger.info("Clicked Live filter (tab/button fallback)")
                        time.sleep(3)
                        live_clicked = True
                        break
                except Exception:
                    continue

        if not live_clicked:
            logger.warning("Could not find Live filter button — scraping all matches instead")

        home_url = driver.current_url

        # Match cards are div[role="button"] with aria-label="View details for match: X vs Y"
        match_cards = driver.find_elements(
            By.CSS_SELECTOR, 'div[role="button"][aria-label^="View details for match:"]'
        )

        if not match_cards:
            logger.warning("No match cards found. Saving debug snapshot...")
            with open('sporty100_debug.html', 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            logger.info("Saved sporty100_debug.html")
            return []

        # Collect match names from aria-label before clicking anything
        match_names = []
        for card in match_cards:
            try:
                label = card.get_attribute('aria-label') or ''
                # aria-label = "View details for match: Chelsea vs Hull"
                name = label.replace('View details for match:', '').strip()
                if name:
                    match_names.append(name)
            except Exception:
                continue

        logger.info(f"Found {len(match_names)} matches: {match_names[:5]}...")

        # ── STEP 2: Click each match card, find "Go to Streamly" ────────────
        for i, match_name in enumerate(match_names):
            logger.info(f"[{i+1}/{len(match_names)}] Match: {match_name}")

            try:
                # Re-fetch cards each time (DOM may re-render after navigation)
                driver.get(home_url)
                time.sleep(3)

                cards = driver.find_elements(
                    By.CSS_SELECTOR, 'div[role="button"][aria-label^="View details for match:"]'
                )

                # Find the card for this match
                target_card = None
                for card in cards:
                    label = card.get_attribute('aria-label') or ''
                    if match_name in label:
                        target_card = card
                        break

                if not target_card:
                    logger.warning(f"  Could not re-find card for: {match_name}")
                    continue

                # Click the match card
                driver.execute_script("arguments[0].click();", target_card)
                time.sleep(4)

                match_page_url = driver.current_url
                logger.info(f"  Match page: {match_page_url}")

                # Find "Go to Streamly" button (it's a <button>, not <a> — JS navigation)
                streamly_btn = None
                for btn in driver.find_elements(By.CSS_SELECTOR, 'button[data-slot="button"]'):
                    try:
                        if 'streamly' in btn.text.strip().lower():
                            streamly_btn = btn
                            break
                    except Exception:
                        continue

                if not streamly_btn:
                    logger.info(f"  No 'Go to Streamly' button for: {match_name} (match has no stream)")
                    continue

                # Click the button and wait for navigation to scdn.monster
                current_url_before = driver.current_url
                driver.execute_script("arguments[0].click();", streamly_btn)
                time.sleep(4)

                # The button may open a new tab or navigate current tab
                if len(driver.window_handles) > 1:
                    driver.switch_to.window(driver.window_handles[-1])
                    time.sleep(3)

                streamly_url = driver.current_url

                if streamly_url == current_url_before:
                    logger.warning(f"  URL did not change after clicking 'Go to Streamly'")
                    continue

                logger.info(f"  Streamly URL: {streamly_url}")

                # ── STEP 3: Extract stream links from scdn.monster page ───────
                time.sleep(2)  # extra wait for stream page to fully load

                stream_links = extract_stream_links(driver)
                logger.info(f"  Extracted {len(stream_links)} links")

                results.append({
                    'match': match_name,
                    'match_page_url': match_page_url,
                    'streamly_url': streamly_url,
                    'stream_links': stream_links,
                    'total_links': len(stream_links),
                    'scraped_at': datetime.now().isoformat(),
                })

                # Save after every match so stopping early doesn't lose data
                save_results(results)

                # Close any extra tabs opened by the button click
                while len(driver.window_handles) > 1:
                    driver.switch_to.window(driver.window_handles[-1])
                    driver.close()
                driver.switch_to.window(driver.window_handles[0])

            except Exception as e:
                logger.error(f"  Error processing {match_name}: {e}")
                continue

    finally:
        if results:
            save_results(results)
        driver.quit()

    return results


def main():
    import sys

    headless = '--visible' not in sys.argv

    print("\n" + "="*60)
    print("  SPORTY100 STREAM SCRAPER")
    print("="*60)
    print(f"  Mode: {'headless' if headless else 'visible browser'}")
    if headless:
        print("  Tip: use --visible to watch the browser")
    print()

    results = scrape_sporty100(headless=headless)

    if not results:
        print("\nNo results scraped.")
        print("If debug_*.html files were created, share them so I can fix the selectors.")
        return

    # Print summary
    print(f"\nScraped {len(results)} matches:\n")
    for r in results:
        print(f"  {r['match']}")
        print(f"    Streamly: {r['streamly_url']}")
        print(f"    Links found: {r['total_links']}")
        for link in r['stream_links'][:5]:
            print(f"      - {link}")
        if r['total_links'] > 5:
            print(f"      ... and {r['total_links'] - 5} more")
        print()

    # Save JSON
    filename = f"sporty100_streams_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Saved to: {filename}")


if __name__ == '__main__':
    main()
