import { Link, Route, Routes } from "react-router-dom";

import { loginUrl } from "./api";
import { useAuth } from "./auth/useAuth";
import { Dashboard } from "./pages/Dashboard";
import { Login } from "./pages/Login";
import { Upload } from "./pages/Upload";

// App shell: brand + auth-aware nav chrome, then the routed pages. `VJA_AUTH_REQUIRED` stays off
// in 9.4, so the dashboard is reachable anonymously; login only gates the upload write path.
export default function App() {
  const { user, loading, logout } = useAuth();

  return (
    <div className="app">
      <header className="header">
        <Link to="/" className="wordmark">
          <span className="prompt">$</span> rolefeed<span className="cursor">▮</span>
        </Link>
        <nav className="nav">
          {loading ? null : user ? (
            <>
              <Link to="/upload" className="nav-link">
                upload résumé
              </Link>
              <span className="nav-user">{user.email}</span>
              <button type="button" className="nav-link as-button" onClick={() => void logout()}>
                sign out
              </button>
            </>
          ) : (
            <a href={loginUrl()} className="nav-link">
              sign in
            </a>
          )}
        </nav>
      </header>

      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/login" element={<Login />} />
        <Route path="/upload" element={<Upload />} />
      </Routes>
    </div>
  );
}
