/**
 * Query keys, fetchers and mutations.
 *
 * Freshness policy (the backend has no push channel, so this is deliberate):
 *  - refetch after any mutation that could change it
 *  - refetch on window focus
 *  - poll ONLY the control tower and the approval inbox, 45s, and only while
 *    the tab is visible. Nothing else polls; a quote under edit never polls.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";
import { api, rows } from "./client";
import type * as T from "./types";

/* ========================================================================== */
/* keys                                                                        */
/* ========================================================================== */
export const qk = {
  me: ["me"] as const,
  users: ["users"] as const,
  controlTower: ["control-tower"] as const,
  attention: (params?: unknown) => ["attention-items", params ?? {}] as const,
  dealHealth: ["deal-health"] as const,
  dealHealthOne: (id: string) => ["deal-health", id] as const,

  deals: (params?: unknown) => ["deals", params ?? {}] as const,
  deal: (id: string) => ["deal", id] as const,
  customers: ["customers"] as const,
  customer: (id: string) => ["customer", id] as const,
  contacts: (id: string) => ["customer", id, "contacts"] as const,

  quotes: (params?: unknown) => ["quotes", params ?? {}] as const,
  quote: (id: string) => ["quote", id] as const,
  version: (id: string) => ["quote-version", id] as const,
  policyResults: (id: string) => ["quote-version", id, "policy-results"] as const,
  impact: (id: string) => ["quote-version", id, "impact"] as const,
  versionApproval: (id: string) => ["quote-version", id, "approval"] as const,
  recommendations: (id: string) => ["quote", id, "recommendations"] as const,
  negotiation: (id: string) => ["quote", id, "negotiation"] as const,

  approvalInbox: ["approvals", "inbox"] as const,
  approval: (id: string) => ["approval", id] as const,

  orders: (params?: unknown) => ["orders", params ?? {}] as const,
  order: (id: string) => ["order", id] as const,
  allocations: (id: string) => ["order", id, "allocations"] as const,
  inventory: ["inventory"] as const,
  warehouses: ["warehouses"] as const,
  warehouse: (id: string) => ["warehouse", id] as const,

  schedules: (params?: unknown) => ["billing", "schedules", params ?? {}] as const,
  billingSummary: (id: string) => ["billing", "summary", id] as const,
  invoices: (params?: unknown) => ["billing", "invoices", params ?? {}] as const,
  creditNotes: ["billing", "credit-notes"] as const,

  products: (params?: unknown) => ["products", params ?? {}] as const,
  product: (id: string) => ["product", id] as const,
  variants: ["admin", "product-variants"] as const,
  priceLists: ["admin", "price-lists"] as const,
  policies: ["policies"] as const,
  settings: ["admin", "settings"] as const,
  salesTeams: ["admin", "sales-teams"] as const,

  audit: (params?: unknown) => ["audit", params ?? {}] as const,
  quoteTimeline: (id: string) => ["audit", "quote", id] as const,

  report: (name: string, params?: unknown) => ["report", name, params ?? {}] as const,
  portalQuotes: ["portal", "quotes"] as const,
  portalQuote: (id: string) => ["portal", "quote", id] as const,
  portalMessages: (id: string) => ["portal", "quote", id, "messages"] as const,
};

/* Anything that can change the action queue invalidates these two. */
const SIGNALS = [qk.controlTower, qk.attention(), qk.dealHealth];

/* ========================================================================== */
/* identity                                                                    */
/* ========================================================================== */
export const useMe = (enabled = true) =>
  useQuery({
    queryKey: qk.me,
    queryFn: () => api.get<T.AuthenticatedUser>("/users/me"),
    enabled,
    staleTime: 5 * 60_000,
    retry: false,
  });

export const useUsers = () =>
  useQuery({ queryKey: qk.users, queryFn: () => api.get<T.UserRead[]>("/users").then(rows) });

/* ========================================================================== */
/* command centre + intelligence                                               */
/* ========================================================================== */
const visiblePoll = (ms: number) => () =>
  typeof document !== "undefined" && document.visibilityState === "visible" ? ms : false;

export const useControlTower = () =>
  useQuery({
    queryKey: qk.controlTower,
    queryFn: () => api.get<T.ControlTowerRead>("/dashboard/control-tower"),
    refetchInterval: visiblePoll(45_000),
  });

export const useAttentionItems = (params?: { status?: string; severity?: string; type?: string }) =>
  useQuery({
    queryKey: qk.attention(params),
    queryFn: () => api.get<T.AttentionItemRead[]>("/dashboard/attention-items", params).then(rows),
  });

export const useDealHealth = () =>
  useQuery({
    queryKey: qk.dealHealth,
    queryFn: () => api.get<T.DealHealthListRead>("/dashboard/deal-health"),
  });

export const useDealHealthOne = (id: string | undefined | null) =>
  useQuery({
    queryKey: qk.dealHealthOne(id!),
    queryFn: () => api.get<T.DealHealthRead>(`/dashboard/deal-health/${id}`),
    enabled: Boolean(id),
  });

export const useAttentionAction = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action, body }: { id: string; action: "acknowledge" | "resolve" | "nudge" | "escalate"; body?: unknown }) =>
      api.post(`/dashboard/attention-items/${id}/${action}`, body ?? {}),
    onSuccess: () => SIGNALS.forEach((k) => qc.invalidateQueries({ queryKey: k })),
  });
};

/* ========================================================================== */
/* deals + customers                                                           */
/* ========================================================================== */
export const useDeals = (params?: Record<string, unknown>) =>
  useQuery({
    queryKey: qk.deals(params),
    queryFn: () => api.get<T.Page<T.DealRead> | T.DealRead[]>("/deals", params as never),
  });

export const useDeal = (id: string | undefined | null) =>
  useQuery({
    queryKey: qk.deal(id!),
    queryFn: () => api.get<T.DealRead>(`/deals/${id}`),
    enabled: Boolean(id),
  });

export const useCreateDeal = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: T.DealCreate) => api.post<T.DealRead>("/deals", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["deals"] }),
  });
};

export const useCustomers = () =>
  useQuery({
    queryKey: qk.customers,
    queryFn: () => api.get<T.CustomerProfileRead[]>("/customers").then(rows),
  });

export const useCustomer = (id: string | undefined | null) =>
  useQuery({
    queryKey: qk.customer(id!),
    queryFn: () => api.get<T.CustomerProfileRead>(`/customers/${id}`),
    enabled: Boolean(id),
  });

export const useContacts = (id: string | undefined | null) =>
  useQuery({
    queryKey: qk.contacts(id!),
    queryFn: () => api.get<T.ContactRead[]>(`/customers/${id}/contacts`).then(rows),
    enabled: Boolean(id),
  });

/* ========================================================================== */
/* quotes                                                                      */
/* ========================================================================== */
export const useQuotes = (params?: Record<string, unknown>) =>
  useQuery({
    queryKey: qk.quotes(params),
    queryFn: () => api.get<T.Page<T.QuoteListItem>>("/quotes", params as never),
  });

export const useQuote = (id: string | undefined | null) =>
  useQuery({
    queryKey: qk.quote(id!),
    queryFn: () => api.get<T.QuoteRead>(`/quotes/${id}`),
    enabled: Boolean(id),
  });

export const useVersion = (
  id: string | undefined,
  options?: Partial<UseQueryOptions<T.QuoteVersionRead>>,
) =>
  useQuery({
    queryKey: qk.version(id!),
    queryFn: () => api.get<T.QuoteVersionRead>(`/quote-versions/${id}`),
    enabled: Boolean(id),
    ...options,
  });

export const usePolicyResults = (id: string | undefined | null) =>
  useQuery({
    queryKey: qk.policyResults(id!),
    queryFn: () => api.get<T.PolicyEvaluationRead>(`/quote-versions/${id}/policy-results`),
    enabled: Boolean(id),
  });

export const useImpact = (id: string | undefined | null) =>
  useQuery({
    queryKey: qk.impact(id!),
    queryFn: () => api.get<T.ImpactRead>(`/quote-versions/${id}/impact`),
    enabled: Boolean(id),
  });

export const useVersionApproval = (id: string | undefined | null) =>
  useQuery({
    queryKey: qk.versionApproval(id!),
    queryFn: () => api.get<T.QuoteVersionApproval>(`/quote-versions/${id}/approval`),
    enabled: Boolean(id),
  });

export const useRecommendations = (quoteId: string | undefined | null) =>
  useQuery({
    queryKey: qk.recommendations(quoteId!),
    queryFn: () => api.get<T.RecommendationsRead>(`/quotes/${quoteId}/recommendations`),
    enabled: Boolean(quoteId),
  });

/** Everything that edits a DRAFT version and must re-read authoritative totals. */
export const useVersionMutations = (versionId: string, quoteId?: string) => {
  const qc = useQueryClient();
  const after = async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: qk.version(versionId) }),
      qc.invalidateQueries({ queryKey: qk.policyResults(versionId) }),
      qc.invalidateQueries({ queryKey: qk.impact(versionId) }),
      qc.invalidateQueries({ queryKey: qk.versionApproval(versionId) }),
      quoteId ? qc.invalidateQueries({ queryKey: qk.quote(quoteId) }) : null,
      quoteId ? qc.invalidateQueries({ queryKey: qk.recommendations(quoteId) }) : null,
      qc.invalidateQueries({ queryKey: ["quotes"] }),
      ...SIGNALS.map((k) => qc.invalidateQueries({ queryKey: k })),
    ]);
  };

  return {
    addLine: useMutation({
      mutationFn: (body: T.QuoteLineCreate) =>
        api.post(`/quote-versions/${versionId}/lines`, body),
      onSuccess: after,
    }),
    updateLine: useMutation({
      mutationFn: ({ lineId, body }: { lineId: string; body: T.QuoteLineUpdate }) =>
        api.patch(`/quote-versions/${versionId}/lines/${lineId}`, body),
      onSuccess: after,
    }),
    deleteLine: useMutation({
      mutationFn: (lineId: string) => api.del(`/quote-versions/${versionId}/lines/${lineId}`),
      onSuccess: after,
    }),
    setDiscount: useMutation({
      mutationFn: (order_discount_pct: string) =>
        api.patch(`/quote-versions/${versionId}/discount`, { order_discount_pct }),
      onSuccess: after,
    }),
    calculate: useMutation({
      mutationFn: () => api.post<T.QuoteVersionRead>(`/quote-versions/${versionId}/calculate`),
      onSuccess: after,
    }),
    submit: useMutation({
      mutationFn: () => api.post<T.ImpactRead>(`/quote-versions/${versionId}/submit`),
      onSuccess: after,
    }),
    send: useMutation({
      mutationFn: () => api.post(`/quote-versions/${versionId}/send`),
      onSuccess: after,
    }),
    revise: useMutation({
      mutationFn: (body: { reason: string }) =>
        api.post<T.QuoteVersionRead>(`/quote-versions/${versionId}/revisions`, body),
      onSuccess: after,
    }),
    simulate: useMutation({
      mutationFn: (body: T.SimulationRequest) =>
        api.post<T.SimulationResult>(`/quote-versions/${versionId}/simulate`, body),
    }),
  };
};

export const useCreateQuote = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ dealId, body }: { dealId: string; body: T.QuoteCreate }) =>
      api.post<T.QuoteRead>(`/deals/${dealId}/quotes`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["quotes"] }),
  });
};

export const useDismissRecommendation = (quoteId: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (productId: string) =>
      api.post(`/quotes/${quoteId}/recommendations/${productId}/dismiss`),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.recommendations(quoteId) }),
  });
};

export const useLoseQuote = (quoteId: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { reason?: string }) => api.post(`/quotes/${quoteId}/lose`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.quote(quoteId) });
      qc.invalidateQueries({ queryKey: ["quotes"] });
      SIGNALS.forEach((k) => qc.invalidateQueries({ queryKey: k }));
    },
  });
};

/* ========================================================================== */
/* approvals                                                                   */
/* ========================================================================== */
export const useApprovalInbox = (enabled = true) =>
  useQuery({
    queryKey: qk.approvalInbox,
    queryFn: () => api.get<T.ApprovalInboxItem[]>("/approvals/inbox").then(rows),
    enabled,
    refetchInterval: visiblePoll(45_000),
    retry: false,
  });

export const useApproval = (id: string | undefined | null) =>
  useQuery({
    queryKey: qk.approval(id!),
    queryFn: () => api.get<T.ApprovalRequestRead>(`/approvals/${id}`),
    enabled: Boolean(id),
  });

export const useApprovalDecision = (requestId: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ action, reason }: { action: "approve" | "reject" | "request-revision"; reason: string }) =>
      api.post<T.ApprovalActionResponse>(`/approvals/${requestId}/${action}`, { reason }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.approval(requestId) });
      qc.invalidateQueries({ queryKey: qk.approvalInbox });
      qc.invalidateQueries({ queryKey: ["quote-version"] });
      qc.invalidateQueries({ queryKey: ["quotes"] });
      qc.invalidateQueries({ queryKey: ["quote"] });
      SIGNALS.forEach((k) => qc.invalidateQueries({ queryKey: k }));
    },
  });
};

/* ========================================================================== */
/* negotiation (seller side)                                                   */
/* ========================================================================== */
export const useNegotiation = (quoteId: string | undefined | null) =>
  useQuery({
    queryKey: qk.negotiation(quoteId!),
    queryFn: () => api.get<T.NegotiationThreadRead>(`/quotes/${quoteId}/negotiation`),
    enabled: Boolean(quoteId),
  });

export const useSellerReply = (quoteId: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { body: string }) => api.post(`/quotes/${quoteId}/negotiation/reply`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.negotiation(quoteId) }),
  });
};

/* ========================================================================== */
/* orders / inventory                                                          */
/* ========================================================================== */
export const useOrders = (params?: Record<string, unknown>) =>
  useQuery({
    queryKey: qk.orders(params),
    queryFn: () => api.get<T.Page<T.SalesOrderSummary>>("/orders", params as never),
  });

export const useOrder = (id: string | undefined | null) =>
  useQuery({
    queryKey: qk.order(id!),
    queryFn: () => api.get<T.SalesOrderRead>(`/orders/${id}`),
    enabled: Boolean(id),
  });

export const useAllocations = (id: string | undefined | null) =>
  useQuery({
    queryKey: qk.allocations(id!),
    queryFn: () => api.get<T.AllocationLineResult[]>(`/orders/${id}/allocations`).then(rows),
    enabled: Boolean(id),
  });

export const useInventory = () =>
  useQuery({ queryKey: qk.inventory, queryFn: () => api.get<T.InventoryRead[]>("/inventory").then(rows) });

export const useWarehouses = () =>
  useQuery({ queryKey: qk.warehouses, queryFn: () => api.get<T.WarehouseRead[]>("/warehouses").then(rows) });

export const useOrderMutations = (orderId: string) => {
  const qc = useQueryClient();
  const after = () => {
    qc.invalidateQueries({ queryKey: qk.order(orderId) });
    qc.invalidateQueries({ queryKey: qk.allocations(orderId) });
    qc.invalidateQueries({ queryKey: ["orders"] });
    qc.invalidateQueries({ queryKey: qk.inventory });
    SIGNALS.forEach((k) => qc.invalidateQueries({ queryKey: k }));
  };
  return {
    allocate: useMutation({
      mutationFn: ({ body, key }: { body?: T.AllocationRequest; key: string }) =>
        api.post<T.AllocationResult>(`/orders/${orderId}/allocate`, body ?? {}, { idempotencyKey: key }),
      onSuccess: after,
    }),
    fulfill: useMutation({
      mutationFn: () => api.post<T.SalesOrderRead>(`/orders/${orderId}/fulfill`),
      onSuccess: after,
    }),
    deliver: useMutation({
      mutationFn: (fulfillmentId: string) =>
        api.post(`/orders/${orderId}/fulfillments/${fulfillmentId}/deliver`),
      onSuccess: after,
    }),
    cancel: useMutation({
      mutationFn: (body: { reason?: string }) => api.post(`/orders/${orderId}/cancel`, body),
      onSuccess: after,
    }),
    promise: useMutation({
      mutationFn: (promised_delivery_date: string) =>
        api.patch(`/orders/${orderId}/promise`, { promised_delivery_date }),
      onSuccess: after,
    }),
  };
};

/* ========================================================================== */
/* billing                                                                     */
/* ========================================================================== */
export const useSchedules = (params?: Record<string, unknown>) =>
  useQuery({
    queryKey: qk.schedules(params),
    queryFn: () => api.get<T.BillingScheduleRead[]>("/billing/schedules", params as never).then(rows),
  });

export const useBillingSummary = (orderId: string | undefined | null) =>
  useQuery({
    queryKey: qk.billingSummary(orderId!),
    queryFn: () => api.get<T.BillingSummaryRead>(`/billing/orders/${orderId}/summary`),
    enabled: Boolean(orderId),
  });

export const useInvoices = (params?: Record<string, unknown>) =>
  useQuery({
    queryKey: qk.invoices(params),
    queryFn: () => api.get<T.InvoiceRead[]>("/billing/invoices", params as never).then(rows),
  });

export const useCreditNotes = () =>
  useQuery({
    queryKey: qk.creditNotes,
    queryFn: () => api.get<T.CreditNoteRead[]>("/billing/credit-notes").then(rows),
  });

export const useBillingMutations = () => {
  const qc = useQueryClient();
  const after = () => {
    qc.invalidateQueries({ queryKey: ["billing"] });
    SIGNALS.forEach((k) => qc.invalidateQueries({ queryKey: k }));
  };
  return {
    issueInvoice: useMutation({
      mutationFn: (body: T.InvoiceCreate) => api.post<T.InvoiceRead>("/billing/invoices", body),
      onSuccess: after,
    }),
    recordPayment: useMutation({
      mutationFn: ({ invoiceId, body }: { invoiceId: string; body: T.PaymentCreate }) =>
        api.post<T.PaymentRead>(`/billing/invoices/${invoiceId}/payments`, body),
      onSuccess: after,
    }),
    voidInvoice: useMutation({
      mutationFn: ({ invoiceId, reason }: { invoiceId: string; reason: string }) =>
        api.post(`/billing/invoices/${invoiceId}/void`, { reason }),
      onSuccess: after,
    }),
    cancelSubscription: useMutation({
      mutationFn: ({ scheduleId, body }: { scheduleId: string; body: Record<string, unknown> }) =>
        api.post<T.SubscriptionChangeResult>(`/billing/subscriptions/${scheduleId}/cancel`, body),
      onSuccess: after,
    }),
    changeSubscription: useMutation({
      mutationFn: ({ scheduleId, body }: { scheduleId: string; body: Record<string, unknown> }) =>
        api.post<T.SubscriptionChangeResult>(`/billing/subscriptions/${scheduleId}/change`, body),
      onSuccess: after,
    }),
  };
};

/* ========================================================================== */
/* catalogue + governance                                                      */
/* ========================================================================== */
export const useProducts = (params?: Record<string, unknown>) =>
  useQuery({
    queryKey: qk.products(params),
    queryFn: () => api.get<T.Page<T.ProductRead>>("/products", params as never),
  });

export const useProduct = (id: string | undefined | null) =>
  useQuery({
    queryKey: qk.product(id!),
    queryFn: () => api.get<T.ProductRead>(`/products/${id}`),
    enabled: Boolean(id),
  });

export const useVariants = (enabled = true) =>
  useQuery({
    queryKey: qk.variants,
    queryFn: () => api.get<T.ProductVariantRead[]>("/admin/product-variants").then(rows),
    enabled,
    retry: false,
  });

export const usePriceLists = (enabled = true) =>
  useQuery({
    queryKey: qk.priceLists,
    queryFn: () => api.get<T.PriceListRead[]>("/admin/price-lists").then(rows),
    enabled,
    retry: false,
  });

export const usePolicies = () =>
  useQuery({ queryKey: qk.policies, queryFn: () => api.get<T.PolicyRead[]>("/policies").then(rows) });

export const useSettings = (enabled = true) =>
  useQuery({
    queryKey: qk.settings,
    queryFn: () => api.get<T.OrganizationSettingsRead>("/admin/settings"),
    enabled,
    retry: false,
  });

export const useSalesTeams = (enabled = true) =>
  useQuery({
    queryKey: qk.salesTeams,
    queryFn: () => api.get<T.SalesTeamRead[]>("/admin/sales-teams").then(rows),
    enabled,
    retry: false,
  });

export const useAdminMutations = () => {
  const qc = useQueryClient();
  return {
    createProduct: useMutation({
      mutationFn: (body: T.ProductCreate) => api.post<T.ProductRead>("/admin/products", body),
      onSuccess: () => qc.invalidateQueries({ queryKey: ["products"] }),
    }),
    updateProduct: useMutation({
      mutationFn: ({ id, body }: { id: string; body: T.ProductUpdate }) =>
        api.patch<T.ProductRead>(`/admin/products/${id}`, body),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ["products"] });
        qc.invalidateQueries({ queryKey: ["product"] });
      },
    }),
    createPolicy: useMutation({
      mutationFn: (body: T.PolicyCreate) => api.post<T.PolicyRead>("/admin/policies", body),
      onSuccess: () => qc.invalidateQueries({ queryKey: qk.policies }),
    }),
    updatePolicy: useMutation({
      mutationFn: ({ id, body }: { id: string; body: T.PolicyUpdate }) =>
        api.patch<T.PolicyRead>(`/admin/policies/${id}`, body),
      onSuccess: () => qc.invalidateQueries({ queryKey: qk.policies }),
    }),
    createWarehouse: useMutation({
      mutationFn: (body: T.WarehouseCreate) => api.post<T.WarehouseRead>("/admin/warehouses", body),
      onSuccess: () => qc.invalidateQueries({ queryKey: qk.warehouses }),
    }),
    updateWarehouse: useMutation({
      mutationFn: ({ id, body }: { id: string; body: T.WarehouseUpdate }) =>
        api.patch<T.WarehouseRead>(`/admin/warehouses/${id}`, body),
      onSuccess: () => qc.invalidateQueries({ queryKey: qk.warehouses }),
    }),
    updateSettings: useMutation({
      mutationFn: (body: T.OrganizationSettingsUpdate) =>
        api.patch<T.OrganizationSettingsRead>("/admin/settings", body),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: qk.settings });
        SIGNALS.forEach((k) => qc.invalidateQueries({ queryKey: k }));
      },
    }),
    setInventory: useMutation({
      mutationFn: (body: Record<string, unknown>) => api.post("/admin/inventory", body),
      onSuccess: () => qc.invalidateQueries({ queryKey: qk.inventory }),
    }),
    adjustInventory: useMutation({
      mutationFn: (body: Record<string, unknown>) => api.post("/admin/inventory/adjust", body),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: qk.inventory });
        qc.invalidateQueries({ queryKey: ["orders"] });
        SIGNALS.forEach((k) => qc.invalidateQueries({ queryKey: k }));
      },
    }),
    createUser: useMutation({
      mutationFn: (body: T.UserCreate) => api.post<T.UserRead>("/users", body),
      onSuccess: () => qc.invalidateQueries({ queryKey: qk.users }),
    }),
  };
};

/* ========================================================================== */
/* audit + reports                                                             */
/* ========================================================================== */
export const useAuditEvents = (params?: Record<string, unknown>) =>
  useQuery({
    queryKey: qk.audit(params),
    queryFn: () => api.get<T.Page<T.AuditEventRead>>("/audit/events", params as never),
  });

export const useQuoteTimeline = (quoteId: string | undefined | null) =>
  useQuery({
    queryKey: qk.quoteTimeline(quoteId!),
    queryFn: () => api.get<T.AuditEventRead[]>(`/audit/quotes/${quoteId}/timeline`).then(rows),
    enabled: Boolean(quoteId),
  });

export const useReport = <R>(name: string, params?: Record<string, unknown>, enabled = true) =>
  useQuery({
    queryKey: qk.report(name, params),
    queryFn: () => api.get<R>(`/reports/${name}`, params as never),
    enabled,
  });

/* ========================================================================== */
/* customer portal                                                             */
/* ========================================================================== */
export const usePortalQuotes = () =>
  useQuery({
    queryKey: qk.portalQuotes,
    queryFn: () => api.get<T.PortalQuoteListItem[]>("/portal/quotes").then(rows),
  });

export const usePortalQuote = (id: string | undefined | null) =>
  useQuery({
    queryKey: qk.portalQuote(id!),
    queryFn: () => api.get<T.PortalQuoteRead>(`/portal/quotes/${id}`),
    enabled: Boolean(id),
  });

export const usePortalMessages = (id: string | undefined | null) =>
  useQuery({
    queryKey: qk.portalMessages(id!),
    queryFn: () => api.get<T.NegotiationThreadRead>(`/portal/quotes/${id}/messages`),
    enabled: Boolean(id),
  });

export const usePortalMutations = (quoteId: string) => {
  const qc = useQueryClient();
  const after = () => {
    qc.invalidateQueries({ queryKey: qk.portalQuote(quoteId) });
    qc.invalidateQueries({ queryKey: qk.portalMessages(quoteId) });
    qc.invalidateQueries({ queryKey: qk.portalQuotes });
  };
  return {
    sendMessage: useMutation({
      mutationFn: (body: T.PortalMessageCreate) =>
        api.post<T.CounterOfferOutcome>(`/portal/quotes/${quoteId}/messages`, body),
      onSuccess: after,
    }),
    confirm: useMutation({
      mutationFn: (key: string) =>
        api.post<T.ConfirmationResult>(`/portal/quotes/${quoteId}/confirm`, {}, { idempotencyKey: key }),
      onSuccess: after,
    }),
  };
};
