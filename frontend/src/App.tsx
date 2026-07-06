import { Link, Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth/useAuth";
import { Dashboard } from "./pages/Dashboard";
import { Landing } from "./pages/Landing";
import { Login } from "./pages/Login";
import { Upload } from "./pages/Upload";

// App shell + auth-aware routing (Phase B, D-064/D-065). Vertical is a property of the logged-in
// user (from `/api/me`), never a global picker — so every gated route resolves off `useAuth()`:
//   logged out            → Landing / Login (the dashboard never renders logged-out)
//   logged in, no profile → /onboarding (pick vertical + upload)
//   logged in, has profile → /dashboard for *their* vertical
function Spinner() {
  return <div className="notice">loading…</div>;
}

// `/` — the smart root: route each visitor to where they belong (D-065).
function Root() {
  const { user, profile, loading } = useAuth();
  if (loading) return <Spinner />;
  if (!user) return <Landing />;
  return <Navigate to={profile ? "/dashboard" : "/onboarding"} replace />;
}

// `/dashboard` — authed + onboarded only; otherwise bounce to login / onboarding.
function DashboardRoute() {
  const { user, profile, loading } = useAuth();
  if (loading) return <Spinner />;
  if (!user) return <Navigate to="/login" replace />;
  if (!profile) return <Navigate to="/onboarding" replace />;
  return <Dashboard vertical={profile.vertical} />;
}

// `/onboarding` — authed + NOT yet onboarded: pick a vertical + upload (the picker mode of Upload).
function OnboardingRoute() {
  const { user, profile, loading } = useAuth();
  if (loading) return <Spinner />;
  if (!user) return <Navigate to="/login" replace />;
  if (profile) return <Navigate to="/dashboard" replace />;
  return <Upload />;
}

// `/upload` — résumé update for an already-onboarded user: vertical is fixed to theirs (immutable,
// one-vertical-per-user D-064). No profile yet → send to onboarding instead.
function UploadRoute() {
  const { user, profile, loading } = useAuth();
  if (loading) return <Spinner />;
  if (!user) return <Navigate to="/login" replace />;
  if (!profile) return <Navigate to="/onboarding" replace />;
  return <Upload lockedVertical={profile.vertical} />;
}

export default function App() {
  const { user, profile, loading, logout } = useAuth();

  return (
    <div className="app">
      <header className="header">
        <Link to="/" className="wordmark">
          <span className="prompt">$</span> rolefeed<span className="cursor">▮</span>
        </Link>
        <nav className="nav">
          {loading ? null : user ? (
            <>
              {profile && (
                <Link to="/upload" className="nav-link">
                  update résumé
                </Link>
              )}
              <span className="nav-user">{user.email}</span>
              <button type="button" className="nav-link as-button" onClick={() => void logout()}>
                sign out
              </button>
            </>
          ) : (
            <Link to="/login" className="nav-link">
              sign in
            </Link>
          )}
        </nav>
      </header>

      <Routes>
        <Route path="/" element={<Root />} />
        <Route path="/login" element={<Login />} />
        <Route path="/onboarding" element={<OnboardingRoute />} />
        <Route path="/dashboard" element={<DashboardRoute />} />
        <Route path="/upload" element={<UploadRoute />} />
      </Routes>
    </div>
  );
}
