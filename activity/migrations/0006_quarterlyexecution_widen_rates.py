from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("activity", "0005_sousactivite_source"),
    ]

    operations = [
        migrations.AlterField(
            model_name="quarterlyexecution",
            name="taux_decaissement",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AlterField(
            model_name="quarterlyexecution",
            name="taux_engagement",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AlterField(
            model_name="quarterlyexecution",
            name="taux_realisation",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
    ]
