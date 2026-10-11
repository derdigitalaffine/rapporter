# Travel expenses

Travel expenses are not a separate finance domain. A trip can be linked to one normal FamilyOS `ExpenseLedger` through the canonical Universal Context Link relation `expense.trip`.

## User flow

From a trip, **Reisekosten / Trip expenses** opens the existing global Expenses area in the ledger linked to that trip.

- If an active linked ledger already exists, FamilyOS reuses it.
- If no ledger exists yet, an Owner or Adult creates it only by explicitly opening Trip expenses.
- The new ledger inherits the family default ledger currency and uses the trip title as its initial name.
- Reopening Trip expenses uses the same ledger; it does not create another travel expense area.
- Guests/read-only members may open an existing linked ledger when their normal FamilyOS visibility permits it, but they cannot create the trip ledger.
- If the linked ledger was archived, FamilyOS does not silently replace it. The user must manage the archived ledger explicitly in Expenses.

The global Expenses page remains the editing surface for expenses, budgets and settlements. A trip-scoped deep link only selects the linked ledger; it does not copy or fork expense data.

## Canonical objects

```text
Trip
  -> ContextLink(relation=expense.trip)
  -> ExpenseLedger
  -> Expense / ExpenseBudget / Settlement
```

There is deliberately no `TripExpense`, travel-specific settlement table or Travel foreign key on `Expense`.

## Permissions and isolation

The server validates active family membership and that the Trip belongs to the same family before resolving or creating a link. Cross-family Trip IDs fail closed.

Creation is restricted to Owner/Adult membership. The canonical Context Link and Expense visibility rules remain authoritative; linking a ledger to a trip never broadens ACLs.

## Lifecycle

A trip expense ledger is created lazily on the first explicit Trip-expenses action. The operation is transactional and locks the Trip while checking/creating the relation so concurrent requests cannot intentionally create parallel travel ledgers.

Archiving a linked ledger preserves the relation and history. FamilyOS returns an explicit archived state rather than generating a replacement ledger behind the user's back.

## Navigation contract

The Travel Hub opens the normal Expenses page with `?ledger=<ledger-id>`. Expenses validates that the requested ledger is one of the active ledgers visible for the current family; otherwise it falls back to the normal default ledger. Changing the selected ledger updates the URL, and navigating to another FamilyOS page clears the expense-specific ledger query parameter.

## Non-goals

This integration does not add FX-rate entry, an Advanced multi-budget editor, travel-specific OCR, booking/search functionality, or a second expense UI. Those remain separate product concerns and must continue to use the canonical Expense and Document cores.
