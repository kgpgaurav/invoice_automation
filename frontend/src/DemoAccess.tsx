import { useEffect, useState } from 'react';
import type { components } from './api.generated';

type Credential = components['schemas']['DemoCredential'];

export default function DemoAccess({
  onUse,
  disabled,
}: {
  onUse: (token: string) => void;
  disabled: boolean;
}) {
  const [roles, setRoles] = useState<Credential[]>([]);
  const [message, setMessage] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/v1/demo-access', { cache: 'no-store', signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error();
        return response.json();
      })
      .then((data) => {
        if (
          !Array.isArray(data.roles) ||
          data.roles.length !== 2 ||
          !['submitter', 'reviewer'].every(
            (role) =>
              data.roles.filter(
                (item: Credential) =>
                  item?.role === role && typeof item.token === 'string' && item.token.length >= 24,
              ).length === 1,
          )
        )
          return;
        if (!controller.signal.aborted) setRoles(data.roles);
      })
      .catch(() => {});
    return () => controller.abort();
  }, []);

  async function copy(credential: Credential) {
    try {
      await navigator.clipboard.writeText(credential.token);
      setMessage(`${credential.role === 'submitter' ? 'Submitter' : 'Reviewer'} token copied.`);
    } catch {
      setMessage('Copy is unavailable. Select and copy the token above.');
    }
  }

  if (!roles.length)
    return (
      <details className="entry-help">
        <summary>Need an access token?</summary>
        <p>
          Ask the person who shared this workspace. Submitter and financial reviewer tokens have
          different permissions.
        </p>
      </details>
    );

  return (
    <details className="entry-help demo-access">
      <summary>Get demo access</summary>
      <p>
        Choose a role to explore this assignment. These demo identities and their activity are
        shared with other visitors. Use synthetic invoices only.
      </p>
      {roles.map((credential) => {
        const submitter = credential.role === 'submitter';
        const name = submitter ? 'Invoice submitter' : 'Financial reviewer';
        const shortName = submitter ? 'submitter' : 'reviewer';
        return (
          <section className="demo-role" aria-label={`${name} demo access`} key={credential.role}>
            <h2>{name}</h2>
            <p>
              {submitter
                ? 'Submit invoices and view submissions made with this identity. Connect your own OpenAI API key and select a model before uploading. Submitters cannot create POs or resolve financial reviews.'
                : 'Add vendors, manage Approved / Inactive / Blacklisted status, create purchase orders for approved vendors, inspect workspace invoices and allocations, and resolve review requests. No OpenAI API key is needed. Reviewers cannot submit invoices or edit existing POs.'}
            </p>
            <code aria-label={`${name} access token`}>{credential.token}</code>
            <div className="demo-actions">
              <button
                className="button quiet small"
                type="button"
                disabled={disabled}
                onClick={() => void copy(credential)}
              >
                Copy {shortName} token
              </button>
              <button
                className="button quiet small"
                type="button"
                disabled={disabled}
                onClick={() => {
                  setMessage('Token filled. Click Connect to verify access.');
                  onUse(credential.token);
                }}
              >
                Use {shortName} token
              </button>
            </div>
          </section>
        );
      })}
      <section className="demo-role" aria-label="Testing with purchase orders">
        <h2>Test with prepared purchase orders</h2>
        <p>
          Use the sample invoice PDFs with their prepared demo purchase orders. Sign in as a
          financial reviewer and open Purchase orders to check the available POs and their remaining
          balances before testing.
        </p>
        <p>
          Reviewers can also create a new PO in Purchase orders. A custom invoice must quote its
          exact reference and match the vendor and line terms. Blacklisted vendors cannot receive
          new POs. Existing POs cannot be edited or deleted here.
        </p>
      </section>
      <p>These are app access tokens, separate from your private OpenAI API key.</p>
      <p className="demo-feedback" role="status">
        {message}
      </p>
    </details>
  );
}
