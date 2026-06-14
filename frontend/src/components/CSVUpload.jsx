import { useState, useRef, useCallback } from "react";
import api from "../lib/api";

const SUPPORTED_BANKS = [
  { id: "hdfc", label: "HDFC Bank", hint: "Net Banking → Accounts → Download Statement → CSV" },
  { id: "icici", label: "ICICI Bank", hint: "iMobile / Net Banking → Statement → Download as CSV" },
  { id: "sbi", label: "SBI", hint: "YONO / Net Banking → Account Statement → Excel/CSV" },
  { id: "axis", label: "Axis Bank", hint: "Net Banking → Statements → Download CSV" },
  { id: "kotak", label: "Kotak Mahindra", hint: "Net Banking → Account Statement → CSV Export" },
];

export default function CSVUpload({ onSuccess, onClose }) {
  const [dragActive, setDragActive] = useState(false);
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [selectedBank, setSelectedBank] = useState(null);
  const inputRef = useRef(null);

  const handleFile = useCallback((f) => {
    setError(null);
    setResult(null);
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".csv")) {
      setError("Only .csv files are accepted. Export your bank statement as CSV first.");
      return;
    }
    if (f.size > 10 * 1024 * 1024) {
      setError("File is too large (max 10 MB). Try a shorter date range.");
      return;
    }
    setFile(f);
  }, []);

  const onDrop = useCallback((e) => {
    e.preventDefault();
    setDragActive(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleFile(f);
  }, [handleFile]);

  const onDragOver = (e) => { e.preventDefault(); setDragActive(true); };
  const onDragLeave = () => setDragActive(false);

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const { data } = await api.post("/api/csv/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(data);
      onSuccess?.();
    } catch (err) {
      const msg =
        err?.response?.data?.detail ||
        "Upload failed. Check your file is a valid bank statement CSV.";
      setError(msg);
    } finally {
      setUploading(false);
    }
  };

  const reset = () => {
    setFile(null);
    setError(null);
    setResult(null);
    setSelectedBank(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg">

        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-6 pb-4 border-b border-sage-100">
          <div>
            <h2 className="font-display text-lg font-semibold text-ink-900">Upload Bank Statement</h2>
            <p className="text-sm text-ink-500 mt-0.5">CSV export from your bank's net banking portal</p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-ink-400 hover:text-ink-700 hover:bg-sage-50 transition-colors"
            aria-label="Close"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="px-6 py-5 space-y-5">

          {/* Success state */}
          {result ? (
            <div className="space-y-4">
              <div className="bg-safe/10 border border-safe/30 rounded-xl p-4">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-8 h-8 rounded-full bg-safe/20 flex items-center justify-center">
                    <svg className="w-4 h-4 text-safe" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <p className="font-medium text-ink-900">Statement imported</p>
                </div>
                <div className="grid grid-cols-3 gap-3 text-center">
                  {[
                    { label: "Bank detected", value: result.bank?.toUpperCase() },
                    { label: "Transactions added", value: result.inserted },
                    { label: "Already existed", value: result.skipped_duplicate },
                  ].map(({ label, value }) => (
                    <div key={label} className="bg-white rounded-lg p-2.5 border border-sage-100">
                      <p className="font-mono text-lg font-semibold text-ink-900">{value}</p>
                      <p className="text-xs text-ink-400 mt-0.5">{label}</p>
                    </div>
                  ))}
                </div>
              </div>
              <div className="flex gap-3">
                <button onClick={reset} className="btn-ghost flex-1 text-sm py-2">
                  Upload another
                </button>
                <button onClick={onClose} className="btn-primary flex-1 text-sm py-2">
                  View dashboard
                </button>
              </div>
            </div>
          ) : (
            <>
              {/* Bank selector */}
              <div>
                <p className="label mb-2">Select your bank</p>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {SUPPORTED_BANKS.map((bank) => (
                    <button
                      key={bank.id}
                      onClick={() => setSelectedBank(selectedBank === bank.id ? null : bank.id)}
                      className={`
                        text-left px-3 py-2.5 rounded-xl border text-sm font-medium transition-all
                        ${selectedBank === bank.id
                          ? "border-forest-600 bg-forest-50 text-forest-700"
                          : "border-sage-200 text-ink-700 hover:border-forest-400 hover:bg-sage-50"
                        }
                      `}
                    >
                      {bank.label}
                    </button>
                  ))}
                </div>
                {selectedBank && (
                  <p className="mt-2 text-xs text-ink-400 flex items-start gap-1.5">
                    <svg className="w-3.5 h-3.5 mt-0.5 shrink-0 text-forest-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    {SUPPORTED_BANKS.find(b => b.id === selectedBank)?.hint}
                  </p>
                )}
              </div>

              {/* Drop zone */}
              <div
                onDrop={onDrop}
                onDragOver={onDragOver}
                onDragLeave={onDragLeave}
                onClick={() => !file && inputRef.current?.click()}
                className={`
                  relative border-2 border-dashed rounded-xl p-6 text-center transition-all cursor-pointer
                  ${dragActive ? "border-forest-500 bg-forest-50" : ""}
                  ${file ? "border-forest-400 bg-forest-50/50 cursor-default" : "border-sage-300 hover:border-forest-400 hover:bg-sage-50"}
                `}
              >
                <input
                  ref={inputRef}
                  type="file"
                  accept=".csv,text/csv"
                  className="hidden"
                  onChange={(e) => handleFile(e.target.files?.[0])}
                />

                {file ? (
                  <div className="flex items-center justify-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-forest-100 flex items-center justify-center shrink-0">
                      <svg className="w-5 h-5 text-forest-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                    </div>
                    <div className="text-left min-w-0">
                      <p className="text-sm font-medium text-ink-900 truncate">{file.name}</p>
                      <p className="text-xs text-ink-400">{(file.size / 1024).toFixed(1)} KB</p>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); reset(); }}
                      className="ml-auto p-1 rounded text-ink-400 hover:text-danger transition-colors shrink-0"
                      aria-label="Remove file"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                ) : (
                  <>
                    <svg className="mx-auto w-8 h-8 text-ink-300 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                    <p className="text-sm text-ink-600">
                      Drop your CSV here, or <span className="text-forest-600 font-medium">browse</span>
                    </p>
                    <p className="text-xs text-ink-400 mt-1">Bank format is detected automatically</p>
                  </>
                )}
              </div>

              {/* Error */}
              {error && (
                <div className="flex items-start gap-2 bg-danger/5 border border-danger/20 rounded-xl px-4 py-3">
                  <svg className="w-4 h-4 text-danger mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <p className="text-sm text-danger">{error}</p>
                </div>
              )}

              {/* Privacy note */}
              <p className="text-xs text-ink-400 text-center leading-relaxed">
                Your file is processed on our servers and never shared.
                Only debit transactions are imported.
              </p>

              {/* Upload button */}
              <button
                onClick={handleUpload}
                disabled={!file || uploading}
                className="btn-primary w-full py-3 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {uploading ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Processing...
                  </span>
                ) : (
                  "Import transactions"
                )}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}