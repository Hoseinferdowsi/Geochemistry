#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Geochemistry Analysis Application Startup Script
"""

import os
import sys
from geochemistry_analysis_app import app

def main():
    """Main function to start the Flask application"""
    
    # Create necessary directories
    os.makedirs('uploads', exist_ok=True)
    os.makedirs('output', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    
    print("=" * 60)
    print("🌍 Geochemistry Analysis System")
    print("=" * 60)
    print("📁 Uploads directory: ./uploads")
    print("📁 Output directory: ./output")
    print("🌐 Web interface: http://localhost:5000")
    print("=" * 60)
    print("🚀 Starting Flask application...")
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    
    try:
        app.run(
            debug=True,
            host='0.0.0.0',
            port=5000,
            threaded=True
        )
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main() 