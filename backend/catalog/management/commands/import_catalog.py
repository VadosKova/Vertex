from django.core.management.base import BaseCommand, CommandError

from catalog.importing import CatalogDataError, import_catalog, load_file


class Command(BaseCommand):
    help = "Import template products with size charts from a JSON file (see catalog/data/example_catalog.json)."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Path to the JSON file")
        parser.add_argument("--dry-run", action="store_true", help="Validate and report, but write nothing")

    def handle(self, *args, **options):
        try:
            report = import_catalog(load_file(options["path"]), dry_run=options["dry_run"])
        except CatalogDataError as exc:
            lines = "\n".join(f"  - {e}" for e in exc.errors[:50])
            more = f"\n  ... and {len(exc.errors) - 50} more" if len(exc.errors) > 50 else ""
            raise CommandError(f"Nothing was imported. {len(exc.errors)} problem(s):\n{lines}{more}")
        prefix = "[dry run] would be " if options["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}imported: {report.created} created, {report.updated} updated."))