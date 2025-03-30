from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import time
import traceback
import json
import logging
from datetime import datetime, timedelta
import sys
from threading import Thread
from srm_scrapper import SRMScraper, run_scraper
import jwt

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app, origins=["*"], supports_credentials=True)

# Dictionary to track active scraper jobs
active_jobs = {}

# Helper function to extract email from JWT token
def get_email_from_token(request):
    """Extract email from JWT token in Authorization header"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None, "No token provided"
        
    token = auth_header.split(" ")[1]
    
    try:
        # Extract email from token
        decoded = jwt.decode(token, os.environ.get("JWT_SECRET", "default-secret"), algorithms=["HS256"])
        email = decoded.get("email")
        if not email:
            return None, "Invalid token: missing email"
        return email, None
    except Exception as e:
        logger.error(f"Token verification error: {str(e)}")
        return None, f"Invalid token: {str(e)}"

def run_scraper_in_background(email, password, scraper_type="all", cookies=None):
    """Run the scraper in a background thread and update status when done"""
    job_id = f"{email}_{scraper_type}_{int(time.time())}"
    
    try:
        logger.info(f"Starting {scraper_type} scraper for {email}")
        active_jobs[job_id] = {"status": "running", "started_at": datetime.utcnow().isoformat()}
        
        # Run the appropriate scraper
        scraper = SRMScraper(email, password)
        driver_created = False
        
        try:
            # If cookies are provided, try to use them
            if cookies:
                scraper.setup_driver()
                driver_created = True
                scraper.driver.get("https://academia.srmist.edu.in")
                for cookie_name, cookie_value in cookies.items():
                    scraper.driver.add_cookie({"name": cookie_name, "value": cookie_value})
                scraper.is_logged_in = True
            
            if scraper_type == "all":
                result = scraper.run_unified_scraper()
            elif scraper_type == "attendance":
                result = scraper.run_attendance_scraper()
            elif scraper_type == "timetable":
                result = scraper.run_timetable_scraper()
            else:
                raise ValueError(f"Unknown scraper type: {scraper_type}")
                
            # Update job status on completion
            active_jobs[job_id] = {
                "status": "completed",
                "finished_at": datetime.utcnow().isoformat(),
                "result": result
            }
            
            logger.info(f"Scraper job {job_id} completed successfully")
            
        except Exception as e:
            # Ensure we handle errors and clean up resources
            logger.error(f"Error in scraper execution: {str(e)}")
            active_jobs[job_id] = {
                "status": "error",
                "error": str(e),
                "finished_at": datetime.utcnow().isoformat()
            }
        finally:
            # Always ensure browser is closed
            if driver_created and scraper.driver:
                try:
                    scraper.driver.quit()
                    logger.info("Browser resources cleaned up")
                except Exception as ce:
                    logger.error(f"Error closing browser: {str(ce)}")
        
    except Exception as e:
        logger.error(f"Error in scraper job {job_id}: {str(e)}")
        traceback.print_exc()
        active_jobs[job_id] = {
            "status": "error",
            "error": str(e),
            "finished_at": datetime.utcnow().isoformat()
        }

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for load balancers"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }), 200

@app.route("/api/login", methods=["POST"])
def login():
    """Login endpoint that returns cookies for future use"""
    try:
        data = request.get_json()
        email = data.get("email")
        password = data.get("password")
        
        if not email or not password:
            return jsonify({"success": False, "error": "Email and password are required"}), 400
            
        logger.info(f"Login attempt for {email}")
        
        # Create scraper instance and perform login
        scraper = SRMScraper(email, password)
        login_success = scraper.login()
        
        if not login_success:
            return jsonify({"success": False, "error": "Invalid credentials or login failed"}), 401
            
        # Get cookies from the browser
        cookies = {}
        for cookie in scraper.driver.get_cookies():
            cookies[cookie['name']] = cookie['value']
            
        # Clean up browser resources
        try:
            scraper.driver.quit()
        except:
            pass
            
        return jsonify({
            "success": True,
            "message": "Login successful",
            "cookies": cookies
        }), 200
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/scrape", methods=["POST"])
def scrape_data():
    """Endpoint to scrape attendance and marks data"""
    try:
        data = request.get_json()
        email = data.get("email")
        password = data.get("password")
        cookies = data.get("cookies")
        
        if not email:
            return jsonify({"success": False, "error": "Email is required"}), 400
            
        if not cookies and not password:
            return jsonify({"success": False, "error": "Either cookies or password is required"}), 400
            
        # Start scraper in background thread
        thread = Thread(
            target=run_scraper_in_background,
            args=(email, password, "attendance"),
            kwargs={"cookies": cookies},  # Pass cookies to the scraper
            daemon=True
        )
        thread.start()
        
        job_id = f"{email}_attendance_{int(time.time())}"
        
        return jsonify({
            "success": True,
            "message": "Scraper started successfully",
            "job_id": job_id
        }), 202
        
    except Exception as e:
        logger.error(f"Scrape error: {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/scrape-timetable", methods=["POST"])
def scrape_timetable():
    """Endpoint to scrape timetable data"""
    try:
        data = request.get_json()
        email = data.get("email")
        password = data.get("password")
        cookies = data.get("cookies")
        
        if not email:
            return jsonify({"success": False, "error": "Email is required"}), 400
            
        if not cookies and not password:
            return jsonify({"success": False, "error": "Either cookies or password is required"}), 400
            
        # Start scraper in background thread
        thread = Thread(
            target=run_scraper_in_background,
            args=(email, password, "timetable"),
            kwargs={"cookies": cookies},  # Pass cookies to the scraper
            daemon=True
        )
        thread.start()
        
        job_id = f"{email}_timetable_{int(time.time())}"
        
        return jsonify({
            "success": True,
            "message": "Timetable scraper started successfully",
            "job_id": job_id
        }), 202
        
    except Exception as e:
        logger.error(f"Timetable scrape error: {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/scrape-all", methods=["POST"])
def scrape_all():
    """Endpoint to scrape all data at once (timetable, attendance, marks)"""
    try:
        data = request.get_json()
        email = data.get("email")
        password = data.get("password")
        cookies = data.get("cookies")
        
        if not email:
            return jsonify({"success": False, "error": "Email is required"}), 400
            
        if not cookies and not password:
            return jsonify({"success": False, "error": "Either cookies or password is required"}), 400
            
        # Start scraper in background thread
        thread = Thread(
            target=run_scraper_in_background,
            args=(email, password, "all"),
            kwargs={"cookies": cookies},  # Pass cookies to the scraper
            daemon=True
        )
        thread.start()
        
        job_id = f"{email}_all_{int(time.time())}"
        
        return jsonify({
            "success": True,
            "message": "Unified scraper started successfully",
            "job_id": job_id
        }), 202
        
    except Exception as e:
        logger.error(f"Unified scrape error: {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/status/<job_id>", methods=["GET"])
def job_status(job_id):
    """Get status of a running or completed scraper job"""
    try:
        if job_id in active_jobs:
            return jsonify({
                "success": True,
                "job_id": job_id,
                "status": active_jobs[job_id]
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": "Job not found"
            }), 404
            
    except Exception as e:
        logger.error(f"Status check error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/scraper-health", methods=["GET"])
def scraper_health():
    """Check the health of this scraper instance"""
    try:
        # Verify token for authorized access
        email, error = get_email_from_token(request)
        if error:
            return jsonify({"success": False, "error": error}), 401
        
        # Run a quick test to ensure Chrome can be initialized
        scraper = SRMScraper("test@example.com", "password")
        can_initialize = False
        
        try:
            scraper.setup_driver()
            can_initialize = True
            # Clean up immediately
            scraper.driver.quit()
        except Exception as e:
            logger.error(f"Chrome initialization error in health check: {str(e)}")
            
        # Return health status
        return jsonify({
            "success": True,
            "status": "healthy" if can_initialize else "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "memory_usage": get_memory_usage(),
            "active_jobs": len(active_jobs)
        })
    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500
        
def get_memory_usage():
    """Get memory usage of the current process"""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        return {
            "rss_mb": memory_info.rss / (1024 * 1024),
            "vms_mb": memory_info.vms / (1024 * 1024)
        }
    except ImportError:
        return {"error": "psutil not installed"}
    except Exception as e:
        return {"error": str(e)}

@app.route("/api/refresh-data", methods=["POST"])
def refresh_data():
    """Endpoint to refresh user data (called when user clicks refresh button)"""
    try:
        # Get email from token
        email, error = get_email_from_token(request)
        if error:
            return jsonify({"success": False, "error": error}), 401
        
        # Get cookies from request body
        data = request.get_json()
        cookies = data.get("cookies")
        
        if not cookies:
            return jsonify({"success": False, "error": "Cookies are required for refresh"}), 400
            
        logger.info(f"Starting refresh for {email}")
        
        # Start scraper in background thread - attendance is sufficient for refresh
        thread = Thread(
            target=run_scraper_in_background,
            args=(email, None, "attendance"),  # Pass None as password since we're using cookies
            kwargs={"cookies": cookies},
            daemon=True
        )
        thread.start()
        
        job_id = f"{email}_refresh_{int(time.time())}"
        
        return jsonify({
            "success": True,
            "message": "Refresh started successfully",
            "job_id": job_id
        }), 202
        
    except Exception as e:
        logger.error(f"Refresh error: {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/verify-cookies", methods=["POST"])
def verify_cookies():
    """Verify if stored cookies are still valid"""
    try:
        # Get email from token
        email, error = get_email_from_token(request)
        if error:
            return jsonify({"success": False, "error": error}), 401
        
        # Get cookies from request body
        data = request.get_json()
        cookies = data.get("cookies")
        
        if not cookies:
            return jsonify({"success": False, "error": "Cookies are required"}), 400
            
        logger.info(f"Verifying cookies for {email}")
        
        # Create a temporary scraper to verify cookies
        scraper = SRMScraper(email, None)  # No password needed
        
        try:
            # Set up driver and add cookies
            scraper.setup_driver()
            scraper.driver.get("https://academia.srmist.edu.in")
            for cookie_name, cookie_value in cookies.items():
                scraper.driver.add_cookie({"name": cookie_name, "value": cookie_value})
                
            # Try to access a page that requires login
            scraper.driver.get("https://academia.srmist.edu.in/#Page:My_Attendance")
            
            # Wait a bit for the page to load
            time.sleep(2)
            
            # Check if we're still on the login page
            current_url = scraper.driver.current_url
            
            # Clean up resources
            scraper.driver.quit()
            
            # If redirected to login, cookies are invalid
            if "login" in current_url.lower():
                return jsonify({
                    "success": True, 
                    "valid": False,
                    "message": "Cookies expired or invalid"
                })
                
            # Cookies are valid
            return jsonify({
                "success": True,
                "valid": True,
                "message": "Cookies are valid"
            })
            
        except Exception as e:
            # If there's any error, assume cookies are invalid
            if scraper.driver:
                try:
                    scraper.driver.quit()
                except:
                    pass
                    
            logger.error(f"Error verifying cookies: {str(e)}")
            return jsonify({
                "success": True,
                "valid": False,
                "message": f"Error verifying cookies: {str(e)}"
            })
            
    except Exception as e:
        logger.error(f"Cookie verification error: {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/cleanup", methods=["POST"])
def cleanup_resources():
    """Manually trigger cleanup of completed or old jobs"""
    try:
        # Remove jobs older than 2 hours
        cutoff_time = (datetime.utcnow() - timedelta(hours=2)).isoformat()
        jobs_to_remove = []
        
        for job_id, job_info in active_jobs.items():
            # Remove completed or errored jobs
            if job_info.get("status") in ["completed", "error"]:
                if job_info.get("finished_at", "") < cutoff_time:
                    jobs_to_remove.append(job_id)
                    
            # Also remove very old running jobs (probably stalled)
            elif job_info.get("status") == "running" and job_info.get("started_at", "") < cutoff_time:
                jobs_to_remove.append(job_id)
        
        # Remove the jobs
        for job_id in jobs_to_remove:
            active_jobs.pop(job_id, None)
            
        # Force garbage collection
        import gc
        gc.collect()
        
        return jsonify({
            "success": True,
            "message": f"Cleaned up {len(jobs_to_remove)} old jobs",
            "remaining_jobs": len(active_jobs)
        })
        
    except Exception as e:
        logger.error(f"Cleanup error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# Setup automatic cleanup
def start_cleanup_scheduler():
    """Start a background thread that periodically cleans up old jobs"""
    def cleanup_job():
        while True:
            try:
                logger.info("Running scheduled cleanup")
                # Remove jobs older than 2 hours
                cutoff_time = (datetime.utcnow() - timedelta(hours=2)).isoformat()
                jobs_to_remove = []
                
                for job_id, job_info in active_jobs.items():
                    # Remove completed or errored jobs
                    if job_info.get("status") in ["completed", "error"]:
                        if job_info.get("finished_at", "") < cutoff_time:
                            jobs_to_remove.append(job_id)
                            
                    # Also remove very old running jobs (probably stalled)
                    elif job_info.get("status") == "running" and job_info.get("started_at", "") < cutoff_time:
                        jobs_to_remove.append(job_id)
                
                # Remove the jobs
                for job_id in jobs_to_remove:
                    active_jobs.pop(job_id, None)
                    
                if jobs_to_remove:
                    logger.info(f"Auto-cleaned {len(jobs_to_remove)} old jobs")
                    
                # Force garbage collection
                import gc
                gc.collect()
            except Exception as e:
                logger.error(f"Error in scheduled cleanup: {str(e)}")
                
            # Sleep for 30 minutes before next cleanup
            time.sleep(30 * 60)

    # Start the cleanup thread
    cleanup_thread = Thread(target=cleanup_job, daemon=True)
    cleanup_thread.start()
    logger.info("Scheduled cleanup thread started")

@app.route("/api/refresh-status", methods=["GET"])
def refresh_status():
    """Check the status of the most recent refresh job for the user"""
    try:
        # Get email from token
        email, error = get_email_from_token(request)
        if error:
            return jsonify({"success": False, "error": error}), 401
            
        # Find the most recent job for this user
        user_jobs = [job_id for job_id in active_jobs if job_id.startswith(email)]
        if not user_jobs:
            return jsonify({
                "success": True,
                "status": "not_started",
                "message": "No refresh jobs found for this user"
            })
            
        # Get the most recent job (sort by timestamp in job_id)
        recent_job_id = sorted(user_jobs, key=lambda x: int(x.split('_')[-1]) if x.split('_')[-1].isdigit() else 0, reverse=True)[0]
        job_status = active_jobs.get(recent_job_id, {"status": "unknown"})
        
        # Get updated_at timestamp if job is completed
        updated_at = None
        if job_status.get("status") == "completed":
            updated_at = job_status.get("finished_at")
        
        return jsonify({
            "success": True,
            "status": job_status.get("status", "unknown"),
            "updated_at": updated_at,
            "job_id": recent_job_id,
            "message": job_status.get("message", "")
        })
        
    except Exception as e:
        logger.error(f"Refresh status error: {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    # Start the automatic cleanup scheduler
    start_cleanup_scheduler()
    
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting scraper service on port {port}")
    app.run(host="0.0.0.0", port=port) 