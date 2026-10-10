import uuid

from django.conf import settings
from django.db import models


class PetBaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class PetCareAccess(PetBaseModel):
    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="pet_care_circle")
    membership = models.ForeignKey("family.Membership", on_delete=models.CASCADE, related_name="pet_care_access")
    can_care = models.BooleanField(default=True)
    health_manage = models.BooleanField(default=False)
    remind_medications = models.BooleanField(default=True)
    remind_prevention = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["family", "membership"], name="pet_care_circle_member_unique")]


class PetProfile(PetBaseModel):
    class Sex(models.TextChoices):
        FEMALE = "female", "Female"
        MALE = "male", "Male"
        UNKNOWN = "unknown", "Unknown"

    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="pet_profiles")
    name = models.CharField(max_length=100)
    species = models.CharField(max_length=80)
    breed = models.CharField(max_length=120, blank=True)
    sex = models.CharField(max_length=12, choices=Sex.choices, default=Sex.UNKNOWN)
    birth_date = models.DateField(null=True, blank=True)
    adoption_date = models.DateField(null=True, blank=True)
    photo_key = models.CharField(max_length=160, blank=True)
    color_description = models.CharField(max_length=240, blank=True)
    microchip_id = models.CharField(max_length=120, blank=True)
    insurance_provider = models.CharField(max_length=160, blank=True)
    insurance_number = models.CharField(max_length=160, blank=True)
    primary_vet_name = models.CharField(max_length=160, blank=True)
    primary_vet_phone = models.CharField(max_length=80, blank=True)
    emergency_contact_name = models.CharField(max_length=160, blank=True)
    emergency_contact_phone = models.CharField(max_length=80, blank=True)
    allergies = models.TextField(blank=True)
    important_notes = models.TextField(blank=True)
    quick_actions = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="pet_profiles_created")

    class Meta:
        ordering = ["name", "created_at"]
        indexes = [models.Index(fields=["family", "active"], name="pet_profile_active_idx")]


class PetCareLog(PetBaseModel):
    class Kind(models.TextChoices):
        FEED = "feed", "Feed"
        WATER = "water", "Water"
        WALK = "walk", "Walk / activity"
        TOILET = "toilet", "Toilet"
        GROOMING = "grooming", "Grooming"
        TRAINING = "training", "Training"
        MEDICATION = "medication", "Medication"
        NOTE = "note", "Note"

    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="pet_care_logs")
    pet = models.ForeignKey(PetProfile, on_delete=models.CASCADE, related_name="care_logs")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    occurred_at = models.DateTimeField(db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    value = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="pet_care_logs_created")
    external_caregiver = models.CharField(max_length=120, blank=True)
    client_event_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["-occurred_at", "-created_at"]
        constraints = [models.UniqueConstraint(fields=["pet", "client_event_id"], name="pet_care_client_event_unique")]
        indexes = [models.Index(fields=["pet", "kind", "occurred_at"], name="pet_care_kind_time_idx")]


class PetHealthEvent(PetBaseModel):
    class Kind(models.TextChoices):
        VACCINATION = "vaccination", "Vaccination"
        DEWORMING = "deworming", "Deworming"
        PARASITE = "parasite_prevention", "Parasite prevention"
        VET = "vet_visit", "Vet visit"
        DENTAL = "dental", "Dental"
        PROCEDURE = "procedure", "Procedure"
        LAB = "lab", "Lab"
        OTHER = "other", "Other"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        DOCUMENT = "document_import", "Document import"
        CALENDAR = "calendar", "Calendar"

    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="pet_health_events")
    pet = models.ForeignKey(PetProfile, on_delete=models.CASCADE, related_name="health_events")
    kind = models.CharField(max_length=32, choices=Kind.choices, default=Kind.OTHER)
    title = models.CharField(max_length=180)
    occurred_at = models.DateTimeField(null=True, blank=True)
    next_due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    provider_name = models.CharField(max_length=180, blank=True)
    note = models.TextField(blank=True)
    source = models.CharField(max_length=24, choices=Source.choices, default=Source.MANUAL)
    source_document = models.ForeignKey("PetDocument", null=True, blank=True, on_delete=models.SET_NULL, related_name="health_events")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="pet_health_events_created")

    class Meta:
        ordering = ["next_due_at", "-occurred_at", "-created_at"]
        indexes = [models.Index(fields=["pet", "kind", "next_due_at"], name="pet_health_due_idx")]


class PetMedication(PetBaseModel):
    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="pet_medications")
    pet = models.ForeignKey(PetProfile, on_delete=models.CASCADE, related_name="medications")
    name = models.CharField(max_length=180)
    instruction_text = models.TextField(blank=True)
    dose_value = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    dose_unit = models.CharField(max_length=40, blank=True)
    schedule = models.JSONField(default=dict, blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True, db_index=True)
    prescribing_provider = models.CharField(max_length=180, blank=True)
    note = models.TextField(blank=True)
    source_document = models.ForeignKey("PetDocument", null=True, blank=True, on_delete=models.SET_NULL, related_name="medications")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="pet_medications_created")

    class Meta:
        ordering = ["-active", "name", "created_at"]


class PetMedicationDose(PetBaseModel):
    class State(models.TextChoices):
        GIVEN = "given", "Given"
        SKIPPED = "skipped", "Skipped"
        MISSED = "missed", "Missed"
        CANCELED = "canceled", "Canceled"

    medication = models.ForeignKey(PetMedication, on_delete=models.CASCADE, related_name="doses")
    scheduled_for = models.DateTimeField(null=True, blank=True)
    given_at = models.DateTimeField(null=True, blank=True)
    state = models.CharField(max_length=16, choices=State.choices)
    given_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="pet_medication_doses")
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-given_at", "-scheduled_for", "-created_at"]
        indexes = [models.Index(fields=["medication", "scheduled_for"], name="pet_med_dose_time_idx")]


class PetWeightMeasurement(PetBaseModel):
    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="pet_weights")
    pet = models.ForeignKey(PetProfile, on_delete=models.CASCADE, related_name="weights")
    measured_at = models.DateTimeField(db_index=True)
    weight_kg = models.DecimalField(max_digits=8, decimal_places=3)
    source = models.CharField(max_length=120, blank=True)
    note = models.TextField(blank=True)
    source_document = models.ForeignKey("PetDocument", null=True, blank=True, on_delete=models.SET_NULL, related_name="weights")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="pet_weights_created")

    class Meta:
        ordering = ["measured_at", "created_at"]
        indexes = [models.Index(fields=["pet", "measured_at"], name="pet_weight_time_idx")]


class PetObservation(PetBaseModel):
    class Category(models.TextChoices):
        APPETITE = "appetite", "Appetite"
        ENERGY = "energy", "Energy"
        STOOL = "stool", "Stool"
        VOMITING = "vomiting", "Vomiting"
        MOBILITY = "mobility", "Mobility"
        SKIN = "skin", "Skin"
        BEHAVIOR = "behavior", "Behavior"
        OTHER = "other", "Other"

    class Severity(models.TextChoices):
        MILD = "mild", "Mild"
        MODERATE = "moderate", "Moderate"
        SEVERE = "severe", "Severe"

    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="pet_observations")
    pet = models.ForeignKey(PetProfile, on_delete=models.CASCADE, related_name="observations")
    observed_at = models.DateTimeField(db_index=True)
    category = models.CharField(max_length=24, choices=Category.choices, default=Category.OTHER)
    severity = models.CharField(max_length=16, choices=Severity.choices, blank=True)
    note = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="pet_observations_created")

    class Meta:
        ordering = ["-observed_at", "-created_at"]


class PetDocument(PetBaseModel):
    class Kind(models.TextChoices):
        VACCINATION = "vaccination_record", "Vaccination record"
        VET_REPORT = "vet_report", "Vet report"
        LAB = "lab", "Lab"
        PRESCRIPTION = "prescription", "Prescription"
        INVOICE = "invoice", "Invoice"
        INSURANCE = "insurance", "Insurance"
        REGISTRATION = "registration", "Registration"
        OTHER = "other", "Other"

    class ExtractionStatus(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        REVIEW = "review", "Review"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="pet_documents")
    pet = models.ForeignKey(PetProfile, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=32, choices=Kind.choices, default=Kind.OTHER)
    title = models.CharField(max_length=180)
    filename = models.CharField(max_length=240)
    content_type = models.CharField(max_length=80)
    content = models.BinaryField(editable=False)
    sha256 = models.CharField(max_length=64, db_index=True)
    occurred_at = models.DateField(null=True, blank=True)
    provider_name = models.CharField(max_length=180, blank=True)
    extraction_status = models.CharField(max_length=16, choices=ExtractionStatus.choices, default=ExtractionStatus.QUEUED, db_index=True)
    extraction_text = models.TextField(blank=True)
    extraction_error = models.TextField(blank=True)
    extraction_data = models.JSONField(default=dict, blank=True)
    field_confidences = models.JSONField(default=dict, blank=True)
    pinned = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="pet_documents_created")

    class Meta:
        ordering = ["-pinned", "-occurred_at", "-created_at"]
        indexes = [models.Index(fields=["pet", "kind", "occurred_at"], name="pet_document_kind_idx")]


class PetHandoverNote(PetBaseModel):
    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="pet_handover_notes")
    pet = models.ForeignKey(PetProfile, on_delete=models.CASCADE, related_name="handover_notes")
    from_at = models.DateTimeField()
    to_at = models.DateTimeField()
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="pet_handover_notes_created")

    class Meta:
        ordering = ["-to_at", "-created_at"]


class PetCareShare(PetBaseModel):
    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="pet_care_shares")
    pet = models.ForeignKey(PetProfile, on_delete=models.CASCADE, related_name="care_shares")
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    permissions = models.JSONField(default=dict, blank=True)
    label = models.CharField(max_length=120, blank=True)
    starts_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_access_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="pet_care_shares_created")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["pet", "expires_at", "revoked_at"], name="pet_share_active_idx")]


class PetReportExportAudit(PetBaseModel):
    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="pet_report_exports")
    pet = models.ForeignKey(PetProfile, on_delete=models.CASCADE, related_name="report_exports")
    membership = models.ForeignKey("family.Membership", on_delete=models.CASCADE, related_name="pet_report_exports")
    export_format = models.CharField(max_length=16)
    sections = models.JSONField(default=list)
    range_start = models.DateTimeField()
    range_end = models.DateTimeField()


class PetVetQuestion(PetBaseModel):
    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="pet_vet_questions")
    pet = models.ForeignKey(PetProfile, on_delete=models.CASCADE, related_name="vet_questions")
    question = models.TextField()
    answered_at = models.DateTimeField(null=True, blank=True)
    answer_note = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="pet_vet_questions_created")

    class Meta:
        ordering = ["answered_at", "created_at"]


class PetReminderDelivery(PetBaseModel):
    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="pet_reminder_deliveries")
    pet = models.ForeignKey(PetProfile, on_delete=models.CASCADE, related_name="reminder_deliveries")
    membership = models.ForeignKey("family.Membership", on_delete=models.CASCADE, related_name="pet_reminder_deliveries")
    topic_key = models.CharField(max_length=180)
    scheduled_for = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["membership", "topic_key", "scheduled_for"], name="pet_reminder_delivery_unique")]
        indexes = [models.Index(fields=["scheduled_for", "sent_at"], name="pet_reminder_due_idx")]
