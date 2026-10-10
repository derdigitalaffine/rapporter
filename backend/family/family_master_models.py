import uuid
from django.db import models
from .models import Family, TimestampedModel


class FamilyMasterData(TimestampedModel):
    """Private, family-scoped master data kept separate from the technical tenant identity."""

    family = models.OneToOneField(Family, on_delete=models.CASCADE, related_name="master_data")
    image_key = models.CharField(max_length=64, blank=True)
    image_version = models.UUIDField(default=uuid.uuid4, editable=False)
    address_street = models.CharField(max_length=160, blank=True)
    address_house_number = models.CharField(max_length=32, blank=True)
    address_postal_code = models.CharField(max_length=32, blank=True)
    address_city = models.CharField(max_length=120, blank=True)
    address_region = models.CharField(max_length=120, blank=True)
    address_country_code = models.CharField(max_length=2, blank=True)

    class Meta:
        verbose_name = "family master data"
        verbose_name_plural = "family master data"

    def address_payload(self):
        return {
            "street": self.address_street,
            "house_number": self.address_house_number,
            "postal_code": self.address_postal_code,
            "city": self.address_city,
            "region": self.address_region,
            "country_code": self.address_country_code,
        }

    def location_context(self):
        """Stable source contract for future weather/public-warning integration defaults.

        Coordinates intentionally stay empty here. A later geocoding feature can enrich this
        context without making FamilyOS silently rewrite existing integration configuration.
        """
        address = self.address_payload()
        return {
            "source": "family_address",
            "address": address,
            "has_address": any(bool(value) for value in address.values()),
            "ready_for_geocoding": bool(address["city"] and address["country_code"]),
            "coordinates": None,
        }
