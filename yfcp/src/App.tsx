import * as React from "react";
import { Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { AppShell } from "@/components/layout/app-shell";
import { TooltipProvider } from "@/components/ui/primitives";
import { useUi } from "@/stores/ui";
import { Onboarding, useOnboarding } from "@/components/layout/onboarding";

const Dashboard = React.lazy(() => import("@/pages/dashboard"));
const Accounts = React.lazy(() => import("@/pages/accounts"));
const AccountDetail = React.lazy(() => import("@/pages/account-detail"));
const Adopt = React.lazy(() => import("@/pages/adopt"));
const Batches = React.lazy(() => import("@/pages/batches"));
const Sessions = React.lazy(() => import("@/pages/sessions"));
const LoginReauth = React.lazy(() => import("@/pages/login-reauth"));
const Warming = React.lazy(() => import("@/pages/warming"));
const Reviews = React.lazy(() => import("@/pages/reviews"));
const Clients = React.lazy(() => import("@/pages/clients"));
const Pools = React.lazy(() => import("@/pages/pools"));
const Trust = React.lazy(() => import("@/pages/trust"));
const Velocity = React.lazy(() => import("@/pages/velocity"));
const Audit = React.lazy(() => import("@/pages/audit"));
const Volume = React.lazy(() => import("@/pages/volume"));
const Reports = React.lazy(() => import("@/pages/reports"));
const Alerts = React.lazy(() => import("@/pages/alerts"));
const Reaper = React.lazy(() => import("@/pages/reaper"));
const Lifecycle = React.lazy(() => import("@/pages/lifecycle"));
const Fingerprints = React.lazy(() => import("@/pages/fingerprints"));
const Governor = React.lazy(() => import("@/pages/governor"));
const Flags = React.lazy(() => import("@/pages/flags"));
const Selectors = React.lazy(() => import("@/pages/selectors"));
const Logs = React.lazy(() => import("@/pages/logs"));
const Health = React.lazy(() => import("@/pages/health"));
const Data = React.lazy(() => import("@/pages/data"));
const Config = React.lazy(() => import("@/pages/config"));

function RouteFallback() {
  return (
    <div className="space-y-3 pt-2">
      <div className="h-6 w-48 animate-pulse rounded-md bg-secondary" />
      <div className="h-3 w-96 animate-pulse rounded bg-secondary/70" />
      <div className="grid grid-cols-2 gap-3 pt-3 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-20 animate-pulse rounded-lg border border-border bg-card/60" />
        ))}
      </div>
      <div className="h-64 animate-pulse rounded-lg border border-border bg-card/60" />
    </div>
  );
}

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div className="grid h-full place-items-center p-8">
          <div className="max-w-md space-y-2 text-center">
            <h2 className="text-sm font-semibold">This screen crashed</h2>
            <p className="text-xs text-muted-foreground">{this.state.error.message}</p>
            <button
              className="mt-2 rounded-md border border-border px-3 py-1.5 text-xs hover:bg-accent"
              onClick={() => this.setState({ error: null })}
            >
              Try again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  const theme = useUi((s) => s.theme);
  const { done, finish } = useOnboarding();

  React.useEffect(() => {
    document.documentElement.classList.toggle("light", theme === "light");
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  return (
    <TooltipProvider>
      <AppShell>
        <ErrorBoundary>
          <React.Suspense fallback={<RouteFallback />}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/accounts" element={<Accounts />} />
              <Route path="/accounts/:id" element={<AccountDetail />} />
              <Route path="/adopt" element={<Adopt />} />
              <Route path="/batches" element={<Batches />} />
              <Route path="/sessions" element={<Sessions />} />
              <Route path="/login" element={<LoginReauth />} />
              <Route path="/warming" element={<Warming />} />
              <Route path="/reviews" element={<Reviews />} />
              <Route path="/clients" element={<Clients />} />
              <Route path="/pools" element={<Pools />} />
              <Route path="/trust" element={<Trust />} />
              <Route path="/velocity" element={<Velocity />} />
              <Route path="/audit" element={<Audit />} />
              <Route path="/volume" element={<Volume />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="/alerts" element={<Alerts />} />
              <Route path="/reaper" element={<Reaper />} />
              <Route path="/lifecycle" element={<Lifecycle />} />
              <Route path="/fingerprints" element={<Fingerprints />} />
              <Route path="/governor" element={<Governor />} />
              <Route path="/flags" element={<Flags />} />
              <Route path="/selectors" element={<Selectors />} />
              <Route path="/logs" element={<Logs />} />
              <Route path="/health" element={<Health />} />
              <Route path="/data" element={<Data />} />
              <Route path="/config" element={<Config />} />
            </Routes>
          </React.Suspense>
        </ErrorBoundary>
      </AppShell>
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: "hsl(var(--popover))",
            border: "1px solid hsl(var(--border))",
            color: "hsl(var(--popover-foreground))",
            fontSize: "12px",
          },
        }}
      />
      <Onboarding open={!done} onDone={finish} />
    </TooltipProvider>
  );
}
