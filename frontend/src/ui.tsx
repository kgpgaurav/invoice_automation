import type { ReactNode } from 'react';
import {
  SquaresFourIcon,
  UploadSimpleIcon,
  FileTextIcon,
  ArrowRightIcon,
  CheckIcon,
  ClockIcon,
  ShieldCheckIcon,
  CaretRightIcon,
  KeyIcon,
  WarningIcon,
  XIcon,
  ArrowsClockwiseIcon,
  ListBulletsIcon,
  ShoppingCartIcon,
  ChartBarIcon,
  UserCircleIcon,
  CaretDownIcon,
  InvoiceIcon,
  ArrowsOutIcon,
  ArrowLeftIcon,
  InfoIcon,
  type Icon as PhosphorIcon,
} from '@phosphor-icons/react';
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
export const fieldLabel = (path: string) => {
  const parts = path.split('.');
  const key = parts.at(-1) ?? path;
  const names: Record<string, string> = {
    vendor_name: 'Supplier name',
    vendor_tax_id: 'Supplier GSTIN / tax ID',
    invoice_number: 'Invoice number',
    invoice_date: 'Invoice date',
    po_reference: 'Purchase order reference',
    currency: 'Currency',
    subtotal_net: 'Subtotal before tax',
    tax_total: 'Total tax',
    total_gross: 'Invoice total',
    tax_mode: 'Tax treatment',
    description: 'Item description',
    sku: 'SKU',
    po_line_no: 'PO line reference',
    quantity: 'Quantity',
    unit_price: 'Unit price',
    price_basis: 'Price includes / excludes tax',
    tax_rate: 'Combined tax rate (%)',
    net_amount: 'Line amount before tax',
    tax_amount: 'Line tax amount',
    gross_amount: 'Line amount including tax',
  };
  return (parts.length === 3 ? `Line ${parts[1]} · ` : '') + (names[key] ?? pretty(key));
};
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
      VENDOR_BLACKLISTED: 'Supplier is blacklisted',
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
const icons: Record<string, PhosphorIcon> = {
  grid: SquaresFourIcon,
  upload: UploadSimpleIcon,
  file: FileTextIcon,
  arrow: ArrowRightIcon,
  check: CheckIcon,
  clock: ClockIcon,
  shield: ShieldCheckIcon,
  chevron: CaretRightIcon,
  key: KeyIcon,
  alert: WarningIcon,
  close: XIcon,
  refresh: ArrowsClockwiseIcon,
  list: ListBulletsIcon,
  cart: ShoppingCartIcon,
  chart: ChartBarIcon,
  user: UserCircleIcon,
  down: CaretDownIcon,
  invoice: InvoiceIcon,
  expand: ArrowsOutIcon,
  back: ArrowLeftIcon,
  info: InfoIcon,
};
export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const Component = icons[name] ?? FileTextIcon;
  return <Component size={size} weight="regular" aria-hidden="true" />;
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
export function vendorStatusLabel(status: string) {
  return (
    (
      { ACTIVE: 'Approved', INACTIVE: 'Inactive', BLACKLISTED: 'Blacklisted' } as Record<
        string,
        string
      >
    )[status] ?? status
  );
}
