from django.db import migrations, models


def drop_duplicate_stations(apps, schema_editor):
    """Collapse duplicate rows left behind by the previous loader.

    The old ``update_or_create`` call passed the price as a lookup rather than a
    default, so every price change inserted a new row. The unique constraint
    added below cannot be applied until those are gone.
    """
    FuelStation = apps.get_model("api", "FuelStation")
    seen: set[tuple] = set()
    duplicate_ids: list[int] = []
    identity = ("station_name", "city", "state", "zip_code", "fuel_type")
    for row in FuelStation.objects.order_by("-id").values_list("id", *identity):
        key = row[1:]
        if key in seen:
            duplicate_ids.append(row[0])
        else:
            seen.add(key)
    if duplicate_ids:
        FuelStation.objects.filter(id__in=duplicate_ids).delete()


class Migration(migrations.Migration):
    dependencies = [("api", "0001_initial")]

    operations = [
        migrations.AlterModelOptions(
            name="fuelstation",
            options={"ordering": ["station_name", "city"]},
        ),
        migrations.AlterField(
            model_name="fuelstation",
            name="city",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AlterField(
            model_name="fuelstation",
            name="state",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AlterField(
            model_name="fuelstation",
            name="zip_code",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AlterField(
            model_name="fuelstation",
            name="fuel_type",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.RunPython(drop_duplicate_stations, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="fuelstation",
            constraint=models.UniqueConstraint(
                fields=("station_name", "city", "state", "zip_code", "fuel_type"),
                name="uniq_fuel_station_identity",
            ),
        ),
        migrations.AddIndex(
            model_name="fuelstation",
            index=models.Index(
                fields=["latitude", "longitude"], name="idx_station_lat_lng"
            ),
        ),
        migrations.AddIndex(
            model_name="fuelstation",
            index=models.Index(fields=["price_per_gallon"], name="idx_station_price"),
        ),
    ]
