from flask import Flask
from pathlib import Path
import sys

PIPELINE_DIR = Path(__file__).resolve().parent
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from crm_routes import crm_bp

app = Flask(__name__)
# Mount crm_bp at root for standalone execution
app.register_blueprint(crm_bp, url_prefix='')

if __name__ == '__main__':
    print("==================================================")
    print(" PIPELINE CRM SERVER (STANDALONE)")
    print(" Web: http://127.0.0.1:5000/")
    print(" Map: http://127.0.0.1:5000/map")
    print(" Dashboard: http://127.0.0.1:5000/dashboard")
    print("==================================================")
    app.run(host='0.0.0.0', port=5000, debug=True)
