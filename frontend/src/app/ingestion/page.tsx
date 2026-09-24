"use client";

import { useCallback, useEffect, useState, ReactNode } from "react";
import { UploadCloud, FileText, Loader2, CheckCircle2 } from "lucide-react";
import { api, ExtractedInvoice, SampleInvoice, API_BASE, formatINR } from "@/lib/api";

export default function IngestionPage() {
  const [samples, setSamples] = useState<SampleInvoice[]>([]);
  const [selected, setSelected] = useState<SampleInvoice | null>(null);
  const [extracted, setExtracted] = useState<ExtractedInvoice | null>(null);
  const [loading, setLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadedUrl, setUploadedUrl] = useState<string | null>(null);

  useEffect(() => {
    api
      .sampleInvoices()
      .then(setSamples)
      .catch(() => setSamples([]));
  }, []);

  const runExtraction = useCallback((sample: SampleInvoice) => {
    setSelected(sample);
    setUploadedUrl(null);
    setLoading(true);
    setError(null);
    api
      .extractSample(sample.filename)
      .then(setExtracted)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const handleFile = useCallback((file: File) => {
    setSelected(null);
    setUploadedUrl(URL.createObjectURL(file));
    setLoading(true);
    setError(null);
    api
      .extractUpload(file)
      .then(setExtracted)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-display font-semibold text-[22px] text-paper">Ingestion &amp; extraction</h2>
        <p className="text-[13px] text-paper-dim mt-1">
          Feed it a vendor invoice — or grab one of the 5 sample ones — and watch it get pulled apart into fields we can actually use.
        </p>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const file = e.dataTransfer.files?.[0];
          if (file) handleFile(file);
        }}
        className={`rounded-xl border-2 border-dashed p-8 text-center transition-colors ${
          dragOver ? "border-gold bg-gold/5" : "border-ink-line bg-ink-raised/40"
        }`}
      >
        <UploadCloud size={26} className="mx-auto text-paper-dim mb-3" />
        <p className="text-[13.5px] text-paper">
          Drop an invoice here — a photo of one works too
        </p>
        <label className="inline-block mt-3 cursor-pointer text-[12.5px] text-gold hover:underline">
          or pick a file
          <input
            type="file"
            accept=".pdf,.png,.jpg,.jpeg"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleFile(file);
            }}
          />
        </label>
      </div>

      <div>
        <p className="text-[12px] text-paper-dim mb-2.5">Or try a bundled sample invoice:</p>
        <div className="flex flex-wrap gap-2">
          {samples.map((s) => (
            <button
              key={s.filename}
              onClick={() => runExtraction(s)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-[12px] transition-colors ${
                selected?.filename === s.filename
                  ? "border-gold/50 bg-gold/10 text-gold"
                  : "border-ink-line bg-ink-raised text-paper-dim hover:text-paper hover:border-ink-line/80"
              }`}
            >
              <FileText size={13} />
              {s.filename.replace(".pdf", "")}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-bad/30 bg-bad/5 p-4 text-[12.5px] text-bad">
          Extraction failed: {error}
        </div>
      )}

      {(selected || uploadedUrl) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="rounded-xl border border-ink-line bg-ink-raised overflow-hidden">
            <div className="px-4 py-3 border-b border-ink-line flex items-center gap-2">
              <FileText size={14} className="text-paper-dim" />
              <span className="text-[12.5px] text-paper-dim">Original document</span>
            </div>
            <div className="h-[560px] bg-[#0d1220]">
              <object
                data={selected ? `${API_BASE}${selected.url}` : uploadedUrl!}
                type="application/pdf"
                className="w-full h-full"
              >
                <div className="p-6 text-[12.5px] text-paper-dim">
                  Preview unavailable in this browser — the file was still sent for extraction.
                </div>
              </object>
            </div>
          </div>

          <div className="rounded-xl border border-ink-line bg-ink-raised overflow-hidden">
            <div className="px-4 py-3 border-b border-ink-line flex items-center gap-2 justify-between">
              <span className="text-[12.5px] text-paper-dim">Extracted structured JSON</span>
              {!loading && extracted && (
                <span className="flex items-center gap-1 text-[11px] text-good">
                  <CheckCircle2 size={12} />
                  {(extracted.extraction_confidence * 100).toFixed(0)}% confidence
                </span>
              )}
            </div>
            <div className="h-[560px] overflow-y-auto p-4">
              {loading ? (
                <div className="h-full flex items-center justify-center text-paper-dim gap-2 text-[13px]">
                  <Loader2 size={16} className="animate-spin" />
                  Running LLM/OCR extraction…
                </div>
              ) : extracted ? (
                <ExtractedFieldsView data={extracted} />
              ) : null}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex justify-between gap-4 py-2 border-b border-ink-line/60 last:border-0">
      <span className="text-[12px] text-paper-dim">{label}</span>
      <span className="text-[12.5px] font-ledger text-paper text-right">{value || "—"}</span>
    </div>
  );
}

function ExtractedFieldsView({ data }: { data: ExtractedInvoice }) {
  return (
    <div className="space-y-5">
      <div>
        <SectionLabel>Who&apos;s billing us</SectionLabel>
        <Field label="Vendor name" value={data.vendor_name} />
        <Field label="GSTIN" value={data.gstin} />
        <Field label="Invoice number" value={data.invoice_number} />
        <Field label="Invoice date" value={data.invoice_date} />
        <Field label="Due date" value={data.due_date} />
        <Field label="Bill to" value={data.bill_to} />
      </div>

      <div>
        <SectionLabel>Where the money goes</SectionLabel>
        <Field label="Bank" value={data.bank_name} />
        <Field label="Account number" value={data.account_number} />
        <Field label="IFSC" value={data.ifsc} />
      </div>

      <div>
        <SectionLabel>Line items</SectionLabel>
        {data.line_items.length === 0 ? (
          <p className="text-[12px] text-paper-dim">Nothing parsed here — the layout may not match what we expect.</p>
        ) : (
          <div className="space-y-1.5">
            {data.line_items.map((item, i) => (
              <div key={i} className="flex justify-between text-[12px]">
                <span className="text-paper-dim truncate max-w-[60%]">{item.description}</span>
                <span className="font-ledger text-paper">{formatINR(item.amount)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div>
        <SectionLabel>Totals</SectionLabel>
        <Field label="Subtotal" value={formatINR(data.subtotal)} />
        <Field label="GST" value={formatINR(data.gst_amount)} />
        {data.tds_amount != null && <Field label="TDS deducted" value={formatINR(data.tds_amount)} />}
        <Field label="Total payable" value={formatINR(data.total_payable)} />
      </div>
    </div>
  );
}

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <h4 className="flex items-center gap-2 text-[12px] text-paper-dim mb-1.5">
      <span className="w-2 h-px bg-gold/60" />
      {children}
    </h4>
  );
}
