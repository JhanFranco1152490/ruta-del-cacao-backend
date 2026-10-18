from django.db import migrations


def number_existing_plots(apps, schema_editor):
    # Cada finca numera sus parcelas por fecha de creación y, a igualdad, por id, y su contador
    # queda en el último número asignado.
    Plot = apps.get_model("plots", "Plot")
    Farm = apps.get_model("farms", "Farm")
    farms = []
    for farm in Farm.objects.all():
        plots = list(Plot.objects.filter(farm_id=farm.pk).order_by("created_at", "id"))
        for number, plot in enumerate(plots, start=1):
            plot.number = number
        Plot.objects.bulk_update(plots, ["number"])
        farm.plot_sequence = len(plots)
        farms.append(farm)
    Farm.objects.bulk_update(farms, ["plot_sequence"])


class Migration(migrations.Migration):
    """Segundo paso: numera lo existente, separado del cambio de esquema porque PostgreSQL no
    deja alterar una tabla con filas modificadas en la misma transacción."""

    dependencies = [
        ("plots", "0003_plot_number"),
        ("farms", "0009_farm_plot_sequence"),
    ]

    operations = [
        migrations.RunPython(number_existing_plots, migrations.RunPython.noop),
    ]
