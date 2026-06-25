import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { setSession } from "../api/client";

const KNOWN_ERRORS = new Set(["google_failed", "email_unverified"]);

/** Lands here after Google redirects back with the token in the URL fragment
 * (#token=…). Fragments aren't sent to servers, so the token stays out of logs
 * and the Referer header. */
export default function AuthCallback() {
  const navigate = useNavigate();

  useEffect(() => {
    const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const token = hash.get("token");
    if (token) {
      setSession(token);
      // Strip the token from the address bar immediately.
      window.history.replaceState(null, "", "/auth/callback");
      navigate("/", { replace: true });
      return;
    }
    // Failure path (token in query as ?error= isn't used, but be defensive).
    const params = new URLSearchParams(window.location.search);
    const raw = params.get("error") ?? hash.get("error") ?? "google_failed";
    const error = KNOWN_ERRORS.has(raw) ? raw : "google_failed";
    navigate(`/login?error=${error}`, { replace: true });
  }, [navigate]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <p className="text-gray-500">Signing you in…</p>
    </div>
  );
}
