import { loginUrl } from "../api";

// Sign-in landing. The button is a plain anchor to the API's `/auth/login` (loginUrl targets the
// API origin so it works in split-origin dev too); the browser follows the 302 to Google, and the
// callback opens a session then redirects home. Login is inert (503) until GOOGLE_CLIENT_* are set.
export function Login() {
  return (
    <div className="panel auth-landing">
      <p className="auth-blurb">
        Sign in to upload your résumé and see roles matched to it. Without signing in you can still
        browse the open postings.
      </p>
      <a className="btn btn-primary" href={loginUrl()}>
        Sign in with Google
      </a>
    </div>
  );
}
