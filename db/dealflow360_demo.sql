--
-- PostgreSQL database dump
--

\restrict 6UrunfRJyGCLYh2SJsLbCqrHFrMa1Afk1XeywrbV3Mlcw2HG74BMEXlOnRRFNPQ

-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: approval_decisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.approval_decisions (
    approval_request_id uuid NOT NULL,
    approval_step_id uuid NOT NULL,
    quote_version_id uuid NOT NULL,
    decision character varying(48) NOT NULL,
    actor_user_id uuid NOT NULL,
    actor_role character varying(48) NOT NULL,
    actor_email character varying(255) NOT NULL,
    reason text NOT NULL,
    decision_snapshot jsonb NOT NULL,
    decided_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: approval_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.approval_requests (
    quote_id uuid NOT NULL,
    quote_version_id uuid NOT NULL,
    status character varying(48) NOT NULL,
    requested_by_user_id uuid NOT NULL,
    reason text NOT NULL,
    required_levels jsonb NOT NULL,
    policy_summary jsonb NOT NULL,
    blended_risk_score numeric(9,4) NOT NULL,
    current_step_sequence integer NOT NULL,
    decided_at timestamp with time zone,
    stale_at timestamp with time zone,
    stale_reason text,
    superseded_by_request_id uuid,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: approval_steps; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.approval_steps (
    approval_request_id uuid NOT NULL,
    sequence integer NOT NULL,
    level character varying(48) NOT NULL,
    required_role character varying(48) NOT NULL,
    status character varying(48) NOT NULL,
    reason text NOT NULL,
    assigned_user_id uuid,
    decided_by_user_id uuid,
    decision_reason text,
    decided_at timestamp with time zone,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT ck_approval_steps_sequence_positive CHECK ((sequence >= 1))
);


--
-- Name: attention_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.attention_items (
    source_type character varying(64) NOT NULL,
    source_id uuid NOT NULL,
    type character varying(48) NOT NULL,
    severity character varying(48) NOT NULL,
    title character varying(255) NOT NULL,
    reason text NOT NULL,
    impact text NOT NULL,
    recommended_action text NOT NULL,
    owner_role character varying(48) NOT NULL,
    owner_user_id uuid,
    status character varying(48) NOT NULL,
    deal_id uuid,
    quote_id uuid,
    detail jsonb NOT NULL,
    resolved_at timestamp with time zone,
    resolved_by_user_id uuid,
    resolution_note text,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    acknowledged_at timestamp with time zone,
    acknowledged_by_user_id uuid,
    nudge_count integer DEFAULT 0 NOT NULL,
    last_nudged_at timestamp with time zone,
    last_nudged_by_user_id uuid,
    escalated_at timestamp with time zone,
    escalated_by_user_id uuid,
    escalation_note text
);


--
-- Name: audit_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_events (
    sequence bigint NOT NULL,
    organization_id uuid,
    event_type character varying(64) NOT NULL,
    entity_type character varying(64) NOT NULL,
    entity_id uuid,
    actor_user_id uuid,
    actor_role character varying(48),
    actor_email character varying(255),
    payload jsonb NOT NULL,
    ip_address character varying(64),
    occurred_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: audit_events_sequence_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.audit_events ALTER COLUMN sequence ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.audit_events_sequence_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: billing_schedules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.billing_schedules (
    schedule_number character varying(64) NOT NULL,
    sales_order_id uuid NOT NULL,
    sales_order_line_id uuid,
    billing_type character varying(48) NOT NULL,
    recurring_interval character varying(48),
    status character varying(48) NOT NULL,
    currency character varying(3) NOT NULL,
    amount numeric(18,2) NOT NULL,
    tax_amount numeric(18,2) NOT NULL,
    total_amount numeric(18,2) NOT NULL,
    period_number integer NOT NULL,
    total_periods integer NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    due_date date NOT NULL,
    is_prorated boolean NOT NULL,
    proration_factor numeric(12,8) NOT NULL,
    description character varying(255) NOT NULL,
    detail jsonb NOT NULL,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT ck_billing_schedules_amount_non_negative CHECK ((amount >= (0)::numeric)),
    CONSTRAINT ck_billing_schedules_period_number_positive CHECK ((period_number >= 1)),
    CONSTRAINT ck_billing_schedules_recurring_requires_interval CHECK (((((billing_type)::text = 'RECURRING'::text) AND (recurring_interval IS NOT NULL)) OR (((billing_type)::text = 'ONE_TIME'::text) AND (recurring_interval IS NULL)))),
    CONSTRAINT ck_billing_schedules_total_periods_positive CHECK ((total_periods >= 1))
);


--
-- Name: commercial_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commercial_snapshots (
    quote_version_id uuid NOT NULL,
    gross_revenue numeric(18,2) NOT NULL,
    total_discount numeric(18,2) NOT NULL,
    revenue numeric(18,2) NOT NULL,
    tax_amount numeric(18,2) NOT NULL,
    cost numeric(18,2) NOT NULL,
    margin numeric(18,2) NOT NULL,
    margin_pct numeric(9,4) NOT NULL,
    effective_discount_pct numeric(9,4) NOT NULL,
    one_time_revenue numeric(18,2) NOT NULL,
    recurring_revenue numeric(18,2) NOT NULL,
    blended_risk_score numeric(9,4) NOT NULL,
    payment_terms character varying(48) NOT NULL,
    customer_tier character varying(48) NOT NULL,
    snapshot_json jsonb NOT NULL,
    is_current boolean NOT NULL,
    calculated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: contacts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contacts (
    customer_organization_id uuid,
    user_id uuid,
    first_name character varying(128) NOT NULL,
    last_name character varying(128),
    email character varying(255) NOT NULL,
    phone character varying(32),
    title character varying(128),
    is_primary boolean NOT NULL,
    is_active boolean NOT NULL,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: credit_notes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.credit_notes (
    credit_note_number character varying(64) NOT NULL,
    sales_order_id uuid NOT NULL,
    invoice_id uuid,
    billing_schedule_id uuid,
    customer_organization_id uuid NOT NULL,
    status character varying(48) NOT NULL,
    reason character varying(48) NOT NULL,
    reason_note text,
    currency character varying(3) NOT NULL,
    subtotal numeric(18,2) NOT NULL,
    tax_amount numeric(18,2) NOT NULL,
    total_amount numeric(18,2) NOT NULL,
    amount_refunded numeric(18,2) NOT NULL,
    issue_date date NOT NULL,
    issued_by_user_id uuid,
    voided_at timestamp with time zone,
    detail jsonb NOT NULL,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT ck_credit_notes_amount_refunded_within_total CHECK (((amount_refunded >= (0)::numeric) AND (amount_refunded <= total_amount))),
    CONSTRAINT ck_credit_notes_subtotal_non_negative CHECK ((subtotal >= (0)::numeric)),
    CONSTRAINT ck_credit_notes_tax_amount_non_negative CHECK ((tax_amount >= (0)::numeric)),
    CONSTRAINT ck_credit_notes_total_amount_non_negative CHECK ((total_amount >= (0)::numeric))
);


--
-- Name: customer_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.customer_profiles (
    customer_organization_id uuid NOT NULL,
    primary_contact_id uuid,
    display_name character varying(255) NOT NULL,
    tier character varying(48) NOT NULL,
    payment_terms character varying(48) NOT NULL,
    currency character varying(3) NOT NULL,
    credit_limit numeric(18,2) NOT NULL,
    credit_used numeric(18,2) NOT NULL,
    tax_rate_pct numeric(9,4) NOT NULL,
    is_active boolean NOT NULL,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT ck_customer_profiles_credit_limit_non_negative CHECK ((credit_limit >= (0)::numeric))
);


--
-- Name: deals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.deals (
    reference character varying(64) NOT NULL,
    name character varying(255) NOT NULL,
    customer_profile_id uuid NOT NULL,
    owner_user_id uuid NOT NULL,
    primary_contact_id uuid,
    stage character varying(48) NOT NULL,
    currency character varying(3) NOT NULL,
    expected_value numeric(18,2) NOT NULL,
    expected_close_date date,
    notes text,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: decision_impacts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.decision_impacts (
    quote_id uuid NOT NULL,
    quote_version_id uuid NOT NULL,
    previous_version_id uuid,
    quote_line_id uuid,
    product_id uuid,
    changed_field character varying(64) NOT NULL,
    subject character varying(255),
    old_value jsonb,
    new_value jsonb,
    material boolean NOT NULL,
    severity character varying(48) NOT NULL,
    change_reason text NOT NULL,
    affected_entity_type character varying(64),
    affected_entity_id uuid,
    action_required character varying(64),
    detected_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: dismissed_recommendations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dismissed_recommendations (
    quote_version_id uuid NOT NULL,
    product_id uuid NOT NULL,
    dismissed_by_user_id uuid,
    note text,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: fulfillments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fulfillments (
    fulfillment_number character varying(64) NOT NULL,
    sales_order_id uuid NOT NULL,
    warehouse_id uuid NOT NULL,
    shipment_sequence integer NOT NULL,
    status character varying(48) NOT NULL,
    carrier character varying(128),
    tracking_number character varying(128),
    shipping_cost numeric(18,2) NOT NULL,
    shipped_at timestamp with time zone,
    delivered_at timestamp with time zone,
    notes text,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: idempotency_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.idempotency_keys (
    key character varying(128) NOT NULL,
    endpoint character varying(255) NOT NULL,
    method character varying(64) NOT NULL,
    request_hash character varying(128) NOT NULL,
    status character varying(48) NOT NULL,
    user_id uuid,
    entity_type character varying(64),
    entity_id uuid,
    response_status_code integer,
    response_body jsonb,
    completed_at timestamp with time zone,
    expires_at timestamp with time zone,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: inventory; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.inventory (
    warehouse_id uuid NOT NULL,
    product_id uuid NOT NULL,
    product_variant_id uuid,
    quantity_on_hand numeric(18,4) NOT NULL,
    quantity_reserved numeric(18,4) NOT NULL,
    quantity_inbound numeric(18,4) NOT NULL,
    reorder_point numeric(18,4) NOT NULL,
    expected_restock_at timestamp with time zone,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT ck_inventory_no_over_reservation CHECK ((quantity_reserved <= quantity_on_hand)),
    CONSTRAINT ck_inventory_quantity_on_hand_non_negative CHECK ((quantity_on_hand >= (0)::numeric)),
    CONSTRAINT ck_inventory_quantity_reserved_non_negative CHECK ((quantity_reserved >= (0)::numeric))
);


--
-- Name: inventory_allocations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.inventory_allocations (
    sales_order_id uuid NOT NULL,
    sales_order_line_id uuid NOT NULL,
    product_id uuid NOT NULL,
    warehouse_id uuid,
    inventory_id uuid,
    fulfillment_id uuid,
    quantity numeric(18,4) NOT NULL,
    status character varying(48) NOT NULL,
    mode character varying(48) NOT NULL,
    allocated_by_user_id uuid,
    allocated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    released_at timestamp with time zone,
    expected_available_at timestamp with time zone,
    notes text,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT ck_inventory_allocations_backorder_has_no_warehouse CHECK (((((status)::text = 'BACKORDERED'::text) AND (warehouse_id IS NULL)) OR (((status)::text <> 'BACKORDERED'::text) AND (warehouse_id IS NOT NULL)))),
    CONSTRAINT ck_inventory_allocations_quantity_positive CHECK ((quantity > (0)::numeric))
);


--
-- Name: invoices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.invoices (
    invoice_number character varying(64) NOT NULL,
    sales_order_id uuid NOT NULL,
    billing_schedule_id uuid,
    customer_organization_id uuid NOT NULL,
    status character varying(48) NOT NULL,
    currency character varying(3) NOT NULL,
    subtotal numeric(18,2) NOT NULL,
    tax_amount numeric(18,2) NOT NULL,
    total_amount numeric(18,2) NOT NULL,
    amount_paid numeric(18,2) NOT NULL,
    issue_date date NOT NULL,
    due_date date NOT NULL,
    paid_at timestamp with time zone,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT ck_invoices_amount_paid_non_negative CHECK ((amount_paid >= (0)::numeric)),
    CONSTRAINT ck_invoices_amount_paid_not_over_total CHECK ((amount_paid <= total_amount))
);


--
-- Name: negotiation_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.negotiation_messages (
    thread_id uuid NOT NULL,
    quote_version_id uuid NOT NULL,
    quote_line_id uuid,
    author_user_id uuid,
    author_kind character varying(48) NOT NULL,
    author_display_name character varying(255) NOT NULL,
    message_type character varying(48) NOT NULL,
    body text NOT NULL,
    requested_discount_pct numeric(9,4),
    requested_quantity numeric(18,4),
    requested_unit_price numeric(18,4),
    payload jsonb NOT NULL,
    triggered_version_id uuid,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT ck_negotiation_messages_requested_discount_pct_range CHECK (((requested_discount_pct IS NULL) OR ((requested_discount_pct >= (0)::numeric) AND (requested_discount_pct <= (100)::numeric)))),
    CONSTRAINT ck_negotiation_messages_requested_quantity_positive CHECK (((requested_quantity IS NULL) OR (requested_quantity > (0)::numeric)))
);


--
-- Name: negotiation_threads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.negotiation_threads (
    quote_id uuid NOT NULL,
    customer_organization_id uuid NOT NULL,
    quote_version_id uuid NOT NULL,
    subject character varying(255) NOT NULL,
    status character varying(48) NOT NULL,
    opened_by_user_id uuid,
    message_count integer NOT NULL,
    last_message_at timestamp with time zone,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: organization_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organization_settings (
    organization_id uuid NOT NULL,
    finance_escalation_threshold numeric(9,4) DEFAULT 60.0 NOT NULL,
    risk_discount_overage_weight numeric(9,4) DEFAULT 3.0 NOT NULL,
    risk_breadth_weight numeric(9,4) DEFAULT 5.0 NOT NULL,
    risk_margin_weight numeric(9,4) DEFAULT 5.0 NOT NULL,
    risk_depth_weight numeric(9,4) DEFAULT 0.4 NOT NULL,
    stalled_deal_days integer DEFAULT 14 NOT NULL,
    discount_anomaly_sigma numeric(9,4) DEFAULT 2.0 NOT NULL,
    discount_anomaly_min_samples integer DEFAULT 5 NOT NULL,
    approval_sla_hours integer DEFAULT 24 NOT NULL,
    recommendation_min_margin_pct numeric(9,4) DEFAULT 0.0 NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT ck_organization_settings_anomaly_min_samples_meaningful CHECK ((discount_anomaly_min_samples >= 2)),
    CONSTRAINT ck_organization_settings_anomaly_sigma_positive CHECK ((discount_anomaly_sigma > (0)::numeric)),
    CONSTRAINT ck_organization_settings_approval_sla_positive CHECK ((approval_sla_hours >= 1)),
    CONSTRAINT ck_organization_settings_stalled_deal_days_positive CHECK ((stalled_deal_days >= 1))
);


--
-- Name: organizations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organizations (
    name character varying(255) NOT NULL,
    slug character varying(64) NOT NULL,
    kind character varying(48) NOT NULL,
    domain character varying(255),
    country character varying(64),
    currency character varying(3) NOT NULL,
    is_active boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: payments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.payments (
    payment_number character varying(64) NOT NULL,
    invoice_id uuid NOT NULL,
    amount numeric(18,2) NOT NULL,
    currency character varying(3) NOT NULL,
    method character varying(48) NOT NULL,
    status character varying(48) NOT NULL,
    reference character varying(128),
    notes text,
    received_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    recorded_by_user_id uuid,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT ck_payments_amount_positive CHECK ((amount > (0)::numeric))
);


--
-- Name: policies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.policies (
    code character varying(64) NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    policy_type character varying(48) NOT NULL,
    customer_tier character varying(48),
    product_category character varying(48),
    customer_profile_id uuid,
    threshold_value numeric(18,4) NOT NULL,
    comparison character varying(48) NOT NULL,
    unit character varying(48) NOT NULL,
    required_action character varying(48) NOT NULL,
    severity character varying(48) NOT NULL,
    priority integer NOT NULL,
    is_active boolean NOT NULL,
    effective_from date,
    effective_to date,
    config jsonb NOT NULL,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: policy_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.policy_results (
    quote_version_id uuid NOT NULL,
    policy_id uuid,
    quote_line_id uuid,
    rule character varying(64) NOT NULL,
    status character varying(48) NOT NULL,
    subject character varying(255),
    actual_value numeric(18,4) NOT NULL,
    threshold_value numeric(18,4) NOT NULL,
    overage_points numeric(18,4) NOT NULL,
    unit character varying(48) NOT NULL,
    scope_category character varying(48),
    scope_tier character varying(48),
    reason text NOT NULL,
    required_action character varying(48),
    severity character varying(48) NOT NULL,
    risk_contribution numeric(9,4) NOT NULL,
    detail jsonb NOT NULL,
    evaluated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: price_lists; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.price_lists (
    code character varying(64) NOT NULL,
    name character varying(255) NOT NULL,
    tier character varying(48),
    currency character varying(3) NOT NULL,
    rules jsonb NOT NULL,
    valid_from date,
    valid_to date,
    is_active boolean NOT NULL,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: product_variants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.product_variants (
    product_id uuid NOT NULL,
    sku character varying(64) NOT NULL,
    name character varying(255) NOT NULL,
    attributes jsonb NOT NULL,
    price_delta numeric(18,4) NOT NULL,
    cost_delta numeric(18,4) NOT NULL,
    is_active boolean NOT NULL,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: products; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.products (
    sku character varying(64) NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    category character varying(48) NOT NULL,
    list_price numeric(18,4) NOT NULL,
    internal_cost numeric(18,4) NOT NULL,
    tax_rate_pct numeric(9,4) NOT NULL,
    uom character varying(32) NOT NULL,
    billing_type character varying(48) NOT NULL,
    recurring_interval character varying(48),
    default_recurring_periods integer NOT NULL,
    is_stock_tracked boolean NOT NULL,
    is_active boolean NOT NULL,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    is_promoted boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_products_internal_cost_non_negative CHECK ((internal_cost >= (0)::numeric)),
    CONSTRAINT ck_products_list_price_non_negative CHECK ((list_price >= (0)::numeric))
);


--
-- Name: quote_lines; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.quote_lines (
    quote_version_id uuid NOT NULL,
    product_id uuid NOT NULL,
    product_variant_id uuid,
    line_number integer NOT NULL,
    description character varying(255) NOT NULL,
    notes text,
    category character varying(48) NOT NULL,
    quantity numeric(18,4) NOT NULL,
    unit_list_price numeric(18,4) NOT NULL,
    unit_cost numeric(18,4) NOT NULL,
    discount_pct numeric(9,4) NOT NULL,
    tax_rate_pct numeric(9,4) NOT NULL,
    billing_type character varying(48) NOT NULL,
    recurring_interval character varying(48),
    recurring_periods integer NOT NULL,
    is_stock_tracked boolean NOT NULL,
    unit_net_price numeric(18,4) NOT NULL,
    gross_amount numeric(18,2) NOT NULL,
    discount_amount numeric(18,2) NOT NULL,
    net_amount numeric(18,2) NOT NULL,
    tax_amount numeric(18,2) NOT NULL,
    total_amount numeric(18,2) NOT NULL,
    line_cost numeric(18,2) NOT NULL,
    line_margin numeric(18,2) NOT NULL,
    line_margin_pct numeric(9,4) NOT NULL,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    source_line_id uuid,
    order_discount_amount numeric(18,2) DEFAULT 0 NOT NULL,
    effective_discount_pct numeric(9,4) DEFAULT 0 NOT NULL,
    CONSTRAINT ck_quote_lines_discount_pct_range CHECK (((discount_pct >= (0)::numeric) AND (discount_pct <= (100)::numeric))),
    CONSTRAINT ck_quote_lines_quantity_positive CHECK ((quantity > (0)::numeric)),
    CONSTRAINT ck_quote_lines_recurring_periods_positive CHECK ((recurring_periods >= 1)),
    CONSTRAINT ck_quote_lines_unit_cost_non_negative CHECK ((unit_cost >= (0)::numeric)),
    CONSTRAINT ck_quote_lines_unit_list_price_non_negative CHECK ((unit_list_price >= (0)::numeric))
);


--
-- Name: quote_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.quote_versions (
    quote_id uuid NOT NULL,
    version_number integer NOT NULL,
    parent_version_id uuid,
    status character varying(48) NOT NULL,
    source character varying(48) NOT NULL,
    revision_reason text,
    created_by_user_id uuid NOT NULL,
    currency character varying(3) NOT NULL,
    payment_terms character varying(48) NOT NULL,
    valid_until date,
    gross_revenue numeric(18,2) NOT NULL,
    total_discount numeric(18,2) NOT NULL,
    net_revenue numeric(18,2) NOT NULL,
    tax_amount numeric(18,2) NOT NULL,
    total_revenue numeric(18,2) NOT NULL,
    total_cost numeric(18,2) NOT NULL,
    margin numeric(18,2) NOT NULL,
    margin_pct numeric(9,4) NOT NULL,
    effective_discount_pct numeric(9,4) NOT NULL,
    one_time_revenue numeric(18,2) NOT NULL,
    recurring_revenue numeric(18,2) NOT NULL,
    blended_risk_score numeric(9,4) NOT NULL,
    risk_band character varying(48) NOT NULL,
    requires_approval boolean NOT NULL,
    is_stale boolean NOT NULL,
    stale_reason text,
    calculated_at timestamp with time zone,
    submitted_at timestamp with time zone,
    approved_at timestamp with time zone,
    sent_at timestamp with time zone,
    confirmed_at timestamp with time zone,
    rejected_at timestamp with time zone,
    superseded_at timestamp with time zone,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    order_discount_pct numeric(9,4) DEFAULT 0 NOT NULL,
    order_discount_amount numeric(18,2) DEFAULT 0 NOT NULL,
    CONSTRAINT ck_quote_versions_version_number_positive CHECK ((version_number >= 1))
);


--
-- Name: quotes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.quotes (
    quote_number character varying(64) NOT NULL,
    title character varying(255) NOT NULL,
    deal_id uuid NOT NULL,
    created_by_user_id uuid NOT NULL,
    status character varying(48) NOT NULL,
    current_version_number integer NOT NULL,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roles (
    code character varying(48) NOT NULL,
    name character varying(128) NOT NULL,
    description text,
    is_internal boolean NOT NULL,
    can_approve boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: sales_order_lines; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sales_order_lines (
    sales_order_id uuid NOT NULL,
    quote_line_id uuid NOT NULL,
    product_id uuid NOT NULL,
    line_number integer NOT NULL,
    description character varying(255) NOT NULL,
    category character varying(48) NOT NULL,
    quantity numeric(18,4) NOT NULL,
    unit_list_price numeric(18,4) NOT NULL,
    unit_net_price numeric(18,4) NOT NULL,
    unit_cost numeric(18,4) NOT NULL,
    discount_pct numeric(9,4) NOT NULL,
    discount_amount numeric(18,2) NOT NULL,
    gross_amount numeric(18,2) NOT NULL,
    net_amount numeric(18,2) NOT NULL,
    tax_amount numeric(18,2) NOT NULL,
    total_amount numeric(18,2) NOT NULL,
    line_cost numeric(18,2) NOT NULL,
    billing_type character varying(48) NOT NULL,
    recurring_interval character varying(48),
    recurring_periods integer NOT NULL,
    is_stock_tracked boolean NOT NULL,
    quantity_allocated numeric(18,4) NOT NULL,
    quantity_backordered numeric(18,4) NOT NULL,
    quantity_fulfilled numeric(18,4) NOT NULL,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    promised_delivery_date date,
    CONSTRAINT ck_sales_order_lines_quantity_allocated_within_bounds CHECK (((quantity_allocated >= (0)::numeric) AND (quantity_allocated <= quantity))),
    CONSTRAINT ck_sales_order_lines_quantity_backordered_non_negative CHECK ((quantity_backordered >= (0)::numeric)),
    CONSTRAINT ck_sales_order_lines_quantity_fulfilled_within_bounds CHECK (((quantity_fulfilled >= (0)::numeric) AND (quantity_fulfilled <= quantity))),
    CONSTRAINT ck_sales_order_lines_quantity_positive CHECK ((quantity > (0)::numeric))
);


--
-- Name: sales_orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sales_orders (
    order_number character varying(64) NOT NULL,
    deal_id uuid NOT NULL,
    quote_id uuid NOT NULL,
    quote_version_id uuid NOT NULL,
    customer_profile_id uuid NOT NULL,
    customer_organization_id uuid NOT NULL,
    status character varying(48) NOT NULL,
    currency character varying(3) NOT NULL,
    payment_terms character varying(48) NOT NULL,
    gross_revenue numeric(18,2) NOT NULL,
    total_discount numeric(18,2) NOT NULL,
    subtotal numeric(18,2) NOT NULL,
    tax_amount numeric(18,2) NOT NULL,
    total_amount numeric(18,2) NOT NULL,
    total_cost numeric(18,2) NOT NULL,
    margin numeric(18,2) NOT NULL,
    margin_pct numeric(9,4) NOT NULL,
    one_time_amount numeric(18,2) NOT NULL,
    recurring_amount numeric(18,2) NOT NULL,
    confirmed_by_user_id uuid NOT NULL,
    confirmed_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    fully_allocated boolean NOT NULL,
    has_backorder boolean NOT NULL,
    allocated_at timestamp with time zone,
    fulfilled_at timestamp with time zone,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    promised_delivery_date date
);


--
-- Name: sales_team_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sales_team_members (
    sales_team_id uuid NOT NULL,
    user_id uuid NOT NULL,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: sales_teams; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sales_teams (
    code character varying(64) NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    manager_user_id uuid,
    region character varying(128),
    is_active boolean DEFAULT true NOT NULL,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    email character varying(255) NOT NULL,
    hashed_password character varying(255) NOT NULL,
    full_name character varying(255) NOT NULL,
    phone character varying(32),
    role_id uuid NOT NULL,
    is_active boolean NOT NULL,
    last_login_at timestamp with time zone,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);


--
-- Name: warehouses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.warehouses (
    code character varying(64) NOT NULL,
    name character varying(255) NOT NULL,
    region character varying(128),
    address_line1 character varying(255),
    city character varying(128),
    country character varying(64),
    postal_code character varying(64),
    priority integer NOT NULL,
    shipping_cost_per_shipment numeric(18,2) NOT NULL,
    is_active boolean NOT NULL,
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT ck_warehouses_shipping_cost_non_negative CHECK ((shipping_cost_per_shipment >= (0)::numeric))
);


--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.alembic_version (version_num) FROM stdin;
7b431beeb960
\.


--
-- Data for Name: approval_decisions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.approval_decisions (approval_request_id, approval_step_id, quote_version_id, decision, actor_user_id, actor_role, actor_email, reason, decision_snapshot, decided_at, id, organization_id, created_at) FROM stdin;
\.


--
-- Data for Name: approval_requests; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.approval_requests (quote_id, quote_version_id, status, requested_by_user_id, reason, required_levels, policy_summary, blended_risk_score, current_step_sequence, decided_at, stale_at, stale_reason, superseded_by_request_id, id, organization_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: approval_steps; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.approval_steps (approval_request_id, sequence, level, required_role, status, reason, assigned_user_id, decided_by_user_id, decision_reason, decided_at, id, organization_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: attention_items; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.attention_items (source_type, source_id, type, severity, title, reason, impact, recommended_action, owner_role, owner_user_id, status, deal_id, quote_id, detail, resolved_at, resolved_by_user_id, resolution_note, id, organization_id, created_at, updated_at, acknowledged_at, acknowledged_by_user_id, nudge_count, last_nudged_at, last_nudged_by_user_id, escalated_at, escalated_by_user_id, escalation_note) FROM stdin;
\.


--
-- Data for Name: audit_events; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.audit_events (sequence, organization_id, event_type, entity_type, entity_id, actor_user_id, actor_role, actor_email, payload, ip_address, occurred_at, id, created_at) FROM stdin;
\.


--
-- Data for Name: billing_schedules; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.billing_schedules (schedule_number, sales_order_id, sales_order_line_id, billing_type, recurring_interval, status, currency, amount, tax_amount, total_amount, period_number, total_periods, period_start, period_end, due_date, is_prorated, proration_factor, description, detail, id, organization_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: commercial_snapshots; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.commercial_snapshots (quote_version_id, gross_revenue, total_discount, revenue, tax_amount, cost, margin, margin_pct, effective_discount_pct, one_time_revenue, recurring_revenue, blended_risk_score, payment_terms, customer_tier, snapshot_json, is_current, calculated_at, id, organization_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: contacts; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.contacts (customer_organization_id, user_id, first_name, last_name, email, phone, title, is_primary, is_active, id, organization_id, created_at, updated_at) FROM stdin;
e7e94765-386b-41d3-9e35-82744e1ad7a2	f9b28ee6-2804-4138-a99d-3a7afabaa4e3	Casey	Nolan	customer@acme.com	\N	Head of IT Procurement	t	t	beebb8d6-6b6c-4a1f-94a5-b383d42a6e2c	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.130555+00	2026-09-06 07:51:41.130557+00
\.


--
-- Data for Name: credit_notes; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.credit_notes (credit_note_number, sales_order_id, invoice_id, billing_schedule_id, customer_organization_id, status, reason, reason_note, currency, subtotal, tax_amount, total_amount, amount_refunded, issue_date, issued_by_user_id, voided_at, detail, id, organization_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: customer_profiles; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.customer_profiles (customer_organization_id, primary_contact_id, display_name, tier, payment_terms, currency, credit_limit, credit_used, tax_rate_pct, is_active, id, organization_id, created_at, updated_at) FROM stdin;
e7e94765-386b-41d3-9e35-82744e1ad7a2	beebb8d6-6b6c-4a1f-94a5-b383d42a6e2c	Acme Corporation	GOLD	NET_30	USD	500000.00	0.00	0.0000	t	11df3b0a-c9b9-4022-a39f-7202a344cf72	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.126821+00	2026-09-06 07:51:41.131919+00
\.


--
-- Data for Name: deals; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.deals (reference, name, customer_profile_id, owner_user_id, primary_contact_id, stage, currency, expected_value, expected_close_date, notes, id, organization_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: decision_impacts; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.decision_impacts (quote_id, quote_version_id, previous_version_id, quote_line_id, product_id, changed_field, subject, old_value, new_value, material, severity, change_reason, affected_entity_type, affected_entity_id, action_required, detected_at, id, organization_id, created_at) FROM stdin;
\.


--
-- Data for Name: dismissed_recommendations; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.dismissed_recommendations (quote_version_id, product_id, dismissed_by_user_id, note, id, organization_id, created_at) FROM stdin;
\.


--
-- Data for Name: fulfillments; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.fulfillments (fulfillment_number, sales_order_id, warehouse_id, shipment_sequence, status, carrier, tracking_number, shipping_cost, shipped_at, delivered_at, notes, id, organization_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: idempotency_keys; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.idempotency_keys (key, endpoint, method, request_hash, status, user_id, entity_type, entity_id, response_status_code, response_body, completed_at, expires_at, id, organization_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: inventory; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.inventory (warehouse_id, product_id, product_variant_id, quantity_on_hand, quantity_reserved, quantity_inbound, reorder_point, expected_restock_at, id, organization_id, created_at, updated_at) FROM stdin;
26f3aa8d-c8be-4c02-9b7e-513535908bbd	2e8ec45a-facb-48d5-8452-7574aef9f6cb	\N	60.0000	0.0000	0.0000	10.0000	\N	a73f0eb3-afee-42b0-bc67-bc138c62dd8c	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.145236+00	2026-09-06 07:51:41.145237+00
3432260f-05fb-408f-811c-66e219ab3ccc	2e8ec45a-facb-48d5-8452-7574aef9f6cb	\N	40.0000	0.0000	0.0000	10.0000	\N	601b80ef-752a-4e53-9b78-c4ea280ffd09	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.147139+00	2026-09-06 07:51:41.14714+00
26f3aa8d-c8be-4c02-9b7e-513535908bbd	258b1e71-8398-425e-9e0d-55709b847509	\N	150.0000	0.0000	0.0000	10.0000	\N	3ee55637-fd6d-427a-b638-2a762b708920	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.148421+00	2026-09-06 07:51:41.148422+00
3432260f-05fb-408f-811c-66e219ab3ccc	258b1e71-8398-425e-9e0d-55709b847509	\N	50.0000	0.0000	0.0000	10.0000	\N	e1c0e160-07df-4881-839e-9bec5557d5e6	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.149698+00	2026-09-06 07:51:41.149699+00
\.


--
-- Data for Name: inventory_allocations; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.inventory_allocations (sales_order_id, sales_order_line_id, product_id, warehouse_id, inventory_id, fulfillment_id, quantity, status, mode, allocated_by_user_id, allocated_at, released_at, expected_available_at, notes, id, organization_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: invoices; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.invoices (invoice_number, sales_order_id, billing_schedule_id, customer_organization_id, status, currency, subtotal, tax_amount, total_amount, amount_paid, issue_date, due_date, paid_at, id, organization_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: negotiation_messages; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.negotiation_messages (thread_id, quote_version_id, quote_line_id, author_user_id, author_kind, author_display_name, message_type, body, requested_discount_pct, requested_quantity, requested_unit_price, payload, triggered_version_id, id, organization_id, created_at) FROM stdin;
\.


--
-- Data for Name: negotiation_threads; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.negotiation_threads (quote_id, customer_organization_id, quote_version_id, subject, status, opened_by_user_id, message_count, last_message_at, id, organization_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: organization_settings; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.organization_settings (organization_id, finance_escalation_threshold, risk_discount_overage_weight, risk_breadth_weight, risk_margin_weight, risk_depth_weight, stalled_deal_days, discount_anomaly_sigma, discount_anomaly_min_samples, approval_sla_hours, recommendation_min_margin_pct, id, created_at, updated_at) FROM stdin;
1c992595-a0fa-472c-8616-ff3c08716d39	60.0000	3.0000	5.0000	5.0000	0.4000	14	2.0000	5	24	0.0000	e05042bc-c56f-4564-b9e8-ac199097d551	2026-09-06 07:51:41.16216+00	2026-09-06 07:51:41.162161+00
\.


--
-- Data for Name: organizations; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.organizations (name, slug, kind, domain, country, currency, is_active, id, created_at, updated_at) FROM stdin;
TechSupply Solutions	techsupply-solutions	SELLER	techsupply.com	\N	USD	t	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:39.679675+00	2026-09-06 07:51:39.679676+00
Acme Corporation	acme-corporation	CUSTOMER	acme.com	\N	USD	t	e7e94765-386b-41d3-9e35-82744e1ad7a2	2026-09-06 07:51:39.682107+00	2026-09-06 07:51:39.682108+00
\.


--
-- Data for Name: payments; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.payments (payment_number, invoice_id, amount, currency, method, status, reference, notes, received_at, recorded_by_user_id, id, organization_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: policies; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.policies (code, name, description, policy_type, customer_tier, product_category, customer_profile_id, threshold_value, comparison, unit, required_action, severity, priority, is_active, effective_from, effective_to, config, id, organization_id, created_at, updated_at) FROM stdin;
GOLD-HW-CEILING	Gold tier hardware discount ceiling	Gold customers may receive up to 15% off hardware without escalation. Anything above requires Sales Manager sign-off.	CATEGORY_DISCOUNT_CEILING	GOLD	HARDWARE	\N	15.0000	LTE	PERCENT	SALES_MANAGER	MEDIUM	10	t	\N	\N	{}	0ad4c041-b1b0-44f7-b5f9-525247ca082a	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.152381+00	2026-09-06 07:51:41.152381+00
GOLD-SV-CEILING	Gold tier service discount ceiling	Services carry far less room than hardware: Gold customers may receive up to 10% off, above which a Sales Manager must approve.	CATEGORY_DISCOUNT_CEILING	GOLD	SERVICE	\N	10.0000	LTE	PERCENT	SALES_MANAGER	MEDIUM	10	t	\N	\N	{}	adb74f7d-3b9f-4966-ab49-dadae22dbbcf	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.154754+00	2026-09-06 07:51:41.154755+00
GOLD-SB-CEILING	Gold tier subscription discount ceiling	Subscriptions may be discounted up to 10% for Gold customers.	CATEGORY_DISCOUNT_CEILING	GOLD	SUBSCRIPTION	\N	10.0000	LTE	PERCENT	SALES_MANAGER	MEDIUM	10	t	\N	\N	{}	5c90576f-07a5-48cf-9382-fa4703b747ae	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.155627+00	2026-09-06 07:51:41.155628+00
STD-HW-CEILING	Standard hardware discount ceiling	Fallback ceiling for any tier without a specific rule. Applies to hardware only.	CATEGORY_DISCOUNT_CEILING	\N	HARDWARE	\N	10.0000	LTE	PERCENT	SALES_MANAGER	MEDIUM	900	t	\N	\N	{}	c468b97b-b0c3-4f97-a5ce-009d82f74329	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.156496+00	2026-09-06 07:51:41.156498+00
MIN-MARGIN-10	Minimum blended margin 10%	No quote may be issued below 10% blended margin without Finance sign-off, regardless of tier.	MIN_MARGIN	\N	\N	\N	10.0000	GTE	PERCENT	FINANCE	HIGH	10	t	\N	\N	{}	7ce9c73b-ade6-417d-9772-5b62858f2d69	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.157417+00	2026-09-06 07:51:41.157417+00
DISCOUNT-AUTHORITY-20K	Discount signing authority 20,000	A Sales Manager may sign off up to 20,000 of total discount. Beyond that the give-away needs Finance authority, independent of margin.	DISCOUNT_AMOUNT_AUTHORITY	\N	\N	\N	20000.0000	LTE	AMOUNT	FINANCE	HIGH	20	t	\N	\N	{}	59c7c91e-ca15-4717-b721-e1711dac3b18	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.158316+00	2026-09-06 07:51:41.158317+00
GOLD-TERMS-60	Gold tier payment terms limit	Gold customers may be granted up to 60 days to pay. Anything longer is a working-capital decision for Finance.	PAYMENT_TERMS_LIMIT	GOLD	\N	\N	60.0000	LTE	DAYS	FINANCE	MEDIUM	30	t	\N	\N	{}	3f6c8dc5-9959-427f-97d3-5f7c6dfda0be	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.159158+00	2026-09-06 07:51:41.159159+00
\.


--
-- Data for Name: policy_results; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.policy_results (quote_version_id, policy_id, quote_line_id, rule, status, subject, actual_value, threshold_value, overage_points, unit, scope_category, scope_tier, reason, required_action, severity, risk_contribution, detail, evaluated_at, id, organization_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: price_lists; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.price_lists (code, name, tier, currency, rules, valid_from, valid_to, is_active, id, organization_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: product_variants; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.product_variants (product_id, sku, name, attributes, price_delta, cost_delta, is_active, id, organization_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: products; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.products (sku, name, description, category, list_price, internal_cost, tax_rate_pct, uom, billing_type, recurring_interval, default_recurring_periods, is_stock_tracked, is_active, id, organization_id, created_at, updated_at, is_promoted) FROM stdin;
HW-LAPTOP-01	Business Laptop	14-inch business laptop, 16GB RAM, 512GB SSD.	HARDWARE	1200.0000	800.0000	0.0000	EACH	ONE_TIME	\N	1	t	t	2e8ec45a-facb-48d5-8452-7574aef9f6cb	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.134774+00	2026-09-06 07:51:41.134775+00	f
HW-MONITOR-27	27" Monitor	27-inch QHD IPS monitor with USB-C docking.	HARDWARE	400.0000	200.0000	0.0000	EACH	ONE_TIME	\N	1	t	t	258b1e71-8398-425e-9e0d-55709b847509	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.13628+00	2026-09-06 07:51:41.136281+00	f
SV-INSTALL-01	Installation Service	On-site deployment, imaging and handover.	SERVICE	500.0000	150.0000	0.0000	EACH	ONE_TIME	\N	1	f	t	b1b3c78e-b258-4627-97a1-6ba26032ac9c	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.137232+00	2026-09-06 07:51:41.137233+00	f
SB-SUPPORT-01	Annual Support Plan	24/7 support and next-business-day hardware replacement.	SUBSCRIPTION	300.0000	50.0000	0.0000	EACH	RECURRING	YEARLY	1	f	t	4b3262cf-92ed-42f0-9b48-641891276fa8	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.138329+00	2026-09-06 07:51:41.159701+00	t
\.


--
-- Data for Name: quote_lines; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.quote_lines (quote_version_id, product_id, product_variant_id, line_number, description, notes, category, quantity, unit_list_price, unit_cost, discount_pct, tax_rate_pct, billing_type, recurring_interval, recurring_periods, is_stock_tracked, unit_net_price, gross_amount, discount_amount, net_amount, tax_amount, total_amount, line_cost, line_margin, line_margin_pct, id, organization_id, created_at, updated_at, source_line_id, order_discount_amount, effective_discount_pct) FROM stdin;
\.


--
-- Data for Name: quote_versions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.quote_versions (quote_id, version_number, parent_version_id, status, source, revision_reason, created_by_user_id, currency, payment_terms, valid_until, gross_revenue, total_discount, net_revenue, tax_amount, total_revenue, total_cost, margin, margin_pct, effective_discount_pct, one_time_revenue, recurring_revenue, blended_risk_score, risk_band, requires_approval, is_stale, stale_reason, calculated_at, submitted_at, approved_at, sent_at, confirmed_at, rejected_at, superseded_at, id, organization_id, created_at, updated_at, order_discount_pct, order_discount_amount) FROM stdin;
\.


--
-- Data for Name: quotes; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.quotes (quote_number, title, deal_id, created_by_user_id, status, current_version_number, id, organization_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: roles; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.roles (code, name, description, is_internal, can_approve, id, created_at, updated_at) FROM stdin;
SALES	Sales Representative	Builds deals and quotes. Cannot approve anything, including own quotes.	t	f	366056f5-5cb3-4279-bfea-b70eba5110b7	2026-09-06 07:51:39.672734+00	2026-09-06 07:51:39.672738+00
MANAGER	Sales Manager	First-line approver for discount ceiling breaches.	t	t	479553b8-0f39-4c77-a5fe-cf2eb74b9405	2026-09-06 07:51:39.672741+00	2026-09-06 07:51:39.672742+00
FINANCE	Finance Approver	Approves margin violations and deals above discount signing authority.	t	t	fdc3337c-5afe-45ab-a376-09f3b3ebe14b	2026-09-06 07:51:39.672745+00	2026-09-06 07:51:39.672746+00
OPS	Operations	Runs inventory allocation and fulfilment.	t	f	d4b85210-90ec-4278-bd0a-bb0512c1a26d	2026-09-06 07:51:39.672751+00	2026-09-06 07:51:39.672752+00
CUSTOMER	Customer Portal User	External buyer. Portal endpoints only; never sees cost or margin.	f	f	10efd9d7-4333-42b4-9540-7742e16b2b31	2026-09-06 07:51:39.672754+00	2026-09-06 07:51:39.672754+00
ADMIN	Administrator	Configures catalog, warehouses and policies; may act on any approval step.	t	t	eecf93b1-a620-4104-b5a6-9460106be7cd	2026-09-06 07:51:39.672756+00	2026-09-06 07:51:39.672757+00
\.


--
-- Data for Name: sales_order_lines; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.sales_order_lines (sales_order_id, quote_line_id, product_id, line_number, description, category, quantity, unit_list_price, unit_net_price, unit_cost, discount_pct, discount_amount, gross_amount, net_amount, tax_amount, total_amount, line_cost, billing_type, recurring_interval, recurring_periods, is_stock_tracked, quantity_allocated, quantity_backordered, quantity_fulfilled, id, organization_id, created_at, updated_at, promised_delivery_date) FROM stdin;
\.


--
-- Data for Name: sales_orders; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.sales_orders (order_number, deal_id, quote_id, quote_version_id, customer_profile_id, customer_organization_id, status, currency, payment_terms, gross_revenue, total_discount, subtotal, tax_amount, total_amount, total_cost, margin, margin_pct, one_time_amount, recurring_amount, confirmed_by_user_id, confirmed_at, fully_allocated, has_backorder, allocated_at, fulfilled_at, id, organization_id, created_at, updated_at, promised_delivery_date) FROM stdin;
\.


--
-- Data for Name: sales_team_members; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.sales_team_members (sales_team_id, user_id, id, organization_id, created_at) FROM stdin;
09a334e1-aae8-4043-8f55-99fc0b7ce45d	0e0f7f3f-e0b8-4660-b6b7-9479ca4c2266	f3fcfbe7-9075-4875-9b22-2f1cbf3f39df	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.172684+00
09a334e1-aae8-4043-8f55-99fc0b7ce45d	11647376-2440-4d1f-aecd-83ae8292ab03	61d6d2c5-ee1d-459d-9da5-209039b0fad1	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.172687+00
\.


--
-- Data for Name: sales_teams; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.sales_teams (code, name, description, manager_user_id, region, is_active, id, organization_id, created_at, updated_at) FROM stdin;
WEST	West Enterprise	Enterprise accounts west of the Rockies.	11647376-2440-4d1f-aecd-83ae8292ab03	West	t	09a334e1-aae8-4043-8f55-99fc0b7ce45d	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.169622+00	2026-09-06 07:51:41.169623+00
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.users (email, hashed_password, full_name, phone, role_id, is_active, last_login_at, id, organization_id, created_at, updated_at) FROM stdin;
sales@techsupply.com	$2b$12$pXb.aMkHQBu5k7iSJLys5uZ3X710cLq6POkASbUsQ6JkATd9Ns0Uu	Sam Rivera	\N	366056f5-5cb3-4279-bfea-b70eba5110b7	t	\N	0e0f7f3f-e0b8-4660-b6b7-9479ca4c2266	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:39.949784+00	2026-09-06 07:51:39.949789+00
manager@techsupply.com	$2b$12$8.diZJGO249pP5PMgBIgTerNbblvAKMbJ5k8qQzQ8colSVBXvVHC6	Morgan Chen	\N	479553b8-0f39-4c77-a5fe-cf2eb74b9405	t	\N	11647376-2440-4d1f-aecd-83ae8292ab03	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:40.190314+00	2026-09-06 07:51:40.190317+00
finance@techsupply.com	$2b$12$IsbhF4odDBOia6/joM0m2eGZCksNcz3f.CwYgS0NaF46i0Vy15EmS	Fran Delgado	\N	fdc3337c-5afe-45ab-a376-09f3b3ebe14b	t	\N	f754d3f5-38a0-4bd3-9692-885435826768	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:40.425096+00	2026-09-06 07:51:40.425098+00
ops@techsupply.com	$2b$12$aB0jT4vVkuTUUPZLL3CCvuqHUGJ7fdxjYf70AU5VoqBlLqF0gfcXm	Omar Petrov	\N	d4b85210-90ec-4278-bd0a-bb0512c1a26d	t	\N	2041d8e7-cfa3-4dc4-9847-d816e73018c5	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:40.657931+00	2026-09-06 07:51:40.657934+00
admin@techsupply.com	$2b$12$LdyPsITj.CxcJDNqo/88TeCrKFs3R0Mdqa07bAO2V0o3TqY7/WwyC	Avery Stone	\N	eecf93b1-a620-4104-b5a6-9460106be7cd	t	\N	aca5a4e5-e08a-41fb-9131-563f4e22cc98	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:40.890265+00	2026-09-06 07:51:40.890267+00
customer@acme.com	$2b$12$XOhSqmDwbGk0k4B2kKwkOe1GquUpk7GvE0t/P20kEmDJcCQNF.cIW	Casey Nolan	\N	10efd9d7-4333-42b4-9540-7742e16b2b31	t	\N	f9b28ee6-2804-4138-a99d-3a7afabaa4e3	e7e94765-386b-41d3-9e35-82744e1ad7a2	2026-09-06 07:51:41.121719+00	2026-09-06 07:51:41.121722+00
\.


--
-- Data for Name: warehouses; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.warehouses (code, name, region, address_line1, city, country, postal_code, priority, shipping_cost_per_shipment, is_active, id, organization_id, created_at, updated_at) FROM stdin;
MAIN	Main Warehouse	West	\N	San Jose	US	\N	10	120.00	t	26f3aa8d-c8be-4c02-9b7e-513535908bbd	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.140603+00	2026-09-06 07:51:41.140603+00
EAST	East Depot	East	\N	Newark	US	\N	20	180.00	t	3432260f-05fb-408f-811c-66e219ab3ccc	1c992595-a0fa-472c-8616-ff3c08716d39	2026-09-06 07:51:41.141955+00	2026-09-06 07:51:41.141956+00
\.


--
-- Name: audit_events_sequence_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.audit_events_sequence_seq', 1, false);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: approval_decisions pk_approval_decisions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_decisions
    ADD CONSTRAINT pk_approval_decisions PRIMARY KEY (id);


--
-- Name: approval_requests pk_approval_requests; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT pk_approval_requests PRIMARY KEY (id);


--
-- Name: approval_steps pk_approval_steps; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_steps
    ADD CONSTRAINT pk_approval_steps PRIMARY KEY (id);


--
-- Name: attention_items pk_attention_items; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attention_items
    ADD CONSTRAINT pk_attention_items PRIMARY KEY (id);


--
-- Name: audit_events pk_audit_events; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT pk_audit_events PRIMARY KEY (id);


--
-- Name: billing_schedules pk_billing_schedules; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.billing_schedules
    ADD CONSTRAINT pk_billing_schedules PRIMARY KEY (id);


--
-- Name: commercial_snapshots pk_commercial_snapshots; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_snapshots
    ADD CONSTRAINT pk_commercial_snapshots PRIMARY KEY (id);


--
-- Name: contacts pk_contacts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contacts
    ADD CONSTRAINT pk_contacts PRIMARY KEY (id);


--
-- Name: credit_notes pk_credit_notes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_notes
    ADD CONSTRAINT pk_credit_notes PRIMARY KEY (id);


--
-- Name: customer_profiles pk_customer_profiles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_profiles
    ADD CONSTRAINT pk_customer_profiles PRIMARY KEY (id);


--
-- Name: deals pk_deals; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.deals
    ADD CONSTRAINT pk_deals PRIMARY KEY (id);


--
-- Name: decision_impacts pk_decision_impacts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.decision_impacts
    ADD CONSTRAINT pk_decision_impacts PRIMARY KEY (id);


--
-- Name: dismissed_recommendations pk_dismissed_recommendations; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dismissed_recommendations
    ADD CONSTRAINT pk_dismissed_recommendations PRIMARY KEY (id);


--
-- Name: fulfillments pk_fulfillments; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fulfillments
    ADD CONSTRAINT pk_fulfillments PRIMARY KEY (id);


--
-- Name: idempotency_keys pk_idempotency_keys; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.idempotency_keys
    ADD CONSTRAINT pk_idempotency_keys PRIMARY KEY (id);


--
-- Name: inventory pk_inventory; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory
    ADD CONSTRAINT pk_inventory PRIMARY KEY (id);


--
-- Name: inventory_allocations pk_inventory_allocations; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory_allocations
    ADD CONSTRAINT pk_inventory_allocations PRIMARY KEY (id);


--
-- Name: invoices pk_invoices; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT pk_invoices PRIMARY KEY (id);


--
-- Name: negotiation_messages pk_negotiation_messages; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.negotiation_messages
    ADD CONSTRAINT pk_negotiation_messages PRIMARY KEY (id);


--
-- Name: negotiation_threads pk_negotiation_threads; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.negotiation_threads
    ADD CONSTRAINT pk_negotiation_threads PRIMARY KEY (id);


--
-- Name: organization_settings pk_organization_settings; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_settings
    ADD CONSTRAINT pk_organization_settings PRIMARY KEY (id);


--
-- Name: organizations pk_organizations; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT pk_organizations PRIMARY KEY (id);


--
-- Name: payments pk_payments; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT pk_payments PRIMARY KEY (id);


--
-- Name: policies pk_policies; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policies
    ADD CONSTRAINT pk_policies PRIMARY KEY (id);


--
-- Name: policy_results pk_policy_results; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policy_results
    ADD CONSTRAINT pk_policy_results PRIMARY KEY (id);


--
-- Name: price_lists pk_price_lists; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.price_lists
    ADD CONSTRAINT pk_price_lists PRIMARY KEY (id);


--
-- Name: product_variants pk_product_variants; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_variants
    ADD CONSTRAINT pk_product_variants PRIMARY KEY (id);


--
-- Name: products pk_products; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT pk_products PRIMARY KEY (id);


--
-- Name: quote_lines pk_quote_lines; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quote_lines
    ADD CONSTRAINT pk_quote_lines PRIMARY KEY (id);


--
-- Name: quote_versions pk_quote_versions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quote_versions
    ADD CONSTRAINT pk_quote_versions PRIMARY KEY (id);


--
-- Name: quotes pk_quotes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quotes
    ADD CONSTRAINT pk_quotes PRIMARY KEY (id);


--
-- Name: roles pk_roles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT pk_roles PRIMARY KEY (id);


--
-- Name: sales_order_lines pk_sales_order_lines; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_order_lines
    ADD CONSTRAINT pk_sales_order_lines PRIMARY KEY (id);


--
-- Name: sales_orders pk_sales_orders; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_orders
    ADD CONSTRAINT pk_sales_orders PRIMARY KEY (id);


--
-- Name: sales_team_members pk_sales_team_members; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_team_members
    ADD CONSTRAINT pk_sales_team_members PRIMARY KEY (id);


--
-- Name: sales_teams pk_sales_teams; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_teams
    ADD CONSTRAINT pk_sales_teams PRIMARY KEY (id);


--
-- Name: users pk_users; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT pk_users PRIMARY KEY (id);


--
-- Name: warehouses pk_warehouses; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.warehouses
    ADD CONSTRAINT pk_warehouses PRIMARY KEY (id);


--
-- Name: approval_steps uq_approval_steps_approval_request_id_sequence; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_steps
    ADD CONSTRAINT uq_approval_steps_approval_request_id_sequence UNIQUE (approval_request_id, sequence);


--
-- Name: audit_events uq_audit_events_sequence; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT uq_audit_events_sequence UNIQUE (sequence);


--
-- Name: billing_schedules uq_billing_schedules_organization_id_schedule_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.billing_schedules
    ADD CONSTRAINT uq_billing_schedules_organization_id_schedule_number UNIQUE (organization_id, schedule_number);


--
-- Name: contacts uq_contacts_organization_id_email; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contacts
    ADD CONSTRAINT uq_contacts_organization_id_email UNIQUE (organization_id, email);


--
-- Name: credit_notes uq_credit_notes_organization_id_credit_note_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_notes
    ADD CONSTRAINT uq_credit_notes_organization_id_credit_note_number UNIQUE (organization_id, credit_note_number);


--
-- Name: customer_profiles uq_customer_profiles_organization_id_customer_organization_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_profiles
    ADD CONSTRAINT uq_customer_profiles_organization_id_customer_organization_id UNIQUE (organization_id, customer_organization_id);


--
-- Name: deals uq_deals_organization_id_reference; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.deals
    ADD CONSTRAINT uq_deals_organization_id_reference UNIQUE (organization_id, reference);


--
-- Name: dismissed_recommendations uq_dismissed_recommendations_quote_version_id_product_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dismissed_recommendations
    ADD CONSTRAINT uq_dismissed_recommendations_quote_version_id_product_id UNIQUE (quote_version_id, product_id);


--
-- Name: fulfillments uq_fulfillments_organization_id_fulfillment_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fulfillments
    ADD CONSTRAINT uq_fulfillments_organization_id_fulfillment_number UNIQUE (organization_id, fulfillment_number);


--
-- Name: idempotency_keys uq_idempotency_keys_organization_id_endpoint_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.idempotency_keys
    ADD CONSTRAINT uq_idempotency_keys_organization_id_endpoint_key UNIQUE (organization_id, endpoint, key);


--
-- Name: inventory uq_inventory_warehouse_id_product_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory
    ADD CONSTRAINT uq_inventory_warehouse_id_product_id UNIQUE (warehouse_id, product_id);


--
-- Name: invoices uq_invoices_organization_id_invoice_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT uq_invoices_organization_id_invoice_number UNIQUE (organization_id, invoice_number);


--
-- Name: negotiation_threads uq_negotiation_threads_quote_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.negotiation_threads
    ADD CONSTRAINT uq_negotiation_threads_quote_id UNIQUE (quote_id);


--
-- Name: organization_settings uq_organization_settings_organization_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_settings
    ADD CONSTRAINT uq_organization_settings_organization_id UNIQUE (organization_id);


--
-- Name: organizations uq_organizations_slug; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT uq_organizations_slug UNIQUE (slug);


--
-- Name: payments uq_payments_organization_id_payment_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT uq_payments_organization_id_payment_number UNIQUE (organization_id, payment_number);


--
-- Name: policies uq_policies_organization_id_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policies
    ADD CONSTRAINT uq_policies_organization_id_code UNIQUE (organization_id, code);


--
-- Name: price_lists uq_price_lists_organization_id_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.price_lists
    ADD CONSTRAINT uq_price_lists_organization_id_code UNIQUE (organization_id, code);


--
-- Name: product_variants uq_product_variants_organization_id_sku; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_variants
    ADD CONSTRAINT uq_product_variants_organization_id_sku UNIQUE (organization_id, sku);


--
-- Name: products uq_products_organization_id_sku; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT uq_products_organization_id_sku UNIQUE (organization_id, sku);


--
-- Name: quote_lines uq_quote_lines_quote_version_id_line_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quote_lines
    ADD CONSTRAINT uq_quote_lines_quote_version_id_line_number UNIQUE (quote_version_id, line_number);


--
-- Name: quote_versions uq_quote_versions_quote_id_version_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quote_versions
    ADD CONSTRAINT uq_quote_versions_quote_id_version_number UNIQUE (quote_id, version_number);


--
-- Name: quotes uq_quotes_organization_id_quote_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quotes
    ADD CONSTRAINT uq_quotes_organization_id_quote_number UNIQUE (organization_id, quote_number);


--
-- Name: roles uq_roles_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT uq_roles_code UNIQUE (code);


--
-- Name: sales_order_lines uq_sales_order_lines_sales_order_id_line_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_order_lines
    ADD CONSTRAINT uq_sales_order_lines_sales_order_id_line_number UNIQUE (sales_order_id, line_number);


--
-- Name: sales_orders uq_sales_orders_organization_id_order_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_orders
    ADD CONSTRAINT uq_sales_orders_organization_id_order_number UNIQUE (organization_id, order_number);


--
-- Name: sales_orders uq_sales_orders_quote_version_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_orders
    ADD CONSTRAINT uq_sales_orders_quote_version_id UNIQUE (quote_version_id);


--
-- Name: sales_team_members uq_sales_team_members_sales_team_id_user_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_team_members
    ADD CONSTRAINT uq_sales_team_members_sales_team_id_user_id UNIQUE (sales_team_id, user_id);


--
-- Name: sales_teams uq_sales_teams_organization_id_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_teams
    ADD CONSTRAINT uq_sales_teams_organization_id_code UNIQUE (organization_id, code);


--
-- Name: users uq_users_email; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT uq_users_email UNIQUE (email);


--
-- Name: warehouses uq_warehouses_organization_id_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.warehouses
    ADD CONSTRAINT uq_warehouses_organization_id_code UNIQUE (organization_id, code);


--
-- Name: ix_approval_decisions_actor_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_decisions_actor_user_id ON public.approval_decisions USING btree (actor_user_id);


--
-- Name: ix_approval_decisions_approval_request_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_decisions_approval_request_id ON public.approval_decisions USING btree (approval_request_id);


--
-- Name: ix_approval_decisions_approval_request_id_decided_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_decisions_approval_request_id_decided_at ON public.approval_decisions USING btree (approval_request_id, decided_at);


--
-- Name: ix_approval_decisions_approval_step_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_decisions_approval_step_id ON public.approval_decisions USING btree (approval_step_id);


--
-- Name: ix_approval_decisions_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_decisions_created_at ON public.approval_decisions USING btree (created_at);


--
-- Name: ix_approval_decisions_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_decisions_organization_id ON public.approval_decisions USING btree (organization_id);


--
-- Name: ix_approval_requests_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_requests_created_at ON public.approval_requests USING btree (created_at);


--
-- Name: ix_approval_requests_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_requests_organization_id ON public.approval_requests USING btree (organization_id);


--
-- Name: ix_approval_requests_organization_id_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_requests_organization_id_status ON public.approval_requests USING btree (organization_id, status);


--
-- Name: ix_approval_requests_quote_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_requests_quote_id ON public.approval_requests USING btree (quote_id);


--
-- Name: ix_approval_requests_quote_id_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_requests_quote_id_status ON public.approval_requests USING btree (quote_id, status);


--
-- Name: ix_approval_requests_quote_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_requests_quote_version_id ON public.approval_requests USING btree (quote_version_id);


--
-- Name: ix_approval_requests_requested_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_requests_requested_by_user_id ON public.approval_requests USING btree (requested_by_user_id);


--
-- Name: ix_approval_steps_approval_request_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_steps_approval_request_id ON public.approval_steps USING btree (approval_request_id);


--
-- Name: ix_approval_steps_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_steps_created_at ON public.approval_steps USING btree (created_at);


--
-- Name: ix_approval_steps_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_steps_organization_id ON public.approval_steps USING btree (organization_id);


--
-- Name: ix_approval_steps_status_required_role; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_steps_status_required_role ON public.approval_steps USING btree (status, required_role);


--
-- Name: ix_attention_items_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attention_items_created_at ON public.attention_items USING btree (created_at);


--
-- Name: ix_attention_items_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attention_items_organization_id ON public.attention_items USING btree (organization_id);


--
-- Name: ix_attention_items_organization_id_status_severity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attention_items_organization_id_status_severity ON public.attention_items USING btree (organization_id, status, severity);


--
-- Name: ix_attention_items_owner_role_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attention_items_owner_role_status ON public.attention_items USING btree (owner_role, status);


--
-- Name: ix_attention_items_owner_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attention_items_owner_user_id ON public.attention_items USING btree (owner_user_id);


--
-- Name: ix_attention_items_source_type_source_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attention_items_source_type_source_id ON public.attention_items USING btree (source_type, source_id);


--
-- Name: ix_audit_events_actor_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_events_actor_user_id ON public.audit_events USING btree (actor_user_id);


--
-- Name: ix_audit_events_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_events_created_at ON public.audit_events USING btree (created_at);


--
-- Name: ix_audit_events_entity_type_entity_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_events_entity_type_entity_id ON public.audit_events USING btree (entity_type, entity_id);


--
-- Name: ix_audit_events_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_events_event_type ON public.audit_events USING btree (event_type);


--
-- Name: ix_audit_events_occurred_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_events_occurred_at ON public.audit_events USING btree (occurred_at);


--
-- Name: ix_audit_events_organization_id_occurred_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_events_organization_id_occurred_at ON public.audit_events USING btree (organization_id, occurred_at);


--
-- Name: ix_billing_schedules_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_billing_schedules_created_at ON public.billing_schedules USING btree (created_at);


--
-- Name: ix_billing_schedules_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_billing_schedules_organization_id ON public.billing_schedules USING btree (organization_id);


--
-- Name: ix_billing_schedules_organization_id_status_due_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_billing_schedules_organization_id_status_due_date ON public.billing_schedules USING btree (organization_id, status, due_date);


--
-- Name: ix_billing_schedules_sales_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_billing_schedules_sales_order_id ON public.billing_schedules USING btree (sales_order_id);


--
-- Name: ix_billing_schedules_sales_order_id_billing_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_billing_schedules_sales_order_id_billing_type ON public.billing_schedules USING btree (sales_order_id, billing_type);


--
-- Name: ix_billing_schedules_sales_order_line_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_billing_schedules_sales_order_line_id ON public.billing_schedules USING btree (sales_order_line_id);


--
-- Name: ix_commercial_snapshots_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commercial_snapshots_created_at ON public.commercial_snapshots USING btree (created_at);


--
-- Name: ix_commercial_snapshots_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commercial_snapshots_organization_id ON public.commercial_snapshots USING btree (organization_id);


--
-- Name: ix_commercial_snapshots_quote_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commercial_snapshots_quote_version_id ON public.commercial_snapshots USING btree (quote_version_id);


--
-- Name: ix_commercial_snapshots_quote_version_id_is_current; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commercial_snapshots_quote_version_id_is_current ON public.commercial_snapshots USING btree (quote_version_id, is_current);


--
-- Name: ix_contacts_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contacts_created_at ON public.contacts USING btree (created_at);


--
-- Name: ix_contacts_customer_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contacts_customer_organization_id ON public.contacts USING btree (customer_organization_id);


--
-- Name: ix_contacts_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contacts_organization_id ON public.contacts USING btree (organization_id);


--
-- Name: ix_contacts_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contacts_user_id ON public.contacts USING btree (user_id);


--
-- Name: ix_credit_notes_billing_schedule_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_credit_notes_billing_schedule_id ON public.credit_notes USING btree (billing_schedule_id);


--
-- Name: ix_credit_notes_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_credit_notes_created_at ON public.credit_notes USING btree (created_at);


--
-- Name: ix_credit_notes_invoice_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_credit_notes_invoice_id ON public.credit_notes USING btree (invoice_id);


--
-- Name: ix_credit_notes_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_credit_notes_organization_id ON public.credit_notes USING btree (organization_id);


--
-- Name: ix_credit_notes_organization_id_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_credit_notes_organization_id_status ON public.credit_notes USING btree (organization_id, status);


--
-- Name: ix_credit_notes_sales_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_credit_notes_sales_order_id ON public.credit_notes USING btree (sales_order_id);


--
-- Name: ix_customer_profiles_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customer_profiles_created_at ON public.customer_profiles USING btree (created_at);


--
-- Name: ix_customer_profiles_customer_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customer_profiles_customer_organization_id ON public.customer_profiles USING btree (customer_organization_id);


--
-- Name: ix_customer_profiles_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customer_profiles_organization_id ON public.customer_profiles USING btree (organization_id);


--
-- Name: ix_customer_profiles_tier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customer_profiles_tier ON public.customer_profiles USING btree (tier);


--
-- Name: ix_deals_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_deals_created_at ON public.deals USING btree (created_at);


--
-- Name: ix_deals_customer_profile_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_deals_customer_profile_id ON public.deals USING btree (customer_profile_id);


--
-- Name: ix_deals_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_deals_organization_id ON public.deals USING btree (organization_id);


--
-- Name: ix_deals_organization_id_stage; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_deals_organization_id_stage ON public.deals USING btree (organization_id, stage);


--
-- Name: ix_deals_owner_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_deals_owner_user_id ON public.deals USING btree (owner_user_id);


--
-- Name: ix_decision_impacts_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_decision_impacts_created_at ON public.decision_impacts USING btree (created_at);


--
-- Name: ix_decision_impacts_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_decision_impacts_organization_id ON public.decision_impacts USING btree (organization_id);


--
-- Name: ix_decision_impacts_organization_id_detected_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_decision_impacts_organization_id_detected_at ON public.decision_impacts USING btree (organization_id, detected_at);


--
-- Name: ix_decision_impacts_quote_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_decision_impacts_quote_id ON public.decision_impacts USING btree (quote_id);


--
-- Name: ix_decision_impacts_quote_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_decision_impacts_quote_version_id ON public.decision_impacts USING btree (quote_version_id);


--
-- Name: ix_decision_impacts_quote_version_id_material; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_decision_impacts_quote_version_id_material ON public.decision_impacts USING btree (quote_version_id, material);


--
-- Name: ix_dismissed_recommendations_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dismissed_recommendations_created_at ON public.dismissed_recommendations USING btree (created_at);


--
-- Name: ix_dismissed_recommendations_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dismissed_recommendations_organization_id ON public.dismissed_recommendations USING btree (organization_id);


--
-- Name: ix_dismissed_recommendations_quote_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dismissed_recommendations_quote_version_id ON public.dismissed_recommendations USING btree (quote_version_id);


--
-- Name: ix_fulfillments_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fulfillments_created_at ON public.fulfillments USING btree (created_at);


--
-- Name: ix_fulfillments_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fulfillments_organization_id ON public.fulfillments USING btree (organization_id);


--
-- Name: ix_fulfillments_sales_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fulfillments_sales_order_id ON public.fulfillments USING btree (sales_order_id);


--
-- Name: ix_fulfillments_sales_order_id_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fulfillments_sales_order_id_status ON public.fulfillments USING btree (sales_order_id, status);


--
-- Name: ix_fulfillments_warehouse_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fulfillments_warehouse_id ON public.fulfillments USING btree (warehouse_id);


--
-- Name: ix_idempotency_keys_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_idempotency_keys_created_at ON public.idempotency_keys USING btree (created_at);


--
-- Name: ix_idempotency_keys_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_idempotency_keys_expires_at ON public.idempotency_keys USING btree (expires_at);


--
-- Name: ix_idempotency_keys_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_idempotency_keys_organization_id ON public.idempotency_keys USING btree (organization_id);


--
-- Name: ix_inventory_allocations_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_allocations_created_at ON public.inventory_allocations USING btree (created_at);


--
-- Name: ix_inventory_allocations_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_allocations_organization_id ON public.inventory_allocations USING btree (organization_id);


--
-- Name: ix_inventory_allocations_sales_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_allocations_sales_order_id ON public.inventory_allocations USING btree (sales_order_id);


--
-- Name: ix_inventory_allocations_sales_order_id_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_allocations_sales_order_id_status ON public.inventory_allocations USING btree (sales_order_id, status);


--
-- Name: ix_inventory_allocations_sales_order_line_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_allocations_sales_order_line_id ON public.inventory_allocations USING btree (sales_order_line_id);


--
-- Name: ix_inventory_allocations_warehouse_id_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_allocations_warehouse_id_product_id ON public.inventory_allocations USING btree (warehouse_id, product_id);


--
-- Name: ix_inventory_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_created_at ON public.inventory USING btree (created_at);


--
-- Name: ix_inventory_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_organization_id ON public.inventory USING btree (organization_id);


--
-- Name: ix_inventory_organization_id_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_organization_id_product_id ON public.inventory USING btree (organization_id, product_id);


--
-- Name: ix_inventory_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_product_id ON public.inventory USING btree (product_id);


--
-- Name: ix_inventory_warehouse_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inventory_warehouse_id ON public.inventory USING btree (warehouse_id);


--
-- Name: ix_invoices_billing_schedule_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_invoices_billing_schedule_id ON public.invoices USING btree (billing_schedule_id);


--
-- Name: ix_invoices_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_invoices_created_at ON public.invoices USING btree (created_at);


--
-- Name: ix_invoices_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_invoices_organization_id ON public.invoices USING btree (organization_id);


--
-- Name: ix_invoices_organization_id_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_invoices_organization_id_status ON public.invoices USING btree (organization_id, status);


--
-- Name: ix_invoices_sales_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_invoices_sales_order_id ON public.invoices USING btree (sales_order_id);


--
-- Name: ix_negotiation_messages_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_negotiation_messages_created_at ON public.negotiation_messages USING btree (created_at);


--
-- Name: ix_negotiation_messages_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_negotiation_messages_organization_id ON public.negotiation_messages USING btree (organization_id);


--
-- Name: ix_negotiation_messages_quote_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_negotiation_messages_quote_version_id ON public.negotiation_messages USING btree (quote_version_id);


--
-- Name: ix_negotiation_messages_thread_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_negotiation_messages_thread_id ON public.negotiation_messages USING btree (thread_id);


--
-- Name: ix_negotiation_messages_thread_id_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_negotiation_messages_thread_id_created_at ON public.negotiation_messages USING btree (thread_id, created_at);


--
-- Name: ix_negotiation_threads_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_negotiation_threads_created_at ON public.negotiation_threads USING btree (created_at);


--
-- Name: ix_negotiation_threads_customer_organization_id_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_negotiation_threads_customer_organization_id_status ON public.negotiation_threads USING btree (customer_organization_id, status);


--
-- Name: ix_negotiation_threads_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_negotiation_threads_organization_id ON public.negotiation_threads USING btree (organization_id);


--
-- Name: ix_negotiation_threads_quote_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_negotiation_threads_quote_version_id ON public.negotiation_threads USING btree (quote_version_id);


--
-- Name: ix_organization_settings_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_organization_settings_created_at ON public.organization_settings USING btree (created_at);


--
-- Name: ix_organization_settings_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_organization_settings_organization_id ON public.organization_settings USING btree (organization_id);


--
-- Name: ix_organizations_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_organizations_created_at ON public.organizations USING btree (created_at);


--
-- Name: ix_organizations_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_organizations_kind ON public.organizations USING btree (kind);


--
-- Name: ix_payments_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_payments_created_at ON public.payments USING btree (created_at);


--
-- Name: ix_payments_invoice_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_payments_invoice_id ON public.payments USING btree (invoice_id);


--
-- Name: ix_payments_invoice_id_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_payments_invoice_id_status ON public.payments USING btree (invoice_id, status);


--
-- Name: ix_payments_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_payments_organization_id ON public.payments USING btree (organization_id);


--
-- Name: ix_policies_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_policies_created_at ON public.policies USING btree (created_at);


--
-- Name: ix_policies_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_policies_organization_id ON public.policies USING btree (organization_id);


--
-- Name: ix_policies_organization_id_policy_type_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_policies_organization_id_policy_type_is_active ON public.policies USING btree (organization_id, policy_type, is_active);


--
-- Name: ix_policy_results_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_policy_results_created_at ON public.policy_results USING btree (created_at);


--
-- Name: ix_policy_results_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_policy_results_organization_id ON public.policy_results USING btree (organization_id);


--
-- Name: ix_policy_results_organization_id_rule; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_policy_results_organization_id_rule ON public.policy_results USING btree (organization_id, rule);


--
-- Name: ix_policy_results_quote_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_policy_results_quote_version_id ON public.policy_results USING btree (quote_version_id);


--
-- Name: ix_policy_results_quote_version_id_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_policy_results_quote_version_id_status ON public.policy_results USING btree (quote_version_id, status);


--
-- Name: ix_price_lists_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_price_lists_created_at ON public.price_lists USING btree (created_at);


--
-- Name: ix_price_lists_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_price_lists_organization_id ON public.price_lists USING btree (organization_id);


--
-- Name: ix_product_variants_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_variants_created_at ON public.product_variants USING btree (created_at);


--
-- Name: ix_product_variants_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_variants_organization_id ON public.product_variants USING btree (organization_id);


--
-- Name: ix_product_variants_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_variants_product_id ON public.product_variants USING btree (product_id);


--
-- Name: ix_products_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_products_created_at ON public.products USING btree (created_at);


--
-- Name: ix_products_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_products_organization_id ON public.products USING btree (organization_id);


--
-- Name: ix_products_organization_id_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_products_organization_id_category ON public.products USING btree (organization_id, category);


--
-- Name: ix_quote_lines_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quote_lines_created_at ON public.quote_lines USING btree (created_at);


--
-- Name: ix_quote_lines_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quote_lines_organization_id ON public.quote_lines USING btree (organization_id);


--
-- Name: ix_quote_lines_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quote_lines_product_id ON public.quote_lines USING btree (product_id);


--
-- Name: ix_quote_lines_quote_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quote_lines_quote_version_id ON public.quote_lines USING btree (quote_version_id);


--
-- Name: ix_quote_lines_source_line_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quote_lines_source_line_id ON public.quote_lines USING btree (source_line_id);


--
-- Name: ix_quote_versions_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quote_versions_created_at ON public.quote_versions USING btree (created_at);


--
-- Name: ix_quote_versions_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quote_versions_organization_id ON public.quote_versions USING btree (organization_id);


--
-- Name: ix_quote_versions_organization_id_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quote_versions_organization_id_status ON public.quote_versions USING btree (organization_id, status);


--
-- Name: ix_quote_versions_quote_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quote_versions_quote_id ON public.quote_versions USING btree (quote_id);


--
-- Name: ix_quote_versions_quote_id_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quote_versions_quote_id_status ON public.quote_versions USING btree (quote_id, status);


--
-- Name: ix_quotes_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quotes_created_at ON public.quotes USING btree (created_at);


--
-- Name: ix_quotes_deal_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quotes_deal_id ON public.quotes USING btree (deal_id);


--
-- Name: ix_quotes_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quotes_organization_id ON public.quotes USING btree (organization_id);


--
-- Name: ix_quotes_organization_id_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quotes_organization_id_status ON public.quotes USING btree (organization_id, status);


--
-- Name: ix_roles_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_roles_created_at ON public.roles USING btree (created_at);


--
-- Name: ix_sales_order_lines_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sales_order_lines_created_at ON public.sales_order_lines USING btree (created_at);


--
-- Name: ix_sales_order_lines_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sales_order_lines_organization_id ON public.sales_order_lines USING btree (organization_id);


--
-- Name: ix_sales_order_lines_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sales_order_lines_product_id ON public.sales_order_lines USING btree (product_id);


--
-- Name: ix_sales_order_lines_sales_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sales_order_lines_sales_order_id ON public.sales_order_lines USING btree (sales_order_id);


--
-- Name: ix_sales_orders_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sales_orders_created_at ON public.sales_orders USING btree (created_at);


--
-- Name: ix_sales_orders_customer_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sales_orders_customer_organization_id ON public.sales_orders USING btree (customer_organization_id);


--
-- Name: ix_sales_orders_deal_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sales_orders_deal_id ON public.sales_orders USING btree (deal_id);


--
-- Name: ix_sales_orders_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sales_orders_organization_id ON public.sales_orders USING btree (organization_id);


--
-- Name: ix_sales_orders_organization_id_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sales_orders_organization_id_status ON public.sales_orders USING btree (organization_id, status);


--
-- Name: ix_sales_orders_quote_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sales_orders_quote_id ON public.sales_orders USING btree (quote_id);


--
-- Name: ix_sales_team_members_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sales_team_members_created_at ON public.sales_team_members USING btree (created_at);


--
-- Name: ix_sales_team_members_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sales_team_members_organization_id ON public.sales_team_members USING btree (organization_id);


--
-- Name: ix_sales_team_members_sales_team_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sales_team_members_sales_team_id ON public.sales_team_members USING btree (sales_team_id);


--
-- Name: ix_sales_team_members_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sales_team_members_user_id ON public.sales_team_members USING btree (user_id);


--
-- Name: ix_sales_teams_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sales_teams_created_at ON public.sales_teams USING btree (created_at);


--
-- Name: ix_sales_teams_manager_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sales_teams_manager_user_id ON public.sales_teams USING btree (manager_user_id);


--
-- Name: ix_sales_teams_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sales_teams_organization_id ON public.sales_teams USING btree (organization_id);


--
-- Name: ix_sales_teams_organization_id_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sales_teams_organization_id_is_active ON public.sales_teams USING btree (organization_id, is_active);


--
-- Name: ix_users_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_created_at ON public.users USING btree (created_at);


--
-- Name: ix_users_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_organization_id ON public.users USING btree (organization_id);


--
-- Name: ix_users_organization_id_role_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_organization_id_role_id ON public.users USING btree (organization_id, role_id);


--
-- Name: ix_users_role_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_role_id ON public.users USING btree (role_id);


--
-- Name: ix_warehouses_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_warehouses_created_at ON public.warehouses USING btree (created_at);


--
-- Name: ix_warehouses_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_warehouses_organization_id ON public.warehouses USING btree (organization_id);


--
-- Name: uq_approval_requests_one_pending_per_version; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_approval_requests_one_pending_per_version ON public.approval_requests USING btree (quote_version_id) WHERE ((status)::text = 'PENDING'::text);


--
-- Name: uq_attention_items_live_per_source; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_attention_items_live_per_source ON public.attention_items USING btree (organization_id, source_type, source_id, type) WHERE ((status)::text <> 'RESOLVED'::text);


--
-- Name: approval_decisions fk_approval_decisions_actor_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_decisions
    ADD CONSTRAINT fk_approval_decisions_actor_user_id_users FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: approval_decisions fk_approval_decisions_approval_request_id_approval_requests; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_decisions
    ADD CONSTRAINT fk_approval_decisions_approval_request_id_approval_requests FOREIGN KEY (approval_request_id) REFERENCES public.approval_requests(id) ON DELETE CASCADE;


--
-- Name: approval_decisions fk_approval_decisions_approval_step_id_approval_steps; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_decisions
    ADD CONSTRAINT fk_approval_decisions_approval_step_id_approval_steps FOREIGN KEY (approval_step_id) REFERENCES public.approval_steps(id) ON DELETE CASCADE;


--
-- Name: approval_decisions fk_approval_decisions_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_decisions
    ADD CONSTRAINT fk_approval_decisions_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: approval_decisions fk_approval_decisions_quote_version_id_quote_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_decisions
    ADD CONSTRAINT fk_approval_decisions_quote_version_id_quote_versions FOREIGN KEY (quote_version_id) REFERENCES public.quote_versions(id) ON DELETE CASCADE;


--
-- Name: approval_requests fk_approval_requests_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT fk_approval_requests_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: approval_requests fk_approval_requests_quote_id_quotes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT fk_approval_requests_quote_id_quotes FOREIGN KEY (quote_id) REFERENCES public.quotes(id) ON DELETE CASCADE;


--
-- Name: approval_requests fk_approval_requests_quote_version_id_quote_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT fk_approval_requests_quote_version_id_quote_versions FOREIGN KEY (quote_version_id) REFERENCES public.quote_versions(id) ON DELETE CASCADE;


--
-- Name: approval_requests fk_approval_requests_requested_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT fk_approval_requests_requested_by_user_id_users FOREIGN KEY (requested_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: approval_requests fk_approval_requests_superseded_by_request_id_approval_requests; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT fk_approval_requests_superseded_by_request_id_approval_requests FOREIGN KEY (superseded_by_request_id) REFERENCES public.approval_requests(id) ON DELETE SET NULL;


--
-- Name: approval_steps fk_approval_steps_approval_request_id_approval_requests; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_steps
    ADD CONSTRAINT fk_approval_steps_approval_request_id_approval_requests FOREIGN KEY (approval_request_id) REFERENCES public.approval_requests(id) ON DELETE CASCADE;


--
-- Name: approval_steps fk_approval_steps_assigned_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_steps
    ADD CONSTRAINT fk_approval_steps_assigned_user_id_users FOREIGN KEY (assigned_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: approval_steps fk_approval_steps_decided_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_steps
    ADD CONSTRAINT fk_approval_steps_decided_by_user_id_users FOREIGN KEY (decided_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: approval_steps fk_approval_steps_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_steps
    ADD CONSTRAINT fk_approval_steps_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: attention_items fk_attention_items_acknowledged_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attention_items
    ADD CONSTRAINT fk_attention_items_acknowledged_by_user_id_users FOREIGN KEY (acknowledged_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: attention_items fk_attention_items_deal_id_deals; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attention_items
    ADD CONSTRAINT fk_attention_items_deal_id_deals FOREIGN KEY (deal_id) REFERENCES public.deals(id) ON DELETE CASCADE;


--
-- Name: attention_items fk_attention_items_escalated_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attention_items
    ADD CONSTRAINT fk_attention_items_escalated_by_user_id_users FOREIGN KEY (escalated_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: attention_items fk_attention_items_last_nudged_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attention_items
    ADD CONSTRAINT fk_attention_items_last_nudged_by_user_id_users FOREIGN KEY (last_nudged_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: attention_items fk_attention_items_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attention_items
    ADD CONSTRAINT fk_attention_items_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: attention_items fk_attention_items_owner_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attention_items
    ADD CONSTRAINT fk_attention_items_owner_user_id_users FOREIGN KEY (owner_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: attention_items fk_attention_items_quote_id_quotes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attention_items
    ADD CONSTRAINT fk_attention_items_quote_id_quotes FOREIGN KEY (quote_id) REFERENCES public.quotes(id) ON DELETE CASCADE;


--
-- Name: attention_items fk_attention_items_resolved_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attention_items
    ADD CONSTRAINT fk_attention_items_resolved_by_user_id_users FOREIGN KEY (resolved_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: audit_events fk_audit_events_actor_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT fk_audit_events_actor_user_id_users FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: audit_events fk_audit_events_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT fk_audit_events_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE SET NULL;


--
-- Name: billing_schedules fk_billing_schedules_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.billing_schedules
    ADD CONSTRAINT fk_billing_schedules_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: billing_schedules fk_billing_schedules_sales_order_id_sales_orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.billing_schedules
    ADD CONSTRAINT fk_billing_schedules_sales_order_id_sales_orders FOREIGN KEY (sales_order_id) REFERENCES public.sales_orders(id) ON DELETE CASCADE;


--
-- Name: billing_schedules fk_billing_schedules_sales_order_line_id_sales_order_lines; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.billing_schedules
    ADD CONSTRAINT fk_billing_schedules_sales_order_line_id_sales_order_lines FOREIGN KEY (sales_order_line_id) REFERENCES public.sales_order_lines(id) ON DELETE CASCADE;


--
-- Name: commercial_snapshots fk_commercial_snapshots_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_snapshots
    ADD CONSTRAINT fk_commercial_snapshots_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: commercial_snapshots fk_commercial_snapshots_quote_version_id_quote_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_snapshots
    ADD CONSTRAINT fk_commercial_snapshots_quote_version_id_quote_versions FOREIGN KEY (quote_version_id) REFERENCES public.quote_versions(id) ON DELETE CASCADE;


--
-- Name: contacts fk_contacts_customer_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contacts
    ADD CONSTRAINT fk_contacts_customer_organization_id_organizations FOREIGN KEY (customer_organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: contacts fk_contacts_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contacts
    ADD CONSTRAINT fk_contacts_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: contacts fk_contacts_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contacts
    ADD CONSTRAINT fk_contacts_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: credit_notes fk_credit_notes_billing_schedule_id_billing_schedules; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_notes
    ADD CONSTRAINT fk_credit_notes_billing_schedule_id_billing_schedules FOREIGN KEY (billing_schedule_id) REFERENCES public.billing_schedules(id) ON DELETE SET NULL;


--
-- Name: credit_notes fk_credit_notes_customer_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_notes
    ADD CONSTRAINT fk_credit_notes_customer_organization_id_organizations FOREIGN KEY (customer_organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: credit_notes fk_credit_notes_invoice_id_invoices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_notes
    ADD CONSTRAINT fk_credit_notes_invoice_id_invoices FOREIGN KEY (invoice_id) REFERENCES public.invoices(id) ON DELETE SET NULL;


--
-- Name: credit_notes fk_credit_notes_issued_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_notes
    ADD CONSTRAINT fk_credit_notes_issued_by_user_id_users FOREIGN KEY (issued_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: credit_notes fk_credit_notes_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_notes
    ADD CONSTRAINT fk_credit_notes_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: credit_notes fk_credit_notes_sales_order_id_sales_orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_notes
    ADD CONSTRAINT fk_credit_notes_sales_order_id_sales_orders FOREIGN KEY (sales_order_id) REFERENCES public.sales_orders(id) ON DELETE RESTRICT;


--
-- Name: customer_profiles fk_customer_profiles_customer_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_profiles
    ADD CONSTRAINT fk_customer_profiles_customer_organization_id_organizations FOREIGN KEY (customer_organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: customer_profiles fk_customer_profiles_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_profiles
    ADD CONSTRAINT fk_customer_profiles_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: customer_profiles fk_customer_profiles_primary_contact_id_contacts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_profiles
    ADD CONSTRAINT fk_customer_profiles_primary_contact_id_contacts FOREIGN KEY (primary_contact_id) REFERENCES public.contacts(id) ON DELETE SET NULL;


--
-- Name: deals fk_deals_customer_profile_id_customer_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.deals
    ADD CONSTRAINT fk_deals_customer_profile_id_customer_profiles FOREIGN KEY (customer_profile_id) REFERENCES public.customer_profiles(id) ON DELETE RESTRICT;


--
-- Name: deals fk_deals_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.deals
    ADD CONSTRAINT fk_deals_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: deals fk_deals_owner_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.deals
    ADD CONSTRAINT fk_deals_owner_user_id_users FOREIGN KEY (owner_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: deals fk_deals_primary_contact_id_contacts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.deals
    ADD CONSTRAINT fk_deals_primary_contact_id_contacts FOREIGN KEY (primary_contact_id) REFERENCES public.contacts(id) ON DELETE SET NULL;


--
-- Name: decision_impacts fk_decision_impacts_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.decision_impacts
    ADD CONSTRAINT fk_decision_impacts_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: decision_impacts fk_decision_impacts_previous_version_id_quote_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.decision_impacts
    ADD CONSTRAINT fk_decision_impacts_previous_version_id_quote_versions FOREIGN KEY (previous_version_id) REFERENCES public.quote_versions(id) ON DELETE SET NULL;


--
-- Name: decision_impacts fk_decision_impacts_product_id_products; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.decision_impacts
    ADD CONSTRAINT fk_decision_impacts_product_id_products FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE SET NULL;


--
-- Name: decision_impacts fk_decision_impacts_quote_id_quotes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.decision_impacts
    ADD CONSTRAINT fk_decision_impacts_quote_id_quotes FOREIGN KEY (quote_id) REFERENCES public.quotes(id) ON DELETE CASCADE;


--
-- Name: decision_impacts fk_decision_impacts_quote_line_id_quote_lines; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.decision_impacts
    ADD CONSTRAINT fk_decision_impacts_quote_line_id_quote_lines FOREIGN KEY (quote_line_id) REFERENCES public.quote_lines(id) ON DELETE SET NULL;


--
-- Name: decision_impacts fk_decision_impacts_quote_version_id_quote_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.decision_impacts
    ADD CONSTRAINT fk_decision_impacts_quote_version_id_quote_versions FOREIGN KEY (quote_version_id) REFERENCES public.quote_versions(id) ON DELETE CASCADE;


--
-- Name: dismissed_recommendations fk_dismissed_recommendations_dismissed_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dismissed_recommendations
    ADD CONSTRAINT fk_dismissed_recommendations_dismissed_by_user_id_users FOREIGN KEY (dismissed_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: dismissed_recommendations fk_dismissed_recommendations_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dismissed_recommendations
    ADD CONSTRAINT fk_dismissed_recommendations_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: dismissed_recommendations fk_dismissed_recommendations_product_id_products; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dismissed_recommendations
    ADD CONSTRAINT fk_dismissed_recommendations_product_id_products FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE CASCADE;


--
-- Name: dismissed_recommendations fk_dismissed_recommendations_quote_version_id_quote_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dismissed_recommendations
    ADD CONSTRAINT fk_dismissed_recommendations_quote_version_id_quote_versions FOREIGN KEY (quote_version_id) REFERENCES public.quote_versions(id) ON DELETE CASCADE;


--
-- Name: fulfillments fk_fulfillments_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fulfillments
    ADD CONSTRAINT fk_fulfillments_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: fulfillments fk_fulfillments_sales_order_id_sales_orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fulfillments
    ADD CONSTRAINT fk_fulfillments_sales_order_id_sales_orders FOREIGN KEY (sales_order_id) REFERENCES public.sales_orders(id) ON DELETE CASCADE;


--
-- Name: fulfillments fk_fulfillments_warehouse_id_warehouses; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fulfillments
    ADD CONSTRAINT fk_fulfillments_warehouse_id_warehouses FOREIGN KEY (warehouse_id) REFERENCES public.warehouses(id) ON DELETE RESTRICT;


--
-- Name: idempotency_keys fk_idempotency_keys_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.idempotency_keys
    ADD CONSTRAINT fk_idempotency_keys_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: idempotency_keys fk_idempotency_keys_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.idempotency_keys
    ADD CONSTRAINT fk_idempotency_keys_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: inventory_allocations fk_inventory_allocations_allocated_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory_allocations
    ADD CONSTRAINT fk_inventory_allocations_allocated_by_user_id_users FOREIGN KEY (allocated_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: inventory_allocations fk_inventory_allocations_fulfillment_id_fulfillments; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory_allocations
    ADD CONSTRAINT fk_inventory_allocations_fulfillment_id_fulfillments FOREIGN KEY (fulfillment_id) REFERENCES public.fulfillments(id) ON DELETE SET NULL;


--
-- Name: inventory_allocations fk_inventory_allocations_inventory_id_inventory; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory_allocations
    ADD CONSTRAINT fk_inventory_allocations_inventory_id_inventory FOREIGN KEY (inventory_id) REFERENCES public.inventory(id) ON DELETE SET NULL;


--
-- Name: inventory_allocations fk_inventory_allocations_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory_allocations
    ADD CONSTRAINT fk_inventory_allocations_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: inventory_allocations fk_inventory_allocations_product_id_products; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory_allocations
    ADD CONSTRAINT fk_inventory_allocations_product_id_products FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE RESTRICT;


--
-- Name: inventory_allocations fk_inventory_allocations_sales_order_id_sales_orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory_allocations
    ADD CONSTRAINT fk_inventory_allocations_sales_order_id_sales_orders FOREIGN KEY (sales_order_id) REFERENCES public.sales_orders(id) ON DELETE CASCADE;


--
-- Name: inventory_allocations fk_inventory_allocations_sales_order_line_id_sales_order_lines; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory_allocations
    ADD CONSTRAINT fk_inventory_allocations_sales_order_line_id_sales_order_lines FOREIGN KEY (sales_order_line_id) REFERENCES public.sales_order_lines(id) ON DELETE CASCADE;


--
-- Name: inventory_allocations fk_inventory_allocations_warehouse_id_warehouses; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory_allocations
    ADD CONSTRAINT fk_inventory_allocations_warehouse_id_warehouses FOREIGN KEY (warehouse_id) REFERENCES public.warehouses(id) ON DELETE RESTRICT;


--
-- Name: inventory fk_inventory_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory
    ADD CONSTRAINT fk_inventory_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: inventory fk_inventory_product_id_products; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory
    ADD CONSTRAINT fk_inventory_product_id_products FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE CASCADE;


--
-- Name: inventory fk_inventory_product_variant_id_product_variants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory
    ADD CONSTRAINT fk_inventory_product_variant_id_product_variants FOREIGN KEY (product_variant_id) REFERENCES public.product_variants(id) ON DELETE CASCADE;


--
-- Name: inventory fk_inventory_warehouse_id_warehouses; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory
    ADD CONSTRAINT fk_inventory_warehouse_id_warehouses FOREIGN KEY (warehouse_id) REFERENCES public.warehouses(id) ON DELETE CASCADE;


--
-- Name: invoices fk_invoices_billing_schedule_id_billing_schedules; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT fk_invoices_billing_schedule_id_billing_schedules FOREIGN KEY (billing_schedule_id) REFERENCES public.billing_schedules(id) ON DELETE SET NULL;


--
-- Name: invoices fk_invoices_customer_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT fk_invoices_customer_organization_id_organizations FOREIGN KEY (customer_organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: invoices fk_invoices_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT fk_invoices_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: invoices fk_invoices_sales_order_id_sales_orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT fk_invoices_sales_order_id_sales_orders FOREIGN KEY (sales_order_id) REFERENCES public.sales_orders(id) ON DELETE RESTRICT;


--
-- Name: negotiation_messages fk_negotiation_messages_author_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.negotiation_messages
    ADD CONSTRAINT fk_negotiation_messages_author_user_id_users FOREIGN KEY (author_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: negotiation_messages fk_negotiation_messages_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.negotiation_messages
    ADD CONSTRAINT fk_negotiation_messages_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: negotiation_messages fk_negotiation_messages_quote_line_id_quote_lines; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.negotiation_messages
    ADD CONSTRAINT fk_negotiation_messages_quote_line_id_quote_lines FOREIGN KEY (quote_line_id) REFERENCES public.quote_lines(id) ON DELETE SET NULL;


--
-- Name: negotiation_messages fk_negotiation_messages_quote_version_id_quote_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.negotiation_messages
    ADD CONSTRAINT fk_negotiation_messages_quote_version_id_quote_versions FOREIGN KEY (quote_version_id) REFERENCES public.quote_versions(id) ON DELETE CASCADE;


--
-- Name: negotiation_messages fk_negotiation_messages_thread_id_negotiation_threads; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.negotiation_messages
    ADD CONSTRAINT fk_negotiation_messages_thread_id_negotiation_threads FOREIGN KEY (thread_id) REFERENCES public.negotiation_threads(id) ON DELETE CASCADE;


--
-- Name: negotiation_messages fk_negotiation_messages_triggered_version_id_quote_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.negotiation_messages
    ADD CONSTRAINT fk_negotiation_messages_triggered_version_id_quote_versions FOREIGN KEY (triggered_version_id) REFERENCES public.quote_versions(id) ON DELETE SET NULL;


--
-- Name: negotiation_threads fk_negotiation_threads_customer_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.negotiation_threads
    ADD CONSTRAINT fk_negotiation_threads_customer_organization_id_organizations FOREIGN KEY (customer_organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: negotiation_threads fk_negotiation_threads_opened_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.negotiation_threads
    ADD CONSTRAINT fk_negotiation_threads_opened_by_user_id_users FOREIGN KEY (opened_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: negotiation_threads fk_negotiation_threads_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.negotiation_threads
    ADD CONSTRAINT fk_negotiation_threads_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: negotiation_threads fk_negotiation_threads_quote_id_quotes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.negotiation_threads
    ADD CONSTRAINT fk_negotiation_threads_quote_id_quotes FOREIGN KEY (quote_id) REFERENCES public.quotes(id) ON DELETE CASCADE;


--
-- Name: negotiation_threads fk_negotiation_threads_quote_version_id_quote_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.negotiation_threads
    ADD CONSTRAINT fk_negotiation_threads_quote_version_id_quote_versions FOREIGN KEY (quote_version_id) REFERENCES public.quote_versions(id) ON DELETE CASCADE;


--
-- Name: organization_settings fk_organization_settings_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_settings
    ADD CONSTRAINT fk_organization_settings_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: payments fk_payments_invoice_id_invoices; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT fk_payments_invoice_id_invoices FOREIGN KEY (invoice_id) REFERENCES public.invoices(id) ON DELETE RESTRICT;


--
-- Name: payments fk_payments_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT fk_payments_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: payments fk_payments_recorded_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT fk_payments_recorded_by_user_id_users FOREIGN KEY (recorded_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: policies fk_policies_customer_profile_id_customer_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policies
    ADD CONSTRAINT fk_policies_customer_profile_id_customer_profiles FOREIGN KEY (customer_profile_id) REFERENCES public.customer_profiles(id) ON DELETE CASCADE;


--
-- Name: policies fk_policies_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policies
    ADD CONSTRAINT fk_policies_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: policy_results fk_policy_results_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policy_results
    ADD CONSTRAINT fk_policy_results_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: policy_results fk_policy_results_policy_id_policies; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policy_results
    ADD CONSTRAINT fk_policy_results_policy_id_policies FOREIGN KEY (policy_id) REFERENCES public.policies(id) ON DELETE SET NULL;


--
-- Name: policy_results fk_policy_results_quote_line_id_quote_lines; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policy_results
    ADD CONSTRAINT fk_policy_results_quote_line_id_quote_lines FOREIGN KEY (quote_line_id) REFERENCES public.quote_lines(id) ON DELETE CASCADE;


--
-- Name: policy_results fk_policy_results_quote_version_id_quote_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policy_results
    ADD CONSTRAINT fk_policy_results_quote_version_id_quote_versions FOREIGN KEY (quote_version_id) REFERENCES public.quote_versions(id) ON DELETE CASCADE;


--
-- Name: price_lists fk_price_lists_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.price_lists
    ADD CONSTRAINT fk_price_lists_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: product_variants fk_product_variants_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_variants
    ADD CONSTRAINT fk_product_variants_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: product_variants fk_product_variants_product_id_products; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_variants
    ADD CONSTRAINT fk_product_variants_product_id_products FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE CASCADE;


--
-- Name: products fk_products_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT fk_products_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: quote_lines fk_quote_lines_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quote_lines
    ADD CONSTRAINT fk_quote_lines_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: quote_lines fk_quote_lines_product_id_products; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quote_lines
    ADD CONSTRAINT fk_quote_lines_product_id_products FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE RESTRICT;


--
-- Name: quote_lines fk_quote_lines_product_variant_id_product_variants; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quote_lines
    ADD CONSTRAINT fk_quote_lines_product_variant_id_product_variants FOREIGN KEY (product_variant_id) REFERENCES public.product_variants(id) ON DELETE SET NULL;


--
-- Name: quote_lines fk_quote_lines_quote_version_id_quote_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quote_lines
    ADD CONSTRAINT fk_quote_lines_quote_version_id_quote_versions FOREIGN KEY (quote_version_id) REFERENCES public.quote_versions(id) ON DELETE CASCADE;


--
-- Name: quote_lines fk_quote_lines_source_line_id_quote_lines; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quote_lines
    ADD CONSTRAINT fk_quote_lines_source_line_id_quote_lines FOREIGN KEY (source_line_id) REFERENCES public.quote_lines(id) ON DELETE SET NULL;


--
-- Name: quote_versions fk_quote_versions_created_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quote_versions
    ADD CONSTRAINT fk_quote_versions_created_by_user_id_users FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: quote_versions fk_quote_versions_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quote_versions
    ADD CONSTRAINT fk_quote_versions_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: quote_versions fk_quote_versions_parent_version_id_quote_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quote_versions
    ADD CONSTRAINT fk_quote_versions_parent_version_id_quote_versions FOREIGN KEY (parent_version_id) REFERENCES public.quote_versions(id) ON DELETE SET NULL;


--
-- Name: quote_versions fk_quote_versions_quote_id_quotes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quote_versions
    ADD CONSTRAINT fk_quote_versions_quote_id_quotes FOREIGN KEY (quote_id) REFERENCES public.quotes(id) ON DELETE CASCADE;


--
-- Name: quotes fk_quotes_created_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quotes
    ADD CONSTRAINT fk_quotes_created_by_user_id_users FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: quotes fk_quotes_deal_id_deals; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quotes
    ADD CONSTRAINT fk_quotes_deal_id_deals FOREIGN KEY (deal_id) REFERENCES public.deals(id) ON DELETE CASCADE;


--
-- Name: quotes fk_quotes_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quotes
    ADD CONSTRAINT fk_quotes_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: sales_order_lines fk_sales_order_lines_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_order_lines
    ADD CONSTRAINT fk_sales_order_lines_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: sales_order_lines fk_sales_order_lines_product_id_products; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_order_lines
    ADD CONSTRAINT fk_sales_order_lines_product_id_products FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE RESTRICT;


--
-- Name: sales_order_lines fk_sales_order_lines_quote_line_id_quote_lines; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_order_lines
    ADD CONSTRAINT fk_sales_order_lines_quote_line_id_quote_lines FOREIGN KEY (quote_line_id) REFERENCES public.quote_lines(id) ON DELETE RESTRICT;


--
-- Name: sales_order_lines fk_sales_order_lines_sales_order_id_sales_orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_order_lines
    ADD CONSTRAINT fk_sales_order_lines_sales_order_id_sales_orders FOREIGN KEY (sales_order_id) REFERENCES public.sales_orders(id) ON DELETE CASCADE;


--
-- Name: sales_orders fk_sales_orders_confirmed_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_orders
    ADD CONSTRAINT fk_sales_orders_confirmed_by_user_id_users FOREIGN KEY (confirmed_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: sales_orders fk_sales_orders_customer_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_orders
    ADD CONSTRAINT fk_sales_orders_customer_organization_id_organizations FOREIGN KEY (customer_organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: sales_orders fk_sales_orders_customer_profile_id_customer_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_orders
    ADD CONSTRAINT fk_sales_orders_customer_profile_id_customer_profiles FOREIGN KEY (customer_profile_id) REFERENCES public.customer_profiles(id) ON DELETE RESTRICT;


--
-- Name: sales_orders fk_sales_orders_deal_id_deals; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_orders
    ADD CONSTRAINT fk_sales_orders_deal_id_deals FOREIGN KEY (deal_id) REFERENCES public.deals(id) ON DELETE RESTRICT;


--
-- Name: sales_orders fk_sales_orders_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_orders
    ADD CONSTRAINT fk_sales_orders_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: sales_orders fk_sales_orders_quote_id_quotes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_orders
    ADD CONSTRAINT fk_sales_orders_quote_id_quotes FOREIGN KEY (quote_id) REFERENCES public.quotes(id) ON DELETE RESTRICT;


--
-- Name: sales_orders fk_sales_orders_quote_version_id_quote_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_orders
    ADD CONSTRAINT fk_sales_orders_quote_version_id_quote_versions FOREIGN KEY (quote_version_id) REFERENCES public.quote_versions(id) ON DELETE RESTRICT;


--
-- Name: sales_team_members fk_sales_team_members_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_team_members
    ADD CONSTRAINT fk_sales_team_members_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: sales_team_members fk_sales_team_members_sales_team_id_sales_teams; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_team_members
    ADD CONSTRAINT fk_sales_team_members_sales_team_id_sales_teams FOREIGN KEY (sales_team_id) REFERENCES public.sales_teams(id) ON DELETE CASCADE;


--
-- Name: sales_team_members fk_sales_team_members_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_team_members
    ADD CONSTRAINT fk_sales_team_members_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: sales_teams fk_sales_teams_manager_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_teams
    ADD CONSTRAINT fk_sales_teams_manager_user_id_users FOREIGN KEY (manager_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: sales_teams fk_sales_teams_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sales_teams
    ADD CONSTRAINT fk_sales_teams_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: users fk_users_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT fk_users_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- Name: users fk_users_role_id_roles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT fk_users_role_id_roles FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE RESTRICT;


--
-- Name: warehouses fk_warehouses_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.warehouses
    ADD CONSTRAINT fk_warehouses_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;


--
-- PostgreSQL database dump complete
--

\unrestrict 6UrunfRJyGCLYh2SJsLbCqrHFrMa1Afk1XeywrbV3Mlcw2HG74BMEXlOnRRFNPQ

