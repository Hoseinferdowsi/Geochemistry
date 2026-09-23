#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Geochemistry Analysis Application Startup Script
"""

import os
import sys
import config
from geochemistry_analysis_app import app, start_cleanup_scheduler

def main():
    """Main function to start the Flask application"""
    
    # Create necessary directories
    os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(config.OUTPUT_FOLDER, exist_ok=True)
    os.makedirs(config.SESSIONS_FOLDER, exist_ok=True)
    os.makedirs(config.TEMPLATES_FOLDER, exist_ok=True)
    
    print("=" * 60)
    print("🌍 Geochemistry Analysis System")
    print("=" * 60)
    print("📁 Uploads directory: ./uploads")
    print("📁 Output directory: ./output")
    print(f"🌐 Web interface: http://localhost:{config.PORT}")
    print("=" * 60)
    print("🚀 Starting Flask application...")
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    
    try:
        start_cleanup_scheduler()
        app.run(
            debug=config.DEBUG,
            host=config.HOST,
            port=config.PORT,
            threaded=True
        )
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main() 