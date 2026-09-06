import * as React from "react";
import { useNavigate } from "react-router-dom";
import { useCreateDeal, useCreateQuote, useCustomers } from "@/api/queries";
import { errorTitle } from "@/api/errors";
import { Button, Dialog, FormField, Input, Select, toast } from "@/design-system";

/**
 * A quotation needs a deal, and a deal needs a customer. Rather than making the
 * user visit three screens, this creates the deal and the quote in sequence and
 * lands them in the builder.
 */
export function NewQuoteDialog({
  open, onOpenChange, presetCustomerId,
}: { open: boolean; onOpenChange: (v: boolean) => void; presetCustomerId?: string }) {
  const nav = useNavigate();
  const customers = useCustomers();
  const createDeal = useCreateDeal();
  const createQuote = useCreateQuote();

  const [customerId, setCustomerId] = React.useState(presetCustomerId ?? "");
  const [title, setTitle] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!customerId && customers.data?.length === 1) setCustomerId(customers.data[0].id);
  }, [customers.data, customerId]);

  const busy = createDeal.isPending || createQuote.isPending;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!customerId) return setError("Choose a customer.");
    if (!title.trim()) return setError("Give the quotation a title.");
    try {
      const deal = await createDeal.mutateAsync({
        name: title.trim(),
        customer_profile_id: customerId,
        stage: "PROPOSAL",
        expected_value: "0",
      });
      const quote = await createQuote.mutateAsync({
        dealId: deal.id,
        body: { title: title.trim(), order_discount_pct: "0" },
      });
      const versionId = quote.current_version_id ?? quote.versions?.[0]?.id;
      toast.success("Quotation created", `${quote.quote_number} is ready to build.`);
      onOpenChange(false);
      nav(versionId ? `/quotes/${quote.id}/versions/${versionId}/build` : `/quotes/${quote.id}`);
    } catch (err) {
      setError(errorTitle(err));
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="New quotation"
      description="Creates the deal and its first draft version, then opens the builder."
      footer={
        <>
          <Button onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={submit}>Create and build</Button>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4">
        <FormField label="Customer" required hint="Tier and payment terms drive every discount ceiling on this quote.">
          {(p) => (
            <Select
              id={p.id}
              value={customerId}
              onValueChange={setCustomerId}
              placeholder={customers.isPending ? "Loading customers…" : "Choose a customer"}
              options={(customers.data ?? []).map((c) => ({
                value: c.id,
                label: c.display_name,
                hint: c.tier,
              }))}
            />
          )}
        </FormField>

        <FormField label="Title" required>
          {(p) => (
            <Input
              {...p}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Q3 laptop refresh"
              autoFocus
            />
          )}
        </FormField>

        {error ? (
          <p role="alert" className="text-sm font-medium text-[var(--policy-violated)]">{error}</p>
        ) : null}
      </form>
    </Dialog>
  );
}
