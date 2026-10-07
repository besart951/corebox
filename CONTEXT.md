# Application Foundation

Reusable application capabilities shared by independently deployed customer applications.

## Language

**User**: A person's application identity and profile. Credentials are separate from this identity.
_Avoid_: Account when referring to a profile.

**Organization**: A tenant within a consuming application, containing memberships and teams.
_Avoid_: Customer when referring to authorization scope.

**Team**: A named subset of an organization's members.
_Avoid_: Tenant when referring to a team.

**Membership**: A user's relationship to an organization or one of its teams, including role and state.

**Customer**: The billing relationship between an organization and its payment provider.
_Avoid_: User when referring to payment-provider customer records.

**Session family**: One authenticated session and all generations of its rotating refresh token.

**Notification**: The content and intended recipient of an application communication.

**Delivery**: One queued attempt stream to transport a notification through an external channel.

**Reminder**: A scheduled trigger associated with an application entity.
