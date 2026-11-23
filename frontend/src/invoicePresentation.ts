import type { Run, SubmitterRun } from './api';
import { money } from './api';
import type { components } from './api.generated';

export type InvoiceRecord = Run | SubmitterRun;
export type Field = components['schemas']['ExtractedField'];
export type InvoiceTab = 'data' | 'comparison' | 'checks' | 'review';
export const fieldValue = (run: InvoiceRecord, name: string) =>
  run.fields.find((field) => field.field === name)?.value ?? null;
export const unresolved = (field: Field) =>
  field.value == null || field.value.trim() === '' || field.value === 'UNKNOWN';
export const financialIssue = (status: string) =>
  status === 'failed' || status === 'requires_review';
export const fieldId = (name: string) => 'invoice-field-' + name.replaceAll('.', '-');

export function displayField(field: Field | undefined, currency: string | null) {
  if (!field || field.value == null || field.value === '') return 'Missing';
  if (
    /^(subtotal_net|tax_total|total_gross|unit_price|net_amount|tax_amount|gross_amount|discount_amount|shipping_amount|other_charges|rounding_adjustment|cgst_amount|sgst_amount|igst_amount|cess_amount)$/.test(
      field.field.split('.').at(-1) ?? '',
    )
  )
    return money(field.value, currency ?? '');
  return field.value;
}

export function fieldStatus(field: Field) {
  if (field.extraction_state === 'AMBIGUOUS') return { label: 'Ambiguous', tone: 'unverified' };
  if (field.verification === 'missing' || field.value == null)
    return { label: 'Missing', tone: field.required_for_approval ? 'missing' : 'optional' };
  if (field.origin === 'derived')
    return {
      label: field.verification === 'verified' ? 'Calculated' : 'Calculated candidate',
      tone: field.verification === 'verified' ? 'calculated' : 'unverified',
    };
  return field.verification === 'verified'
    ? { label: 'Verified', tone: 'verified' }
    : { label: 'Unverified', tone: 'unverified' };
}

export function requirement(field: Field) {
  return field.field === 'vendor_tax_id'
    ? 'Conditional: optional when absent; a printed supplier tax ID must match the vendor.'
    : field.required_for_approval
      ? 'Required by the current approval checks.'
      : 'Optional when absent; supplied values still need supporting evidence.';
}

export function sourceExplanation(field: Field) {
  if (field.financial_validation_errors?.length)
    return `${field.source_reason ?? 'Source support is unresolved.'} Financial format checks failed: ${field.financial_validation_errors.join(', ')}.`;
  if (field.source_reason) return field.source_reason;
  if (field.value == null) return requirement(field);
  if (field.origin === 'derived')
    return field.verification === 'verified'
      ? 'Calculated locally from supported PDF values. Financial validation is separate.'
      : 'Calculated candidate; its source support is unresolved.';
  return field.verification === 'verified'
    ? 'Supported by local PDF evidence. This does not establish agreement with the PO.'
    : 'A saved extraction value without verified local source support.';
}

export function lineGroups(fields: Field[]) {
  const lines = new Map<string, { key: string; label: string; fields: Field[] }>();
  for (const field of fields) {
    const parts = field.field.split('.');
    if (parts.length !== 3 || !['lines', 'unidentified_lines'].includes(parts[0])) continue;
    const key = parts.slice(0, 2).join('.');
    if (!lines.has(key))
      lines.set(key, {
        key,
        label:
          parts[0] === 'unidentified_lines' ? `Unnumbered item ${parts[1]}` : `Item ${parts[1]}`,
        fields: [],
      });
    lines.get(key)!.fields.push(field);
  }
  return [...lines.values()];
}

// Read-only display ratio, never a tolerance or authorization result. Keep decimal
// operands exact with BigInt; absent/invalid/zero bases have no relative figure.
export function relativeDifference(difference: string, reference: string | null) {
  const parse = (value: string) => {
    if (!/^-?\d{1,24}(?:\.\d{1,12})?$/.test(value)) return null;
    const decimals = value.split('.')[1]?.length ?? 0;
    return { value: BigInt(value.replace('.', '')), scale: 10n ** BigInt(decimals) };
  };
  const change = parse(difference),
    base = reference == null ? null : parse(reference);
  if (!change || !base || base.value === 0n) return null;
  const absolute = (value: bigint) => (value < 0n ? -value : value);
  const numerator = absolute(change.value) * base.scale * 10000n;
  const denominator = absolute(base.value) * change.scale;
  const rounded = (numerator + denominator / 2n) / denominator;
  return `${change.value < 0n ? '−' : ''}${rounded / 100n}.${(rounded % 100n).toString().padStart(2, '0')}%`;
}
