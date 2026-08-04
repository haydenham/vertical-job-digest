import { loginUrl } from "../api";

// Sign-in card (UI rework PR 2, D-080). The button is a plain anchor to the API's `/auth/login`
// (loginUrl targets the API origin so it works in split-origin dev too); the browser follows the
// 302 to Google, and the callback opens a session then redirects home. Login is inert (503) until
// GOOGLE_CLIENT_* are set. Signing in is required — auth went ON at go-live (D-067), so there is
// no logged-out browsing to advertise.
const BENEFITS = [
  "A daily digest of new roles in your vertical",
  "Honest match verdicts against your résumé",
  "Every apply link verified before it reaches you",
];

export function Login() {
  return (
    <div className="auth-page">
      <div className="panel auth-card">
        <span className="mark auth-mark" aria-hidden="true" />
        <h1 className="auth-title">Sign in to Rolefeed</h1>
        <ul className="auth-benefits">
          {BENEFITS.map((b) => (
            <li key={b}>{b}</li>
          ))}
        </ul>
        <a className="btn btn-primary" href={loginUrl()}>
          Sign in with Google
        </a>
      </div>
    </div>
  );
}
