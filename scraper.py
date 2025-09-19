import time
import json
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime, timedelta
import os
import re
import concurrent.futures
import threading
from queue import Queue
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("ihc_scraper_fixed.log", encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class FastIHCScraper:
    def __init__(self, max_workers=4):
        self.max_workers = max_workers
        self.results_lock = threading.Lock()
        self.all_cases = []
        
    def setup_webdriver(self):
        """Setup Chrome WebDriver with optimized options"""
        try:
            options = Options()
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-plugins")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-notifications")
            options.add_argument("--disable-popup-blocking")
            options.add_argument("--headless")
            options.add_argument("--window-size=1400,1000")
            
            # Additional speed optimizations
            options.add_argument("--disable-images")
            options.add_argument("--no-first-run")
            options.add_argument("--disable-default-apps")
            
            options.add_experimental_option("useAutomationExtension", False)
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_argument("--disable-blink-features=AutomationControlled")
            
            prefs = {
                "profile.default_content_setting_values": {
                    "plugins": 2,
                    "popups": 2,
                    "geolocation": 2,
                    "notifications": 2,
                    "media_stream": 2,
                    "images": 2  # Disable images for speed
                }
            }
            options.add_experimental_option("prefs", prefs)
            
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.implicitly_wait(5)
            driver.set_page_load_timeout(20)
            
            return driver
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {str(e)}")
            raise

    def extract_clean_text(self, element):
        """Extract and clean text from web element"""
        try:
            text = element.get_attribute('textContent') or element.text or ""
            return re.sub(r'\s+', ' ', text.strip()) if text.strip() else "N/A"
        except:
            return "N/A"

    def parse_hearing_date(self, text):
        """Parse hearing date from various formats - optimized"""
        try:
            patterns = [
                re.compile(r'(\w{3}\s+\d{2}-\d{2}-\d{4}\s*\([^)]+\))', re.IGNORECASE),
                re.compile(r'(\d{2}-\d{2}-\d{4}\s*\([^)]+\))', re.IGNORECASE),
                re.compile(r'(\w{3}\s+\d{2}/\d{2}/\d{4})', re.IGNORECASE),
                re.compile(r'(\d{2}/\d{2}/\d{4})', re.IGNORECASE),
                re.compile(r'(\d{2}-\d{2}-\d{4})', re.IGNORECASE),
            ]
            
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    return match.group(1).strip()
            
            return "N/A"
        except:
            return "N/A"

    def parse_bench_names_fast(self, text):
        """Parse bench names from text - optimized version"""
        try:
            bench_names = []
            
            patterns = [
                re.compile(r'Hon(?:ourable|\'ble)?\s+(?:Mr\.|Ms\.)?\s*Justice\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', re.IGNORECASE),
                re.compile(r'Justice\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', re.IGNORECASE),
            ]
            
            for pattern in patterns:
                matches = pattern.findall(text)
                for match in matches:
                    if len(match.strip()) > 2:
                        full_name = f"Honourable Mr. Justice {match.strip()}"
                        if full_name not in bench_names:
                            bench_names.append(full_name)
            
            return bench_names if bench_names else []
        except:
            return []

    def extract_advocate_info_fast(self, driver, case_link, case_data):
        """Fast advocate extraction - only extract advocate info from details"""
        original_window = driver.current_window_handle
        
        try:
            # Click case link quickly
            driver.execute_script("arguments[0].click();", case_link)
            time.sleep(2)
            
            # Handle new window
            windows = driver.window_handles
            if len(windows) > 1:
                for window in windows:
                    if window != original_window:
                        driver.switch_to.window(window)
                        break
            
            # Quick wait and extract only advocate info
            time.sleep(2)
            page_source = driver.page_source
            
            # Extract advocate information quickly
            counsel_patterns = [
                r'Counsel\s+for\s+Petitioner[:\s]*([^<\n]+)',
                r'Petitioner[^:]*Counsel[:\s]*([^<\n]+)', 
                r'For\s+Petitioner[:\s]*([A-Z][a-zA-Z\s]+)',
                r'Advocate\s+for\s+Petitioner[:\s]*([^<\n]+)'
            ]
            
            for pattern in counsel_patterns:
                matches = re.findall(pattern, page_source, re.IGNORECASE)
                if matches:
                    counsel = matches[0].strip()
                    if len(counsel) > 3 and not any(x in counsel.lower() for x in ['not', 'n/a', 'nil', 'none']):
                        case_data["Details"]["Advocates"]["Petitioner"] = counsel
                        break
            
            # Try to get respondent counsel too
            respondent_patterns = [
                r'Counsel\s+for\s+Respondent[:\s]*([^<\n]+)',
                r'Respondent[^:]*Counsel[:\s]*([^<\n]+)',
                r'For\s+Respondent[:\s]*([A-Z][a-zA-Z\s]+)'
            ]
            
            for pattern in respondent_patterns:
                matches = re.findall(pattern, page_source, re.IGNORECASE)
                if matches:
                    counsel = matches[0].strip()
                    if len(counsel) > 3 and not any(x in counsel.lower() for x in ['not', 'n/a', 'nil', 'none']):
                        case_data["Details"]["Advocates"]["Respondent"] = counsel
                        break
            
        except Exception as e:
            logger.warning(f"Quick advocate extraction failed: {e}")
        finally:
            # Quick cleanup
            try:
                windows = driver.window_handles
                if len(windows) > 1:
                    driver.close()
                    driver.switch_to.window(original_window)
                time.sleep(0.5)
            except:
                pass

    def extract_table_row_data_fast(self, row, sr_number, date, driver):
        """Fast table row data extraction with selective advocate lookup"""
        try:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) < 3:
                return None

            # Pre-extract all cell texts at once
            cell_texts = [self.extract_clean_text(cell) for cell in cells]
            
            # Initialize case data structure with defaults
            case_data = {
                "Sr": sr_number,
                "Institution_Date": date,
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

            # Pre-compiled regex patterns for speed
            case_no_pattern = re.compile(r'(W\.P\.?\s*\d+/\d{4}[^,]*|Crl\.?\s*[A-Z]*\.?\s*\d+/\d{4}[^,]*|Civil\s*[A-Z]*\.?\s*\d+/\d{4}[^,]*|[A-Z]+\.?\s*\d+/\d{4}[^,]*)', re.IGNORECASE)
            title_vs_pattern = re.compile(r' VS | vs | V/S | v/s | - VS - | Vs ', re.IGNORECASE)
            category_pattern = re.compile(r'NOTICE|REGULAR|URGENT|MISC|SUPPLIMENTRY', re.IGNORECASE)
            status_pattern = re.compile(r'decided|pending|disposed|fixed', re.IGNORECASE)
            
            # Fast extraction from all cells
            all_text = " | ".join(cell_texts)  # Combine for faster searching
            
            # Extract case number
            case_match = case_no_pattern.search(all_text)
            if case_match:
                case_data["Case_No"] = case_match.group(1).strip()
                case_data["Details"]["Case_No"] = case_match.group(1).strip()
            
            # Extract case title and look for clickable case links
            case_link = None
            for i, cell in enumerate(cells):
                cell_text = cell_texts[i]
                if title_vs_pattern.search(cell_text):
                    case_data["Case_Title"] = cell_text
                    case_data["Details"]["Case_Title"] = cell_text
                    break
                
                # Also check for case number with clickable link
                if case_no_pattern.search(cell_text):
                    links = cell.find_elements(By.TAG_NAME, "a")
                    if links:
                        case_link = links[0]  # Store for later use
            
            # If we found a clickable case link, extract advocate info
            if case_link:
                try:
                    self.extract_advocate_info_fast(driver, case_link, case_data)
                except Exception as e:
                    logger.warning(f"Could not extract advocate info: {e}")
            
            # Extract bench names
            bench_names = self.parse_bench_names_fast(all_text)
            if bench_names:
                case_data["Bench"] = bench_names
                case_data["Details"]["Before_Bench"] = bench_names
            
            # Extract hearing date
            hearing_date = self.parse_hearing_date(all_text)
            if hearing_date != "N/A":
                case_data["Hearing_Date"] = hearing_date
                case_data["Details"]["Hearing_Date"] = hearing_date
            
            # Extract category
            category_match = category_pattern.search(all_text)
            if category_match:
                case_data["Case_Category"] = category_match.group(0).upper() + " CASES"
                case_data["Details"]["Case_Stage"] = category_match.group(0).upper()
            
            # Extract status
            status_match = status_pattern.search(all_text)
            if status_match:
                case_data["Status"] = status_match.group(0).title()
                case_data["Details"]["Case_Status"] = status_match.group(0).title()

            # Skip this case if no case number found
            if case_data["Case_No"] == "N/A":
                return None

            # Set default orders
            case_data["Orders"] = [{
                "Sr": 1,
                "Hearing_Date": case_data["Hearing_Date"],
                "Bench": case_data["Bench"],
                "List_Type": "N/A",
                "Case_Stage": case_data["Case_Category"],
                "Short_Order": case_data["Status"] if case_data["Status"] != "N/A" else "N/A",
                "Disposal_Date": "N/A" if case_data["Status"] == "Pending" else case_data["Hearing_Date"],
                "Order_File": "N/A"
            }]

            # Set default comments
            case_data["Comments"] = [{
                "Compliance_Date": "N/A",
                "Case_No": case_data["Case_No"],
                "Case_Title": case_data["Case_Title"],
                "Doc_Type": "N/A",
                "Parties": case_data["Case_Title"],
                "Description": "No comments available",
                "View_File": "N/A"
            }]

            # Set default CMs
            case_data["CMs"] = [{
                "Sr": 1,
                "CM": "N/A",
                "Institution_Date": "N/A",
                "Disposal_Date": "N/A",
                "Order_Passed": "N/A",
                "Description": "No CMs available",
                "Status": "N/A"
            }]

            # Update disposal information if decided/disposed
            if case_data["Status"].lower() in ['decided', 'disposed']:
                case_data["Details"]["Disposal_Information"]["Disposed_Status"] = f"{case_data['Status']} (Disposed Of)"
                case_data["Details"]["Disposal_Information"]["Case_Disposal_Date"] = case_data["Hearing_Date"]
                case_data["Details"]["Disposal_Information"]["Disposal_Bench"] = case_data["Bench"]

            return case_data

        except Exception as e:
            logger.error(f"Error extracting case {sr_number}: {e}")
            return None

    def extract_cases_from_page_fast(self, driver, date, page_num, starting_sr, thread_id=0, max_cases_per_page=None):
        """Fast case extraction from page"""
        cases = []
        try:
            wait = WebDriverWait(driver, 15)
            table = wait.until(EC.visibility_of_element_located((By.ID, "tblCases")))
            
            # Get all rows at once
            rows = table.find_elements(By.XPATH, ".//tbody/tr")
            print(f"Thread {thread_id}: Page {page_num} - Found {len(rows)} rows")
            
            # Filter data rows quickly
            data_rows = []
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 3:
                    first_cell_text = self.extract_clean_text(cells[0])
                    if not any(header in first_cell_text.lower() for header in ['sr', 'case', 'title', 'bench']):
                        data_rows.append(row)
            
            # Limit for testing
            rows_to_process = data_rows[:max_cases_per_page] if max_cases_per_page else data_rows
            
            # Process rows
            for i, row in enumerate(rows_to_process):
                try:
                    sr_number = starting_sr + i
                    case_data = self.extract_table_row_data_fast(row, sr_number, date, driver)
                    
                    if case_data:
                        cases.append(case_data)
                        if i % 10 == 0:
                            print(f"Thread {thread_id}: Processed {i+1}/{len(rows_to_process)} cases")
                        
                except Exception as e:
                    logger.warning(f"Thread {thread_id}: Error processing row {i}: {e}")
                    continue
            
            print(f"Thread {thread_id}: Page {page_num} completed - {len(cases)}/{len(rows_to_process)} cases extracted")
            return cases
            
        except Exception as e:
            logger.error(f"Thread {thread_id}: Error extracting from page {page_num}: {e}")
            return cases

    def scrape_single_date_fast(self, date, thread_id, max_cases_per_date=None):
        """Fast single date scraping"""
        driver = None
        try:
            driver = self.setup_webdriver()
            logger.info(f"Thread {thread_id}: Starting FAST scrape for {date}")
            
            cases = []
            page = 1
            total_cases_count = 0
            
            print(f"Thread {thread_id}: Navigating to IHC website for {date}...")
            driver.get("https://mis.ihc.gov.pk/frmCseSrch")
            wait = WebDriverWait(driver, 15)
            
            # Setup search
            adv_btn = wait.until(EC.element_to_be_clickable((By.ID, "lnkAdvncSrch")))
            adv_btn.click()
            time.sleep(2)
            
            date_input = wait.until(EC.presence_of_element_located((By.ID, "txtDt")))
            date_input.clear()
            date_input.send_keys(date)
            time.sleep(1)
            
            search_btn = wait.until(EC.element_to_be_clickable((By.ID, "btnAdvnSrch")))
            search_btn.click()
            time.sleep(8)
            
            # Wait for results
            wait.until(EC.visibility_of_element_located((By.ID, "grdCaseInfo")))
            wait.until(EC.visibility_of_element_located((By.ID, "tblCases")))
            time.sleep(2)
            
            # Process all pages quickly
            while True:
                starting_sr = total_cases_count + 1
                page_cases = self.extract_cases_from_page_fast(
                    driver, date, page, starting_sr, thread_id, 
                    max_cases_per_date - total_cases_count if max_cases_per_date else None
                )
                cases.extend(page_cases)
                total_cases_count += len(page_cases)
                
                print(f"Thread {thread_id}: Page {page} completed - {len(page_cases)} cases extracted")
                
                if max_cases_per_date and total_cases_count >= max_cases_per_date:
                    print(f"Thread {thread_id}: Reached max cases limit ({max_cases_per_date})")
                    break
                
                if not self.has_next_page_fast(driver):
                    break
                
                page += 1
                if page > 50:
                    break
            
            logger.info(f"Thread {thread_id}: Completed {date} - {len(cases)} cases")
            return cases
            
        except Exception as e:
            logger.error(f"Thread {thread_id}: Error scraping {date}: {e}")
            return []
        finally:
            if driver:
                driver.quit()

    def has_next_page_fast(self, driver):
        """Fast pagination check"""
        try:
            wait = WebDriverWait(driver, 8)
            pagination_div = wait.until(EC.presence_of_element_located((By.ID, "tblCases_paginate")))
            
            next_button = pagination_div.find_element(By.XPATH, ".//a[contains(@class, 'paginate_button') and contains(@class, 'next')]")
            button_classes = next_button.get_attribute('class')
            
            if 'disabled' in button_classes:
                return False
            else:
                driver.execute_script("arguments[0].click();", next_button)
                time.sleep(3)
                return True
                
        except Exception as e:
            return False

    def scrape_parallel_fast(self, date_list, max_workers=None):
        """Fast parallel scraping"""
        if max_workers is None:
            max_workers = self.max_workers
            
        all_cases = []
        completed_dates = 0
        
        print(f"Starting FAST parallel scraping with {max_workers} workers...")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_date = {
                executor.submit(self.scrape_single_date_fast, date, i % max_workers): date 
                for i, date in enumerate(date_list)
            }
            
            for future in as_completed(future_to_date):
                date = future_to_date[future]
                try:
                    cases = future.result()
                    all_cases.extend(cases)
                    completed_dates += 1
                    print(f"✅ FAST: Completed {date} ({completed_dates}/{len(date_list)}) - Found {len(cases)} cases")
                except Exception as e:
                    logger.error(f"Error processing {date}: {e}")
        
        return all_cases

def get_user_input():
    print("\n=== FIXED IHC Case Scraper (Optimized for Speed) ===")
    
    while True:
        print("\nSelect scraping mode:")
        print("1. Single date (for testing)")
        print("2. Date range (from start date to current date)")
        
        mode = input("\nEnter your choice (1 or 2): ").strip()
        if mode in ['1', '2']:
            break
    
    if mode == '1':
        while True:
            single_date = input("\nEnter date to scrape (DD/MM/YYYY): ").strip()
            try:
                datetime.strptime(single_date, "%d/%m/%Y")
                break
            except ValueError:
                print("Invalid date format. Please use DD/MM/YYYY")
        
        return {
            'mode': 'single',
            'single_date': single_date,
            'start_date': single_date,
            'max_workers': 1,
            'batch_size': 1
        }
    
    else:
        while True:
            start_date = input("\nEnter start date (DD/MM/YYYY): ").strip()
            try:
                datetime.strptime(start_date, "%d/%m/%Y")
                break
            except ValueError:
                print("Invalid date format. Please use DD/MM/YYYY")
        
        while True:
            try:
                workers = input(f"\nNumber of parallel workers (1-8, default=4): ").strip()
                if not workers:
                    workers = 4
                else:
                    workers = int(workers)
                if 1 <= workers <= 8:
                    break
            except ValueError:
                pass
        
        while True:
            try:
                batch_size = input(f"\nBatch size (dates per batch, default=30): ").strip()
                if not batch_size:
                    batch_size = 30
                else:
                    batch_size = int(batch_size)
                if 1 <= batch_size <= 100:
                    break
            except ValueError:
                pass
        
        return {
            'mode': 'range',
            'start_date': start_date,
            'max_workers': workers,
            'batch_size': batch_size
        }

def get_date_range(start_date_str, mode='range'):
    if mode == 'single':
        date_obj = datetime.strptime(start_date_str, "%d/%m/%Y")
        return [date_obj.strftime("%d-%m-%Y")]
    else:
        start_date = datetime.strptime(start_date_str, "%d/%m/%Y")
        end_date = datetime.now()
        date_list = []
        current = start_date
        while current <= end_date:
            date_list.append(current.strftime("%d-%m-%Y"))
            current += timedelta(days=1)
        return date_list

def save_results(all_cases, config):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if config['mode'] == 'single':
        filename = f"ihc_cases_fixed_single_{config['single_date'].replace('/', '-')}_{timestamp}.json"
    else:
        filename = f"ihc_cases_fixed_range_{config['start_date'].replace('/', '-')}_{timestamp}.json"
    
    os.makedirs("output", exist_ok=True)
    filepath = os.path.join("output", filename)
    
    output_data = {
        "scrape_config": {
            "mode": config['mode'],
            "start_date": config['start_date'],
            "end_date": datetime.now().strftime("%d/%m/%Y") if config['mode'] == 'range' else config.get('single_date', config['start_date']),
            "max_workers": config['max_workers'],
            "batch_size": config['batch_size'],
            "total_cases": len(all_cases),
            "fixes_applied": [
                "Fixed function structure and indentation",
                "Corrected method placement",
                "Fixed advocate extraction with popup handling",
                "Proper error handling",
                "Maintained speed optimizations"
            ]
        },
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
    try:
        config = get_user_input()
        date_list = get_date_range(config['start_date'], config['mode'])
        
        if config['mode'] == 'single':
            print(f"\n📊 FIXED Single Date Scraping:")
            print(f"   Date: {config['single_date']}")
            print(f"   Features: Fixed structure + advocate extraction + speed optimization")
            confirm = input("\nProceed with FIXED single date scraping? (y/n): ").strip().lower()
        else:
            print(f"\n📊 FIXED Date Range Scraping:")
            print(f"   Date range: {config['start_date']} to today")
            print(f"   Total dates: {len(date_list)}")
            print(f"   Parallel workers: {config['max_workers']}")
            print(f"   Features: Fixed structure + advocate extraction + parallel processing")
            confirm = input("\nProceed with FIXED range scraping? (y/n): ").strip().lower()
        
        if confirm != 'y':
            return
        
        scraper = FastIHCScraper(max_workers=config['max_workers'])
        start_time = time.time()
        
        if config['mode'] == 'single':
            all_cases = scraper.scrape_single_date_fast(date_list[0], 0, max_cases_per_date=20)
        else:
            all_cases = scraper.scrape_parallel_fast(date_list, config['max_workers'])
        
        end_time = time.time()
        
        if all_cases:
            filepath = save_results(all_cases, config)
            if filepath:
                print(f"\n✅ FIXED scraping completed successfully!")
                print(f"📁 File saved: {filepath}")
                print(f"📊 Total cases: {len(all_cases)}")
                print(f"⏱️ Total time: {(end_time - start_time):.2f} seconds")
                print(f"🚀 Speed: {len(all_cases) / (end_time - start_time) * 60:.1f} cases/minute")
                
                if all_cases:
                    case = all_cases[0]
                    print(f"\n📋 Sample case data:")
                    print(f"   Case No: {case.get('Case_No', 'N/A')}")
                    print(f"   Title: {case.get('Case_Title', 'N/A')[:50]}...")
                    print(f"   Bench: {len(case.get('Bench', []))} judge(s)")
                    print(f"   Status: {case.get('Status', 'N/A')}")
                    print(f"   Advocates: {case.get('Details', {}).get('Advocates', {})}")
        else:
            print("\n⚠️ No cases found")
            
    except KeyboardInterrupt:
        print("\n🛑 Scraping interrupted")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()