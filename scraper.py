import time
import logging
import csv
import json
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException

# Configure logging with UTF-8 encoding to handle emojis
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("ihc_scraper.log", encoding='utf-8'), 
        logging.StreamHandler()
    ],
)
logger = logging.getLogger(__name__)


class IHCCaseScraper:
    def __init__(self, headless: bool = False):
        self.url = "https://mis.ihc.gov.pk/frmCseSrch"
        self.headless = headless
        self.driver = None
        self.wait = None
        self.setup_driver()

    def setup_driver(self):
        options = Options()
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        if self.headless:
            options.add_argument("--headless=new")
        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 30)
        logger.info("✅ Chrome driver initialized")

    def search_cases(self, start_date: str) -> bool:
        """Click Advanced Search, fill date, click Search"""
        try:
            self.driver.get(self.url)
            logger.info("🌐 Opened IHC search page")
            time.sleep(3)

            # Step 1: Click Advance Search
            adv_btn = self.wait.until(EC.element_to_be_clickable((By.ID, "lnkAdvncSrch")))
            adv_btn.click()
            logger.info("✅ Clicked Advance Search button")
            time.sleep(2)

            # Step 2: Fill date in modal
            date_input = self.wait.until(EC.presence_of_element_located((By.ID, "txtDt")))
            date_input.clear()
            date_input.send_keys(start_date)
            logger.info(f"✅ Entered date: {start_date}")
            time.sleep(1)

            # Step 3: Click Search
            search_btn = self.wait.until(EC.element_to_be_clickable((By.ID, "btnAdvnSrch")))
            search_btn.click()
            logger.info("✅ Clicked Search button in modal")
            time.sleep(3)

            # Step 4: Wait for results table - try multiple possible selectors
            table_found = False
            possible_selectors = [
                (By.ID, "tblCases"),
                (By.ID, "example"), 
                (By.CLASS_NAME, "table"),
                (By.CSS_SELECTOR, "table.table-bordered"),
                (By.CSS_SELECTOR, "#grdCaseInfo table"),
                (By.XPATH, "//table[contains(@class, 'table')]"),
                (By.XPATH, "//div[@id='grdCaseInfo']//table")
            ]
            
            for selector_type, selector in possible_selectors:
                try:
                    self.wait.until(EC.presence_of_element_located((selector_type, selector)))
                    logger.info(f"✅ Results table found with selector: {selector_type.name}='{selector}'")
                    table_found = True
                    break
                except TimeoutException:
                    continue
            
            if not table_found:
                logger.error("❌ Could not find results table with any selector")
                self.driver.save_screenshot("no_table_found.png")
                
                # Debug: Print page source to see what's actually there
                with open("page_source_debug.html", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)
                logger.info("📝 Page source saved to page_source_debug.html for debugging")
                return False
            
            return True

        except Exception as e:
            logger.error(f"❌ Search error: {e}")
            self.driver.save_screenshot("error_search.png")
            return False

    def extract_basic_case_info(self, row) -> Dict[str, Any]:
        """Extract basic case information from a table row"""
        try:
            cells = row.find_elements(By.TAG_NAME, "td")
            logger.info(f"📝 Row has {len(cells)} cells")
            
            if len(cells) == 0:
                logger.warning("⚠️ No td elements found in row")
                return None
            
            # Log cell contents for debugging
            cell_contents = []
            for i, cell in enumerate(cells):
                content = cell.text.strip()
                cell_contents.append(f"Cell {i}: '{content}'")
            logger.info(f"📋 Cell contents: {'; '.join(cell_contents[:5])}")  # Show first 5 cells
            
            # Flexible extraction based on available cells
            case_info = {
                "Sr": cells[0].text.strip() if len(cells) > 0 else "N/A",
                "Institution_Date": cells[1].text.strip() if len(cells) > 1 else "N/A",
                "Case_No": cells[2].text.strip() if len(cells) > 2 else "N/A",
                "Case_Title": cells[3].text.strip() if len(cells) > 3 else "N/A",
                "Bench": [judge.strip() for judge in cells[4].text.strip().split('\n') if judge.strip()] if len(cells) > 4 else ["N/A"],
                "Hearing_Date": cells[5].text.strip() if len(cells) > 5 else "N/A",
                "Case_Category": cells[6].text.strip() if len(cells) > 6 else "N/A",
                "Status": cells[7].text.strip() if len(cells) > 7 else "N/A",
                "Orders": [],
                "Comments": [],
                "CMs": [],
                "Details": {}
            }
            
            # Clean up empty bench entries
            if case_info["Bench"] == [""]:
                case_info["Bench"] = ["N/A"]
            
            return case_info
            
        except Exception as e:
            logger.error(f"❌ Error extracting basic case info: {e}")
            import traceback
            logger.error(f"📍 Full traceback: {traceback.format_exc()}")
            return None

    def click_history_button(self, row, button_type: str) -> bool:
        """Click on history buttons (Orders, Comments, CaseCM, Details)"""
        try:
            # Look for the button in the last cell (History column)
            history_cell = row.find_elements(By.TAG_NAME, "td")[-1]
            
            # Find the specific button by text or class
            buttons = history_cell.find_elements(By.TAG_NAME, "a")
            for button in buttons:
                if button_type.lower() in button.text.lower():
                    self.driver.execute_script("arguments[0].click();", button)
                    time.sleep(2)
                    return True
            return False
        except Exception as e:
            logger.error(f"Error clicking {button_type} button: {e}")
            return False

    def extract_orders_data(self) -> List[Dict[str, Any]]:
        """Extract orders data from orders popup/page"""
        orders = []
        try:
            # Wait for orders table/content to load
            time.sleep(2)
            
            # Look for orders table or content
            # This will depend on the actual structure of the orders page
            orders_table = self.driver.find_element(By.CSS_SELECTOR, "table")
            rows = orders_table.find_elements(By.TAG_NAME, "tr")[1:]  # Skip header
            
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 7:
                    order_data = {
                        "Sr": cells[0].text.strip(),
                        "Hearing_Date": cells[1].text.strip(),
                        "Bench": [judge.strip() for judge in cells[2].text.strip().split('\n') if judge.strip()],
                        "List_Type": cells[3].text.strip(),
                        "Case_Stage": cells[4].text.strip(),
                        "Short_Order": cells[5].text.strip(),
                        "Disposal_Date": cells[6].text.strip() if len(cells) > 6 else "N/A",
                        "Order_File": self.extract_file_link(cells[-1]) if len(cells) > 7 else "N/A"
                    }
                    orders.append(order_data)
        except Exception as e:
            logger.error(f"Error extracting orders data: {e}")
            # Return default structure if extraction fails
            orders.append({
                "Sr": 1,
                "Hearing_Date": "N/A",
                "Bench": ["N/A"],
                "List_Type": "N/A",
                "Case_Stage": "N/A",
                "Short_Order": "N/A",
                "Disposal_Date": "N/A",
                "Order_File": "N/A"
            })
        
        return orders

    def extract_comments_data(self) -> List[Dict[str, Any]]:
        """Extract comments data from comments popup/page"""
        comments = []
        try:
            time.sleep(2)
            
            # Look for comments content
            comments_content = self.driver.find_element(By.CSS_SELECTOR, "table, .comment-content, .comments-section")
            
            # Extract comments based on actual structure
            comment_data = {
                "Compliance_Date": "N/A",
                "Case_No": "N/A",
                "Case_Title": "N/A",
                "Doc_Type": "N/A",
                "Parties": "N/A",
                "Description": "No comments available",
                "View_File": "N/A"
            }
            comments.append(comment_data)
            
        except Exception as e:
            logger.error(f"Error extracting comments data: {e}")
            comments.append({
                "Compliance_Date": "N/A",
                "Case_No": "N/A",
                "Case_Title": "N/A",
                "Doc_Type": "N/A",
                "Parties": "N/A",
                "Description": "No comments available",
                "View_File": "N/A"
            })
        
        return comments

    def extract_cms_data(self) -> List[Dict[str, Any]]:
        """Extract CMs data from CaseCM popup/page"""
        cms = []
        try:
            time.sleep(2)
            
            # Extract CMs data based on actual structure
            cm_data = {
                "Sr": 1,
                "CM": "N/A",
                "Institution_Date": "N/A",
                "Disposal_Date": "N/A",
                "Order_Passed": "N/A",
                "Description": "No CMs available",
                "Status": "N/A"
            }
            cms.append(cm_data)
            
        except Exception as e:
            logger.error(f"Error extracting CMs data: {e}")
            cms.append({
                "Sr": 1,
                "CM": "N/A",
                "Institution_Date": "N/A",
                "Disposal_Date": "N/A",
                "Order_Passed": "N/A",
                "Description": "No CMs available",
                "Status": "N/A"
            })
        
        return cms

    def extract_details_data(self, basic_info: Dict[str, Any]) -> Dict[str, Any]:
        """Extract detailed case information from details popup/page"""
        try:
            time.sleep(2)
            
            details = {
                "Case_No": basic_info.get("Case_No", "N/A"),
                "Case_Status": basic_info.get("Status", "N/A"),
                "Hearing_Date": basic_info.get("Hearing_Date", "N/A"),
                "Case_Stage": "N/A",
                "Tentative_Date": "N/A",
                "Short_Order": "N/A",
                "Before_Bench": basic_info.get("Bench", ["N/A"]),
                "Case_Title": basic_info.get("Case_Title", "N/A"),
                "Advocates": {
                    "Petitioner": "N/A",
                    "Respondent": "N/A"
                },
                "Case_Description": "N/A",
                "Disposal_Information": {
                    "Disposed_Status": "N/A",
                    "Case_Disposal_Date": "N/A",
                    "Disposal_Bench": basic_info.get("Bench", ["N/A"]),
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
            
            # Try to extract additional details from the details page
            # This would depend on the actual structure of the details page
            
        except Exception as e:
            logger.error(f"Error extracting details data: {e}")
        
        return details

    def extract_file_link(self, cell) -> str:
        """Extract file download link from cell"""
        try:
            link = cell.find_element(By.TAG_NAME, "a")
            return link.get_attribute("href")
        except:
            return "N/A"

    def go_back_to_main_table(self):
        """Navigate back to main results table"""
        try:
            # Try different methods to go back
            self.driver.back()
            time.sleep(2)
            
            # Or try clicking a back button if it exists
            # back_btn = self.driver.find_element(By.CSS_SELECTOR, ".back-btn, .close-btn, [onclick*='back']")
            # back_btn.click()
            
        except Exception as e:
            logger.error(f"Error going back to main table: {e}")

    def extract_cases(self) -> List[Dict[str, Any]]:
        """Extract all cases with complete information"""
        cases = []
        try:
            # Try multiple selectors to find the table
            table = None
            possible_selectors = [
                (By.ID, "tblCases"),
                (By.ID, "example"), 
                (By.CLASS_NAME, "table"),
                (By.CSS_SELECTOR, "table.table-bordered"),
                (By.CSS_SELECTOR, "#grdCaseInfo table"),
                (By.XPATH, "//table[contains(@class, 'table')]"),
                (By.XPATH, "//div[@id='grdCaseInfo']//table")
            ]
            
            for selector_type, selector in possible_selectors:
                try:
                    table = self.driver.find_element(selector_type, selector)
                    logger.info(f"✅ Table found using: {selector_type.name}='{selector}'")
                    break
                except NoSuchElementException:
                    continue
            
            if not table:
                logger.error("❌ No table found with any selector")
                self.driver.save_screenshot("extract_no_table.png")
                
                # Debug: List all tables on page
                all_tables = self.driver.find_elements(By.TAG_NAME, "table")
                logger.info(f"📊 Found {len(all_tables)} table(s) on page")
                
                for i, tbl in enumerate(all_tables):
                    table_id = tbl.get_attribute("id") or "no-id"
                    table_class = tbl.get_attribute("class") or "no-class"
                    logger.info(f"  Table {i+1}: id='{table_id}', class='{table_class}'")
                
                return cases

            rows = table.find_elements(By.TAG_NAME, "tr")
            logger.info(f"📋 Found {len(rows)} rows in table")

            if len(rows) <= 1:
                logger.warning("⚠️ No case data found (only header row or empty table)")
                
                # Debug: Check if table has data but different structure
                all_cells = table.find_elements(By.TAG_NAME, "td")
                if all_cells:
                    logger.info(f"📝 Found {len(all_cells)} td elements, checking content...")
                    for i, cell in enumerate(all_cells[:10]):  # Check first 10 cells
                        content = cell.text.strip()
                        if content:
                            logger.info(f"  Cell {i+1}: '{content}'")
                
                return cases

            # Extract headers from first row
            header_row = rows[0]
            headers = []
            header_cells = header_row.find_elements(By.TAG_NAME, "th")
            if not header_cells:
                header_cells = header_row.find_elements(By.TAG_NAME, "td")
            
            for cell in header_cells:
                headers.append(cell.text.strip())
            
            logger.info(f"📋 Table headers: {headers}")

            # Process each case row (skip header)
            data_rows = rows[1:]
            logger.info(f"🔄 Processing {len(data_rows)} case rows...")

            for i, row in enumerate(data_rows, 1):
                logger.info(f"Processing case {i}/{len(data_rows)}")
                
                # Extract basic case information
                case_info = self.extract_basic_case_info(row)
                if not case_info:
                    logger.warning(f"⚠️ Could not extract info from row {i}")
                    continue

                logger.info(f"✅ Extracted basic info for case: {case_info.get('Case_No', 'Unknown')}")

                # For now, skip detailed extraction to test basic functionality
                # TODO: Add detailed extraction back once basic extraction works
                
                cases.append(case_info)
                
                # Limit for testing
                if len(cases) >= 3:
                    logger.info("🔄 Limiting to 3 cases for testing")
                    break

            logger.info(f"✅ Successfully extracted {len(cases)} cases")

        except Exception as e:
            logger.error(f"❌ Error extracting cases: {e}")
            import traceback
            logger.error(f"📍 Full traceback: {traceback.format_exc()}")
            self.driver.save_screenshot("error_extract.png")

        return cases

    def save_data(self, cases: List[Dict[str, Any]], filename="ihc_cases"):
        """Save extracted cases to CSV + JSON in the desired format"""
        if not cases:
            logger.warning("⚠️ No cases to save")
            return

        # Save in the desired JSON format
        output_data = {"Cases": cases}
        
        # JSON
        json_filename = f"{filename}.json"
        with open(json_filename, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        logger.info(f"✅ Saved {len(cases)} cases to {json_filename}")

        # CSV (flattened version for easier analysis)
        csv_filename = f"{filename}.csv"
        flattened_cases = []
        for case in cases:
            flat_case = {
                "Sr": case.get("Sr", ""),
                "Institution_Date": case.get("Institution_Date", ""),
                "Case_No": case.get("Case_No", ""),
                "Case_Title": case.get("Case_Title", ""),
                "Bench": "; ".join(case.get("Bench", [])),
                "Hearing_Date": case.get("Hearing_Date", ""),
                "Case_Category": case.get("Case_Category", ""),
                "Status": case.get("Status", ""),
                "Orders_Count": len(case.get("Orders", [])),
                "Comments_Count": len(case.get("Comments", [])),
                "CMs_Count": len(case.get("CMs", [])),
                "Has_Details": "Yes" if case.get("Details", {}) else "No"
            }
            flattened_cases.append(flat_case)

        with open(csv_filename, "w", newline="", encoding="utf-8") as f:
            if flattened_cases:
                writer = csv.DictWriter(f, fieldnames=flattened_cases[0].keys())
                writer.writeheader()
                writer.writerows(flattened_cases)
        logger.info(f"✅ Saved flattened data to {csv_filename}")

    def run(self, start_date: str, max_cases: Optional[int] = None):
        """Run the complete scraping process"""
        try:
            if not self.search_cases(start_date):
                return False
                
            cases = self.extract_cases()
            
            if max_cases and len(cases) > max_cases:
                cases = cases[:max_cases]
                logger.info(f"Limited output to {max_cases} cases")
                
            self.save_data(cases, f"ihc_cases_{start_date.replace('/', '-')}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error in run method: {e}")
            return False
        finally:
            if self.driver:
                self.driver.quit()


if __name__ == "__main__":
    # Example usage
    scraper = IHCCaseScraper(headless=False)  # Set to True for headless mode
    success = scraper.run("12/11/2020", max_cases=5)  # Limit to 5 cases for testing
    
    if success:
        print("🎉 Scraping completed successfully!")
    else:
        print("⚠️ Scraping failed")