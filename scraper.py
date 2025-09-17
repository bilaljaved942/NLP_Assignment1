import time
import json
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime, timedelta
import os
import re

# Configure logging (INFO level for less verbose output)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("ihc_scraper.log", encoding='utf-8'),
        logging.StreamHandler()
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
        date_list.append(current.strftime("%d-%m-%Y"))  # Changed to %d-%m-%Y format
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
            logger.debug(f"Skipping row {row_index}: Fewer than 5 cells")
            return None

        cell_texts = [extract_clean_text(cell) for cell in cells]
        logger.debug(f"Row {row_index} cells: {cell_texts}")
        
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
            logger.debug(f"Skipping row {row_index}: No case number found")
            return None

        logger.info(f"Extracted case: {case_data['Case_No']}")
        return case_data

    except Exception as e:
        logger.error(f"Error extracting case {row_index}: {e}")
        return None

def extract_cases_from_page(driver, date, page_num):
    """Extract cases from current page"""
    cases = []
    try:
        wait = WebDriverWait(driver, 15)  # Increased timeout
        table = wait.until(EC.visibility_of_element_located((By.ID, "tblCases")))
        
        # Wait for at least one data row
        wait.until(EC.presence_of_element_located((By.XPATH, "//table[@id='tblCases']//tbody/tr")))
        
        # Get data rows from tbody
        rows = table.find_elements(By.XPATH, ".//tbody/tr")
        logger.info(f"Found {len(rows)} data rows on page {page_num}")
        
        for i, row in enumerate(rows, 1):
            case_data = extract_case_data(row, i, date)
            if case_data:
                cases.append(case_data)
        
        return cases
    except TimeoutException:
        logger.error(f"Timeout waiting for table or data rows on page {page_num}")
        return cases
    except Exception as e:
        logger.error(f"Error extracting cases from page {page_num}: {e}")
        return cases

def has_next_page(driver):
    """Check if next page exists and navigate to it"""
    try:
        # Wait for pagination to load
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "tblCases_paginate")))
        logger.debug("Pagination container loaded")
        
        next_button = driver.find_element(By.ID, "tblCases_next")
        classes = next_button.get_attribute('class')
        logger.debug(f"Next button classes: {classes}")
        
        if 'disabled' not in classes:
            driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
            time.sleep(0.5)
            next_button.click()
            logger.info("Clicked next page button")
            time.sleep(5)  # Increased wait after click
            return True
        else:
            logger.info("Next button disabled - end of pages")
            return False
    except NoSuchElementException:
        logger.debug("Next button or pagination not found")
        return False
    except TimeoutException:
        logger.error("Timeout waiting for pagination")
        return False
    except Exception as e:
        logger.error(f"Error checking/clicking next page: {e}")
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
        logger.debug("Clicked advanced search button")
        time.sleep(1)
        
        # Enter date (replace / with - if needed)
        date_input = wait.until(EC.presence_of_element_located((By.ID, "txtDt")))
        date_input.clear()
        input_date = date.replace('/', '-')  # Ensure - format
        date_input.send_keys(input_date)
        logger.debug(f"Entered date: {input_date}")
        time.sleep(0.5)
        
        # Click search
        search_btn = wait.until(EC.element_to_be_clickable((By.ID, "btnAdvnSrch")))
        search_btn.click()
        logger.debug("Clicked search button")
        time.sleep(10)  # Increased wait for results to load
        
        # Wait for results container
        wait.until(EC.visibility_of_element_located((By.ID, "grdCaseInfo")))
        logger.info("Results container loaded")
        
        # Process all pages
        while True:
            logger.info(f"Processing page {page} for {date}")
            page_cases = extract_cases_from_page(driver, date, page)
            all_cases.extend(page_cases)
            
            if not has_next_page(driver):
                break
            page += 1
        
        logger.info(f"Total cases for {date}: {len(all_cases)}")
        return all_cases
        
    except TimeoutException:
        logger.error(f"Timeout during setup or loading results for {date}")
        return all_cases
    except Exception as e:
        logger.error(f"Error scraping {date}: {e}")
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