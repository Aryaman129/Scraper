import time
import json
import os
import re
import logging
import traceback
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from supabase import create_client, Client
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime, timedelta
import jwt
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
import hashlib
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import functools
import logging.handlers

# Load environment variables from .env file
load_dotenv()

# ====== Logging Setup ======
# Set up logging BEFORE calling any functions that use it
def setup_logging():
    """
    Setup comprehensive logging with rotation to prevent log files from growing too large.
    This helps with troubleshooting in production environments.
    """
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Remove any existing handlers to prevent duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Console handler for immediate feedback
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console.setFormatter(console_format)
    logger.addHandler(console)
    
    # Rotating file handler to prevent huge log files
    rotating = logging.handlers.RotatingFileHandler(
        filename="logs/scraper.log",
        maxBytes=10485760,  # 10MB
        backupCount=10
    )
    rotating.setLevel(logging.DEBUG)  # More detailed in file
    file_format = logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
    rotating.setFormatter(file_format)
    logger.addHandler(rotating)
    
    # Set up a special error log for critical issues
    error_log = logging.handlers.RotatingFileHandler(
        filename="logs/errors.log",
        maxBytes=5242880,  # 5MB
        backupCount=5
    )
    error_log.setLevel(logging.ERROR)
    error_log.setFormatter(file_format)
    logger.addHandler(error_log)
    
    # Log startup message
    logger.info("==== SRM Scraper Starting ====")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Current directory: {os.getcwd()}")
    
    return logger

logger = setup_logging()

# Environment variable logging for Render debugging
def log_environment():
    """Log environment variables to help debug Render deployment"""
    logger.info("=== Environment Variables ===")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Current directory: {os.getcwd()}")
    for key in ["PORT", "PYTHONUNBUFFERED", "PATH", "RENDER", "RENDER_SERVICE_ID"]:
        if key in os.environ:
            logger.info(f"{key}: {os.environ[key]}")
    logger.info("===========================")

# Call environment logging AFTER logger is defined
log_environment()

# ====== Supabase Configuration ======
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ====== URLs and Constants ======
BASE_URL = "https://academia.srmist.edu.in"
LOGIN_URL = BASE_URL
ATTENDANCE_PAGE_URL = BASE_URL + "/#Page:My_Attendance"
TIMETABLE_URL = BASE_URL + "/#Page:My_Time_Table_2023_24"

# Time slots mapping (for display only)
slot_times = {
    "1": "08:00-08:50",
    "2": "08:50-09:40",
    "3": "09:45-10:35",
    "4": "10:40-11:30",
    "5": "11:35-12:25",
    "6": "12:30-01:20",
    "7": "01:25-02:15",
    "8": "02:20-03:10",
    "9": "03:10-04:00",
    "10": "04:00-04:50",
    "11": "04:50-05:30",
    "12": "05:30-06:10"
}

# Hard-coded official timetables for two batches
batch_1_timetable = {
    "Day 1": {
        slot_times["1"]: "A", slot_times["2"]: "A/X", slot_times["3"]: "F/X", slot_times["4"]: "F",
        slot_times["5"]: "G", slot_times["6"]: "P6-", slot_times["7"]: "P7-", slot_times["8"]: "P8-",
        slot_times["9"]: "P9-", slot_times["10"]: "P10-", slot_times["11"]: "L11", slot_times["12"]: "L11"
    },
    "Day 2": {
        slot_times["1"]: "P11-", slot_times["2"]: "P12-/X", slot_times["3"]: "P13-/X", slot_times["4"]: "P14-",
        slot_times["5"]: "P15-", slot_times["6"]: "B", slot_times["7"]: "B", slot_times["8"]: "G",
        slot_times["9"]: "G", slot_times["10"]: "A", slot_times["11"]: "L21", slot_times["12"]: "L22"
    },
    "Day 3": {
        slot_times["1"]: "C", slot_times["2"]: "C/X", slot_times["3"]: "A/X", slot_times["4"]: "D",
        slot_times["5"]: "B", slot_times["6"]: "P26-", slot_times["7"]: "P27-", slot_times["8"]: "P28-",
        slot_times["9"]: "P29-", slot_times["10"]: "P30-", slot_times["11"]: "L31", slot_times["12"]: "L32"
    },
    "Day 4": {
        slot_times["1"]: "P31-", slot_times["2"]: "P32-/X", slot_times["3"]: "P33-/X", slot_times["4"]: "P34-",
        slot_times["5"]: "P35-", slot_times["6"]: "D", slot_times["7"]: "D", slot_times["8"]: "B",
        slot_times["9"]: "E", slot_times["10"]: "C", slot_times["11"]: "L41", slot_times["12"]: "L42"
    },
    "Day 5": {
        slot_times["1"]: "E", slot_times["2"]: "E/X", slot_times["3"]: "C/X", slot_times["4"]: "F",
        slot_times["5"]: "D", slot_times["6"]: "P46-", slot_times["7"]: "P47-", slot_times["8"]: "P48-",
        slot_times["9"]: "P49-", slot_times["10"]: "P50-", slot_times["11"]: "L51", slot_times["12"]: "L52"
    }
}

batch_2_timetable = {
    "Day 1": {
        slot_times["1"]: "P1-", slot_times["2"]: "P2-/X", slot_times["3"]: "P3-/X", slot_times["4"]: "P4-",
        slot_times["5"]: "P5-", slot_times["6"]: "A", slot_times["7"]: "A", slot_times["8"]: "F",
        slot_times["9"]: "F", slot_times["10"]: "G", slot_times["11"]: "L11", slot_times["12"]: "L12"
    },
    "Day 2": {
        slot_times["1"]: "B", slot_times["2"]: "B/X", slot_times["3"]: "G/X", slot_times["4"]: "G",
        slot_times["5"]: "A", slot_times["6"]: "P16-", slot_times["7"]: "P17-", slot_times["8"]: "P18-",
        slot_times["9"]: "P19-", slot_times["10"]: "P20-", slot_times["11"]: "L21", slot_times["12"]: "L22"
    },
    "Day 3": {
        slot_times["1"]: "P21-", slot_times["2"]: "P22-/X", slot_times["3"]: "P23-/X", slot_times["4"]: "P24-",
        slot_times["5"]: "P25-", slot_times["6"]: "C", slot_times["7"]: "C", slot_times["8"]: "A",
        slot_times["9"]: "D", slot_times["10"]: "B", slot_times["11"]: "L31", slot_times["12"]: "L32"
    },
    "Day 4": {
        slot_times["1"]: "D", slot_times["2"]: "D/X", slot_times["3"]: "B/X", slot_times["4"]: "E",
        slot_times["5"]: "C", slot_times["6"]: "P36-", slot_times["7"]: "P37-", slot_times["8"]: "P38-",
        slot_times["9"]: "P39-", slot_times["10"]: "P40-", slot_times["11"]: "L41", slot_times["12"]: "L42"
    },
    "Day 5": {
        slot_times["1"]: "P41-", slot_times["2"]: "P42-/X", slot_times["3"]: "P43-/X", slot_times["4"]: "P44-",
        slot_times["5"]: "P45-", slot_times["6"]: "E", slot_times["7"]: "E", slot_times["8"]: "C",
        slot_times["9"]: "F", slot_times["10"]: "D", slot_times["11"]: "L51", slot_times["12"]: "L52"
    }
}

class SRMScraper:
    """
    Unified scraper for SRM Academia portal data.
    Handles both timetable and attendance scraping with a single browser session.
    """
    def __init__(self, email, password):
        self.driver = None
        self.is_logged_in = False
        self.email = email
        self.password = password
        
    def setup_driver(self):
        """Initialize Chrome driver with robust fallback mechanisms"""
        logger.info("Setting up Chrome driver with enhanced robustness...")
        
        # Use the globally imported Options
        chrome_options = Options()
        
        # Core headless settings with multiple user agents to try
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
        
        # Container optimization flags
        container_flags = [
            '--headless',
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--disable-software-rasterizer',
            '--disable-extensions',
            '--disable-web-security',
            '--allow-running-insecure-content',
            '--disable-features=IsolateOrigins',
            '--disable-site-isolation-trials',
            '--disable-content-security-policy',
            '--window-size=1920,1080',
            '--start-maximized',
            '--disable-blink-features=AutomationControlled'
        ]
        
        # Memory optimization flags
        memory_flags = [
            '--disable-renderer-backgrounding',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-client-side-phishing-detection',
            '--memory-pressure-off'
        ]
        
        # Apply all flags
        for flag in container_flags + memory_flags:
            chrome_options.add_argument(flag)
        
        # Set experimental options
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Try to initialize driver with progressively more aggressive fallbacks
        for attempt in range(5):
            logger.info(f"Chrome driver initialization attempt {attempt+1}/5")
            
            # Set a different user agent for each attempt
            if attempt < len(user_agents):
                chrome_options.add_argument(f'--user-agent="{user_agents[attempt]}"')
            
            # Try different initialization strategies based on attempt number
            try:
                if attempt == 0:
                    # Standard approach
                    logger.info("Trying standard ChromeDriver initialization...")
                    self.driver = webdriver.Chrome(options=chrome_options)
                elif attempt == 1:
                    # Try with explicit binary location
                    logger.info("Trying with explicit Chrome binary location...")
                    chrome_options.binary_location = "/usr/bin/google-chrome-stable"
                    self.driver = webdriver.Chrome(options=chrome_options)
                elif attempt == 2:
                # Try with webdriver-manager
                    logger.info("Trying with webdriver-manager...")
                    service = Service(ChromeDriverManager().install())
                    self.driver = webdriver.Chrome(service=service, options=chrome_options)
                elif attempt == 3:
                    # Try with undetected-chromedriver
                    logger.info("Trying with undetected-chromedriver...")
                    import undetected_chromedriver as uc
                    self.driver = uc.Chrome(headless=True, options=chrome_options)
                elif attempt == 4:
                    # Last resort: try remote debugging approach
                    logger.info("Trying with remote debugging port approach...")
                    import subprocess
                    import time
                    
                    # Start Chrome in background with remote debugging
                    debug_port = 9222
                    chrome_cmd = [
                        "/usr/bin/google-chrome-stable",
                        f"--remote-debugging-port={debug_port}",
                        "--headless",
                        "--no-sandbox",
                        "--disable-gpu"
                    ]
                    chrome_process = subprocess.Popen(chrome_cmd)
                    time.sleep(3)
                    
                    # Connect to the running Chrome instance
                    # Use the Options class that was already imported at the top of the file
                    chrome_options = Options()
                    chrome_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{debug_port}")
                    self.driver = webdriver.Chrome(options=chrome_options)
                
                logger.info("✅ Chrome driver successfully initialized!")
                
                # Log driver capabilities for debugging
                try:
                    caps = self.driver.capabilities
                    browser_name = caps.get('browserName', 'unknown')
                    browser_version = caps.get('browserVersion', 'unknown')
                    logger.info(f"Browser: {browser_name} {browser_version}")
                except:
                    pass
                    
                # Apply timeouts
                self.apply_timeouts()
                return self.driver
                
            except Exception as e:
                logger.warning(f"⚠️ Driver initialization attempt {attempt+1} failed: {e}")
                if hasattr(self, 'driver') and self.driver:
                    try:
                        self.driver.quit()
                    except:
                        pass
                    self.driver = None
                
                # Short delay before next attempt
                time.sleep(2)
        
        # If we get here, all attempts failed
        logger.error("❌ ALL DRIVER INITIALIZATION ATTEMPTS FAILED")
        raise Exception("Failed to initialize Chrome driver after multiple strategies")

    def ensure_login(self):
        """Login if not already logged in, or reuse existing session"""
        # If already logged in, return True
        if self.is_logged_in:
            return True
            
        # Initialize driver if needed
        if not self.driver:
            self.setup_driver()
            
        # Perform login
        return self.login()
    
    def create_jwt_token(self, email):
        """Create a JWT token with 30-day expiration"""
        try:
            expiration = datetime.utcnow() + timedelta(days=30)
            token = jwt.encode(
                {
                    'email': email,
                    'exp': expiration
                },
                os.getenv('JWT_SECRET_KEY', 'your-secret-key'),  # Make sure to set this in .env
                algorithm='HS256'
            )
            logger.info("✅ Created JWT token with 30-day expiration")
            return token
        except Exception as e:
            logger.error(f"❌ Failed to create JWT token: {e}")
            return None

    def login(self):
        """Ultra-robust login with multiple fallback strategies"""
        logger.info(f"Attempting login for user: {self.email}")
        
        # Track various metrics for debugging
        metrics = {
            "attempts": 0,
            "page_loads": 0,
            "iframe_attempts": 0,
            "login_form_attempts": 0
        }
        
        # We'll try the entire login process up to 3 times
        for login_attempt in range(3):
            metrics["attempts"] += 1
            logger.info(f"🔄 Login attempt {login_attempt+1}/3")
            
            try:
                # 1. Load the login page with retry logic
                page_loaded = False
                for page_attempt in range(3):
                    metrics["page_loads"] += 1
                    try:
                        logger.info(f"Loading login page (attempt {page_attempt+1}/3)")
                        self.driver.get(LOGIN_URL)
                        
                        # Wait for page to load
                        WebDriverWait(self.driver, 20).until(
                            lambda d: d.execute_script('return document.readyState') == 'complete'
                        )
                        
                        # Take screenshot for debugging
                        try:
                            self.driver.save_screenshot(f"/tmp/login_page_{login_attempt}_{page_attempt}.png")
                            logger.info(f"Screenshot saved of login page")
                        except Exception as ss_err:
                            logger.warning(f"Failed to save login page screenshot: {ss_err}")
                        
                        # Verify we have loaded something reasonable
                        if "SRM" in self.driver.title or "academia" in self.driver.current_url.lower():
                            logger.info("✅ Login page loaded successfully")
                            page_loaded = True
                            break
                        else:
                            logger.warning(f"⚠️ Page loaded but may not be correct login page. Title: {self.driver.title}")
                            # Continue anyway, maybe it's still workable
                            page_loaded = True
                            break
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to load login page on attempt {page_attempt+1}: {e}")
                        time.sleep(3)
                        
                        if not page_loaded:
                            logger.error("❌ Failed to load login page after multiple attempts")
                            continue  # Try the entire login process again
            except Exception as e:
                logger.warning(f"⚠️ Failed to load login page on attempt {page_attempt+1}: {e}")
                time.sleep(3)
                
                if not page_loaded:
                    logger.error("❌ Failed to load login page after multiple attempts")
                    continue  # Try the entire login process again
                
                # 2. Advanced iframe handling with multiple strategies
                iframe_strategies = [
                    {"name": "signinFrame", "by": By.ID, "value": "signinFrame"},
                    {"name": "previewIframe", "by": By.NAME, "value": "previewIframe"},
                    {"name": "wmspconnect", "by": By.NAME, "value": "wmspconnect"},
                    {"name": "any iframe", "by": None, "value": None},
                ]
                
                iframe_success = False
                for strategy in iframe_strategies:
                    metrics["iframe_attempts"] += 1
                    
                    if strategy["by"] is None:
                        # This is the "any iframe" strategy
                        logger.info("Trying to find ANY iframe on the page...")
                        try:
                            # Wait for at least one iframe to be present
                            WebDriverWait(self.driver, 10).until(
                                lambda d: len(d.find_elements(By.TAG_NAME, "iframe")) > 0
                            )
                            
                            # Get all iframes
                            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                            logger.info(f"Found {len(iframes)} iframe(s)")
                            
                            # Try each iframe in order
                            for i, frame in enumerate(iframes):
                                try:
                                    # Switch to this iframe
                                    self.driver.switch_to.frame(frame)
                                    logger.info(f"✅ Successfully switched to iframe #{i+1}")
                                    
                                    # See if this iframe has any login-like elements
                                    login_elements = len(self.driver.find_elements(By.CSS_SELECTOR, 
                                        "input[type='text'], input[type='email'], input[type='password'], button[type='submit']"))
                                    
                                    if login_elements > 0:
                                        logger.info(f"✅ Iframe #{i+1} contains {login_elements} potential login elements")
                                        iframe_success = True
                                        break
                                    else:
                                        logger.info(f"Iframe #{i+1} doesn't contain login elements, trying next iframe")
                                        self.driver.switch_to.default_content()
                                except Exception as iframe_err:
                                    logger.warning(f"Error switching to iframe #{i+1}: {iframe_err}")
                                    self.driver.switch_to.default_content()
                            
                            if iframe_success:
                                break
                        except Exception as e:
                            logger.warning(f"Error in 'any iframe' strategy: {e}")
                    
                    else:
                        # This is a specific iframe strategy
                        logger.info(f"Trying iframe strategy: {strategy['name']}")
                        iframe_selector = (strategy["by"], strategy["value"])
                        
                        if self.switch_to_iframe_safely(iframe_selector, max_attempts=2):
                            logger.info(f"✅ Successfully switched to {strategy['name']} iframe")
                            iframe_success = True
                            break
                
                if not iframe_success:
                    logger.error("❌ Failed to switch to any suitable iframe")
                    
                    # Last resort: try to find login elements on the main page
                    logger.info("Trying to find login elements on the main page as last resort...")
                    self.driver.switch_to.default_content()
                    
                    login_elements = self.driver.find_elements(By.CSS_SELECTOR, 
                        "input[type='text'], input[type='email'], input[type='password'], button[type='submit']")
                    
                    if len(login_elements) > 0:
                        logger.info(f"Found {len(login_elements)} potential login elements on main page")
                        iframe_success = True
                    else:
                        # Try the entire login process again
                        continue
                
                # 3. Super-flexible login form handling
                wait = WebDriverWait(self.driver, 10)
                
                # First, analyze the page to find the best login strategy
                login_form_found = False
                login_strategy = "unknown"
                
                # Collect all potential login-related elements
                metrics["login_form_attempts"] += 1
                inputs = self.driver.find_elements(By.TAG_NAME, "input")
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                
                # Look for visible text input fields (likely username/email)
                text_inputs = [inp for inp in inputs if inp.get_attribute("type") in ["text", "email"] and self.is_element_visible(inp)]
                
                # Look for visible password fields
                password_inputs = [inp for inp in inputs if inp.get_attribute("type") == "password" and self.is_element_visible(inp)]
                
                # Look for visible submit buttons
                submit_buttons = [btn for btn in buttons if (btn.get_attribute("type") == "submit" or 
                                                         "login" in btn.text.lower() or 
                                                         "next" in btn.text.lower() or 
                                                         "sign" in btn.text.lower()) and 
                                                        self.is_element_visible(btn)]
                
                # Determine the login strategy based on visible elements
                if len(text_inputs) > 0 and len(password_inputs) > 0 and len(submit_buttons) > 0:
                    login_strategy = "single-step"
                    login_form_found = True
                    logger.info("Detected single-step login form (username + password)")
                elif len(text_inputs) > 0 and len(submit_buttons) > 0:
                    login_strategy = "two-step"
                    login_form_found = True
                    logger.info("Detected two-step login form (username first, then password)")
                else:
                    logger.warning("Could not determine login form strategy from visible elements")
                    
                if not login_form_found:
                    # Try with the find_login_elements method as fallback
                    logger.info("Using fallback method to find login elements")
                    email_field, next_btn = self.find_login_elements()
                    if email_field and next_btn:
                        login_form_found = True
                        login_strategy = "fallback"
                        logger.info("Found login elements with fallback method")
                        text_inputs = [email_field]
                        submit_buttons = [next_btn]
                
                if not login_form_found:
                    logger.error("❌ Could not find any usable login form")
                    # Take a full screenshot for debugging
                    try:
                        self.driver.save_screenshot(f"/tmp/failed_login_form_{login_attempt}.png")
                        logger.info("Screenshot saved of failed login form detection")
                    except Exception as ss_err:
                        logger.warning(f"Failed to save login form screenshot: {ss_err}")
                        
                    # Try again with the entire login process
                    continue
                
                # Now perform the actual login based on the detected strategy
                try:
                    if login_strategy == "single-step":
                        # Enter username/email
                        text_inputs[0].clear()
                        time.sleep(0.5)
                        text_inputs[0].send_keys(self.email)
                        logger.info(f"Entered email: {self.email}")
                        
                        # Enter password
                        password_inputs[0].clear()
                        time.sleep(0.5)
                        password_inputs[0].send_keys(self.password)
                        logger.info("Entered password")
                        
                        # Click submit
                        submit_buttons[0].click()
                        logger.info("Clicked submit button")
                        
                    elif login_strategy == "two-step" or login_strategy == "fallback":
                        # Enter username/email
                        text_inputs[0].clear()
                        time.sleep(0.5)
                        text_inputs[0].send_keys(self.email)
                        logger.info(f"Entered email: {self.email}")
                        
                        # Click next/submit
                        self.click_element_safely(submit_buttons[0])
                        logger.info("Clicked next button")
                        
                        # Now look for password field (should appear after clicking next)
                        time.sleep(3)  # Wait for transition
                        
                        # Try to find password field
                        password_field = None
                        for find_attempt in range(3):
                            try:
                                # First check if we need to switch iframe context again
                                try:
                                    password_field = self.driver.find_element(By.ID, "password")
                                except Exception:
                                    logger.info("Password field not found directly, checking iframe context")
                                    # Maybe we're back to default content or in a different iframe
                                    self.driver.switch_to.default_content()
                                    
                                    # Look for iframe again
                                    for strategy in iframe_strategies:
                                        if strategy["by"] is not None:
                                            iframe_selector = (strategy["by"], strategy["value"])
                                            if self.switch_to_iframe_safely(iframe_selector, max_attempts=1):
                                                logger.info(f"Switched to {strategy['name']} iframe for password field")
                                                break
                                # Look for password field again with multiple selectors
                                for selector in [
                                    (By.ID, "password"),
                                    (By.NAME, "password"),
                                    (By.CSS_SELECTOR, "input[type='password']")
                                ]:
                                    try:
                                        password_field = wait.until(EC.element_to_be_clickable(selector))
                                        logger.info(f"Found password field with selector: {selector}")
                                        break
                                    except:
                                        continue
                                
                                if password_field:
                                    break
                                    
                            except Exception as pw_err:
                                logger.warning(f"Error finding password field (attempt {find_attempt+1}): {pw_err}")
                        time.sleep(2)

                        if not password_field:
                            logger.error("❌ Could not find password field after clicking next")
            
                            # Take screenshot for debugging
                        try:
                            self.driver.save_screenshot(f"/tmp/password_field_not_found_{login_attempt}.png")
                        except:
                           pass
                                
                            # Try the entire login process again
                        continue
                        
                        # Enter password
                    try:
                        password_field.clear()
                        time.sleep(0.5)
                        password_field.send_keys(self.password)
                        logger.info("Entered password")
                    except Exception as pw_entry_err:
                        logger.warning(f"Error entering password: {pw_entry_err}")
                        # Try JavaScript as fallback
                        try:
                            self.driver.execute_script(
                                    'arguments[0].value = arguments[1]', 
                                    password_field, self.password
                            )
                            logger.info("Entered password via JavaScript")
                        except Exception as js_err:
                            logger.error(f"Failed to enter password via JavaScript: {js_err}")
                            continue
                        
                        # Find and click Sign In button
                        sign_in_button = None
                        for selector in [
                            (By.ID, "nextbtn"),
                            (By.CSS_SELECTOR, "button[type='submit']"),
                            (By.XPATH, "//button[contains(text(), 'Sign')]"),
                            (By.XPATH, "//button[contains(text(), 'Login')]"),
                            (By.XPATH, "//input[@type='submit']"),
                        ]:
                            try:
                                sign_in_button = wait.until(EC.element_to_be_clickable(selector))
                                logger.info(f"Found sign in button with selector: {selector}")
                                break
                            except:
                                continue
                        
                        if not sign_in_button:
                            logger.error("❌ Could not find sign in button")
                            continue
                        
                        # Click sign in button
                        self.click_element_safely(sign_in_button)
                        logger.info("Clicked sign in button")
                
                except Exception as login_err:
                    logger.error(f"❌ Error during login form submission: {login_err}")
                    continue
                
                # 4. Verify login success with multiple indicators
                time.sleep(5)  # Wait for login to complete
            
            # Switch back to default content
            self.driver.switch_to.default_content()
            
                # Take screenshot for debugging
            try:
                    self.driver.save_screenshot(f"/tmp/post_login_{login_attempt}.png")
                    logger.info("Screenshot saved of post-login page")
            except Exception as ss_err:
                    logger.warning(f"Failed to save post-login screenshot: {ss_err}")
                
                # Check for login success indicators
            login_successful = False
                
                # Strategy 1: Check URL
            if BASE_URL in self.driver.current_url and "login" not in self.driver.current_url.lower():
                    logger.info("URL indicates successful login")
                    login_successful = True
                
                # Strategy 2: Check for dashboard elements
            if not login_successful:
                    try:
                        dashboard_elements = self.driver.find_elements(By.XPATH, 
                                                                   "//a[contains(@href, 'My_Attendance') or contains(@href, 'Dashboard')]")
                        if dashboard_elements:
                            logger.info(f"Found {len(dashboard_elements)} dashboard elements")
                            login_successful = True
                    except:
                        pass
                
                # Strategy 3: Check for user-specific content
            if not login_successful:
                    page_source = self.driver.page_source.lower()
                    if "log out" in page_source or "sign out" in page_source or "logout" in page_source or "signout" in page_source:
                        logger.info("Found logout option, indicating successful login")
                        login_successful = True
                
            if login_successful:
                    logger.info("✅ Login verified as successful")
                    
                    # Extract cookies with retry
                    cookies_extracted = False
                    for cookie_attempt in range(3):
                        try:
                            cookies = self.driver.get_cookies()
                            cookie_dict = {cookie['name']: cookie['value'] for cookie in cookies}
                            logger.info(f"✅ Extracted {len(cookie_dict)} cookies: {list(cookie_dict.keys())}")
                            cookies_extracted = True
                            break
                        except Exception as cookie_err:
                            logger.warning(f"Error extracting cookies (attempt {cookie_attempt+1}): {cookie_err}")
                            time.sleep(2)
                            # Generate JWT token
                            token = self.create_jwt_token(self.email)
                    
                            if not token:
                                raise Exception("Failed to generate JWT token")
                            
                            # Save to Supabase with robust retry
                            for db_attempt in range(3):
                                try:
                                    cookie_data = {
                                        'email': self.email,
                                        'cookies': cookie_dict,
                                        'token': token,
                                        'updated_at': datetime.now().isoformat()
                                    }
                                    
                                    # Delete old record first
                                    supabase.table('user_cookies').delete().eq('email', self.email).execute()
                                    logger.info("✅ Deleted old cookie record")
                                    
                                    # Insert new record
                                    result = supabase.table('user_cookies').insert(cookie_data).execute()
                                    logger.info("✅ Stored new cookie record with token")
                                    cookies_extracted = True
                                    break
                                except Exception as db_err:
                                    logger.warning(f"Error saving cookies to database (attempt {db_attempt+1}): {db_err}")
                                    time.sleep(2)
                                    
                                    if cookies_extracted:
                                        break
                                except Exception as cookie_err:
                                    logger.warning(f"Error extracting cookies (attempt {cookie_attempt+1}): {cookie_err}")
                                    time.sleep(2)
                    
                    self.is_logged_in = True
                
                    # Log metrics for debugging
                    logger.info(f"Login success metrics: {metrics}")
                    return True
        
        # If we get here, all login attempts failed
        logger.error(f"❌ ALL LOGIN ATTEMPTS FAILED. Metrics: {metrics}")
        return False
                
    def is_element_visible(self, element):
        """Check if an element is visible on the page"""
        try:
            return element.is_displayed() and element.size['height'] > 0 and element.size['width'] > 0
        except:
            return False

    def click_element_safely(self, element):
        """Try multiple methods to click an element"""
        try:
            # Try standard click first
            element.click()
            return True
        except Exception as e:
            logger.warning(f"Standard click failed: {e}, trying JavaScript click")
            try:
                # Try JavaScript click
                self.driver.execute_script("arguments[0].click();", element)
                return True
            except Exception as js_err:
                logger.warning(f"JavaScript click failed: {js_err}, trying ActionChains")
                try:
                    # Try ActionChains
                    from selenium.webdriver.common.action_chains import ActionChains
                    ActionChains(self.driver).move_to_element(element).click().perform()
                    return True
                except Exception as ac_err:
                    logger.error(f"All click methods failed: {ac_err}")
            return False

    def get_attendance_page(self):
        """Navigate to attendance page and get HTML with better load detection"""
        if not self.ensure_login():
            return None
            
        logger.info("Navigating to attendance page")
        self.driver.get(ATTENDANCE_PAGE_URL)
        
        # First, give it a reasonable time to start loading
        initial_wait = 15  # seconds
        logger.info(f"Waiting initial {initial_wait} seconds for page to load")
        time.sleep(initial_wait)
        
        # Then check for the marks message text that indicates the page is fully loaded
        max_additional_wait = 15  # total max wait will be initial_wait + max_additional_wait
        marks_text = "Internal Marks Detail will be updated after each assessment has been conducted."
        
        try:
            logger.info("Looking for marks text to confirm page is fully loaded")
            wait = WebDriverWait(self.driver, max_additional_wait)
            wait.until(EC.text_to_be_present_in_element(
                (By.XPATH, "//*[contains(text(), 'Internal Marks Detail')]"),
                marks_text
            ))
            logger.info("✅ Attendance page fully loaded with marks section")
        except Exception as e:
            logger.warning(f"Could not find marks text after waiting: {e}")
            # Try looking for other indicators that the page loaded correctly
            try:
                logger.info("Looking for attendance table as fallback")
                wait = WebDriverWait(self.driver, 5)  # Short additional wait
                wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//table[contains(., 'Course Code')]")
                ))
                logger.info("✅ Found attendance table, proceeding")
            except Exception as e2:
                logger.error(f"Could not verify page loaded correctly: {e2}")
                logger.info("Continuing anyway, but data may be incomplete")
        
        html_source = self.driver.page_source
        return html_source

    def extract_registration_number(self, soup):
        """Extract registration number from page HTML"""
        registration_number = None
        label_td = soup.find("td", string=lambda text: text and "Registration Number" in text)
        if label_td:
            value_td = label_td.find_next("td")
            if value_td:
                strong_elem = value_td.find("strong") or value_td.find("b")
                if strong_elem:
                    registration_number = strong_elem.get_text(strip=True)
                else:
                    registration_number = value_td.get_text(strip=True)
        if not registration_number:
            for row in soup.find_all("tr"):
                tds = row.find_all("td")
                if len(tds) >= 2 and "Registration" in tds[0].get_text():
                    registration_number = tds[1].get_text(strip=True)
                    break
        if not registration_number:
            import re
            match = re.search(r'RA\d{10,}', soup.get_text())
            if match:
                registration_number = match.group(0)
        return registration_number

    def get_user_id_robust(self, registration_number):
        """Get or create user ID in Supabase with robust error handling"""
        max_attempts = 3
        backoff_factor = 2  # Exponential backoff
        
        for attempt in range(max_attempts):
            try:
                # First try to get the user by email
                logger.info(f"Looking up user by email: {self.email}")
                resp = supabase.table("users").select("id, registration_number").eq("email", self.email).single().execute()
                user = resp.data
                
                if user:
                    # User exists - check if we need to update registration number
                    if registration_number and (not user.get("registration_number") or 
                                              user.get("registration_number") != registration_number):
                        logger.info(f"Updating registration number for existing user: {registration_number}")
                        try:
                            supabase.table("users").update({"registration_number": registration_number})\
                                .eq("id", user["id"]).execute()
                        except Exception as update_err:
                            logger.warning(f"Failed to update registration number, but continuing: {update_err}")
                    
                    logger.info(f"✅ Found existing user with ID: {user['id']}")
                    return user["id"]
                
            except Exception as e:
                logger.error(f"❌ Exception during user lookup (attempt {attempt+1}/{max_attempts}): {e}")
                traceback.print_exc()
                metrics["user_lookup_errors"].append(str(e))
                time.sleep(backoff_factor ** attempt)
                
                # If no user found, try looking up by registration number as fallback
            if registration_number:
                    logger.info(f"Looking up user by registration number: {registration_number}")
                    try:
                        reg_resp = supabase.table("users").select("id")\
                            .eq("registration_number", registration_number).execute()
                        
                        if reg_resp.data and len(reg_resp.data) > 0:
                            user_id = reg_resp.data[0]["id"]
                            logger.info(f"✅ Found user by registration number with ID: {user_id}")
                            
                            # Update the email field to match current email
                            try:
                                supabase.table("users").update({"email": self.email})\
                                    .eq("id", user_id).execute()
                                logger.info(f"Updated email for user {user_id}")
                            except Exception as email_err:
                                logger.warning(f"Failed to update email, but continuing: {email_err}")
                                
                            return user_id
                    except Exception as reg_err:
                        logger.warning(f"Error looking up by registration: {reg_err}, will create new user")
                
                # Create a new user with the available information
                        logger.info("Creating new user")
        new_user = {
            "email": self.email,
                    "registration_number": registration_number or "",
                    "password_hash": generate_password_hash("temporary_password_" + str(int(time.time()))),
                    "created_at": datetime.now().isoformat()
        }
                
        insert_resp = supabase.table("users").insert(new_user).execute()
        if insert_resp.data and len(insert_resp.data) > 0:
                    user_id = insert_resp.data[0]["id"]
                    logger.info(f"✅ Created new user with ID: {user_id}")
                    return user_id
        else:
                    raise Exception("Insert returned no data")
                

    def parse_and_save_attendance_robust(self, html, user_id):
        """Parse attendance data and save to Supabase with robust error handling"""
        try:
            logger.info("Parsing and saving attendance data with enhanced robustness...")
            
            # Parse HTML with defense against malformed content
            try:
                soup = BeautifulSoup(html, "html.parser")
            except Exception as parse_err:
                logger.error(f"BeautifulSoup parsing failed: {parse_err}")
                # Try a more lenient parser
                soup = BeautifulSoup(html, "html5lib")
        except Exception as e:
                logger.error(f"BeautifulSoup parsing failed: {e}")
            # ===== Multi-strategy attendance table extraction =====
        attendance_tables = []
            
            # Strategy 1: Look for tables containing "Course Code"
        logger.info("Trying to find attendance tables containing 'Course Code'")
        tables_1 = [table for table in soup.find_all("table") if "Course Code" in table.text]
        if tables_1:
                logger.info(f"Found {len(tables_1)} attendance tables using Strategy 1")
                attendance_tables.extend(tables_1)
            
            # Strategy 2: Look for tables with specific structure
        if not attendance_tables:
                logger.info("Trying to find attendance tables with attendance structure")
                for table in soup.find_all("table"):
                    # Check header row for attendance-related columns
                    header_row = table.find("tr")
                    if not header_row:
                        continue
                    
                    header_cells = header_row.find_all(["th", "td"])
                    header_text = " ".join([cell.get_text() for cell in header_cells]).lower()
                    
                    if "attendance" in header_text and ("course" in header_text or "subject" in header_text):
                        attendance_tables.append(table)
                        
                if attendance_tables:
                    logger.info(f"Found {len(attendance_tables)} attendance tables using Strategy 2")
            
            # Strategy 3: Look for any tables near "Attendance" text
        if not attendance_tables:
                logger.info("Trying to find attendance tables by proximity to 'Attendance' text")
                attendance_heading = soup.find(string=lambda s: s and "Attendance" in s)
                if attendance_heading:
                    parent = attendance_heading.parent
                    # Look for the nearest table within 5 levels up
                    for i in range(5):
                        if not parent:
                            break
                        table = parent.find("table")
                        if table:
                            attendance_tables.append(table)
                            break
                        parent = parent.parent
                        
                if attendance_tables:
                    logger.info(f"Found {len(attendance_tables)} attendance tables using Strategy 3")
            
            # If no tables found, check if we can proceed with other sections
                if not attendance_tables:
                   logger.error("No attendance tables found in the HTML!")
                # Save empty attendance data as placeholder
                empty_attendance = {
                    "registration_number": "Unknown",
                    "last_updated": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                    "records": []
                }
                
                self.upsert_attendance_data(user_id, empty_attendance)
                return False

            # ===== Multi-strategy attendance record extraction =====
                logger.info(f"Processing {len(attendance_tables)} attendance tables")
        attendance_records = []
            
        for table_idx, attendance_table in enumerate(attendance_tables):
                logger.info(f"Processing attendance table {table_idx+1}")
                
                # Try to determine header row and column mapping
                header_row = attendance_table.find("tr")
                if not header_row:
                    logger.warning(f"Table {table_idx+1}: No header row found, skipping")
                    continue
                
                header_cells = header_row.find_all(["th", "td"])
                headers = [cell.get_text(strip=True).lower() for cell in header_cells]
                
                # Try to map column indices to standard field names
                col_map = {}
                for i, header in enumerate(headers):
                    if "course code" in header or "subject code" in header:
                        col_map["course_code"] = i
                    elif "course title" in header or "subject name" in header or "course name" in header:
                        col_map["course_title"] = i
                    elif "category" in header:
                        col_map["category"] = i
                    elif "faculty" in header or "teacher" in header or "instructor" in header:
                        col_map["faculty"] = i
                    elif "slot" in header or "period" in header or "time" in header:
                        col_map["slot"] = i
                    elif "conducted" in header:
                        col_map["hours_conducted"] = i
                    elif "absent" in header:
                        col_map["hours_absent"] = i
                    elif "attendance" in header and "percentage" in header:
                        col_map["attendance_percentage"] = i
                
                # Skip table if we couldn't map essential columns
                essential_cols = ["course_code", "course_title"]
                missing_cols = [col for col in essential_cols if col not in col_map]
                if missing_cols:
                    logger.warning(f"Table {table_idx+1}: Missing essential columns: {missing_cols}, skipping")
                    continue
                
                # Process data rows
                data_rows = attendance_table.find_all("tr")[1:]  # skip header row
                for row_idx, row in enumerate(data_rows):
                    cells = row.find_all("td")
                    
                    # Skip rows with too few cells
                    min_cells_needed = max(col_map.values()) + 1
                    if len(cells) < min_cells_needed:
                        logger.warning(f"Table {table_idx+1}, Row {row_idx+1}: Not enough cells, skipping")
                        continue
                    
                    try:
                        # Create record with None for missing fields
                        record = {field: None for field in ["course_code", "course_title", "category", 
                                                           "faculty", "slot", "hours_conducted", 
                                                           "hours_absent", "attendance_percentage"]}
                        
                        # Fill in mapped fields
                        for field, col_idx in col_map.items():
                            if col_idx < len(cells):
                                cell_text = cells[col_idx].get_text(strip=True)
                                
                                # Type conversion for numerical fields
                                if field == "hours_conducted":
                                    record[field] = int(cell_text) if cell_text.strip().isdigit() else 0
                                elif field == "hours_absent":
                                    record[field] = int(cell_text) if cell_text.strip().isdigit() else 0
                                elif field == "attendance_percentage":
                                    record[field] = float(cell_text) if cell_text.strip().replace('.', '', 1).isdigit() else 0.0
                                else:
                                    record[field] = cell_text
                        
                        # Validate the record
                        if not record["course_code"] or not record["course_title"]:
                            logger.warning(f"Table {table_idx+1}, Row {row_idx+1}: Missing course code/title, skipping")
                            continue
                            
                            attendance_records.append(record)
                        
                    except Exception as record_error:
                        logger.warning(f"Error processing row {row_idx+1} in table {table_idx+1}: {record_error}")
                        continue
            
            # Deduplicate records
        deduplicated_records = {}
        for record in attendance_records:
                key = (record["course_code"], record["category"]) if record["category"] else record["course_code"]
                # Keep the record with the most information
                if key not in deduplicated_records or self._record_completeness(record) > self._record_completeness(deduplicated_records[key]):
                    deduplicated_records[key] = record
            
        attendance_records = list(deduplicated_records.values())
        logger.info(f"Extracted {len(attendance_records)} unique attendance records")
            
            # If we have no records, check if we should continue
        if not attendance_records:
                logger.warning("No attendance records extracted, saving empty data")
                empty_attendance = {
                    "registration_number": "Unknown",
                    "last_updated": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                    "records": []
                }
                
                self.upsert_attendance_data(user_id, empty_attendance)
                return False
            
            # Construct the full attendance JSON
        registration_number = self.extract_registration_number_robust(soup) or "Unknown"
        attendance_json = {
                "registration_number": registration_number,
                "last_updated": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                "records": attendance_records
            }

            # Save to database with retry
        return self.upsert_attendance_data(user_id, attendance_json)

    def _record_completeness(self, record):
        """Helper to determine how complete a record is"""
        completeness = 0
        for field, value in record.items():
            if value is not None and value != "":
                completeness += 1
        return completeness

    def upsert_attendance_data(self, user_id, attendance_json):
        """Upsert attendance data with retry logic"""
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                logger.info(f"Upserting attendance data (attempt {attempt+1}/{max_attempts})")
                
                # First check if record exists
                try:
                    sel_resp = supabase.table("attendance").select("id").eq("user_id", user_id).execute()
                    record_exists = sel_resp.data and len(sel_resp.data) > 0
                except Exception as sel_err:
                    logger.warning(f"Error checking for existing record: {sel_err}")
                    record_exists = False
                
                if record_exists:
                    # Update existing
                    up_resp = supabase.table("attendance").update({
                        "attendance_data": attendance_json,
                        "updated_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                    }).eq("user_id", user_id).execute()
                    
                    if up_resp.data and len(up_resp.data) > 0:
                        logger.info("✅ Attendance data updated successfully")
                        return True
                    else:
                        logger.warning("Update returned empty response, trying insert")
                        # Fall through to insert
                
                # Insert new
                in_resp = supabase.table("attendance").insert({
                    "user_id": user_id,
                    "attendance_data": attendance_json,
                    "created_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                    "updated_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                }).execute()

                if in_resp.data and len(in_resp.data) > 0:
                    logger.info("✅ Attendance data inserted successfully")
                    return True
            except Exception as e:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Database operation failed (attempt {attempt+1}): {e}")
                
                if attempt < max_attempts - 1:
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error("❌ All database save attempts failed")
                    
                    # Last resort: save to a local file
                    try:
                        backup_file = f"attendance_backup_{user_id}.json"
                        with open(backup_file, 'w') as f:
                            json.dump(attendance_json, f)
                        logger.info(f"✅ Saved attendance data to backup file: {backup_file}")
                        return True
                    except Exception as backup_err:
                        logger.error(f"Even backup file save failed: {backup_err}")
                        return False
        
            return False

    def get_course_title(self, course_code, attendance_records):
        """
        Matches course codes to course titles using the attendance records of the logged-in user.
        Ignores case and the "Regular" suffix.
        Returns the course title if found; otherwise, falls back to the original course code.
        """
        if not attendance_records:
            logger.warning("No attendance records found, using fallback course code.")
            return course_code
        
        for record in attendance_records:
            stored_code = record.get("course_code", "").strip()
            # Check for an exact match (ignoring case)
            if stored_code.lower() == course_code.lower():
                return record.get("course_title", course_code)
            # Check match when "Regular" is removed
            if stored_code.replace("Regular", "").strip().lower() == course_code.replace("Regular", "").strip().lower():
                return record.get("course_title", course_code)
        
        logger.warning(f"No match found for {course_code}, using fallback course code.")
        return course_code

    def parse_and_save_marks(self, html, driver):
        """
        Scrapes the marks details from the page and upserts the data into the Supabase 'marks' table.
        This function handles any number of courses dynamically and includes multiple defense mechanisms.
        """
        soup = BeautifulSoup(html, "html.parser")
        
        # Extract registration number
        registration_number = self.extract_registration_number(soup)
        if not registration_number:
            logger.error("Could not find Registration Number for marks!")
            return False
        logger.info(f"Extracted Registration Number (marks): {registration_number}")
        
        # Get or create the user in Supabase
        user_id = self.get_user_id_robust(registration_number)
        if not user_id:
            logger.error("Could not retrieve or create user in Supabase for marks.")
            return False

        # Fetch attendance records for the CURRENT user only
        try:
            attendance_resp = supabase.table("attendance").select("attendance_data").eq("user_id", user_id).execute()
        except Exception as e:
            logger.error(f"Error fetching attendance records: {e}")
            attendance_resp = None
        attendance_records = []
        if attendance_resp and attendance_resp.data and len(attendance_resp.data) > 0:
            attendance_data = attendance_resp.data[0].get("attendance_data", {})
            attendance_records = attendance_data.get("records", [])
        logger.info(f"Loaded {len(attendance_records)} attendance records for user {user_id}")
        
        # Locate the marks table by searching for "Test Performance"
        marks_table = None
        for table in soup.find_all("table"):
            header = table.find("tr")
            if header and "Test Performance" in header.get_text():
                marks_table = table
                break
        if not marks_table:
            logger.error("No marks table found!")
            return False

        marks_records = []
        rows = marks_table.find_all("tr")
        if rows:
            for row in rows[1:]:  # Skip header row
                try:
                    cells = row.find_all("td")
                    if len(cells) < 3:
                        continue

                    course_code = cells[0].get_text(strip=True)
                    fallback_title = cells[1].get_text(strip=True)

                    # Try to map course title using attendance records
                    if attendance_records:
                        try:
                            course_title = self.get_course_title(course_code, attendance_records)
                        except Exception as e:
                            logger.error(f"Error mapping course code {course_code}: {e}")
                            course_title = fallback_title
                    else:
                        course_title = fallback_title

                    # The third cell contains a nested table with test details
                    nested_table = cells[2].find("table")
                    tests = []
                    if nested_table:
                        test_cells = nested_table.find_all("td")
                        for tc in test_cells:
                            strong_elem = tc.find("strong")
                            if not strong_elem:
                                continue
                            test_info = strong_elem.get_text(strip=True)
                            parts = test_info.split("/")
                            test_code = parts[0].strip()
                            try:
                                max_marks = float(parts[1].strip()) if len(parts) == 2 else 0.0
                            except:
                                max_marks = 0.0
                            br = tc.find("br")
                            obtained_text = br.next_sibling.strip() if br and br.next_sibling else "0"
                            try:
                                obtained_marks = float(obtained_text) if obtained_text.replace(".", "").isdigit() else obtained_text
                            except:
                                obtained_marks = obtained_text
                            tests.append({
                                "test_code": test_code,
                                "max_marks": max_marks,
                                "obtained_marks": obtained_marks
                            })
                    
                    marks_records.append({
                        "course_name": course_title,
                        "tests": tests
                    })
                    logger.info(f"Mapping: {course_code} → {course_title}")
                except Exception as row_err:
                    logger.warning(f"Error processing a row: {row_err}")
                    continue

        logger.info(f"Parsed {len(marks_records)} unique marks records.")

        # Build JSON object for marks data
        marks_json = {
            "registration_number": registration_number,
            "last_updated": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            "records": marks_records
        }

        # Save data in Supabase using update/insert pattern with defense mechanisms
        try:
            sel_resp = supabase.table("marks").select("id").eq("user_id", user_id).execute()
        except Exception as e:
            logger.error(f"Error selecting marks record: {e}")
            sel_resp = None

        if sel_resp and sel_resp.data and len(sel_resp.data) > 0:
            try:
                up_resp = supabase.table("marks").update({
                    "marks_data": marks_json,
                    "updated_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                }).eq("user_id", user_id).execute()
                if up_resp.data and len(up_resp.data) > 0:
                    logger.info("Marks JSON updated successfully.")
                else:
                    raise Exception("Update returned no data")
            except Exception as update_err:
                logger.error(f"Update failed; trying insert as fallback: {update_err}")
                try:
                    in_resp = supabase.table("marks").insert({
                        "user_id": user_id,
                        "marks_data": marks_json
                    }).execute()
                    if in_resp.data and len(in_resp.data) > 0:
                        logger.info("Marks JSON inserted successfully as fallback.")
                    else:
                        raise Exception("Fallback insert failed")
                except Exception as insert_err:
                    logger.error(f"Final failure in saving marks JSON: {insert_err}")
                    return False
        else:
            try:
                in_resp = supabase.table("marks").insert({
                    "user_id": user_id,
                    "marks_data": marks_json
                }).execute()
                if in_resp.data and len(in_resp.data) > 0:
                    logger.info("Marks JSON inserted successfully.")
                else:
                    raise Exception("Insert returned no data")
            except Exception as insert_err:
                logger.error(f"Initial insert failed: {insert_err}")
                return False

        return True

    # TIMETABLE SCRAPER METHODS

    def get_timetable_page(self):
        """Navigate to timetable page and get HTML"""
        if not self.ensure_login():
            return None
        
        logger.info(f"Navigating to timetable page: {TIMETABLE_URL}")
        self.driver.get(TIMETABLE_URL)
        time.sleep(15)  # Wait for the page to load
        
        html_source = self.driver.page_source
        return html_source

    def dump_page_source(self, filename="debug_page_source.html", num_chars=1000):
        """
        Writes the first 'num_chars' characters of the page source to a file.
        If you need the full source, set num_chars to None.
        """
        source = self.driver.page_source if num_chars is None else self.driver.page_source[:num_chars]
        with open(filename, "w", encoding="utf-8") as f:
            f.write(source)
        logger.info(f"Page source snippet dumped to {filename}")

    def parse_batch_number_from_page(self):
        """
        Extract batch number from either timetable or attendance page HTML.
        Returns the batch number as a string or None if not found.
        """
        try:
            WebDriverWait(self.driver, 50).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'Batch')]"))
            )
        except Exception as e:
            logger.warning(f"Timeout waiting for batch element: {e}")
            # We'll try to parse from the current page source anyway

        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        
        # Method 1: Look for a table cell with "Batch:" label
        batch_label = soup.find("td", string=lambda text: text and "Batch:" in text)
        if batch_label:
            next_cell = batch_label.find_next("td")
            if next_cell:
                batch_text = next_cell.get_text(strip=True)
                if batch_text and batch_text.isdigit():
                    return batch_text
        
        # Method 2: Look for a table row with batch information
        batch_td = soup.find("td", string=lambda text: text and "Batch" in text and ":" not in text)
        if batch_td:
            # The batch number might be in the next cell
            next_td = batch_td.find_next("td")
            if next_td:
                batch_text = next_td.get_text(strip=True)
                if batch_text and batch_text.isdigit():
                    return batch_text
        
        # Method 3: Look for a specific pattern in the HTML
        batch_rows = soup.find_all("tr")
        for row in batch_rows:
            cells = row.find_all("td")
            for i, cell in enumerate(cells):
                if "Batch" in cell.get_text() and i+1 < len(cells):
                    batch_text = cells[i+1].get_text(strip=True)
                    if batch_text and batch_text.isdigit():
                        return batch_text
        
        # Method 4: Use regex to find batch number pattern in the HTML
        batch_pattern = re.compile(r'Batch:?\s*</td>\s*<td[^>]*>\s*(\d+)\s*</td>', re.IGNORECASE)
        match = batch_pattern.search(str(soup))
        if match:
            return match.group(1)
        
        # Method 5: Look for strong tag with batch number
        batch_strong = soup.find("strong", string=lambda text: text and text.isdigit() and len(text.strip()) == 1)
        if batch_strong:
            return batch_strong.get_text(strip=True)
        
        return None

    def scrape_timetable(self):
        """
        Scrapes the timetable table from the page.
        """
        html_source = self.get_timetable_page()
        if not html_source:
            return []
            
        max_retries = 3
        extracted_rows = []
        
        for attempt in range(max_retries):
            logger.info(f"Attempt {attempt+1}: Extracting timetable table...")
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            
            # Attempt to find the timetable
            table = soup.find("table", class_="course_tbl")
            if not table:
                # Some pages have a different class or structure
                for t in soup.find_all("table"):
                    if "Course Code" in t.get_text():
                        table = t
                        break

            if table:
                try:
                    rows = table.find_all("tr")
                    if len(rows) < 2:
                        continue
                    header_cells = rows[0].find_all(["th", "td"])
                    headers = [cell.get_text(strip=True) for cell in header_cells]

                    def col_index(name):
                        for i, h in enumerate(headers):
                            if name in h:
                                return i
                        return -1

                    idx_code = col_index("Course Code")
                    idx_title = col_index("Course Title")
                    idx_slot = col_index("Slot")
                    idx_gcr = col_index("GCR Code")
                    idx_faculty = col_index("Faculty")
                    idx_ctype = col_index("Course Type")
                    idx_room = col_index("Room")

                    data_rows = []
                    for row in rows[1:]:
                        cells = row.find_all("td")
                        if len(cells) > max(idx_code, idx_title, idx_slot, idx_faculty, idx_ctype, idx_room):
                            course_code = cells[idx_code].get_text(strip=True)
                            course_title = cells[idx_title].get_text(strip=True)
                            slot = cells[idx_slot].get_text(strip=True)
                            gcr_code = cells[idx_gcr].get_text(strip=True) if idx_gcr != -1 else ""
                            faculty_name = cells[idx_faculty].get_text(strip=True) if idx_faculty != -1 else ""
                            course_type = cells[idx_ctype].get_text(strip=True) if idx_ctype != -1 else ""
                            room_no = cells[idx_room].get_text(strip=True) if idx_room != -1 else ""

                            if course_code and course_title:
                                data_rows.append({
                                    "course_code": course_code,
                                    "course_title": course_title,
                                    "slot": slot,
                                    "gcr_code": gcr_code,
                                    "faculty_name": faculty_name,
                                    "course_type": course_type,
                                    "room_no": room_no
                                })

                    if data_rows:
                        logger.info(f"Extracted {len(data_rows)} course entries.")
                        extracted_rows = data_rows
                        break
                except Exception as e:
                    logger.warning(f"Error parsing table on attempt {attempt+1}: {e}")

            time.sleep(5)

        if not extracted_rows:
            logger.error("Failed to extract timetable table after retries.")
        return extracted_rows

    def is_empty_slot(self, slot_code):
        """Determine if a slot is empty"""
        if not slot_code or not slot_code.strip():
            return True
        if slot_code.lower() in ['empty', 'break', '-']:
            return True
        return False

    def merge_timetable_with_courses(self, course_data, batch_input=None, personal_details=None):
        """
        Merge course data with the appropriate timetable format based on batch
        """
        # Determine student's batch
        student_batch = None
        if batch_input in ["1", "2"]:
            student_batch = f"Batch {batch_input}"
            logger.info(f"Auto-detected batch: {student_batch}")
        elif personal_details:
            # If you already have a 'Batch' in personal_details, parse it
            raw_batch = personal_details.get("Batch", "").strip()
            if raw_batch in ["1", "2"]:
                student_batch = f"Batch {raw_batch}"
            else:
                match = re.search(r'(\d+)', raw_batch)
                if match and match.group(1) in ["1", "2"]:
                    student_batch = f"Batch {match.group(1)}"

        # If we still have no batch, return an error or fallback
        if not student_batch:
            logger.error("Could not auto-detect batch from the page.")
            return {"status": "error", "msg": "Could not auto-detect batch (must be 1 or 2)"}

        # Select the official timetable based on batch
        if "1" in student_batch:
            official_tt = batch_1_timetable
        elif "2" in student_batch:
            official_tt = batch_2_timetable
        else:
            logger.error(f"Invalid batch: {student_batch}")
            return {"status": "error", "msg": f"Invalid batch: {student_batch}"}

        # Build an enhanced slot-to-course mapping with lab handling
        logger.info("Building enhanced slot to course mapping with improved lab handling...")
        enhanced_mapping = {}
        multi_slot_labs = {}  # Keep track of multi-slot lab courses

        # First pass: Identify all courses and parse their slots
        for course in course_data:
            slot = course.get("slot", "").strip()
            if not slot:
                continue

            course_info = {
                "title": course.get("course_title", "").strip(),
                "faculty": course.get("faculty_name", "").strip(),
                "room": course.get("room_no", "").strip(),
                "code": course.get("course_code", "").strip(),
                "type": course.get("course_type", "").strip(),
                "gcr_code": course.get("gcr_code", "").strip()
            }

            # Handle regular slots with possible "/X" format
            if "/" in slot and "-" not in slot:
                slot_parts = [s.strip() for s in slot.split("/") if s.strip()]
                for part in slot_parts:
                    enhanced_mapping[part] = course_info

            # Special handling for multi-slot lab courses like "P37-P38-P39-P40-"
            elif "-" in slot:
                slot_codes = []

                # Split combined lab slots (handling both forms: "P37-P38-P39-" and "P37-38-39-")
                if re.search(r'P\d+-P\d+-', slot):  # Format: P37-P38-P39-
                    slot_parts = [s.strip() for s in re.findall(r'(P\d+)-', slot)]
                    slot_codes.extend(slot_parts)
                else:  # Format: P37-38-39- (without repeating P)
                    prefix_match = re.match(r'(P)(\d+)-', slot)
                    if prefix_match:
                        prefix = prefix_match.group(1)
                        numbers = re.findall(r'(\d+)-', slot)
                        slot_codes = [f"{prefix}{num}" for num in numbers]

                # Add dash to each slot code to match official timetable format
                slot_codes = [f"{code}-" for code in slot_codes]

                # Register these slot codes with the course
                for code in slot_codes:
                    enhanced_mapping[code] = course_info

                # Also register the full original slot for reference
                enhanced_mapping[slot] = course_info

                # Track this as a multi-slot lab for debugging
                multi_slot_labs[slot] = slot_codes

            # Regular single slot
            else:
                enhanced_mapping[slot] = course_info

        logger.info(f"Processed {len(course_data)} courses, found {len(multi_slot_labs)} multi-slot labs")
        for lab_slot, codes in multi_slot_labs.items():
            logger.info(f"Lab slot {lab_slot} mapped to individual codes: {', '.join(codes)}")

        # Define break codes: slots with no corresponding course info
        break_codes = set()
        for day, slots in official_tt.items():
            for _, slot_code in slots.items():
                if "/" in slot_code:
                    for part in slot_code.split("/"):
                        part = part.strip()
                        if part and part not in enhanced_mapping:
                            break_codes.add(part)
                else:
                    if slot_code and slot_code not in enhanced_mapping:
                        break_codes.add(slot_code)

        # Merge official timetable with the mapping
        logger.info("Merging timetable with course information...")
        merged_tt = {}
        for day, slots in official_tt.items():
            merged_day = {}
            for time_slot, slot_code in slots.items():
                merged_day[time_slot] = {
                    "time": time_slot,
                    "original_slot": slot_code,
                    "courses": [],
                    "display": ""
                }

                if self.is_empty_slot(slot_code):
                    continue

                # Handle multiple parts if present (e.g., "A/X")
                if "/" in slot_code:
                    parts = [s.strip() for s in slot_code.split("/") if s.strip()]
                    matched = []
                    for p in parts:
                        if p in enhanced_mapping:
                            matched.append(enhanced_mapping[p])

                    if matched:
                        titles = " / ".join(mc["title"] for mc in matched)
                        merged_day[time_slot] = {
                            "display": f"{titles} ({time_slot})",
                            "original_slot": slot_code,
                            "courses": matched,
                            "time": time_slot
                        }
                else:
                    if slot_code in enhanced_mapping:
                        course_info = enhanced_mapping[slot_code]
                        merged_day[time_slot] = {
                            "display": f"{course_info['title']} ({time_slot})",
                            "original_slot": slot_code,
                            "courses": [course_info],
                            "time": time_slot
                        }
                    else:
                        is_br = slot_code in break_codes or slot_code == "X"
                        merged_day[time_slot] = {
                            "display": "" if is_br else slot_code,
                            "original_slot": slot_code,
                            "courses": [],
                            "time": time_slot
                        }
            merged_tt[day] = merged_day

        logger.info("Timetable merging completed successfully")
        return {
            "status": "success",
            "batch": student_batch,
            "merged_timetable": merged_tt,
            "personal_details": personal_details,
            "course_data": course_data
        }

    def store_timetable_in_supabase(self, merged_result):
        """Store timetable data in Supabase with proper error handling and delays"""
        try:
            logger.info("Storing timetable data in Supabase...")
            
            # Add delay before database operation
            time.sleep(1)
            
            # Get user_id from email
            user_query = supabase.table("users").select("id").eq("email", self.email).execute()
            if not user_query.data:
                raise Exception("User not found in database")
            user_id = user_query.data[0]["id"]
            
            # Add delay between operations
            time.sleep(1)
            
            # Check if timetable exists
            existing = supabase.table("timetable").select("*").eq("user_id", user_id).execute()
            
            # Prepare timetable data
            timetable_data = {
                "user_id": user_id,
                "timetable_data": merged_result["merged_timetable"],
                "batch": merged_result["batch"],
                "personal_details": merged_result.get("personal_details", {})
            }
            
            # Add delay before final operation
            time.sleep(1)
            
            if existing.data and len(existing.data) > 0:
                # Update existing record
                update_resp = supabase.table("timetable").update(timetable_data).eq("user_id", user_id).execute()
                if not update_resp.data:
                    raise Exception("Failed to update timetable data")
            else:
                # Insert new record
                insert_resp = supabase.table("timetable").insert(timetable_data).execute()
                if not insert_resp.data:
                    raise Exception("Failed to insert timetable data")
                    
            logger.info("✅ Timetable data stored successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error storing timetable data: {e}")
            return False

    def run_timetable_scraper(self):
        """Public interface to run the timetable scraper with enhanced error handling"""
        logger.info("Starting timetable scraper with multi-level error recovery")
        start_time = time.time()
        
        result = {
            "status": "error",
            "message": "Not started",
            "timetable_data": None,
            "batch": None,
            "errors": [],
            "execution_time": 0
        }
        
        try:
            # Step 1: Initialize driver
            try:
                self.driver = self.setup_driver()
                if not self.driver:
                    result["message"] = "Failed to initialize Chrome driver"
                    return result
            except Exception as driver_err:
                result["message"] = f"Driver initialization failed: {str(driver_err)}"
                result["errors"].append({"phase": "driver_setup", "error": str(driver_err)})
                return result
            
            # Step 2: Login
            login_success = False
            max_login_attempts = 3
            for login_attempt in range(max_login_attempts):
                try:
                    logger.info(f"Login attempt {login_attempt+1}/{max_login_attempts}")
                    login_success = self.ensure_login()
                    if login_success:
                        logger.info("✅ Login successful for timetable scraper")
                        break
                    else:
                        logger.warning(f"Login attempt {login_attempt+1} failed")
                        if login_attempt < max_login_attempts - 1:
                            logger.info("Retrying login...")
                            time.sleep(3)
                except Exception as login_err:
                    logger.error(f"Login error on attempt {login_attempt+1}: {login_err}")
                    if login_attempt < max_login_attempts - 1:
                        logger.info("Retrying login after error...")
                        time.sleep(3)
            
            if not login_success:
                result["message"] = "Failed to log in after multiple attempts"
                result["errors"].append({"phase": "login", "error": "Authentication failed"})
                return result
            
            # Step 3: Navigate to timetable page with retries and wait for content
            timetable_html = None
            for page_attempt in range(3):
                try:
                    logger.info(f"Navigating to timetable page (attempt {page_attempt+1}/3)")
                    self.driver.get(TIMETABLE_URL)
                    
                    # Wait for the page to load substantially
                    wait_success = False
                    for i in range(30):  # 30 seconds max wait
                        try:
                            ready_state = self.driver.execute_script('return document.readyState')
                            if ready_state == 'complete':
                                logger.info(f"Page load complete after {i} seconds")
                                
                                # Check for actual timetable content
                                page_text = self.driver.page_source
                                if "Time Table" in page_text or "Timetable" in page_text:
                                    logger.info("Timetable content detected")
                                    wait_success = True
                                    break
                        except:
                            pass
                        time.sleep(1)
                    
                    if not wait_success:
                        logger.warning("Page loaded but timetable content not detected, waiting longer")
                        time.sleep(15)  # Extra wait
                    
                    # Take screenshot for debugging
                    try:
                        self.driver.save_screenshot(f"/tmp/timetable_page_{page_attempt}.png")
                    except Exception as ss_err:
                        logger.warning(f"Failed to save screenshot: {ss_err}")
                    
                    timetable_html = self.driver.page_source
                    
                    # Quick check if we got meaningful content
                    if timetable_html and len(timetable_html) > 5000 and ("Time Table" in timetable_html or "Timetable" in timetable_html):
                        logger.info("✅ Timetable page loaded successfully")
                        break
                    else:
                        logger.warning(f"Timetable HTML may be incomplete (size: {len(timetable_html) if timetable_html else 0})")
                        if page_attempt < 2:
                            logger.info("Retrying page load...")
                            time.sleep(5)
                
                except Exception as page_err:
                    logger.error(f"Error loading timetable page on attempt {page_attempt+1}: {page_err}")
                    if page_attempt < 2:
                        logger.info("Retrying page load after error...")
                        time.sleep(5)
            
            if not timetable_html:
                result["message"] = "Failed to load timetable page"
                result["errors"].append({"phase": "page_load", "error": "Timetable page load failed"})
                return result
            
            # Step 4: Extract batch number with multiple methods
            batch_number = None
            try:
                batch_number = self.parse_batch_number_from_page()
                if batch_number:
                    logger.info(f"✅ Detected batch number: {batch_number}")
                else:
                    logger.warning("Could not detect batch number, will try fallback methods")
                    
                    # Fallback 1: Look for batch in URL
                    current_url = self.driver.current_url
                    import re
                    batch_match = re.search(r'batch=(\d+)', current_url)
                    if batch_match:
                        batch_number = batch_match.group(1)
                        logger.info(f"Found batch {batch_number} from URL")
                    
                    # Fallback 2: Try to extract from user profile or cookies
                    if not batch_number:
                        batch_number = self.extract_batch_from_profile()
                    
                    # Fallback 3: Use default
                    if not batch_number:
                        # Default to batch 1 as safer option
                        batch_number = "1"
                        logger.warning(f"Using default batch number: {batch_number}")
            except Exception as batch_err:
                logger.error(f"Error detecting batch: {batch_err}")
                # Use a default batch to continue
                batch_number = "1"
                logger.warning(f"Using default batch after error: {batch_number}")
            
            # Step 5: Scrape timetable data with multiple strategies
            course_data = []
            try:
                # First try with standard approach
                course_data = self.scrape_timetable()
                
                # If that fails, try alternative method
                if not course_data:
                    logger.warning("Standard timetable scraping failed, trying alternative method")
                    course_data = self.scrape_timetable_alternative()
                
                logger.info(f"Scraped {len(course_data)} course entries")
            except Exception as scrape_err:
                logger.error(f"Error scraping timetable: {scrape_err}")
                result["message"] = f"Timetable scraping failed: {str(scrape_err)}"
                result["errors"].append({"phase": "scraping", "error": str(scrape_err)})
                return result
            
            # Step 6: Merge timetable with appropriate template and save
            try:
                logger.info(f"Merging timetable with batch {batch_number} template")
                merged_result = self.merge_timetable_with_courses(course_data, batch_number)
                
                if merged_result["status"] != "success":
                    logger.error(f"Timetable merging failed: {merged_result.get('msg', 'Unknown error')}")
                    result["message"] = f"Timetable merging failed: {merged_result.get('msg', 'Unknown error')}"
                    result["errors"].append({"phase": "merging", "error": merged_result.get('msg', 'Unknown error')})
                    return result
                
                logger.info("✅ Timetable merged successfully")
            except Exception as merge_err:
                logger.error(f"Error in timetable merging: {merge_err}")
                result["message"] = f"Timetable merging failed: {str(merge_err)}"
                result["errors"].append({"phase": "merging", "error": str(merge_err)})
                return result
                
                # Try to store in database with retries
            store_success = False
            for db_attempt in range(3):
                    try:
                        logger.info(f"Storing timetable in database (attempt {db_attempt+1}/3)")
                        store_success = self.store_timetable_in_supabase(merged_result)
                        if store_success:
                            logger.info("✅ Timetable stored successfully")
                            break
                        else:
                            logger.warning(f"Database storage attempt {db_attempt+1} failed")
                    except Exception as db_err:
                        logger.error(f"Database error on attempt {db_attempt+1}: {db_err}")
                        if db_attempt < 2:
                            wait_time = 2 ** db_attempt
                            logger.info(f"Retrying in {wait_time} seconds...")
                            time.sleep(wait_time)
                
                # Even if database storage failed, we can still return the data
            execution_time = time.time() - start_time
            result = {
                    "status": "success",
                    "message": "Timetable scraping completed" + ("" if store_success else " (but storage failed)"),
                    "timetable_data": merged_result["merged_timetable"],
                    "batch": merged_result["batch"],
                    "execution_time": execution_time
                }
                
            logger.info(f"Timetable scraping completed in {execution_time:.2f} seconds")
            return result
                
        except Exception as merge_err:
                logger.error(f"Error in timetable merging or storage: {merge_err}")
                result["message"] = f"Timetable processing failed: {str(merge_err)}"
                result["errors"].append({"phase": "processing", "error": str(merge_err)})
                return result
        
        finally:
            # Clean up resources
            if hasattr(self, 'driver') and self.driver:
                try:
                    self.driver.quit()
                    logger.info("Chrome driver closed successfully")
                except:
                    logger.warning("Error closing Chrome driver")

    def run_attendance_scraper(self):
        """Public interface to run the attendance scraper"""
        logger.info("Starting attendance scraper")
        try:
            self.driver = self.setup_driver()
            if self.driver is None:
                logger.error("Failed to initialize Chrome driver")
                return {"status": "error", "message": "Failed to initialize Chrome driver"}
            
            self.apply_timeouts()
            
            success = self.ensure_login()
            if not success:
                logger.error("Failed to log in to Academia. Aborting attendance scraping.")
                return {"status": "error", "message": "Login failed"}
                
            html_source = self.get_attendance_page()
            if not html_source:
                logger.error("Failed to load attendance page")
                return {"status": "error", "message": "Failed to load attendance page"}
                
            registration_number = self.extract_registration_number(BeautifulSoup(html_source, "html.parser"))
            if not registration_number:
                logger.error("Failed to extract registration number")
                return {"status": "error", "message": "Failed to extract registration number"}
                
            user_id = self.get_user_id_robust(registration_number)
            if not user_id:
                logger.error("Failed to get or create user in database")
                return {"status": "error", "message": "Failed to get or create user in database"}
                
            result = self.parse_and_save_attendance_robust(html_source, user_id)
            marks_result = self.parse_and_save_marks(html_source, self.driver)
            
            self.driver.quit()
            logger.info("Attendance scraper finished successfully")
            
            combined_result = {
                "status": "success",
                "attendance": result,
                "marks": marks_result
            }
            return combined_result
            
        except Exception as e:
            logger.error(f"Error in attendance scraper: {str(e)}")
            if self.driver:
                self.driver.quit()
            return {"status": "error", "message": str(e)}

    def clear_browser_cache(self):
        """Clear browser cache to free up memory"""
        try:
            self.driver.execute_script("window.gc();")  # Force garbage collection
            self.driver.execute_cdp_cmd('Network.clearBrowserCache', {})
            logger.info("Browser cache cleared")
        except Exception as e:
            logger.warning(f"Failed to clear browser cache: {e}")

    def log_memory_usage(self):
        """Log current memory usage to help with debugging"""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            logger.info(f"Memory usage: {process.memory_info().rss / 1024 / 1024:.2f} MB")
        except:
            logger.warning("Unable to log memory usage (psutil not available)")

    def apply_timeouts(self):
        """Apply various timeouts to improve reliability on Render"""
        if self.driver:
            self.driver.set_page_load_timeout(120)  # 2 minutes
            self.driver.set_script_timeout(60)  # 1 minute
            # Add implicit wait - careful with this as it affects all find_element calls
            self.driver.implicitly_wait(10)  # 10 seconds

    def verify_cookies(self):
        """Verify that cookies and token were properly extracted and stored"""
        try:
            # Check browser cookies
            browser_cookies = self.driver.get_cookies()
            browser_cookie_dict = {cookie['name']: cookie['value'] for cookie in browser_cookies}
            
            # Check file data
            file_data = {}
            try:
                with open('debug_cookies.json', 'r') as f:
                    file_data = json.load(f)
            except:
                pass
            
            # Check database data
            db_data = {}
            try:
                result = supabase.table('user_cookies').select('*').eq('email', self.email).execute()
                if result.data:
                    db_data = result.data[0]
            except Exception as e:
                logger.error(f"Failed to fetch database data: {e}")
            
            logger.info(f"""
            Storage Status:
            - Browser: {len(browser_cookie_dict)} cookies
            - File: {len(file_data.get('cookies', {}))} cookies, Token: {'Present' if 'token' in file_data else 'Missing'}
            - Database: {len(db_data.get('cookies', {}))} cookies, Token: {'Present' if 'token' in db_data else 'Missing'}
            """)
            
            return {
                'browser': browser_cookie_dict,
                'file': file_data,
                'database': db_data
            }
        except Exception as e:
            logger.error(f"Error verifying cookies and token: {e}")
            return None

    def run_unified_scraper(self):
        """Run both scrapers in a single session with enhanced robustness"""
        logger.info("Starting unified scraper with advanced error handling")
        start_time = time.time()
        
        result = {
            "status": "error",
            "message": "Not started",
            "attendance": {
                "status": "not_started",
                "data": None
            },
            "timetable": {
                "status": "not_started",
                "data": None
            },
            "marks": {
                "status": "not_started",
                "data": None
            },
            "execution_time": 0
        }
        
        try:
            # Setup driver with enhanced error handling
            self.driver = self.setup_driver()
            if not self.driver:
                result["message"] = "Failed to initialize Chrome driver"
                return result
            
            # Login with retry mechanism
            login_success = self.ensure_login()
            if not login_success:
                result["message"] = "Failed to log in after multiple attempts"
                return result
            
            # Run attendance scraper first
            try:
                logger.info("Starting attendance data collection")
                html_source = self.get_attendance_page()
                
                if html_source:
                    # Get registration number
                    soup = BeautifulSoup(html_source, "html.parser")
                    registration_number = self.extract_registration_number_robust(soup)
                    
                    if registration_number:
                        # Get user ID
                        user_id = self.get_user_id_robust(registration_number)
                        
                        if user_id:
                            # Process attendance data
                            attendance_success = self.parse_and_save_attendance_robust(html_source, user_id)
                            
                            # Process marks data
                            marks_success = self.parse_and_save_marks(html_source, self.driver)
                            
                            result["attendance"]["status"] = "success" if attendance_success else "error"
                            result["marks"]["status"] = "success" if marks_success else "error"
                            
                            logger.info(f"Attendance scraping finished: {result['attendance']['status']}")
                            logger.info(f"Marks scraping finished: {result['marks']['status']}")
                else:
                    logger.error("Failed to get attendance page HTML")
                    result["attendance"]["status"] = "error"
                    result["marks"]["status"] = "error"
                    result["attendance"]["message"] = "Failed to load attendance page"
            except Exception as attendance_err:
                logger.error(f"Error during attendance scraping: {attendance_err}")
                result["attendance"]["status"] = "error"
                result["attendance"]["message"] = str(attendance_err)
                result["marks"]["status"] = "error"
                result["marks"]["message"] = str(attendance_err)
            
            # Clear browsing data to minimize memory usage
            try:
                self.clear_browser_cache()
            except:
                pass
            
            # Run timetable scraper
            try:
                logger.info("Starting timetable data collection")
                
                # Navigate to timetable page
                self.driver.get(TIMETABLE_URL)
                
                # Wait for page to load
                timetable_loaded = False
                for i in range(30):
                    try:
                        ready_state = self.driver.execute_script('return document.readyState')
                        if ready_state == 'complete':
                            timetable_loaded = True
                            break
                    except:
                        pass
                    time.sleep(1)
                
                if timetable_loaded:
                    # Extract batch number
                    batch_number = self.parse_batch_number_from_page()
                    
                    if not batch_number:
                        batch_number = self.extract_batch_from_profile()
                        
                    if not batch_number:
                        # Default to batch 1 as safer option
                        batch_number = "1"
                        logger.warning(f"Using default batch number: {batch_number}")
                    
                    # Scrape course data
                    course_data = self.scrape_timetable()
                    
                    if not course_data:
                        # Try alternative method
                        course_data = self.scrape_timetable_alternative()
                    
                    if course_data:
                        # Merge with template
                        merged_result = self.merge_timetable_with_courses(course_data, batch_number)
                        
                        if merged_result["status"] == "success":
                            # Store in database
                            store_success = self.store_timetable_in_supabase(merged_result)
                            
                            result["timetable"]["status"] = "success"
                            result["timetable"]["data"] = {
                                "batch": merged_result["batch"],
                                "entries": len(course_data),
                                "storage": "success" if store_success else "failed"
                            }
                            
                            logger.info(f"Timetable scraping finished: {result['timetable']['status']}")
                        else:
                            result["timetable"]["status"] = "error"
                            result["timetable"]["message"] = merged_result.get("msg", "Unknown error")
                    else:
                        result["timetable"]["status"] = "error"
                        result["timetable"]["message"] = "No timetable data found"
                else:
                    result["timetable"]["status"] = "error"
                    result["timetable"]["message"] = "Timetable page did not load"
            except Exception as timetable_err:
                logger.error(f"Error during timetable scraping: {timetable_err}")
                result["timetable"]["status"] = "error"
                result["timetable"]["message"] = str(timetable_err)
            
            # Set overall status
            component_statuses = [
                result["attendance"]["status"],
                result["marks"]["status"],
                result["timetable"]["status"]
            ]
            
            if all(status == "success" for status in component_statuses):
                result["status"] = "success"
                result["message"] = "All scraping tasks completed successfully"
            elif all(status == "error" for status in component_statuses):
                result["status"] = "error"
                result["message"] = "All scraping tasks failed"
            else:
                result["status"] = "partial_success"
                result["message"] = "Some scraping tasks completed successfully"
            
            # Calculate execution time
            result["execution_time"] = time.time() - start_time
            
            logger.info(f"Unified scraper finished in {result['execution_time']:.2f} seconds with status: {result['status']}")
            return result
        
        except Exception as e:
            logger.error(f"Unified scraper critical error: {e}")
            result["status"] = "error"
            result["message"] = f"Critical error: {str(e)}"
            traceback.print_exc()
            return result
        
        finally:
            # Clean up resources
            if hasattr(self, 'driver') and self.driver:
                try:
                    self.driver.quit()
                    logger.info("Browser closed successfully")
                except:
                    logger.warning("Error closing browser")

    def verify_token(self, token):
        """Verify a JWT token"""
        try:
            decoded = jwt.decode(
                token,
                os.getenv('JWT_SECRET_KEY', 'your-secret-key'),
                algorithms=['HS256']
            )
            # Check if token has expired
            exp = decoded.get('exp')
            if exp and datetime.utcnow().timestamp() > exp:
                logger.warning("Token has expired")
                return None
            return decoded['email']
        except Exception as e:
            logger.error(f"Token verification failed: {e}")
            return None

    def check_token_status(self):
        """Check token status in Supabase and local storage"""
        try:
            # Check Supabase
            result = supabase.table('user_cookies').select('token, updated_at').eq('email', self.email).execute()
            if not result.data:
                return {
                    'status': 'error',
                    'message': 'No token found in database'
                }
            
            db_token = result.data[0].get('token')
            updated_at = result.data[0].get('updated_at')
            
            # Verify the token
            email = self.verify_token(db_token)
            if not email:
                return {
                    'status': 'error',
                    'message': 'Token is invalid or expired'
                }
            
            return {
                'status': 'success',
                'email': email,
                'updated_at': updated_at,
                'days_remaining': self.get_token_days_remaining(db_token)
            }
        
        except Exception as e:
            logger.error(f"Error checking token status: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }

    def get_token_days_remaining(self, token):
        """Calculate days remaining before token expires"""
        try:
            decoded = jwt.decode(
                token,
                os.getenv('JWT_SECRET_KEY', 'your-secret-key'),
                algorithms=['HS256']
            )
            exp = decoded.get('exp')
            if exp:
                remaining = exp - datetime.utcnow().timestamp()
                return max(0, int(remaining / (24 * 3600)))  # Convert to days
            return 0
        except:
            return 0

    def switch_to_iframe_safely(self, iframe_selector, max_attempts=3, wait_time=10):
        """Safely switch to an iframe with multiple attempts and proper waits"""
        logger.info(f"Attempting to switch to iframe: {iframe_selector}")
        
        for attempt in range(1, max_attempts + 1):
            try:
                # First make sure we're in the main content
                self.driver.switch_to.default_content()
                
                # Wait for page to be fully loaded first
                WebDriverWait(self.driver, wait_time).until(
                    lambda d: d.execute_script('return document.readyState') == 'complete'
                )
                
                # Take a screenshot for debugging
                try:
                    self.driver.save_screenshot(f"/tmp/before_iframe_switch_{attempt}.png")
                    logger.info(f"Saved screenshot before iframe switch attempt {attempt}")
                except Exception as ss_err:
                    logger.warning(f"Failed to save pre-switch screenshot: {ss_err}")
                
                # Log HTML title and URL for debugging
                logger.info(f"Page title: {self.driver.title}")
                logger.info(f"Current URL: {self.driver.current_url}")
                
                # Check page ready state
                ready_state = self.driver.execute_script('return document.readyState')
                logger.info(f"Document ready state: {ready_state}")
                
                # See if iframe exists at all
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                logger.info(f"Found {len(iframes)} iframes on page")
                for i, frame in enumerate(iframes):
                    frame_id = frame.get_attribute("id") or "No ID"
                    frame_name = frame.get_attribute("name") or "No Name"
                    frame_src = frame.get_attribute("src") or "No Source"
                    is_displayed = "Visible" if self.is_element_visible(frame) else "Hidden"
                    logger.info(f"Frame {i}: ID={frame_id}, Name={frame_name}, Src={frame_src}, {is_displayed}")
                
                # Handle different selector types
                if iframe_selector[0] == By.ID:
                    # Try iframe with matching ID
                    matching_frames = [f for f in iframes if f.get_attribute("id") == iframe_selector[1]]
                    if matching_frames:
                        logger.info(f"Found {len(matching_frames)} iframes with matching ID")
                        iframe = matching_frames[0]
                    else:
                        # Wait for the iframe to be available in the DOM
                        WebDriverWait(self.driver, wait_time).until(
                            EC.presence_of_element_located(iframe_selector)
                        )
                        iframe = self.driver.find_element(*iframe_selector)
                elif iframe_selector[0] == By.NAME:
                    # Try iframe with matching name
                    matching_frames = [f for f in iframes if f.get_attribute("name") == iframe_selector[1]]
                    if matching_frames:
                        logger.info(f"Found {len(matching_frames)} iframes with matching name")
                        iframe = matching_frames[0]
                    else:
                        # Wait for the iframe to be available in the DOM
                        WebDriverWait(self.driver, wait_time).until(
                            EC.presence_of_element_located(iframe_selector)
                        )
                        iframe = self.driver.find_element(*iframe_selector)
                else:
                    # Default to standard presence of element for other selector types
                    WebDriverWait(self.driver, wait_time).until(
                        EC.presence_of_element_located(iframe_selector)
                    )
                    iframe = self.driver.find_element(*iframe_selector)
                
                # Wait a bit for the iframe to fully load
                time.sleep(2)
                
                # Scroll to the iframe to make sure it's in view
                self.driver.execute_script("arguments[0].scrollIntoView(true);", iframe)
                time.sleep(1)
                
                # Check if iframe is in a proper state
                if not self.is_element_visible(iframe):
                    logger.warning("iframe is not visible, attempting to scroll and wait...")
                    self.driver.execute_script("window.scrollTo(0, 0);")  # Scroll to top
                    time.sleep(1)
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", iframe)
                    time.sleep(2)
                
                # Switch to the iframe
                self.driver.switch_to.frame(iframe)
                
                # Verify the switch worked by checking we can access the iframe's document
                self.driver.execute_script('return document.readyState')
                
                logger.info(f"✅ Successfully switched to iframe on attempt {attempt}")
                return True
                
            except Exception as e:
                logger.warning(f"⚠️ Attempt {attempt} to switch to iframe failed: {e}")
                traceback.print_exc()
                
                # Take a screenshot for debugging
                try:
                    screenshot_path = f"/tmp/iframe_switch_failure_{attempt}.png"
                    self.driver.save_screenshot(screenshot_path)
                    logger.info(f"Screenshot saved to {screenshot_path}")
                except Exception as ss_err:
                    logger.warning(f"Failed to save screenshot: {ss_err}")
                    
                if attempt == max_attempts:
                    logger.error(f"❌ Failed to switch to iframe after {max_attempts} attempts")
                    return False
                
                # Wait before trying again
                time.sleep(5)
                
                # Try refreshing the page as a last resort on the final attempt
                if attempt == max_attempts - 1:
                    logger.info("Refreshing page for final attempt...")
                    self.driver.refresh()
                    time.sleep(5)

    def find_login_elements(self):
        """Find login elements using multiple strategies"""
        wait = WebDriverWait(self.driver, 10)
        
        # Try to find email field
        email_field = None
        for selector in [
            (By.ID, "login_id"),
            (By.NAME, "username"),
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.CSS_SELECTOR, "input[type='text']"),
        ]:
            try:
                email_field = wait.until(EC.presence_of_element_located(selector))
                logger.info(f"Found email field using selector: {selector}")
                break
            except:
                continue
        
        # Try to find login button
        login_button = None
        for selector in [
            (By.ID, "nextbtn"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.XPATH, "//button[contains(text(), 'Next')]"),
            (By.XPATH, "//button[contains(text(), 'Login')]"),
            (By.XPATH, "//input[@type='submit']"),
        ]:
            try:
                login_button = wait.until(EC.element_to_be_clickable(selector))
                logger.info(f"Found login button using selector: {selector}")
                break
            except:
                continue
        
        return email_field, login_button

    def extract_registration_number_robust(self, soup):
        """Extract registration number with multiple strategies"""
        registration_number = None
        strategies = [
            # Strategy 1: Look for standard label and value pattern
            lambda: self._extract_reg_number_from_label(soup),
            
            # Strategy 2: Look for registration patterns in any text
            lambda: self._extract_reg_number_from_pattern(soup),
            
            # Strategy 3: Look for registration in specific page sections
            lambda: self._extract_reg_number_from_sections(soup),
            
            # Strategy 4: Try to extract from URL or hidden fields
            lambda: self._extract_reg_number_from_page_metadata(soup)
        ]
        
        for i, strategy in enumerate(strategies):
            try:
                logger.info(f"Trying registration number extraction strategy {i+1}")
                result = strategy()
                if result:
                    logger.info(f"✅ Successfully extracted registration number using strategy {i+1}: {result}")
                    return result
            except Exception as e:
                logger.warning(f"Registration number extraction strategy {i+1} failed: {e}")
        
        # Last resort: try to use email as identifier
        logger.warning("Failed to extract registration number, will use email as identifier")
        return self.email.split('@')[0] if '@' in self.email else self.email

    def _extract_reg_number_from_label(self, soup):
        """Strategy 1: Extract registration from labeled elements"""
        # Look for a table cell with "Registration Number" label
        label_td = soup.find("td", string=lambda text: text and "Registration Number" in text)
        if label_td:
            value_td = label_td.find_next("td")
            if value_td:
                strong_elem = value_td.find("strong") or value_td.find("b")
                if strong_elem:
                    return strong_elem.get_text(strip=True)
                else:
                    return value_td.get_text(strip=True)
        return None

    def _extract_reg_number_from_pattern(self, soup):
        """Strategy 2: Extract using regex patterns for registration numbers"""
        import re
        # Common formats: RA2211003010xxxx, RA22110xxxxx
        patterns = [
            r'RA\d{10,}',  # Standard SRM registration format
            r'RA\d{8,}',    # Shorter variant
            r'\d{10,}'      # Just digits as fallback
        ]
        
        for pattern in patterns:
            match = re.search(pattern, soup.get_text())
            if match:
                return match.group(0)
        return None

    def _extract_reg_number_from_sections(self, soup):
        """Strategy 3: Look in specific sections that might contain registration"""
        # Check profile section
        profile_section = soup.find("div", class_=lambda c: c and "profile" in c.lower())
        if profile_section:
            # Look for registration pattern in profile
            import re
            match = re.search(r'RA\d{10,}', profile_section.get_text())
            if match:
                return match.group(0)
        
        # Check tables
        for row in soup.find_all("tr"):
            tds = row.find_all("td")
            if len(tds) >= 2 and "Registration" in tds[0].get_text():
                return tds[1].get_text(strip=True)
        
        return None

    def _extract_reg_number_from_page_metadata(self, soup):
        """Strategy 4: Try to extract from page metadata or driver state"""
        # Try to get from URL if present
        if hasattr(self, 'driver') and self.driver:
            current_url = self.driver.current_url
            import re
            match = re.search(r'regnum=([A-Za-z0-9]+)', current_url)
            if match:
                return match.group(1)
        
        # Try from hidden input fields
        for hidden_input in soup.find_all("input", type="hidden"):
            name = hidden_input.get("name", "").lower()
            if "reg" in name or "registration" in name:
                return hidden_input.get("value", "")
        
        return None

    def resilient_request(self, url, method="GET", data=None, headers=None, max_retries=3, timeout=30):
        """Make a network request with retries and exponential backoff"""
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,  # 1, 2, 4, 8, 16, 32, ... seconds between retries
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        try:
            logger.info(f"Making {method} request to {url}")
            
            if method.upper() == "GET":
                response = session.get(url, headers=headers, timeout=timeout)
            elif method.upper() == "POST":
                response = session.post(url, json=data, headers=headers, timeout=timeout)
            else:
                logger.error(f"Unsupported method: {method}")
                return None
            
            response.raise_for_status()
            logger.info(f"Request successful: {response.status_code}")
            return response
            
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error: {http_err}")
            return None
        except requests.exceptions.ConnectionError as conn_err:
            logger.error(f"Connection error: {conn_err}")
            return None
        except requests.exceptions.Timeout as timeout_err:
            logger.error(f"Timeout error: {timeout_err}")
            return None
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Request error: {req_err}")
            return None

    def health_check(self):
        """Run a comprehensive health check to verify all components are working"""
        health_status = {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "components": {
                "driver": {"status": "not_checked"},
                "network": {"status": "not_checked"},
                "database": {"status": "not_checked"},
                "academia_site": {"status": "not_checked"}
            },
            "errors": []
        }
        
        # Check WebDriver
        try:
            logger.info("Checking WebDriver...")
            self.driver = self.setup_driver()
            if self.driver:
                health_status["components"]["driver"]["status"] = "ok"
                
                # Get browser details
                try:
                    browser_info = {
                        "name": self.driver.capabilities.get("browserName", "unknown"),
                        "version": self.driver.capabilities.get("browserVersion", "unknown")
                    }
                    health_status["components"]["driver"]["details"] = browser_info
                except:
                    pass
            else:
                health_status["components"]["driver"]["status"] = "error"
                health_status["errors"].append("Failed to initialize WebDriver")
        except Exception as driver_err:
            health_status["components"]["driver"]["status"] = "error"
            health_status["components"]["driver"]["error"] = str(driver_err)
            health_status["errors"].append(f"WebDriver error: {str(driver_err)}")
        
        # Check network
        try:
            logger.info("Checking network connectivity...")
            # Try a few different domains to check connectivity
            sites = ["https://google.com", "https://cloudflare.com", "https://github.com"]
            network_results = {}
            
            for site in sites:
                try:
                    response = self.resilient_request(site, timeout=5)
                    if response:
                        network_results[site] = {
                            "status": "ok",
                            "status_code": response.status_code,
                            "response_time": response.elapsed.total_seconds()
                        }
                    else:
                        network_results[site] = {
                            "status": "error",
                            "error": "Request failed"
                        }
                except Exception as site_err:
                    network_results[site] = {
                        "status": "error",
                        "error": str(site_err)
                    }
            
            # Check if at least one site is accessible
            if any(result["status"] == "ok" for result in network_results.values()):
                health_status["components"]["network"]["status"] = "ok"
                health_status["components"]["network"]["details"] = network_results
            else:
                health_status["components"]["network"]["status"] = "error"
                health_status["components"]["network"]["details"] = network_results
                health_status["errors"].append("Network connectivity issues detected")
        except Exception as net_err:
            health_status["components"]["network"]["status"] = "error"
            health_status["components"]["network"]["error"] = str(net_err)
            health_status["errors"].append(f"Network check error: {str(net_err)}")
        
        # Check database
        try:
            logger.info("Checking database connectivity...")
            # Try a simple query to check database connectivity
            try:
                db_test = supabase.from_("users").select("count").limit(1).execute()
                health_status["components"]["database"]["status"] = "ok"
                health_status["components"]["database"]["details"] = {
                    "query_success": True
                }
            except Exception as db_err:
                health_status["components"]["database"]["status"] = "error"
                health_status["components"]["database"]["error"] = str(db_err)
                health_status["errors"].append(f"Database error: {str(db_err)}")
        except Exception as db_wrapper_err:
            health_status["components"]["database"]["status"] = "error"
            health_status["components"]["database"]["error"] = str(db_wrapper_err)
            health_status["errors"].append(f"Database wrapper error: {str(db_wrapper_err)}")
        
        # Check Academia site
        try:
            logger.info("Checking Academia site accessibility...")
            if self.driver:
                try:
                    self.driver.set_page_load_timeout(10)  # Short timeout for health check
                    self.driver.get(LOGIN_URL)
                    
                    # Wait for page to start loading
                    time.sleep(2)
                    
                    # Check if page loaded something reasonable
                    current_url = self.driver.current_url
                    page_source = self.driver.page_source
                    
                    if "academia" in current_url.lower() and len(page_source) > 1000:
                        health_status["components"]["academia_site"]["status"] = "ok"
                        health_status["components"]["academia_site"]["details"] = {
                            "url": current_url,
                            "title": self.driver.title,
                            "content_length": len(page_source)
                        }
                    else:
                        health_status["components"]["academia_site"]["status"] = "warning"
                        health_status["components"]["academia_site"]["details"] = {
                            "url": current_url,
                            "title": self.driver.title,
                            "content_length": len(page_source)
                        }
                        health_status["errors"].append("Academia site may be inaccessible or loading differently")
                except Exception as site_err:
                    health_status["components"]["academia_site"]["status"] = "error"
                    health_status["components"]["academia_site"]["error"] = str(site_err)
                    health_status["errors"].append(f"Academia site error: {str(site_err)}")
            else:
                health_status["components"]["academia_site"]["status"] = "skipped"
                health_status["components"]["academia_site"]["message"] = "WebDriver not available"
        except Exception as site_wrapper_err:
            health_status["components"]["academia_site"]["status"] = "error"
            health_status["components"]["academia_site"]["error"] = str(site_wrapper_err)
            health_status["errors"].append(f"Academia site wrapper error: {str(site_wrapper_err)}")
        
        # Clean up
        if hasattr(self, 'driver') and self.driver:
            try:
                self.driver.quit()
            except:
                pass
        
        # Final status determination
        component_statuses = [comp["status"] for comp in health_status["components"].values()]
        if all(status == "ok" for status in component_statuses):
            health_status["status"] = "ok"
        elif "error" in component_statuses:
            health_status["status"] = "error"
        else:
            health_status["status"] = "warning"
        
        return health_status

    def scrape_timetable_alternative(self):
        """
        Alternative timetable scraping method used when the standard method fails.
        Implements different strategies to extract course data.
        """
        logger.info("Using alternative timetable extraction method")
        
        try:
            # First try to find course data using JavaScript approach
            logger.info("Trying JavaScript extraction of timetable data")
            try:
                # This may work if the data is available in the page's JavaScript objects
                js_result = self.driver.execute_script("""
                    if (typeof timetableData !== 'undefined') {
                        return timetableData;
                    } else if (typeof window.courseData !== 'undefined') {
                        return window.courseData;
                    } else {
                        // Try to find any array with course-like objects
                        for (let key in window) {
                            if (window[key] && 
                                Array.isArray(window[key]) && 
                                window[key].length > 0 &&
                                typeof window[key][0] === 'object' &&
                                (window[key][0].hasOwnProperty('courseCode') || 
                                 window[key][0].hasOwnProperty('course_code') ||
                                 window[key][0].hasOwnProperty('slot'))) {
                                return window[key];
                            }
                        }
                    }
                    return null;
                """)
                
                if js_result and isinstance(js_result, list) and len(js_result) > 0:
                    logger.info(f"Successfully extracted {len(js_result)} courses via JavaScript")
                    
                    # Convert from JavaScript format to our expected format
                    converted_data = []
                    for item in js_result:
                        converted = {}
                        # Map different possible key names to our standard keys
                        key_mappings = {
                            'courseCode': 'course_code',
                            'course_code': 'course_code',
                            'course': 'course_code',
                            'courseTitle': 'course_title',
                            'course_title': 'course_title',
                            'title': 'course_title',
                            'name': 'course_title',
                            'slot': 'slot',
                            'timeSlot': 'slot',
                            'facultyName': 'faculty_name',
                            'faculty_name': 'faculty_name',
                            'faculty': 'faculty_name',
                            'instructor': 'faculty_name',
                            'gcrCode': 'gcr_code',
                            'gcr_code': 'gcr_code',
                            'gcr': 'gcr_code',
                            'courseType': 'course_type',
                            'course_type': 'course_type',
                            'type': 'course_type',
                            'roomNo': 'room_no',
                            'room_no': 'room_no',
                            'room': 'room_no'
                        }
                        
                        # Apply mappings
                        for src_key, dst_key in key_mappings.items():
                            if src_key in item:
                                converted[dst_key] = item[src_key]
                        
                        # Ensure all required fields exist
                        if 'course_code' in converted and 'course_title' in converted:
                            converted_data.append(converted)
                    
                    if converted_data:
                        return converted_data
            except Exception as js_err:
                logger.warning(f"JavaScript extraction failed: {js_err}")
            
            # If JavaScript approach failed, try HTML parsing approach
            logger.info("Trying direct HTML parsing for timetable data")
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            
            # Strategy 1: Look for tables with specific structure related to timetable
            all_tables = soup.find_all("table")
            course_data = []
            
            for table in all_tables:
                # Skip small tables that are unlikely to be the timetable
                rows = table.find_all("tr")
                if len(rows) < 2:
                    continue
                    
                # Check if this looks like a course table by examining headers
                headers = rows[0].find_all(["th", "td"])
                header_text = " ".join([h.get_text().lower() for h in headers])
                
                if any(term in header_text for term in ["course", "slot", "faculty", "subject"]):
                    logger.info(f"Found potential timetable with {len(rows)-1} entries")
                    
                    # Try to determine column mapping
                    header_texts = [h.get_text().lower().strip() for h in headers]
                    
                    col_map = {}
                    for i, header in enumerate(header_texts):
                        if any(term in header for term in ["course code", "subject code"]):
                            col_map["course_code"] = i
                        elif any(term in header for term in ["course title", "subject name", "course name"]):
                            col_map["course_title"] = i
                        elif "slot" in header:
                            col_map["slot"] = i
                        elif any(term in header for term in ["gcr", "venue code"]):
                            col_map["gcr_code"] = i
                        elif any(term in header for term in ["faculty", "teacher", "instructor"]):
                            col_map["faculty_name"] = i
                        elif any(term in header for term in ["course type", "category"]):
                            col_map["course_type"] = i
                        elif any(term in header for term in ["room", "venue"]):
                            col_map["room_no"] = i
                    
                    # Skip if we couldn't identify the essential columns
                    if "course_code" not in col_map or "course_title" not in col_map:
                        logger.warning("Table doesn't have required columns, skipping")
                        continue
                    
                    # Process data rows
                    for row in rows[1:]:
                        cells = row.find_all(["td", "th"])
                        
                        # Skip rows with insufficient cells
                        if len(cells) < max(col_map.values()) + 1:
                            continue
                            
                        course_record = {}
                        for field, idx in col_map.items():
                            if idx < len(cells):
                                course_record[field] = cells[idx].get_text().strip()
                        
                        # Add default values for missing fields
                        for field in ["course_code", "course_title", "slot", "gcr_code", "faculty_name", "course_type", "room_no"]:
                            if field not in course_record:
                                course_record[field] = ""
                                
                        # Only add if we have the essential data
                        if course_record["course_code"] and course_record["course_title"]:
                            course_data.append(course_record)
                    
                    # If we found data in this table, return it
                    if course_data:
                        logger.info(f"Successfully extracted {len(course_data)} courses via HTML parsing")
                        return course_data
            
            # If no data found from tables, try looking for structured divs or lists
            logger.info("Trying div/list structures for timetable data")
            
            # Strategy for divs that might contain course information
            course_sections = soup.find_all("div", class_=lambda c: c and any(term in c.lower() for term in ["course", "subject", "timetable"]))
            
            for section in course_sections:
                # Look for structured data within this section
                course_elements = section.find_all("div", class_=lambda c: c and any(term in c.lower() for term in ["item", "course", "row"]))
                
                if course_elements:
                    logger.info(f"Found {len(course_elements)} potential course elements")
                    
                    for element in course_elements:
                        try:
                            # Try to extract course info from this element
                            course_info = {}
                            
                            # Look for labeled data
                            for label in ["course code", "subject code", "code"]:
                                code_elem = element.find(string=lambda s: s and label in s.lower())
                                if code_elem:
                                    # Find the value near this label
                                    parent = code_elem.parent
                                    # Look for value in siblings
                                    next_elem = parent.find_next(["span", "div", "p", "strong"])
                                    if next_elem:
                                        course_info["course_code"] = next_elem.get_text().strip()
                                        break
                            
                            for label in ["course title", "subject name", "course name", "title"]:
                                title_elem = element.find(string=lambda s: s and label in s.lower())
                                if title_elem:
                                    parent = title_elem.parent
                                    next_elem = parent.find_next(["span", "div", "p", "strong"])
                                    if next_elem:
                                        course_info["course_title"] = next_elem.get_text().strip()
                                        break
                            
                            for label in ["slot", "time slot"]:
                                slot_elem = element.find(string=lambda s: s and label in s.lower())
                                if slot_elem:
                                    parent = slot_elem.parent
                                    next_elem = parent.find_next(["span", "div", "p", "strong"])
                                    if next_elem:
                                        course_info["slot"] = next_elem.get_text().strip()
                                        break
                            
                            # Only add if we have essential info
                            if "course_code" in course_info and "course_title" in course_info:
                                # Add empty strings for missing fields
                                for field in ["slot", "gcr_code", "faculty_name", "course_type", "room_no"]:
                                    if field not in course_info:
                                        course_info[field] = ""
                                
                                course_data.append(course_info)
                        except Exception as elem_err:
                            logger.warning(f"Error processing course element: {elem_err}")
                    
                    if course_data:
                        logger.info(f"Successfully extracted {len(course_data)} courses from div/list structures")
                        return course_data
            
            # If all methods failed, look for any tables with data that might be course-related
            if not course_data:
                logger.info("Trying generic table extraction as last resort")
                
                for table in all_tables:
                    rows = table.find_all("tr")
                    if len(rows) < 2 or len(rows[0].find_all(["th", "td"])) < 2:
                        continue
                    
                    # Check if table has enough cells that might be course data
                    data_cells = rows[1].find_all(["td", "th"])
                    if len(data_cells) >= 3:
                        for row in rows[1:]:
                            cells = row.find_all(["td", "th"])
                            if len(cells) >= 3:
                                # Assume first cell is code, second is title, third might be slot
                                course_info = {
                                    "course_code": cells[0].get_text().strip(),
                                    "course_title": cells[1].get_text().strip(),
                                    "slot": cells[2].get_text().strip() if len(cells) > 2 else "",
                                    "gcr_code": cells[3].get_text().strip() if len(cells) > 3 else "",
                                    "faculty_name": cells[4].get_text().strip() if len(cells) > 4 else "",
                                    "course_type": cells[5].get_text().strip() if len(cells) > 5 else "",
                                    "room_no": cells[6].get_text().strip() if len(cells) > 6 else ""
                                }
                                
                                # Check if this looks like course data (code usually has letters and numbers)
                                if re.match(r'[A-Za-z0-9]+', course_info["course_code"]) and len(course_info["course_title"]) > 3:
                                    course_data.append(course_info)
                        
                        if course_data:
                            logger.info(f"Extracted {len(course_data)} potential courses via generic table extraction")
                            return course_data
            
            # If all methods failed, return empty list
            logger.warning("All timetable extraction methods failed")
            return []
            
        except Exception as e:
            logger.error(f"Error in alternative timetable scraping: {e}")
            traceback.print_exc()
            return []

    def extract_batch_from_profile(self):
        """
        Try to extract batch info from the user profile page or from cookies
        """
        logger.info("Attempting to extract batch from user profile")
        
        try:
            # Try to navigate to profile page if available
            try:
                profile_links = self.driver.find_elements(By.XPATH, "//a[contains(@href, 'Profile') or contains(@href, 'profile') or contains(text(), 'Profile')]")
                
                if profile_links:
                    # Save current URL to return later
                    current_url = self.driver.current_url
                    
                    # Click on profile link
                    self.click_element_safely(profile_links[0])
                    logger.info("Clicked on profile link")
                    
                    # Wait for profile page to load
                    time.sleep(5)
                    
                    # Look for batch info on the page
                    page_source = self.driver.page_source
                    soup = BeautifulSoup(page_source, "html.parser")
                    
                    # Try various strategies to find batch
                    batch_label = soup.find(string=lambda s: s and "Batch" in s)
                    if batch_label:
                        parent = batch_label.parent
                        # Look for value near this label
                        for i in range(3):  # Check a few levels
                            if not parent:
                                break
                            # Check siblings or children
                            next_elem = parent.find_next(["td", "span", "div", "p", "strong"])
                            if next_elem:
                                batch_text = next_elem.get_text().strip()
                                # Extract numeric part
                                batch_match = re.search(r'(\d+)', batch_text)
                                if batch_match and batch_match.group(1) in ["1", "2"]:
                                    logger.info(f"Found batch {batch_match.group(1)} in profile")
                                    
                                    # Return to original page
                                    self.driver.get(current_url)
                                    
                                    return batch_match.group(1)
                            parent = parent.parent
                    
                    # Return to original page
                    self.driver.get(current_url)
            except Exception as profile_err:
                logger.warning(f"Error accessing profile page: {profile_err}")
            
            # If profile page didn't work, try to extract from cookies or local storage
            logger.info("Trying to extract batch from cookies or storage")
            try:
                # Check cookies
                cookies = self.driver.get_cookies()
                for cookie in cookies:
                    if "batch" in cookie["name"].lower():
                        value = cookie["value"]
                        batch_match = re.search(r'(\d+)', value)
                        if batch_match and batch_match.group(1) in ["1", "2"]:
                            logger.info(f"Found batch {batch_match.group(1)} in cookies")
                            return batch_match.group(1)
                
                # Check local storage
                local_storage = self.driver.execute_script("return Object.keys(localStorage).reduce((obj, key) => {obj[key] = localStorage.getItem(key); return obj;}, {})")
                
                for key, value in local_storage.items():
                    if "batch" in key.lower() and value:
                        batch_match = re.search(r'(\d+)', value)
                        if batch_match and batch_match.group(1) in ["1", "2"]:
                            logger.info(f"Found batch {batch_match.group(1)} in local storage")
                            return batch_match.group(1)
            except Exception as storage_err:
                logger.warning(f"Error extracting from cookies/storage: {storage_err}")
            
            # Try to guess from URL patterns
            try:
                current_url = self.driver.current_url
                batch_param = re.search(r'[?&]batch=(\d+)', current_url)
                if batch_param and batch_param.group(1) in ["1", "2"]:
                    logger.info(f"Found batch {batch_param.group(1)} in URL")
                    return batch_param.group(1)
            except Exception as url_err:
                logger.warning(f"Error extracting from URL: {url_err}")
            
            # If all methods failed, return None
            logger.warning("Could not extract batch information")
            return None
            
        except Exception as e:
            logger.error(f"Error in batch extraction: {e}")
            return None

    def detect_environment(self):
        """
        Detect the current deployment environment and adapt settings accordingly.
        This improves robustness across different hosting platforms.
        """
        environment = {
            "platform": "unknown",
            "is_containerized": False,
            "memory_limit_mb": None,
            "cpu_count": None,
            "python_version": sys.version.split()[0],
            "os": os.name
        }
        
        # Detect platform
        if "RAILWAY_STATIC_URL" in os.environ:
            environment["platform"] = "railway"
            environment["is_containerized"] = True
        elif "RENDER" in os.environ:
            environment["platform"] = "render"
            environment["is_containerized"] = True
        elif "VERCEL" in os.environ or "VERCEL_URL" in os.environ:
            environment["platform"] = "vercel"
            environment["is_containerized"] = True
        elif "KOYEB" in os.environ:
            environment["platform"] = "koyeb"
            environment["is_containerized"] = True
        elif "NETLIFY" in os.environ:
            environment["platform"] = "netlify"
            environment["is_containerized"] = True
        elif "HEROKU_APP_ID" in os.environ:
            environment["platform"] = "heroku"
            environment["is_containerized"] = True
        elif os.path.exists("/.dockerenv"):
            environment["platform"] = "docker"
            environment["is_containerized"] = True
        
        # Try to detect resources
        try:
            import psutil
            memory = psutil.virtual_memory()
            environment["memory_limit_mb"] = memory.total / (1024 * 1024)
            environment["cpu_count"] = psutil.cpu_count()
        except:
            pass
        
        # Log the environment info
        logger.info(f"Detected environment: {environment}")
        
        # Adjust scraper settings based on environment
        if environment["is_containerized"]:
            logger.info("Running in containerized environment, applying optimizations")
            
            # Apply specific optimizations for low-memory environments
            if environment["memory_limit_mb"] and environment["memory_limit_mb"] < 1024:
                logger.info("Low memory environment detected (<1GB), applying aggressive memory optimizations")
                # Will affect setup_driver and other memory-intensive operations
                self.low_memory_mode = True
            else:
                self.low_memory_mode = False
                
            # Platform-specific adjustments
            if environment["platform"] == "railway":
                # Railway-specific settings
                pass
            elif environment["platform"] == "render":
                # Render-specific settings
                pass
        else:
            logger.info("Running in non-containerized environment")
            self.low_memory_mode = False
        
        return environment

    def recover_from_error(self, error_type, context=None):
        """
        Advanced error recovery system that can take different actions based on the type of error.
        This makes the scraper much more resilient to failures.
        """
        logger.info(f"Attempting to recover from {error_type} error in context: {context}")
        
        if error_type == "driver_crash":
            # Handle WebDriver crash
            logger.info("Attempting to restart WebDriver after crash")
            
            if hasattr(self, 'driver') and self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
                self.driver = None
            
            # Reinitialize driver
            try:
                self.driver = self.setup_driver()
                return self.driver is not None
            except Exception as restart_err:
                logger.error(f"Failed to restart WebDriver: {restart_err}")
                return False
                
        elif error_type == "session_expired":
            # Handle expired login session
            logger.info("Attempting to refresh login session")
            
            try:
                if hasattr(self, 'driver') and self.driver:
                    self.is_logged_in = False
                    return self.ensure_login()
                else:
                    logger.error("No active WebDriver to refresh session")
                    return False
            except Exception as login_err:
                logger.error(f"Failed to refresh login session: {login_err}")
                return False
                
        elif error_type == "page_load_timeout":
            # Handle page load timeout
            logger.info("Attempting to recover from page load timeout")
            
            try:
                if hasattr(self, 'driver') and self.driver:
                    # Refresh page with longer timeout
                    self.driver.set_page_load_timeout(60)  # Extended timeout
                    self.driver.refresh()
                    time.sleep(2)
                    return True
                else:
                    logger.error("No active WebDriver for page refresh")
                    return False
            except Exception as refresh_err:
                logger.error(f"Failed to refresh page: {refresh_err}")
                return False
                
        elif error_type == "database_error":
            # Handle database connection error
            logger.info("Attempting to recover from database error")
            
            try:
                # Try a simple query to check if db connection is working again
                test_query = supabase.from_("users").select("count").limit(1).execute()
                logger.info("Database connection restored")
                return True
            except Exception as db_err:
                logger.error(f"Database still unavailable: {db_err}")
                
                # Fall back to local storage if necessary
                if context and isinstance(context, dict) and "data" in context and "user_id" in context:
                    try:
                        # Save to backup file
                        backup_file = f"{context['user_id']}_{int(time.time())}.json"
                        with open(backup_file, 'w') as f:
                            json.dump(context["data"], f)
                        logger.info(f"Saved data to backup file: {backup_file}")
                        return True
                    except Exception as backup_err:
                        logger.error(f"Failed to save backup: {backup_err}")
                
                return False
                
        elif error_type == "stale_element":
            # Handle stale element reference
            logger.info("Attempting to recover from stale element")
            
            try:
                if hasattr(self, 'driver') and self.driver:
                    # Refresh the DOM
                    self.driver.refresh()
                    time.sleep(2)
                    return True
                else:
                    return False
            except Exception as refresh_err:
                logger.error(f"Failed to refresh DOM: {refresh_err}")
                return False
        
        elif error_type == "memory_pressure":
            # Handle memory pressure
            logger.info("Attempting to recover from memory pressure")
            
            try:
                if hasattr(self, 'driver') and self.driver:
                    # Clear cache
                    self.clear_browser_cache()
                    
                    # Execute garbage collection
                    self.driver.execute_script("window.gc();")
                    
                    # Limit open tabs/windows
                    if len(self.driver.window_handles) > 1:
                        current_handle = self.driver.current_window_handle
                        for handle in self.driver.window_handles:
                            if handle != current_handle:
                                self.driver.switch_to.window(handle)
                                self.driver.close()
                        self.driver.switch_to.window(current_handle)
                    
                    # Reduce image loading
                    self.driver.execute_script("""
                        document.querySelectorAll('img').forEach(img => {
                            img.loading = 'lazy';
                            if (img.src && !img.src.startsWith('data:')) {
                                img.setAttribute('data-src', img.src);
                                img.src = '';
                            }
                        });
                    """)
                    
                    logger.info("Applied memory optimization measures")
                    return True
                else:
                    return False
            except Exception as mem_err:
                logger.error(f"Failed to optimize memory: {mem_err}")
                return False
        
        elif error_type == "iframe_switch_failure":
            # Handle iframe switch failures
            logger.info("Attempting to recover from iframe switch failure")
            
            try:
                if hasattr(self, 'driver') and self.driver:
                    # Reset frame context
                    self.driver.switch_to.default_content()
                    
                    # Try a different approach - direct URL navigation
                    if context and isinstance(context, dict) and "target_url" in context:
                        self.driver.get(context["target_url"])
                        logger.info(f"Direct navigation to {context['target_url']}")
                        return True
                    else:
                        # Refresh and try slower loading strategy
                        self.driver.refresh()
                        # Wait longer before attempting iframe operations
                        time.sleep(10)
                        logger.info("Page refreshed with extended wait time")
                        return True
                else:
                    return False
            except Exception as frame_err:
                logger.error(f"Failed to recover from iframe failure: {frame_err}")
                return False
        
        elif error_type == "network_error":
            # Handle network connectivity issues
            logger.info("Attempting to recover from network error")
            
            # Wait for connectivity to return
            for attempt in range(5):
                try:
                    # Check connection by making a lightweight request
                    import requests
                    response = requests.get("https://www.google.com", timeout=5)
                    if response.status_code == 200:
                        logger.info(f"Network connectivity restored after {attempt+1} attempts")
                        
                        # Refresh current page if we have a driver
                        if hasattr(self, 'driver') and self.driver:
                            self.driver.refresh()
                            logger.info("Current page refreshed after network recovery")
                        
                        return True
                except:
                    wait_time = 5 * (attempt + 1)
                    logger.info(f"Network still down, waiting {wait_time} seconds...")
                    time.sleep(wait_time)
            
            logger.error("Failed to recover from network error after multiple attempts")
            return False
        
        # Unknown error type - general recovery attempt
        logger.warning(f"Unknown error type: {error_type}, attempting generic recovery")
        try:
            if hasattr(self, 'driver') and self.driver:
                # Try to refresh the page
                self.driver.refresh()
                time.sleep(3)
                return True
            else:
                return False
        except Exception as generic_err:
            logger.error(f"Generic recovery failed: {generic_err}")
            return False

    def save_cookies_with_fallbacks(self, cookies, email):
        """
        Save cookies with multiple fallback strategies to ensure they're preserved.
        This helps maintain sessions across different environments.
        """
        logger.info(f"Saving cookies for {email} with fallback strategies")
        
        if not cookies:
            logger.error("No cookies to save")
            return False
        
        success = False
        error_messages = []
        
        # Strategy 1: Save to Supabase
        try:
            # Generate JWT token
            token = self.create_jwt_token(email)
            
            if token:
                cookie_data = {
                    'email': email,
                    'cookies': cookies,
                    'token': token,
                    'updated_at': datetime.now().isoformat()
                }
                
                # Delete old record first
                supabase.table('user_cookies').delete().eq('email', email).execute()
                
                # Insert new record
                result = supabase.table('user_cookies').insert(cookie_data).execute()
                if result.data:
                    logger.info("✅ Successfully saved cookies to Supabase")
                    success = True
                else:
                    error_messages.append("Supabase insert returned no data")
            else:
                error_messages.append("Failed to generate JWT token")
        except Exception as db_err:
            error_messages.append(f"Supabase error: {str(db_err)}")
            logger.warning(f"Failed to save cookies to Supabase: {db_err}")
        
        # Strategy 2: Save to local file as backup
        try:
            cookie_file = f"cookies_{email.replace('@', '_at_')}.json"
            with open(cookie_file, 'w') as f:
                json.dump({
                    'email': email,
                    'cookies': cookies,
                    'timestamp': datetime.now().isoformat()
                }, f)
            logger.info(f"✅ Successfully saved cookies to local file: {cookie_file}")
            success = True
        except Exception as file_err:
            error_messages.append(f"File error: {str(file_err)}")
            logger.warning(f"Failed to save cookies to file: {file_err}")
        
        # Strategy 3: Save to environment variables
        try:
            # Convert cookies to a base64-encoded string
            import base64
            cookie_str = json.dumps(cookies)
            encoded_cookies = base64.b64encode(cookie_str.encode()).decode()
            
            # Set environment variable
            os.environ[f"COOKIES_{email.replace('@', '_AT_').upper()}"] = encoded_cookies
            logger.info("✅ Successfully saved cookies to environment variable")
            success = True
        except Exception as env_err:
            error_messages.append(f"Environment error: {str(env_err)}")
            logger.warning(f"Failed to save cookies to environment: {env_err}")
        
        if not success:
            logger.error(f"Failed to save cookies with all strategies: {'; '.join(error_messages)}")
        
        return success

    def load_cookies_with_fallbacks(self, email):
        """
        Load cookies with multiple fallback strategies to ensure maximum reliability.
        """
        logger.info(f"Loading cookies for {email} with fallback strategies")
        
        # Strategy 1: Load from Supabase
        try:
            resp = supabase.table('user_cookies').select('cookies, updated_at').eq('email', email).single().execute()
            
            if resp.data and 'cookies' in resp.data:
                cookies = resp.data['cookies']
                updated_at = resp.data.get('updated_at')
                
                # Check if cookies are stale
                if updated_at:
                    try:
                        updated_time = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                        now = datetime.now(updated_time.tzinfo)
                        age_hours = (now - updated_time).total_seconds() / 3600
                        
                        if age_hours > 12:  # If cookies are older than 12 hours
                            logger.warning(f"Cookies are {age_hours:.1f} hours old, might be stale")
                        else:
                            logger.info(f"Cookies are {age_hours:.1f} hours old, should be fresh")
                    except Exception as date_err:
                        logger.warning(f"Error calculating cookie age: {date_err}")
                
                logger.info("✅ Successfully loaded cookies from Supabase")
                return cookies
        except Exception as db_err:
            logger.warning(f"Failed to load cookies from Supabase: {db_err}")
        
        # Strategy 2: Load from local file
        try:
            cookie_file = f"cookies_{email.replace('@', '_at_')}.json"
            if os.path.exists(cookie_file):
                with open(cookie_file, 'r') as f:
                    data = json.load(f)
                    if 'cookies' in data:
                        logger.info(f"✅ Successfully loaded cookies from file: {cookie_file}")
                        return data['cookies']
        except Exception as file_err:
            logger.warning(f"Failed to load cookies from file: {file_err}")
        
        # Strategy 3: Load from environment variables
        try:
            env_key = f"COOKIES_{email.replace('@', '_AT_').upper()}"
            if env_key in os.environ:
                import base64
                encoded_cookies = os.environ[env_key]
                cookie_str = base64.b64decode(encoded_cookies.encode()).decode()
                cookies = json.loads(cookie_str)
                logger.info("✅ Successfully loaded cookies from environment variable")
                return cookies
        except Exception as env_err:
            logger.warning(f"Failed to load cookies from environment: {env_err}")
        
        logger.warning("No cookies found with any strategy")
        return None

    def login_with_fallbacks(self):
        """
        Multi-stage login strategy that tries Selenium first, then falls back to
        direct requests-based login if Selenium fails. This ensures maximum
        resilience for login which is a critical step.
        """
        logger.info("Attempting login with multiple fallback strategies")
        
        # First try: Selenium-based login
        try:
            logger.info("Trying Selenium-based login")
            selenium_success = self.login()
            
            if selenium_success:
                logger.info("✅ Selenium login successful")
                return True
            else:
                logger.warning("Selenium login failed, trying alternatives")
        except Exception as selenium_err:
            logger.warning(f"Selenium login error: {selenium_err}")
        
        # Second try: Load cookies from storage
        try:
            logger.info("Trying to login with stored cookies")
            stored_cookies = self.load_cookies_with_fallbacks(self.email)
            
            if stored_cookies and len(stored_cookies) > 0:
                # Apply cookies to the driver
                if hasattr(self, 'driver') and self.driver:
                    try:
                        # Clear existing cookies first
                        self.driver.delete_all_cookies()
                        
                        # Add each cookie
                        for cookie in stored_cookies:
                            try:
                                self.driver.add_cookie(cookie)
                            except Exception as cookie_err:
                                logger.warning(f"Error adding cookie: {cookie_err}")
                        
                        # Navigate to homepage to test cookies
                        self.driver.get(BASE_URL)
                        time.sleep(3)
                        
                        # Check if we're logged in
                        if self.is_logged_in_check():
                            logger.info("✅ Login with stored cookies successful")
                            self.is_logged_in = True
                            return True
                    except Exception as cookie_apply_err:
                        logger.warning(f"Error applying cookies: {cookie_apply_err}")
        except Exception as cookie_err:
            logger.warning(f"Cookie-based login error: {cookie_err}")
        
        # Final try: Requests-based login (HTTP fallback)
        try:
            logger.info("Trying HTTP-based fallback login")
            cookies = self.login_with_requests()
            
            if cookies:
                # Save the cookies for future use
                self.save_cookies_with_fallbacks(cookies, self.email)
                
                # Apply cookies to the driver if available
                if hasattr(self, 'driver') and self.driver:
                    try:
                        # Clear existing cookies
                        self.driver.delete_all_cookies()
                        
                        # Add each cookie
                        for name, value in cookies.items():
                            cookie = {
                                'name': name,
                                'value': value,
                                'domain': '.academia.srmist.edu.in',
                                'path': '/'
                            }
                            self.driver.add_cookie(cookie)
                        
                        # Navigate to homepage to test cookies
                        self.driver.get(BASE_URL)
                        time.sleep(3)
                        
                        if self.is_logged_in_check():
                            logger.info("✅ HTTP fallback login and cookie application successful")
                            self.is_logged_in = True
                            return True
                    except Exception as apply_err:
                        logger.warning(f"Error applying HTTP cookies to driver: {apply_err}")
                
                # Even if we couldn't apply to driver, consider this a "partial" success
                # We at least have cookies that could be used later
                logger.info("⚠️ HTTP login successful but cookies not applied to driver")
                self.is_logged_in = True
                return True
        except Exception as http_err:
            logger.error(f"HTTP fallback login error: {http_err}")
        
        # If we reach here, all login methods failed
        logger.error("❌ All login methods failed")
        return False

    def is_logged_in_check(self):
        """Check if we're currently logged in based on page content"""
        if not hasattr(self, 'driver') or not self.driver:
            return False
        
        try:
            # Look for elements that indicate being logged in
            page_source = self.driver.page_source.lower()
            
            # Check 1: Look for logout link/button
            if "logout" in page_source or "sign out" in page_source:
                return True
            
            # Check 2: Look for user profile elements
            if "my profile" in page_source or "my account" in page_source:
                return True
            
            # Check 3: Check for specific dashboard elements
            dashboard_elements = self.driver.find_elements(By.XPATH, 
                                                        "//a[contains(@href, 'My_Attendance') or contains(@href, 'Dashboard')]")
            if dashboard_elements:
                return True
            
            # Check 4: Check for personal greeting with email
            email_prefix = self.email.split('@')[0]
            if email_prefix.lower() in page_source:
                return True
        except Exception as check_err:
            logger.warning(f"Error checking login status: {check_err}")
        
        return False

    def login_with_requests(self):
        """
        HTTP-based login fallback that doesn't rely on Selenium.
        This is useful when browser automation is unreliable.
        """
        logger.info("Performing HTTP-based login")
        
        import requests
        
        # Start a session to maintain cookies
        session = requests.Session()
        
        try:
            # Step 1: Get initial cookies from login page
            logger.info("Fetching login page")
            response = session.get(LOGIN_URL, timeout=30)
            response.raise_for_status()
            
            # Step 2: Extract CSRF token or other form fields if present
            import re
            
            # Extract hidden input fields
            form_fields = {}
            csrf_pattern = re.compile(r'<input[^>]*name=["\'](_csrf|csrfToken|csrf-token)["\'][^>]*value=["\']([^"\']+)["\']', re.IGNORECASE)
            csrf_match = csrf_pattern.search(response.text)
            if csrf_match:
                form_fields[csrf_match.group(1)] = csrf_match.group(2)
                logger.info(f"Found CSRF token: {csrf_match.group(1)}={csrf_match.group(2)}")
            
            # Look for other required hidden fields
            hidden_inputs = re.findall(r'<input[^>]*type=["\']hidden["\'][^>]*name=["\']([^"\']+)["\'][^>]*value=["\']([^"\']*)["\']', response.text)
            for name, value in hidden_inputs:
                form_fields[name] = value
                logger.info(f"Found hidden field: {name}={value}")
            
            # Step 3: Submit login form
            logger.info("Submitting login form")
            login_data = {
                'login_id': self.email,
                'password': self.password,
                **form_fields
            }
            
            # Find login form action URL
            form_action = LOGIN_URL  # Default
            form_action_match = re.search(r'<form[^>]*action=["\']([^"\']+)["\']', response.text)
            if form_action_match:
                form_action = form_action_match.group(1)
                # Handle relative URLs
                if not form_action.startswith('http'):
                    if form_action.startswith('/'):
                        form_action = LOGIN_URL + form_action[1:]
                    else:
                        form_action = LOGIN_URL + form_action
            
            # Submit form
            login_response = session.post(form_action, data=login_data, timeout=30)
            
            # Step 4: Check for login success
            if login_response.url != LOGIN_URL and "login" not in login_response.url.lower():
                logger.info("Login seems successful based on redirect URL")
                
                # Check content for confirmation
                success_indicators = [
                    "dashboard", "attendance", "profile", "my account", "welcome", "logged in"
                ]
                
                if any(indicator in login_response.text.lower() for indicator in success_indicators):
                    logger.info("✅ Login confirmed by page content")
                    
                    # Return the cookies as a dictionary
                    return dict(session.cookies.items())
                else:
                    logger.warning("Login redirect happened but content doesn't confirm login")
            else:
                logger.warning("Login failed, still on login page")
            
            return None
        
        except requests.exceptions.RequestException as req_err:
            logger.error(f"HTTP request error during login: {req_err}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in HTTP login: {e}")
            return None

def run_scraper(email, password, scraper_type="attendance", max_retries=2):
    """
    Enhanced public interface to run the scraper with comprehensive reporting
    and automatic retry logic.
    
    Args:
        email: User's SRM email
        password: User's password
        scraper_type: Type of scraper to run (attendance, timetable, unified)
        max_retries: Number of full retries if execution fails completely
    
    Returns:
        dict: Results of the scraping operation with detailed status info
    """
    result = {
        "status": "error",
        "message": "Not started",
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        "duration_seconds": None,
        "scraper_type": scraper_type,
        "environment": None,
        "retries": 0,
        "data": None,
        "errors": []
    }
    
    # Configure detailed logging
    setup_logging()
    
    # Record start time
    start_time = time.time()
    
    logger.info(f"Starting {scraper_type} scraper for {email}")
    
    # Create scraper instance
    scraper = SRMScraper(email, password)
    
    # Detect environment for adaptive settings
    try:
        result["environment"] = scraper.detect_environment()
    except Exception as env_err:
        logger.warning(f"Environment detection failed: {env_err}")
    
    # Main execution loop with retries
    for attempt in range(max_retries + 1):
        if attempt > 0:
            result["retries"] += 1
            logger.info(f"Retry attempt {attempt}/{max_retries} for the complete scraper")
            # Sleep with exponential backoff
            wait_time = 5 * (2 ** (attempt - 1))
            logger.info(f"Waiting {wait_time} seconds before retry...")
            time.sleep(wait_time)
        
        try:
            # Execute the appropriate scraper type
            if scraper_type.lower() == "attendance":
                scraper_result = scraper.run_attendance_scraper()
            elif scraper_type.lower() == "timetable":
                scraper_result = scraper.run_timetable_scraper()
            elif scraper_type.lower() == "unified":
                scraper_result = scraper.run_unified_scraper()
            else:
                result["message"] = f"Unknown scraper type: {scraper_type}"
                result["errors"].append({
                    "type": "configuration",
                    "message": f"Unknown scraper type: {scraper_type}"
                })
                break
            
            # Update result with scraper output
            result["status"] = scraper_result.get("status", "unknown")
            result["message"] = scraper_result.get("message", "Execution completed without detailed status")
            result["data"] = scraper_result
            
            # If successful, break the retry loop
            if result["status"] == "success" or result["status"] == "partial_success":
                logger.info(f"Scraper executed successfully: {result['status']}")
                break
            else:
                # Log error for retry
                logger.error(f"Scraper execution failed: {result['status']} - {result['message']}")
                result["errors"].append({
                    "type": "execution",
                    "attempt": attempt,
                    "message": result["message"]
                })
        
        except Exception as e:
            # Log the exception
            logger.error(f"Exception during scraper execution: {e}")
            logger.error(traceback.format_exc())
            
            # Update result with error details
            result["errors"].append({
                "type": "exception",
                "attempt": attempt,
                "message": str(e),
                "traceback": traceback.format_exc()
            })
            
            # If all retries are exhausted, update the final status
            if attempt == max_retries:
                result["message"] = f"Failed after {max_retries+1} attempts: {str(e)}"
    
    # Calculate duration
    end_time = time.time()
    result["duration_seconds"] = end_time - start_time
    result["completed_at"] = datetime.now().isoformat()
    
    # Log completion
    logger.info(f"Scraper execution completed in {result['duration_seconds']:.2f} seconds with status: {result['status']}")
    logger.info(f"Total retries: {result['retries']}")
    
    return result

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="SRM Academia Scraper")
    parser.add_argument("--email", required=True, help="SRM Academia email")
    parser.add_argument("--password", required=True, help="SRM Academia password")
    parser.add_argument("--type", choices=["attendance", "timetable", "unified"], default="attendance",
                      help="Type of scraper to run (attendance, timetable, or unified)")
    
    args = parser.parse_args()
    
    result = run_scraper(args.email, args.password, args.type)
    
    if result["status"] == "success":
        print(f"{args.type.capitalize()} data scraped successfully!")
    else:
        print(f"Error: {result.get('message', 'Unknown error')}")