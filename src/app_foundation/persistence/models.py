"""Explicit ORM registration for migrations; not imported by domain modules."""

from app_foundation.access_control.sqlalchemy import RoleAssignmentRecord, RoleRecord
from app_foundation.auth.email import VerificationDeliveryRecord
from app_foundation.auth.oauth.state import OAuthStateRecord
from app_foundation.auth.rate_limit import RateLimitRecord
from app_foundation.auth.sqlalchemy import (
    CredentialRecord,
    MfaRecord,
    OAuthIdentityRecord,
    RefreshRecord,
    SessionRecord,
    VerificationRecord,
)
from app_foundation.billing.sqlalchemy import CustomerRecord, PaymentEventRecord, SubscriptionRecord
from app_foundation.identity.sqlalchemy import UserRecord
from app_foundation.notification.sqlalchemy import (
    DeliveryRecord,
    NotificationRecord,
    PreferenceRecord,
)
from app_foundation.observability.sqlalchemy import AuditRecordRow
from app_foundation.organization.sqlalchemy import (
    InvitationRecord,
    MembershipRecord,
    OrganizationRecord,
    TeamRecord,
)
from app_foundation.scheduling.sqlalchemy import CalendarEventRecord, ReminderRecord

__all__ = (
    "AuditRecordRow",
    "CalendarEventRecord",
    "CredentialRecord",
    "CustomerRecord",
    "DeliveryRecord",
    "InvitationRecord",
    "MembershipRecord",
    "MfaRecord",
    "NotificationRecord",
    "OAuthIdentityRecord",
    "OAuthStateRecord",
    "OrganizationRecord",
    "PaymentEventRecord",
    "PreferenceRecord",
    "RateLimitRecord",
    "RefreshRecord",
    "ReminderRecord",
    "RoleAssignmentRecord",
    "RoleRecord",
    "SessionRecord",
    "SubscriptionRecord",
    "TeamRecord",
    "UserRecord",
    "VerificationDeliveryRecord",
    "VerificationRecord",
)
