import time
import json
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime, timedelta
import os
import re

# Configure logging (INFO level to reduce terminal output)
logging.basicConfig(
    level=logging.INFO,  # Changed to INFO to reduce debug noise
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("ihc_scraper.log", encoding='utf-8')
        # Removed StreamHandler to stop logging to terminal
    ]
)
logger = logging.getLogger(__name__)

def get_user_input():
    """Get user preferences for date range"""
    print("\n=== IHC Case Scraper ===")
    while True:
        start_date = input("\nEnter start date (DD/MM/YYYY): ").strip()
        try:
            datetime.strptime(start_date, "%d/%m/%Y")
            break
        except ValueError:
            print("Invalid date format. Please use DD/MM/YYYY")
    return {'start_date': start_date}

def get_date_range(start_date_str):
    """Generate date list from start date to current date"""
    start_date = datetime.strptime(start_date_str, "%d/%m/%Y")
    end_date = datetime.now()
    date_list = []
    current = start_date
    while current <= end_date:
        date_list.append(current.strftime("%d-%m-%Y"))  # Format with -
        current += timedelta(days=1)
    return date_list

def setup_webdriver():
    """Setup Chrome WebDriver with auto-driver management"""
    try:
        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        # Browser opens visibly for debugging
        
        logger.info("Installing/setting up ChromeDriver...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.implicitly_wait(5)
        logger.info("WebDriver initialized successfully")
        return driver
    except Exception as e:
        logger.error(f"Failed to initialize WebDriver: {str(e)}")
        raise

def extract_clean_text(element):
    """Extract and clean text from web element"""
    try:
        text = element.get_attribute('textContent') or element.text or ""
        return re.sub(r'\s+', ' ', text.strip()) if text.strip() else "N/A"
    except:
        return "N/A"

def extract_case_data(row, row_index, date):
    """Extract case data matching desired JSON structure"""
    try:
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) < 5:
            return None

        cell_texts = [extract_clean_text(cell) for cell in cells]
        
        case_data = {
            "Sr": row_index,
            "Institution_Date": date,
            "Case_No": "N/A",
            "Case_Title": "N/A",
            "Bench": [],
            "Hearing_Date": "N/A",
            "Case_Category": "N/A",
            "Status": "N/A",
            "Orders": [{"Sr": 1, "Hearing_Date": "N/A", "Bench": [], "List_Type": "N/A", 
                       "Case_Stage": "N/A", "Short_Order": "N/A", "Disposal_Date": "N/A", 
                       "Order_File": "N/A"}],
            "Comments": [{"Compliance_Date": "N/A", "Case_No": "N/A", "Case_Title": "N/A", 
                         "Doc_Type": "N/A", "Parties": "N/A", "Description": "No comments available", 
                         "View_File": "N/A"}],
            "CMs": [{"Sr": 1, "CM": "N/A", "Institution_Date": "N/A", "Disposal_Date": "N/A", 
                    "Order_Passed": "N/A", "Description": "No CMs available", "Status": "N/A"}],
            "Details": {
                "Case_No": "N/A",
                "Case_Status": "N/A",
                "Hearing_Date": "N/A",
                "Case_Stage": "N/A",
                "Tentative_Date": "N/A",
                "Short_Order": "N/A",
                "Before_Bench": [],
                "Case_Title": "N/A",
                "Advocates": {"Petitioner": "N/A", "Respondent": "N/A"},
                "Case_Description": "N/A",
                "Disposal_Information": {
                    "Disposed_Status": "N/A",
                    "Case_Disposal_Date": "N/A",
                    "Disposal_Bench": [],
                    "Consigned_Date": "N/A"
                },
                "FIR_Information": {
                    "FIR_No": "N/A",
                    "FIR_Date": "N/A",
                    "Police_Station": "N/A",
                    "Under_Section": "N/A",
                    "Incident": "N/A",
                    "Accused": "N/A"
                }
            }
        }

        # Extract basic case info
        for i, text in enumerate(cell_texts):
            if re.search(r'\d+/\d{4}|W\.P|Crl|Civil', text, re.IGNORECASE):
                case_data["Case_No"] = text
                case_data["Details"]["Case_No"] = text
                case_data["Comments"][0]["Case_No"] = text
            elif any(vs in text for vs in [' VS ', ' vs ', ' V/S ', ' v/s ', ' - VS - ']):
                case_data["Case_Title"] = text
                case_data["Details"]["Case_Title"] = text
                case_data["Comments"][0]["Case_Title"] = text
                case_data["Comments"][0]["Parties"] = text
                parts = re.split(r'\s+(VS|vs|V/S|v/s|- VS -)\s+', text)
                if len(parts) >= 3:
                    case_data["Details"]["Advocates"]["Petitioner"] = parts[0].strip()
                    case_data["Details"]["Advocates"]["Respondent"] = parts[2].strip()
            elif re.search(r'\d{1,2}[-/]\d{1,2}[-/]\d{4}', text):
                case_data["Hearing_Date"] = text
                case_data["Details"]["Hearing_Date"] = text
                case_data["Orders"][0]["Hearing_Date"] = text
            elif any(status in text.lower() for status in ['pending', 'disposed', 'fixed', 'adjourned', 'decided']):
                case_data["Status"] = text
                case_data["Details"]["Case_Status"] = text
                case_data["Details"]["Short_Order"] = text
                case_data["Orders"][0]["Short_Order"] = text
            elif any(title in text for title in ['Justice', 'Hon', 'CJ']):
                bench = [b.strip() for b in re.split(r',|and', text) if b.strip()]
                case_data["Bench"] = bench
                case_data["Orders"][0]["Bench"] = bench
                case_data["Details"]["Before_Bench"] = bench
                case_data["Details"]["Disposal_Information"]["Disposal_Bench"] = bench

        if case_data["Case_No"] == "N/A":
            return None

        print(f"    → Extracted: {case_data['Case_No']}")
        return case_data

    except Exception as e:
        print(f"    → Error extracting case {row_index}: {e}")
        return None

def extract_cases_from_page(driver, date, page_num):
    """Extract cases from current page"""
    cases = []
    try:
        wait = WebDriverWait(driver, 15)
        table = wait.until(EC.visibility_of_element_located((By.ID, "tblCases")))
        
        # Wait for at least one data row
        wait.until(EC.presence_of_element_located((By.XPATH, "//table[@id='tblCases']//tbody/tr")))
        
        # Get data rows from tbody
        rows = table.find_elements(By.XPATH, ".//tbody/tr")
        print(f"    → Found {len(rows)} rows on page {page_num}")
        
        for i, row in enumerate(rows, 1):
            case_data = extract_case_data(row, i, date)
            if case_data:
                cases.append(case_data)
        
        return cases
    except TimeoutException:
        print(f"    → Timeout waiting for table on page {page_num}")
        return cases
    except Exception as e:
        print(f"    → Error extracting from page {page_num}: {e}")
        return cases

def get_pagination_info(driver):
    """Get current pagination information"""
    try:
        info_xpath = "//div[@id='tblCases_info']"
        info_element = driver.find_element(By.XPATH, info_xpath)
        info_text = extract_clean_text(info_element)
        return info_text
    except NoSuchElementException:
        return None

def has_next_page_simple(driver):
    """Simplified and correct function to check and click next page button"""
    try:
        print("  → Checking for next page...")
        
        # Wait for pagination to load
        wait = WebDriverWait(driver, 5)
        pagination_div = wait.until(EC.presence_of_element_located((By.ID, "tblCases_paginate")))
        
        # Find the Next button - DataTables uses specific structure
        # Look for: <a class="paginate_button next" ...>Next</a>
        try:
            next_button = pagination_div.find_element(By.XPATH, ".//a[contains(@class, 'paginate_button') and contains(@class, 'next')]")
            
            # Check if the next button is disabled
            button_classes = next_button.get_attribute('class')
            print(f"  → Next button classes: {button_classes}")
            
            if 'disabled' in button_classes:
                print("  → Next button is disabled - reached last page")
                return False
            else:
                print("  → Next button is enabled - clicking...")
                # Store current page info to verify page change
                try:
                    current_info = driver.find_element(By.ID, "tblCases_info").text
                    print(f"  → Current: {current_info}")
                except:
                    current_info = None
                
                # Click the next button
                driver.execute_script("arguments[0].click();", next_button)
                print("  → Clicked Next button")
                
                # Wait for page to change
                time.sleep(3)
                
                # Verify page actually changed
                try:
                    new_info = driver.find_element(By.ID, "tblCases_info").text
                    if new_info != current_info:
                        print(f"  → Page changed to: {new_info}")
                        return True
                    else:
                        print("  → Page didn't change - might be last page")
                        return False
                except:
                    print("  → Assuming page changed (couldn't verify)")
                    return True
                    
        except NoSuchElementException:
            print("  → Next button not found - reached last page")
            return False
            
    except Exception as e:
        print(f"  → Pagination check failed: {e}")
        return False

def scrape_date(driver, date):
    """Scrape all cases for a specific date"""
    logger.info(f"Scraping cases for {date}")
    all_cases = []
    page = 1
    
    try:
        driver.get("https://mis.ihc.gov.pk/frmCseSrch")
        wait = WebDriverWait(driver, 15)
        
        # Click advanced search
        adv_btn = wait.until(EC.element_to_be_clickable((By.ID, "lnkAdvncSrch")))
        adv_btn.click()
        print("  → Clicked advanced search")
        time.sleep(2)
        
        # Enter date
        date_input = wait.until(EC.presence_of_element_located((By.ID, "txtDt")))
        date_input.clear()
        input_date = date  # Already in DD-MM-YYYY
        date_input.send_keys(input_date)
        print(f"  → Entered date: {input_date}")
        time.sleep(1)
        
        # Click search
        search_btn = wait.until(EC.element_to_be_clickable((By.ID, "btnAdvnSrch")))
        search_btn.click()
        print("  → Clicked search button")
        time.sleep(5)  # Wait for results to load
        
        # Wait for results container
        wait.until(EC.visibility_of_element_located((By.ID, "grdCaseInfo")))
        print("  → Results loaded")
        
        # Additional wait for table to fully load
        wait.until(EC.visibility_of_element_located((By.ID, "tblCases")))
        time.sleep(3)
        
        # Get initial pagination info
        initial_info = get_pagination_info(driver)
        print(f"  → {initial_info}")
        
        # Process all pages
        while True:
            print(f"  → Processing page {page}")
            page_cases = extract_cases_from_page(driver, date, page)
            all_cases.extend(page_cases)
            print(f"  → Extracted {len(page_cases)} cases from page {page}")
            
            # Check if there's a next page
            if not has_next_page_simple(driver):
                print(f"  → Reached last page for {date}. Total pages: {page}")
                break
            
            page += 1
            
            # Safety check to prevent infinite loops
            if page > 50:  # Reasonable upper limit
                print(f"  → Reached maximum page limit (50) for {date}")
                break
        
        print(f"Total cases extracted for {date}: {len(all_cases)}")
        return all_cases
        
    except TimeoutException:
        print(f"  → Timeout during setup for {date}")
        return all_cases
    except Exception as e:
        print(f"  → Error scraping {date}: {e}")
        return all_cases

def save_results(all_cases, start_date):
    """Save results to JSON file"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"ihc_cases_{start_date.replace('/', '-')}_{timestamp}.json"
    os.makedirs("output", exist_ok=True)
    filepath = os.path.join("output", filename)
    
    output_data = {
        "Cases": all_cases
    }
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(all_cases)} cases to {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Error saving results: {e}")
        return None

def main():
    """Main function"""
    driver = None
    try:
        config = get_user_input()
        date_list = get_date_range(config['start_date'])
        
        print(f"\nDate range: {config['start_date']} to today ({len(date_list)} dates total)")
        logger.info(f"Starting scraper for {len(date_list)} dates")
        print("Initializing WebDriver...")
        driver = setup_webdriver()
        print("WebDriver ready. Starting scraping...")
        
        all_cases = []
        for i, date in enumerate(date_list, 1):
            print(f"\n--- Processing date {i}/{len(date_list)}: {date} ---")
            date_cases = scrape_date(driver, date)
            all_cases.extend(date_cases)
            print(f"Cases found for {date}: {len(date_cases)}")
            
            # Small delay between dates to be respectful to the server
            time.sleep(2)
        
        if all_cases:
            filepath = save_results(all_cases, config['start_date'])
            if filepath:
                print(f"\n✅ Scraping completed! Saved to {filepath}")
                print(f"📊 Total cases across all dates: {len(all_cases)}")
            else:
                print("\n❌ Error saving results. Check ihc_scraper.log for details.")
        else:
            print("\n⚠️ No cases found across all dates")
            
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}")
        print(f"\n❌ Error: {e}. Check ihc_scraper.log for details.")
    finally:
        if driver:
            driver.quit()
            logger.info("WebDriver closed")
            print("WebDriver closed.")

if __name__ == "__main__":
    main()