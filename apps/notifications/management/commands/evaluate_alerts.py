import time
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ...services.evaluate import evaluate_alerts, evaluation_date


def _day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise CommandError("La fecha va como AAAA-MM-DD.") from error


class Command(BaseCommand):
    help = (
        "Revisa las condiciones de aviso de todas las apps y guarda los avisos nuevos. Corre "
        "cada hora como tarea programada; repetirla no duplica nada."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--today",
            type=str,
            help="Evaluar como si fuera ese día (AAAA-MM-DD), para probar sin esperar.",
        )

    def handle(self, *args, **options):
        started = time.monotonic()
        now = timezone.now()
        today = _day(options["today"]) if options["today"] else evaluation_date(now)

        result = evaluate_alerts(today, now)

        # Solo conteos: ningún nombre ni dato de las personas avisadas.
        created = ", ".join(f"{name}: {count}" for name, count in result.created.items())
        self.stdout.write(
            f"Evaluación del {today}: avisos nuevos ({created or 'ninguno'}), "
            f"purgados {result.purged}, {time.monotonic() - started:.1f} s."
        )
        if result.failed:
            raise CommandError(f"Fallaron los evaluadores: {', '.join(result.failed)}.")
