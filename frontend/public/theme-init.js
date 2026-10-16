// Apply the saved theme before first paint (no flash). Values: "light" | "dark"; absent = follow the system.
// A file rather than an inline script so the Content-Security-Policy needs no 'unsafe-inline' (vercel.json).
try { var t = localStorage.getItem('vaulta-theme'); if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t } catch { /* storage blocked: follow the system */ }
