"""Conditional migration: add M2M to merankabandi.Indicator if merankabandi is installed."""
from django.apps import apps as django_apps
from django.db import migrations, models


def merankabandi_installed():
    try:
        django_apps.get_app_config('merankabandi')
        return True
    except LookupError:
        return False


class Migration(migrations.Migration):

    dependencies = [
        ("activity", "0001_initial"),
    ]

    if merankabandi_installed():
        dependencies.append(("merankabandi", "0013_precollecte_pmtformula_selectionquota"))

    operations = [
        migrations.AddField(
            model_name="activite",
            name="indicators",
            field=models.ManyToManyField(
                blank=True,
                related_name="activities",
                to="merankabandi.indicator",
            ),
        ),
    ] if merankabandi_installed() else []
