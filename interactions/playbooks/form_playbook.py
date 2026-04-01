import asyncio
import time
from playwright.async_api import Page

async def run_form(page: Page, selector: str) -> int:
    """
    Intelligently fills detected form fields using fuzzy matching for labels.
    """
    t0 = time.monotonic()
    try:
        # 📝 Define common field mappings
        fields = {
            "name": "Performance Tester",
            "email": "tester@example.com",
            "subject": "Performance Audit Request",
            "message": "This is an automated performance test of your form interaction stability.",
            "phone": "555-0199",
            "zip": "90210"
        }
        
        # 🔍 Attempt fuzzy filling
        inputs = await page.query_selector_all('input:not([type="hidden"]):not([type="submit"]), textarea')
        
        for el in inputs[:6]: # Don't overwhelm, just the top fields
            label_text = ""
            # Try to find associated label or placeholder
            id_attr = await el.get_attribute("id")
            if id_attr:
                label = await page.query_selector(f'label[for="{id_attr}"]')
                if label: label_text = await label.inner_text()
            
            placeholder = await el.get_attribute("placeholder") or ""
            name_attr = await el.get_attribute("name") or ""
            
            search_text = (label_text + " " + placeholder + " " + name_attr).lower()
            
            # Match against our map
            filled = False
            for key, val in fields.items():
                if key in search_text:
                    await el.fill(val)
                    filled = True
                    break
            
            if not filled:
                await el.fill("Automated Test Data")

        # ⏳ Observe interaction stability
        await asyncio.sleep(0.5)
        
        return int((time.monotonic() - t0) * 1000)
    except Exception as e:
        print(f"  [WARN] Form playbook failed: {e}")
        return int((time.monotonic() - t0) * 1000)
