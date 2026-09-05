"""Business logic. Routers orchestrate; services decide.

Beyond the services named in the implementation plan, two were split out to
keep transaction ownership clear:

* ``quote_service``  — version lifecycle and immutability (was bundled into
  ``negotiation_service`` in the plan; separated so revision mechanics have a
  single owner).
* ``order_service``  — quote confirmation and order materialisation.
* ``idempotency``    — shared replay protection used by both.
"""
