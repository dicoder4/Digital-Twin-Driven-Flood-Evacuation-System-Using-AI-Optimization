import { useState, useContext } from 'react';
import {
    Loader, Truck, Anchor, Megaphone, Cpu, CheckCircle,
    ChevronDown, Play, List, ClipboardCheck, Maximize2, X,
    AlertTriangle, Package, Shield, Radio, Download, FileText, FileDown
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { API_URL } from '../config';
import { useAuth } from '../context/AuthContext';
import { createPortal } from 'react-dom';

// ── Tab config ────────────────────────────────────────────────────────────────
const TABS = [
    {
        key: 'logistics',
        label: 'Logistics Chief',
        shortLabel: 'Logistics',
        icon: Truck,
        color: '#2563eb',
        accentLight: '#eff6ff',
        accentBorder: '#bfdbfe',
        headerBg: 'linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%)',
        loadingMsg: 'Calculating supply chains...',
        badge: 'SUPPLY',
        badgeColor: '#1d4ed8',
        description: 'Analyses shelter capacity and allocates critical resources from local inventory. Generates a shelter-by-shelter supply plan.',
    },
    {
        key: 'tactical',
        label: 'Tactical Commander',
        shortLabel: 'Tactical',
        icon: Shield,
        color: '#b45309',
        accentLight: '#fffbeb',
        accentBorder: '#fcd34d',
        headerBg: 'linear-gradient(135deg, #78350f 0%, #b45309 100%)',
        loadingMsg: 'Mapping field operations...',
        badge: 'OPS',
        badgeColor: '#92400e',
        description: 'Deploys rescue assets to hazard zones. Assigns teams to sectors. Identifies escalation needs.',
    },
    {
        key: 'civic',
        label: 'Civic Authority',
        shortLabel: 'Civic',
        icon: Megaphone,
        color: '#16a34a',
        accentLight: '#f0fdf4',
        accentBorder: '#bbf7d0',
        headerBg: 'linear-gradient(135deg, #14532d 0%, #16a34a 100%)',
        loadingMsg: 'Drafting civic communications...',
        badge: 'COMMS',
        badgeColor: '#166534',
        description: 'Drafts official situation reports and public SMS broadcast warnings.',
    },
    {
        key: 'sos_expert',
        label: 'Mass SOS',
        shortLabel: 'SOS',
        icon: Megaphone,
        color: '#dc2626',
        accentLight: '#fef2f2',
        accentBorder: '#fecaca',
        headerBg: 'linear-gradient(135deg, #7f1d1d 0%, #dc2626 100%)',
        loadingMsg: 'Drafting SMS Alerts in EN/KA...',
        badge: 'ALERT',
        badgeColor: '#7f1d1d',
        description: 'Drafts Bilingual Emergency Broadcast formats.',
    },
];

// ── Per-persona table styles ──────────────────────────────────────────────────
const TABLE_THEMES = {
    logistics: {
        headerBg: '#1e3a8a',
        headerColor: '#fff',
        rowEven: '#f8faff',
        rowOdd: '#ffffff',
        borderColor: '#dbeafe',
        statusColors: {
            '🔴': '#fef2f2',
            '🟡': '#fffbeb',
            '🟢': '#f0fdf4',
        },
    },
    tactical: {
        headerBg: '#78350f',
        headerColor: '#fff',
        rowEven: '#fffdf5',
        rowOdd: '#ffffff',
        borderColor: '#fde68a',
        statusColors: {
            '🔴': '#fef2f2',
            '🟡': '#fffbeb',
            '🟢': '#f0fdf4',
        },
    },
    civic: {
        headerBg: '#14532d',
        headerColor: '#fff',
        rowEven: '#f0fdf4',
        rowOdd: '#ffffff',
        borderColor: '#bbf7d0',
        statusColors: {},
    },
};

// ── Markdown component factories ──────────────────────────────────────────────
function makeMarkdownComponents(persona, compact = false) {
    const theme = TABLE_THEMES[persona] || TABLE_THEMES.logistics;
    const tab = TABS.find(t => t.key === persona);
    const fontSize = compact ? '12px' : '14px';
    const pFontSize = compact ? '13px' : '14px';

    return {
        // Tables — themed header, alternating rows
        table: ({ node, ...props }) => (
            <div style={{
                overflowX: 'auto',
                margin: compact ? '10px 0' : '16px 0',
                border: `1px solid ${theme.borderColor}`,
                borderRadius: '8px',
                boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
            }}>
                <table className="expert-md-table" style={{
                    minWidth: '100%',
                    borderCollapse: 'collapse',
                    fontSize,
                }} {...props} />
            </div>
        ),
        thead: ({ node, ...props }) => (
            <thead style={{ background: theme.headerBg }} {...props} />
        ),
        th: ({ node, ...props }) => (
            <th style={{
                padding: compact ? '10px 12px' : '12px 16px',
                textAlign: 'left',
                fontWeight: 700,
                color: theme.headerColor,
                fontSize: compact ? '11px' : '12px',
                letterSpacing: '0.03em',
                textTransform: 'uppercase',
                whiteSpace: 'normal',          // allow wrapping instead of cramming
                wordBreak: 'break-word',
                lineHeight: '1.3',
                minWidth: '60px',
                borderRight: `1px solid rgba(255,255,255,0.15)`,
            }} {...props} />
        ),
        tbody: ({ node, children, ...props }) => (
            <tbody {...props}>{children}</tbody>
        ),
        tr: ({ node, isHeader, children, ...props }) => {
            return <tr style={{
                borderBottom: `1px solid ${theme.borderColor}`,
            }} {...props}>{children}</tr>;
        },
        td: ({ node, ...props }) => (
            <td style={{
                padding: compact ? '10px 12px' : '14px 18px',
                color: '#334155',
                fontSize,
                borderRight: `1px solid ${theme.borderColor}`,
                verticalAlign: 'top',
                lineHeight: '1.5',
            }} {...props} />
        ),

        // Headings
        h1: ({ node, ...props }) => (
            <h1 style={{
                fontSize: compact ? '18px' : '22px',
                fontWeight: 800,
                color: tab?.color || '#0f172a',
                margin: compact ? '0 0 12px' : '0 0 20px',
                paddingBottom: '10px',
                borderBottom: `3px solid ${tab?.color || '#0f172a'}`,
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
            }} {...props} />
        ),
        h2: ({ node, ...props }) => (
            <h2 style={{
                fontSize: compact ? '14px' : '16px',
                fontWeight: 700,
                color: tab?.color || '#1e293b',
                margin: compact ? '18px 0 8px' : '24px 0 10px',
                paddingBottom: '6px',
                borderBottom: `2px solid ${tab?.accentBorder || '#e2e8f0'}`,
                letterSpacing: '0.01em',
            }} {...props} />
        ),
        h3: ({ node, ...props }) => (
            <h3 style={{
                fontSize: compact ? '13px' : '14px',
                fontWeight: 600,
                color: '#475569',
                margin: compact ? '12px 0 6px' : '16px 0 8px',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
            }} {...props} />
        ),

        // Blockquote — used for the status summary line
        blockquote: ({ node, ...props }) => (
            <blockquote style={{
                background: tab?.accentLight || '#f8fafc',
                borderLeft: `4px solid ${tab?.color || '#64748b'}`,
                borderRadius: '0 8px 8px 0',
                padding: compact ? '8px 14px' : '12px 18px',
                margin: compact ? '8px 0' : '12px 0',
                color: '#334155',
                fontSize: pFontSize,
                fontStyle: 'normal',
            }} {...props} />
        ),

        // Paragraphs
        p: ({ node, ...props }) => (
            <p style={{
                margin: compact ? '4px 0 8px' : '6px 0 12px',
                fontSize: pFontSize,
                color: '#1e293b',
                lineHeight: '1.6',
            }} {...props} />
        ),

        // Lists
        ul: ({ node, ...props }) => (
            <ul style={{
                paddingLeft: '20px',
                margin: compact ? '4px 0 8px' : '6px 0 12px',
            }} {...props} />
        ),
        li: ({ node, ...props }) => (
            <li style={{
                margin: compact ? '3px 0' : '5px 0',
                fontSize: pFontSize,
                color: '#1e293b',
                lineHeight: '1.5',
            }} {...props} />
        ),

        strong: ({ node, ...props }) => (
            <strong style={{ fontWeight: 700, color: '#0f172a' }} {...props} />
        ),

        // Horizontal rule — section divider
        hr: ({ node, ...props }) => (
            <hr style={{
                border: 'none',
                borderTop: `1px solid ${tab?.accentBorder || '#e2e8f0'}`,
                margin: compact ? '12px 0' : '20px 0',
            }} {...props} />
        ),

        // Code inline (used for IDs like M-01, Z-02)
        code: ({ node, inline, ...props }) => inline ? (
            <code style={{
                background: tab?.accentLight || '#f1f5f9',
                color: tab?.color || '#334155',
                padding: '1px 5px',
                borderRadius: '4px',
                fontSize: '0.9em',
                fontWeight: 600,
                fontFamily: 'monospace',
            }} {...props} />
        ) : (
            <code style={{
                display: 'block',
                background: '#f8fafc',
                padding: '10px',
                borderRadius: '6px',
                fontSize: '12px',
                fontFamily: 'monospace',
                overflowX: 'auto',
            }} {...props} />
        ),
    };
}

// ── Main component ─────────────────────────────────────────────────────────────
export function PanelOfExperts({ summary, evacuationPlan, locationName: propLocationName }) {
    const { user } = useAuth();
    const [notifyLoading, setNotifyLoading] = useState(false);

    const [isOpen, setIsOpen] = useState(false);
    const [activeTab, setActiveTab] = useState('logistics');
    const [responses, setResponses] = useState({ logistics: '', tactical: '', civic: '' });
    const [loading, setLoading] = useState({ logistics: false, tactical: false, civic: false });
    const [fetched, setFetched] = useState({ logistics: false, tactical: false, civic: false });
    const [isExpanded, setIsExpanded] = useState(false);

    const [showInventory, setShowInventory] = useState(false);
    const [inventoryData, setInventoryData] = useState(null);
    const [loadingInventory, setLoadingInventory] = useState(false);
    const [resourceFilter, setResourceFilter] = useState('all');
    const [distanceFilter, setDistanceFilter] = useState('all');
    const [countData, setCountData] = useState(0);

    const locationName =
        propLocationName ||
        summary?.simulation_location ||
        summary?.simulation?.simulation_location ||
        'Unknown';

    const activeConfig = TABS.find(t => t.key === activeTab);

    // ── Fetch inventory ──────────────────────────────────────────────────────
    const fetchInventory = async () => {
        setShowInventory(true);
        if (!locationName || locationName === 'Unknown') {
            setInventoryData([]);
            return;
        }
        setLoadingInventory(true);
        try {
            const res = await fetch(`${API_URL}/resources/${encodeURIComponent(locationName)}`);
            if (!res.ok) throw new Error('Failed');
            const data = await res.json();
            setInventoryData(Array.isArray(data) ? data : []);
        } catch {
            setInventoryData([]);
        } finally {
            setLoadingInventory(false);
        }
    };

    // ── Update badge count on data mount ────────────────────────────────────
    useState(() => {
        if (summary?.local_inventory) {
            setCountData(summary.local_inventory.length);
        }
    }, [summary]);

    // ── Fetch expert advice ──────────────────────────────────────────────────
    const fetchExpertise = (persona) => {
        if (!summary || loading[persona]) return;
        setLoading(prev => ({ ...prev, [persona]: true }));
        setResponses(prev => ({ ...prev, [persona]: '' }));

        fetch(`${API_URL}/expert-advice-stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                persona,
                summary_data: { ...summary, simulation_location: locationName },
                evacuation_plan: evacuationPlan || [],
            }),
        }).then(async res => {
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const chunk = decoder.decode(value);
                for (const line of chunk.split('\n\n')) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.trim().slice(6));
                            if (data.text) {
                                setResponses(prev => ({ ...prev, [persona]: prev[persona] + data.text }));
                            }
                        } catch { /* ignore */ }
                    }
                }
            }
        }).catch(err => {
            setResponses(prev => ({ ...prev, [persona]: '⚠️ Error: ' + err.message }));
        }).finally(() => {
            setLoading(prev => ({ ...prev, [persona]: false }));
            setFetched(prev => ({ ...prev, [persona]: true }));
        });
    };

    // ── Download report (fully client-side — no backend route needed) ──────────
    const [downloading, setDownloading] = useState({ docx: false, pdf: false });

    // Handle Notify Actions Role-based
    const handleNotifyActions = async () => {
        setNotifyLoading(true);
        try {
            const endpoint = (user?.role === 'authority') ? '/api/notifications/sos' : '/api/notifications/notify-authorities';
            
            // Try to capture map image if a canvas exists on the screen
            let mapImageBase64 = null;
            try {
                // maplibre uses .maplibregl-canvas
                const mapCanvas = document.querySelector('.maplibregl-canvas') || document.querySelector('canvas.mapboxgl-canvas') || document.querySelector('canvas');
                if (mapCanvas) {
                    mapImageBase64 = mapCanvas.toDataURL('image/png').split(',')[1];
                }
            } catch (e) {
                console.warn('Map capture failed', e);
            }

            const payload = {
                user_data: user || {},
                researcher_data: user || {},
                evacuation_data: {
                   algorithm: summary?.algorithm || 'AI Computed',
                   evacuation_time: summary?.ga_execution_time || summary?.avg_distance_per_person || 0.0,
                   evacuated_count: summary?.total_evacuated || 0,
                   total_at_risk: summary?.total_at_risk_initial || summary?.simulation_population || 0
                },
                location_data: { location_name: locationName || 'Unknown' },
                ai_report: (user?.role === 'authority') ? (responses['sos_expert'] || responses['civic']) : (responses['civic'] || ""),
                map_image_base64: mapImageBase64
            };
            const res = await fetch(`${API_URL}${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (res.ok) alert('Notification dispatched successfully!');
            else alert('Failed to send notification: ' + res.statusText);
        } catch(e) {
            alert('Error sending notification.');
        } finally {
            setNotifyLoading(false);
        }
    };


    // Convert markdown to styled HTML (client-side, no server needed)
    const markdownToHtml = (md, persona, location) => {
        const meta = {
            logistics: { color: '#1E3A8A', light: '#DBEAFE', title: 'Logistics Report' },
            tactical:  { color: '#78350F', light: '#FEF3C7', title: 'Tactical Ops Plan' },
            civic:     { color: '#14532D', light: '#DCFCE7', title: 'Civic Situation Report' },
        }[persona] || { color: '#1E3A8A', light: '#DBEAFE', title: 'Report' };

        // ── Parse markdown tables first (before line-level transforms) ────────
        // Split into blocks; convert table blocks to HTML, leave others alone
        const blocks = md.split('\n\n');
        const convertedBlocks = blocks.map(block => {
            const lines = block.split('\n');
            // Detect markdown table: has | characters and a separator row (---)
            const hasPipe = lines.some(l => l.includes('|'));
            const hasSep  = lines.some(l => l.trim().startsWith('|') && l.includes('-') && !l.replace(/-/g, '').replace(/\|/g, '').replace(/:/g, '').replace(/ /g, '').trim());
            if (!hasPipe || !hasSep) return block;

            // Strip leading/trailing pipe, split on |
            const stripPipes = (row) => {
                const trimmed = row.trim();
                const inner = trimmed.startsWith('|') ? trimmed.slice(1) : trimmed;
                const final = inner.endsWith('|') ? inner.slice(0, -1) : inner;
                return final.split('|').map(c => c.trim());
            };

            const tableLines = lines.filter(l => l.trim().startsWith('|'));
            if (tableLines.length < 2) return block;

            const headerCells = stripPipes(tableLines[0]);
            // Skip separator row (index 1), rest are data rows
            const dataRows = tableLines.slice(2).map(stripPipes);

            const thHtml = headerCells.map(h => '<th>' + h + '</th>').join('');
            const tbHtml = dataRows.map(cells =>
                '<tr>' + cells.map(c => '<td>' + c + '</td>').join('') + '</tr>'
            ).join('');

            return '<table><thead><tr>' + thHtml + '</tr></thead><tbody>' + tbHtml + '</tbody></table>';
        });
        let html = convertedBlocks.join('\n\n');

        // ── Line-level transforms ─────────────────────────────────────────────
        html = html
            .replace(/^---$/gm, '<hr>')
            .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
            .replace(/^# (.+)$/gm, '<h1>$1</h1>')
            .replace(/^## (.+)$/gm, '<h2>$1</h2>')
            .replace(/^### (.+)$/gm, '<h3>$1</h3>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .replace(/`(.+?)`/g, '<code>$1</code>')
            .replace(/^- (.+)$/gm, '<li>$1</li>');

        // Wrap consecutive li elements in ul
        html = html.replace(/(<li>[\s\S]+?<\/li>)(\s*)(?!<li>)/g, '<ul>$1</ul>');

        // Double newlines → paragraph breaks
        html = html.replace(/\n\n+/g, '</p><p>');

        // Already a table/heading/hr — don't wrap in <p>
        // (this is cosmetic; browsers handle it gracefully either way)

        const ts = new Date().toLocaleString('en-IN', { dateStyle: 'long', timeStyle: 'short' });
        return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>${meta.title} — ${location}</title>
<style>
  body { font-family: Arial, sans-serif; font-size: 11pt; color: #334155;
         max-width: 960px; margin: 0 auto; padding: 24px 32px; }
  h1   { color: ${meta.color}; border-bottom: 3px solid ${meta.color};
         padding-bottom: 8px; font-size: 20pt; margin-top: 0; }
  h2   { color: ${meta.color}; border-bottom: 1px solid #CBD5E1;
         padding-bottom: 4px; font-size: 14pt; margin-top: 24pt; }
  h3   { color: #475569; font-size: 11pt; margin-top: 14pt;
         text-transform: uppercase; letter-spacing: 0.04em; }
  blockquote { background: ${meta.light}; border-left: 4px solid ${meta.color};
               padding: 10px 14px; margin: 10px 0; border-radius: 0 6px 6px 0; font-style: normal; }
  table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 10pt; }
  th    { background: ${meta.color}; color: #fff; padding: 8px 10px;
          text-align: left; font-weight: bold; }
  td    { padding: 7px 10px; border-bottom: 1px solid #E2E8F0; vertical-align: top; }
  tr:nth-child(even) td { background: #F8FAFC; }
  ul    { padding-left: 20px; margin: 6px 0; }
  li    { margin: 3px 0; }
  code  { background: #F1F5F9; padding: 1px 4px; border-radius: 3px;
          font-size: 9pt; font-family: monospace; }
  hr    { border: none; border-top: 1px solid #E2E8F0; margin: 16px 0; }
  strong { font-weight: 700; color: #0f172a; }
  p     { margin: 6px 0 10px; line-height: 1.6; }
  .report-header { border-bottom: 2px solid ${meta.color}; margin-bottom: 20px;
                   padding-bottom: 12px; display: flex;
                   justify-content: space-between; align-items: flex-end; }
  .report-meta   { font-size: 9pt; color: #64748B; text-align: right; }
  @media print {
    body { padding: 10px; }
    h1, h2 { page-break-after: avoid; }
    table  { page-break-inside: avoid; }
  }
</style>
</head>
<body>
<div class="report-header">
  <div><strong style="color:${meta.color};font-size:9pt;letter-spacing:0.1em;">${persona.toUpperCase()} REPORT · CONFIDENTIAL</strong></div>
  <div class="report-meta">Location: ${location}<br>Generated: ${ts}</div>
</div>
<p>${html}</p>
</body>
</html>`;
    };

    const handleDownload = (format) => {
        const markdown = responses[activeTab];
        if (!markdown) return;
        setDownloading(prev => ({ ...prev, [format]: true }));

        try {
            const ts       = new Date().toISOString().slice(0,16).replace(/[-:T]/g,'_');
            const loc      = (locationName || 'location').replace(/[^a-zA-Z0-9_-]/g, '_');
            const html     = markdownToHtml(markdown, activeTab, locationName);

            if (format === 'pdf') {
                // Open in new window → user prints to PDF (Ctrl+P → Save as PDF)
                const win = window.open('', '_blank');
                if (!win) { alert('Please allow pop-ups for this site to download PDF.'); return; }
                win.document.write(html);
                win.document.close();
                // Small delay so content renders before print dialog
                setTimeout(() => {
                    win.focus();
                    win.print();
                }, 600);
            } else {
                // Word: download as .doc — Word and LibreOffice both open HTML .doc files
                // The mhtml MIME trick wraps it so Word opens it natively
                const blob     = new Blob([html], { type: 'application/msword;charset=utf-8' });
                const url      = URL.createObjectURL(blob);
                const filename = `${activeTab.toUpperCase()}_REPORT_${loc}_${ts}.doc`;
                const a        = document.createElement('a');
                a.href         = url;
                a.download     = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }
        } catch (err) {
            console.error('Download error:', err);
            alert('Download failed: ' + err.message);
        } finally {
            // Slight delay so the spinner shows briefly
            setTimeout(() => setDownloading(prev => ({ ...prev, [format]: false })), 800);
        }
    };

    // ── Inventory modal ──────────────────────────────────────────────────────
    const InventoryModal = () => {
        if (!showInventory) return null;
        let list = inventoryData || [];
        let warningItem = null;
        if (list.length > 0 && list[0].type === 'Info') {
            warningItem = list[0];
            list = list.slice(1);
        }
        const filtered = list.filter(item => {
            const rMatch = resourceFilter === 'all' || (item.type || '').toLowerCase() === resourceFilter;
            const dMatch = distanceFilter === 'all' || (item.category_distance || 'distant').toLowerCase() === distanceFilter;
            return rMatch && dMatch;
        });

        const FilterPill = ({ id, label, color, active, onClick }) => (
            <button onClick={() => onClick(id)} style={{
                padding: '5px 12px', borderRadius: '20px',
                border: `1px solid ${active === id ? color : '#e2e8f0'}`,
                backgroundColor: active === id ? color + '18' : 'white',
                color: active === id ? color : '#64748b',
                fontSize: '12px', fontWeight: 500, cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: '5px',
                transition: 'all 0.15s',
            }}>
                {label}
                {active === id && <CheckCircle size={12} />}
            </button>
        );

        return createPortal(
            <div style={{
                position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
                display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999,
            }}>
                <div style={{
                    backgroundColor: 'white', borderRadius: '10px',
                    width: '820px', maxWidth: '95%', maxHeight: '85vh',
                    display: 'flex', flexDirection: 'column',
                    boxShadow: '0 20px 40px rgba(0,0,0,0.2)',
                }}>
                    {/* Header */}
                    <div style={{
                        padding: '14px 18px', borderBottom: '1px solid #e2e8f0',
                        background: 'linear-gradient(135deg,#1e293b,#334155)',
                        borderRadius: '10px 10px 0 0',
                    }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                            <h3 style={{ margin: 0, color: '#fff', fontSize: '16px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <Package size={18} /> Local Resource Inventory — {locationName}
                            </h3>
                            <button onClick={() => setShowInventory(false)} style={{ background: 'rgba(255,255,255,0.15)', border: 'none', borderRadius: '50%', width: '30px', height: '30px', cursor: 'pointer', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                <X size={16} />
                            </button>
                        </div>
                        <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                            <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                                <span style={{ fontSize: '11px', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Type:</span>
                                <FilterPill id="all" label="All" color="#64748b" active={resourceFilter} onClick={setResourceFilter} />
                                <FilterPill id="logistics" label="Logistics" color="#3b82f6" active={resourceFilter} onClick={setResourceFilter} />
                                <FilterPill id="tactical" label="Tactical" color="#f59e0b" active={resourceFilter} onClick={setResourceFilter} />
                                <FilterPill id="civic" label="Civic" color="#16a34a" active={resourceFilter} onClick={setResourceFilter} />
                            </div>
                            <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                                <span style={{ fontSize: '11px', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Dist:</span>
                                <FilterPill id="all" label="Any" color="#64748b" active={distanceFilter} onClick={setDistanceFilter} />
                                <FilterPill id="immediate" label="< 5km" color="#16a34a" active={distanceFilter} onClick={setDistanceFilter} />
                                <FilterPill id="extended" label="5–15km" color="#ca8a04" active={distanceFilter} onClick={setDistanceFilter} />
                                <FilterPill id="distant" label="> 15km" color="#dc2626" active={distanceFilter} onClick={setDistanceFilter} />
                            </div>
                            <span style={{ marginLeft: 'auto', fontSize: '12px', color: '#94a3b8', alignSelf: 'center' }}>
                                {filtered.length} items
                            </span>
                        </div>
                    </div>

                    {warningItem && (
                        <div style={{ backgroundColor: '#fffbeb', borderBottom: '1px solid #fcd34d', padding: '10px 18px', display: 'flex', gap: '10px', color: '#92400e', fontSize: '13px' }}>
                            <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: '2px', color: '#d97706' }} />
                            <div><strong>{warningItem.item}</strong> — {warningItem.source}</div>
                        </div>
                    )}

                    <div className="custom-scrollbar" style={{ overflowY: 'auto', flex: 1 }}>
                        {loadingInventory ? (
                            <div style={{ textAlign: 'center', padding: '40px', color: '#64748b' }}>
                                <Loader size={24} className="spin" style={{ marginBottom: '10px' }} />
                                <div>Scanning resource nodes...</div>
                            </div>
                        ) : filtered.length > 0 ? (
                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                                <thead style={{ position: 'sticky', top: 0, background: '#1e293b', zIndex: 1 }}>
                                    <tr>
                                        {['Item', 'Type', 'Qty', 'Distance', 'Source / Contact'].map(h => (
                                            <th key={h} style={{
                                                padding: '10px 12px', textAlign: 'left', fontWeight: 700,
                                                fontSize: '11px', color: '#e2e8f0',
                                                textTransform: 'uppercase', letterSpacing: '0.04em',
                                                whiteSpace: 'normal', lineHeight: '1.3',
                                                borderRight: '1px solid rgba(255,255,255,0.12)',
                                            }}>{h}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {filtered.map((item, i) => (
                                        <tr key={i} style={{ backgroundColor: i % 2 === 0 ? '#ffffff' : '#f8fafc', borderBottom: '1px solid #f1f5f9' }}>
                                            <td style={{ padding: '10px 12px' }}>
                                                <div style={{ fontWeight: 600, color: '#0f172a' }}>{item.item}</div>
                                                {item.activity && <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>{item.activity}</div>}
                                            </td>
                                            <td style={{ padding: '10px 12px' }}>
                                                {item.type === 'Tactical'
                                                    ? <span style={{ color: '#b45309', fontWeight: 700, fontSize: '11px', display: 'flex', alignItems: 'center', gap: '3px' }}><Shield size={12} /> TAC</span>
                                                    : <span style={{ color: '#2563eb', fontWeight: 700, fontSize: '11px', display: 'flex', alignItems: 'center', gap: '3px' }}><Truck size={12} /> LOG</span>
                                                }
                                            </td>
                                            <td style={{ padding: '10px 12px', fontWeight: 700, color: '#0f172a' }}>{item.qty}</td>
                                            <td style={{ padding: '10px 12px', color: '#64748b' }}>{item.distance || 'N/A'}</td>
                                            <td style={{ padding: '10px 12px' }}>
                                                <div style={{ fontWeight: 500, color: '#334155', fontSize: '12px' }}>{item.source}</div>
                                                <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px', display: 'flex', gap: '10px' }}>
                                                    {item.contact && <span>👤 {item.contact}</span>}
                                                    {item.phone && <span style={{ color: '#2563eb' }}>📞 {item.phone}</span>}
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        ) : (
                            <div style={{ padding: '40px', textAlign: 'center', color: '#94a3b8' }}>
                                No resources match the current filter.
                            </div>
                        )}
                    </div>
                </div>
            </div>,
            document.body
        );
    };

    // ── Expanded report modal ────────────────────────────────────────────────
    const ReportModal = () => {
        if (!isExpanded) return null;
        const mdComponents = makeMarkdownComponents(activeTab, false);

        return createPortal(
            <div
                style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 10000, backdropFilter: 'blur(3px)' }}
                onClick={() => setIsExpanded(false)}
            >
                <div
                    style={{ backgroundColor: 'white', borderRadius: '12px', width: '960px', maxWidth: '95vw', height: '88vh', display: 'flex', flexDirection: 'column', boxShadow: '0 25px 60px rgba(0,0,0,0.3)', overflow: 'hidden' }}
                    onClick={e => e.stopPropagation()}
                >
                    {/* Coloured header bar */}
                    <div style={{
                        background: activeConfig?.headerBg,
                        padding: '14px 20px',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                            {(() => { const I = activeConfig?.icon; return I ? <I size={22} color="rgba(255,255,255,0.9)" /> : null; })()}
                            <div>
                                <div style={{ color: 'rgba(255,255,255,0.7)', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em' }}>{activeConfig?.badge} REPORT</div>
                                <div style={{ color: '#fff', fontSize: '17px', fontWeight: 700 }}>{activeConfig?.label} — {locationName}</div>
                            </div>
                        </div>
                        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                            {activeTab === 'civic' && (
                                <button
                                    onClick={handleNotifyActions}
                                    disabled={notifyLoading}
                                    style={{
                                        background: '#f59e0b', color: '#fff', border: 'none', borderRadius: '4px',
                                        cursor: 'pointer', padding: '6px 12px', display: 'flex', alignItems: 'center', fontSize: '13px'
                                    }}>
                                    {notifyLoading ? 'Sending...' : (user?.role === 'authority' ? 'Broadcast Mass SOS' : 'Notify Authorities')}
                                </button>
                            )}
                            <button
                                onClick={() => handleDownload('docx')}
                                disabled={downloading.docx}
                                style={{
                                    background: 'rgba(255,255,255,0.15)', border: '1px solid rgba(255,255,255,0.3)',
                                    borderRadius: '6px', padding: '6px 12px', cursor: downloading.docx ? 'wait' : 'pointer',
                                    color: '#fff', display: 'flex', alignItems: 'center', gap: '6px',
                                    fontSize: '12px', fontWeight: 600,
                                    opacity: downloading.docx ? 0.6 : 1,
                                }}
                            >
                                {downloading.docx ? <Loader size={13} className="spin" /> : <FileText size={13} />}
                                Download Word
                            </button>
                            <button
                                onClick={() => handleDownload('pdf')}
                                disabled={downloading.pdf}
                                style={{
                                    background: 'rgba(255,255,255,0.15)', border: '1px solid rgba(255,255,255,0.3)',
                                    borderRadius: '6px', padding: '6px 12px', cursor: downloading.pdf ? 'wait' : 'pointer',
                                    color: '#fff', display: 'flex', alignItems: 'center', gap: '6px',
                                    fontSize: '12px', fontWeight: 600,
                                    opacity: downloading.pdf ? 0.6 : 1,
                                }}
                            >
                                {downloading.pdf ? <Loader size={13} className="spin" /> : <FileDown size={13} />}
                                Download PDF
                            </button>
                            <button onClick={() => setIsExpanded(false)} style={{ background: 'rgba(255,255,255,0.15)', border: 'none', borderRadius: '50%', width: '34px', height: '34px', cursor: 'pointer', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                <X size={18} />
                            </button>
                        </div>
                    </div>

                    <div className="custom-scrollbar" style={{ padding: '28px 32px', overflowY: 'auto', flex: 1, background: '#fafafa' }}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                            {responses[activeTab]}
                        </ReactMarkdown>
                    </div>
                </div>
            </div>,
            document.body
        );
    };

    // ── Inline report preview ────────────────────────────────────────────────
    const InlineReport = () => {
        const mdComponents = makeMarkdownComponents(activeTab, true);
        return (
            <div style={{ position: 'relative' }}>
                {/* Action bar: Expand + Download buttons */}
                <div style={{ position: 'absolute', top: 0, right: 0, zIndex: 10,
                              display: 'flex', gap: '4px', alignItems: 'center' }}>
                    {activeTab === 'civic' && (
                                <button
                                    onClick={handleNotifyActions}
                                    disabled={notifyLoading}
                                    style={{
                                        background: '#f59e0b', color: '#fff', border: 'none', borderRadius: '4px',
                                        cursor: 'pointer', padding: '6px 12px', display: 'flex', alignItems: 'center', fontSize: '13px'
                                    }}>
                                    {notifyLoading ? 'Sending...' : (user?.role === 'authority' ? 'Broadcast Mass SOS' : 'Notify Authorities')}
                                </button>
                            )}
                    <button
                        onClick={() => handleDownload('docx')}
                        title="Download as Word (.docx)"
                        disabled={downloading.docx}
                        style={{
                            background: activeConfig?.accentLight,
                            border: `1px solid ${activeConfig?.accentBorder}`,
                            borderRadius: '6px', padding: '5px 9px',
                            cursor: downloading.docx ? 'wait' : 'pointer',
                            color: activeConfig?.color,
                            display: 'flex', alignItems: 'center', gap: '4px',
                            fontSize: '11px', fontWeight: 600, transition: 'all 0.15s',
                            opacity: downloading.docx ? 0.6 : 1,
                        }}
                    >
                        {downloading.docx
                            ? <Loader size={11} className="spin" />
                            : <FileText size={11} />}
                        Word
                    </button>
                    <button
                        onClick={() => handleDownload('pdf')}
                        title="Download as PDF"
                        disabled={downloading.pdf}
                        style={{
                            background: activeConfig?.accentLight,
                            border: `1px solid ${activeConfig?.accentBorder}`,
                            borderRadius: '6px', padding: '5px 9px',
                            cursor: downloading.pdf ? 'wait' : 'pointer',
                            color: activeConfig?.color,
                            display: 'flex', alignItems: 'center', gap: '4px',
                            fontSize: '11px', fontWeight: 600, transition: 'all 0.15s',
                            opacity: downloading.pdf ? 0.6 : 1,
                        }}
                    >
                        {downloading.pdf
                            ? <Loader size={11} className="spin" />
                            : <FileDown size={11} />}
                        PDF
                    </button>
                    <button
                        onClick={() => setIsExpanded(true)}
                        title="Open full report"
                        style={{
                            background: activeConfig?.accentLight,
                            border: `1px solid ${activeConfig?.accentBorder}`,
                            borderRadius: '6px', padding: '5px 9px',
                            cursor: 'pointer', color: activeConfig?.color,
                            display: 'flex', alignItems: 'center', gap: '4px',
                            fontSize: '11px', fontWeight: 600, transition: 'all 0.15s',
                        }}
                        onMouseOver={e => e.currentTarget.style.opacity = '0.85'}
                        onMouseOut={e => e.currentTarget.style.opacity = '1'}
                    >
                        <Maximize2 size={11} /> Expand
                    </button>
                </div>

                <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                    {responses[activeTab]}
                </ReactMarkdown>

                {loading[activeTab] && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '8px', fontSize: '11px', color: '#94a3b8' }}>
                        <Loader size={10} className="spin" /> Generating...
                    </div>
                )}
            </div>
        );
    };

    // ── Main render ──────────────────────────────────────────────────────────
    const activeThemeConfig = TABLE_THEMES[activeTab] || TABLE_THEMES.logistics;

    return (
        <div className="expert-panel-wrapper expert-markdown-container">
            <style>{`
                .expert-markdown-container table.expert-md-table tbody tr:nth-child(even) td {
                    background-color: ${activeThemeConfig.rowEven};
                }
                .expert-markdown-container table.expert-md-table tbody tr:nth-child(odd) td {
                    background-color: ${activeThemeConfig.rowOdd};
                }
                .expert-markdown-container table.expert-md-table tbody tr:hover td {
                    background-color: ${activeTab === 'logistics' ? '#eff6ff' : activeTab === 'tactical' ? '#fef3c7' : '#dcfce3'} !important;
                    transition: background-color 0.15s ease;
                }
            `}</style>
            
            <InventoryModal />
            <ReportModal />

            {/* Toggle header */}
            <button className="expert-panel-toggle" onClick={() => setIsOpen(p => !p)}>
                <span className="expert-panel-toggle-title">
                    <Cpu size={13} /> AI Panel of Experts
                </span>
                <ChevronDown size={13} className={`genai-chevron ${isOpen ? 'genai-chevron--open' : ''}`} />
            </button>

            {isOpen && (
                <div className="expert-panel-body">
                    {/* ── Row 1: Tab Pills ────────────────────────────── */}
                    <div
                        className="expert-tabs"
                        style={{
                            display: 'flex',
                            borderBottom: '2px solid #f1f5f9',
                            background: '#fff',
                            overflowX: 'auto',
                        }}
                    >
                        {TABS.map(tab => {
                            const Icon = tab.icon;
                            const isActive = activeTab === tab.key;
                            const isDone = fetched[tab.key] && !loading[tab.key] && responses[tab.key];
                            const isLoading = loading[tab.key];
                            return (
                                <button
                                    key={tab.key}
                                    onClick={() => setActiveTab(tab.key)}
                                    style={{
                                        flex: '1 1 auto',
                                        minWidth: 'max-content',
                                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '5px',
                                        padding: '9px 10px',
                                        border: 'none',
                                        borderBottom: isActive ? `3px solid ${tab.color}` : '3px solid transparent',
                                        background: isActive ? tab.accentLight : 'transparent',
                                        color: isActive ? tab.color : '#64748b',
                                        cursor: 'pointer',
                                        fontSize: '12px', fontWeight: isActive ? 700 : 500,
                                        transition: 'all 0.15s',
                                        marginBottom: '-2px',
                                        whiteSpace: 'nowrap',
                                    }}
                                >
                                    <Icon size={13} />
                                    <span>{tab.shortLabel}</span>
                                    {isActive && (
                                        <span style={{
                                            background: tab.color, color: '#fff',
                                            fontSize: '9px', fontWeight: 800,
                                            padding: '1px 5px', borderRadius: '4px',
                                            letterSpacing: '0.05em',
                                        }}>{tab.badge}</span>
                                    )}
                                    {isLoading && <Loader size={10} className="spin" />}
                                    {isDone && <CheckCircle size={10} style={{ color: '#16a34a' }} />}
                                </button>
                            );
                        })}

                        {/* Inventory button pinned to right of tab row */}
                        <div style={{
                            display: 'flex', alignItems: 'center',
                            padding: '0 10px', marginLeft: 'auto',
                            borderLeft: '1px solid #f1f5f9', flexShrink: 0,
                        }}>
                            <button
                                onClick={fetchInventory}
                                style={{
                                    display: 'flex', alignItems: 'center', gap: '5px',
                                    background: '#f8fafc', border: '1px solid #e2e8f0',
                                    borderRadius: '5px', padding: '5px 9px',
                                    fontSize: '11px', color: '#475569', cursor: 'pointer',
                                    fontWeight: 500, transition: 'all 0.15s', whiteSpace: 'nowrap',
                                }}
                                onMouseOver={e => { e.currentTarget.style.borderColor = '#94a3b8'; e.currentTarget.style.color = '#1e293b'; }}
                                onMouseOut={e => { e.currentTarget.style.borderColor = '#e2e8f0'; e.currentTarget.style.color = '#475569'; }}
                            >
                                <List size={12} /> Inventory
                                {countData > 0 && (
                                    <span style={{
                                        background: '#3b82f6', color: '#fff', fontSize: '9px',
                                        padding: '1px 4px', borderRadius: '8px', fontWeight: 700,
                                    }}>{countData}</span>
                                )}
                            </button>
                        </div>
                    </div>


                    {/* Content area */}
                    <div
                        className="expert-content custom-scrollbar"
                        style={{
                            background: '#fff',
                            padding: '14px 16px',
                            borderRadius: '0 0 6px 6px',
                            minHeight: '160px',
                            maxHeight: '480px',
                            overflowY: 'auto',
                            border: `1px solid ${activeConfig?.accentBorder || '#e2e8f0'}`,
                            borderTop: `3px solid ${activeConfig?.color || '#3b82f6'}`,
                        }}
                    >
                        {/* Empty state */}
                        {!fetched[activeTab] && !loading[activeTab] && !responses[activeTab] && (
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '14px', padding: '24px', textAlign: 'center' }}>
                                <div style={{
                                    width: '48px', height: '48px', borderRadius: '50%',
                                    background: activeConfig?.accentLight,
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                }}>
                                    {(() => { const I = activeConfig?.icon; return I ? <I size={22} color={activeConfig.color} /> : null; })()}
                                </div>
                                <div>
                                    <div style={{ fontWeight: 700, fontSize: '14px', color: '#1e293b', marginBottom: '4px' }}>
                                        {activeConfig?.label}
                                    </div>
                                    <div style={{ fontSize: '12px', color: '#64748b', maxWidth: '320px', lineHeight: 1.5 }}>
                                        {activeConfig?.description}
                                    </div>
                                </div>
                                <button
                                    onClick={() => fetchExpertise(activeTab)}
                                    style={{
                                        display: 'flex', alignItems: 'center', gap: '8px',
                                        padding: '9px 20px',
                                        backgroundColor: activeConfig?.color,
                                        color: 'white', border: 'none', borderRadius: '6px',
                                        cursor: 'pointer', fontSize: '13px', fontWeight: 600,
                                        boxShadow: `0 2px 8px ${activeConfig?.color}40`,
                                        transition: 'all 0.2s',
                                    }}
                                    onMouseOver={e => { e.currentTarget.style.opacity = '0.9'; e.currentTarget.style.transform = 'translateY(-1px)'; }}
                                    onMouseOut={e => { e.currentTarget.style.opacity = '1'; e.currentTarget.style.transform = 'translateY(0)'; }}
                                >
                                    <Play size={13} fill="white" /> Generate Report
                                </button>
                            </div>
                        )}

                        {/* Loading skeleton */}
                        {loading[activeTab] && !responses[activeTab] && (
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '10px', padding: '40px', color: '#64748b' }}>
                                <Loader size={20} className="spin" color={activeConfig?.color} />
                                <span style={{ fontSize: '13px' }}>{activeConfig?.loadingMsg}</span>
                            </div>
                        )}

                        {/* Report content */}
                        {responses[activeTab] && <InlineReport />}

                        {/* Error state */}
                        {!loading[activeTab] && !responses[activeTab] && fetched[activeTab] && (
                            <div style={{ color: '#ef4444', textAlign: 'center', padding: '30px' }}>
                                <AlertTriangle size={20} style={{ marginBottom: '8px' }} />
                                <div>No response received.</div>
                                <button onClick={() => fetchExpertise(activeTab)} style={{ marginTop: '10px', padding: '6px 16px', borderRadius: '6px', border: '1px solid #ef4444', background: 'transparent', color: '#ef4444', cursor: 'pointer', fontSize: '13px' }}>
                                    Retry
                                </button>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}