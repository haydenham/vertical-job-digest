import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { useAuth } from "./auth/useAuth";
import { TOUR_SEEN_KEY, WelcomeTour } from "./components/WelcomeTour";
import { Dashboard } from "./pages/Dashboard";
import { Landing } from "./pages/Landing";
import { Login } from "./pages/Login";
import { Privacy } from "./pages/Privacy";
import { Settings } from "./pages/Settings";
import { Upload } from "./pages/Upload";

// App shell + auth-aware routing (Phase B, D-064/D-065). Vertical is a property of the logged-in
// user (from `/api/me`), never a global picker — so every gated route resolves off `useAuth()`:
//   logged out            → Landing / Login (the dashboard never renders logged-out)
//   logged in, no profile → /onboarding (pick vertical + upload)
//   logged in, has profile → /dashboard for *their* vertical
function Spinner() {
  return <div className="notice">loading…</div>;
}

function AccountLoadError() {
  const { refresh } = useAuth();
  return (
    <div className="notice error" role="alert">
      We couldn't load your account.{" "}
      <button
        type="button"
        className="link-button"
        onClick={() => void refresh().catch(() => undefined)}
      >
        Try again
      </button>
      .
    </div>
  );
}

// `/` — the smart root: route each visitor to where they belong (D-065).
function Root() {
  const { user, profile, loading, authError } = useAuth();
  if (loading) return <Spinner />;
  if (authError) return <AccountLoadError />;
  if (!user) return <Landing />;
  return <Navigate to={profile ? "/dashboard" : "/onboarding"} replace />;
}

// `/dashboard` — authed + onboarded only; otherwise bounce to login / onboarding.
function DashboardRoute() {
  const { user, profile, loading, authError } = useAuth();
  if (loading) return <Spinner />;
  if (authError) return <AccountLoadError />;
  if (!user) return <Navigate to="/login" replace />;
  if (!profile) return <Navigate to="/onboarding" replace />;
  return <Dashboard vertical={profile.vertical} />;
}

// `/onboarding` — authed + NOT yet onboarded: pick a vertical + upload (the picker mode of Upload).
function OnboardingRoute() {
  const { user, profile, loading, authError } = useAuth();
  if (loading) return <Spinner />;
  if (authError) return <AccountLoadError />;
  if (!user) return <Navigate to="/login" replace />;
  if (profile) return <Navigate to="/dashboard" replace />;
  return <Upload />;
}

// `/upload` — résumé update for an already-onboarded user: vertical is fixed to theirs (immutable,
// one-vertical-per-user D-064). No profile yet → send to onboarding instead.
function UploadRoute() {
  const { user, profile, loading, authError } = useAuth();
  if (loading) return <Spinner />;
  if (authError) return <AccountLoadError />;
  if (!user) return <Navigate to="/login" replace />;
  if (!profile) return <Navigate to="/onboarding" replace />;
  return <Upload lockedVertical={profile.vertical} />;
}

// `/settings` — login-gated only (D-094): a user with no profile yet must still reach account
// deletion, so there is no onboarding bounce (Settings handles its own post-deletion routing).
function SettingsRoute() {
  const { user, loading, authError } = useAuth();
  if (loading) return <Spinner />;
  if (authError) return <AccountLoadError />;
  if (!user) return <Navigate to="/login" replace />;
  return <Settings />;
}

// `/login` is a logged-out-only route. An existing session continues through the same one-profile
// routing as `/` instead of presenting another Google sign-in form (D-083).
function LoginRoute() {
  const { user, profile, loading, authError } = useAuth();
  if (loading) return <Spinner />;
  if (authError) return <AccountLoadError />;
  if (!user) return <Login />;
  return <Navigate to={profile ? "/dashboard" : "/onboarding"} replace />;
}

export default function App() {
  const { user, profile, loading, authError, logout } = useAuth();
  const location = useLocation();
  const [tourOpen, setTourOpen] = useState(false);

  // D-085 first-run tutorial: browser-local is sufficient for beta. Auto-open only when an
  // onboarded user reaches the dashboard; the nav button can reopen it from any profiled route.
  useEffect(() => {
    if (profile && location.pathname === "/dashboard" && !localStorage.getItem(TOUR_SEEN_KEY)) {
      setTourOpen(true);
    }
  }, [location.pathname, profile]);

  const dismissTour = useCallback(() => {
    localStorage.setItem(TOUR_SEEN_KEY, "1");
    setTourOpen(false);
  }, []);

  return (
    <div className="app">
      <header className="header">
        <Link to="/" className="wordmark">
          <span className="mark" aria-hidden="true" />
          Rolefeed
        </Link>
        <nav className="nav">
          {loading || authError ? null : user ? (
            <>
              {profile && (
                <>
                  <button
                    type="button"
                    className="nav-link as-button tour-help"
                    aria-label="Open welcome tour"
                    title="How Rolefeed works"
                    onClick={() => setTourOpen(true)}
                  >
                    ?
                  </button>
                  <Link to="/upload" className="nav-link">
                    Update résumé
                  </Link>
                </>
              )}
              <Link to="/settings" className="nav-link">
                Settings
              </Link>
              <span className="nav-user">{user.email}</span>
              <button type="button" className="nav-link as-button" onClick={() => void logout()}>
                Sign out
              </button>
            </>
          ) : (
            <Link to="/login" className="nav-link">
              Sign in
            </Link>
          )}
        </nav>
      </header>

      <Routes>
        <Route path="/" element={<Root />} />
        <Route path="/login" element={<LoginRoute />} />
        <Route path="/onboarding" element={<OnboardingRoute />} />
        <Route path="/dashboard" element={<DashboardRoute />} />
        <Route path="/upload" element={<UploadRoute />} />
        <Route path="/settings" element={<SettingsRoute />} />
        <Route path="/privacy" element={<Privacy />} />
      </Routes>
      {/* The landing page owns its own footer (with its own Privacy link), so the shell footer
          skips `/` — where Landing renders logged-out and logged-in visitors redirect anyway. */}
      {location.pathname !== "/" && (
        <footer className="app-footer">
          <Link to="/privacy" className="app-footer-link">
            Privacy
          </Link>
          <span className="app-footer-copy">© 2026 Rolefeed</span>
        </footer>
      )}
      {tourOpen && profile && <WelcomeTour onDismiss={dismissTour} />}
    </div>
  );
}
