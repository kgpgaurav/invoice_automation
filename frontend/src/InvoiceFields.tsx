import { Fragment, useEffect, useState } from 'react';
import { fieldLabel, Icon } from './ui';
import {
  displayField,
  fieldId,
  fieldStatus,
  lineGroups,
  requirement,
  sourceExplanation,
  type Field,
  type InvoiceRecord,
} from './invoicePresentation';

export function SourceStatus({ field }: { field: Field }) {
  const status = fieldStatus(field);
  return (
    <span className={'source-status ' + status.tone} title={sourceExplanation(field)}>
      <Icon
        name={status.tone === 'verified' ? 'check' : status.tone === 'calculated' ? 'file' : 'info'}
        size={12}
      />
      {status.label}
    </span>
  );
}

function FieldGrid({
  fields,
  currency,
  showPage,
}: {
  fields: Field[];
  currency: string | null;
  showPage: (page: number, field: string) => void;
}) {
  return (
    <dl className="invoice-field-grid">
      {fields.map((field) => (
        <div key={field.field} id={fieldId(field.field)} className="invoice-field" tabIndex={-1}>
          <dt>
            {fieldLabel(field.field).replace(/^Line \S+ · /, '')}
            {!field.required_for_approval && (
              <small>{field.field === 'vendor_tax_id' ? 'Conditional' : 'Optional'}</small>
            )}
          </dt>
          <dd>
            <strong className={field.value == null ? 'empty-value' : ''}>
              {displayField(field, currency)}
            </strong>
            <details className="field-evidence">
              <summary aria-label={'Evidence for ' + fieldLabel(field.field)}>
                <SourceStatus field={field} />
              </summary>
              <div className="field-evidence-body">
                <p>{sourceExplanation(field)}</p>
                <p>{requirement(field)}</p>
                {field.calculation && <p className="calculation">{field.calculation}</p>}
                {field.original_value != null && field.original_value !== field.value && (
                  <p>Original extraction: {field.original_value}</p>
                )}
                {field.pages.map((page) => (
                  <button
                    className="text-link"
                    key={page}
                    onClick={() => showPage(page, field.field)}
                  >
                    View {fieldLabel(field.field)} source, page {page}
                  </button>
                ))}
                {!field.pages.length && <small>No verified page reference is available.</small>}
              </div>
            </details>
          </dd>
        </div>
      ))}
    </dl>
  );
}

export default function InvoiceFields({
  run,
  showPage,
  focusField,
}: {
  run: InvoiceRecord;
  showPage: (page: number, field: string) => void;
  focusField?: { field: string; revision: number };
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const lines = lineGroups(run.fields);
  useEffect(() => {
    if (!focusField) return;
    const key = focusField.field.split('.').slice(0, 2).join('.');
    if (focusField.field.includes('.')) setExpanded((old) => new Set([...old, key]));
    const timer = setTimeout(() => {
      const target = document.getElementById(fieldId(focusField.field));
      target?.scrollIntoView({ block: 'center', behavior: 'instant' });
      target?.focus({ preventScroll: true });
    }, 0);
    return () => clearTimeout(timer);
  }, [focusField]);
  const groups = [
    {
      title: 'Invoice details',
      keys: [
        'invoice_number',
        'invoice_date',
        'due_date',
        'currency',
        'po_reference',
        'payment_terms',
      ],
    },
    { title: 'Supplier details', keys: ['vendor_name', 'vendor_tax_id', 'vendor_address'] },
    {
      title: 'Buyer and delivery',
      keys: ['buyer_name', 'buyer_tax_id', 'buyer_address', 'ship_to_address'],
    },
    { title: 'Financial summary', keys: ['subtotal_net', 'tax_total', 'total_gross', 'tax_mode'] },
    {
      title: 'Tax breakdown',
      keys: [
        'cgst_rate',
        'cgst_amount',
        'sgst_rate',
        'sgst_amount',
        'igst_rate',
        'igst_amount',
        'cess_rate',
        'cess_amount',
      ],
    },
    {
      title: 'Discounts and charges',
      keys: [
        'discount_amount',
        'discount_rate',
        'shipping_amount',
        'other_charges',
        'rounding_adjustment',
      ],
    },
  ];
  if (!run.fields.length)
    return (
      <div className="invoice-data-empty" role="status">
        <Icon name="file" size={24} />
        <h2>Invoice information is not available yet</h2>
        <p>Saved extracted values will appear here. Missing values will remain missing.</p>
      </div>
    );
  return (
    <section className="invoice-data" aria-label="Extracted invoice information">
      <div className="invoice-field-groups">
        {groups
          .filter((group) =>
            group.keys.some((key) => run.fields.some((field) => field.field === key)),
          )
          .map((group) => (
            <section
              key={group.title}
              className={
                'invoice-field-group ' +
                (group.title === 'Financial summary' ? 'financial-fields' : '')
              }
            >
              <h2>{group.title}</h2>
              <FieldGrid
                fields={group.keys.flatMap((key) =>
                  run.fields.filter((field) => field.field === key),
                )}
                currency={run.invoice_currency}
                showPage={showPage}
              />
            </section>
          ))}
      </div>
      <section className="invoice-lines" aria-label="Invoice line items">
        <div className="invoice-section-heading">
          <h2>
            Line items <span className="item-count">{lines.length}</span>
          </h2>
          <small>Open an item for source details</small>
        </div>
        {!lines.length ? (
          <p className="empty-inline">No line items are available in the saved extraction.</p>
        ) : (
          <div
            className="invoice-table-scroll"
            role="region"
            aria-label="Scrollable invoice line items"
            tabIndex={0}
          >
            <table className="invoice-line-table">
              <caption className="sr-only">
                Invoice line values and local source verification
              </caption>
              <thead>
                <tr>
                  <th scope="col">Item / code</th>
                  <th scope="col">Qty</th>
                  <th scope="col">Unit price</th>
                  <th scope="col">Tax %</th>
                  <th scope="col">Tax amount</th>
                  <th scope="col">Line total</th>
                  <th scope="col">Source</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((line) => {
                  const find = (key: string) =>
                    line.fields.find((f) => f.field.endsWith('.' + key));
                  const required = line.fields.filter((field) => field.required_for_approval);
                  const status = required.some((f) => f.value == null)
                    ? 'Missing'
                    : required.length && required.every((f) => f.verification === 'verified')
                      ? 'Verified'
                      : 'Unverified';
                  const open = expanded.has(line.key);
                  return (
                    <Fragment key={line.key}>
                      <tr id={fieldId(line.key)}>
                        <th scope="row">
                          <button
                            className="line-expand"
                            aria-expanded={open}
                            aria-controls={fieldId(line.key) + '-detail'}
                            onClick={() =>
                              setExpanded((old) => {
                                const next = new Set(old);
                                if (next.has(line.key)) next.delete(line.key);
                                else next.add(line.key);
                                return next;
                              })
                            }
                          >
                            <Icon name={open ? 'down' : 'chevron'} size={14} />
                            <span>
                              <strong>{find('description')?.value ?? 'Description missing'}</strong>
                              <small>
                                {line.label}
                                {find('sku')?.value ? ' · ' + find('sku')!.value : ''}
                              </small>
                            </span>
                          </button>
                        </th>
                        {['quantity', 'unit_price', 'tax_rate', 'tax_amount', 'gross_amount'].map(
                          (key) => (
                            <td
                              key={key}
                              className={
                                'amount ' + (find(key)?.value == null ? 'empty-value' : '')
                              }
                            >
                              {displayField(find(key), run.invoice_currency)}
                              {key === 'unit_price' && find('price_basis')?.value && (
                                <small>
                                  {find('price_basis')!.value === 'NET'
                                    ? 'Before tax'
                                    : find('price_basis')!.value === 'GROSS'
                                      ? 'Including tax'
                                      : 'Basis unknown'}
                                </small>
                              )}
                            </td>
                          ),
                        )}
                        <td>
                          <span className={'source-status ' + status.toLowerCase()}>{status}</span>
                        </td>
                      </tr>
                      {open && (
                        <tr id={fieldId(line.key) + '-detail'} className="line-evidence-row">
                          <td colSpan={7}>
                            <FieldGrid
                              fields={line.fields}
                              currency={run.invoice_currency}
                              showPage={showPage}
                            />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <p className="invoice-source-note">
        Verified means supported by the PDF. PO agreement and financial authorization are checked
        separately.
      </p>
    </section>
  );
}
