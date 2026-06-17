import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { BrandMark } from "../components/BrandMark";
import { Card } from "../components/ui/Card";
import { authStorage } from "../lib/api";

export function AuthCallbackPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [message, setMessage] = useState("Completing sign in...");
  const [isError, setIsError] = useState(false);

  useEffect(() => {
    const token = searchParams.get("token");
    const error = searchParams.get("error");

    if (error) {
      setIsError(true);
      setMessage(`Authentication failed: ${error}`);
      return;
    }

    if (token) {
      authStorage.setToken(token);
      navigate("/chat");
      return;
    }

    setIsError(true);
    setMessage("Missing authentication token.");
  }, [navigate, searchParams]);

  return (
    <div className="flex h-full items-center justify-center overflow-hidden bg-gradient-to-br from-white via-brand-50/30 to-white px-4">
      <Card className="w-full max-w-md text-center shadow-panel" padding="lg">
        <BrandMark subtitle="Signing in" size="md" />
        {!isError ? (
          <div className="mx-auto mt-6 h-8 w-8 animate-spin rounded-full border-2 border-brand-200 border-t-brand-600" />
        ) : null}
        <p className={`mt-4 text-sm ${isError ? "text-red-600" : "text-slate-600"}`}>{message}</p>
      </Card>
    </div>
  );
}
