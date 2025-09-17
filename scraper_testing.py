import time
import json
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("ihc_scraper.log", encoding='utf-8'), 
        logging.StreamHandler()
    ],
)
logger = logging.getLogger(__name__)

def extract_case_details(driver, case_row, sr_number):
    """Extract detailed information for a single case"""
    case_data = {
        "Sr": sr_number,
        "Institution_Date": "N/A",
        "Case_No": "N/A",
        "Case_Title": "N/A",
        "Bench": [],
        "Hearing_Date": "N/A",
        "Case_Category": "N/A",
        "Status": "N/A",
        "Orders": [],
        "Comments": [],
        "CMs": [],
        "Details": {
            "Case_No": "N/A",
            "Case_Status": "N/A",
            "Hearing_Date": "N/A",
            "Case_Stage": "N/A",
            "Tentative_Date": "N/A",
            "Short_Order": "N/A",
            "Before_Bench": [],
            "Case_Title": "N/A",
            "Advocates": {
                "Petitioner": "N/A",
                "Respondent": "N/A"
            },
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
    
    try:
        # Extract basic information from the row
        cells = case_row.find_elements(By.TAG_NAME, "td")
        if len(cells) >= 5:
            case_data["Institution_Date"] = cells[1].text.strip()
            case_data["Case_No"] = cells[2].text.strip()
            case_data["Case_Title"] = cells[3].text.strip()
            case_data["Bench"] = [cells[4].text.strip()] if cells[4].text.strip() and cells[4].text.strip() != "N/A" else []
            
            # Update Details section with basic info
            case_data["Details"]["Case_No"] = case_data["Case_No"]
            case_data["Details"]["Case_Title"] = case_data["Case_Title"]
            case_data["Details"]["Before_Bench"] = case_data["Bench"].copy()
            
            if len(cells) >= 6:
                case_data["Hearing_Date"] = cells[5].text.strip()
                case_data["Details"]["Hearing_Date"] = case_data["Hearing_Date"]
            
            if len(cells) >= 7:
                case_data["Status"] = cells[6].text.strip()
                case_data["Details"]["Case_Status"] = case_data["Status"]
        
        # Try to click on Details button to get more information
        try:
            details_buttons = case_row.find_elements(By.XPATH, ".//button[contains(@class, 'btn') and contains(text(), 'Details')]")
            if details_buttons:
                logger.info(f"Clicking details for case {sr_number}")
                driver.execute_script("arguments[0].click();", details_buttons[0])
                time.sleep(2)
                
                # Extract detailed information from modal or new section
                case_data = extract_detailed_info(driver, case_data)
                
                # Close modal if it exists
                try:
                    close_buttons = driver.find_elements(By.XPATH, "//button[contains(@class, 'close') or contains(text(), 'Close')]")
                    if close_buttons:
                        close_buttons[0].click()
                        time.sleep(1)
                except:
                    pass
                    
        except Exception as e:
            logger.warning(f"Could not extract detailed info for case {sr_number}: {e}")
    
    except Exception as e:
        logger.error(f"Error extracting case {sr_number}: {e}")
    
    return case_data

def extract_detailed_info(driver, case_data):
    """Extract detailed information from case details section"""
    try:
        # Look for additional tables that might contain detailed information
        detail_tables = driver.find_elements(By.XPATH, "//table[contains(@id, 'tbl') and not(contains(@id, 'tblCases'))]")
        
        for table in detail_tables:
            table_id = table.get_attribute("id")
            
            if "Hstry" in table_id or "History" in table_id:
                # Extract case history/orders
                rows = table.find_elements(By.TAG_NAME, "tr")[1:]  # Skip header
                for i, row in enumerate(rows):
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 3 and any(cell.text.strip() for cell in cells):
                        order = {
                            "Sr": i + 1,
                            "Hearing_Date": cells[0].text.strip() if len(cells) > 0 else "N/A",
                            "Bench": [cells[1].text.strip()] if len(cells) > 1 and cells[1].text.strip() else [],
                            "List_Type": cells[2].text.strip() if len(cells) > 2 else "N/A",
                            "Case_Stage": cells[3].text.strip() if len(cells) > 3 else "N/A",
                            "Short_Order": cells[4].text.strip() if len(cells) > 4 else "N/A",
                            "Disposal_Date": cells[5].text.strip() if len(cells) > 5 else "N/A",
                            "Order_File": f"orders/order_{case_data['Case_No'].replace('/', '-').replace(' ', '')}.pdf"
                        }
                        case_data["Orders"].append(order)
            
            elif "Cmnts" in table_id or "Comments" in table_id:
                # Extract comments
                rows = table.find_elements(By.TAG_NAME, "tr")[1:]  # Skip header
                for row in rows:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 3 and any(cell.text.strip() for cell in cells):
                        comment = {
                            "Compliance_Date": cells[0].text.strip() if len(cells) > 0 else "N/A",
                            "Case_No": case_data["Case_No"],
                            "Case_Title": case_data["Case_Title"],
                            "Doc_Type": cells[1].text.strip() if len(cells) > 1 else "N/A",
                            "Parties": case_data["Case_Title"],
                            "Description": cells[2].text.strip() if len(cells) > 2 else "No comments available",
                            "View_File": f"comments/comment_{case_data['Case_No'].replace('/', '-').replace(' ', '')}.pdf"
                        }
                        case_data["Comments"].append(comment)
            
            elif "Cms" in table_id or "CM" in table_id:
                # Extract CMs (Case Management)
                rows = table.find_elements(By.TAG_NAME, "tr")[1:]  # Skip header
                for i, row in enumerate(rows):
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 3 and any(cell.text.strip() for cell in cells):
                        cm = {
                            "Sr": i + 1,
                            "CM": cells[0].text.strip() if len(cells) > 0 else "N/A",
                            "Institution_Date": cells[1].text.strip() if len(cells) > 1 else "N/A",
                            "Disposal_Date": cells[2].text.strip() if len(cells) > 2 else "N/A",
                            "Order_Passed": cells[3].text.strip() if len(cells) > 3 else "N/A",
                            "Description": cells[4].text.strip() if len(cells) > 4 else "No CMs available",
                            "Status": cells[5].text.strip() if len(cells) > 5 else "N/A"
                        }
                        case_data["CMs"].append(cm)
        
        # If no detailed data was found, add default entries
        if not case_data["Orders"]:
            case_data["Orders"].append({
                "Sr": 1,
                "Hearing_Date": case_data["Hearing_Date"],
                "Bench": case_data["Bench"].copy(),
                "List_Type": "N/A",
                "Case_Stage": "N/A",
                "Short_Order": case_data["Status"],
                "Disposal_Date": "N/A",
                "Order_File": f"orders/order_{case_data['Case_No'].replace('/', '-').replace(' ', '')}.pdf"
            })
        
        if not case_data["Comments"]:
            case_data["Comments"].append({
                "Compliance_Date": "N/A",
                "Case_No": case_data["Case_No"],
                "Case_Title": case_data["Case_Title"],
                "Doc_Type": "N/A",
                "Parties": case_data["Case_Title"],
                "Description": "No comments available",
                "View_File": f"comments/comment_{case_data['Case_No'].replace('/', '-').replace(' ', '')}.pdf"
            })
        
        if not case_data["CMs"]:
            case_data["CMs"].append({
                "Sr": 1,
                "CM": "N/A",
                "Institution_Date": "N/A",
                "Disposal_Date": "N/A",
                "Order_Passed": "N/A",
                "Description": "No CMs available",
                "Status": "N/A"
            })
    
    except Exception as e:
        logger.warning(f"Error extracting detailed info: {e}")
    
    return case_data

def scrape_ihc_cases(search_date="12/11/2020", output_file="ihc_cases.json"):
    """Main scraper function that extracts all cases and saves to JSON"""
    
    # Setup driver
    options = Options()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    driver = webdriver.Chrome(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    wait = WebDriverWait(driver, 60)
    
    all_cases = []
    
    try:
        # Step 1: Open the page
        url = "https://mis.ihc.gov.pk/frmCseSrch"
        logger.info(f"Opening: {url}")
        driver.get(url)
        time.sleep(5)
        
        # Step 2: Click Advanced Search
        logger.info("Looking for Advanced Search button...")
        adv_btn = wait.until(EC.element_to_be_clickable((By.ID, "lnkAdvncSrch")))
        logger.info("Found Advanced Search button, clicking...")
        adv_btn.click()
        time.sleep(3)
        
        # Step 3: Enter date
        logger.info("Looking for date input field...")
        date_input = wait.until(EC.presence_of_element_located((By.ID, "txtDt")))
        date_input.clear()
        date_input.send_keys(search_date)
        logger.info(f"Date '{search_date}' entered successfully")
        time.sleep(2)
        
        # Step 4: Click Search
        logger.info("Looking for search button...")
        search_btn = wait.until(EC.element_to_be_clickable((By.ID, "btnAdvnSrch")))
        logger.info("Found search button, clicking...")
        search_btn.click()
        logger.info("Search button clicked, waiting for results...")
        
        # Step 5: Wait for results to load with better detection
        logger.info("Waiting for search results to load...")
        
        # First, wait for the table to be present
        results_table = wait.until(EC.presence_of_element_located((By.ID, "tblCases")))
        logger.info("Results table found, waiting for data to populate...")
        
        # Wait for actual data to load by checking for data rows
        # The table might exist but be empty initially
        def check_for_data_rows(driver):
            try:
                table = driver.find_element(By.ID, "tblCases")
                rows = table.find_elements(By.TAG_NAME, "tr")
                # Check if we have more than just the header row
                if len(rows) > 1:
                    # Check if the first data row has actual content (not just empty cells)
                    first_data_row = rows[1]
                    cells = first_data_row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 3:  # Should have at least 3 columns
                        # Check if cells have meaningful content
                        cell_texts = [cell.text.strip() for cell in cells[:3]]
                        if any(cell_texts) and not all(text in ["", "Loading...", "Please wait..."] for text in cell_texts):
                            logger.info(f"Data detected! Found {len(rows)-1} rows")
                            return True
                logger.info(f"Still loading... found {len(rows)-1 if len(rows) > 0 else 0} data rows")
                return False
            except:
                return False
        
        # Wait up to 60 seconds for data to appear
        data_loaded = False
        max_wait_time = 60
        check_interval = 2
        
        for i in range(0, max_wait_time, check_interval):
            if check_for_data_rows(driver):
                data_loaded = True
                break
            time.sleep(check_interval)
            
        if not data_loaded:
            logger.warning("Data did not load within 60 seconds, trying to extract anyway...")
            # Take a screenshot for debugging
            driver.save_screenshot("data_not_loaded_screenshot.png")
        
        # Final check - get all data rows (skip header)
        results_table = driver.find_element(By.ID, "tblCases")
        rows = results_table.find_elements(By.TAG_NAME, "tr")[1:]
        logger.info(f"Found {len(rows)} case records")
        
        for i, row in enumerate(rows, 1):
            logger.info(f"Processing case {i} of {len(rows)}")
            case_data = extract_case_details(driver, row, i)
            all_cases.append(case_data)
            
            # Add a small delay between cases to avoid overwhelming the server
            time.sleep(0.5)
        
        # Step 7: Create final JSON structure
        final_data = {
            "metadata": {
                "search_date": search_date,
                "extraction_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_cases": len(all_cases),
                "source_url": url
            },
            "Cases": all_cases
        }
        
        # Step 8: Save to JSON file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Successfully saved {len(all_cases)} cases to {output_file}")
        
    except Exception as e:
        logger.error(f"Error occurred: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        driver.save_screenshot("error_screenshot.png")
        
        # Save partial results if any were collected
        if all_cases:
            partial_data = {
                "metadata": {
                    "search_date": search_date,
                    "extraction_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "total_cases": len(all_cases),
                    "source_url": url,
                    "status": "partial_extraction_due_to_error"
                },
                "Cases": all_cases
            }
            
            partial_filename = f"partial_{output_file}"
            with open(partial_filename, 'w', encoding='utf-8') as f:
                json.dump(partial_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved partial results ({len(all_cases)} cases) to {partial_filename}")
        
    finally:
        logger.info("Closing browser...")
        driver.quit()
    
    return len(all_cases)

if __name__ == "__main__":
    # You can modify these parameters as needed
    search_date = "12/11/2020"  # Date to search for
    output_file = "ihc_cases.json"  # Output JSON file name
    
    logger.info("Starting IHC Cases Scraper...")
    logger.info(f"Search Date: {search_date}")
    logger.info(f"Output File: {output_file}")
    
    cases_count = scrape_ihc_cases(search_date, output_file)
    
    if cases_count > 0:
        logger.info(f"Scraping completed successfully! Extracted {cases_count} cases.")
    else:
        logger.error("No cases were extracted. Check the logs for errors.")