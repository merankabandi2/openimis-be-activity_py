from django.core.management.base import BaseCommand
from activity.models import FundingSource


SOURCES = [
    ('BM', 'Banque Mondiale'),
    ('UE', 'Union Europeenne'),
    ('FIDA', 'Fonds International de Developpement Agricole'),
    ('BAD', 'Banque Africaine de Developpement'),
    ('ENABEL', 'Agence Belge de Developpement'),
    ('GOV', 'Gouvernement du Burundi'),
]


class Command(BaseCommand):
    help = 'Seed funding sources for PTBA (BM, UE, FIDA, BAD, ENABEL, GOV)'

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for code, name in SOURCES:
            obj, created = FundingSource.objects.update_or_create(
                code=code,
                defaults={'name': name, 'is_active': True},
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  Created: {code} - {name}"))
            else:
                updated_count += 1
                self.stdout.write(f"  Updated: {code} - {name}")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Created: {created_count}, Updated: {updated_count}"
        ))
