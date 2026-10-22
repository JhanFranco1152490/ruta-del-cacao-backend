from django.apps import AppConfig


class HealthConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.health"

    def ready(self):
        # El resultado del monitoreo y la detección que atiende un control, en la representación de
        # la actividad. Las rutas de precarga van desde la actividad.
        from apps.common.contracts.activity_details import register_activity_details
        from apps.common.contracts.alerts import register_evaluator

        from .alerts import evaluate
        from .serializers import ActivityMonitoringSerializer, ControlOfSerializer

        # Los avisos de los controles que alguien pidió y nadie atendió.
        register_evaluator("health", evaluate)

        register_activity_details(
            fields={
                "monitoring": lambda: ActivityMonitoringSerializer(
                    source="phytosanitary_monitoring", allow_null=True, read_only=True
                ),
                "control_of": lambda: ControlOfSerializer(
                    source="phytosanitary_treatment", allow_null=True, read_only=True
                ),
            },
            prefetch=[
                "phytosanitary_monitoring__detections__pest_disease",
                "phytosanitary_monitoring__detections__treatments__activity",
                "phytosanitary_monitoring__detections__control_requested_by",
                "phytosanitary_monitoring__detections__control_dismissed_by",
                "phytosanitary_treatment__detection__pest_disease",
                "phytosanitary_treatment__detection__monitoring__activity",
                "phytosanitary_treatment__planned_input",
                "phytosanitary_monitoring__evidence",
                "phytosanitary_treatment__evidence",
            ],
        )
