"""Django admin registration for the station catalogue."""

from django.contrib import admin

from .models import FuelStation


@admin.register(FuelStation)
class FuelStationAdmin(admin.ModelAdmin):
    list_display = ("station_name", "city", "state", "fuel_type", "price_per_gallon")
    list_filter = ("state", "fuel_type")
    search_fields = ("station_name", "city", "zip_code")
    ordering = ("price_per_gallon",)
