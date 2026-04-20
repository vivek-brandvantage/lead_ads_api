import re
import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import uvicorn

app = FastAPI(title="Google Ads Transparency Checker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AdsRequest(BaseModel):
    domain: str
    # Defaulting region to AU as requested
    region: str = "AU"

_executor = ThreadPoolExecutor(max_workers=4)

def _scrape_ads(domain: str, region: str) -> dict:
    url = f"https://adstransparency.google.com/?domain={domain}&region={region}"

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=chrome_options)
    try:
        driver.get(url)

        # Wait up to 15 seconds for the angular app to fetch api data and render the element
        wait = WebDriverWait(driver, 15)
        element = wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".ads-count"))
        )

        ads_text = element.text.strip()

        # The text should be like "8 ads" or "0 ads" or "10,000 ads"
        # Extract all digits, remove commas then check if >= 1
        numbers = re.findall(r'\d+', ads_text.replace(',', ''))

        if numbers:
            count = int(numbers[0])
            has_ads = "yes" if count >= 1 else "no"
        else:
            has_ads = "no"

        return {
            "domain": domain,
            "region": region,
            "has_ads": has_ads,
            "raw_text": ads_text
        }

    except TimeoutException:
        # If it times out finding the element, typically implies 0 ads or loading failure
        return {
            "domain": domain,
            "region": region,
            "has_ads": "no",
            "error": "timeout (could not detect ads count within 15 seconds)"
        }
    except Exception as e:
        return {
            "domain": domain,
            "region": region,
            "has_ads": "no",
            "error": str(e)
        }
    finally:
        driver.quit()


@app.post("/check_ads_status")
async def check_ads_status(req: AdsRequest):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(_executor, _scrape_ads, req.domain, req.region)
    return result


if __name__ == "__main__":
    uvicorn.run("adsapi:app", host="0.0.0.0", port=8005, reload=True)
