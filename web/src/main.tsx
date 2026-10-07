import React from "react";
import ReactDOM from "react-dom/client";

import CatalogWorkspace from "./CatalogWorkspace";
import "@xyflow/react/dist/style.css";
import "./styles/tokens.css";
import "./style.css";

type CurrentUser = {
  email: string;
  tenant_name: string;
};

type ApiError = {
  detail?: string;
};

function getCookie(name: string): string | null {
  const prefix = `${name}=`;
  const cookie = document.cookie.split("; ").find((entry) => entry.startsWith(prefix));
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : null;
}

async function getError(response: Response): Promise<string> {
  const body = (await response.json().catch(() => ({}))) as ApiError;
  if (response.status === 429) {
    return "Too many login attempts. Wait a minute and try again.";
  }
  return body.detail ?? "The request could not be completed.";
}

function App() {
  const [status, setStatus] = React.useState("Checking API and database…");
  const [user, setUser] = React.useState<CurrentUser | null>(null);
  const [checkingSession, setCheckingSession] = React.useState(true);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    let active = true;

    void Promise.all([
      fetch("/health").then(async (response) => {
        const result: { api: string; database: string } = await response.json();
        if (!response.ok) {
          throw new Error("Database is unavailable");
        }
        if (active) {
          setStatus(`API ${result.api} · Database ${result.database}`);
        }
      }),
      fetch("/api/auth/me").then(async (response) => {
        if (response.ok) {
          const currentUser = (await response.json()) as CurrentUser;
          if (active) {
            setUser(currentUser);
          }
        } else if (response.status !== 401) {
          throw new Error("Could not check the current session");
        }
      }),
    ])
      .catch(() => {
        if (active) {
          setStatus("Application services are unavailable");
        }
      })
      .finally(() => {
        if (active) {
          setCheckingSession(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  async function handleLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    const form = new FormData(event.currentTarget);
    try {
      const csrfResponse = await fetch("/api/auth/csrf");
      if (!csrfResponse.ok) {
        throw new Error(await getError(csrfResponse));
      }
      const { csrf_token: csrfToken } = (await csrfResponse.json()) as {
        csrf_token: string;
      };
      const loginResponse = await fetch("/api/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
        },
        body: JSON.stringify({
          email: form.get("email"),
          password: form.get("password"),
        }),
      });
      if (!loginResponse.ok) {
        throw new Error(await getError(loginResponse));
      }
      const currentResponse = await fetch("/api/auth/me");
      if (!currentResponse.ok) {
        throw new Error(await getError(currentResponse));
      }
      setUser((await currentResponse.json()) as CurrentUser);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Login failed.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleLogout() {
    setError("");
    setSubmitting(true);
    try {
      const csrfToken = getCookie("dd_csrf");
      if (!csrfToken) {
        throw new Error("Your session could not be verified. Reload and try again.");
      }
      const response = await fetch("/api/auth/logout", {
        method: "POST",
        headers: { "X-CSRF-Token": csrfToken },
      });
      if (!response.ok) {
        throw new Error(await getError(response));
      }
      setUser(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Logout failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    user ? (
      <CatalogWorkspace
        onLogout={() => void handleLogout()}
        email={user.email}
        tenantName={user.tenant_name}
        loggingOut={submitting}
      />
    ) : (
      <main className="page">
        <section className="card" aria-labelledby="title">
          <p className="eyebrow">INTERNAL DATA ARCHITECTURE</p>
          <h1 id="title">Data Designer</h1>
          <p className="summary">
            Design systems, objects, fields, and the contracts between them.
          </p>
          <p className="health" role="status" aria-live="polite">
            {status}
          </p>
          {checkingSession ? (
            <p className="session-status" role="status">
              Checking your session…
            </p>
          ) : (
            <form className="login-form" onSubmit={handleLogin}>
              <h2>Sign in</h2>
              <label>
                Email
                <input
                  type="email"
                  name="email"
                  autoComplete="username"
                  required
                  maxLength={255}
                />
              </label>
              <label>
                Password
                <input
                  type="password"
                  name="password"
                  autoComplete="current-password"
                  required
                  maxLength={1024}
                />
              </label>
              {error && (
                <p className="error" role="alert">
                  {error}
                </p>
              )}
              <button type="submit" disabled={submitting}>
                {submitting ? "Signing in…" : "Sign in"}
              </button>
            </form>
          )}
        </section>
      </main>
    )
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
