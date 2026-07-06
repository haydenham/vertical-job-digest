import { loginUrl } from "../api";

// Logged-out landing at `/` (D-065). A minimal placeholder — the dashboard is never rendered
// logged-out (that leaked a raw 401 string), so an anonymous visitor lands here with a clear login
// CTA instead. Real marketing design comes later; for now: brand + one line + sign in.
export function Landing() {
  return (
    <div className="panel auth-landing">
      <p className="success-line">Rolefeed — total-coverage job intelligence.</p>
      <p className="auth-blurb">
        We watch a bounded universe of employers, diff their postings nightly, and match new roles to
        your résumé with a written verdict. Sign in to pick your vertical and upload a résumé.
      </p>
      <a className="btn btn-primary" href={loginUrl()}>
        Sign in with Google
      </a>
    </div>
  );
}
