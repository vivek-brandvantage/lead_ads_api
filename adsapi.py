import re
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from playwright.async_api import async_playwright, TimeoutError
import uvicorn

app = FastAPI(title="Google Ads Transparency Checker")

# add a middleware here 

class AdsRequest(BaseModel):
    domain: str
    # Defaulting region to AU as requested
    region: str = "AU"

@app.post("/check_ads_status")
async def check_ads_status(req: AdsRequest):
    url = f"https://adstransparency.google.com/?domain={req.domain}&region={req.region}"
    
    async with async_playwright() as p:
        try:
            # Launch chromium in headless mode
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Go to the URL and wait until network is mostly idle
            await page.goto(url, wait_until='networkidle')
            
            # Locate the '.ads-count' element
            locator = page.locator('.ads-count').first
            
            # Wait up to 15 seconds for the angular app to fetch api data and render the element
            await locator.wait_for(state="visible", timeout=15000)
            
            ads_text = await locator.inner_text()
            ads_text = ads_text.strip()
            
            # The text should be like "8 ads" or "0 ads" or "10,000 ads"
            # Extract all digits, remove commas then check if >= 1
            numbers = re.findall(r'\d+', ads_text.replace(',', ''))
            
            if numbers:
                count = int(numbers[0])
                has_ads = "yes" if count >= 1 else "no"
            else:
                has_ads = "no"
                
            return {
                "domain": req.domain, 
                "region": req.region,
                "has_ads": has_ads,
                "raw_text": ads_text
            }
            
        except TimeoutError:
            # If it times out finding the element, typically implies 0 ads or loading failure
            return {
                "domain": req.domain, 
                "region": req.region,
                "has_ads": "no", 
                "error": "timeout (could not detect ads count within 15 seconds)"
            }
        except Exception as e:
            return {
                "domain": req.domain, 
                "region": req.region,
                "has_ads": "no", 
                "error": str(e)
            }
        finally:
            if 'browser' in locals():
                await browser.close()

if __name__ == "__main__":
    uvicorn.run("adsapi:app", host="0.0.0.0", port=8005, reload=True)
