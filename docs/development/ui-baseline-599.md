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
