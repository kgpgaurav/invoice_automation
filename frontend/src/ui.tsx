import type { ReactNode } from 'react';
export type Navigate = (query: string) => void;
const labels: Record<string, string> = {
  WAITING_REVIEW: 'Needs review',
  NEEDS_REVIEW: 'Needs review',
  NOT_LOADED: 'Loading',
  INTERRUPTED: 'Stopped',
  RUNNING: 'Processing',
  QUEUED: 'Queued',
  COMPLETED: 'Completed',
  FAILED: 'Processing failed',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
  po_reference: 'PO Reference',
  vendor_tax_id: 'Vendor Tax ID',
  invoice_number: 'Invoice Number',
  invoice_date: 'Invoice Date',
  tax_total: 'Tax Total',
  subtotal_net: 'Subtotal',
  total_gross: 'Invoice Total',
  sku: 'SKU',
  po_line_no: 'PO Line',
  tax_rate: 'Tax Rate (%)',
  gstin: 'GSTIN',
};
export const pretty = (value: string) =>
  labels[value] ??
  value
    .toLowerCase()
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
export const reasonLabel = (code?: string | null) =>
  (
    ({
      PO_CAP_EXCEEDED: 'Invoice exceeds the remaining PO balance',
      PO_AMBIGUOUS: 'Choose a supporting purchase order',
      PO_MISSING: 'Supporting PO information needed',
      BANK_MISMATCH: 'Independently verify changed bank details',
      DUPLICATE_APPROVED: 'Invoice already approved',
      DUPLICATE_CONFLICT: 'Conflicting invoice identity',
      VALIDATED: 'Financial checks passed',
      ARITHMETIC_MISMATCH: 'Invoice amounts do not reconcile',
      TAX_UNCLEAR: 'Tax information needs review',
      UNVERIFIED_TOTAL: 'Source evidence needs review',
      CRITICAL_FIELD_MISSING: 'Required information is missing',
      VENDOR_UNKNOWN: 'Supplier identity needs verification',
      VENDOR_INACTIVE: 'Supplier is inactive',
      VENDOR_ID_MISMATCH: 'Supplier identity conflicts',
      PO_VENDOR_MISMATCH: 'PO belongs to another supplier',
      QTY_EXCEEDED: 'Quantity exceeds the PO allowance',
      PRICE_VARIANCE: 'Unit price differs from the PO',
      LINE_AMBIGUOUS: 'Invoice line needs a clear PO match',
      PO_CLOSED: 'PO is closed or expired',
      FUTURE_DATE: 'Confirm the future invoice date',
      DATE_BEFORE_PO: 'Invoice date precedes the PO',
      REQUEST_INFO: 'Corrected source information requested',
      REVIEWER_REJECTED: 'Rejected by an authorized reviewer',
      ALLOCATION_CONFLICT: 'PO allocations need reconciliation',
    }) as Record<string, string>
  )[code ?? ''] ?? 'Open the invoice for recorded details';
export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, ReactNode> = {
    grid: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </>
    ),
    upload: <path d="M12 16V3m-5 5 5-5 5 5M4 16v4h16v-4" />,
    file: <path d="M14 2H5v20h14V7l-5-5Zm0 0v6h5M8 12h8m-8 4h6" />,
    arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
    check: <path d="m5 12 4 4L19 6" />,
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    shield: (
      <>
        <path d="m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6l8-4Z" />
        <path d="m8 12 3 3 5-6" />
      </>
    ),
    chevron: <path d="m9 5 7 7-7 7" />,
    key: (
      <>
        <circle cx="8" cy="9" r="5" />
        <path d="m12 13 8 8m-5-5 3-3m-6 0 3-3" />
      </>
    ),
    alert: (
      <>
        <path d="m12 3 10 18H2L12 3Z" />
        <path d="M12 9v5m0 3v1" />
      </>
    ),
    close: <path d="m6 6 12 12M6 18 18 6" />,
    refresh: (
      <>
        <path d="M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-1l2 6M4 12l2 6a7 7 0 0 0 12-1" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] ?? paths.file}
    </svg>
  );
}
export function Badge({ value }: { value: string }) {
  return <span className={`badge ${value.toLowerCase()}`}>{pretty(value)}</span>;
}
export function Mode({ value }: { value: string }) {
  return value === 'MOCK_OPENAI' || value === 'DEMO_REPLAY' ? (
    <span className="mode-warning">
      {value === 'MOCK_OPENAI' ? 'MOCK EXTRACTION' : 'DEMO REPLAY'}
    </span>
  ) : null;
}
export function Link({
  to,
  navigate,
  children,
  className = '',
}: {
  to: string;
  navigate: Navigate;
  children: ReactNode;
  className?: string;
}) {
  return (
    <a
      href={to}
      className={className}
      aria-current={className === 'active' ? 'page' : undefined}
      onClick={(e) => {
        if (!e.ctrlKey && !e.metaKey && !e.shiftKey && e.button === 0) {
          e.preventDefault();
          navigate(to);
        }
      }}
    >
      {children}
    </a>
  );
}
