import uuid

from django.conf import settings
from django.db import models


class BabyBaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class FamilyModuleSetting(BabyBaseModel):
    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="module_settings")
    module_key = models.CharField(max_length=64)
    enabled = models.BooleanField(default=False)
    show_in_main_navigation = models.BooleanField(default=False)
    settings = models.JSONField(default=dict, blank=True)
    enabled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="enabled_family_modules")
    enabled_at = models.DateTimeField(null=True, blank=True)
    disabled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["family", "module_key"], name="baby_family_module_unique")]


class CareCircleAccess(BabyBaseModel):
    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="baby_care_circle")
    membership = models.ForeignKey("family.Membership", on_delete=models.CASCADE, related_name="baby_care_access")
    can_view_pregnancy = models.BooleanField(default=False)
    can_log_care = models.BooleanField(default=False)
    can_view_growth_development = models.BooleanField(default=False)
    is_guardian = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["family", "membership"], name="baby_care_circle_member_unique")]


class PregnancyJourney(BabyBaseModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        BIRTH_COMPLETED = "birth_completed", "Birth completed"
        ARCHIVED = "archived", "Archived"
        ENDED = "ended", "Ended"

    class EstimatedFrom(models.TextChoices):
        CLINICIAN = "clinician", "Clinician"
        LMP = "lmp", "LMP"
        MANUAL = "manual", "Manual"

    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="pregnancy_journeys")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    expected_due_date = models.DateField()
    estimated_from = models.CharField(max_length=16, choices=EstimatedFrom.choices, default=EstimatedFrom.MANUAL)
    start_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    weekly_notification_enabled = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="pregnancy_journeys_created")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["family", "status"], name="baby_pregnancy_status_idx")]


class PregnancyBaby(BabyBaseModel):
    class Status(models.TextChoices):
        EXPECTED = "expected", "Expected"
        BORN = "born", "Born"
        ARCHIVED = "archived", "Archived"

    pregnancy = models.ForeignKey(PregnancyJourney, on_delete=models.CASCADE, related_name="expected_babies")
    stable_label = models.CharField(max_length=32)
    display_name = models.CharField(max_length=80, blank=True)
    order_index = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.EXPECTED)

    class Meta:
        ordering = ["order_index", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["pregnancy", "order_index"], name="baby_pregnancy_order_unique"),
            models.UniqueConstraint(fields=["pregnancy", "stable_label"], name="baby_pregnancy_label_unique"),
        ]


class BabyProfile(BabyBaseModel):
    class ReferenceSex(models.TextChoices):
        FEMALE = "female", "Female"
        MALE = "male", "Male"
        UNSPECIFIED = "unspecified", "Unspecified"

    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="baby_profiles")
    membership = models.OneToOneField("family.Membership", null=True, blank=True, on_delete=models.PROTECT, related_name="managed_baby_profile")
    source_pregnancy = models.ForeignKey(PregnancyJourney, null=True, blank=True, on_delete=models.SET_NULL, related_name="baby_profiles")
    source_pregnancy_baby = models.OneToOneField(PregnancyBaby, null=True, blank=True, on_delete=models.SET_NULL, related_name="baby_profile")
    client_identity_key = models.UUIDField(null=True, blank=True, unique=True)
    display_name = models.CharField(max_length=80)
    birth_date = models.DateField()
    birth_time = models.TimeField(null=True, blank=True)
    gestational_age_weeks = models.PositiveSmallIntegerField(null=True, blank=True)
    gestational_age_days = models.PositiveSmallIntegerField(null=True, blank=True)
    birth_weight_g = models.PositiveIntegerField(null=True, blank=True)
    birth_length_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    birth_head_circumference_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    growth_reference_sex = models.CharField(max_length=16, choices=ReferenceSex.choices, default=ReferenceSex.UNSPECIFIED)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="baby_profiles_created")

    class Meta:
        ordering = ["birth_date", "created_at"]
        indexes = [models.Index(fields=["family", "active"], name="baby_profile_active_idx")]


class ManagedChildGuardian(BabyBaseModel):
    baby = models.ForeignKey(BabyProfile, on_delete=models.CASCADE, related_name="guardians")
    membership = models.ForeignKey("family.Membership", on_delete=models.CASCADE, related_name="managed_children")
    can_manage_account = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["baby", "membership"], name="baby_guardian_member_unique")]


class PregnancyUtilitySession(BabyBaseModel):
    class Kind(models.TextChoices):
        KICK = "kick", "Kick counter"
        CONTRACTION = "contraction", "Contraction"

    pregnancy = models.ForeignKey(PregnancyJourney, on_delete=models.CASCADE, related_name="utility_sessions")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    value = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    client_event_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        constraints = [models.UniqueConstraint(fields=["pregnancy", "client_event_id"], name="baby_pregnancy_session_client_unique")]
        indexes = [models.Index(fields=["pregnancy", "kind", "started_at"], name="baby_pregnancy_session_idx")]


class PregnancyJournalEntry(BabyBaseModel):
    pregnancy = models.ForeignKey(PregnancyJourney, on_delete=models.CASCADE, related_name="journal_entries")
    pregnancy_baby = models.ForeignKey(PregnancyBaby, null=True, blank=True, on_delete=models.SET_NULL, related_name="journal_entries")
    entry_date = models.DateField()
    note = models.TextField(blank=True)
    media_key = models.CharField(max_length=180, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-entry_date", "-created_at"]


class BabyCareLog(BabyBaseModel):
    class Kind(models.TextChoices):
        BREASTFEED = "breastfeed", "Breastfeed"
        BOTTLE = "bottle", "Bottle"
        PUMP = "pump", "Pump"
        DIAPER = "diaper", "Diaper"
        SLEEP = "sleep", "Sleep"
        MEDICATION = "medication", "Medication"
        TEMPERATURE = "temperature", "Temperature"
        NOTE = "note", "Note"

    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="baby_care_logs")
    baby = models.ForeignKey(BabyProfile, on_delete=models.CASCADE, related_name="care_logs")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    started_at = models.DateTimeField(db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    value = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="baby_care_logs_created")
    client_event_id = models.UUIDField(null=True, blank=True)
    corrected_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-started_at", "-created_at"]
        constraints = [models.UniqueConstraint(fields=["baby", "client_event_id"], name="baby_care_client_event_unique")]
        indexes = [models.Index(fields=["baby", "kind", "started_at"], name="baby_care_kind_time_idx")]


class BabyGrowthMeasurement(BabyBaseModel):
    class Source(models.TextChoices):
        HOME = "home", "Home"
        MIDWIFE = "midwife", "Midwife"
        PEDIATRICIAN = "pediatrician", "Pediatrician"
        CLINIC = "clinic", "Clinic"
        OTHER = "other", "Other"

    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="baby_growth_measurements")
    baby = models.ForeignKey(BabyProfile, on_delete=models.CASCADE, related_name="growth_measurements")
    measured_at = models.DateTimeField(db_index=True)
    weight_g = models.PositiveIntegerField(null=True, blank=True)
    length_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    head_circumference_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.HOME)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["measured_at", "created_at"]
        indexes = [models.Index(fields=["baby", "measured_at"], name="baby_growth_time_idx")]


class BabyGrowthReferenceSetting(BabyBaseModel):
    baby = models.OneToOneField(BabyProfile, on_delete=models.CASCADE, related_name="growth_reference")
    reference_key = models.CharField(max_length=48, default="who_2006")
    reference_version = models.CharField(max_length=48, default="WHO Child Growth Standards 2006")
    corrected_age_enabled = models.BooleanField(default=False)


class DevelopmentReference(BabyBaseModel):
    source_key = models.CharField(max_length=48)
    source_version = models.CharField(max_length=48)
    milestone_key = models.CharField(max_length=96)
    age_month_start = models.PositiveSmallIntegerField()
    age_month_end = models.PositiveSmallIntegerField()
    category = models.CharField(max_length=32)
    localized_text = models.JSONField(default=dict)
    source_url = models.URLField(blank=True)

    class Meta:
        ordering = ["age_month_start", "category", "milestone_key"]
        constraints = [models.UniqueConstraint(fields=["source_key", "source_version", "milestone_key"], name="baby_development_ref_unique")]


class DevelopmentObservation(BabyBaseModel):
    class State(models.TextChoices):
        OBSERVED = "observed", "Observed"
        NOT_OBSERVED = "not_observed", "Not observed"
        LATER = "later", "Later"

    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="baby_development_observations")
    baby = models.ForeignKey(BabyProfile, on_delete=models.CASCADE, related_name="development_observations")
    milestone_key = models.CharField(max_length=96, blank=True)
    title = models.CharField(max_length=160, blank=True)
    observed_at = models.DateTimeField(null=True, blank=True)
    state = models.CharField(max_length=20, choices=State.choices, default=State.OBSERVED)
    note = models.TextField(blank=True)
    media_key = models.CharField(max_length=180, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-observed_at", "-created_at"]
        indexes = [models.Index(fields=["baby", "state"], name="baby_development_state_idx")]


class AppointmentQuestion(BabyBaseModel):
    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="baby_appointment_questions")
    baby = models.ForeignKey(BabyProfile, on_delete=models.CASCADE, related_name="appointment_questions")
    event = models.ForeignKey("family.FamilyEvent", on_delete=models.CASCADE, related_name="baby_questions")
    text = models.TextField()
    answered_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["created_at"]


class CareHandoverNote(BabyBaseModel):
    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="baby_handover_notes")
    baby = models.ForeignKey(BabyProfile, on_delete=models.CASCADE, related_name="handover_notes")
    from_at = models.DateTimeField()
    to_at = models.DateTimeField()
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-to_at"]


class HandoverRead(BabyBaseModel):
    handover = models.ForeignKey(CareHandoverNote, on_delete=models.CASCADE, related_name="reads")
    membership = models.ForeignKey("family.Membership", on_delete=models.CASCADE, related_name="baby_handover_reads")
    read_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["handover", "membership"], name="baby_handover_read_unique")]


class BabyViewState(BabyBaseModel):
    baby = models.ForeignKey(BabyProfile, on_delete=models.CASCADE, related_name="view_states")
    membership = models.ForeignKey("family.Membership", on_delete=models.CASCADE, related_name="baby_view_states")
    last_viewed_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["baby", "membership"], name="baby_view_state_unique")]


class ReportExportAudit(BabyBaseModel):
    baby = models.ForeignKey(BabyProfile, on_delete=models.CASCADE, related_name="report_exports")
    membership = models.ForeignKey("family.Membership", on_delete=models.CASCADE, related_name="baby_report_exports")
    export_format = models.CharField(max_length=16)
    sections = models.JSONField(default=list)
    range_start = models.DateTimeField()
    range_end = models.DateTimeField()
