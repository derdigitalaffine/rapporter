# Native chat and navigation baseline (#599)

The current navigation follows merged #602: five visible primary roots (Today,
To-dos, Shopping, Calendar, More) plus the global Messages header entry. The older
six-visible-roots requirement in #599 is superseded by that explicit decision.
The header entry has a translated accessible name/unread count and a 44px target.

Global Create's Message shortcut uses the existing native family conversation for
the currently selected family. It only selects a writable family channel and
focuses the composer; it sends nothing automatically. The transient compose URL
parameter is removed after selection. A missing writable family channel never
falls back to a personal chat, another family, or the read-only system channel.
The existing family role and server permission rules remain authoritative.

Family and System are native messenger channels. System messages remain read
only, with canonical read receipts. Old FamilyInbox composer/audience/filter
assertions are replaced with native channel regression coverage, not restored UI.

Message-menu actions stay readable before hover and retain 44px targets. Tinted
bubble metadata consumes the existing ink token for WCAG contrast. Chat state and
personal consent behavior stay owned by the existing Messenger domain.

The ui-baseline-regressions workflow runs both browser projects for native chat,
message capture, visible navigation, history/back routes and responsive layout.
Full CI and the Action compatibility workflow remain enabled. Independent existing
full-CI failures are tracked explicitly; focused green is not a claim of global
green or a waiver of the parent issue's remaining release gate.

## Current shell and language follow-up

The current product contract is five primary roots plus the header Messenger
shortcut. Native family/system chats replaced legacy family notices. The existing
ui-baseline-regressions workflow covers their permissions, message retry identity,
contrast, responsive layouts and keyboard behavior on mobile and desktop.

This follow-up preserves that coverage and adds the shared shell/language/brand
and entitlement regressions. Page headings contain the contextual page title;
FamilyOS branding comes from the header's generated label. VIP fixtures include
the existing statistics capability instead of inventing a locked VIP feature.
Both existing language controls now call the canonical explicit locale adapter
through language-options. Previously duplicated de/en handlers relied on the
global compatibility interception to reach all five locales. That adapter stays
intact for other consumers; no second list or interpretation of locales is added.

The broad repository CI remains a separate acceptance concern. At pre-change head
b5be88ed, desktop shards show 25 + 23 failures across Calendar visuals/participants,
member invitation/profile/custody fixtures, Global Create ranking, media/cropping,
Shopping legacy/store adapters, PWA/overlay, Superadmin and Vehicles checks. This
slice does not remove those tests, change their permissions or accept new failures.
#599 remains open until the residual full-CI acceptance criterion is resolved or
explicitly scoped by the maintainer; a focused follow-up PR must use Refs #599.
