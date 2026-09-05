"""Final self-audit — asks the dangerous questions and proves the answers.

Every check below maps to a named test in the suite. This script exists so the
answers can be reviewed in one place without reading 344 tests.

    ENVIRONMENT=test python -m scripts.self_audit
"""

from __future__ import annotations

import subprocess
import sys

#: (question, safe answer, the test that proves it)
AUDIT: tuple[tuple[str, str, str], ...] = (
    (
        "Can a sales rep approve their own quote?",
        "No — 403 SELF_APPROVAL_FORBIDDEN, and it never enters their inbox. "
        "Enforced by authorship, not role: even a MANAGER who authored the "
        "quote is refused.",
        "tests/test_approval_flow.py::test_a_manager_cannot_approve_a_quote_they_raised",
    ),
    (
        "Can a customer see internal cost?",
        "No — the portal schemas have no cost field at all, and the OpenAPI "
        "document is asserted to contain none.",
        "tests/test_negotiation.py::test_openapi_portal_schemas_declare_no_cost_or_margin",
    ),
    (
        "Can a customer see margin?",
        "No — every portal response is walked key-by-key and value-by-value "
        "for margin data.",
        "tests/test_negotiation.py::test_portal_quote_detail_is_fully_redacted",
    ),
    (
        "Can an approved quote be edited directly?",
        "No — 409 IMMUTABLE_VERSION for all 7 non-DRAFT states, on add, patch "
        "and delete.",
        "tests/test_quote_versioning.py::test_non_draft_versions_reject_line_patch",
    ),
    (
        "Can a stale approval accidentally remain valid?",
        "No — a material change marks it STALE, flags the version, opens a new "
        "request and blocks confirmation.",
        "tests/test_decision_fabric.py::test_material_revision_marks_the_previous_approval_stale",
    ),
    (
        "Can confirmation create duplicate orders?",
        "No — 5 concurrent confirmations produce exactly one order; the UNIQUE "
        "constraint on sales_orders.quote_version_id is the guarantee.",
        "tests/test_idempotency.py::test_concurrent_confirmations_create_exactly_one_order",
    ),
    (
        "Can inventory be over-allocated?",
        "No — two concurrent orders for 100 units reserve exactly 100 between "
        "them; the rest is backordered.",
        "tests/test_inventory.py::test_concurrent_allocations_cannot_over_allocate",
    ),
    (
        "Does the database itself refuse over-reservation?",
        "Yes — CHECK (quantity_reserved <= quantity_on_hand) rejects the write "
        "even if the service is bypassed.",
        "tests/test_inventory.py::test_database_refuses_over_reservation_even_if_code_is_wrong",
    ),
    (
        "Can two organizations access each other's data?",
        "No — cross-tenant reads and writes return 404 (not 403, which would "
        "confirm the id exists), and no totals appear in the body.",
        "tests/test_tenant_isolation.py::test_quote_ids_from_another_org_do_not_leak_data",
    ),
    (
        "Can a customer see another customer's quote?",
        "No — portal access requires the quote to be issued to their own "
        "organization.",
        "tests/test_tenant_isolation.py::test_customer_only_sees_quotes_issued_to_their_organization",
    ),
    (
        "Can the frontend manipulate totals?",
        "No — clients send quantity/discount only; cost is copied from the "
        "catalog and unit_cost is rejected outright.",
        "tests/test_commercial_engine.py::test_client_cannot_supply_cost",
    ),
    (
        "Can a discount violation bypass the Policy Engine?",
        "No — every line is evaluated against its own category ceiling on "
        "every recalculation.",
        "tests/test_policy_engine.py::test_each_line_is_evaluated_against_its_own_policy",
    ),
    (
        "Can a material revision bypass the Decision Fabric?",
        "No — three consecutive revisions each leave a full evaluation behind.",
        "tests/test_decision_fabric.py::test_fabric_runs_on_every_revision_without_exception",
    ),
    (
        "Can billing be created without a valid order?",
        "No — schedules derive only from sales_order_lines and there is no "
        "endpoint that creates one from nothing.",
        "tests/test_billing.py::test_billing_cannot_exist_without_an_order",
    ),
    (
        "Can important transitions happen without audit events?",
        "No — a global event subscriber writes the audit row inside the "
        "caller's transaction; all 16 required events are asserted.",
        "tests/test_audit.py::test_the_full_flow_leaves_every_required_event",
    ),
    (
        "Is money ever a float?",
        "No — 110 NUMERIC columns, zero float columns, and no float survives in "
        "any JSONB audit payload.",
        "tests/test_models.py::test_no_money_column_is_a_float",
    ),
    (
        "Can seed data be run twice safely?",
        "Yes — the second run creates nothing and disturbs no reservations.",
        "tests/test_end_to_end.py::test_seeding_twice_creates_nothing_the_second_time",
    ),
    (
        "Is approval routing ever hardcoded for the demo?",
        "No — routing comes from the required_action of the policy rows that "
        "fire. Finance is pulled in by a real 20,000 signing-authority policy, "
        "on a quote whose margin passes.",
        "tests/test_policy_engine.py::test_discount_authority_routes_to_finance_on_amount_not_margin",
    ),
    (
        "Is the 60/40 warehouse split hardcoded?",
        "No — rebalancing stock to 30/70 produces a 30/70 allocation.",
        "tests/test_inventory.py::test_split_changes_when_stock_changes",
    ),
    (
        "Is the blended risk score reproducible by hand?",
        "Yes — the test recomputes it from the documented formula and compares.",
        "tests/test_policy_engine.py::test_blended_risk_matches_the_documented_formula",
    ),
)


def main() -> int:
    print("=" * 74)
    print("DEALFLOW360 FINAL SELF-AUDIT")
    print("=" * 74)

    node_ids = [test for _q, _a, test in AUDIT]
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", *node_ids],
        capture_output=True,
        text=True,
    )
    passed = result.returncode == 0

    for index, (question, answer, test) in enumerate(AUDIT, start=1):
        mark = "✓" if passed else "?"
        print(f"\n{index:2d}. {question}")
        print(f"    [{mark}] {answer}")
        print(f"        proof: {test.split('::')[-1]}")

    print("\n" + "=" * 74)
    if passed:
        print(f"SELF-AUDIT PASSED — {len(AUDIT)} dangerous questions, all answered safely.")
    else:
        print("SELF-AUDIT FAILED — see output below")
        print(result.stdout[-4000:])
        print(result.stderr[-2000:])
    print("=" * 74)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
