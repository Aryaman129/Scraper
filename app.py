from flask import Flask, request, jsonify
import threading
import traceback
from srm_scrapper import SRMScraper, run_scraper
import os

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok'}), 200

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    try:
        # Get cookies from SRM
        scraper = SRMScraper(email, password)
        cookies = scraper.get_srm_cookies()
        
        return jsonify({
            'success': True,
            'cookies': cookies
        })
    except Exception as e:
        print(f"Login error: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/scrape', methods=['POST'])
def scrape():
    data = request.json
    email = data.get('email')
    cookies = data.get('cookies')
    
    def run_scraper_thread():
        try:
            # Create scraper without password (using cookies)
            scraper = SRMScraper(email, None)
            driver = scraper.setup_driver()
            
            # Apply cookies
            driver.get("https://academia.srmist.edu.in")
            for name, value in cookies.items():
                driver.add_cookie({
                    'name': name,
                    'value': value,
                    'domain': '.srmist.edu.in'
                })
            
            # Get attendance page
            html_source = scraper.get_attendance_page()
            
            if html_source:
                # Parse and save data
                scraper.parse_and_save_attendance(html_source, driver)
                scraper.parse_and_save_marks(html_source, driver)
            
            driver.quit()
            
        except Exception as e:
            print(f"Scraper error: {str(e)}")
            traceback.print_exc()
    
    # Start scraper in background
    threading.Thread(target=run_scraper_thread, daemon=True).start()
    
    return jsonify({
        'success': True,
        'message': 'Scraper started'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
