import { Link } from "react-router-dom";

import { BrandMark } from "./components/BrandMark";
import { Badge } from "./components/ui/Badge";
import { Button } from "./components/ui/Button";
import { Card } from "./components/ui/Card";
import { buildAppShell } from "./app-shell";

export function App() {
  const shell = buildAppShell();

  return (
    <div className="flex h-full overflow-hidden bg-gradient-to-br from-white via-brand-50/30 to-slate-50">
      <main className="mx-auto flex w-full max-w-5xl flex-col justify-center gap-6 overflow-hidden px-4 py-8">
        <Card className="shadow-panel" padding="lg">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <BrandMark subtitle="Phase 1 MVP" size="lg" />
            <Badge variant="success">Production ready</Badge>
          </div>

          <h1 className="mt-6 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">{shell.title}</h1>
          <p className="mt-3 max-w-3xl text-base leading-relaxed text-slate-600">{shell.subtitle}</p>

          <div className="mt-6 flex flex-wrap gap-2">
            {shell.scopeHighlights.map((item) => (
              <Badge key={item}>{item}</Badge>
            ))}
          </div>

          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/login">
              <Button variant="primary" size="lg">
                Sign in
              </Button>
            </Link>
            <Link to="/chat">
              <Button variant="secondary" size="lg">
                Open chat
              </Button>
            </Link>
          </div>
        </Card>

        <div className="grid shrink-0 gap-4 md:grid-cols-2">
          <Card padding="md">
            <h2 className="text-lg font-semibold text-slate-900">Data posture</h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">{shell.tenantModel}</p>
            <p className="mt-2 text-sm text-slate-500">{shell.dataPolicy}</p>
          </Card>
          <Card className="border-brand-200 bg-brand-50/30" padding="md">
            <h2 className="text-lg font-semibold text-slate-900">Retention</h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">
              Conversation data is retained for {shell.retentionPolicyDays} days.
            </p>
            <p className="mt-2 text-sm text-slate-500">
              Tenant-level deletion is supported for user-controlled data removal.
            </p>
          </Card>
        </div>
      </main>
    </div>
  );
}
