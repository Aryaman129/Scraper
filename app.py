from flask import Flask, request, jsonify
import threading
import traceback
from srm_scrapper import SRMScraper
import os
from flask_cors import CORS
import bs4

app = Flask(__name__)
# Enable CORS for all domains to allow calls from any API server
CORS(app, origins="*", supports_credentials=True, allow_headers=["Content-Type", "Authorization"])

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok'}), 200

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    try:
        # Create scraper and perform login
        scraper = SRMScraper(email, password)
        driver = scraper.setup_driver()
        login_success = scraper.login()
        
        if not login_success:
            return jsonify({'success': False, 'error': 'Login failed'}), 401
            
        # Extract cookies from the browser
        browser_cookies = driver.get_cookies()
        cookie_dict = {cookie['name']: cookie['value'] for cookie in browser_cookies}
        
        # Cleanup
        driver.quit()
        
        return jsonify({
            'success': True,
            'cookies': cookie_dict
        })
    except Exception as e:
        print(f"Login error: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/scrape', methods=['POST'])
def scrape():
    data = request.json
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
        
    email = data.get('email')
    cookies = data.get('cookies')
    
    if not email:
        return jsonify({'success': False, 'error': 'Email is required'}), 400
    if not cookies:
        return jsonify({'success': False, 'error': 'Cookies are required'}), 400
    
    print(f"Received scrape request for {email} with {len(cookies)} cookies")
    
    def run_scraper_thread():
        try:
            # Create scraper without password (using cookies)
            scraper = SRMScraper(email, None)
            driver = scraper.setup_driver()
            
            # Apply cookies
            print(f"Applying {len(cookies)} cookies")
            driver.get("https://academia.srmist.edu.in")
            for name, value in cookies.items():
                driver.add_cookie({
                    'name': name,
                    'value': value,
                    'domain': '.srmist.edu.in'
                })
            
            # Get attendance page with intelligent waiting
            print("Navigating to attendance page with smart loading detection")
            html_source = scraper.get_attendance_page()
            
            if html_source:
                # Verify the page loaded correctly
                if "Internal Marks Detail" in html_source or "Course Code" in html_source:
                    print("✅ Page loaded successfully with expected content")
                    
                    # Parse and save data
                    print("Parsing attendance data")
                    # Extract registration number from HTML to get user_id
                    soup = bs4.BeautifulSoup(html_source, "html.parser")
                    registration_number = scraper.extract_registration_number(soup)
                    user_id = scraper.get_user_id_robust(registration_number)
                    
                    attendance_success = scraper.parse_and_save_attendance_robust(html_source, user_id)
                    print(f"Attendance parsing {'succeeded' if attendance_success else 'failed'}")
                    
                    print("Parsing marks data")
                    marks_success = scraper.parse_and_save_marks(html_source, driver)
                    print(f"Marks parsing {'succeeded' if marks_success else 'failed'}")
                else:
                    print("⚠️ Page loaded but may be missing expected content")
                    # Still try to parse the data
                    soup = bs4.BeautifulSoup(html_source, "html.parser")
                    registration_number = scraper.extract_registration_number(soup)
                    user_id = scraper.get_user_id_robust(registration_number)
                    
                    scraper.parse_and_save_attendance_robust(html_source, user_id)
                    scraper.parse_and_save_marks(html_source, driver)
            else:
                print("❌ Failed to get attendance page HTML")
            
            driver.quit()
            print("Scraper thread completed")
            
        except Exception as e:
            print(f"Scraper error: {str(e)}")
            traceback.print_exc()
    
    # Start scraper in background
    threading.Thread(target=run_scraper_thread, daemon=True).start()
    
    return jsonify({
        'success': True,
        'message': 'Scraper started'
    })

@app.route('/api/scrape-timetable', methods=['POST'])
def scrape_timetable():
    data = request.json
    email = data.get('email')
    cookies = data.get('cookies')
    
    if not email:
        return jsonify({'success': False, 'error': 'Email is required'}), 400
    if not cookies:
        return jsonify({'success': False, 'error': 'Cookies are required'}), 400
    
    print(f"Received timetable scrape request for {email} with {len(cookies)} cookies")
    
    def run_timetable_scraper_thread():
        try:
            # Create scraper without password (using cookies)
            scraper = SRMScraper(email, None)
            driver = scraper.setup_driver()
            
            # Apply cookies
            print(f"Applying {len(cookies)} cookies for timetable scraping")
            driver.get("https://academia.srmist.edu.in")
            for name, value in cookies.items():
                driver.add_cookie({
                    'name': name,
                    'value': value,
                    'domain': '.srmist.edu.in'
                })
            
            # Get timetable page
            print("Navigating to timetable page")
            html_source = scraper.get_timetable_page()
            
            if html_source:
                # Parse and save data
                print("Running timetable scraper")
                result = scraper.run_timetable_scraper()
                print(f"Timetable scraping {'succeeded' if result.get('status') == 'success' else 'failed'}")
            else:
                print("Failed to get timetable page HTML")
            
            driver.quit()
            print("Timetable scraper thread completed")
            
        except Exception as e:
            print(f"Timetable scraper error: {str(e)}")
            traceback.print_exc()
    
    # Start scraper in background
    threading.Thread(target=run_timetable_scraper_thread, daemon=True).start()
    
    return jsonify({
        'success': True,
        'message': 'Timetable scraper started'
    })

@app.route('/status', methods=['GET'])
def status():
    """Return version and environment info"""
    import sys
    import platform
    
    return jsonify({
        'status': 'ok',
        'python_version': sys.version,
        'platform': platform.platform(),
        'host': platform.node()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # Use 0.0.0.0 to allow external connections
    app.run(host='0.0.0.0', port=port)
