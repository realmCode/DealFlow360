import { useAuth } from "@/app/auth";
import { Field, FieldList } from "@/design-system";

export function PortalProfilePage() {
  const { user } = useAuth();

  return (
    <div>
      <header className="mb-7">
        <h1 className="font-ui text-3xl font-semibold tracking-tight text-ink-900">Profile</h1>
        <p className="mt-2 max-w-2xl text-lg leading-relaxed text-content-secondary">
          The account you are signed in with.
        </p>
      </header>

      <div className="max-w-xl rounded-xl border border-[#e8e4dd] bg-white p-6">
        <div className="flex items-center gap-4">
          <span className="flex size-12 items-center justify-center rounded-full bg-accent-100 font-ui text-lg font-semibold text-accent-700">
            {(user?.full_name ?? "?").split(" ").map((s) => s[0]).slice(0, 2).join("")}
          </span>
          <div className="min-w-0">
            <p className="font-ui text-lg font-semibold text-ink-900">{user?.full_name}</p>
            <p className="text-md text-content-muted">{user?.email}</p>
          </div>
        </div>

        <FieldList className="mt-6">
          <Field label="Organisation">{user?.organization_name}</Field>
          <Field label="Account type">Customer</Field>
        </FieldList>

        <p className="mt-6 text-sm leading-relaxed text-content-muted">
          To change your details or add a colleague to this account, message your account team from any
          proposal.
        </p>
      </div>
    </div>
  );
}
