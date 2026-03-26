import argparse
import asyncio
import sys
from playwright.async_api import async_playwright

async def extract_html_source(url: str, output_file: str = "extracted_source.html"):
    """
    Launch a headless Chromium browser, navigate to the target URL,
    wait for JavaScript rendering (networkidle), and save the HTML.
    """
    print(f"🌍 Navigating to: {url}...")
    try:
        async with async_playwright() as p:
            # Launch in headless mode
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                # Ignore HTTPS errors sometimes found on test instances
                ignore_https_errors=True
            )
            page = await context.new_page()
            
            # Navigate and wait until network traffic has halted
            # This ensures all async JS fetches and React/Vue/Angular rendering is complete
            response = await page.goto(url, wait_until="networkidle", timeout=30000)
            
            # Basic validation of response state
            if not response or not response.ok:
                status = response.status if response else 'Unknown'
                print(f"⚠️ Warning: Received HTTP {status} from the server but attempting HTML extraction anyway.")
            
            # 1. Extract the standard fully hydrated DOM structure
            standard_content = await page.content()
            
            # 3. Extract purely evaluated DOM state directly via JavaScript
            evaluated_content = await page.evaluate("() => document.documentElement.outerHTML")
            
            # Combine them to guarantee no dynamic locators are skipped
            combined_content = (
                "<!-- [[ STANDARD PAGE.CONTENT() ]] -->\n" 
                + standard_content 
                + "\n\n<!-- [[ EVALUATED outerHTML ]] -->\n" 
                + evaluated_content
            )
            
            # Safely write to disk with enforced UTF-8
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(combined_content)
                
            char_count = len(combined_content)
            
            # Confirmation & Character Count
            print(f"✅ Success! Captured {char_count:,} characters of rendered HTML.")
            print(f"📁 Source saved to: {output_file}")
            
            # Clean up
            await browser.close()
            
    except Exception as e:
        print(f"\n❌ Error capturing source for {url}:\n   {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="Extract fully JS-rendered HTML source from a URL for locator parsing."
    )
    parser.add_argument(
        "url", 
        help="The target URL to extract HTML from (e.g. https://example.com)"
    )
    parser.add_argument(
        "-o", "--output", 
        default="extracted_source.html", 
        help="Target output file name (default: extracted_source.html)"
    )
    
    args = parser.parse_args()
    
    # URL formatting
    target_url = args.url
    if not target_url.startswith("http://") and not target_url.startswith("https://"):
        target_url = "https://" + target_url
        
    # Execute the asynchronous crawler
    asyncio.run(extract_html_source(target_url, args.output))

if __name__ == "__main__":
    main()
