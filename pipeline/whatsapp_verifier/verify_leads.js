/**
 * MESLATT PIPELINE V4 — HEADLESS WHATSAPP BATCH VERIFIER (METHOD A)
 * =================================================================
 * Connects directly to WhatsApp WebSocket protocol via Baileys.
 * Checks whether prospect phone numbers are active WhatsApp accounts
 * without launching a heavy Chromium browser instance.
 *
 * Cost: $0.00 MXN
 * Throughput: ~2,500 - 5,000 checks / hour
 */

import makeWASocket, {
    useMultiFileAuthState,
    DisconnectReason,
    fetchLatestBaileysVersion
} from '@whiskeysockets/baileys';
import pino from 'pino';
import qrcode from 'qrcode-terminal';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Paths
const BASE_DIR = path.resolve(__dirname, '../../../../');
const LEADS_FILE = path.join(BASE_DIR, 'Datasets', 'processed_leads_v4.json');
const AUTH_DIR = path.join(__dirname, 'auth_session');

// Configuration
const BATCH_SIZE = 15;        // Check 15 numbers per batch
const BATCH_DELAY_MS = 350;    // Jitter delay between batches to respect rate limits
const SAVE_INTERVAL = 50;      // Save progress to JSON every 50 leads

/**
 * Normalizes Mexican phone numbers into clean WhatsApp JIDs.
 * Example: "442 123 4567" -> "524421234567@s.whatsapp.net"
 */
function normalizeMexicanPhone(phoneRaw) {
    if (!phoneRaw) return null;
    let digits = phoneRaw.replace(/\D/g, '');

    // Strip leading 0 or 044/045 prefixes (legacy Mexican prefixes)
    if (digits.startsWith('044') || digits.startsWith('045')) {
        digits = digits.substring(3);
    }

    // If 10 digits (Standard Mexican national number)
    if (digits.length === 10) {
        return `521${digits}`; // or 52+digits
    }

    // If 12 digits (already includes 52 + 10 digits)
    if (digits.length === 12 && digits.startsWith('52')) {
        return digits;
    }

    // If 13 digits (521 + 10 digits)
    if (digits.length === 13 && digits.startsWith('521')) {
        return digits;
    }

    return digits.length >= 10 ? digits : null;
}

async function startVerifier() {
    console.log('============================================================');
    console.log('   MESLATT V4 — HEADLESS WHATSAPP BATCH VERIFIER (METHOD A) ');
    console.log('============================================================\n');

    if (!fs.existsSync(LEADS_FILE)) {
        console.error(`❌ Leads database not found at: ${LEADS_FILE}`);
        process.exit(1);
    }

    const rawData = JSON.parse(fs.readFileSync(LEADS_FILE, 'utf-8'));
    const leads = rawData.leads || {};
    const totalLeads = Object.keys(leads).length;
    console.log(`📦 Loaded ${totalLeads.toLocaleString()} total leads from database.`);

    // Filter leads that have a phone and haven't been checked yet
    const pendingLeads = Object.entries(leads).filter(([_, lead]) => {
        return lead.phone && lead.has_whatsapp === undefined;
    });

    console.log(`🔍 Found ${pendingLeads.length.toLocaleString()} leads with pending WhatsApp verification.\n`);

    if (pendingLeads.length === 0) {
        console.log('✅ All prospects have already been verified for WhatsApp. Exiting.');
        process.exit(0);
    }

    // Initialize Baileys Auth Session
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const { version } = await fetchLatestBaileysVersion();

    const sock = makeWASocket({
        version,
        auth: state,
        logger: pino({ level: 'silent' }), // Suppress internal socket logs
        printQRInTerminal: false
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            console.log('📱 SCAN THIS QR CODE WITH YOUR WHATSAPP MOBILE APP (LINKED DEVICES):\n');
            qrcode.generate(qr, { small: true });
            console.log('\n⏳ Waiting for device pairing...');
        }

        if (connection === 'close') {
            const shouldReconnect =
                lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
            console.log(`⚠️ Connection closed. Reconnecting: ${shouldReconnect}`);
            if (shouldReconnect) {
                startVerifier();
            } else {
                console.log('❌ Device logged out. Please delete auth_session folder and re-scan QR.');
            }
        } else if (connection === 'open') {
            console.log('🚀 WHATSAPP PROTOCOL CONNECTED SUCCESSFULLY!\n');
            await processLeadBatches(sock, leads, pendingLeads, rawData);
        }
    });
}

async function processLeadBatches(sock, allLeads, pendingLeads, rawData) {
    let checkedCount = 0;
    let verifiedWhatsAppCount = 0;
    let noWhatsAppCount = 0;

    console.log(`⚡ Starting verification in batches of ${BATCH_SIZE} numbers...\n`);

    for (let i = 0; i < pendingLeads.length; i += BATCH_SIZE) {
        const chunk = pendingLeads.slice(i, i + BATCH_SIZE);
        const queryList = [];

        chunk.forEach(([pid, lead]) => {
            const normalized = normalizeMexicanPhone(lead.phone);
            if (normalized) {
                queryList.push({ pid, normalized, phone: lead.phone });
            } else {
                // Invalid phone format
                allLeads[pid].has_whatsapp = false;
                allLeads[pid].whatsapp_verified_at = new Date().toISOString();
                noWhatsAppCount++;
                checkedCount++;
            }
        });

        if (queryList.length > 0) {
            try {
                // Query WhatsApp directly for batch numbers
                const phoneNumbersToCheck = queryList.map(q => q.normalized);
                const results = await sock.onWhatsApp(...phoneNumbersToCheck);

                const foundMap = new Map();
                if (Array.isArray(results)) {
                    results.forEach(r => {
                        if (r.exists) {
                            foundMap.set(r.jid.split('@')[0], r.jid);
                        }
                    });
                }

                queryList.forEach(q => {
                    const existsJid = foundMap.get(q.normalized) || foundMap.get(q.normalized.replace('521', '52'));
                    if (existsJid) {
                        allLeads[q.pid].has_whatsapp = true;
                        allLeads[q.pid].whatsapp_jid = existsJid;
                        verifiedWhatsAppCount++;
                    } else {
                        allLeads[q.pid].has_whatsapp = false;
                        noWhatsAppCount++;
                    }
                    allLeads[q.pid].whatsapp_verified_at = new Date().toISOString();
                    checkedCount++;
                });

            } catch (err) {
                console.error(`   [!] Batch query error at offset ${i}:`, err.message);
            }
        }

        // Progress update in console
        const percent = ((checkedCount / pendingLeads.length) * 100).toFixed(1);
        process.stdout.write(
            `\r📊 Progress: ${checkedCount}/${pendingLeads.length} (${percent}%) | ` +
            `🟢 WhatsApp Active: ${verifiedWhatsAppCount} | ⚪ No WhatsApp: ${noWhatsAppCount}`
        );

        // Periodic atomic save to disk
        if (checkedCount % SAVE_INTERVAL === 0 || i + BATCH_SIZE >= pendingLeads.length) {
            fs.writeFileSync(LEADS_FILE, JSON.stringify(rawData, null, 2), 'utf-8');
        }

        // Polite jitter delay to prevent rate limiting
        await new Promise(r => setTimeout(r, BATCH_DELAY_MS + Math.floor(Math.random() * 100)));
    }

    // Final save
    fs.writeFileSync(LEADS_FILE, JSON.stringify(rawData, null, 2), 'utf-8');

    console.log('\n\n============================================================');
    console.log('   WHATSAPP BATCH VERIFICATION COMPLETE');
    console.log('============================================================');
    console.log(`✅ Total Checked:    ${checkedCount.toLocaleString()}`);
    console.log(`🟢 Active WhatsApp:  ${verifiedWhatsAppCount.toLocaleString()} (${((verifiedWhatsAppCount / checkedCount) * 100).toFixed(1)}%)`);
    console.log(`⚪ Landline / None:  ${noWhatsAppCount.toLocaleString()} (${((noWhatsAppCount / checkedCount) * 100).toFixed(1)}%)`);
    console.log(`💾 Database updated: ${LEADS_FILE}\n`);

    process.exit(0);
}

// Execute runner
startVerifier().catch(err => {
    console.error('Fatal Verifier Error:', err);
    process.exit(1);
});
