#!/usr/bin/env python3
"""
MEZLAT PIPELINE V4 — STEP 05: WHATSAPP BATCH VERIFIER (ORCHESTRATOR)
====================================================================
Orchestrates the Node.js Baileys headless verifier (Method A).
Checks and updates `has_whatsapp: True | False` in processed_leads_v4.json.
"""

import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
VERIFIER_DIR = Path(__file__).resolve().parent / "whatsapp_verifier"
NODE_SCRIPT = VERIFIER_DIR / "verify_leads.js"
PACKAGE_JSON = VERIFIER_DIR / "package.json"

def check_node_environment():
    """Verifies Node.js and dependencies are ready."""
    try:
        res = subprocess.run(["node", "-v"], capture_output=True, text=True, check=True)
        print(f"📦 Found Node.js: {res.stdout.strip()}")
    except Exception:
        print("❌ Node.js is required to run the Baileys WebSocket verifier.")
        print("   Please install Node.js (https://nodejs.org) or via brew: `brew install node`")
        sys.exit(1)

    node_modules = VERIFIER_DIR / "node_modules"
    if not node_modules.exists():
        print("📥 Installing WhatsApp verifier dependencies (@whiskeysockets/baileys)...")
        subprocess.run(["npm", "install"], cwd=str(VERIFIER_DIR), check=True)

def run_verifier():
    """Launches the interactive verifier."""
    check_node_environment()
    print("\n🚀 Starting Headless WhatsApp Verifier Service (Method A)...")
    subprocess.run(["node", str(NODE_SCRIPT)], cwd=str(VERIFIER_DIR))

if __name__ == "__main__":
    print("============================================================")
    print("   MEZLAT PIPELINE V4 — 05 WHATSAPP PRESENCE VERIFIER      ")
    print("============================================================")
    print("⚠️  Security Note: Ensure you pair using a dedicated business/secondary SIM.\n")
    
    choice = input("Do you want to start the WhatsApp Verifier now? (y/n): ").strip().lower()
    if choice in ("y", "yes"):
        run_verifier()
    else:
        print("⏹️  Verification cancelled by user.")
