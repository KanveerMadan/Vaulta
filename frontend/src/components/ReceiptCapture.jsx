import { useRef, useState } from "react";
import { browserOcr } from "../import/ocr";
import { ocrPagesResult } from "../import/pdfExtract";
import { extractReceipt } from "../import/receipt";
import ManualEntryModal from "./ManualEntryModal";

/**
 * Photo of a bill → OCR on this device → prefilled entry to confirm.
 * The image is read in memory and never uploaded.
 */
export default function ReceiptCapture({ onSaved }) {
  const input = useRef(null);
  const [state, setState] = useState("idle"); // idle | reading | error
  const [entry, setEntry] = useState(null);

  const read = async (file) => {
    if (!file) return;
    setState("reading");
    let ocr;
    try {
      ocr = await browserOcr();
      const { lineTexts } = ocrPagesResult([await ocr.recognize(file)]);
      const r = extractReceipt(lineTexts);
      setEntry({
        amount: r.amount || "", merchant: r.merchant || "", category: r.category || "",
        payment_method: r.payment_method || "cash",
        ...(r.date && { date: r.date }),
      });
      setState("idle");
    } catch {
      setState("error");
    } finally {
      await ocr?.terminate();
      if (input.current) input.current.value = "";
    }
  };

  return (
    <>
      <button type="button" onClick={() => input.current?.click()} disabled={state === "reading"}
        className="btn-ghost text-sm px-3 whitespace-nowrap" title="Photo of a bill or receipt. It stays on your device.">
        {state === "reading" ? "Reading…" : "Scan bill"}
      </button>
      <input ref={input} type="file" accept="image/*" capture="environment" className="hidden"
        onChange={(e) => read(e.target.files?.[0])} aria-label="Photo of a bill" />
      {state === "error" && <p className="text-xs text-danger">Couldn't read that photo. Try a sharper, well-lit one.</p>}
      {entry && (
        <ManualEntryModal initial={entry} onClose={() => setEntry(null)}
          onSaved={() => { setEntry(null); onSaved?.(); }} />
      )}
    </>
  );
}
