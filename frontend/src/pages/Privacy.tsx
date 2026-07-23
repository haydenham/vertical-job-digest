// Privacy notice (D-094, compliance PR 1) — a static, plain-language page reachable logged-out.
// Honest description of what Rolefeed stores and where résumé text goes (third-party AI model
// APIs). Self-serve unsubscribe shipped with PR 2 (every digest footer carries the link);
// self-serve delete lands in PR 3, so "delete my data" points at the founder contact until then.
// Copy is a product notice, not legal advice.

const CONTACT_EMAIL = "haydenham10@gmail.com";

export function Privacy() {
  return (
    <div className="legal-page">
      <h1 className="legal-title">Privacy notice</h1>
      <p className="legal-updated">Last updated: July 22, 2026</p>

      <p>
        Rolefeed is a small job-matching service. This page describes, in plain language, what data
        it keeps and what happens to it. If anything here is unclear, email{" "}
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
      </p>

      <h2>What Rolefeed stores</h2>
      <ul>
        <li>
          <strong>Your Google account email and name</strong>, from signing in with Google. Rolefeed
          never sees your Google password.
        </li>
        <li>
          <strong>Your résumé text</strong>, which you upload so new job postings can be matched
          against it.
        </li>
        <li>
          <strong>Your match results and digest history</strong> — the fits, gaps, verdicts, and
          emails Rolefeed generates for you.
        </li>
      </ul>

      <h2>How your résumé is used</h2>
      <p>
        Your résumé text is sent to third-party AI model providers — currently{" "}
        <strong>Anthropic</strong> and <strong>OpenAI</strong> — to produce your match write-ups
        (what fits, what doesn&rsquo;t, and a verdict). Job-posting text is processed by the same
        providers. Under both providers&rsquo; API terms, data sent through their APIs is not used
        to train their models. Your résumé is used only to generate your matches — nothing else.
      </p>

      <h2>Email</h2>
      <p>
        Rolefeed sends your morning digest to your Google account email through Resend, an email
        delivery service. To stop receiving digests, use the unsubscribe link in any digest&rsquo;s
        footer — matching and your dashboard keep working. You can also email{" "}
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
      </p>

      <h2>Cookies</h2>
      <p>
        Rolefeed uses one session cookie so you stay signed in. There are no advertising or
        cross-site tracking cookies.
      </p>

      <h2>What Rolefeed never does</h2>
      <ul>
        <li>It never sells or shares your data with anyone beyond the services named above.</li>
        <li>It never submits job applications on your behalf — every application stays yours.</li>
      </ul>

      <h2>Deleting your data</h2>
      <p>
        To delete your account and everything attached to it (résumé, matches, digest history),
        email <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> and it will be removed. A
        self-serve delete button is on its way.
      </p>
    </div>
  );
}
