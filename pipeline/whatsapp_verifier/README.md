# MESLATT Pipeline V4 — Headless WhatsApp Verifier (Method A)

## 📌 Architecture Overview
Uses `@whiskeysockets/baileys` to connect directly to the WhatsApp Multi-Device WebSocket protocol without needing Puppeteer or Chromium.

- **Cost:** `$0.00 MXN`
- **Speed:** ~2,500 – 5,000 queries / hour
- **Target File:** `Datasets/processed_leads_v4.json`
- **Output Fields:**
  - `has_whatsapp: true | false`
  - `whatsapp_jid: string` (e.g., `5214421234567@s.whatsapp.net`)
  - `whatsapp_verified_at: ISO8601 string`

---

## 🚀 How to Run (When Ready)

### 1. Install Dependencies
```bash
cd scripts/allocation_v4/pipeline/whatsapp_verifier
npm install
```

### 2. Launch Verifier
```bash
node verify_leads.js
```
*(Or run via the pipeline orchestrator: `python3 scripts/allocation_v4/pipeline/05_verify_whatsapp.py`)*

### 3. Pair Device
A QR code will render directly in your terminal. Scan it once using the WhatsApp mobile app on a secondary or dedicated business SIM (`Linked Devices` / `Dispositivos Vinculados`).

---

## 🔒 Safety & Best Practices
1. **Never use your primary personal phone number** for automated mass verification to prevent temporary rate-limit blocks.
2. Use a dedicated SIM / eSIM ($50–$100 MXN OXXO chip).
3. The script automatically incorporates **jitter delays** (350–450ms per batch of 15 numbers) to respect WhatsApp's connection limits.
