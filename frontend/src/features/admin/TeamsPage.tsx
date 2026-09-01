import { Users2 } from "lucide-react";
import { useSalesTeams } from "@/api/queries";
import { Page } from "@/app/shells/InternalShell";
import { Async, EmptyState, Panel, PanelHead } from "@/design-system";

export function TeamsPage() {
  const query = useSalesTeams();

  return (
    <Page title="Sales teams" subtitle="Teams enable the Sales Team filter on every report.">
      <Async
        query={query}
        isEmpty={(d) => d.length === 0}
        empty={
          <Panel>
            <EmptyState icon={<Users2 className="size-5" />} title="No sales teams" body="Create a team to group reps and filter reporting by it." />
          </Panel>
        }
      >
        {(teams) => (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {teams.map((t) => (
              <Panel key={t.id}>
                <PanelHead
                  dense
                  title={t.name}
                  subtitle={t.code}
                  actions={<span className="num text-xs text-content-muted">{t.members?.length ?? 0} members</span>}
                />
                <div className="p-3.5">
                  {(t.members?.length ?? 0) === 0 ? (
                    <p className="text-sm text-content-muted">No members yet.</p>
                  ) : (
                    <ul className="space-y-1.5">
                      {t.members!.map((mem) => (
                        <li key={mem.user_id} className="flex items-center gap-2">
                          <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-accent-100 font-ui text-2xs font-semibold text-accent-700">
                            {(mem.full_name ?? mem.email ?? "?").split(" ").map((s) => s[0]).slice(0, 2).join("")}
                          </span>
                          <span className="min-w-0 flex-1 truncate text-sm text-content">{mem.full_name ?? mem.email}</span>
                          <span className="shrink-0 text-2xs uppercase tracking-wide text-content-faint">{mem.role}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </Panel>
            ))}
          </div>
        )}
      </Async>
    </Page>
  );
}
